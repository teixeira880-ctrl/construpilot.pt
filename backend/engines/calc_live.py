"""Acompanhamento do cálculo ao vivo — reservado à conta CLT Rezult (teste com o investidor).

Cada pedido ao Assistente cria uma «execução» (db.calc_live_runs) onde os motores escrevem, à medida que trabalham, o que
fizeram e PORQUÊ: ferramenta escolhida, dados oficiais lidos (com a fonte), fórmulas com os valores, decisões tomadas,
verificações (valor obtido / limite / norma / OK-KO), hipóteses e avisos. A página /acompanhamento-calculo lê estas
execuções a cada 2 s.

Sem tracer ativo (todas as outras contas) cada chamada é um no-op: nada é gravado, nenhum motor muda de comportamento.
O tracer viaja num contextvar: segue as tarefas asyncio criadas dentro do pedido e os threads de asyncio.to_thread.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
import itertools
import time
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

MAX_EVENTS = 2500
CLT_EMAILS = {"clt-rezult.demo@construpilot.pt", "clt-rezult.demo@construpilot.fr", "office@clt-rezult.com"}
TIPOS = {"etapa", "ferramenta", "dado", "calculo", "decisao", "verificacao", "pressuposto", "aviso", "erro", "resultado"}

# Nome legível de cada motor (o Assistente escolhe a ferramenta; isto diz ao investidor que motor trabalha)
MOTORES = {
    "licenciamento_automatico": "Motor de licenciamento automático (urbanismo PT: PDM, servidões, implantação, RJUE)",
    "licenciamento_atualizar": "Motor de licenciamento automático — recálculo com novos dados",
    "licenciamento_materiais": "Motor de materiais (fachada, cobertura, caixilharia)",
    "preparar_autorizacao_obras": "Diagnóstico RJUE (DL 555/99)",
    "calcul_ucrania": "Motor Ucrânia — ДБН / ДСТУ (térmica, cargas, estrutura CLT, orçamento com ПДВ)",
    "generate_full_bet_study": "Estudo BET completo (leitura dos planos + motores determinísticos)",
    "read_full_bet_study": "Leitura do estado do estudo BET",
    "generate_bet_lot_plans": "Planos de execução por especialidade",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_clt(user: Optional[Dict[str, Any]]) -> bool:
    """Conta CLT Rezult (e as contas extra da variável CALC_LIVE_EMAILS, separadas por vírgulas)."""
    if not user:
        return False
    email = str(user.get("email") or "").strip().lower()
    extra = {e.strip().lower() for e in (os.environ.get("CALC_LIVE_EMAILS") or "").split(",") if e.strip()}
    return email in CLT_EMAILS or email in extra


# ------------------------------------------------------------------------------------------------ formatação
def num(x: Any, casas: int = 2, unidade: str = "") -> str:
    """Número à portuguesa (vírgula decimal, espaço nos milhares)."""
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "sim" if x else "não"
    if not isinstance(x, (int, float)) or (isinstance(x, float) and not math.isfinite(x)):
        return str(x)
    if isinstance(x, int) or float(x).is_integer() and abs(x) >= 100:
        s = f"{x:,.0f}"
    else:
        s = f"{x:,.{casas}f}"
    s = s.replace(",", " ").replace(".", ",")
    return f"{s} {unidade}".strip()


def _limpo(v: Any) -> Any:
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {str(k)[:80]: _limpo(x) for k, x in list(v.items())[:40]}
    if isinstance(v, (list, tuple)):
        return [_limpo(x) for x in list(v)[:60]]
    if isinstance(v, (str, int, bool)) or v is None:
        return v if not isinstance(v, str) else v[:1500]
    return str(v)[:500]


# ------------------------------------------------------------------------------------------------ tracer
class Tracer:
    def __init__(self, db, run_id: str, loop: asyncio.AbstractEventLoop):
        self.db, self.run_id, self.loop = db, run_id, loop
        self._seq = itertools.count(1)          # seq = relógio em ns: ordem global entre ferramentas do mesmo pedido
        self.motor = ""

    def _evento(self, tipo: str, titulo: str, campos: Dict[str, Any]) -> Dict[str, Any]:
        e = {"seq": max(time.time_ns(), next(self._seq)), "t": _now(), "tipo": tipo if tipo in TIPOS else "dado", "titulo": str(titulo)[:400],
             "motor": campos.pop("motor", None) or self.motor}
        for k, v in campos.items():
            if v not in (None, "", [], {}):
                e[k] = _limpo(v)
        return e

    async def _gravar(self, eventos: list) -> None:
        try:
            inc = {"n_" + t: sum(1 for e in eventos if e["tipo"] == t) for t in {e["tipo"] for e in eventos}}
            ko = sum(1 for e in eventos if e["tipo"] == "verificacao" and e.get("ok") is False)
            if ko:
                inc["n_ko"] = ko
            await self.db.calc_live_runs.update_one(
                {"run_id": self.run_id},
                {"$push": {"eventos": {"$each": eventos, "$slice": -MAX_EVENTS}}, "$set": {"updated_at": _now()}, "$inc": inc})
        except Exception:  # noqa: BLE001 — o acompanhamento nunca pode partir um cálculo
            log.warning("calc_live: gravação falhou", exc_info=True)

    async def aev(self, tipo: str, titulo: str, **campos) -> None:
        await self._gravar([self._evento(tipo, titulo, campos)])

    def sev(self, tipo: str, titulo: str, **campos) -> None:
        """Versão síncrona (motores que correm num thread): agenda a gravação no loop do pedido."""
        e = self._evento(tipo, titulo, campos)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self.loop:
            t = self.loop.create_task(self._gravar([e]))
            _TASKS.add(t)
            t.add_done_callback(_TASKS.discard)
        else:
            try:
                asyncio.run_coroutine_threadsafe(self._gravar([e]), self.loop).result(timeout=10)
            except Exception:  # noqa: BLE001
                log.warning("calc_live: evento perdido", exc_info=True)


_TASKS: set = set()
_CUR: contextvars.ContextVar[Optional[Tracer]] = contextvars.ContextVar("calc_live_tracer", default=None)


def ativo() -> bool:
    return _CUR.get() is not None


async def ev(tipo: str, titulo: str, **campos) -> None:
    """Evento a partir de código assíncrono. No-op sem tracer."""
    tr = _CUR.get()
    if tr is not None:
        await tr.aev(tipo, titulo, **campos)


def ev_sync(tipo: str, titulo: str, **campos) -> None:
    """Evento a partir de código síncrono (thread de cálculo). No-op sem tracer."""
    tr = _CUR.get()
    if tr is not None:
        tr.sev(tipo, titulo, **campos)


# ------------------------------------------------------------------------------------------------ execução por pedido
def _resumo_args(args: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for k, v in (args or {}).items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, (dict, list)):
            v = f"{type(v).__name__} ({len(v)} campos)" if isinstance(v, dict) else f"lista de {len(v)}"
        out[k] = str(v)[:200]
    return out


async def _run_do_pedido(db, user: Dict[str, Any], conv: Dict[str, Any]) -> str:
    rid = conv.get("_quote_request_id") or conv.get("conversation_id") or uuid.uuid4().hex
    texto = (conv.get("_user_request_text") or "").strip()
    run_id = "live_" + str(rid)[:40]
    await db.calc_live_runs.update_one(
        {"run_id": run_id},
        {"$setOnInsert": {"run_id": run_id, "user_id": user["user_id"], "conversation_id": conv.get("conversation_id"),
                          "request_id": rid, "pedido": texto[:600] or "Pedido ao Assistente", "eventos": [],
                          "ferramentas": [], "em_curso": 0, "started_at": _now()},
         "$set": {"updated_at": _now()}},
        upsert=True)
    return run_id


@contextlib.asynccontextmanager
async def ferramenta(db, user: Dict[str, Any], conv: Dict[str, Any], name: str, args: Dict[str, Any]):
    """Envolve uma chamada de ferramenta do Assistente: regista a escolha do motor, ativa o tracer, fecha com o resultado."""
    run_id = await _run_do_pedido(db, user, conv)
    tr = Tracer(db, run_id, asyncio.get_running_loop())
    tr.motor = name
    token = _CUR.set(tr)
    await db.calc_live_runs.update_one({"run_id": run_id}, {"$inc": {"em_curso": 1}, "$addToSet": {"ferramentas": name},
                                                            "$set": {"estado": "a_calcular"}})
    await tr.aev("ferramenta", MOTORES.get(name, name), porque="Escolhido pelo Assistente para responder ao pedido",
                 valores=_resumo_args(args), ferramenta=name)
    t0 = asyncio.get_running_loop().time()
    ok = None
    try:
        yield tr
        ok = True
    except asyncio.CancelledError:
        await tr.aev("aviso", "Cálculo interrompido (pedido parado ou reiniciado)")
        ok = False
        raise
    except Exception as exc:
        await tr.aev("erro", f"{type(exc).__name__}: {exc}"[:400])
        ok = False
        raise
    finally:
        dt = asyncio.get_running_loop().time() - t0
        await tr.aev("etapa", f"{MOTORES.get(name, name).split(' (')[0]} — terminado em {num(dt, 1)} s" if ok
                     else f"{name} — terminou com erro")
        await db.calc_live_runs.update_one({"run_id": run_id}, {"$inc": {"em_curso": -1}, "$set": {"updated_at": _now()}})
        _CUR.reset(token)


async def resultado_ferramenta(name: str, res: Any) -> None:
    """Resultado devolvido ao Assistente (o que ele vai explicar ao utilizador)."""
    if not isinstance(res, dict):
        return
    if res.get("ok") is False:
        await ev("erro", "O motor devolveu um erro ao Assistente", resultado=str(res.get("error") or res.get("motivo") or res.get("estado"))[:400])
        for p in res.get("perguntas") or []:
            await ev("aviso", "Pergunta devolvida: " + str(p))
        return
    if name == "calcul_ucrania":            # os eventos detalhados já vieram do motor
        return
    if res.get("resume"):
        for linha in str(res["resume"]).splitlines():
            await _linha_resumo(linha)


async def _linha_resumo(linha: str) -> None:
    linha = linha.strip()
    if not linha or linha.startswith("—") or len(linha) < 3:
        return
    if linha.startswith(("OK ", "KO ", "A VERIFICAR ")):
        st, _, resto = linha.partition(" ")
        if st == "A":
            resto = resto.partition(" ")[2]
        await ev("verificacao", resto, ok=True if st == "OK" else (False if st == "KO" else None))
    elif linha.startswith("Hipótese:"):
        await ev("pressuposto", linha[9:].strip())
    else:
        await ev("resultado", linha)


# ------------------------------------------------------------------------------------------------ leitura (rotas)
def _idade_s(ts: Optional[str]) -> float:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(str(ts))).total_seconds()
    except Exception:  # noqa: BLE001
        return 1e9


def estado(r: Dict[str, Any]) -> str:
    """a_calcular: ferramenta em curso (ou estudo de fundo que escreveu há < 20 s); interrompido: sem sinal há 6 min."""
    idade = _idade_s(r.get("updated_at"))
    if (r.get("em_curso") or 0) > 0:
        return "a_calcular" if idade < 360 else "interrompido"
    return "a_calcular" if idade < 20 else "terminado"


def resumo_run(r: Dict[str, Any]) -> Dict[str, Any]:
    return {k: r.get(k) for k in ("run_id", "pedido", "ferramentas", "started_at", "updated_at", "conversation_id",
                                  "n_verificacao", "n_ko", "n_decisao", "n_calculo")} | {"estado": estado(r)}
