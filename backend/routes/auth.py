import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Response, Request, Depends
from pydantic import BaseModel, EmailStr
import httpx

from core.db import db
from core.security import (hash_password, verify_password, make_jwt, new_user_id,
                          current_user, optional_user)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    referred_by_code: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def _public(u: dict) -> dict:
    return {k: u.get(k) for k in ("user_id", "email", "name", "picture", "role", "plan", "created_at")}


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
    user = {
        "user_id": new_user_id(), "email": email, "name": body.name,
        "password_hash": hash_password(body.password), "picture": None,
        "role": "user", "plan": "free", "auth_provider": "password",
        "referred_by": (body.referred_by_code or "").upper().strip() or None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    # Credit the referrer (silent no-op if code invalid) — routed via referrals module
    if body.referred_by_code:
        from routes.referrals import credit_referrer
        try:
            await credit_referrer(body.referred_by_code)
        except Exception:
            pass  # never break signup on a bonus-credit error
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user), "token": make_jwt(user["user_id"]), "session_token": token}


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
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user), "token": make_jwt(user["user_id"]), "session_token": token}


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, request: Request,
                          user=Depends(current_user)) -> dict:
    """Change le mot de passe (vérifie l'actuel) et révoque les autres sessions."""
    full = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not full or not full.get("password_hash"):
        raise HTTPException(status_code=400,
                            detail="Compte Google — pas de mot de passe à changer")
    if not verify_password(body.current_password, full["password_hash"]):
        raise HTTPException(status_code=401, detail="Mot de passe actuel incorrect")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400,
                            detail="Nouveau mot de passe : 8 caractères minimum")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"password_hash": hash_password(body.new_password),
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
