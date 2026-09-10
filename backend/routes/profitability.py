"""Rapport de rentabilité : marge réelle par chantier (devis signé) et par mois.

Coût réel = dépenses saisies (`job_costs`, éventuellement rattachées à un bon de commande fournisseur)
sinon coût de revient du devis. Un chantier est « terminé » via PATCH .../finish (`job_finished_at`).
"""
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/pro/profitability", tags=["profitability"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month(iso: str | None) -> str:
    return (iso or "")[:7] or "—"


def _quote_cost(lines: list[dict]) -> float:
    return round(sum(float(l.get("cost_price_ht") or 0) * float(l.get("qty") or 0) for l in lines), 2)


class CostIn(BaseModel):
    label: str = Field(min_length=1, max_length=160)
    amount_ht: float = Field(ge=0)
    kind: Literal["achat", "main_oeuvre", "sous_traitance", "location", "commande", "autre"] = "achat"
    date: str | None = None
    supplier: str | None = Field(default=None, max_length=120)
    order_id: str | None = None


class FinishIn(BaseModel):
    finished: bool = True


async def _quote(doc_id: str, uid: str) -> dict:
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": uid, "doc_type": "quote"}, {"_id": 0})
    if not q:
        raise HTTPException(404, "Devis introuvable")
    return q


def _job_view(q: dict, costs: list[dict]) -> dict:
    revenue = float((q.get("totals") or {}).get("ht") or 0)
    quoted_cost = _quote_cost(q.get("lines") or [])
    real = round(sum(float(c.get("amount_ht") or 0) for c in costs), 2)
    basis = real if costs else quoted_cost
    margin = round(revenue - basis, 2)
    ref = q.get("job_finished_at") or q.get("signed_at") or q.get("issue_date") or q.get("updated_at")
    return {
        "doc_id": q["doc_id"], "number": q.get("number"), "title": q.get("title") or "Devis",
        "client": ((q.get("client") or {}).get("name") or (q.get("client") or {}).get("company") or ""),
        "status": q.get("status"), "finished": bool(q.get("job_finished_at")),
        "finished_at": q.get("job_finished_at"), "month": _month(ref),
        "revenue_ht": round(revenue, 2), "quoted_cost_ht": quoted_cost, "real_cost_ht": real,
        "cost_basis": "reel" if costs else "devis", "margin_ht": margin,
        "margin_pct": round(margin / revenue * 100, 1) if revenue else None,
        "quoted_margin_ht": round(revenue - quoted_cost, 2),
        "quoted_margin_pct": round((revenue - quoted_cost) / revenue * 100, 1) if revenue else None,
        "costs_count": len(costs),
    }


@router.get("")
async def report(months: int = 12, include_open: bool = False, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    q = {"user_id": uid, "doc_type": "quote",
         "$or": [{"signed": True}, {"status": {"$in": ["signed", "issued", "partial"]}}, {"job_finished_at": {"$ne": None}}]}
    quotes = await db.pro_documents.find(q, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    costs = await db.job_costs.find({"user_id": uid}, {"_id": 0}).to_list(20000)
    by_doc: dict[str, list] = {}
    for c in costs:
        by_doc.setdefault(c["doc_id"], []).append(c)
    jobs = [_job_view(qd, by_doc.get(qd["doc_id"], [])) for qd in quotes]
    if not include_open:
        jobs = [j for j in jobs if j["finished"]]
    months_map: dict[str, dict] = {}
    for j in jobs:
        m = months_map.setdefault(j["month"], {"month": j["month"], "jobs": 0, "revenue_ht": 0.0,
                                               "quoted_cost_ht": 0.0, "real_cost_ht": 0.0, "margin_ht": 0.0})
        m["jobs"] += 1
        m["revenue_ht"] += j["revenue_ht"]
        m["quoted_cost_ht"] += j["quoted_cost_ht"]
        m["real_cost_ht"] += j["real_cost_ht"] if j["cost_basis"] == "reel" else j["quoted_cost_ht"]
        m["margin_ht"] += j["margin_ht"]
    monthly = sorted(months_map.values(), key=lambda x: x["month"], reverse=True)[:max(1, months)]
    for m in monthly:
        for k in ("revenue_ht", "quoted_cost_ht", "real_cost_ht", "margin_ht"):
            m[k] = round(m[k], 2)
        m["margin_pct"] = round(m["margin_ht"] / m["revenue_ht"] * 100, 1) if m["revenue_ht"] else None
    rev = sum(j["revenue_ht"] for j in jobs)
    marg = sum(j["margin_ht"] for j in jobs)
    return {
        "summary": {"jobs": len(jobs), "revenue_ht": round(rev, 2), "margin_ht": round(marg, 2),
                    "margin_pct": round(marg / rev * 100, 1) if rev else None,
                    "with_real_costs": sum(1 for j in jobs if j["cost_basis"] == "reel")},
        "monthly": monthly, "jobs": jobs,
    }


@router.get("/{doc_id}/costs")
async def list_costs(doc_id: str, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    q = await _quote(doc_id, uid)
    costs = await db.job_costs.find({"user_id": uid, "doc_id": doc_id}, {"_id": 0}).sort("date", -1).to_list(1000)
    orders = await db.material_orders.find({"user_id": uid}, {"_id": 0, "order_id": 1, "type": 1, "project": 1,
                                                                 "status": 1, "created_at": 1, "supplier": 1}).sort("created_at", -1).to_list(200)
    return {"job": _job_view(q, costs), "costs": costs,
            "orders": [{**o, "supplier": (o.get("supplier") or {}).get("name") if isinstance(o.get("supplier"), dict) else o.get("supplier")} for o in orders]}


@router.post("/{doc_id}/costs")
async def add_cost(doc_id: str, body: CostIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _quote(doc_id, uid)
    cost = {"cost_id": "cost_" + secrets.token_hex(5), "user_id": uid, "doc_id": doc_id,
            **body.model_dump(), "date": body.date or _now()[:10], "created_at": _now()}
    await db.job_costs.insert_one(dict(cost))
    cost.pop("_id", None)
    await _check_overrun(doc_id, uid, user)
    return await list_costs(doc_id, user)


async def _check_overrun(doc_id: str, uid: str, user) -> None:
    """Alerte le pro (notification + e-mail) quand les achats réels dépassent le coût prévu au devis (chantier ouvert)."""
    import uuid
    q = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": uid}, {"_id": 0})
    if not q or q.get("job_finished_at") or q.get("cost_overrun_alerted_at"):
        return
    costs = await db.job_costs.find({"user_id": uid, "doc_id": doc_id}, {"_id": 0, "amount_ht": 1}).to_list(5000)
    j = _job_view(q, costs)
    if not j["quoted_cost_ht"] or j["real_cost_ht"] <= j["quoted_cost_ht"]:
        return
    over = round(j["real_cost_ht"] - j["quoted_cost_ht"], 2)
    pct = round(over / j["quoted_cost_ht"] * 100, 1)
    title = f"Dérive de coûts : {j['title']} — +{over:,.0f} € ({pct} %) au-dessus du devis".replace(",", " ")
    await db.pro_documents.update_one({"doc_id": doc_id}, {"$set": {"cost_overrun_alerted_at": _now()}})
    await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": uid, "type": "cost_overrun",
                                       "doc_id": doc_id, "message": title, "created_at": _now(), "read": False})
    try:
        from engines.emailer import send_email, wrap_html
        if user.get("email"):
            html = (f"<h2>⚠️ Dérive de coûts sur un chantier</h2><p><b>{j['title']}</b>{(' · ' + j['client']) if j['client'] else ''}</p>"
                    f"<ul><li>Coût prévu au devis : <b>{j['quoted_cost_ht']:,.2f} € HT</b></li>"
                    f"<li>Achats réels saisis : <b>{j['real_cost_ht']:,.2f} € HT</b></li>"
                    f"<li>Dépassement : <b style='color:#dc2626'>+{over:,.2f} € ({pct} %)</b></li>"
                    f"<li>Marge réelle actuelle : <b>{j['margin_ht']:,.2f} € ({j['margin_pct']} %)</b></li></ul>"
                    "<p>Consultez le rapport de rentabilité pour le détail des dépenses.</p>").replace(",", " ")
            await send_email(user["email"], title, wrap_html(html))
    except Exception:  # noqa: BLE001
        pass


@router.delete("/costs/{cost_id}")
async def delete_cost(cost_id: str, user=Depends(current_user)) -> dict:
    c = await db.job_costs.find_one({"cost_id": cost_id, "user_id": user["user_id"]}, {"_id": 0, "doc_id": 1})
    if not c:
        raise HTTPException(404, "Dépense introuvable")
    await db.job_costs.delete_one({"cost_id": cost_id})
    await db.pro_documents.update_one({"doc_id": c["doc_id"]}, {"$unset": {"cost_overrun_alerted_at": ""}})
    return {"ok": True}


@router.patch("/{doc_id}/finish")
async def finish_job(doc_id: str, body: FinishIn, user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    await _quote(doc_id, uid)
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": uid},
                                      {"$set": {"job_finished_at": _now() if body.finished else None}})
    return await list_costs(doc_id, user)
