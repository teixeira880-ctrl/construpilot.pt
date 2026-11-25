"""Aprendizagem automática com o uso — «a ConstruPilot aprende com cada obra».

Sem intervenção de ninguém, cada utilização alimenta duas memórias:

1. MEMÓRIA PRIVADA DE CADA CLIENTE (isolada por empresa: org_id = organization_id ou user_id)
   - cada obra / material / mão de obra orçamentado, faturado ou comprado, com o preço REAL
     praticado (observações em ``price_observations``, uma por linha de documento) ;
   - estatísticas por obra (n, mediana, mín., máx., último preço, mediana dos preços reais =
     orçamentos assinados, faturas, compras a fornecedores) gravadas em ``library_items.price_stats`` ;
   - os pedidos (prompts) do cliente ao assistente (``client_requests``, sem e-mails/telefones) ;
   - os 👎 com comentário (correções).
   Esta memória é injetada automaticamente nos prompts IA DESSE cliente apenas.

2. BIBLIOTECA GERAL CONSTRUPILOT (``library_global_auto``), anónima :
   - só designação normalizada + unidade + preço mediano de cada empresa, sob uma impressão
     HMAC da empresa (nunca user_id, cliente, obra ou documento) ;
   - um preço só é publicado quando ≥ K_ANON empresas distintas praticaram a mesma obra
     (k-anonimato : nenhum preço de uma empresa isolada é revelado) ;
   - só preços de documentos enviados / assinados / faturados / compras (nunca rascunhos,
     estimativas IA nem orçamentos recusados) ;
   - cada empresa pode desativar a contribuição (``users.share_anonymous_prices = False``) ;
   - contas demo excluídas.

Nada aqui bloqueia o fluxo principal : todas as entradas públicas apanham as exceções.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone

from core.db import db

logger = logging.getLogger(__name__)

OBS = "price_observations"
REQ = "client_requests"
GLOBAL = "library_global_auto"

K_ANON = 3                      # empresas distintas mínimas para publicar um preço geral
MAX_OBS_PER_KEY = 60            # observações recentes usadas nas estatísticas
BLOCK_TTL_S = 60.0

# Peso de fiabilidade de cada etapa (0 = excluída das estatísticas).
STAGE_WEIGHT = {"draft": 1, "sent": 2, "signed": 4, "invoice": 5, "purchase": 5, "refused": 0}
REAL_STAGES = {"signed", "invoice", "purchase"}
GLOBAL_STAGES = {"sent", "signed", "invoice", "purchase"}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:(?:\+\d{1,3}[\s.-]?)?(?:\d[\s.-]?){8,13}\d)")
_NIF_RE = re.compile(r"\b(?:NIF|NIPC|contribuinte)\s*[:nº.]*\s*\d{9}\b", re.I)
_STOP = {"de", "da", "do", "das", "dos", "e", "em", "com", "para", "por", "a", "o", "as", "os", "um", "uma",
         "no", "na", "nos", "nas", "ao", "aos", "que", "se", "me", "faz", "fazer", "quero", "preciso",
         "orcamento", "obra", "obras", "pf", "favor", "ola", "bom", "dia", "boa", "tarde"}

_block_cache: dict[str, tuple[float, str]] = {}


# ----------------------------------------------------------------------------- utilitários

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def org_of(user: dict) -> str:
    return (user or {}).get("organization_id") or (user or {}).get("user_id") or ""


def scrub(text, limit: int = 1500) -> str:
    """Retira e-mails, telefones e NIF (RGPD) antes de qualquer gravação de texto livre."""
    if not text:
        return ""
    t = _EMAIL_RE.sub("[email]", str(text))
    t = _NIF_RE.sub("[nif]", t)
    t = _PHONE_RE.sub("[tel]", t)
    return t.strip()[:limit]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("œ", "oe"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def unit_norm(u: str) -> str:
    v = unicodedata.normalize("NFKC", str(u or "")).lower().strip()
    return {"m^2": "m²", "m2": "m²", "m^3": "m³", "m3": "m³", "m": "ml", "un": "u", "un.": "u",
            "unid": "u", "pç": "u", "pc": "u", "vg": "forfait", "vg.": "forfait"}.get(v, v or "u")


def key_of(designation: str, unit: str) -> str:
    return f"{norm(designation)}|{unit_norm(unit)}"


def _median(vals: list[float]) -> float | None:
    s = sorted(v for v in vals if v is not None)
    if not s:
        return None
    n = len(s)
    return round(s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2, 2)


def _quantile(vals: list[float], q: float) -> float | None:
    s = sorted(vals)
    if not s:
        return None
    pos = (len(s) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 2)


def _org_hash(org: str) -> str:
    secret = (os.environ.get("LEARNING_SALT") or os.environ.get("JWT_SECRET") or "construpilot").encode()
    return hmac.new(secret, org.encode(), hashlib.sha256).hexdigest()[:20]


def _kind(line: dict) -> str:
    lk = (line.get("line_kind") or line.get("kind_detail") or "").lower()
    cat = norm(line.get("category") or "")
    if lk in ("fourniture", "materiau", "material") or cat.startswith("materia"):
        return "materiau"
    if lk in ("main_oeuvre", "mao_obra"):
        return "mao_obra"
    return "ouvrage"


def _is_demo(user: dict) -> bool:
    return bool((user or {}).get("is_demo"))


_tasks: set = set()


def schedule(coro) -> None:
    """Executa a aprendizagem em segundo plano : gravar um orçamento nunca fica mais lento."""
    import asyncio
    try:
        task = asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
        return
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def invalidate(user_id: str | None = None) -> None:
    if user_id:
        _block_cache.pop(user_id, None)
    else:
        _block_cache.clear()


# ----------------------------------------------------------------------------- extração

def _doc_stage(doc: dict) -> str | None:
    dtype = doc.get("doc_type") or "quote"
    status = doc.get("status") or "draft"
    if dtype == "credit_note":
        return None
    if dtype == "invoice":
        return "draft" if status == "draft" else "invoice"
    if status in ("signed", "partial", "paid"):
        return "signed"
    if status in ("sent", "issued"):
        return "sent"
    if status == "refused":
        return "refused"
    return "draft"


def _priced_rows(lines: list[dict]) -> list[dict]:
    """Linhas com preço real utilizável (obras + componentes de obras compostas)."""
    out = []
    for i, ln in enumerate(lines or []):
        if (ln.get("kind") or "line") != "line":
            continue
        cat = (ln.get("category") or "").lower()
        if cat.startswith("situation") or cat.startswith("avancement") or cat.startswith("situação"):
            continue
        base_key = ln.get("line_id") or f"idx{i}"
        rows = [(base_key, ln)]
        for j, comp in enumerate(ln.get("components") or []):
            if isinstance(comp, dict):
                rows.append((f"{base_key}:c{j}", comp))
        for lkey, r in rows:
            if r.get("price_missing") or r.get("price_estimated") or r.get("quantity_missing"):
                continue  # estimativas IA e linhas incompletas nunca se tornam referência
            try:
                price = round(float(r.get("unit_price_ht") if r.get("unit_price_ht") is not None else r.get("unit_price") or 0), 2)
            except (TypeError, ValueError):
                continue
            desig = scrub(r.get("designation") or r.get("label") or "", 200)
            if price <= 0 or price > 10_000_000 or len(norm(desig)) < 3:
                continue
            try:
                qty = float(r.get("qty") if r.get("qty") is not None else r.get("quantity") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            try:
                cost = round(float(r.get("cost_price_ht") or 0), 2)
            except (TypeError, ValueError):
                cost = 0.0
            out.append({"line_key": lkey, "designation": desig, "unit": unit_norm(r.get("unit")),
                        "kind": _kind(r), "category": scrub(r.get("category") or "", 80),
                        "unit_price_ht": price, "cost_price_ht": cost, "qty": qty})
    return out


# ----------------------------------------------------------------------------- gravação

async def _share_allowed(user: dict) -> bool:
    if _is_demo(user):
        return False
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "share_anonymous_prices": 1}) or {}
    return u.get("share_anonymous_prices", True) is not False


async def _record(user: dict, deal_id: str, stage: str, rows: list[dict], *, source: str,
                  replace_missing: bool = True) -> int:
    org = org_of(user)
    uid = user["user_id"]
    existing = {o["line_key"]: o async for o in db[OBS].find(
        {"org_id": org, "deal_id": deal_id, "source": source}, {"_id": 0, "line_key": 1, "stage": 1})}
    now = _now()
    touched: dict[str, dict] = {}
    for r in rows:
        prev = existing.get(r["line_key"])
        st = stage
        # Uma etapa nunca regride (fatura rascunho criada a partir de um orçamento assinado, etc.),
        # exceto «recusado» que retira o preço das estatísticas.
        if prev and stage != "refused" and STAGE_WEIGHT.get(prev.get("stage"), 0) > STAGE_WEIGHT.get(stage, 0):
            st = prev["stage"]
        key = key_of(r["designation"], r["unit"])
        await db[OBS].update_one(
            {"org_id": org, "deal_id": deal_id, "source": source, "line_key": r["line_key"]},
            {"$set": {**r, "key": key, "stage": st, "weight": STAGE_WEIGHT.get(st, 1), "user_id": uid,
                      "updated_at": now},
             "$setOnInsert": {"obs_id": "obs_" + secrets.token_hex(8), "created_at": now}},
            upsert=True)
        touched[key] = r
    if replace_missing:
        gone = [k for k in existing if k not in {r["line_key"] for r in rows}]
        if gone:
            # Linhas retiradas do documento : deixam de contar (marcadas, não apagadas).
            async for o in db[OBS].find({"org_id": org, "deal_id": deal_id, "source": source,
                                          "line_key": {"$in": gone}}, {"_id": 0, "key": 1, "designation": 1,
                                                                        "unit": 1, "kind": 1, "category": 1}):
                touched.setdefault(o["key"], o)
            await db[OBS].update_many({"org_id": org, "deal_id": deal_id, "source": source,
                                       "line_key": {"$in": gone}},
                                      {"$set": {"stage": "removed", "weight": 0, "updated_at": now}})
    share = await _share_allowed(user)
    for key, r in touched.items():
        stats = await _refresh_stats(uid, org, key, r)
        if share and stats:
            await _feed_global(org, key, r, stats)
    invalidate(uid)
    return len(rows)


async def record_document(user: dict, doc: dict | None) -> int:
    """Orçamento / fatura gravado ou com mudança de estado → observações de preço do cliente."""
    try:
        if not doc or _is_demo(user):
            return 0
        stage = _doc_stage(doc)
        if not stage:
            return 0
        deal_id = doc.get("parent_doc_id") or doc.get("doc_id") or ""
        if not deal_id:
            return 0
        return await _record(user, deal_id, stage, _priced_rows(doc.get("lines") or []), source="document")
    except Exception:  # noqa: BLE001 — a aprendizagem nunca bloqueia a gravação
        logger.warning("usage_learning.record_document falhou", exc_info=True)
        return 0


async def record_document_id(user: dict, doc_id: str) -> int:
    try:
        doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"]},
                                              {"_id": 0, "doc_id": 1, "parent_doc_id": 1, "doc_type": 1,
                                               "status": 1, "lines": 1})
        return await record_document(user, doc)
    except Exception:  # noqa: BLE001
        logger.warning("usage_learning.record_document_id falhou", exc_info=True)
        return 0


async def record_purchase(user: dict, order: dict | None) -> int:
    """Nota de encomenda enviada a um fornecedor → custo REAL de compra dos materiais."""
    try:
        if not order or _is_demo(user):
            return 0
        rows = []
        for i, it in enumerate(order.get("items") or []):
            if not isinstance(it, dict):
                continue
            rows.append({**it, "line_id": it.get("line_id") or f"idx{i}", "line_kind": "fourniture",
                         "designation": it.get("designation") or it.get("label") or it.get("name") or "",
                         "unit_price_ht": it.get("unit_price") if it.get("unit_price") is not None else it.get("unit_price_ht"),
                         "qty": it.get("qty") if it.get("qty") is not None else it.get("quantity")})
        priced = _priced_rows(rows)
        for r in priced:
            r["kind"] = "materiau"
            r["cost_price_ht"] = r["unit_price_ht"]
        return await _record(user, order.get("order_id") or "", "purchase", priced, source="purchase")
    except Exception:  # noqa: BLE001
        logger.warning("usage_learning.record_purchase falhou", exc_info=True)
        return 0


async def record_request(user: dict, text: str, source: str = "assistant", dedupe_id: str | None = None) -> None:
    """Pedido (prompt) do cliente — memória privada dos seus hábitos e obras pedidas."""
    try:
        if _is_demo(user) or not (text or "").strip():
            return
        clean = scrub(text, 800)
        terms = [t for t in norm(clean).split() if len(t) > 3 and t not in _STOP][:25]
        rid = dedupe_id or ("req_" + secrets.token_hex(8))
        await db[REQ].update_one(
            {"org_id": org_of(user), "req_id": rid},
            {"$setOnInsert": {"req_id": rid, "org_id": org_of(user), "user_id": user["user_id"], "source": source,
                              "text": clean, "terms": terms, "created_at": _now()}}, upsert=True)
        invalidate(user["user_id"])
    except Exception:  # noqa: BLE001
        logger.warning("usage_learning.record_request falhou", exc_info=True)


# ----------------------------------------------------------------------------- estatísticas

async def _refresh_stats(user_id: str, org: str, key: str, sample: dict) -> dict | None:
    obs = await db[OBS].find({"org_id": org, "key": key, "weight": {"$gt": 0}},
                             {"_id": 0, "unit_price_ht": 1, "stage": 1, "source": 1, "updated_at": 1,
                              "designation": 1}).sort("updated_at", -1).to_list(MAX_OBS_PER_KEY)
    sale = [o for o in obs if o.get("source") != "purchase"]
    buy = [o for o in obs if o.get("source") == "purchase"]
    real = [o["unit_price_ht"] for o in sale if o.get("stage") in REAL_STAGES]
    prices = [o["unit_price_ht"] for o in sale]
    stats = {
        "n": len(sale), "n_real": len(real),
        "median": _median(prices), "median_real": _median(real),
        "min": min(prices) if prices else None, "max": max(prices) if prices else None,
        "last": sale[0]["unit_price_ht"] if sale else None,
        "last_at": sale[0].get("updated_at") if sale else None,
        "n_purchase": len(buy), "purchase_median": _median([o["unit_price_ht"] for o in buy]),
        "purchase_last": buy[0]["unit_price_ht"] if buy else None,
        "updated_at": _now(),
    }
    if not obs:
        stats = {**stats, "n": 0}
    desig = sample.get("designation") or (obs[0]["designation"] if obs else "")
    if desig:
        upd = {"price_stats": stats, "usage_count": len(obs)}
        if stats["purchase_median"]:
            upd["purchase_cost_ht"] = stats["purchase_median"]
        await db.library_items.update_many(
            {"user_id": user_id, "designation": {"$regex": f"^{re.escape(desig)}$", "$options": "i"}},
            {"$set": upd})
    return stats


async def _feed_global(org: str, key: str, sample: dict, stats: dict) -> None:
    """Contribuição anónima à biblioteca geral (mediana da empresa sob impressão HMAC)."""
    org_obs = await db[OBS].find({"org_id": org, "key": key, "stage": {"$in": list(GLOBAL_STAGES)}},
                                 {"_id": 0, "unit_price_ht": 1, "source": 1}).sort("updated_at", -1).to_list(MAX_OBS_PER_KEY)
    sale = [o["unit_price_ht"] for o in org_obs if o.get("source") != "purchase"]
    buy = [o["unit_price_ht"] for o in org_obs if o.get("source") == "purchase"]
    gkey = hashlib.sha256(key.encode()).hexdigest()[:32]
    h = _org_hash(org)
    contrib = {"sale": _median(sale), "buy": _median(buy), "at": _now()}
    if not sale and not buy:
        await db[GLOBAL].update_one({"gkey": gkey}, {"$unset": {f"orgs.{h}": ""}})
    else:
        await db[GLOBAL].update_one(
            {"gkey": gkey},
            {"$set": {f"orgs.{h}": contrib, "unit": sample.get("unit") or "u", "kind": sample.get("kind") or "ouvrage",
                      "country": "PT", "updated_at": _now()},
             "$setOnInsert": {"created_at": _now()}}, upsert=True)
    doc = await db[GLOBAL].find_one({"gkey": gkey}, {"_id": 0, "orgs": 1}) or {}
    orgs = doc.get("orgs") or {}
    sales = [v["sale"] for v in orgs.values() if v.get("sale")]
    buys = [v["buy"] for v in orgs.values() if v.get("buy")]
    n_orgs = len(orgs)
    published = n_orgs >= K_ANON
    upd = {"n_orgs": n_orgs, "published": published}
    if published:
        upd.update({
            # Texto da designação só é guardado quando ≥ K empresas usam a mesma obra.
            "designation": sample.get("designation") or "",
            "unit_price_ht": _median(sales) if len(sales) >= K_ANON else None,
            "price_low": _quantile(sales, 0.25) if len(sales) >= K_ANON else None,
            "price_high": _quantile(sales, 0.75) if len(sales) >= K_ANON else None,
            "purchase_median": _median(buys) if len(buys) >= K_ANON else None,
        })
    else:
        upd.update({"designation": None, "unit_price_ht": None, "price_low": None, "price_high": None,
                    "purchase_median": None})
    await db[GLOBAL].update_one({"gkey": gkey}, {"$set": upd})


async def global_published(limit: int = 5000) -> list[dict]:
    return await db[GLOBAL].find({"published": True, "unit_price_ht": {"$ne": None}},
                                 {"_id": 0, "orgs": 0}).sort("n_orgs", -1).to_list(limit)


# ----------------------------------------------------------------------------- injeção nos prompts

async def client_memory_block(user_id: str | None) -> str:
    """Bloco privado do cliente a juntar ao system prompt (vazio se não houver histórico)."""
    if not user_id:
        return ""
    hit = _block_cache.get(user_id)
    if hit and time.monotonic() - hit[0] < BLOCK_TTL_S:
        return hit[1]
    try:
        text = await _build_block(user_id)
    except Exception:  # noqa: BLE001
        logger.warning("client_memory_block falhou", exc_info=True)
        text = ""
    _block_cache[user_id] = (time.monotonic(), text)
    return text


def _eur(v) -> str:
    return f"{float(v):,.2f} €".replace(",", " ").replace(".", ",") if v is not None else "—"


async def _build_block(user_id: str) -> str:
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "user_id": 1, "organization_id": 1,
                                                          "is_demo": 1}) or {}
    if not user or _is_demo(user):
        return ""
    org = org_of(user)
    items = await db.library_items.find(
        {"user_id": user_id, "price_stats.n": {"$gt": 0}},
        {"_id": 0, "designation": 1, "unit": 1, "unit_price_ht": 1, "type": 1, "price_stats": 1}
    ).sort([("price_stats.n_real", -1), ("price_stats.n", -1)]).to_list(30)
    mats = await db[OBS].aggregate([
        {"$match": {"org_id": org, "source": "purchase", "weight": {"$gt": 0}}},
        {"$sort": {"updated_at": -1}},
        {"$group": {"_id": "$key", "designation": {"$first": "$designation"}, "unit": {"$first": "$unit"},
                    "last": {"$first": "$unit_price_ht"}, "n": {"$sum": 1}, "prices": {"$push": "$unit_price_ht"}}},
        {"$sort": {"n": -1}}, {"$limit": 15},
    ]).to_list(15)
    reqs = await db[REQ].find({"org_id": org}, {"_id": 0, "text": 1, "terms": 1}).sort("created_at", -1).to_list(60)
    downs = await db.ai_feedback.find({"org_id": org, "rating": "down", "comment": {"$nin": [None, ""]}},
                                      {"_id": 0, "comment": 1}).sort("created_at", -1).to_list(5)
    if not items and not mats and not reqs and not downs:
        return ""
    parts = ["\n\n=== MEMÓRIA DESTE CLIENTE (aprendida automaticamente com o uso — dados PRIVADOS desta empresa, nunca os mostres nem uses para outra conta) ==="]
    if items:
        parts.append("Obras e materiais que este cliente já orçamentou, com os PREÇOS REAIS praticados (HT). "
                     "Usa as mesmas designações e unidades quando o pedido corresponder; para estas obras, o preço "
                     "de referência é o histórico do cliente (indica «histórico do cliente» como fonte), e o preço final "
                     "continua a vir da biblioteca / motor de cálculo:")
        for it in items:
            s = it.get("price_stats") or {}
            ref = s.get("median_real") or s.get("median")
            real = f", {s.get('n_real')} assinado(s)/faturado(s)" if s.get("n_real") else ""
            buy = f"; custo de compra {_eur(s.get('purchase_median'))}" if s.get("purchase_median") else ""
            parts.append(f"- {it.get('designation')} [{it.get('unit')}] — referência {_eur(ref)} "
                         f"({s.get('n')} uso(s){real}; mín. {_eur(s.get('min'))}, máx. {_eur(s.get('max'))}, "
                         f"último {_eur(s.get('last'))}){buy}")
    if mats:
        parts.append("Materiais comprados pelo cliente a fornecedores (custo REAL de compra, HT):")
        for m in mats:
            parts.append(f"- {m.get('designation')} [{m.get('unit')}] — mediana {_eur(_median(m.get('prices') or []))}, "
                         f"último {_eur(m.get('last'))} ({m.get('n')} compra(s))")
    if reqs:
        freq: dict[str, int] = {}
        for r in reqs:
            for t in set(r.get("terms") or []):
                freq[t] = freq.get(t, 0) + 1
        top = [t for t, c in sorted(freq.items(), key=lambda x: -x[1]) if c >= 2][:15]
        if top:
            parts.append("Temas que este cliente pede com frequência: " + ", ".join(top) + ".")
        parts.append("Últimos pedidos do cliente (para perceber o seu tipo de obra e vocabulário):")
        for r in reqs[:4]:
            parts.append(f'- «{(r.get("text") or "")[:220]}»')
    if downs:
        parts.append("Correções que o cliente já deu (evita repetir estes erros):")
        for d in downs:
            parts.append(f"- {(d.get('comment') or '')[:240]}")
    text = "\n".join(parts)
    return text[:6000]
