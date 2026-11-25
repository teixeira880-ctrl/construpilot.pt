"""Ciclo de aprendizagem por feedback + aprendizagem automática com o uso (PT).

Sinais recolhidos (porte do ciclo FR, adaptado ao PT) :
- 👍/👎 nas respostas do Assistente (👍 → caso de referência ; 👎 + comentário → correção) ;
- diferença orçamento IA ↔ orçamento validado ; correções de medições ;
- automaticamente (engines.usage_learning) : cada obra / material / preço real e cada pedido do cliente.

Isolamento estrito por empresa (org_id = organization_id ou user_id). Contas demo excluídas.
RGPD : e-mails, telefones e NIF retirados de todos os textos gravados.
Sem re-treino de modelo : os sinais são reinjetados nos prompts do próprio cliente.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.demo_guards import is_demo_user
from core.security import admin_user, current_user
from engines import usage_learning as ul

router = APIRouter(prefix="/learning", tags=["learning"])

VALID_ENGINES = {"assistant", "chiffrage", "takeoff"}


class FeedbackIn(BaseModel):
    engine: str = Field(default="assistant", max_length=20)
    conversation_id: str | None = Field(default=None, max_length=80)
    message_id: str | None = Field(default=None, max_length=80)
    rating: str
    comment: str | None = Field(default=None, max_length=2000)
    question: str | None = Field(default=None, max_length=8000)
    answer: str | None = Field(default=None, max_length=20000)
    tools: list[str] | None = None
    cites_norm: bool = False


class QuoteOutcomeIn(BaseModel):
    quote_id: str | None = None
    ouvrage_type: str | None = None
    region: str | None = None
    lot: str | None = None
    ai_total: float
    final_total: float
    accepted: bool = False
    lines_changed: list[dict] | None = None


class TakeoffCorrectionIn(BaseModel):
    doc_id: str | None = None
    ouvrage_type: str | None = None
    corrections: list[dict]


@router.post("/feedback")
async def feedback(body: FeedbackIn, user=Depends(current_user)) -> dict:
    if is_demo_user(user):
        return {"ok": True, "skipped": "demo"}
    if body.rating not in ("up", "down"):
        raise HTTPException(422, "rating deve ser 'up' ou 'down'")
    engine = body.engine if body.engine in VALID_ENGINES else "assistant"
    org = ul.org_of(user)
    doc = {
        "feedback_id": "fb_" + uuid.uuid4().hex[:16], "org_id": org, "user_id": user["user_id"],
        "engine": engine, "conversation_id": body.conversation_id, "message_id": body.message_id,
        "rating": body.rating, "comment": ul.scrub(body.comment, 2000) or None,
        "question": ul.scrub(body.question, 4000), "answer": ul.scrub(body.answer, 4000),
        "tools": (body.tools or [])[:30], "cites_norm": bool(body.cites_norm), "created_at": ul._now(),
    }
    await db.ai_feedback.update_one(
        {"org_id": org, "message_id": body.message_id} if body.message_id else {"feedback_id": doc["feedback_id"]},
        {"$set": doc}, upsert=True)
    if body.rating == "up" and body.question:
        await db.ai_reference_cases.update_one(
            {"org_id": org, "engine": engine, "source_id": body.message_id or doc["feedback_id"]},
            {"$set": {"case_id": "case_" + uuid.uuid4().hex[:16], "org_id": org, "user_id": user["user_id"],
                      "engine": engine, "source_id": body.message_id or doc["feedback_id"], "kind": "assistant_up",
                      "question": doc["question"], "solution": doc["answer"], "created_at": ul._now()}},
            upsert=True)
    ul.invalidate(user["user_id"])
    return {"ok": True}


@router.post("/quote-outcome")
async def quote_outcome(body: QuoteOutcomeIn, user=Depends(current_user)) -> dict:
    if is_demo_user(user):
        return {"ok": True, "skipped": "demo"}
    final = max(body.final_total, 0.01)
    divergence = abs(body.ai_total - body.final_total) / final
    org = ul.org_of(user)
    doc = {
        "feedback_id": "qo_" + uuid.uuid4().hex[:16], "org_id": org, "user_id": user["user_id"],
        "engine": "chiffrage", "quote_id": body.quote_id, "ouvrage_type": body.ouvrage_type,
        "region": body.region, "lot": body.lot, "ai_total": body.ai_total, "final_total": body.final_total,
        "divergence_pct": round(divergence * 100, 1), "accepted": bool(body.accepted),
        "lines_changed": (body.lines_changed or [])[:200], "created_at": ul._now(),
    }
    await db.ai_feedback.update_one(
        {"org_id": org, "engine": "chiffrage", "quote_id": body.quote_id} if body.quote_id else {"feedback_id": doc["feedback_id"]},
        {"$set": doc}, upsert=True)
    return {"ok": True, "divergence_pct": doc["divergence_pct"]}


@router.post("/takeoff-correction")
async def takeoff_correction(body: TakeoffCorrectionIn, user=Depends(current_user)) -> dict:
    if is_demo_user(user):
        return {"ok": True, "skipped": "demo"}
    doc = {
        "feedback_id": "tk_" + uuid.uuid4().hex[:16], "org_id": ul.org_of(user), "user_id": user["user_id"],
        "engine": "takeoff", "doc_id": body.doc_id, "ouvrage_type": body.ouvrage_type,
        "corrections": body.corrections[:200], "n_corrections": len(body.corrections), "created_at": ul._now(),
    }
    await db.ai_feedback.insert_one(dict(doc))
    return {"ok": True}


# ---------------------------------------------------------------- admin

@router.get("/dashboard")
async def dashboard(admin=Depends(admin_user)) -> dict:
    org = ul.org_of(admin)
    scope = {"org_id": org}
    fb = db.ai_feedback
    up = await fb.count_documents({**scope, "engine": "assistant", "rating": "up"})
    down = await fb.count_documents({**scope, "engine": "assistant", "rating": "down"})
    total_rated = up + down
    quotes = [d async for d in fb.find({**scope, "engine": "chiffrage"}, {"_id": 0, "divergence_pct": 1})]
    divs = [q["divergence_pct"] for q in quotes if q.get("divergence_pct") is not None]
    return {
        "thumbs_up_rate": round(up / total_rated * 100, 1) if total_rated else None,
        "thumbs_up": up, "thumbs_down": down, "total_feedback": total_rated,
        "reference_cases": await db.ai_reference_cases.count_documents(scope),
        "quote_samples": len(divs),
        "avg_quote_divergence_pct": round(sum(divs) / len(divs), 1) if divs else 0.0,
        "high_divergence_quotes": sum(1 for d in divs if d > 10),
        "takeoff_corrections": await fb.count_documents({**scope, "engine": "takeoff"}),
        # Aprendizagem automática (todas as empresas, só contagens)
        "auto_price_observations": await db[ul.OBS].count_documents({"weight": {"$gt": 0}}),
        "auto_real_price_observations": await db[ul.OBS].count_documents({"stage": {"$in": list(ul.REAL_STAGES)}}),
        "auto_companies_learning": len(await db[ul.OBS].distinct("org_id")),
        "auto_client_requests": await db[ul.REQ].count_documents({}),
        "global_pool_candidates": await db[ul.GLOBAL].count_documents({"n_orgs": {"$gte": 1}}),
        "global_pool_published": await db[ul.GLOBAL].count_documents({"published": True, "unit_price_ht": {"$ne": None}}),
        "k_anon": ul.K_ANON,
    }


@router.get("/global-pool")
async def global_pool(limit: int = 500, admin=Depends(admin_user)) -> dict:
    """Preços gerais aprendidos (anónimos, ≥ K empresas) — candidatos à biblioteca geral."""
    rows = await ul.global_published(max(1, min(limit, 5000)))
    return {"items": rows, "count": len(rows), "k_anon": ul.K_ANON}


class PromoteIn(BaseModel):
    gkeys: list[str] = Field(default_factory=list, max_length=2000)


@router.post("/global-pool/promote")
async def promote_global(body: PromoteIn, admin=Depends(admin_user)) -> dict:
    """Integra preços gerais aprendidos na biblioteca geral ConstruPilot PT (shared_library_items)."""
    q = {"published": True, "unit_price_ht": {"$ne": None}}
    if body.gkeys:
        q["gkey"] = {"$in": body.gkeys}
    rows = await db[ul.GLOBAL].find(q, {"_id": 0, "orgs": 0}).to_list(5000)
    added = updated = 0
    for r in rows:
        desig = (r.get("designation") or "").strip()
        if not desig:
            continue
        mid = r["unit_price_ht"]
        fields = {
            "designation": desig, "unit": r.get("unit") or "u",
            "category": "Materiais" if r.get("kind") == "materiau" else "Aprendido com o uso",
            "price_low": r.get("price_low") or mid, "price_mid": mid, "price_high": r.get("price_high") or mid,
            "lang": "pt", "country": "PT", "source": f"ConstruPilot — aprendizagem anónima ({r.get('n_orgs')} empresas)",
            "learned_gkey": r["gkey"], "ref_date": ul._now()[:10], "updated_at": ul._now(),
        }
        res = await db.shared_library_items.update_one(
            {"learned_gkey": r["gkey"]},
            {"$set": fields, "$setOnInsert": {"item_id": "shl_" + uuid.uuid4().hex[:12], "created_at": ul._now()}},
            upsert=True)
        if res.upserted_id is not None:
            added += 1
        else:
            updated += 1
        await db[ul.GLOBAL].update_one({"gkey": r["gkey"]}, {"$set": {"promoted_at": ul._now()}})
    return {"ok": True, "added": added, "updated": updated}
