"""Espace Client & Sous-traitant — Sprint 1 : invitations (identifiant chantier + e-mail), session participant, jalons,
publication des comptes rendus et page « Avancement »."""
import asyncio
import hashlib
import hmac
import io
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.rate_limit import limiter
from core.security import JWT_ALGO, JWT_SECRET, current_user, pro_required
from engines import storage
from routes.chantiers import _get as get_chantier_owned

logger = logging.getLogger(__name__)
pro_router = APIRouter(prefix="/chantiers", tags=["portal-pro"], dependencies=[Depends(pro_required)])
router = APIRouter(prefix="/portal", tags=["portal"])

COOKIE = "participant_session"
SESSION_DAYS = 30
INVITE_DAYS = 14
OTP_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
ACCEPT_GRACE_MINUTES = 15
DEFAULT_PERMS = {"client": {"progress": True, "photos": True, "quotes": True, "invoices": True, "sign": True, "chat": True, "report_issue": True, "post_reports": False},
                 "subcontractor": {"progress": True, "photos": True, "quotes": False, "invoices": False, "sign": False, "chat": True, "report_issue": True, "post_reports": True}}
PERM_KEYS = tuple(DEFAULT_PERMS["client"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _hash(value: str) -> str:
    return hmac.new(JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def _frontend_url() -> str:
    import os
    return os.environ["FRONTEND_URL"].rstrip("/")


def _new_ref() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "CP-" + "".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(secrets.choice(alphabet) for _ in range(4))


async def _ensure_ref(chantier: dict) -> str:
    """Identifiant chantier lisible, unique, généré une seule fois."""
    if chantier.get("ref"):
        return chantier["ref"]
    for _ in range(20):
        ref = _new_ref()
        if not await db.chantiers.find_one({"ref": ref}, {"_id": 1}):
            await db.chantiers.update_one({"chantier_id": chantier["chantier_id"]}, {"$set": {"ref": ref}})
            return ref
    raise HTTPException(500, "Impossível gerar um identificador de obra")


def _public_participant(p: dict) -> dict:
    return {k: v for k, v in p.items() if k not in ("invite_token_hash", "_id")}


# ---------------------------------------------------------------- pro : invitations
class ParticipantIn(BaseModel):
    role: Literal["client", "subcontractor"]
    email: EmailStr
    name: str = Field("", max_length=120)
    lot: str = Field("", max_length=80)
    permissions: Optional[dict[str, bool]] = None


class PermissionsIn(BaseModel):
    permissions: dict[str, bool]


def _perms(role: str, given: Optional[dict]) -> dict:
    base = dict(DEFAULT_PERMS[role])
    for k, v in (given or {}).items():
        if k in PERM_KEYS:
            base[k] = bool(v)
    return base


async def _send_invite(pro: dict, chantier: dict, participant: dict, token: str) -> str:
    """Envoie le lien d'invitation. Renvoie l'état d'envoi vérifié (jamais de faux succès)."""
    from engines.emailer import send_email, wrap_html
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(pro["user_id"]) or {}
    company = branding.get("company_name") or pro.get("name") or "A sua empresa"
    link = f"{_frontend_url()}/espace/invitation/{token}"
    role_label = "client" if participant["role"] == "client" else "sous-traitant"
    html = wrap_html(f"Convite — obra {chantier['name']}",
                     f"<p>Olá {participant.get('name') or ''},</p><p><strong>{company}</strong> convida-o na qualidade de <strong>{role_label}</strong> a acompanhar a obra <strong>{chantier['name']}</strong> no ConstruPilot: andamento, fotografias, atas.</p><p>Identificador da obra: <strong>{chantier['ref']}</strong><br>E-mail de acesso: <strong>{participant['email']}</strong></p><p>A ligação é válida durante {INVITE_DAYS} dias. Depois, inicie sessão com o identificador da obra e o seu e-mail: ser-lhe-á enviado um código.</p>",
                     cta_url=link, cta_label="Aceder à minha área de obra")
    try:
        await send_email(participant["email"], f"{company} convida-o a acompanhar a obra {chantier['name']}", html, from_name=company)
        return "sent"
    except Exception as e:  # noqa: BLE001
        logger.warning("invite email failed: %s", e)
        return "failed"


@pro_router.post("/{chantier_id}/participants", status_code=201)
async def invite_participant(chantier_id: str, body: ParticipantIn, user=Depends(current_user)) -> dict:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    chantier["ref"] = await _ensure_ref(chantier)
    email = body.email.strip().lower()
    if await db.chantier_participants.find_one({"chantier_id": chantier_id, "email": email, "status": {"$ne": "revoked"}}, {"_id": 1}):
        raise HTTPException(409, "Este e-mail já está convidado para esta obra")
    token = secrets.token_urlsafe(32)
    now = _now()
    doc = {"participant_id": "part_" + secrets.token_hex(6), "chantier_id": chantier_id, "chantier_ref": chantier["ref"], "owner_user_id": user["user_id"],
           "role": body.role, "email": email, "name": body.name.strip(), "lot": body.lot.strip(), "permissions": _perms(body.role, body.permissions),
           "status": "invited", "invite_token_hash": _hash(token), "invite_expires_at": _iso(now + timedelta(days=INVITE_DAYS)), "invite_sent_at": _iso(now),
           "accepted_at": None, "last_seen_at": None, "session_version": 0, "created_at": _iso(now), "updated_at": _iso(now)}
    await db.chantier_participants.insert_one(dict(doc))
    doc["invite_email_status"] = await _send_invite(user, chantier, doc, token)
    await db.chantier_participants.update_one({"participant_id": doc["participant_id"]}, {"$set": {"invite_email_status": doc["invite_email_status"]}})
    return {**_public_participant(doc), "invite_link": f"{_frontend_url()}/espace/invitation/{token}"}


@pro_router.get("/{chantier_id}/participants")
async def list_participants(chantier_id: str, user=Depends(current_user)) -> dict:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    rows = await db.chantier_participants.find({"chantier_id": chantier_id}, {"_id": 0, "invite_token_hash": 0}).sort("created_at", -1).to_list(200)
    return {"ref": chantier.get("ref"), "participants": rows, "portal_url": f"{_frontend_url()}/espace"}


@pro_router.post("/{chantier_id}/participants/{participant_id}/resend")
async def resend_invite(chantier_id: str, participant_id: str, user=Depends(current_user)) -> dict:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    chantier["ref"] = await _ensure_ref(chantier)
    p = await db.chantier_participants.find_one({"participant_id": participant_id, "chantier_id": chantier_id}, {"_id": 0})
    if not p or p["status"] == "revoked":
        raise HTTPException(404, "Convite não encontrado ou revogado")
    token = secrets.token_urlsafe(32)
    now = _now()
    status = await _send_invite(user, chantier, p, token)
    await db.chantier_participants.update_one({"participant_id": participant_id}, {"$set": {"invite_token_hash": _hash(token), "invite_expires_at": _iso(now + timedelta(days=INVITE_DAYS)),
                                                                                             "invite_sent_at": _iso(now), "invite_email_status": status, "updated_at": _iso(now)}})
    return {"ok": True, "invite_email_status": status, "invite_link": f"{_frontend_url()}/espace/invitation/{token}"}


@pro_router.post("/{chantier_id}/participants/{participant_id}/revoke")
async def revoke_participant(chantier_id: str, participant_id: str, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    r = await db.chantier_participants.update_one({"participant_id": participant_id, "chantier_id": chantier_id},
                                                  {"$set": {"status": "revoked", "revoked_at": _iso(_now()), "updated_at": _iso(_now())}, "$inc": {"session_version": 1}})
    if not r.matched_count:
        raise HTTPException(404, "Participante não encontrado")
    await db.portal_otps.delete_many({"participant_id": participant_id})
    return {"ok": True}


@pro_router.put("/{chantier_id}/participants/{participant_id}/permissions")
async def set_permissions(chantier_id: str, participant_id: str, body: PermissionsIn, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    p = await db.chantier_participants.find_one({"participant_id": participant_id, "chantier_id": chantier_id}, {"_id": 0, "role": 1, "permissions": 1})
    if not p:
        raise HTTPException(404, "Participante não encontrado")
    perms = _perms(p["role"], {**p.get("permissions", {}), **body.permissions})
    await db.chantier_participants.update_one({"participant_id": participant_id}, {"$set": {"permissions": perms, "updated_at": _iso(_now())}})
    return {"permissions": perms}


# ---------------------------------------------------------------- pro : jalons & publication
class MilestoneIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    planned_start: Optional[str] = Field(None, max_length=10)
    planned_end: Optional[str] = Field(None, max_length=10)
    status: Literal["planned", "in_progress", "done", "late"] = "planned"
    progress_pct: int = Field(0, ge=0, le=100)
    lot: str = Field("", max_length=80)
    visible: bool = True


@pro_router.post("/{chantier_id}/milestones", status_code=201)
async def add_milestone(chantier_id: str, body: MilestoneIn, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    n = await db.chantier_milestones.count_documents({"chantier_id": chantier_id})
    doc = {"milestone_id": "ms_" + secrets.token_hex(5), "chantier_id": chantier_id, "user_id": user["user_id"], "order": n, **body.model_dump(),
           "created_at": _iso(_now()), "updated_at": _iso(_now())}
    await db.chantier_milestones.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@pro_router.put("/{chantier_id}/milestones/{milestone_id}")
async def update_milestone(chantier_id: str, milestone_id: str, body: MilestoneIn, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    r = await db.chantier_milestones.update_one({"milestone_id": milestone_id, "chantier_id": chantier_id}, {"$set": {**body.model_dump(), "updated_at": _iso(_now())}})
    if not r.matched_count:
        raise HTTPException(404, "Marco não encontrado")
    return await db.chantier_milestones.find_one({"milestone_id": milestone_id}, {"_id": 0})


@pro_router.delete("/{chantier_id}/milestones/{milestone_id}")
async def delete_milestone(chantier_id: str, milestone_id: str, user=Depends(current_user)) -> dict:
    await get_chantier_owned(chantier_id, user["user_id"])
    r = await db.chantier_milestones.delete_one({"milestone_id": milestone_id, "chantier_id": chantier_id})
    if not r.deleted_count:
        raise HTTPException(404, "Marco não encontrado")
    return {"ok": True}


class PublishIn(BaseModel):
    published: bool


@pro_router.put("/{chantier_id}/reports/{report_id}/publish")
async def publish_report(chantier_id: str, report_id: str, body: PublishIn, user=Depends(current_user)) -> dict:
    """Un compte rendu n'est visible des invités que s'il est explicitement publié ; il est alors rattaché au dossier."""
    await get_chantier_owned(chantier_id, user["user_id"])
    r = await db.site_reports.update_one({"report_id": report_id, "user_id": user["user_id"]},
                                         {"$set": {"published": body.published, "published_at": _iso(_now()) if body.published else None, "chantier_id": chantier_id}})
    if not r.matched_count:
        raise HTTPException(404, "Ata não encontrada")
    return {"ok": True, "published": body.published}


# ---------------------------------------------------------------- participant : session
def _session_token(p: dict) -> str:
    return jwt.encode({"sub": p["participant_id"], "email": p["email"], "sv": int(p.get("session_version") or 0), "typ": "participant",
                       "exp": _now() + timedelta(days=SESSION_DAYS)}, JWT_SECRET, algorithm=JWT_ALGO)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE, token, httponly=True, secure=True, samesite="lax", path="/", max_age=SESSION_DAYS * 86400)


async def current_participant(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sessão de convidado necessária")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.PyJWTError:
        raise HTTPException(401, "Sessão expirada")
    if payload.get("typ") != "participant":
        raise HTTPException(401, "Sessão inválida")
    p = await db.chantier_participants.find_one({"participant_id": payload.get("sub")}, {"_id": 0, "invite_token_hash": 0})
    if not p or p["status"] != "active" or int(payload.get("sv") or 0) != int(p.get("session_version") or 0):
        raise HTTPException(401, "Acesso revogado ou expirado")
    await db.chantier_participants.update_one({"participant_id": p["participant_id"]}, {"$set": {"last_seen_at": _iso(_now())}})
    return p


@router.post("/accept/{token}")
@limiter.limit("20/hour")
async def accept_invite(token: str, request: Request, response: Response) -> dict:
    p = await db.chantier_participants.find_one({"invite_token_hash": _hash(token)}, {"_id": 0})
    if not p or p["status"] == "revoked":
        raise HTTPException(404, "Convite não encontrado ou revogado")
    if p["status"] == "invited":
        if (p.get("invite_expires_at") or "") < _iso(_now()):
            raise HTTPException(410, "Convite expirado: peça uma nova ligação à empresa ou inicie sessão com o identificador da obra.")
        await db.chantier_participants.update_one({"participant_id": p["participant_id"]},
                                                  {"$set": {"status": "active", "accepted_at": _iso(_now()), "updated_at": _iso(_now())}})
        p["status"] = "active"
    elif (p.get("accepted_at") or "") < _iso(_now() - timedelta(minutes=ACCEPT_GRACE_MINUTES)):
        # lien déjà consommé : on le neutralise définitivement (usage unique, avec une courte tolérance pour le double appel du navigateur)
        await db.chantier_participants.update_one({"participant_id": p["participant_id"]}, {"$unset": {"invite_token_hash": ""}})
        raise HTTPException(404, "Esta ligação já foi utilizada: inicie sessão com o identificador da obra e o seu e-mail.")
    _set_cookie(response, _session_token(p))
    return {"ok": True, "participant": _public_participant(p)}


class LoginIn(BaseModel):
    ref: str = Field(..., min_length=6, max_length=20)
    email: EmailStr


class VerifyIn(LoginIn):
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/login")
@limiter.limit("5/15minutes")
async def portal_login(body: LoginIn, request: Request, response: Response) -> dict:
    """Identifiant chantier + e-mail → code à 6 chiffres par e-mail. Réponse identique qu'il y ait ou non un compte (pas d'énumération)."""
    ref = body.ref.strip().upper()
    email = body.email.strip().lower()
    p = await db.chantier_participants.find_one({"chantier_ref": ref, "email": email, "status": {"$in": ["active", "invited"]}}, {"_id": 0})
    if p:
        code = f"{secrets.randbelow(10**6):06d}"
        await db.portal_otps.delete_many({"participant_id": p["participant_id"]})
        await db.portal_otps.insert_one({"participant_id": p["participant_id"], "code_hash": _hash(code), "attempts": 0,
                                         "expires_at": _now() + timedelta(minutes=OTP_MINUTES), "created_at": _now()})
        asyncio.create_task(_send_otp(p, code))
    return {"ok": True, "message": "Se este e-mail estiver convidado para esta obra, acaba de ser enviado um código."}


async def _send_otp(p: dict, code: str) -> None:
    from engines.emailer import send_email, wrap_html
    try:
        await send_email(p["email"], f"O seu código de acesso à obra {p['chantier_ref']}",
                         wrap_html("Código de acesso", f"<p>O seu código para aceder à obra <strong>{p['chantier_ref']}</strong> :</p><p style='font-size:28px;letter-spacing:6px'><strong>{code}</strong></p><p>Válido durante {OTP_MINUTES} minutes.</p>"))
    except Exception as e:  # noqa: BLE001
        logger.warning("otp email failed: %s", e)


@router.post("/verify")
@limiter.limit("10/15minutes")
async def portal_verify(body: VerifyIn, request: Request, response: Response) -> dict:
    ref = body.ref.strip().upper()
    email = body.email.strip().lower()
    p = await db.chantier_participants.find_one({"chantier_ref": ref, "email": email, "status": {"$in": ["active", "invited"]}}, {"_id": 0})
    otp = await db.portal_otps.find_one({"participant_id": p["participant_id"]}) if p else None
    if not p or not otp or otp["expires_at"].replace(tzinfo=timezone.utc) < _now():
        raise HTTPException(401, "Código expirado ou inválido: peça um novo código.")
    if otp["attempts"] >= OTP_MAX_ATTEMPTS:
        await db.portal_otps.delete_one({"_id": otp["_id"]})
        raise HTTPException(429, "Demasiadas tentativas: peça um novo código.")
    if not hmac.compare_digest(otp["code_hash"], _hash(body.code.strip())):
        await db.portal_otps.update_one({"_id": otp["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(401, "Código incorreto")
    await db.portal_otps.delete_one({"_id": otp["_id"]})
    if p["status"] == "invited":
        await db.chantier_participants.update_one({"participant_id": p["participant_id"]}, {"$set": {"status": "active", "accepted_at": _iso(_now())}, "$unset": {"invite_token_hash": ""}})
        p["status"] = "active"
    _set_cookie(response, _session_token(p))
    return {"ok": True, "participant": _public_participant(p)}


@router.post("/logout")
async def portal_logout(response: Response) -> dict:
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


async def _chantier_card(p: dict) -> dict:
    c = await db.chantiers.find_one({"chantier_id": p["chantier_id"]}, {"_id": 0, "name": 1, "ref": 1, "city": 1, "status": 1, "user_id": 1})
    if not c:
        return {"participant_id": p["participant_id"], "ref": p["chantier_ref"], "name": "Obra eliminada", "available": False}
    from routes.plans_common import _resolve_branding
    b = await _resolve_branding(c["user_id"]) or {}
    return {"participant_id": p["participant_id"], "ref": c.get("ref") or p["chantier_ref"], "name": c["name"], "city": c.get("city"), "status": c.get("status"),
            "role": p["role"], "company": b.get("company_name") or "", "available": True}


@router.get("/me")
async def portal_me(p=Depends(current_participant)) -> dict:
    others = await db.chantier_participants.find({"email": p["email"], "status": "active"}, {"_id": 0, "invite_token_hash": 0}).to_list(50)
    return {"participant": p, "chantiers": [await _chantier_card(o) for o in others]}


class SwitchIn(BaseModel):
    participant_id: str


@router.post("/switch")
async def portal_switch(body: SwitchIn, response: Response, p=Depends(current_participant)) -> dict:
    """Même e-mail, autre chantier : nouvelle session limitée à ce chantier."""
    target = await db.chantier_participants.find_one({"participant_id": body.participant_id, "email": p["email"], "status": "active"}, {"_id": 0, "invite_token_hash": 0})
    if not target:
        raise HTTPException(404, "Obra não acessível")
    _set_cookie(response, _session_token(target))
    return {"ok": True, "participant": target}


def _require_ref(p: dict, ref: str) -> None:
    if p["chantier_ref"] != ref.strip().upper():
        raise HTTPException(403, "Esta obra não é acessível com esta sessão")


@router.get("/{ref}/overview")
async def portal_overview(ref: str, p=Depends(current_participant)) -> dict:
    _require_ref(p, ref)
    return await overview_for(p)


async def overview_for(p: dict) -> dict:
    """Vue « Avancement » pour un participant (réel ou simulé par le pro via « Voir comme le client »)."""
    c = await db.chantiers.find_one({"chantier_id": p["chantier_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Obra não encontrada")
    from routes.plans_common import _resolve_branding
    b = await _resolve_branding(c["user_id"]) or {}
    pro = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0, "name": 1, "email": 1, "phone": 1, "brand_phone": 1, "brand_accent_color": 1})
    logo = b.get("logo_b64") or b.get("photo") or None
    if logo and not logo.startswith(("data:", "http")):
        logo = f"data:image/png;base64,{logo}"
    perms = p.get("permissions") or {}
    milestones = await db.chantier_milestones.find({"chantier_id": c["chantier_id"], "visible": True}, {"_id": 0}).sort("order", 1).to_list(100) if perms.get("progress") else []
    reports = []
    if perms.get("progress"):
        q = {"chantier_id": c["chantier_id"], "published": True}
        reports = await db.site_reports.find(q, {"_id": 0, "report_id": 1, "title": 1, "notes": 1, "photos": 1, "created_at": 1, "published_at": 1}).sort("created_at", -1).to_list(100)
        if not perms.get("photos"):
            for r in reports:
                r["photos"] = []
    progress = round(sum(m.get("progress_pct", 0) for m in milestones) / len(milestones)) if milestones else None
    return {"chantier": {"ref": c.get("ref") or p["chantier_ref"], "name": c["name"], "status": c.get("status"), "address": " ".join(filter(None, [c.get("address"), c.get("postal_code"), c.get("city")]))},
            "company": {"name": b.get("company_name") or (pro or {}).get("name") or "", "logo": logo, "accent": (pro or {}).get("brand_accent_color"),
                        "phone": b.get("contact_line") or (pro or {}).get("brand_phone") or (pro or {}).get("phone"), "email": b.get("company_email") or (pro or {}).get("email")},
            "participant": {"role": p["role"], "name": p.get("name"), "lot": p.get("lot"), "permissions": perms},
            "progress_pct": progress, "milestones": milestones, "reports": reports,
            "photos": [{"path": ph, "report_id": r["report_id"], "title": r.get("title"), "date": r.get("created_at")} for r in reports for ph in (r.get("photos") or [])]}


@pro_router.get("/{chantier_id}/preview-as")
async def preview_as(chantier_id: str, role: Literal["client", "subcontractor"] = "client", participant_id: Optional[str] = None, user=Depends(current_user)) -> dict:
    """« Voir comme le client » : exactement ce que verrait un invité (droits d'un participant réel ou droits par défaut du rôle)."""
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    p = await db.chantier_participants.find_one({"participant_id": participant_id, "chantier_id": chantier_id}, {"_id": 0, "invite_token_hash": 0}) if participant_id else None
    if not p:
        p = {"participant_id": None, "chantier_id": chantier_id, "chantier_ref": chantier.get("ref") or "CP-…", "role": role, "name": "Convidado (pré-visualização)", "lot": "", "permissions": dict(DEFAULT_PERMS[role])}
    from routes.portal_chat import ISSUE_LABELS, channel_for
    overview = await overview_for(p)
    perms = p.get("permissions") or {}
    messages = await db.chantier_messages.find({"chantier_id": chantier_id, "channel": channel_for(p)}, {"_id": 0}).sort("created_at", 1).to_list(200) if perms.get("chat") else []
    iq = {"chantier_id": chantier_id, "participant_id": p["participant_id"]} if p.get("participant_id") else {"chantier_id": chantier_id, "reporter_role": p["role"]}
    issues = await db.chantier_issues.find(iq, {"_id": 0, "history": 0}).sort("created_at", -1).to_list(100) if perms.get("report_issue") else []
    hidden = {"reports_internal": await db.site_reports.count_documents({"chantier_id": chantier_id, "published": {"$ne": True}}),
              "milestones_hidden": await db.chantier_milestones.count_documents({"chantier_id": chantier_id, "visible": False})}
    docs_view = {"quotes": [], "invoices": [], "can_sign": False}
    types = await _visible_types(p)
    if types:
        c = await db.chantiers.find_one({"chantier_id": chantier_id}, {"_id": 0})
        rows = await db.pro_documents.find(_doc_scope(c, types), {"_id": 0, "lines": 0, "frozen_pdf_b64": 0, "facturx_pdf_b64": 0}).to_list(300)
        for d in rows:
            if isinstance(d.get("created_at"), datetime):
                d["created_at"] = d["created_at"].isoformat()
        cards = sorted((_doc_card(d) for d in rows), key=lambda x: x.get("created_at") or "", reverse=True)
        docs_view = {"quotes": [x for x in cards if x["doc_type"] == "quote"],
                     "invoices": [x for x in cards if x["doc_type"] in ("invoice", "credit_note")],
                     "can_sign": bool(perms.get("sign"))}
    return {**overview, "messages": messages, "issues": issues, "issue_labels": ISSUE_LABELS, "hidden": hidden,
            "documents": docs_view, "simulated": not bool(p.get("participant_id"))}


@router.get("/{ref}/photo")
async def portal_photo(ref: str, path: str, p=Depends(current_participant)):
    _require_ref(p, ref)
    if not (p.get("permissions") or {}).get("photos"):
        raise HTTPException(403, "Fotografias não partilhadas")
    owned = await db.site_reports.find_one({"chantier_id": p["chantier_id"], "published": True, "photos": path}, {"_id": 1})
    if not owned:
        raise HTTPException(404, "Fotografia não encontrada")
    data, ct = await asyncio.to_thread(storage.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ct, headers={"Cache-Control": "private, no-store"})


# ─────────────────────────  Sprint 3 : devis & factures dans le portail  ─────────────────────────

DOC_TYPE_PERM = {"quote": "quotes", "invoice": "invoices", "credit_note": "invoices"}


async def _chantier_of(p: dict) -> dict:
    c = await db.chantiers.find_one({"chantier_id": p["chantier_id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Obra não encontrada")
    return c


async def _visible_types(p: dict) -> list[str]:
    """Types de documents que ce participant a le droit de voir (droits + rôle client)."""
    perms = p.get("permissions") or {}
    if p.get("role") != "client":
        return []
    types = []
    if perms.get("quotes"):
        types.append("quote")
    if perms.get("invoices"):
        types += ["invoice", "credit_note"]
    return types


def _doc_scope(c: dict, types: list[str]) -> dict:
    """Documents rattachés à ce chantier (par chantier_id, ou par client si renseigné), hors brouillons."""
    ors = [{"chantier_id": c["chantier_id"]}]
    if c.get("client_id"):
        ors.append({"client_id": c["client_id"]})
    return {"user_id": c["user_id"], "doc_type": {"$in": types},
            "status": {"$nin": ["draft", "trashed"]}, "$or": ors}


def _doc_card(d: dict) -> dict:
    t = d.get("totals") or {}
    accepted = bool(d.get("client_accepted_at")) or bool(d.get("signed")) or d.get("status") in ("signed", "accepted", "invoiced")
    return {
        "doc_id": d["doc_id"], "doc_type": d["doc_type"],
        "number": d.get("number"), "title": d.get("title") or "",
        "status": d.get("status"), "issue_date": d.get("issue_date"), "due_date": d.get("due_date"),
        "total_ht": t.get("ht", 0), "total_ttc": t.get("ttc", 0),
        "accepted": accepted, "accepted_at": d.get("client_accepted_at") or d.get("signed_at"),
        "accepted_name": d.get("client_accepted_name"),
        "declined_at": d.get("client_declined_at"),
        "signed": bool(d.get("signed")),
        "created_at": d.get("created_at"),
    }


@router.get("/{ref}/documents")
async def portal_documents(ref: str, p=Depends(current_participant)) -> dict:
    """Devis & factures partagés avec le client de ce chantier."""
    _require_ref(p, ref)
    types = await _visible_types(p)
    if not types:
        return {"quotes": [], "invoices": [], "can_sign": False}
    c = await _chantier_of(p)
    docs = await db.pro_documents.find(_doc_scope(c, types), {"_id": 0, "lines": 0, "frozen_pdf_b64": 0, "facturx_pdf_b64": 0}).to_list(300)
    for d in docs:
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
    cards = [_doc_card(d) for d in docs]
    cards.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"quotes": [x for x in cards if x["doc_type"] == "quote"],
            "invoices": [x for x in cards if x["doc_type"] in ("invoice", "credit_note")],
            "can_sign": bool((p.get("permissions") or {}).get("sign"))}


async def _portal_doc(ref: str, doc_id: str, p: dict) -> tuple[dict, dict]:
    _require_ref(p, ref)
    types = await _visible_types(p)
    c = await _chantier_of(p)
    d = await db.pro_documents.find_one({**_doc_scope(c, types or ["quote", "invoice", "credit_note"]),
                                         "doc_id": doc_id}, {"_id": 0})
    if not d or d["doc_type"] not in types:
        raise HTTPException(404, "Documento não encontrado")
    return c, d


@router.get("/{ref}/document/{doc_id}/pdf")
async def portal_document_pdf(ref: str, doc_id: str, p=Depends(current_participant)):
    c, d = await _portal_doc(ref, doc_id, p)
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding
    from routes.reviews import get_reviews_for_user
    from routes.company_page import pdf_customization
    from routes.documents import _doc_lang
    branding = {**(await _resolve_branding(c["user_id"]) or {}), **await pdf_customization(c["user_id"])}
    reviews = await get_reviews_for_user(c["user_id"]) if d["doc_type"] == "quote" else None
    pdf = build_document_pdf(d, branding=branding, reviews=reviews, lang=await _doc_lang(d, branding))
    fname = f"{d.get('number') or d['doc_id']}.pdf"
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{fname}"',
                                      "Cache-Control": "private, no-store"})


async def _notify_pro_decision(d: dict, c: dict, p: dict, accepted: bool, signer: str = "") -> None:
    label = "accepté" if accepted else "refusé"
    who = signer or p.get("name") or p.get("email")
    msg = f"Orçamento {d.get('number') or ''} {label} por {who} · obra {c.get('name') or ''}".strip()
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(6), "user_id": c["user_id"],
        "type": "quote_accepted" if accepted else "quote_declined", "doc_id": d["doc_id"],
        "message": msg, "url": f"/chantiers/{c['chantier_id']}", "read": False, "created_at": _iso(_now())})
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": c["user_id"]}, {"_id": 0, "email": 1})
        if pro and pro.get("email"):
            await send_email(pro["email"], f"{('✅' if accepted else '✖')} Orçamento {label} — {c.get('name') or ''}",
                             wrap_html(f'Orçamento {label}', f'<p>{msg}.</p><p>Encontre-o no acompanhamento dos seus orçamentos.</p>'))
    except Exception:  # noqa: BLE001
        pass


class SignIn(BaseModel):
    signature: str = Field(..., min_length=2, max_length=120)


@router.post("/{ref}/document/{doc_id}/accept")
async def portal_accept_quote(ref: str, doc_id: str, body: SignIn, request: Request,
                              p=Depends(current_participant)) -> dict:
    """Le client accepte le devis en ligne (bon pour accord signé de son nom)."""
    if not (p.get("permissions") or {}).get("sign"):
        raise HTTPException(403, "A assinatura online não é autorizada nesta obra")
    c, d = await _portal_doc(ref, doc_id, p)
    if d["doc_type"] != "quote":
        raise HTTPException(400, "Apenas um orçamento pode ser aceite")
    if d.get("client_declined_at"):
        raise HTTPException(400, "Este orçamento já foi recusado")
    if d.get("client_accepted_at") or d.get("signed"):
        return {"ok": True, "already": True, "document": _doc_card(d)}
    signer = body.signature.strip()[:120]
    now = _iso(_now())
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": c["user_id"]}, {"$set": {
        "client_accepted_at": now, "client_accepted_by": p["participant_id"],
        "client_accepted_name": signer, "client_accepted_via": "portail",
        "client_accepted_ip": (request.client.host if request.client else None),
        "signed": True, "signed_at": now, "status": "signed"}})
    d.update({"client_accepted_at": now, "client_accepted_name": signer, "signed": True, "status": "signed"})
    await _notify_pro_decision(d, c, p, True, signer)
    deposit = await _auto_deposit(d, c)
    return {"ok": True, "document": _doc_card(d), "deposit_invoice": deposit}


async def _auto_deposit(d: dict, c: dict) -> dict | None:
    """Génère la facture d'acompte si le pro l'a activée (réglage documents/auto-deposit).

    Pourcentage : celui saisi sur le devis s'il est > 0, sinon le réglage « acompte auto »
    (défaut 30 %). Silencieux si déjà émis ou en cas d'erreur : l'acceptation reste prioritaire.
    """
    owner = await db.users.find_one(
        {"user_id": c["user_id"]},
        {"_id": 0, "user_id": 1, "name": 1, "email": 1, "auto_deposit_invoice": 1, "auto_deposit_pct": 1}) or {}
    if not owner.get("auto_deposit_invoice"):
        return None
    pct = d.get("deposit_pct") or 0
    if not pct or pct <= 0:
        pct = owner.get("auto_deposit_pct") or 30
    try:
        from routes.documents import build_deposit_invoice
        inv = await build_deposit_invoice(d["doc_id"], owner, float(pct))
        return {"doc_id": inv["doc_id"], "number": inv.get("number"), "pct": float(pct)}
    except HTTPException:
        return None  # ex. : acompte déjà existant
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("auto deposit failed: %s", exc)
        return None


class DeclineIn(BaseModel):
    reason: str = Field("", max_length=500)


@router.post("/{ref}/document/{doc_id}/decline")
async def portal_decline_quote(ref: str, doc_id: str, body: DeclineIn,
                               p=Depends(current_participant)) -> dict:
    """Le client refuse le devis en ligne (motif facultatif)."""
    if not (p.get("permissions") or {}).get("sign"):
        raise HTTPException(403, "A ação não é autorizada nesta obra")
    c, d = await _portal_doc(ref, doc_id, p)
    if d["doc_type"] != "quote":
        raise HTTPException(400, "Apenas um orçamento pode ser recusado")
    if d.get("signed") or d.get("client_accepted_at"):
        raise HTTPException(400, "Este orçamento já foi aceite")
    now = _iso(_now())
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": c["user_id"]}, {"$set": {
        "client_declined_at": now, "client_declined_reason": body.reason.strip()[:500],
        "client_declined_by": p["participant_id"], "status": "refused"}})
    d.update({"client_declined_at": now, "status": "refused"})
    await _notify_pro_decision(d, c, p, False)
    return {"ok": True, "document": _doc_card(d)}



# ─────────────────────  PV de réception de travaux (Sprint 4)  ─────────────────────

PV_DECISIONS = ("sans_reserve", "avec_reserve", "refus")


class PvReserveIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=500)
    lot: str = Field("", max_length=80)


class PvIn(BaseModel):
    date_reception: str = Field("", max_length=30)
    decision: str = "sans_reserve"
    reserves: list[PvReserveIn] = []
    notes: str = Field("", max_length=2000)
    import_open_reserves: bool = False


def _pv_public(pv: dict) -> dict:
    return {k: v for k, v in pv.items() if k != "_id"}


async def _owned_pv(pv_id: str, user_id: str) -> dict:
    pv = await db.pv_receptions.find_one({"pv_id": pv_id, "user_id": user_id}, {"_id": 0})
    if not pv:
        raise HTTPException(404, "Auto não encontrado")
    return pv


async def _pv_branding(user_id: str) -> dict:
    from routes.plans_common import _resolve_branding
    from routes.company_page import pdf_customization
    return {**(await _resolve_branding(user_id) or {}), **await pdf_customization(user_id)}


@pro_router.post("/{chantier_id}/receptions", status_code=201)
async def create_pv(chantier_id: str, body: PvIn, user=Depends(current_user)) -> dict:
    c = await get_chantier_owned(chantier_id, user["user_id"])
    if body.decision not in PV_DECISIONS:
        raise HTTPException(400, "Decisão inválida")
    client = await db.clients.find_one({"client_id": c.get("client_id"), "user_id": user["user_id"]}, {"_id": 0}) if c.get("client_id") else None
    reserves = [{"id": secrets.token_hex(4), "description": r.description.strip()[:500],
                 "lot": r.lot.strip()[:80], "lifted_at": None, "lifted_by": None}
                for r in body.reserves]
    if body.import_open_reserves:
        rx = {"user_id": user["user_id"], "chantier_id": chantier_id, "status": {"$nin": ["levee", "lifted", "closed", "done"]}}
        for r in await db.site_reserves.find(rx, {"_id": 0, "description": 1, "lot": 1}).to_list(200):
            reserves.append({"id": secrets.token_hex(4), "description": (r.get("description") or "").strip()[:500],
                             "lot": (r.get("lot") or "").strip()[:80], "lifted_at": None, "lifted_by": None})
    now = _iso(_now())
    seq = await db.pv_receptions.count_documents({"user_id": user["user_id"]}) + 1
    pv = {
        "pv_id": "pv_" + secrets.token_hex(6), "user_id": user["user_id"],
        "chantier_id": chantier_id, "chantier_ref": c.get("ref"), "chantier_name": c.get("name"),
        "chantier_address": ", ".join(x for x in [c.get("address"), c.get("postal_code"), c.get("city")] if x),
        "client": client, "ref": f"PV-{now[:4]}-{seq:04d}",
        "date_reception": (body.date_reception or now[:10]), "decision": body.decision,
        "reserves": reserves, "notes": body.notes.strip()[:2000],
        "status": "draft", "pro_signature": None, "client_signature": None,
        "created_at": now, "updated_at": now,
    }
    await db.pv_receptions.insert_one(dict(pv))
    return _pv_public(pv)


@pro_router.get("/{chantier_id}/receptions")
async def list_pv(chantier_id: str, user=Depends(current_user)) -> list:
    await get_chantier_owned(chantier_id, user["user_id"])
    return await db.pv_receptions.find({"user_id": user["user_id"], "chantier_id": chantier_id}, {"_id": 0}).sort("created_at", -1).to_list(100)


@pro_router.put("/receptions/{pv_id}")
async def update_pv(pv_id: str, body: PvIn, user=Depends(current_user)) -> dict:
    pv = await _owned_pv(pv_id, user["user_id"])
    if pv.get("client_signature"):
        raise HTTPException(409, "O cliente já assinou este auto: já não pode ser modificado")
    if body.decision not in PV_DECISIONS:
        raise HTTPException(400, "Decisão inválida")
    reserves = [{"id": secrets.token_hex(4), "description": r.description.strip()[:500],
                 "lot": r.lot.strip()[:80], "lifted_at": None, "lifted_by": None} for r in body.reserves]
    upd = {"decision": body.decision, "reserves": reserves, "notes": body.notes.strip()[:2000],
           "date_reception": (body.date_reception or pv.get("date_reception")), "updated_at": _iso(_now())}
    await db.pv_receptions.update_one({"pv_id": pv_id, "user_id": user["user_id"]}, {"$set": upd})
    return _pv_public({**pv, **upd})


class PvSignIn(BaseModel):
    signature: str = Field(..., min_length=2, max_length=120)


@pro_router.post("/receptions/{pv_id}/sign")
async def sign_pv_pro(pv_id: str, body: PvSignIn, user=Depends(current_user)) -> dict:
    pv = await _owned_pv(pv_id, user["user_id"])
    now = _iso(_now())
    sig = {"name": body.signature.strip()[:120], "at": now}
    await db.pv_receptions.update_one({"pv_id": pv_id, "user_id": user["user_id"]}, {"$set": {"pro_signature": sig, "updated_at": now}})
    return _pv_public({**pv, "pro_signature": sig})


@pro_router.post("/receptions/{pv_id}/publish")
async def publish_pv(pv_id: str, user=Depends(current_user)) -> dict:
    pv = await _owned_pv(pv_id, user["user_id"])
    status = pv.get("status") if pv.get("status") in ("signed",) else "published"
    await db.pv_receptions.update_one({"pv_id": pv_id, "user_id": user["user_id"]}, {"$set": {"status": status, "published_at": _iso(_now())}})
    return _pv_public({**pv, "status": status})


@pro_router.delete("/receptions/{pv_id}")
async def delete_pv(pv_id: str, user=Depends(current_user)) -> dict:
    pv = await _owned_pv(pv_id, user["user_id"])
    if pv.get("client_signature"):
        raise HTTPException(409, "Auto assinado pelo cliente: eliminação impossível")
    await db.pv_receptions.delete_one({"pv_id": pv_id, "user_id": user["user_id"]})
    return {"ok": True}


@pro_router.get("/receptions/{pv_id}/pdf")
async def pv_pdf_pro(pv_id: str, user=Depends(current_user)):
    pv = await _owned_pv(pv_id, user["user_id"])
    from engines.pv_pdf import build_pv_pdf
    pdf = build_pv_pdf(pv, await _pv_branding(user["user_id"]))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{pv.get("ref") or pv_id}.pdf"',
                                      "Cache-Control": "private, no-store"})


# ---- Côté portail (client) ----

@router.get("/{ref}/planning")
async def portal_planning(ref: str, p=Depends(current_participant)) -> dict:
    _require_ref(p, ref)
    if not (p.get("permissions") or {}).get("progress"):
        return {"planning": None}
    from routes.planning import client_view
    return {"planning": await client_view(p["chantier_id"])}


@router.get("/{ref}/receptions")
async def portal_receptions(ref: str, p=Depends(current_participant)) -> dict:
    _require_ref(p, ref)
    if p.get("role") != "client":
        return {"receptions": [], "can_sign": False}
    rows = await db.pv_receptions.find(
        {"chantier_id": p["chantier_id"], "status": {"$in": ["published", "signed"]}},
        {"_id": 0, "pv_id": 1, "ref": 1, "date_reception": 1, "decision": 1, "reserves": 1,
         "status": 1, "pro_signature": 1, "client_signature": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(50)
    for r in rows:
        rlist = r.get("reserves") or []
        r["reserve_count"] = len(rlist)
        r["reserve_lifted"] = sum(1 for x in rlist if x.get("lifted_at"))
        r["reserves"] = [{"id": x.get("id"), "description": x.get("description"), "lot": x.get("lot"),
                          "lifted_at": x.get("lifted_at"), "lifted_by": x.get("lifted_by")} for x in rlist]
        r["signed_client"] = bool(r.get("client_signature"))
    return {"receptions": rows, "can_sign": bool((p.get("permissions") or {}).get("sign"))}


async def _portal_pv(ref: str, pv_id: str, p: dict) -> dict:
    _require_ref(p, ref)
    if p.get("role") != "client":
        raise HTTPException(403, "Reservado ao cliente da obra")
    pv = await db.pv_receptions.find_one(
        {"pv_id": pv_id, "chantier_id": p["chantier_id"], "status": {"$in": ["published", "signed"]}}, {"_id": 0})
    if not pv:
        raise HTTPException(404, "Auto não encontrado")
    return pv


@router.get("/{ref}/reception/{pv_id}/pdf")
async def portal_pv_pdf(ref: str, pv_id: str, p=Depends(current_participant)):
    pv = await _portal_pv(ref, pv_id, p)
    from engines.pv_pdf import build_pv_pdf
    pdf = build_pv_pdf(pv, await _pv_branding(pv["user_id"]))
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": f'inline; filename="{pv.get("ref") or pv_id}.pdf"',
                                      "Cache-Control": "private, no-store"})


@router.post("/{ref}/reception/{pv_id}/sign")
async def portal_pv_sign(ref: str, pv_id: str, body: PvSignIn, request: Request,
                         p=Depends(current_participant)) -> dict:
    if not (p.get("permissions") or {}).get("sign"):
        raise HTTPException(403, "A assinatura online não é autorizada nesta obra")
    pv = await _portal_pv(ref, pv_id, p)
    if pv.get("client_signature"):
        return {"ok": True, "already": True}
    now = _iso(_now())
    sig = {"name": body.signature.strip()[:120], "at": now, "by": p["participant_id"],
           "ip": (request.client.host if request.client else None)}
    await db.pv_receptions.update_one({"pv_id": pv_id}, {"$set": {
        "client_signature": sig, "status": "signed", "updated_at": now}})
    c = await db.chantiers.find_one({"chantier_id": pv["chantier_id"]}, {"_id": 0, "user_id": 1, "name": 1, "chantier_id": 1})
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(6), "user_id": pv["user_id"], "type": "pv_signed",
        "message": f"Auto de receção {pv.get('ref') or ''} assinado por {sig['name']} · {(c or {}).get('name') or ''}".strip(),
        "url": f"/chantiers/{pv['chantier_id']}", "read": False, "created_at": now})
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": pv["user_id"]}, {"_id": 0, "email": 1})
        if pro and pro.get("email"):
            await send_email(pro["email"], f"✅ Auto de receção assinado — {(c or {}).get('name') or ''}",
                             wrap_html("Auto de receção assinado", f"<p>O auto <strong>{pv.get('ref') or ''}</strong> acaba de ser assinado online por {sig['name']}.</p>"))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True}


class ReserveLiftIn(BaseModel):
    resolved: bool = True


@router.post("/{ref}/reception/{pv_id}/reserve/{reserve_id}/lift")
async def portal_lift_reserve(ref: str, pv_id: str, reserve_id: str, body: ReserveLiftIn,
                              p=Depends(current_participant)) -> dict:
    """Le client marque une réserve du PV comme levée (résolue) — ou annule ce marquage."""
    pv = await _portal_pv(ref, pv_id, p)
    reserves = pv.get("reserves") or []
    target = next((r for r in reserves if r.get("id") == reserve_id), None)
    if not target:
        raise HTTPException(404, "Reserva não encontrada")
    now = _iso(_now())
    who = (p.get("display_name") or p.get("name") or p.get("email") or "Cliente")
    for r in reserves:
        if r.get("id") == reserve_id:
            r["lifted_at"] = now if body.resolved else None
            r["lifted_by"] = who if body.resolved else None
    await db.pv_receptions.update_one({"pv_id": pv_id}, {"$set": {"reserves": reserves, "updated_at": now}})
    if body.resolved:
        c = await db.chantiers.find_one({"chantier_id": pv["chantier_id"]}, {"_id": 0, "name": 1, "chantier_id": 1})
        await db.notifications.insert_one({
            "notif_id": "n_" + secrets.token_hex(6), "user_id": pv["user_id"], "type": "reserve_lifted",
            "message": f"Reserva levantada por {who} no auto {pv.get('ref') or ''} · {(c or {}).get('name') or ''}".strip(),
            "url": f"/chantiers/{pv['chantier_id']}", "read": False, "created_at": now})
    lifted = sum(1 for r in reserves if r.get("lifted_at"))
    return {"ok": True, "reserve_id": reserve_id, "lifted_at": target.get("lifted_at"),
            "lifted_by": target.get("lifted_by"), "reserve_lifted": lifted, "reserve_count": len(reserves)}
