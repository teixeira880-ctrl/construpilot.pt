"""Routes Phase 7 : Push notifications + Retention email + Referral share + Team."""
import os
import json
import secrets
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, EmailStr

from core.db import db
from core.security import current_user, admin_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["phase7"])

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "admin@construpilot.fr")


def _now():
    return datetime.now(timezone.utc).isoformat()


# =============== PUSH NOTIFICATIONS ===============

@router.get("/push/public-key")
async def push_public_key() -> dict:
    return {"public_key": VAPID_PUBLIC}


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict  # {p256dh, auth}


@router.post("/push/subscribe")
async def push_subscribe(body: PushSubIn, user=Depends(current_user)) -> dict:
    doc = {"user_id": user["user_id"], "endpoint": body.endpoint,
           "keys": body.keys, "created_at": _now()}
    await db.push_subscriptions.update_one({"endpoint": body.endpoint},
                                           {"$set": doc}, upsert=True)
    return {"ok": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(body: PushSubIn, user=Depends(current_user)) -> dict:
    await db.push_subscriptions.delete_one({"endpoint": body.endpoint,
                                            "user_id": user["user_id"]})
    return {"ok": True}


def _send_push(sub: dict, payload: dict) -> bool:
    if not VAPID_PRIVATE:
        return False
    try:
        from pywebpush import webpush
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"})
        return True
    except Exception as e:  # includes WebPushException
        logger.warning(f"Push failed for {sub.get('endpoint','')[:40]}: {e}")
        return False


async def notify_user(user_id: str, title: str, body: str, url: str = "/") -> int:
    subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(20)
    sent = 0
    for s in subs:
        payload = {"title": title, "body": body, "url": url,
                   "icon": "/logo192.png"}
        if _send_push(s, payload):
            sent += 1
    return sent


@router.post("/push/test")
async def push_test(user=Depends(current_user)) -> dict:
    n = await notify_user(user["user_id"], "ConstruPilot",
                          "🎉 Vos notifications push sont bien activées !", "/dashboard")
    return {"ok": True, "sent": n}


# =============== RETENTION digest manual trigger ===============

@router.post("/admin/retention/send-digests")
async def send_digests_now(admin=Depends(admin_user)) -> dict:
    from engines import retention
    sent = await retention.send_weekly_digests()
    return {"ok": True, "sent": sent}


# =============== USER PREFS ===============

class PrefsIn(BaseModel):
    weekly_digest: bool | None = None
    push_price_alerts: bool | None = None


@router.put("/users/me/preferences")
async def update_prefs(body: PrefsIn, user=Depends(current_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    fresh = await db.users.find_one({"user_id": user["user_id"]},
                                    {"_id": 0, "weekly_digest": 1, "push_price_alerts": 1})
    return fresh or {}


# =============== PDF BRANDING (Pro) ===============

class BrandingIn(BaseModel):
    company_name: str | None = None
    company_email: str | None = None
    contact_line: str | None = None
    logo_b64: str | None = None
    siret: str | None = None
    vat: str | None = None
    address: str | None = None
    city: str | None = None
    postal_code: str | None = None
    country: str | None = None
    certifications: list[dict] | None = None


CERT_LABELS = {"qualibat": "Qualibat", "rge": "RGE", "qualipac": "QualiPAC",
               "qualifelec": "Qualifelec", "qualibois": "Qualibois"}


class OrgJoinIn(BaseModel):
    org_code: str = Field(min_length=4, max_length=32)


class SnapshotLabelIn(BaseModel):
    label: str = Field(max_length=80)


@router.get("/users/me/branding")
async def get_branding(user=Depends(current_user)) -> dict:
    # Si user membre d'une org → branding org (partagé équipe)
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1,
                                  "brand_company_name": 1, "brand_contact_line": 1,
                                  "brand_company_email": 1,
                                  "brand_siret": 1, "brand_vat": 1,
                                  "brand_address": 1, "brand_city": 1,
                                  "brand_postal": 1, "brand_country": 1,
                                  "brand_logo_b64": 1, "brand_certifications": 1}) or {}
    org_id = u.get("organization_id")
    if org_id:
        org = await db.organizations.find_one({"org_id": org_id},
                                                {"_id": 0, "brand_company_name": 1,
                                                 "brand_contact_line": 1,
                                                 "brand_company_email": 1,
                                                 "brand_logo_b64": 1, "org_code": 1,
                                                 "brand_certifications": 1,
                                                 "org_id": 1, "name": 1})
        if org:
            role = u.get("org_role", "member")
            return {"source": "organization", "org_id": org["org_id"],
                    "org_code": org.get("org_code"), "org_name": org.get("name"),
                    "org_role": role, "can_edit": role in ("owner", "admin"),
                    "company_name": org.get("brand_company_name"),
                    "company_email": org.get("brand_company_email"),
                    "contact_line": org.get("brand_contact_line"),
                    "has_logo": bool(org.get("brand_logo_b64")),
                    "logo_b64": org.get("brand_logo_b64"),
                    "certifications": org.get("brand_certifications") or []}
    return {"source": "user", "can_edit": True,
            "company_name": u.get("brand_company_name"),
            "company_email": u.get("brand_company_email"),
            "contact_line": u.get("brand_contact_line"),
            "siret": u.get("brand_siret"),
            "vat": u.get("brand_vat"),
            "address": u.get("brand_address"),
            "city": u.get("brand_city"),
            "postal_code": u.get("brand_postal"),
            "country": u.get("brand_country"),
            "has_logo": bool(u.get("brand_logo_b64")),
            "logo_b64": u.get("brand_logo_b64"),
            "certifications": u.get("brand_certifications") or []}


@router.put("/users/me/branding")
async def update_branding(body: BrandingIn, user=Depends(current_user)):
    # Récupère l'org id (si l'utilisateur en fait partie)
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1}) or {}
    org_id = u.get("organization_id")

    upd = {}
    if body.company_name is not None:
        upd["brand_company_name"] = body.company_name.strip()[:120] or None
    if body.company_email is not None:
        import re as _re
        ce = body.company_email.strip().lower()[:120]
        upd["brand_company_email"] = ce if _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", ce) else None
    if body.contact_line is not None:
        upd["brand_contact_line"] = body.contact_line.strip()[:200] or None
    if body.siret is not None:
        upd["brand_siret"] = "".join(ch for ch in body.siret if ch.isdigit())[:14] or None
    if body.vat is not None:
        upd["brand_vat"] = body.vat.strip().upper().replace(" ", "")[:20] or None
    if body.address is not None:
        upd["brand_address"] = body.address.strip()[:160] or None
    if body.city is not None:
        upd["brand_city"] = body.city.strip()[:80] or None
    if body.postal_code is not None:
        upd["brand_postal"] = body.postal_code.strip()[:12] or None
    if body.country is not None:
        upd["brand_country"] = body.country.strip().upper()[:2] or None
    if body.certifications is not None:
        certs = []
        for c in (body.certifications or [])[:10]:
            code = str(c.get("code", "")).lower().strip()
            if code in CERT_LABELS:
                certs.append({"code": code, "number": str(c.get("number", "")).strip()[:40]})
        upd["brand_certifications"] = certs
    if body.logo_b64 is not None:
        # Limite raisonnable : ~500 ko en base64 = 375 ko fichier
        b64_clean = body.logo_b64.split(",")[-1] if body.logo_b64 else ""
        if len(b64_clean) > 500_000:
            raise HTTPException(413, "Logo trop volumineux (max ~375 Ko)")
        upd["brand_logo_b64"] = b64_clean or None

    if org_id:
        # Seul le owner/admin de l'org peut modifier le branding partagé
        if u.get("org_role") not in ("owner", "admin"):
            raise HTTPException(403,
                "Le branding de l'équipe ne peut être modifié que par un admin/propriétaire de l'organisation.")
        if upd:
            await db.organizations.update_one({"org_id": org_id}, {"$set": upd})
    else:
        if upd:
            await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})

    return await get_branding(user)


# =============== TEAM / ORGANIZATIONS (Multi-User Branding) ===============

class OrgCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class OrgInviteIn(BaseModel):
    email: EmailStr
    role: str = Field(default="member")  # member | admin


def _new_org_code() -> str:
    """Code humain simple : 4 lettres + 4 chiffres, ex CPLT-4821 (non-prédictible)."""
    letters = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))
    digits = "".join(str(secrets.randbelow(10)) for _ in range(4))
    return f"{letters}-{digits}"


async def _org_public(org_id: str) -> dict | None:
    org = await db.organizations.find_one({"org_id": org_id}, {"_id": 0})
    if not org:
        return None
    members = await db.users.find(
        {"organization_id": org_id},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1, "org_role": 1, "joined_org_at": 1}
    ).to_list(200)
    return {
        "org_id": org["org_id"],
        "org_code": org.get("org_code"),
        "name": org.get("name"),
        "owner_user_id": org.get("owner_user_id"),
        "created_at": org.get("created_at"),
        "member_count": len(members),
        "members": members,
        "has_branding": any(org.get(k) for k in
                            ("brand_company_name", "brand_contact_line", "brand_logo_b64")),
    }


@router.get("/organizations/me")
async def org_me(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1})
    org_id = (u or {}).get("organization_id")
    if not org_id:
        return {"in_org": False}
    org = await _org_public(org_id)
    if not org:
        # Utilisateur pointé vers une org supprimée → cleanup
        await db.users.update_one({"user_id": user["user_id"]},
                                   {"$unset": {"organization_id": "", "org_role": ""}})
        return {"in_org": False}
    return {"in_org": True, "role": u.get("org_role", "member"), **org}


@router.post("/organizations")
async def org_create(body: OrgCreateIn, user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1})
    if u and u.get("organization_id"):
        raise HTTPException(400, "Vous appartenez déjà à une organisation.")
    org_id = "org_" + secrets.token_hex(6)
    # Génère un code unique
    for _ in range(10):
        code = _new_org_code()
        if not await db.organizations.find_one({"org_code": code}):
            break
    else:
        raise HTTPException(500, "Impossible de générer un code d'organisation")
    doc = {
        "org_id": org_id,
        "org_code": code,
        "name": body.name.strip(),
        "owner_user_id": user["user_id"],
        "created_at": _now(),
        # branding vide initialement — hérite du branding user si présent
        "brand_company_name": None, "brand_contact_line": None, "brand_logo_b64": None,
    }
    # Migre le branding perso du user vers l'org à la création
    u_full = await db.users.find_one({"user_id": user["user_id"]},
                                      {"_id": 0, "brand_company_name": 1,
                                       "brand_contact_line": 1, "brand_logo_b64": 1})
    if u_full:
        for k in ("brand_company_name", "brand_contact_line", "brand_logo_b64"):
            if u_full.get(k):
                doc[k] = u_full[k]
    await db.organizations.insert_one(doc)
    await db.users.update_one({"user_id": user["user_id"]},
                               {"$set": {"organization_id": org_id, "org_role": "owner",
                                          "joined_org_at": _now()}})
    return {"ok": True, **(await _org_public(org_id))}


class OrgJoinCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=32)


@router.post("/organizations/join")
async def org_join(body: OrgJoinCodeIn, user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1})
    if u and u.get("organization_id"):
        raise HTTPException(400, "Vous appartenez déjà à une organisation. Quittez-la d'abord.")
    code = body.code.strip().upper()
    org = await db.organizations.find_one({"org_code": code}, {"_id": 0, "org_id": 1, "name": 1})
    if not org:
        raise HTTPException(404, "Code d'organisation inconnu")
    await db.users.update_one({"user_id": user["user_id"]},
                               {"$set": {"organization_id": org["org_id"],
                                          "org_role": "member",
                                          "joined_org_at": _now()}})
    return {"ok": True, "org_id": org["org_id"], "org_name": org["name"]}


@router.post("/organizations/leave")
async def org_leave(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1})
    org_id = (u or {}).get("organization_id")
    if not org_id:
        raise HTTPException(400, "Aucune organisation.")
    if u.get("org_role") == "owner":
        # Check that there are other members
        others = await db.users.count_documents({"organization_id": org_id,
                                                  "user_id": {"$ne": user["user_id"]}})
        if others > 0:
            raise HTTPException(400,
                "Le propriétaire ne peut pas quitter tant qu'il reste des membres. "
                "Transférez la propriété ou retirez d'abord tous les membres.")
        # Owner solo → supprime l'org
        await db.organizations.delete_one({"org_id": org_id})
    await db.users.update_one({"user_id": user["user_id"]},
                               {"$unset": {"organization_id": "", "org_role": "",
                                            "joined_org_at": ""}})
    return {"ok": True}


class OrgTransferIn(BaseModel):
    new_owner_user_id: str


@router.post("/organizations/transfer-ownership")
async def org_transfer_ownership(body: OrgTransferIn, user=Depends(current_user)) -> dict:
    """Transfère la propriété de l'org à un autre membre. L'ancien devient admin."""
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1})
    if not u or not u.get("organization_id"):
        raise HTTPException(400, "Aucune organisation.")
    if u.get("org_role") != "owner":
        raise HTTPException(403, "Réservé au propriétaire actuel.")
    if body.new_owner_user_id == user["user_id"]:
        raise HTTPException(400, "Vous êtes déjà propriétaire.")
    new_owner = await db.users.find_one(
        {"user_id": body.new_owner_user_id, "organization_id": u["organization_id"]},
        {"_id": 0, "user_id": 1, "email": 1, "name": 1}
    )
    if not new_owner:
        raise HTTPException(404, "Ce membre ne fait pas partie de votre organisation.")
    # Swap roles
    await db.users.update_one({"user_id": user["user_id"]},
                               {"$set": {"org_role": "admin"}})
    await db.users.update_one({"user_id": body.new_owner_user_id},
                               {"$set": {"org_role": "owner"}})
    await db.organizations.update_one({"org_id": u["organization_id"]},
                                       {"$set": {"owner_user_id": body.new_owner_user_id}})
    return {"ok": True, "new_owner": new_owner}


@router.delete("/organizations/members/{member_user_id}")
async def org_remove_member(member_user_id: str, user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1})
    if not u or not u.get("organization_id"):
        raise HTTPException(400, "Aucune organisation.")
    if u.get("org_role") not in ("owner", "admin"):
        raise HTTPException(403, "Réservé au propriétaire/admin.")
    if member_user_id == user["user_id"]:
        raise HTTPException(400, "Utilisez /leave pour vous retirer vous-même.")
    m = await db.users.find_one({"user_id": member_user_id,
                                  "organization_id": u["organization_id"]},
                                 {"_id": 0, "org_role": 1})
    if not m:
        raise HTTPException(404, "Membre introuvable dans l'organisation.")
    if m.get("org_role") == "owner":
        raise HTTPException(400, "Impossible de retirer le propriétaire.")
    await db.users.update_one({"user_id": member_user_id},
                               {"$unset": {"organization_id": "", "org_role": "",
                                            "joined_org_at": ""}})
    return {"ok": True}


@router.post("/organizations/invite")
async def org_invite(body: OrgInviteIn, user=Depends(current_user)) -> dict:
    """Envoie un email d'invitation contenant le code de l'organisation."""
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1, "email": 1,
                                  "name": 1})
    org_id = (u or {}).get("organization_id")
    if not org_id:
        raise HTTPException(400, "Créez d'abord une organisation.")
    if u.get("org_role") not in ("owner", "admin"):
        raise HTTPException(403, "Réservé au propriétaire/admin.")
    org = await db.organizations.find_one({"org_id": org_id},
                                            {"_id": 0, "org_code": 1, "name": 1})
    if not org:
        raise HTTPException(404, "Organisation introuvable.")

    invite_id = "inv_" + secrets.token_hex(6)
    invite = {
        "invite_id": invite_id, "org_id": org_id, "org_code": org["org_code"],
        "email": body.email.lower(), "role": body.role if body.role in ("member", "admin") else "member",
        "invited_by": user["user_id"], "invited_by_name": u.get("name") or u.get("email"),
        "created_at": _now(), "accepted": False,
    }
    await db.org_invites.insert_one(invite)

    # Email (best-effort)
    email_status = "skipped"
    try:
        from engines.emailer import send_email, wrap_html
        from_name = u.get("name") or u.get("email") or "Votre collègue"
        html = wrap_html(
            f"{from_name} vous invite sur ConstruPilot",
            f"<p>{from_name} vous invite à rejoindre l'organisation "
            f"<b>{org['name']}</b> sur ConstruPilot.</p>"
            f"<p style='font-size:16px'>Votre code d'invitation :</p>"
            f"<div style='font-family:monospace;font-size:26px;font-weight:800;"
            f"background:#f1f5f9;padding:14px 20px;border-radius:6px;text-align:center;"
            f"letter-spacing:3px;color:#FF5A00'>{org['org_code']}</div>"
            f"<p>Créez votre compte (ou connectez-vous) sur ConstruPilot puis rejoignez "
            f"l'équipe depuis <b>Équipe</b> avec ce code.</p>",
        )
        await send_email(body.email, f"Invitation ConstruPilot — {org['name']}", html)
        email_status = "sent"
    except Exception as e:
        logger.warning(f"Invite email failed: {e}")
        email_status = "failed"

    return {"ok": True, "invite_id": invite_id, "email_status": email_status,
            "org_code": org["org_code"]}



# =============== BOÎTE E-MAIL ENTREPRISE (SMTP, comme Obat) ===============

class MailboxIn(BaseModel):
    host: str
    port: int | None = None
    security: str = "ssl"  # "ssl" | "starttls"
    email: EmailStr
    password: str | None = None  # None => conserve le mot de passe existant
    from_name: str | None = None


async def _mailbox_target(user) -> tuple[str, dict]:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1, "org_role": 1}) or {}
    org_id = u.get("organization_id")
    if org_id:
        if u.get("org_role") not in ("owner", "admin"):
            raise HTTPException(403,
                "Seul un admin/propriétaire peut configurer la boîte e-mail de l'équipe.")
        return "organizations", {"org_id": org_id}
    return "users", {"user_id": user["user_id"]}


async def _mailbox_doc(user) -> tuple[dict, str]:
    """Retourne (doc effectif contenant les champs smtp_*, source)."""
    proj = {"_id": 0, "smtp_host": 1, "smtp_port": 1, "smtp_security": 1,
            "smtp_email": 1, "smtp_password_enc": 1, "smtp_from_name": 1,
            "smtp_verified": 1}
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {**proj, "organization_id": 1}) or {}
    if u.get("smtp_host"):
        return u, "user"
    if u.get("organization_id"):
        org = await db.organizations.find_one({"org_id": u["organization_id"]}, proj) or {}
        if org.get("smtp_host"):
            return org, "organization"
    return u, "user"


@router.get("/users/me/mailbox")
async def get_mailbox(user=Depends(current_user)) -> dict:
    doc, source = await _mailbox_doc(user)
    return {
        "configured": bool(doc.get("smtp_host") and doc.get("smtp_email")),
        "verified": bool(doc.get("smtp_verified")),
        "host": doc.get("smtp_host"),
        "port": doc.get("smtp_port"),
        "security": doc.get("smtp_security") or "ssl",
        "email": doc.get("smtp_email"),
        "from_name": doc.get("smtp_from_name"),
        "source": source,
    }


@router.put("/users/me/mailbox")
async def update_mailbox(body: MailboxIn, user=Depends(current_user)) -> dict:
    from engines.mailbox_smtp import encrypt_secret, decrypt_secret, smtp_verify
    coll, key = await _mailbox_target(user)
    existing = await db[coll].find_one(key, {"_id": 0, "smtp_password_enc": 1}) or {}

    if body.password:
        pwd = body.password
        enc = encrypt_secret(pwd)
    elif existing.get("smtp_password_enc"):
        enc = existing["smtp_password_enc"]
        try:
            pwd = decrypt_secret(enc)
        except Exception:  # noqa: BLE001
            raise HTTPException(400, "Mot de passe illisible — ressaisissez-le.")
    else:
        raise HTTPException(400, "Mot de passe d'application requis.")

    if body.security not in ("ssl", "starttls"):
        raise HTTPException(400, "Sécurité invalide (ssl ou starttls).")

    cfg = {"host": body.host.strip(), "port": body.port,
           "security": body.security, "email": str(body.email).strip().lower(),
           "password": pwd, "from_name": (body.from_name or "").strip() or None}

    # Vérifie la connexion + l'authentification avant d'enregistrer.
    try:
        await smtp_verify(cfg)
    except Exception as e:  # noqa: BLE001
        logger.warning("SMTP verify failed for %s: %s", cfg["email"], e)
        raise HTTPException(400,
            f"Connexion SMTP impossible : {str(e)[:180]}. Vérifiez l'hôte, le port, "
            "l'e-mail et le mot de passe d'application.")

    await db[coll].update_one(key, {"$set": {
        "smtp_host": cfg["host"], "smtp_port": cfg["port"],
        "smtp_security": cfg["security"], "smtp_email": cfg["email"],
        "smtp_password_enc": enc, "smtp_from_name": cfg["from_name"],
        "smtp_verified": True, "smtp_updated_at": _now(),
    }})
    return await get_mailbox(user)


@router.post("/users/me/mailbox/test")
async def test_mailbox(user=Depends(current_user)) -> dict:
    """Envoie un e-mail de test vers sa propre boîte (doit apparaître dans « Envoyés »)."""
    from routes.plans_common import get_mailbox_config
    from engines.mailbox_smtp import smtp_send
    cfg = await get_mailbox_config(user["user_id"])
    if not cfg:
        raise HTTPException(400, "Aucune boîte e-mail connectée/vérifiée.")
    html = ("<p>Ceci est un e-mail de test envoyé depuis ConstruPilot via votre boîte.</p>"
            "<p>Une copie doit apparaître dans votre dossier <b>Envoyés</b>. "
            "Si c'est le cas, la configuration est parfaite ✅</p>")
    try:
        await smtp_send(cfg, cfg["email"], "Test ConstruPilot — envoi via votre boîte",
                        html, from_name=cfg.get("from_name"))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Envoi de test échoué : {str(e)[:180]}")
    return {"ok": True, "sent_to": cfg["email"]}


@router.delete("/users/me/mailbox")
async def delete_mailbox(user=Depends(current_user)) -> dict:
    coll, key = await _mailbox_target(user)
    await db[coll].update_one(key, {"$unset": {
        "smtp_host": "", "smtp_port": "", "smtp_security": "",
        "smtp_email": "", "smtp_password_enc": "", "smtp_from_name": "",
        "smtp_verified": "", "smtp_updated_at": "",
    }})
    return {"ok": True}
