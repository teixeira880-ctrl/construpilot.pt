import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, optional_user

router = APIRouter(prefix="/leads", tags=["leads"])


def _frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "https://construpilot.fr").rstrip("/")


def _welcome_html(name: str, email: str = "") -> str:
    hello = f"Olá {name}," if name else "Olá,"
    from urllib.parse import quote
    signup = f"{_frontend_url()}/inscription?email={quote(email)}" if email else f"{_frontend_url()}/inscription"
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f4;padding:24px;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e7e5e4;">
<tr><td style="background:#3f7d54;padding:24px 32px;color:#fff;font-size:20px;font-weight:800;">ConstruPilot</td></tr>
<tr><td style="padding:32px;color:#1a1d20;font-size:15px;line-height:1.6;">
<p>{hello}</p>
<p>Merci pour votre demande de travaux sur <strong>ConstruPilot</strong> ! Nous l'avons bien reçue.</p>
<p><strong>Pour suivre votre demande, obtenir votre estimation détaillée et recevoir vos devis, créez votre compte gratuit</strong> — cela prend moins d'une minute.</p>
<p style="text-align:center;margin:32px 0;">
<a href="{signup}" style="background:#3f7d54;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:700;display:inline-block;">Créer mon compte gratuit</a>
</p>
<p style="color:#78716c;font-size:13px;">Votre compte vous permet de&nbsp;: suivre l'avancement de votre demande, comparer les prix, et échanger avec un professionnel.</p>
<p style="color:#78716c;font-size:13px;">Une question ? Répondez simplement à cet e-mail.</p>
<p style="color:#78716c;font-size:13px;">— L'équipe ConstruPilot</p>
</td></tr>
<tr><td style="background:#fafaf9;padding:16px 32px;color:#a8a29e;font-size:11px;">ConstruPilot — Estimez. Comparez. Construisez. · Brevet FR261104</td></tr>
</table></td></tr></table></body></html>"""


async def _send_welcome(email: str, name: str) -> None:
    try:
        from engines.emailer import send_email
        await send_email(email, "Votre demande ConstruPilot — créez votre compte pour la suivre",
                         _welcome_html(name, email))
    except Exception:
        pass


async def send_account_invite(email: str, name: str = "") -> None:
    """Invitation (manuelle) à créer un compte, envoyée à un lead depuis l'admin."""
    from engines.emailer import send_email
    await send_email(
        email,
        "Créez votre compte ConstruPilot pour profiter pleinement du logiciel",
        _welcome_html(name, email))


class LeadIn(BaseModel):
    name: str = ""
    email: EmailStr
    phone: str = ""
    address: str = ""
    postal_code: str = ""
    availability: str = ""
    budget: float | None = None
    description: str = ""
    project_id: str | None = None
    source: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    photos: list[str] = []
    documents: list[dict] = []


@router.post("")
async def create_lead(body: LeadIn, user=Depends(optional_user)):
    project = None
    if body.project_id:
        project = await db.projects.find_one({"project_id": body.project_id}, {"_id": 0})
    doc = {
        "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
        "user_id": user["user_id"] if user else None,
        **body.model_dump(),
        "project_snapshot": {
            "name": project.get("name"), "surface": project.get("surface"),
            "city": project.get("city"), "estimation": project.get("estimation", {}).get("total_avg"),
            "lots": [l["name"] for l in project.get("estimation", {}).get("lots", [])],
            "materials": project.get("materials", []),
        } if project else None,
        "status": "nouveau", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    doc["department"] = _dept_from_text(body.postal_code, body.address, body.description)
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    # E-mail de bienvenue automatique pour les leads venant de la page d'accueil
    if body.email and (body.source or "").startswith("landing"):
        asyncio.create_task(_send_welcome(body.email, body.name))
    # Alerte admin (cloche + e-mail) + tentative d'assignation automatique par zone
    asyncio.create_task(_notify_new_lead_admins(doc))
    asyncio.create_task(_auto_assign_lead(doc))
    return doc


async def _notify_new_lead_admins(lead: dict) -> None:
    name = lead.get("name") or lead.get("email") or "un client"
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1, "email": 1}).to_list(20)
    for a in admins:
        try:
            await db.notifications.insert_one({
                "notif_id": "n_" + uuid.uuid4().hex[:10],
                "user_id": a["user_id"], "type": "new_lead", "lead_id": lead.get("lead_id"),
                "message": f"Nouvelle demande de travaux : {name}",
                "created_at": datetime.now(timezone.utc).isoformat(), "read": False})
        except Exception:
            pass
    try:
        from engines.emailer import send_email, wrap_html
        rows = [("Client", lead.get("name") or "—"), ("E-mail", lead.get("email") or "—"),
                ("Téléphone", lead.get("phone") or "—"), ("Adresse", lead.get("address") or "—"),
                ("Demande", lead.get("description") or "—")]
        body_html = "".join(f'<p style="margin:0 0 8px 0"><b>{k} :</b> {v}</p>' for k, v in rows)
        html = wrap_html("Nouvelle demande de travaux",
                         f"<p>Une nouvelle demande vient d'arriver sur ConstruPilot :</p>{body_html}",
                         cta_url=f"{_frontend_url()}/admin", cta_label="Voir dans l'admin")
        for a in admins:
            if a.get("email"):
                await send_email(a["email"], "Nouvelle demande de travaux — ConstruPilot", html)
    except Exception:
        pass


async def _notify_lead_pro(pro: dict, lead: dict) -> None:
    name = lead.get("name") or lead.get("email") or "un client"
    try:
        await db.notifications.insert_one({
            "notif_id": "n_" + uuid.uuid4().hex[:10],
            "user_id": pro["user_id"], "type": "lead_assigned", "lead_id": lead.get("lead_id"),
            "message": f"Nouvelle demande de travaux à prendre en charge : {name}",
            "created_at": datetime.now(timezone.utc).isoformat(), "read": False})
    except Exception:
        pass
    try:
        from engines.emailer import send_email, wrap_html
        html = wrap_html("Une demande vous a été assignée",
                         f"<p>Olá,</p><p>Une demande de travaux ({name}) vous a été assignée. "
                         f"Retrouvez-la dans votre espace « Mes demandes ».</p>",
                         cta_url=f"{_frontend_url()}/mes-demandes", cta_label="Voir mes demandes")
        if pro.get("email"):
            await send_email(pro["email"], "Une demande de travaux vous a été assignée — ConstruPilot", html)
    except Exception:
        pass


def _dept_from_text(*parts) -> str | None:
    """Déduit le département FR (2 chiffres, ou 2A/2B/97x/98x) depuis un code postal trouvé."""
    import re as _re
    m = _re.search(r"\b(\d{5})\b", " ".join(p or "" for p in parts))
    if not m:
        return None
    cp = m.group(1)
    d = cp[:2]
    if d == "20":
        return "2A" if cp[:3] in ("200", "201") else "2B"
    if d in ("97", "98"):
        return cp[:3]
    return d


def _zone_match(pro: dict, lead: dict) -> bool:
    hay = f"{lead.get('address', '')} {lead.get('description', '')} {lead.get('postal_code', '')}".lower()
    dept = (lead.get("department") or "").lower()
    zones = [z for z in ([pro.get("brand_city")] + (pro.get("service_zones") or [])) if z]
    for z in zones:
        zl = (z or "").lower().strip()
        if not zl:
            continue
        if zl in hay or (dept and zl == dept):
            return True
    return False


async def _pro_score(pro: dict) -> float:
    """Score de priorité : note moyenne (avis) + réactivité (acceptations - refus)."""
    uid = pro["user_id"]
    revs = await db.reviews.find(
        {"user_id": uid, "submitted": True, "published": True}, {"_id": 0, "rating": 1}).to_list(500)
    ratings = [r["rating"] for r in revs if r.get("rating")]
    avg = (sum(ratings) / len(ratings)) if ratings else 0
    acc = await db.leads.count_documents({"assigned_to": uid, "handling_status": "acceptee"})
    ref = await db.leads.count_documents({"refused_by": uid})
    return round(avg * 2 + acc - 0.5 * ref + (0.5 if ratings else 0), 2)


async def _rank_pros_for_zone(lead: dict, exclude_ids=None, limit: int = 3) -> list:
    """Pros de la zone triés par score de priorité (meilleurs d'abord)."""
    exclude = set(exclude_ids or [])
    pros = await db.users.find(
        {"account_type": {"$in": ["pro", "pro_business"]}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "brand_city": 1, "service_zones": 1}
    ).to_list(300)
    matching = [p for p in pros if p["user_id"] not in exclude and _zone_match(p, lead)]
    scored = [(await _pro_score(p), p) for p in matching]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:limit]]


async def _log_assignment(lead_id: str, action: str, pro: dict | None = None, note: str | None = None) -> None:
    entry = {"action": action, "at": datetime.now(timezone.utc).isoformat()}
    if pro:
        entry["user_id"] = pro.get("user_id")
        entry["user_name"] = pro.get("name") or pro.get("email")
    if note:
        entry["note"] = note
    await db.leads.update_one({"lead_id": lead_id}, {"$push": {"assignment_log": entry}})


async def _propose_to_pros(lead: dict, pros: list) -> None:
    """Propose la demande à plusieurs pros (le premier qui accepte la remporte)."""
    ids = [p["user_id"] for p in pros]
    await db.leads.update_one({"lead_id": lead["lead_id"]}, {"$set": {
        "candidates": ids, "candidates_at": datetime.now(timezone.utc).isoformat(),
        "auto_assigned": True, "response_reminded_at": None}})
    for p in pros:
        await _notify_lead_pro(p, lead)
        await _log_assignment(lead["lead_id"], "proposee", p)


async def _auto_assign_lead(lead: dict) -> None:
    """Propose automatiquement la demande aux meilleurs pros de la zone."""
    if lead.get("assigned_to") or lead.get("candidates"):
        return
    pros = await _rank_pros_for_zone(lead, exclude_ids=lead.get("refused_by"), limit=3)
    if pros:
        await _propose_to_pros(lead, pros)


@router.get("/public-count")
async def public_signup_count():
    """Compteur public d'inscrits (preuve sociale sur la landing)."""
    users = await db.users.count_documents({"role": {"$ne": "worker"}})
    leads = await db.leads.count_documents({})
    # Base de démarrage pour l'effet de preuve sociale au lancement
    return {"count": users + 1240, "users": users, "leads": leads}


async def run_signup_followups() -> int:
    """Relance J+3 : e-mail aux inscrits (par mot de passe) de ~3 jours n'ayant créé aucun devis."""
    now = datetime.now(timezone.utc)
    older = (now - timedelta(days=4)).isoformat()
    newer = (now - timedelta(days=3)).isoformat()
    users = await db.users.find(
        {"auth_provider": "password", "welcome_followup": {"$ne": True},
         "created_at": {"$gte": older, "$lte": newer}},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(500)
    from engines import emailer
    sent = 0
    for u in users:
        if await db.pro_documents.count_documents({"user_id": u["user_id"]}) > 0:
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"welcome_followup": True}})
            continue
        html = (f"<p>Olá {u.get('name') or ''},</p>"
                "<p>Vous avez rejoint <b>ConstruPilot</b> il y a quelques jours 🙂</p>"
                "<p>Créez votre premier devis en 2 minutes — c'est <b>100% gratuit pendant le lancement</b>. "
                "Nos calculateurs, prix matériaux et rendu 3D vous attendent !</p>"
                "<p>À très vite,<br/>L'équipe ConstruPilot</p>")
        try:
            await emailer.send_email(u["email"], "Votre premier devis vous attend sur ConstruPilot", html)
            await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"welcome_followup": True}})
            sent += 1
        except Exception:
            pass
    return sent



@router.get("/mine")
async def my_leads(user=Depends(current_user)):
    return await db.leads.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)


@router.get("/assigned")
async def assigned_leads(user=Depends(current_user)):
    """Demandes assignées OU proposées au pro connecté (« Mes demandes »)."""
    uid = user["user_id"]
    docs = await db.leads.find(
        {"$or": [{"assigned_to": uid}, {"candidates": uid}]}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    for d in docs:
        d["is_mine"] = d.get("assigned_to") == uid
        d["is_candidate"] = (uid in (d.get("candidates") or [])) and not d.get("assigned_to")
    return docs


class HandlingIn(BaseModel):
    handling_status: str  # acceptee | refusee | en_cours


async def _notify_admins_handling(lead: dict, pro_name: str, status: str) -> None:
    label = {"acceptee": "a pris en charge", "refusee": "a refusé", "en_cours": "traite"}[status]
    client = lead.get("name") or lead.get("email") or "client"
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}).to_list(20)
    for a in admins:
        try:
            await db.notifications.insert_one({
                "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": a["user_id"],
                "type": "lead_handling", "lead_id": lead.get("lead_id"),
                "message": f"{pro_name} {label} la demande de {client}.",
                "created_at": datetime.now(timezone.utc).isoformat(), "read": False})
        except Exception:
            pass


@router.put("/{lead_id}/handling")
async def update_handling(lead_id: str, body: HandlingIn, user=Depends(current_user)):
    """Le pro assigné ou candidat prend en charge / refuse la demande."""
    from fastapi import HTTPException
    if body.handling_status not in {"acceptee", "refusee", "en_cours"}:
        raise HTTPException(400, "Statut invalide")
    uid = user["user_id"]
    me = {"user_id": uid, "name": user.get("name"), "email": user.get("email")}
    pro_name = user.get("name") or user.get("email")
    lead = await db.leads.find_one(
        {"lead_id": lead_id, "$or": [{"assigned_to": uid}, {"candidates": uid}]}, {"_id": 0})
    if not lead:
        raise HTTPException(404, "Demande introuvable ou non proposée")
    now = datetime.now(timezone.utc).isoformat()
    reassigned_to = None

    if body.handling_status == "acceptee":
        if lead.get("assigned_to") and lead["assigned_to"] != uid:
            raise HTTPException(409, "Cette demande a déjà été prise par un autre professionnel")
        await db.leads.update_one({"lead_id": lead_id}, {"$set": {
            "assigned_to": uid, "assigned_to_name": pro_name, "assigned_at": now,
            "handling_status": "acceptee", "handling_updated_at": now, "candidates": []}})
        await _log_assignment(lead_id, "acceptee", me)
        # Informe les autres pros candidats que la demande est déjà attribuée
        for oid in (lead.get("candidates") or []):
            if oid == uid:
                continue
            try:
                await db.notifications.insert_one({
                    "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": oid,
                    "type": "lead_taken", "lead_id": lead_id,
                    "message": f"La demande de {lead.get('name') or 'client'} a été prise par un autre pro.",
                    "created_at": now, "read": False})
            except Exception:
                pass
        await _notify_admins_handling(lead, pro_name, "acceptee")

    elif body.handling_status == "refusee":
        op = {"$addToSet": {"refused_by": uid}, "$pull": {"candidates": uid},
              "$set": {"handling_updated_at": now}}
        if lead.get("assigned_to") == uid:
            op["$set"]["assigned_to"] = None
            op["$set"]["assigned_to_name"] = None
            op["$set"]["handling_status"] = None
        await db.leads.update_one({"lead_id": lead_id}, op)
        await _log_assignment(lead_id, "refusee", me)
        await _notify_admins_handling(lead, pro_name, "refusee")
        # Réattribution : si plus aucun candidat/assigné, on propose aux pros suivants
        fresh = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
        if not fresh.get("assigned_to") and not fresh.get("candidates"):
            pros = await _rank_pros_for_zone(fresh, exclude_ids=fresh.get("refused_by"), limit=3)
            if pros:
                await _propose_to_pros(fresh, pros)
                reassigned_to = ", ".join(p.get("name") or p.get("email") for p in pros)
    else:  # en_cours
        await db.leads.update_one({"lead_id": lead_id},
                                  {"$set": {"handling_status": "en_cours", "handling_updated_at": now}})
        await _log_assignment(lead_id, "en_cours", me)

    result = await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})
    result["reassigned_to"] = reassigned_to
    return result


async def run_assignment_reminders() -> int:
    """Relance le pro + alerte l'admin si une demande assignée reste sans réponse > 24 h."""
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=24)).isoformat()
    sent = 0
    leads = await db.leads.find({
        "assigned_to": {"$nin": [None, ""]},
        "handling_status": {"$in": [None, "en_cours"]},
        "assigned_at": {"$lte": cutoff},
        "response_reminded_at": {"$in": [None]},
    }, {"_id": 0}).to_list(200)
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1, "email": 1}).to_list(20)
    for lead in leads:
        pro = await db.users.find_one({"user_id": lead["assigned_to"]}, {"_id": 0, "user_id": 1, "email": 1, "name": 1})
        client = lead.get("name") or lead.get("email") or "un client"
        if pro:
            try:
                await db.notifications.insert_one({
                    "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": pro["user_id"],
                    "type": "lead_reminder", "lead_id": lead.get("lead_id"),
                    "message": f"Rappel : la demande de {client} attend votre réponse.",
                    "created_at": now.isoformat(), "read": False})
            except Exception:
                pass
        for a in admins:
            try:
                await db.notifications.insert_one({
                    "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": a["user_id"],
                    "type": "lead_reminder_admin", "lead_id": lead.get("lead_id"),
                    "message": f"Sans réponse >24 h : {(pro or {}).get('name') or 'un pro'} n'a pas traité la demande de {client}.",
                    "created_at": now.isoformat(), "read": False})
            except Exception:
                pass
        try:
            from engines.emailer import send_email, wrap_html
            if pro and pro.get("email"):
                html = wrap_html("Une demande attend votre réponse",
                                 f"<p>La demande de <b>{client}</b> vous est assignée depuis plus de 24 h et attend votre réponse.</p>",
                                 cta_url=f"{_frontend_url()}/mes-demandes", cta_label="Voir mes demandes")
                await send_email(pro["email"], "Rappel : une demande attend votre réponse — ConstruPilot", html)
        except Exception:
            pass
        await db.leads.update_one({"lead_id": lead["lead_id"]}, {"$set": {"response_reminded_at": now.isoformat()}})
        sent += 1
    return sent


@router.post("/mine/mark-viewed")
async def mark_mine_viewed(user=Depends(current_user)) -> dict:
    """Marque toutes les demandes de l'utilisateur comme vues (notification persistante)."""
    res = await db.leads.update_many(
        {"user_id": user["user_id"], "viewed": {"$ne": True}},
        {"$set": {"viewed": True, "viewed_at": datetime.now(timezone.utc).isoformat()}})
    return {"ok": True, "marked": res.modified_count}


def _j2_reminder_html(name: str) -> str:
    hello = f"Olá {name}," if name else "Olá,"
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f4;padding:24px;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e7e5e4;">
<tr><td style="background:#3f7d54;padding:24px 32px;color:#fff;font-size:20px;font-weight:800;">ConstruPilot</td></tr>
<tr><td style="padding:32px;color:#1a1d20;font-size:15px;line-height:1.6;">
<p>{hello}</p>
<p>Vous avez commencé une estimation de travaux sur <strong>ConstruPilot</strong> il y a quelques jours,
mais il semble que vous ne l'ayez pas terminée.</p>
<p>Bonne nouvelle : il ne vous reste que quelques secondes pour obtenir une estimation détaillée,
poste par poste — <strong>gratuitement et sans engagement</strong>.</p>
<p style="text-align:center;margin:32px 0;">
<a href="https://construpilot.fr/smart-project" style="background:#3f7d54;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:700;display:inline-block;">Terminer mon estimation</a>
</p>
<p style="color:#78716c;font-size:13px;">Une question ? Répondez simplement à cet e-mail, nous sommes là pour vous aider.</p>
<p style="color:#78716c;font-size:13px;">— L'équipe ConstruPilot</p>
</td></tr>
<tr><td style="background:#fafaf9;padding:16px 32px;color:#a8a29e;font-size:11px;">ConstruPilot — Estimez. Comparez. Construisez. · Brevet FR261104</td></tr>
</table></td></tr></table></body></html>"""


async def run_prospect_reminders() -> int:
    """Relance à J+2 les prospects (leads landing, statut 'nouveau') qui n'ont pas
    terminé leur estimation. Envoyée une seule fois (flag j2_reminded)."""
    from datetime import timedelta
    from engines.emailer import send_email
    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=4)).isoformat()
    hi = (now - timedelta(days=2)).isoformat()
    cursor = db.leads.find({
        "source": {"$regex": "^landing"},
        "status": "nouveau",
        "j2_reminded": {"$ne": True},
        "email": {"$nin": [None, ""]},
        "created_at": {"$gte": lo, "$lte": hi},
    }, {"_id": 0, "lead_id": 1, "email": 1, "name": 1, "project_snapshot": 1})
    sent = 0
    async for lead in cursor:
        # « n'ont pas terminé leur estimation » : pas de total d'estimation calculé
        snap = lead.get("project_snapshot") or {}
        if snap.get("estimation"):
            await db.leads.update_one({"lead_id": lead["lead_id"]},
                                      {"$set": {"j2_reminded": True}})
            continue
        try:
            await send_email(lead["email"],
                             "Il ne vous reste qu'un clic — terminez votre estimation ConstruPilot",
                             _j2_reminder_html(lead.get("name") or ""))
            sent += 1
        except Exception:
            pass
        await db.leads.update_one({"lead_id": lead["lead_id"]},
                                  {"$set": {"j2_reminded": True,
                                            "j2_reminded_at": now.isoformat()}})
    return sent
