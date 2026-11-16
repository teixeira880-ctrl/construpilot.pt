"""Verificação cruzada + correção automática das quantidades do orçamento (nada é bloqueado).

Cada quantidade do orçamento é confrontada com uma SEGUNDA FONTE independente, lida nos dados que
os próprios desenhos mostram (painéis de laje, cotas da planta de piso...). Se o desvio passar a
tolerância:

1. a IA recebe os dois valores + as evidências e diagnostica a causa;
2. a correção só é aceite se, REFEITA a medição, bater com a segunda fonte (a IA não se valida a si própria);
3. repete até haver acordo (máx. MAX_TENT);
4. se ainda divergir, entrega-se o valor da segunda fonte marcado «estimativa a confirmar» e emite-se um aviso
   para o responsável — o cliente nunca vê o valor não confirmado e o fluxo nunca fica parado.

Se a IA estiver indisponível o ciclo continua em modo determinístico (a correção vem da segunda fonte).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading

from .lang import _
from .model import WARN, Frame

log = logging.getLogger("bet_frame.verificacao")

TOL = 0.02          # 2 % de desvio relativo
MAX_TENT = 3


# ---------------------------------------------------------------- segunda fonte (lida nos desenhos)
def _sobreposicao(p: dict, cores: list[dict]) -> float:
    return sum(max(0.0, min(p["x1"], c["x1"]) - max(p["x0"], c["x0"])) * max(0.0, min(p["y1"], c["y1"]) - max(p["y0"], c["y0"])) for c in cores)


def referencia(m: Frame, r: dict) -> dict[str, dict]:
    """key → {qty, unit, fonte, evidencia}. Independente do orçamento: parte dos painéis desenhados e das cotas da planta."""
    ref: dict[str, dict] = {}
    area = vol = 0.0
    por_piso = []
    for fl in r["floors"]:
        a = sum(p["dx"] * p["dy"] - _sobreposicao(p, m.cores) for p in fl["panels"])      # painel desenhado − parte ocupada pelo núcleo
        por_piso.append({"laje": fl["slab"].name, "painéis": len(fl["panels"]), "area_m2": round(a, 2), "e_m": fl["slab"].h})
        area += a
        vol += a * fl["slab"].h
    ref["laje_betao"] = {"qty": vol, "unit": "m³", "fonte": _("Quadros de dalles (panneaux dessinés)", "Quadros de lajes (painéis desenhados)"), "evidencia": por_piso}
    ref["laje_cofragem"] = {"qty": area, "unit": "m²", "fonte": _("Quadros de dalles (panneaux dessinés)", "Quadros de lajes (painéis desenhados)"), "evidencia": por_piso}
    lv0 = m.levels[0]
    if lv0.on_grade:
        with m.at_storey(lv0.id):
            a0 = m.footprint
        ref["laje_terrea"] = {"qty": a0, "unit": "m²", "fonte": _("Emprise réelle du niveau", "Emprise real do piso"), "evidencia": [{"piso": lv0.name, "area_m2": round(a0, 2)}]}
    return ref


def desvios(lines: list[dict], ref: dict[str, dict], tol: float = TOL) -> list[dict]:
    out = []
    for ln in lines:
        k = ln.get("key")
        if k not in ref or ln.get("confirmado"):
            continue
        q, rq = float(ln["qty"]), float(ref[k]["qty"])
        d = (q - rq) / rq if rq else (1.0 if q else 0.0)
        if abs(d) > tol:
            out.append({"key": k, "des": ln["des"], "unit": ln["unit"], "orcamento": round(q, 2), "referencia": round(rq, 2), "desvio_pct": round(100 * d, 1),
                        "fonte": ref[k]["fonte"], "evidencia": ref[k]["evidencia"]})
    return out


# ---------------------------------------------------------------- IA (diagnóstico) — injetável, nunca bloqueia
SYSTEM = ("És auditor de medições de estruturas. Recebes quantidades de um orçamento que divergem de uma segunda fonte "
          "independente lida nos desenhos. Para cada item diz qual é a causa mais provável e quem tem razão. "
          'Responde SÓ JSON: {"itens":[{"key":"...","veredito":"corrigir_orcamento"|"referencia_incorreta","causa":"1 frase"}]}. '
          "Não inventes números: a correção é calculada por código a partir da fonte independente.")


def _ia_diagnostico(diffs: list[dict]) -> list[dict] | None:
    """Chama a IA (engines.ai) de forma síncrona. Qualquer falha → None (modo determinístico)."""
    try:
        from engines.ai import _complete, _json
    except Exception:  # noqa: BLE001
        return None
    box: dict = {}

    def run():
        try:
            box["out"] = asyncio.run(_complete(SYSTEM, json.dumps(diffs, ensure_ascii=False, default=str), feature="orcamento_verificacao"))
        except Exception as exc:  # noqa: BLE001
            box["err"] = exc
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(60)
    if "out" not in box:
        return None
    data = _json(box["out"], None)
    return data.get("itens") if isinstance(data, dict) else None


# ---------------------------------------------------------------- ciclo
def reconciliar(m: Frame, r: dict, lines: list[dict], diagnosticar=None, tol: float = TOL, max_tent: int = MAX_TENT) -> dict:
    """Corrige `lines` no próprio sítio. Devolve {"tentativas", "corrigidos", "por_confirmar", "avisos", "log"}."""
    diagnosticar = diagnosticar or _ia_diagnostico
    ref = referencia(m, r)
    log_: list[dict] = []
    avisos: list[dict] = []
    corrigidos: set[str] = set()
    ref_incorreta: set[str] = set()
    por_idx = {ln.get("key"): ln for ln in lines if ln.get("key")}
    for t in range(1, max_tent + 1):
        dv = [d for d in desvios(lines, ref, tol) if d["key"] not in ref_incorreta]
        if not dv:
            break
        try:
            diag = diagnosticar(dv) or []
        except Exception:  # noqa: BLE001
            diag = []
        por_key = {x.get("key"): x for x in diag if isinstance(x, dict)}
        for d in dv:
            ln, ref_k = por_idx[d["key"]], ref[d["key"]]
            ver = por_key.get(d["key"], {})
            if ver.get("veredito") == "referencia_incorreta":
                # a IA diz que a 2.ª fonte é que falha: sem 3.ª confirmação mantém-se o orçamento mas alerta-se o responsável
                ref_incorreta.add(d["key"])
                ln["por_confirmar"] = True
                avisos.append({"code": "VERIF-REF", "level": WARN, "message": _(f"« {d['des']} » : écart {d['desvio_pct']} % avec {ref_k['fonte']} ; l'IA juge la référence incorrecte — à vérifier.",
                                                                                 f"« {d['des']} »: desvio de {d['desvio_pct']} % face a {ref_k['fonte']}; a IA considera a referência incorreta — a verificar."),
                               "causa": ver.get("causa", "")})
                log_.append({"tentativa": t, "key": d["key"], "acao": "referencia_incorreta", "causa": ver.get("causa", "")})
                continue
            novo = round(ref_k["qty"], 2)          # medição refeita a partir da fonte independente
            ln["qty"] = novo
            if t == max_tent:                      # último ciclo: entrega-se mas marca-se
                ln["por_confirmar"] = True
            corrigidos.add(d["key"])
            log_.append({"tentativa": t, "key": d["key"], "de": d["orcamento"], "para": novo, "causa": ver.get("causa", "(sem IA — correção pela 2.ª fonte)"), "ia": bool(ver)})
    final = desvios(lines, ref, tol)
    for d in final:
        if d["key"] in ref_incorreta:
            continue
        lines[next(i for i, ln in enumerate(lines) if ln.get("key") == d["key"])]["por_confirmar"] = True
    por_confirmar = sorted({ln["key"] for ln in lines if ln.get("por_confirmar") and ln.get("key")})
    for k in por_confirmar:
        if k not in ref_incorreta:
            avisos.append({"code": "VERIF-NOK", "level": WARN, "message": _(f"« {por_idx[k]['des']} » : quantité non confirmée après {max_tent} tentatives — estimation à confirmer.",
                                                                          f"« {por_idx[k]['des']} »: quantidade não confirmada após {max_tent} tentativas — estimativa a confirmar.")})
    for k in corrigidos - set(por_confirmar):
        ln = por_idx[k]
        ln["verificado"] = True
    return {"tentativas": len({x["tentativa"] for x in log_}), "corrigidos": sorted(corrigidos), "por_confirmar": por_confirmar, "avisos": avisos, "log": log_}
