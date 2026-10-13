"""Dossier chantier continu : un client, ses plans, analyses, diagnostics, devis/factures et photos au même endroit."""
import secrets
import re
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.db import db
from core.permissions import require_feature
from engines.chantier_scope import named_scope, labor_scope, purchase_scope
from core.security import current_user, pro_required

router = APIRouter(prefix="/chantiers", tags=["chantiers"], dependencies=[Depends(pro_required)])
STATUSES = ("prospect", "en_cours", "termine")
ATTACH_KINDS = {
    "plan": (db.plans_takeoff, "plan_id"),
    "plans_pro": (db.plans_pro_jobs, "job_id"),
    "btp_problem": (db.btp_problems, "problem_id"),
    "document": (db.pro_documents, "doc_id"),
    "site_report": (db.site_reports, "report_id"),
    "purchase": (db.material_orders, "order_id"),
    "hr_project": (db.projects, "project_id"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChantierIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    client_id: Optional[str] = None
    address: str = Field("", max_length=200)
    postal_code: str = Field("", max_length=16)
    city: str = Field("", max_length=80)
    status: Literal["prospect", "en_cours", "termine"] = "en_cours"
    notes: str = Field("", max_length=2000)


class AttachIn(BaseModel):
    kind: Literal["plan", "plans_pro", "btp_problem", "document", "site_report", "purchase", "hr_project"]
    ref_id: str = Field(..., min_length=1, max_length=80)


async def owned_chantier_id(user_id: str, chantier_id: Optional[str]) -> Optional[str]:
    """Renvoie l'identifiant si le dossier appartient à l'utilisateur, sinon None (jamais d'erreur bloquante)."""
    if not chantier_id:
        return None
    ok = await db.chantiers.find_one({"chantier_id": chantier_id, "user_id": user_id}, {"_id": 1})
    return chantier_id if ok else None


async def _client(user_id: str, client_id: Optional[str]) -> Optional[dict]:
    if not client_id:
        return None
    c = await db.clients.find_one({"client_id": client_id, "user_id": user_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Cliente não encontrado")
    return c


def _client_label(c: Optional[dict]) -> str:
    if not c:
        return ""
    return c.get("company") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or c.get("email") or ""


async def _get(chantier_id: str, user_id: str) -> dict:
    c = await db.chantiers.find_one({"chantier_id": chantier_id, "user_id": user_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Processo de obra não encontrado")
    return c


@router.post("")
async def create_chantier(body: ChantierIn, user=Depends(current_user)) -> dict:
    client = await _client(user["user_id"], body.client_id)
    doc = {"chantier_id": "cht_" + secrets.token_hex(6), "user_id": user["user_id"], **body.model_dump(),
           "client_name": _client_label(client), "created_at": _now(), "updated_at": _now()}
    if client and not (doc["address"] or doc["city"]):
        doc.update({"address": client.get("address", ""), "postal_code": client.get("postal_code", ""), "city": client.get("city", "")})
    await db.chantiers.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


async def _counts(user_id: str, ids: list[str]) -> dict:
    out = {i: {"documents": 0, "plans": 0, "plans_pro": 0, "diagnostics": 0, "reports": 0} for i in ids}
    if not ids:
        return out
    for key, coll in (("documents", db.pro_documents), ("plans", db.plans_takeoff), ("plans_pro", db.plans_pro_jobs),
                      ("diagnostics", db.btp_problems), ("reports", db.site_reports)):
        rows = await coll.aggregate([{"$match": {"user_id": user_id, "chantier_id": {"$in": ids}}},
                                     {"$group": {"_id": "$chantier_id", "n": {"$sum": 1}}}]).to_list(len(ids) + 1)
        for r in rows:
            if r["_id"] in out:
                out[r["_id"]][key] = r["n"]
    return out


@router.get("")
async def list_chantiers(q: str = "", status: str = "", user=Depends(current_user)) -> dict:
    query: dict = {"user_id": user["user_id"]}
    if status in STATUSES:
        query["status"] = status
    if q.strip():
        rx = {"$regex": re.escape(q.strip()[:160]), "$options": "i"}
        query["$or"] = [{"name": rx}, {"client_name": rx}, {"city": rx}, {"address": rx}]
    docs = await db.chantiers.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    counts = await _counts(user["user_id"], [d["chantier_id"] for d in docs])
    for d in docs:
        d["counts"] = counts[d["chantier_id"]]
    return {"chantiers": docs, "count": len(docs)}


@router.get("/{chantier_id}")
async def get_chantier(chantier_id: str, user=Depends(current_user)) -> dict:
    return await build_dossier(chantier_id, user["user_id"])


def assistant_summary(d: dict) -> dict:
    """Vue compacte du dossier pour l'assistant : uniquement des faits connus, jamais de montants inventés."""
    cl = d.get("client") or {}
    return {
        "chantier_id": d["chantier_id"], "nom": d["name"], "statut": d.get("status"),
        "adresse": " ".join(filter(None, [d.get("address"), d.get("postal_code"), d.get("city")])) or None, "notes": d.get("notes") or None,
        "client": {"client_id": cl.get("client_id"), "nom": d.get("client_name") or None, "email": cl.get("email"), "telephone": cl.get("phone"),
                   "adresse": " ".join(filter(None, [cl.get("address"), cl.get("postal_code"), cl.get("city")])) or None} if cl else None,
        "devis_factures": [{"doc_id": x["doc_id"], "type": x.get("doc_type"), "numero": x.get("number"), "titre": x.get("title"), "statut": x.get("status"),
                            "total_ht": (x.get("totals") or {}).get("ht"), "total_ttc": (x.get("totals") or {}).get("ttc"), "paye": x.get("paid"), "date": (x.get("created_at") or "")[:10]}
                           for x in d["documents"][:40]],
        "plans": [{"plan_id": p["plan_id"], "fichier": p.get("filename"), "pages": p.get("page_count")} for p in d["plans"][:20]],
        "analyses_plan_pro": [{"job_id": j["job_id"], "fichier": j.get("filename"), "statut": j.get("status")} for j in d["plans_pro"][:20]],
        "diagnostics": [{"problem_id": x["problem_id"], "description": (x.get("description") or "")[:200], "domaine": x.get("domain"), "urgence": x.get("urgency"), "statut": x.get("status")}
                        for x in d["diagnostics"][:20]],
        "comptes_rendus": [{"titre": r.get("title"), "date": (r.get("created_at") or "")[:10], "photos": len(r.get("photos") or []), "notes": (r.get("notes") or "")[:300]} for r in d["reports"][:15]],
        "reserves_ouvertes": [{"lot": r.get("lot"), "description": (r.get("description") or "")[:200], "entreprise": r.get("company"), "statut": r.get("status")}
                              for r in d["reserves"] if r.get("status") not in ("levee", "closed", "done")][:30],
        "indicateurs": d["kpis"],
    }


async def build_dossier(chantier_id: str, uid: str) -> dict:
    c = await _get(chantier_id, uid)
    link = {"user_id": uid, "chantier_id": chantier_id}
    client = await db.clients.find_one({"client_id": c.get("client_id"), "user_id": uid}, {"_id": 0}) if c.get("client_id") else None
    documents = await db.pro_documents.find(link, {"_id": 0, "lines": 0, "frozen_pdf_b64": 0, "facturx_pdf_b64": 0}).sort("created_at", -1).to_list(300)
    plans = await db.plans_takeoff.find({**link, "trashed_at": None}, {"_id": 0, "plan_id": 1, "filename": 1, "kind": 1, "page_count": 1, "created_at": 1}).sort("created_at", -1).to_list(100)
    jobs = await db.plans_pro_jobs.find(link, {"_id": 0, "job_id": 1, "filename": 1, "status": 1, "created_at": 1, "extension": 1}).sort("created_at", -1).to_list(100)
    problems = await db.btp_problems.find(link, {"_id": 0, "problem_id": 1, "description": 1, "status": 1, "domain": 1, "urgency": 1, "created_at": 1}).sort("created_at", -1).to_list(100)
    report_q = named_scope(c, uid)
    reports = await db.site_reports.find(report_q, {"_id": 0}).sort("created_at", -1).to_list(200)
    reserves = await db.site_reserves.find(report_q, {"_id": 0}).sort("created_at", -1).to_list(200)
    for coll in (plans, jobs, problems, documents):
        for r in coll:
            if isinstance(r.get("created_at"), datetime):
                r["created_at"] = r["created_at"].isoformat()
    photos = [{"path": p, "report_id": r["report_id"], "title": r.get("title"), "created_at": r.get("created_at")}
              for r in reports for p in (r.get("photos") or [])]
    milestones = await db.chantier_milestones.find({"chantier_id": chantier_id}, {"_id": 0}).sort("order", 1).to_list(100)
    participants_n = await db.chantier_participants.count_documents({"chantier_id": chantier_id, "status": {"$ne": "revoked"}})
    ttc = lambda ds: round(sum((d.get("totals") or {}).get("ttc", 0) for d in ds), 2)  # noqa: E731
    quotes = [d for d in documents if d.get("doc_type") == "quote"]
    invoices = [d for d in documents if d.get("doc_type") == "invoice"]
    return {**c, "client": client, "documents": documents, "plans": plans, "plans_pro": jobs, "diagnostics": problems,
            "reports": reports, "reserves": reserves, "photos": photos, "milestones": milestones, "participants_count": participants_n,
            "kpis": {"quotes": len(quotes), "signed_ttc": ttc([q for q in quotes if q.get("status") == "signed"]),
                     "invoiced_ttc": ttc(invoices), "paid": round(sum(i.get("paid", 0) for i in invoices), 2),
                     "open_reserves": len([r for r in reserves if r.get("status") not in ("levee", "lifted", "closed", "done")])}}


def _rx(text: str) -> str:
    import re
    return re.escape(text or "")


@router.get("/{chantier_id}/costs")
async def chantier_costs(chantier_id: str, labor_rate: Optional[float] = Query(None, ge=0, le=10000, allow_inf_nan=False), user=Depends(current_user)) -> dict:
    """Module 7 — Coûts réels & marge : budget/marge prévisionnelle par lot (devis) + heures + achats engagés."""
    c = await _get(chantier_id, user["user_id"])
    require_feature(user, "devis")
    from engines.chantier_costs import compute_chantier_costs
    return await compute_chantier_costs(c, user["user_id"], labor_rate=labor_rate)


class LotAssignIn(BaseModel):
    lot: Optional[str] = Field(None, max_length=160)


@router.patch("/{chantier_id}/costs/labor/{entry_id}")
async def assign_labor_lot(chantier_id: str, entry_id: str, body: LotAssignIn, user=Depends(current_user)) -> dict:
    """Affecter (ou retirer) une saisie d'heures à un lot."""
    c = await _get(chantier_id, user["user_id"])
    require_feature(user, "chantier")
    q = {**await labor_scope(db, c, user["user_id"]), "entry_id": entry_id}
    lot = (body.lot or "").strip() or None
    res = await db.hr_timesheets.update_one(q, {"$set": {"lot": lot}})
    if res.matched_count == 0:
        raise HTTPException(404, "Registo de horas não encontrado para esta obra")
    return {"ok": True, "entry_id": entry_id, "lot": lot}


@router.patch("/{chantier_id}/costs/purchase/{order_id}")
async def assign_purchase_lot(chantier_id: str, order_id: str, body: LotAssignIn, user=Depends(current_user)) -> dict:
    """Affecter (ou retirer) une commande d'achat à un lot."""
    c = await _get(chantier_id, user["user_id"])
    require_feature(user, "chantier")
    lot = (body.lot or "").strip() or None
    res = await db.material_orders.update_one({**await purchase_scope(db, c, user["user_id"]), "order_id": order_id}, {"$set": {"lot": lot}})
    if res.matched_count == 0:
        raise HTTPException(404, "Encomenda não encontrada")
    return {"ok": True, "order_id": order_id, "lot": lot}



@router.put("/{chantier_id}")
async def update_chantier(chantier_id: str, body: ChantierIn, user=Depends(current_user)) -> dict:
    await _get(chantier_id, user["user_id"])
    client = await _client(user["user_id"], body.client_id)
    await db.chantiers.update_one({"chantier_id": chantier_id, "user_id": user["user_id"]},
                                  {"$set": {**body.model_dump(), "client_name": _client_label(client), "updated_at": _now()}})
    return await _get(chantier_id, user["user_id"])


@router.delete("/{chantier_id}")
async def delete_chantier(chantier_id: str, user=Depends(current_user)) -> dict:
    await _get(chantier_id, user["user_id"])
    for coll, _ in ATTACH_KINDS.values():
        await coll.update_many({"user_id": user["user_id"], "chantier_id": chantier_id}, {"$unset": {"chantier_id": ""}})
    await db.chantiers.delete_one({"chantier_id": chantier_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/{chantier_id}/attach")
async def attach(chantier_id: str, body: AttachIn, user=Depends(current_user)) -> dict:
    await _get(chantier_id, user["user_id"])
    if body.kind in ("purchase", "hr_project"):
        require_feature(user, "chantier")
    coll, key = ATTACH_KINDS[body.kind]
    r = await coll.update_one({key: body.ref_id, "user_id": user["user_id"]}, {"$set": {"chantier_id": chantier_id}})
    if not r.matched_count:
        raise HTTPException(404, "Elemento não encontrado para esta conta")
    await db.chantiers.update_one({"chantier_id": chantier_id}, {"$set": {"updated_at": _now()}})
    return {"ok": True, "chantier_id": chantier_id, "kind": body.kind, "ref_id": body.ref_id}


@router.post("/{chantier_id}/detach")
async def detach(chantier_id: str, body: AttachIn, user=Depends(current_user)) -> dict:
    await _get(chantier_id, user["user_id"])
    if body.kind in ("purchase", "hr_project"):
        require_feature(user, "chantier")
    coll, key = ATTACH_KINDS[body.kind]
    r = await coll.update_one({key: body.ref_id, "user_id": user["user_id"], "chantier_id": chantier_id}, {"$unset": {"chantier_id": ""}})
    if not r.matched_count:
        raise HTTPException(404, "Elemento não encontrado neste processo")
    return {"ok": True}


class CostSettingsIn(BaseModel):
    expected_version: int = Field(0, ge=0)
    labor_rate: Optional[float] = Field(None, ge=0, le=10000, allow_inf_nan=False)
    remaining_cost_ht: Optional[float] = Field(None, ge=0, le=1e10, allow_inf_nan=False)
    quote_ids: Optional[list[str]] = Field(None, max_length=300)


@router.put("/{chantier_id}/cost-settings")
async def save_cost_settings(chantier_id: str, body: CostSettingsIn, user=Depends(current_user)):
    require_feature(user, "devis")
    c = await _get(chantier_id, user["user_id"])
    if body.quote_ids is not None:
        from engines.chantier_costs import EXCLUDED_QUOTES
        quotes = await db.pro_documents.find({"user_id": user["user_id"], "chantier_id": chantier_id,
            "doc_type": "quote", "trashed_at": None, "doc_id": {"$in": body.quote_ids}}, {"doc_id": 1, "status": 1}).to_list(301)
        if len(body.quote_ids) != len(set(body.quote_ids)) or {q["doc_id"] for q in quotes if q.get("status") not in EXCLUDED_QUOTES} != set(body.quote_ids):
            raise HTTPException(422, "Seleção de orçamentos ausente, duplicada ou inacessível neste processo")
    if c.get("cost_version", 0) != body.expected_version:
        raise HTTPException(409, "O orçamento mudou. Recarregue antes de guardar.")
    version = c.get("cost_version", {"$exists": False})
    result = await db.chantiers.update_one({"user_id": user["user_id"], "chantier_id": chantier_id, "cost_version": version},
        {"$set": {"cost_settings": body.model_dump(exclude={"expected_version"}), "cost_version": body.expected_version + 1, "updated_at": _now()}})
    if not result.matched_count:
        raise HTTPException(409, "O orçamento mudou. Recarregue antes de guardar.")
    return await chantier_costs(chantier_id, None, user)


class DeliveryIn(BaseModel):
    expected_version: int = Field(0, ge=0)
    status: Literal["awaiting", "partial", "received", "issue"] = "awaiting"
    expected_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notes: str = Field("", max_length=2000)


@router.put("/{chantier_id}/purchases/{order_id}/delivery")
async def save_delivery(chantier_id: str, order_id: str, body: DeliveryIn, user=Depends(current_user)):
    require_feature(user, "chantier")
    c = await _get(chantier_id, user["user_id"])
    query = {**await purchase_scope(db, c, user["user_id"]), "order_id": order_id}
    order = await db.material_orders.find_one(query)
    if not order:
        raise HTTPException(404, "Encomenda não encontrada neste processo")
    from engines.chantier_costs import ENGAGED
    if order.get("status") not in ENGAGED:
        raise HTTPException(422, "A entrega diz respeito apenas a uma encomenda enviada ou confirmada")
    if body.expected_date:
        from datetime import date
        try:
            date.fromisoformat(body.expected_date)
        except ValueError:
            raise HTTPException(422, "Data de entrega inválida") from None
    if order.get("delivery_version", 0) != body.expected_version:
        raise HTTPException(409, "O seguimento mudou. Recarregue a encomenda.")
    delivery = {**body.model_dump(exclude={"expected_version"}), "updated_at": _now(), "updated_by": user["user_id"]}
    query.update(delivery_version=order.get("delivery_version", {"$exists": False}), status=order.get("status"))
    result = await db.material_orders.update_one(query, {"$set": {"delivery": delivery, "delivery_version": body.expected_version + 1}})
    if not result.matched_count:
        raise HTTPException(409, "A encomenda mudou. Recarregue antes de guardar.")
    return {"order_id": order_id, "delivery": delivery, "delivery_version": body.expected_version + 1}


@router.get("/{chantier_id}/pilot")
async def chantier_pilot(chantier_id: str, user=Depends(current_user)):
    c = await _get(chantier_id, user["user_id"])
    from engines.chantier_workspace import build_workspace
    return await build_workspace(db, c, user)
