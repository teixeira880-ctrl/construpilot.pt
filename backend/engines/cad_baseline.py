"""Resultados de referência congelados por desenho CAD — 14/11 (Martinho).

Regra: em todas as contas (as existentes e as novas), o mesmo DWG/DXF dá SEMPRE o mesmo mapa de quantidades e o mesmo
orçamento, mesmo que o pedido seja reescrito, repetido ou feito noutra conversa. O desenho é identificado pelo CONTEÚDO
(sha256 do ficheiro original), não pelo nome nem pelo plan_id — voltar a importar o mesmo ficheiro dá a mesma referência.

- Medição por camadas: a primeira fica congelada (mesmo que o motor evolua; recalcular só a pedido explícito).
- Estrutura: congelada por sistema. Os parâmetros que o utilizador DÁ (pé-direito, pisos) acrescentam-se aos anteriores;
  um parâmetro omitido (null) mantém o valor anterior. Só um dado novo muda a estrutura, e fica uma revisão com o que mudou.
- Preços: o primeiro preço de cada artigo fica fixo para esse desenho; artigos novos recebem preço e juntam-se.
Os dados ficam por conta (user_id): nada é partilhado entre contas — a igualdade entre contas vem dos motores determinísticos.
"""
import re
import unicodedata
from contextvars import ContextVar
from datetime import datetime, timezone

# preços fixos do desenho em curso, lidos por assistant_quote_pricing.build_lines (chave → campos de preço)
PRECOS_FIXOS: ContextVar[dict | None] = ContextVar("PRECOS_FIXOS", default=None)

CAMPOS_PRECO = ("unit_price_ht", "cost_price_ht", "price_source", "price_estimated", "price_reference", "price_reference_label")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def chave_artigo(designation: str, unit: str) -> str:
    d = unicodedata.normalize("NFKD", str(designation or "")).encode("ascii", "ignore").decode().lower()
    d = re.sub(r"[^a-z0-9]+", " ", d).strip()
    return f"{d}|{str(unit or '').strip().lower()}"


async def sha_do_desenho(db, plan_id: str, user_id: str) -> str | None:
    """sha256 do ficheiro original importado (guardado com a fonte CAD); sem fonte original → DXF convertido."""
    for kind in ("original", "converted_dxf"):
        rec = await db.plan_cad_sources.find_one({"plan_id": plan_id, "user_id": user_id, "source_kind": kind, "index": 0},
                                                 {"_id": 0, "sha256": 1})
        if rec and rec.get("sha256"):
            return rec["sha256"]
    return None


async def ler(db, user_id: str, sha: str | None) -> dict | None:
    if not sha:
        return None
    return await db.cad_baselines.find_one({"user_id": user_id, "sha256": sha}, {"_id": 0})


async def guardar_medicao(db, user_id: str, sha: str, medicao: dict, plan_id: str) -> None:
    await db.cad_baselines.update_one({"user_id": user_id, "sha256": sha},
                                      {"$setOnInsert": {"user_id": user_id, "sha256": sha, "medicao": medicao, "criado_em": _now(),
                                                        "plan_id_origem": plan_id, "estrutura": {}, "precos": {}}},
                                      upsert=True)


def juntar_parametros(anteriores: dict | None, novos: dict) -> tuple[dict, list[str]]:
    """Parâmetros anteriores + os que o utilizador acrescenta agora. null nunca apaga um valor anterior."""
    base = dict(anteriores or {})
    mudou = []
    for k, v in (novos or {}).items():
        if v is None:
            continue
        if base.get(k) != v:
            mudou.append(f"{k}: {base.get(k)!r} → {v!r}" if base.get(k) is not None else f"{k} = {v!r} (dado novo)")
            base[k] = v
    return base, mudou


def diferencas(antigas: list[dict], novas: list[dict]) -> list[str]:
    a = {chave_artigo(l.get("designation"), l.get("unit")): l for l in antigas or []}
    n = {chave_artigo(l.get("designation"), l.get("unit")): l for l in novas or []}
    out = []
    for k, l in n.items():
        if k not in a:
            out.append(f"+ {l.get('designation')} — {l.get('qty')} {l.get('unit')}")
        elif round(float(a[k].get("qty") or 0), 3) != round(float(l.get("qty") or 0), 3):
            out.append(f"~ {l.get('designation')}: {a[k].get('qty')} → {l.get('qty')} {l.get('unit')}")
    for k, l in a.items():
        if k not in n:
            out.append(f"− {l.get('designation')}")
    return out


async def guardar_estrutura(db, user_id: str, sha: str, sistema: str, params: dict, resultado: dict, mudancas: list[str]) -> None:
    rec = await ler(db, user_id, sha) or {}
    ant = (rec.get("estrutura") or {}).get(sistema)
    revisoes = list((ant or {}).get("revisoes") or [])
    if ant:
        revisoes.append({"em": _now(), "parametros_anteriores": ant.get("parametros"), "mudancas": mudancas,
                         "diferencas": diferencas(ant.get("resultado", {}).get("linhas"), resultado.get("linhas"))})
    await db.cad_baselines.update_one({"user_id": user_id, "sha256": sha},
                                      {"$set": {f"estrutura.{sistema}": {"parametros": params, "resultado": resultado,
                                                                         "em": (ant or {}).get("em") or _now(), "revisoes": revisoes[-20:]}},
                                       "$setOnInsert": {"user_id": user_id, "sha256": sha, "criado_em": _now(), "precos": {}}},
                                      upsert=True)


async def juntar_precos(db, user_id: str, sha: str, linhas: list[dict]) -> int:
    """Junta os preços de artigos ainda sem preço fixo (nunca altera um preço já fixado)."""
    rec = await ler(db, user_id, sha) or {}
    fixos = rec.get("precos") or {}
    novos = {}
    for r in linhas or []:
        if r.get("price_missing"):
            continue
        k = chave_fixa(r.get("designation"), r.get("unit"))
        if k not in fixos and k not in novos:
            novos[k] = {c: r.get(c) for c in CAMPOS_PRECO}
    if novos:
        await db.cad_baselines.update_one({"user_id": user_id, "sha256": sha},
                                          {"$set": {f"precos.{k}": v for k, v in novos.items()}}, upsert=True)
    return len(novos)


def precos_fixos(rec: dict | None) -> dict:
    return {k: v for k, v in ((rec or {}).get("precos") or {}).items()}


def chave_fixa(designation: str, unit: str) -> str:
    return chave_artigo(designation, unit).replace(".", "_")
