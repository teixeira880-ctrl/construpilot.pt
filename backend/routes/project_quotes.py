"""Lien Devis ↔ Chantier côté particulier : artisan assigné, devis reçus, acceptation / refus, PDF.

Le devis est rattaché au chantier via `pro_documents.lead_id` → `leads.project_id` (devis créé depuis
« Mes demandes ») ou directement `pro_documents.project_id`.
"""
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/projects", tags=["project-quotes"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _owned_project(project_id: str, user) -> dict:
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    return p


async def _pro_card(user_id: str) -> dict | None:
    from routes.plans_common import _resolve_branding
    from routes.reviews import get_reviews_for_user
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "name": 1, "email": 1, "phone": 1, "kyc_status": 1})
    if not u:
        return None
    b = await _resolve_branding(user_id) or {}
    rv = await get_reviews_for_user(user_id, limit=3)
    return {
        "user_id": user_id, "company_name": b.get("company_name") or u.get("name") or "Professionnel",
        "contact_name": u.get("name"), "email": b.get("email") or u.get("email"), "phone": b.get("phone") or u.get("phone"),
        "city": b.get("city"), "verified": u.get("kyc_status") == "verified",
        "rating": rv.get("average") or None, "reviews_count": rv.get("count", 0),
        "profile_url": f"/pro-verifie/{user_id}",
    }


def _quote_view(d: dict, sign_token: str | None) -> dict:
    t = d.get("totals") or {}
    accepted = bool(d.get("client_accepted_at")) or bool(d.get("signed")) or d.get("status") in ("signed", "accepted")
    return {
        "doc_id": d["doc_id"], "number": d.get("number"), "title": d.get("title") or "Devis", "status": d.get("status"),
        "issue_date": d.get("issue_date") or d.get("created_at"), "total_ht": t.get("ht"), "total_ttc": t.get("ttc"),
        "lines_count": len(d.get("lines") or []), "accepted": accepted, "accepted_at": d.get("client_accepted_at") or d.get("signed_at"),
        "declined_at": d.get("client_declined_at"), "signed": bool(d.get("signed")),
        "pdf_url": f"/api/projects/{d.get('project_id')}/quotes/{d['doc_id']}/pdf",
        "sign_url": f"/sign/{sign_token}" if sign_token and not d.get("signed") else None,
        "pro_user_id": d.get("user_id"),
    }


async def _sign_token(doc: dict, create: bool = False, who: dict | None = None) -> str | None:
    s = await db.quote_sends.find_one({"doc_id": doc["doc_id"], "signed": {"$ne": True}}, {"_id": 0, "signature_token": 1},
                                      sort=[("created_at", -1)])
    if s and s.get("signature_token"):
        return s["signature_token"]
    if not create:
        return None
    token = secrets.token_urlsafe(24)
    await db.quote_sends.insert_one({
        "log_id": "qs_" + secrets.token_hex(6), "doc_id": doc["doc_id"], "user_id": doc["user_id"], "plan_id": None,
        "signature_token": token, "signature_token_created_at": _now(),
        "client_email": (who or {}).get("email") or (doc.get("client") or {}).get("email"),
        "client_name": (who or {}).get("name") or (doc.get("client") or {}).get("name"), "total_ttc": (doc.get("totals") or {}).get("ttc"),
        "subject": "Acceptation depuis l'espace chantier", "email_status": "portal", "created_at": _now(),
        "opened": True, "open_count": 1, "signed": False, "reminder_sent": False})
    return token


async def project_artisan_block(project: dict) -> dict:
    """Bloc « Artisan & devis » fusionné dans GET /projects/{id}."""
    pid = project["project_id"]
    leads = await db.leads.find({"project_id": pid}, {"_id": 0, "lead_id": 1, "assigned_to": 1, "assigned_to_name": 1,
                                                       "handling_status": 1, "status": 1, "assigned_at": 1}).to_list(50)
    lead_ids = [l["lead_id"] for l in leads]
    assigned = next((l for l in leads if l.get("assigned_to") and l.get("handling_status") == "acceptee"), None) \
        or next((l for l in leads if l.get("assigned_to")), None)
    q = {"doc_type": "quote", "status": {"$nin": ["draft", "cancelled"]},
         "$or": [{"project_id": pid}] + ([{"lead_id": {"$in": lead_ids}}] if lead_ids else [])}
    docs = await db.pro_documents.find(q, {"_id": 0}).sort("created_at", -1).to_list(50)
    quotes = []
    for d in docs:
        d.setdefault("project_id", pid)
        quotes.append(_quote_view(d, await _sign_token(d)))
    accepted = next((x for x in quotes if x["accepted"]), None)
    pro = await _pro_card(accepted["pro_user_id"]) if accepted else (await _pro_card(assigned["assigned_to"]) if assigned else None)
    return {"assigned_pro": pro, "quotes": quotes, "accepted_quote": accepted,
            "lead_status": (assigned or {}).get("handling_status") or (leads[0].get("status") if leads else None)}


async def _project_quote(project_id: str, doc_id: str, user) -> tuple[dict, dict]:
    p = await _owned_project(project_id, user)
    d = await db.pro_documents.find_one({"doc_id": doc_id, "doc_type": "quote"}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Devis introuvable")
    ok = d.get("project_id") == project_id
    if not ok and d.get("lead_id"):
        ok = bool(await db.leads.find_one({"lead_id": d["lead_id"], "project_id": project_id}, {"_id": 1}))
    if not ok:
        raise HTTPException(403, "Ce devis n'est pas rattaché à ce chantier")
    return p, d


@router.get("/{project_id}/artisan")
async def get_artisan_block(project_id: str, user=Depends(current_user)) -> dict:
    return await project_artisan_block(await _owned_project(project_id, user))


async def _notify_pro(doc: dict, project: dict, user, accepted: bool) -> None:
    label = "accepté" if accepted else "refusé"
    msg = f"Devis {doc.get('number') or ''} {label} par {user.get('name') or user.get('email')} · {project.get('name') or 'chantier'}"
    await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": doc["user_id"],
                                       "type": "quote_accepted" if accepted else "quote_declined", "doc_id": doc["doc_id"],
                                       "message": msg, "created_at": _now(), "read": False})
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": doc["user_id"]}, {"_id": 0, "email": 1})
        if pro and pro.get("email"):
            await send_email(pro["email"], f"{'✅' if accepted else '✖'} Devis {label} — {project.get('name') or ''}",
                             wrap_html(f"<p>{msg}.</p><p>Retrouvez-le dans le suivi de vos devis.</p>"))
    except Exception:  # noqa: BLE001
        pass


@router.post("/{project_id}/quotes/{doc_id}/accept")
async def accept_quote(project_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    p, d = await _project_quote(project_id, doc_id, user)
    if d.get("client_declined_at"):
        raise HTTPException(400, "Devis déjà refusé")
    if not d.get("client_accepted_at"):
        await db.pro_documents.update_one({"doc_id": doc_id}, {"$set": {
            "client_accepted_at": _now(), "client_accepted_by": user["user_id"], "project_id": project_id,
            **({"status": "accepted"} if d.get("status") not in ("signed", "invoiced") else {})}})
        if d.get("lead_id"):
            await db.leads.update_one({"lead_id": d["lead_id"]}, {"$set": {"status": "devis_accepte", "accepted_doc_id": doc_id}})
        await db.projects.update_one({"project_id": project_id}, {"$set": {"accepted_quote_id": doc_id, "assigned_pro_id": d["user_id"]}})
        await _notify_pro(d, p, user, True)
    token = await _sign_token({**d, "project_id": project_id}, create=True, who=user)
    block = await project_artisan_block(p)
    block["sign_url"] = f"/sign/{token}" if not d.get("signed") else None
    return block


@router.post("/{project_id}/quotes/{doc_id}/decline")
async def decline_quote(project_id: str, doc_id: str, user=Depends(current_user)) -> dict:
    p, d = await _project_quote(project_id, doc_id, user)
    if d.get("signed") or d.get("client_accepted_at"):
        raise HTTPException(400, "Devis déjà accepté")
    await db.pro_documents.update_one({"doc_id": doc_id}, {"$set": {"client_declined_at": _now(), "status": "refused", "project_id": project_id}})
    await _notify_pro(d, p, user, False)
    return await project_artisan_block(p)


@router.get("/{project_id}/quotes/{doc_id}/pdf")
async def project_quote_pdf(project_id: str, doc_id: str, user=Depends(current_user)):
    _, d = await _project_quote(project_id, doc_id, user)
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding
    from routes.reviews import get_reviews_for_user
    pdf = build_document_pdf(d, branding=await _resolve_branding(d["user_id"]), reviews=await get_reviews_for_user(d["user_id"]),
                             lang=d.get("lang") or user.get("lang"))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="devis_{d.get("number") or doc_id}.pdf"'})
