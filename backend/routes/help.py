"""Chatbot d'aide public ConstruPilot (modèle actif configurable) + actions suggérées + formulaire d'assistance."""
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.rate_limit import limiter
from engines import ai
from engines.evolution import EVO_AI_MODELS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/help", tags=["help"])

# Règles d'actions : mot-clé → bouton pré-rempli (label + route)
ACTION_RULES = [
    (("plan", "dwg", "dxf", "métré", "metre"), {"label": "Analyser un plan", "to": "/plan"}),
    (("étanch", "etanch", "toiture", "vrd", "réseau", "reseau", "ferraill", "acier", "approvision", "commande", "fournisseur"),
     {"label": "Ouvrir l'Approvisionnement", "to": "/appro"}),
    (("devis", "estim", "chiffr", "budget", "prix", "coût", "cout"),
     {"label": "Démarrer mon estimation", "to": "/estimation"}),
    (("calcul", "surface", "volume", "quantit"), {"label": "Ouvrir les calculateurs", "to": "/calculateurs"}),
    (("tarif", "offre", "abonn", "pro"), {"label": "Voir les tarifs", "to": "/tarifs"}),
]
DEFAULT_ACTIONS = [{"label": "Démarrer mon estimation", "to": "/estimation"},
                   {"label": "Analyser un plan", "to": "/plan"}]


def _suggest_actions(text: str, page: str | None) -> list:
    t = (text or "").lower()
    out, seen = [], set()
    for keys, action in ACTION_RULES:
        if any(k in t for k in keys) and action["to"] not in seen and action["to"] != (page or ""):
            out.append(action); seen.add(action["to"])
    if not out:
        out = [a for a in DEFAULT_ACTIONS if a["to"] != (page or "")]
    return out[:2]


async def _active_model():
    doc = await db.app_settings.find_one({"_id": "evolution"}) or {}
    key = doc.get("active_ai_model", "opus")
    return EVO_AI_MODELS.get(key, EVO_AI_MODELS["opus"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    page: str | None = None


@router.post("/chat")
async def chat(body: ChatIn) -> dict:
    sid = body.session_id or ("help_" + uuid.uuid4().hex[:12])
    prov, mdl = await _active_model()
    reply = await ai.help_assistant(body.history, body.message, sid, body.page, prov, mdl)
    actions = _suggest_actions(body.message + " " + reply, body.page)
    return {"reply": reply, "session_id": sid, "actions": actions}


class ContactIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=4000)
    website: str = ""  # honeypot


@router.post("/contact", status_code=201)
@limiter.limit("5/hour")
async def contact(body: ContactIn, request: Request, response: Response) -> dict:
    """Formulaire d'assistance (/aide) : enregistre la demande, prévient les admins (cloche + e-mail), accuse réception. État d'e-mail vérifié."""
    if body.website.strip():
        return {"ok": True, "ticket_id": "spam", "email_status": "skipped"}
    now = datetime.now(timezone.utc).isoformat()
    doc = {"ticket_id": "sup_" + uuid.uuid4().hex[:8], "name": body.name.strip(), "email": body.email.strip().lower(), "subject": body.subject.strip(),
           "message": body.message.strip(), "page": request.headers.get("referer", ""), "status": "new", "created_at": now}
    await db.support_requests.insert_one(dict(doc))
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": a["user_id"], "type": "support_request", "url": "/admin?tab=support",
                                           "message": f"Assistance : {doc['name']} — {doc['subject'][:60]}", "read": False, "created_at": now})
    from engines.emailer import send_email, wrap_html
    support_to = os.environ.get("SUPPORT_EMAIL") or os.environ.get("ADMIN_SEED_EMAIL") or "info@construpilot.fr"
    status = "sent"
    try:
        await send_email(support_to, f"[Assistance {doc['ticket_id']}] {doc['subject']}",
                         wrap_html("Nouvelle demande d'assistance", f"<p><strong>{doc['name']}</strong> &lt;{doc['email']}&gt;</p><p><strong>{doc['subject']}</strong></p><p style='white-space:pre-wrap'>{doc['message']}</p><p>Page : {doc['page'] or '—'}</p>"),
                         reply_to=doc["email"])
        await send_email(doc["email"], f"Votre demande d'assistance {doc['ticket_id']} est bien reçue",
                         wrap_html("Demande reçue", f"<p>Bonjour {doc['name']},</p><p>Nous avons bien reçu votre demande <strong>« {doc['subject']} »</strong> (référence {doc['ticket_id']}). Notre équipe vous répond par e-mail sous 1 jour ouvré.</p>"
                                                    f"<p>En attendant, l'assistant en ligne (bouton « Besoin d'aide ? ») répond immédiatement aux questions courantes.</p>"))
    except Exception as e:  # noqa: BLE001
        status = "failed"
        logger.warning("support email failed: %s", e)
    await db.support_requests.update_one({"ticket_id": doc["ticket_id"]}, {"$set": {"email_status": status}})
    return {"ok": True, "ticket_id": doc["ticket_id"], "email_status": status}


# ---------------------------------------------------------------- admin : tickets d'assistance
from fastapi import Depends, HTTPException  # noqa: E402
from core.security import admin_user, current_user  # noqa: E402

admin_router = APIRouter(prefix="/admin/support", tags=["admin"], dependencies=[Depends(admin_user)])
TICKET_STATUS = ("new", "in_progress", "answered", "closed")


def _hours(a: str | None, b: str | None) -> float | None:
    if not a or not b:
        return None
    return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600, 1)


def _ticket_view(t: dict) -> dict:
    t.pop("_id", None)
    t["first_response_hours"] = _hours(t.get("created_at"), t.get("first_response_at"))
    t["resolution_hours"] = _hours(t.get("created_at"), t.get("closed_at"))
    if t.get("status") in ("new", "in_progress"):
        t["waiting_hours"] = _hours(t.get("created_at"), datetime.now(timezone.utc).isoformat())
    return t


@admin_router.get("")
async def list_tickets(status: str | None = None, limit: int = 200) -> dict:
    q = {"status": status} if status in TICKET_STATUS else {}
    rows = [_ticket_view(t) for t in await db.support_requests.find(q).sort("created_at", -1).to_list(min(limit, 500))]
    allrows = await db.support_requests.find({}, {"_id": 0, "status": 1, "created_at": 1, "first_response_at": 1, "closed_at": 1}).to_list(5000)
    counts = {s: sum(1 for t in allrows if t.get("status") == s) for s in TICKET_STATUS}
    fr = [h for h in (_hours(t.get("created_at"), t.get("first_response_at")) for t in allrows) if h is not None]
    rs = [h for h in (_hours(t.get("created_at"), t.get("closed_at")) for t in allrows) if h is not None]
    stats = {"counts": counts, "total": len(allrows), "avg_first_response_hours": round(sum(fr) / len(fr), 1) if fr else None,
             "avg_resolution_hours": round(sum(rs) / len(rs), 1) if rs else None, "answered_within_24h_pct": round(100 * sum(1 for h in fr if h <= 24) / len(fr)) if fr else None}
    return {"tickets": rows, "stats": stats, "statuses": TICKET_STATUS}


class TicketUpdateIn(BaseModel):
    status: str | None = Field(None, pattern="^(new|in_progress|answered|closed)$")
    internal_note: str | None = Field(None, max_length=2000)


@admin_router.put("/{ticket_id}")
async def update_ticket(ticket_id: str, body: TicketUpdateIn) -> dict:
    t = await db.support_requests.find_one({"ticket_id": ticket_id})
    if not t:
        raise HTTPException(404, "Ticket introuvable")
    now = datetime.now(timezone.utc).isoformat()
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    if not changes:
        raise HTTPException(422, "Aucune modification")
    if changes.get("status") == "closed" and not t.get("closed_at"):
        changes["closed_at"] = now
    if changes.get("status") and changes["status"] != "closed":
        changes["closed_at"] = None
    await db.support_requests.update_one({"ticket_id": ticket_id}, {"$set": {**changes, "updated_at": now}})
    return _ticket_view(await db.support_requests.find_one({"ticket_id": ticket_id}))


class TicketReplyIn(BaseModel):
    message: str = Field(min_length=2, max_length=5000)
    close: bool = False


@admin_router.post("/{ticket_id}/reply")
async def reply_ticket(ticket_id: str, body: TicketReplyIn, admin=Depends(current_user)) -> dict:
    """Réponse rapide envoyée par e-mail au demandeur (reply-to support) ; état d'envoi vérifié, jamais de faux succès."""
    t = await db.support_requests.find_one({"ticket_id": ticket_id})
    if not t:
        raise HTTPException(404, "Ticket introuvable")
    now = datetime.now(timezone.utc).isoformat()
    from engines.emailer import send_email, wrap_html
    support_to = os.environ.get("SUPPORT_EMAIL") or os.environ.get("ADMIN_SEED_EMAIL") or "info@construpilot.fr"
    try:
        await send_email(t["email"], f"Re: [Assistance {ticket_id}] {t['subject']}",
                         wrap_html(f"Réponse à votre demande {ticket_id}", f"<p>Bonjour {t['name']},</p><div style='white-space:pre-wrap'>{body.message.strip()}</div>"
                                                                            f"<hr><p style='color:#6b7280;font-size:12px'>Votre demande : « {t['subject']} »<br>{t['message'][:800]}</p>"),
                         reply_to=support_to, from_name="Assistance ConstruPilot")
        status = "sent"
    except Exception as e:  # noqa: BLE001
        logger.warning("support reply failed: %s", e)
        status = "failed"
    reply = {"at": now, "by": admin.get("email"), "message": body.message.strip(), "email_status": status}
    sets = {"updated_at": now}
    if status == "sent":
        sets["status"] = "closed" if body.close else "answered"
        if not t.get("first_response_at"):
            sets["first_response_at"] = now
        if body.close:
            sets["closed_at"] = now
    await db.support_requests.update_one({"ticket_id": ticket_id}, {"$set": sets, "$push": {"replies": reply}})
    return {"ok": status == "sent", "email_status": status, "ticket": _ticket_view(await db.support_requests.find_one({"ticket_id": ticket_id}))}
