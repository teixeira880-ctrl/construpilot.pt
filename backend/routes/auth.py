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
    response.set_cookie("session_token", token, httponly=True, secure=True,
                        samesite="none", path="/", max_age=7 * 24 * 3600)
    return token


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
async def login(body: LoginIn, response: Response) -> dict:
    user = await db.users.find_one({"email": body.email.lower()}, {"_id": 0})
    if not user or not user.get("password_hash") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    token = await _set_session(response, user["user_id"])
    return {"user": _public(user), "token": make_jwt(user["user_id"]), "session_token": token}


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
    response.delete_cookie("session_token", path="/", secure=True, samesite="none")
    return {"ok": True}
