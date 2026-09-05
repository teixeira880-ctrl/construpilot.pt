import uuid
import asyncio
import hashlib
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Response, Request, Depends, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
import httpx

from core.db import db
from core.security import (hash_password, verify_password, make_jwt, new_user_id,
                          current_user, optional_user, admin_user)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    referred_by_code: str | None = None
    lang: str | None = None
    account_type: str | None = "particulier"
    siret: str | None = None


def _valid_siret(value: str) -> bool:
    import re
    s = re.sub(r"[ .\-]", "", value or "")
    if not re.fullmatch(r"\d{14}", s):
        return False
    total = 0
    for i, ch in enumerate(s):
        n = int(ch)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _public(u: dict) -> dict:
    out = {k: u.get(k) for k in ("user_id", "email", "name", "picture", "role", "plan",
                                  "phone", "auth_provider", "must_change_password",
                                  "two_fa_enabled", "two_fa_email", "invoicing_addon",
                                  "lang", "created_at", "account_type", "kyc_status",
                                  "siret")}
    out["has_password"] = bool(u.get("password_hash"))
    out["email_verified"] = bool(u.get("email_verified"))
    return out


async def _verify_email_token(token: str) -> dict:
    u = await db.users.find_one({"email_verify_token": token}, {"_id": 0, "user_id": 1, "email_verified": 1})
    if not u:
        raise HTTPException(status_code=404, detail="Lien de confirmation invalide ou expiré")
    if not u.get("email_verified"):
        await db.users.update_one({"user_id": u["user_id"]},
                                  {"$set": {"email_verified": True},
                                   "$unset": {"email_verify_token": ""}})
    return {"ok": True, "already": bool(u.get("email_verified"))}


async def _set_session(response: Response, user_id: str, token: str | None = None) -> str:
    token = token or f"st_{uuid.uuid4().hex}"
    await db.user_sessions.insert_one({
        "user_id": user_id, "session_token": token,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": datetime.now(timezone.utc),
    })
    # SEC-003 : SameSite=lax — front et API sur la même origine, bloque le CSRF cross-site
    response.set_cookie("session_token", token, httponly=True, secure=True,
                        samesite="lax", path="/", max_age=7 * 24 * 3600)
    return token


# ---- Protection anti-brute force (audit sécurité) ---------------------------
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _check_lockout(identifier: str) -> None:
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if not doc or doc.get("count", 0) < MAX_LOGIN_ATTEMPTS:
        return
    until = doc.get("locked_until")
    if until and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    if until and until > datetime.now(timezone.utc):
        raise HTTPException(status_code=429,
                            detail="Trop de tentatives — réessayez dans 15 minutes")
    await db.login_attempts.delete_one({"identifier": identifier})


async def _record_failed_login(identifier: str) -> None:
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1},
         "$set": {"locked_until": datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES),
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True)


@router.post("/register")
async def register(body: RegisterIn, response: Response) -> dict:
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe : 6 caractères minimum")
    account_type = body.account_type if body.account_type in ("particulier", "pro", "pro_business") else "particulier"
    is_pro = account_type in ("pro", "pro_business")
    siret = None
    if is_pro:
        import re
        siret = re.sub(r"[ .\-]", "", body.siret or "")
        if not _valid_siret(siret):
            raise HTTPException(status_code=400, detail="SIRET invalide (14 chiffres requis)")
    from engines.email_i18n import norm_lang
    user = {
        "user_id": new_user_id(), "email": email, "name": body.name,
        "password_hash": hash_password(body.password), "picture": None,
        "role": "user", "plan": "free", "auth_provider": "password",
        "account_type": account_type,
        "siret": siret,
        "kyc_status": "pending" if is_pro else "not_applicable",
        "kyc_documents": {},
        "referred_by": (body.referred_by_code or "").upper().strip() or None,
        "lang": norm_lang(body.lang),
        "email_verified": False,
        "email_verify_token": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    # E-mail de bienvenue (best-effort, ne bloque jamais l'inscription)
    try:
        import os
        from engines import emailer
        verify_url = f"{os.getenv('FRONTEND_URL', '')}/verifier-email/{user['email_verify_token']}"
        body_html = (
            f"<p>Bonjour {body.name.split(' ')[0] if body.name else ''},</p>"
            "<p>Bienvenue sur <b>ConstruPilot</b> ! Merci de <b>confirmer votre adresse e-mail</b> "
            "en cliquant sur le bouton ci-dessous pour activer toutes les fonctionnalités.</p>"
            "<p>Pour bien démarrer :</p>"
            "<ul style='margin:0 0 8px 18px;padding:0'>"
            "<li><b>Particulier</b> : estimez le coût de vos travaux et comparez les prix</li>"
            "<li><b>Professionnel</b> : mesurez un plan et générez un devis client</li>"
            "</ul>"
            "<p>À très vite,<br/>L'équipe ConstruPilot</p>"
        )
        html = emailer.wrap_html(
            "Confirmez votre e-mail — ConstruPilot 🎉", body_html,
            cta_url=verify_url,
            cta_label="Confirmer mon e-mail",
        )
        await emailer.send_email(email, "Confirmez votre e-mail — ConstruPilot", html)
    except Exception:
        pass
    # Credit the referrer (silent no-op if code invalid) — routed via referrals module
    if body.referred_by_code:
        from routes.referrals import credit_referrer
        try:
            await credit_referrer(body.referred_by_code)
        except Exception:
            pass  # never break signup on a bonus-credit error
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user), "token": make_jwt(user["user_id"]), "session_token": token}


@router.get("/verify-email/{token}")
async def verify_email(token: str) -> dict:
    return await _verify_email_token(token)


@router.post("/resend-verification")
async def resend_verification(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "email": 1, "name": 1, "email_verified": 1,
                                  "email_verify_token": 1})
    if not u:
        raise HTTPException(404, "Utilisateur introuvable")
    if u.get("email_verified"):
        return {"ok": True, "already_verified": True}
    token = u.get("email_verify_token") or uuid.uuid4().hex
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"email_verify_token": token}})
    try:
        import os
        from engines import emailer
        verify_url = f"{os.getenv('FRONTEND_URL', '')}/verifier-email/{token}"
        html = emailer.wrap_html(
            "Confirmez votre e-mail — ConstruPilot",
            "<p>Confirmez votre adresse e-mail pour activer toutes les fonctionnalités.</p>",
            cta_url=verify_url, cta_label="Confirmer mon e-mail")
        await emailer.send_email(u["email"], "Confirmez votre e-mail — ConstruPilot", html)
    except Exception:
        pass
    return {"ok": True, "sent": True}


async def run_signup_followups():
    """Relance J+3 : email aux inscrits (email/mot de passe) qui n'ont pas encore créé
    de devis. Envoyé une seule fois par utilisateur (flag jplus3_sent)."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    lo = (now - timedelta(days=4)).isoformat()
    hi = (now - timedelta(days=3)).isoformat()
    users = await db.users.find({
        "auth_provider": "password",
        "created_at": {"$gte": lo, "$lte": hi},
        "jplus3_sent": {"$ne": True},
    }, {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(500)
    if not users:
        return
    from engines import emailer
    for u in users:
        await db.users.update_one({"user_id": u["user_id"]}, {"$set": {"jplus3_sent": True}})
        # Actif = a créé un devis, une estimation/projet OU un plan → pas de relance
        uid = u["user_id"]
        active = (
            await db.pro_documents.find_one({"user_id": uid, "doc_type": "quote"}, {"_id": 1})
            or await db.projects.find_one({"user_id": uid}, {"_id": 1})
            or await db.plans_takeoff.find_one({"user_id": uid}, {"_id": 1})
        )
        if active:
            continue
        try:
            first = (u.get("name") or "").split(" ")[0]
            body_html = (
                f"<p>Bonjour {first},</p>"
                "<p>Vous avez créé votre compte ConstruPilot il y a quelques jours, "
                "mais vous n'avez pas encore commencé. On est là pour vous aider !</p>"
                "<p>En quelques minutes, vous pouvez :</p>"
                "<ul style='margin:0 0 8px 18px;padding:0'>"
                "<li><b>Particulier</b> : estimez le coût de vos travaux et comparez les prix</li>"
                "<li><b>Professionnel</b> : mesurez un plan et générez un devis client</li>"
                "</ul>"
                "<p>Tout est <b>gratuit pendant la phase de lancement</b>. À vous de jouer !</p>"
            )
            html = emailer.wrap_html(
                "Besoin d'un coup de main pour démarrer ?", body_html,
                cta_url="https://construpilot.fr/estimation",
                cta_label="Estimer mes travaux",
            )
            await emailer.send_email(
                u["email"], "Prêt à estimer votre projet ? On vous aide ⚡", html)
        except Exception:
            pass


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response) -> dict:
    email = body.email.lower()
    identifier = f"{_client_ip(request)}:{email}"
    await _check_lockout(identifier)
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        await _record_failed_login(identifier)
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    await db.login_attempts.delete_one({"identifier": identifier})
    if user.get("role") == "admin" and user.get("two_fa_enabled"):
        return await _start_2fa(user)
    await _register_device(user, request)
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user),
            "token": make_jwt(user["user_id"], user.get("token_version") or 0),
            "session_token": token}


class ChangePasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request,
                          user=Depends(current_user)) -> dict:
    """Change (ou définit) le mot de passe et révoque les autres sessions.

    - Compte avec mot de passe : `current_password` requis et vérifié.
    - Compte Google sans mot de passe : on autorise la DÉFINITION d'un mot de passe
      sans ancien mot de passe (l'utilisateur ne peut pas en fournir).
    """
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    has_password = bool(full and full.get("password_hash"))
    if has_password:
        if not body.current_password or not verify_password(
                body.current_password, full["password_hash"]):
            raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400,
                            detail="Mot de passe : 8 caractères minimum")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(body.new_password),
                  "must_change_password": False,
                  "password_changed_at": datetime.now(timezone.utc).isoformat()}})
    # Révoque toutes les autres sessions (garde la session courante)
    current = request.cookies.get("session_token")
    if not current:
        auth = request.headers.get("Authorization", "")
        current = auth[7:] if auth.startswith("Bearer ") else None
    q = {"user_id": user["user_id"]}
    if current:
        q["session_token"] = {"$ne": current}
    await db.user_sessions.delete_many(q)
    return {"ok": True}


class ProfileIn(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    two_fa_email: str | None = None
    current_password: str | None = None
    lang: str | None = None


@router.put("/profile")
async def update_profile(body: ProfileIn, user=Depends(current_user)) -> dict:
    """Met à jour nom / téléphone / email (changement d'email : mot de passe requis)."""
    updates: dict = {}
    if body.name is not None:
        name = body.name.strip()
        if not 2 <= len(name) <= 80:
            raise HTTPException(status_code=400, detail="Nom : entre 2 et 80 caractères")
        updates["name"] = name
    if body.phone is not None:
        updates["phone"] = body.phone.strip()[:20] or None
    if body.lang is not None:
        from engines.email_i18n import norm_lang
        updates["lang"] = norm_lang(body.lang)
    if body.two_fa_email is not None:
        val = body.two_fa_email.strip().lower()
        if val and ("@" not in val or "." not in val.split("@")[-1]):
            raise HTTPException(status_code=400, detail="E-mail de réception 2FA invalide")
        updates["two_fa_email"] = val or None
    if body.email is not None and body.email.lower() != user["email"]:
        full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if full.get("auth_provider") == "google":
            raise HTTPException(status_code=400,
                                detail="Compte Google — l'email ne peut pas être modifié")
        if not body.current_password or not verify_password(
                body.current_password, full.get("password_hash") or ""):
            raise HTTPException(status_code=401,
                                detail="Mot de passe actuel requis pour changer l'email")
        new_email = body.email.lower()
        if await db.users.find_one({"email": new_email}):
            raise HTTPException(status_code=400, detail="Un compte existe déjà avec cet email")
        updates["email"] = new_email
    if not updates:
        return {"user": _public(user)}
    updates["profile_updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"user": _public(fresh)}


class LanguageIn(BaseModel):
    lang: str


@router.put("/language")
async def set_language(body: LanguageIn, user=Depends(current_user)) -> dict:
    """Enregistre la langue préférée de l'utilisateur (sync auto depuis l'UI)."""
    from engines.email_i18n import norm_lang
    lang = norm_lang(body.lang)
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"lang": lang}})
    return {"lang": lang}


class PhotoIn(BaseModel):
    image_b64: str


@router.post("/profile-photo")
async def upload_profile_photo(body: PhotoIn, user=Depends(current_user)) -> dict:
    """Upload d'une photo de profil (redimensionnée 256px, stockée en data URL)."""
    import base64
    from io import BytesIO
    from PIL import Image
    try:
        data = base64.b64decode(body.image_b64.split(",")[-1])
    except Exception:
        raise HTTPException(status_code=400, detail="Image invalide")
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="Image trop lourde (5 Mo max)")
    try:
        img = Image.open(BytesIO(data)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Format d'image non reconnu")
    img.thumbnail((256, 256))
    out = BytesIO()
    img.save(out, format="JPEG", quality=85)
    data_url = "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": data_url}})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"user": _public(fresh)}


@router.delete("/profile-photo")
async def delete_profile_photo(user=Depends(current_user)) -> dict:
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"picture": None}})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"user": _public(fresh)}


# ---- KYC PRO : dépôt & validation des documents (K-bis + décennale) ----------

_KYC_MAGIC = {"application/pdf": b"%PDF-", "image/jpeg": b"\xff\xd8\xff",
              "image/png": b"\x89PNG\r\n\x1a\n"}
_KYC_EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}


async def _store_kyc_file(user_id: str, kind: str, up: UploadFile) -> dict:
    ct = (up.content_type or "").lower()
    if ct not in _KYC_MAGIC:
        raise HTTPException(415, "Type de document non supporté (PDF, JPEG ou PNG)")
    data = await up.read(10 * 1024 * 1024 + 1)
    if not data or len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, "Document vide ou trop volumineux (10 Mo max)")
    if not data.startswith(_KYC_MAGIC[ct]):
        raise HTTPException(415, "Le contenu ne correspond pas au type de fichier")
    from engines import storage
    path = f"private/kyc/{user_id}/{kind}/{uuid.uuid4().hex}.{_KYC_EXT[ct]}"
    storage.put_object(path, data, ct)
    return {"path": path, "content_type": ct, "size": len(data),
            "uploaded_at": datetime.now(timezone.utc).isoformat()}


@router.post("/kyc/submit")
async def submit_kyc_documents(
    kbis: UploadFile = File(...),
    decennale: UploadFile = File(...),
    siret: str | None = Form(None),
    user=Depends(current_user),
) -> dict:
    """Dépôt des documents pro (K-bis + attestation décennale). Compte actif,
    passe en kyc_status=pending pour validation admin."""
    docs = {
        "kbis": await _store_kyc_file(user["user_id"], "kbis", kbis),
        "decennale": await _store_kyc_file(user["user_id"], "decennale", decennale),
    }
    upd = {"kyc_documents": docs, "kyc_status": "pending",
           "updated_at": datetime.now(timezone.utc).isoformat()}
    if siret:
        import re
        s = re.sub(r"[ .\-]", "", siret)
        if _valid_siret(s):
            upd["siret"] = s
    if (await db.users.find_one({"user_id": user["user_id"]}, {"account_type": 1})).get("account_type") not in ("pro", "pro_business"):
        upd["account_type"] = "pro"
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return {"ok": True, "kyc_status": "pending"}


@router.get("/admin/kyc-pros")
async def list_kyc_pros(status: str | None = None, admin=Depends(admin_user)):
    """Liste des comptes pro et leur statut de validation KYC."""
    q = {"account_type": {"$in": ["pro", "pro_business"]}}
    if status:
        q["kyc_status"] = status
    rows = await db.users.find(q, {
        "_id": 0, "user_id": 1, "name": 1, "email": 1, "account_type": 1,
        "siret": 1, "kyc_status": 1, "kyc_documents": 1, "created_at": 1,
        "kyc_rejection_reason": 1,
    }).sort("created_at", -1).to_list(500)
    for r in rows:
        docs = r.get("kyc_documents") or {}
        r["has_kbis"] = bool(docs.get("kbis"))
        r["has_decennale"] = bool(docs.get("decennale"))
        r.pop("kyc_documents", None)
    return rows


class KycProReview(BaseModel):
    user_id: str
    approve: bool
    reason: str | None = None


@router.post("/admin/kyc-pros/review")
async def review_kyc_pro(body: KycProReview, admin=Depends(admin_user)) -> dict:
    upd = {"kyc_status": "verified" if body.approve else "rejected",
           "kyc_reviewed_by": admin["user_id"],
           "kyc_reviewed_at": datetime.now(timezone.utc).isoformat(),
           "kyc_rejection_reason": None if body.approve else (body.reason or "Documents non conformes")}
    r = await db.users.update_one({"user_id": body.user_id}, {"$set": upd})
    if not r.matched_count:
        raise HTTPException(404, "Compte introuvable")
    # Email de décision au pro (best-effort)
    try:
        u = await db.users.find_one({"user_id": body.user_id}, {"_id": 0, "email": 1, "name": 1})
        from engines import emailer
        first = (u.get("name") or "").split(" ")[0]
        if body.approve:
            body_html = (
                f"<p>Bonjour {first},</p>"
                "<p>Bonne nouvelle : votre compte professionnel ConstruPilot vient d'être "
                "<b>validé</b> ✅.</p>"
                "<p>Vos justificatifs (K-bis, assurance décennale) sont conformes. "
                "Vous bénéficiez désormais du badge <b>« Pro vérifié »</b> sur votre profil et vos devis.</p>"
                "<p>Bonne continuation avec ConstruPilot !</p>"
            )
            html = emailer.wrap_html("Votre compte Pro est validé ✅", body_html,
                                     cta_url="https://construpilot.fr/dashboard",
                                     cta_label="Accéder à mon espace")
            subject = "Votre compte Pro ConstruPilot est validé ✅"
        else:
            reason = upd["kyc_rejection_reason"]
            body_html = (
                f"<p>Bonjour {first},</p>"
                "<p>Après vérification, nous ne pouvons pas valider votre compte professionnel "
                "pour le moment.</p>"
                f"<p><b>Motif :</b> {reason}</p>"
                "<p>Vous pouvez renvoyer des documents conformes depuis votre espace. "
                "Notre équipe reste à votre disposition.</p>"
            )
            html = emailer.wrap_html("Validation de votre compte Pro", body_html,
                                     cta_url="https://construpilot.fr/compte",
                                     cta_label="Renvoyer mes documents")
            subject = "Votre compte Pro ConstruPilot — action requise"
        await emailer.send_email(u["email"], subject, html)
    except Exception:
        pass
    return {"ok": True, "kyc_status": upd["kyc_status"]}


@router.get("/admin/kyc-pros/{user_id}/doc/{kind}")
async def get_kyc_doc(user_id: str, kind: str, admin=Depends(admin_user)):
    if kind not in ("kbis", "decennale"):
        raise HTTPException(404, "Document inconnu")
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "kyc_documents": 1})
    meta = ((u or {}).get("kyc_documents") or {}).get(kind)
    if not meta:
        raise HTTPException(404, "Document introuvable")
    from engines import storage
    content, ct = storage.get_object(meta["path"])
    return Response(content, media_type=meta.get("content_type") or ct,
                    headers={"Content-Disposition": f'inline; filename="{kind}"'})


# ---- Mot de passe oublié -----------------------------------------------------

class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    token: str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(body: ForgotIn, request: Request) -> dict:
    """Envoie un lien de réinitialisation (réponse identique que le compte existe
    ou non — anti-énumération). Max 3 demandes/heure par email."""
    import os
    from engines.email_i18n import T
    email = body.email.lower()
    user = await db.users.find_one({"email": email},
                                   {"_id": 0, "user_id": 1, "password_hash": 1, "name": 1, "lang": 1})
    if not user:
        return {"ok": True}
    has_password = bool(user.get("password_hash"))
    lang = user.get("lang")
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = await db.password_reset_tokens.count_documents(
        {"email": email, "created_at": {"$gt": hour_ago}})
    if recent >= 3:
        return {"ok": True}
    token = secrets.token_urlsafe(32)
    await db.password_reset_tokens.insert_one({
        "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        "email": email, "user_id": user["user_id"], "used": False,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    })
    origin = request.headers.get("origin") or os.environ.get("FRONTEND_URL", "")
    link = f"{origin}/reinitialiser?token={token}"
    intro = T(lang, "reset.intro_has") if has_password else T(lang, "reset.intro_set")
    cta = T(lang, "reset.cta_has") if has_password else T(lang, "reset.cta_set")
    html = (
        f"<p>{T(lang, 'reset.greeting', name=user.get('name') or '')}</p>"
        f"<p>{intro}</p>"
        f"<p><a href='{link}' style='background:#16a34a;color:#fff;padding:10px 18px;"
        f"border-radius:4px;text-decoration:none'>{cta}</a></p>"
        f"<p style='font-size:12px;color:#666'>{T(lang, 'reset.note')}</p>"
    )
    subject = (T(lang, "reset.subject_has") if has_password
               else T(lang, "reset.subject_set"))

    async def _send():
        from engines.emailer import send_email
        try:
            await send_email(email, subject, html)
        except Exception:
            pass
    asyncio.create_task(_send())
    return {"ok": True}


@router.post("/reset-password")
async def reset_password(body: ResetIn) -> dict:
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="Nouveau mot de passe : 8 caractères minimum")
    th = hashlib.sha256(body.token.encode()).hexdigest()
    rec = await db.password_reset_tokens.find_one({"token_hash": th, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Lien invalide ou déjà utilisé")
    exp = rec["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Lien expiré — refaites une demande")
    await db.users.update_one(
        {"user_id": rec["user_id"]},
        {"$set": {"password_hash": hash_password(body.new_password),
                  "must_change_password": False,
                  "password_changed_at": datetime.now(timezone.utc).isoformat()}})
    await db.password_reset_tokens.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    await db.user_sessions.delete_many({"user_id": rec["user_id"]})
    return {"ok": True}


# ---- Alerte connexion admin depuis un nouvel appareil ------------------------

async def _register_device(user: dict, request: Request) -> None:
    """Trace l'appareil (IP + user-agent) pour l'historique des connexions.
    Nouvel appareil sur un compte admin → email d'alerte (fire-and-forget)."""
    ip = _client_ip(request)
    ua = (request.headers.get("user-agent") or "inconnu")[:200]
    device_key = hashlib.sha256(f"{user['user_id']}:{ip}:{ua}".encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    if await db.known_devices.find_one({"device_key": device_key}, {"_id": 1}):
        await db.known_devices.update_one({"device_key": device_key},
                                          {"$set": {"last_seen": now}})
        return
    await db.known_devices.insert_one({
        "device_key": device_key, "user_id": user["user_id"], "ip": ip,
        "user_agent": ua, "created_at": now, "last_seen": now})
    if user.get("role") != "admin":
        return
    html = (
        f"<p>Bonjour {user.get('name') or ''},</p>"
        f"<p>Une connexion à votre compte <b>administrateur ConstruPilot</b> vient d'avoir lieu "
        f"depuis un nouvel appareil :</p>"
        f"<ul><li><b>Adresse IP</b> : {ip}</li>"
        f"<li><b>Appareil / navigateur</b> : {ua}</li>"
        f"<li><b>Date</b> : {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}</li></ul>"
        f"<p style='font-size:12px;color:#666'>Si c'était bien vous, aucune action n'est requise. "
        f"Sinon, changez immédiatement votre mot de passe depuis la page Mon compte.</p>"
    )

    async def _send():
        from engines.emailer import send_email
        try:
            await send_email(user["email"], "Nouvelle connexion admin — ConstruPilot", html)
        except Exception:
            pass
    asyncio.create_task(_send())


# ---- 2FA email (admin) -------------------------------------------------------

def _mask_email(email: str) -> str:
    try:
        local, domain = email.split("@", 1)
    except ValueError:
        return email
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}{'*' * max(1, len(local) - len(shown))}@{domain}"


async def _send_2fa_email(user: dict, code: str) -> None:
    from engines.email_i18n import T
    lang = user.get("lang")
    html = (
        f"<p>{T(lang, 'twofa.greeting', name=user.get('name') or '')}</p>"
        f"<p>{T(lang, 'twofa.line')}</p>"
        f"<p style='font-size:32px;font-weight:bold;letter-spacing:8px'>{code}</p>"
        f"<p style='font-size:12px;color:#666'>{T(lang, 'twofa.note')}</p>")

    async def _send():
        from engines.emailer import send_email
        try:
            recipient = user.get("two_fa_email") or user["email"]
            await send_email(recipient, T(lang, "twofa.subject", code=code), html)
        except Exception:
            pass
    asyncio.create_task(_send())


async def _start_2fa(user: dict) -> dict:
    code = f"{secrets.randbelow(900000) + 100000}"
    pending = secrets.token_urlsafe(32)
    await db.two_fa_codes.insert_one({
        "pending_token": pending, "user_id": user["user_id"],
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "attempts": 0, "resends": 0,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10)})
    await _send_2fa_email(user, code)
    recipient = user.get("two_fa_email") or user["email"]
    masked = _mask_email(recipient)
    return {"two_fa_required": True, "pending_token": pending,
            "message": f"Code de vérification envoyé à {masked}"}


class TwoFaVerifyIn(BaseModel):
    pending_token: str
    code: str


@router.post("/verify-2fa")
async def verify_2fa(body: TwoFaVerifyIn, request: Request, response: Response) -> dict:
    rec = await db.two_fa_codes.find_one({"pending_token": body.pending_token})
    if not rec:
        raise HTTPException(status_code=401,
                            detail="Session de vérification expirée — reconnectez-vous")
    exp = rec["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        await db.two_fa_codes.delete_one({"_id": rec["_id"]})
        raise HTTPException(status_code=401, detail="Code expiré — reconnectez-vous")
    if rec.get("attempts", 0) >= 5:
        await db.two_fa_codes.delete_one({"_id": rec["_id"]})
        raise HTTPException(status_code=429, detail="Trop d'essais — reconnectez-vous")
    if hashlib.sha256(body.code.strip().encode()).hexdigest() != rec["code_hash"]:
        await db.two_fa_codes.update_one({"_id": rec["_id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=401, detail="Code incorrect")
    await db.two_fa_codes.delete_one({"_id": rec["_id"]})
    user = await db.users.find_one({"user_id": rec["user_id"]}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Compte introuvable")
    await _register_device(user, request)
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user),
            "token": make_jwt(user["user_id"], user.get("token_version") or 0),
            "session_token": token}


class TwoFaResendIn(BaseModel):
    pending_token: str


@router.post("/resend-2fa")
async def resend_2fa(body: TwoFaResendIn) -> dict:
    rec = await db.two_fa_codes.find_one({"pending_token": body.pending_token})
    if not rec:
        raise HTTPException(status_code=401,
                            detail="Session de vérification expirée — reconnectez-vous")
    if rec.get("resends", 0) >= 3:
        raise HTTPException(status_code=429, detail="Limite de renvois atteinte — reconnectez-vous")
    code = f"{secrets.randbelow(900000) + 100000}"
    await db.two_fa_codes.update_one(
        {"_id": rec["_id"]},
        {"$set": {"code_hash": hashlib.sha256(code.encode()).hexdigest(),
                  "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
                  "attempts": 0},
         "$inc": {"resends": 1}})
    user = await db.users.find_one({"user_id": rec["user_id"]}, {"_id": 0})
    await _send_2fa_email(user, code)
    return {"ok": True}


class TwoFaToggleIn(BaseModel):
    enabled: bool
    current_password: str | None = None


@router.put("/2fa")
async def toggle_2fa(body: TwoFaToggleIn, user=Depends(current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Réservé aux administrateurs")
    if not body.enabled:
        full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
        if not body.current_password or not verify_password(
                body.current_password, full.get("password_hash") or ""):
            raise HTTPException(status_code=401,
                                detail="Mot de passe actuel requis pour désactiver la double authentification")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"two_fa_enabled": body.enabled}})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"user": _public(fresh)}


# ---- Appareils connectés -------------------------------------------------------

@router.get("/devices")
async def list_devices(request: Request, user=Depends(current_user)) -> dict:
    ip = _client_ip(request)
    ua = (request.headers.get("user-agent") or "inconnu")[:200]
    current_key = hashlib.sha256(f"{user['user_id']}:{ip}:{ua}".encode()).hexdigest()
    docs = await (db.known_devices.find({"user_id": user["user_id"]}, {"_id": 0})
                  .sort("last_seen", -1).to_list(50))
    return {"devices": [{**d, "current": d["device_key"] == current_key} for d in docs]}


@router.delete("/devices/{device_key}")
async def delete_device(device_key: str, user=Depends(current_user)) -> dict:
    await db.known_devices.delete_one({"device_key": device_key, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/logout-others")
async def logout_other_devices(response: Response, user=Depends(current_user)) -> dict:
    """Invalide tous les JWT existants (token_version++) et toutes les sessions,
    puis ré-émet un jeton frais pour l'appareil courant."""
    new_version = int(user.get("token_version") or 0) + 1
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"token_version": new_version}})
    await db.user_sessions.delete_many({"user_id": user["user_id"]})
    token = await _set_session(response, user["user_id"])
    return {"ok": True, "token": make_jwt(user["user_id"], new_version),
            "session_token": token}


@router.post("/session")
async def google_session(request: Request, response: Response) -> dict:
    session_id = request.headers.get("X-Session-ID") or (await request.json()).get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id manquant")
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Session Google invalide")
    data = r.json()
    email = (data.get("email") or "").lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user:
        user = {
            "user_id": new_user_id(), "email": email, "name": data.get("name") or email,
            "picture": data.get("picture"), "role": "user", "plan": "free",
            "auth_provider": "google", "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.users.insert_one(user)
    else:
        await db.users.update_one({"user_id": user["user_id"]},
                                  {"$set": {"picture": data.get("picture") or user.get("picture"),
                                            "name": data.get("name") or user.get("name")}})
    token = await _set_session(response, user["user_id"], data.get("session_token"))
    await _register_device(user, request)
    return {"user": _public(user), "session_token": token}


@router.get("/me")
async def me(user=Depends(current_user)):
    return _public(user)


@router.post("/logout")
async def logout(request: Request, response: Response, user=Depends(optional_user)) -> dict:
    token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_many({"session_token": token})
    response.delete_cookie("session_token", path="/", secure=True, samesite="lax")
    return {"ok": True}
