"""API commerciale ConstruPilot.

- Génération de clés API par plan (Starter/Business/Scale)
- Rate limiting simple sur DB (fenêtre glissante mensuelle par clé)
- Middleware `require_api_key` pour les endpoints /api/v1/public/*
"""
import secrets
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, Header

from core.db import db

logger = logging.getLogger(__name__)


def _now():
    return datetime.now(timezone.utc)


def _month_key(dt=None):
    dt = dt or _now()
    return dt.strftime("%Y-%m")


async def issue_api_key(user_id: str, plan_id: str, name: str = "Default") -> dict:
    plan = await db.plans.find_one({"plan_id": plan_id}, {"_id": 0})
    if not plan or plan.get("audience") != "api":
        raise ValueError("Plano API não encontrado")
    key = "ckp_live_" + secrets.token_urlsafe(24)
    prefix = key[:12]
    doc = {
        "key": key,
        "prefix": prefix,
        "user_id": user_id,
        "plan_id": plan_id,
        "name": name,
        "monthly_quota": plan.get("quotas", {}).get("api_calls_monthly", 1000),
        "monthly_usage": {},
        "active": True,
        "created_at": _now().isoformat(),
        "last_used_at": None,
    }
    await db.api_keys.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def rotate_api_key(key_id: str, user_id: str) -> dict:
    existing = await db.api_keys.find_one({"prefix": key_id, "user_id": user_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Chave não encontrada")
    new_key = "ckp_live_" + secrets.token_urlsafe(24)
    new_prefix = new_key[:12]
    await db.api_keys.update_one(
        {"prefix": key_id, "user_id": user_id},
        {"$set": {"key": new_key, "prefix": new_prefix, "rotated_at": _now().isoformat()}})
    existing["key"] = new_key
    existing["prefix"] = new_prefix
    return existing


async def revoke_api_key(prefix: str, user_id: str) -> None:
    await db.api_keys.update_one(
        {"prefix": prefix, "user_id": user_id},
        {"$set": {"active": False, "revoked_at": _now().isoformat()}})


async def list_keys_for(user_id: str) -> list:
    keys = await db.api_keys.find({"user_id": user_id}, {"_id": 0}).to_list(50)
    # Masquer la clé complète — on garde seulement le prefix
    for k in keys:
        k["key_masked"] = k["prefix"] + "…"
        k.pop("key", None)
    return keys


async def _check_and_record(api_key: str) -> dict:
    doc = await db.api_keys.find_one({"key": api_key, "active": True}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=401, detail="Chave API inválida")
    month = _month_key()
    used = (doc.get("monthly_usage") or {}).get(month, 0)
    quota = doc.get("monthly_quota", 1000)
    if quota > 0 and used >= quota:
        raise HTTPException(status_code=429, detail=f'Quota mensal atingida ({quota})')
    await db.api_keys.update_one(
        {"key": api_key},
        {"$set": {"last_used_at": _now().isoformat()},
         "$inc": {f"monthly_usage.{month}": 1}})
    await db.api_usage.insert_one({
        "key_prefix": doc["prefix"], "user_id": doc["user_id"],
        "plan_id": doc["plan_id"], "at": _now().isoformat(), "month": month,
    })
    return doc


async def require_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Cabeçalho X-API-Key obrigatório")
    return await _check_and_record(x_api_key)
