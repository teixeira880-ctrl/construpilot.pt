import os
import uuid
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException, Request

from core.db import db

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret')
JWT_ALGO = 'HS256'
TOKEN_DAYS = 7


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False


def make_jwt(user_id: str) -> str:
    payload = {
        'sub': user_id,
        'exp': datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)


def new_user_id() -> str:
    return f"user_{uuid.uuid4().hex[:12]}"


async def _user_from_jwt(token: str):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except Exception:
        return None
    return await db.users.find_one({"user_id": payload.get('sub')}, {"_id": 0})


async def _user_from_session(token: str):
    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        return None
    expires_at = session.get('expires_at')
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at and expires_at < datetime.now(timezone.utc):
        return None
    return await db.users.find_one({"user_id": session['user_id']}, {"_id": 0})


async def optional_user(request: Request):
    token = request.cookies.get('session_token')
    if not token:
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
    if not token:
        return None
    user = await _user_from_session(token)
    if user:
        return user
    return await _user_from_jwt(token)


async def current_user(user=Depends(optional_user)):
    if not user:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return user


async def admin_user(user=Depends(current_user)):
    if user.get('role') != 'admin':
        raise HTTPException(status_code=403, detail="Accès administrateur requis")
    return user
