"""Partage public d'estimation (WhatsApp/email) via lien signé.

- `POST /api/projects/{id}/share` (auth) : génère (ou récupère) un token public,
  persiste-le sur le projet, renvoie l'URL frontend `/e/{token}`.
- `GET  /api/public/estimation/{token}` : vue lecture seule (pas d'auth) —
  renvoie uniquement les champs sûrs (aucun email/user_id/coût interne).
"""
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends

from core.db import db
from core.security import current_user

router = APIRouter(tags=["share"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _public_url(token: str) -> str:
    base = os.environ.get("PUBLIC_APP_URL") or "https://cmrenov-ai.preview.emergentagent.com"
    return f"{base.rstrip('/')}/e/{token}"


@router.post("/projects/{project_id}/share")
async def create_share_link(project_id: str, user=Depends(current_user)):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    token = p.get("share_token")
    if not token:
        token = secrets.token_urlsafe(16)
        await db.projects.update_one(
            {"project_id": project_id},
            {"$set": {"share_token": token, "share_created_at": _now()}},
        )
    return {"token": token, "url": _public_url(token), "project_id": project_id}


@router.delete("/projects/{project_id}/share")
async def revoke_share_link(project_id: str, user=Depends(current_user)):
    res = await db.projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$unset": {"share_token": "", "share_created_at": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Projet introuvable")
    return {"ok": True}


@router.get("/public/estimation/{token}")
async def public_estimation(token: str):
    p = await db.projects.find_one({"share_token": token},
                                   {"_id": 0, "user_id": 0, "share_token": 0})
    if not p:
        raise HTTPException(404, "Lien invalide ou expiré")
    est = p.get("estimation") or {}
    # Champs sûrs pour un lien public — pas de secrets internes
    return {
        "project": {
            "name": p.get("name"),
            "city": p.get("city"),
            "surface": p.get("surface"),
            "region": p.get("region"),
            "description": (p.get("description") or "")[:500],
            "created_at": p.get("created_at"),
        },
        "estimation": {
            "project_type_name": est.get("project_type_name"),
            "finish_level_name": est.get("finish_level_name"),
            "surface": est.get("surface"),
            "region": est.get("region"),
            "coef_region": est.get("coef_region"),
            "total_min": est.get("total_min"),
            "total_avg": est.get("total_avg"),
            "total_max": est.get("total_max"),
            "labor_hours": est.get("labor_hours"),
            "lots": est.get("lots") or [],
            "unit_price_avg": est.get("unit_price_avg"),
        },
        "shared_at": p.get("share_created_at"),
    }
