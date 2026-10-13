"""Checklist de prise en main branchée sur les vraies données du compte (pas sur les devis scannés)."""
from fastapi import APIRouter, Depends

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status")
async def onboarding_status(user=Depends(current_user)) -> dict:
    uid = user["user_id"]
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "public_published": 1}) or {}
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(uid) or {}
    return {
        "client": await db.clients.count_documents({"user_id": uid}) > 0,
        "chantier": await db.chantiers.count_documents({"user_id": uid}) > 0,
        "plan": await db.plans_takeoff.count_documents({"user_id": uid, "trashed_at": None}) > 0,
        "quote": await db.pro_documents.count_documents({"user_id": uid, "doc_type": "quote"}) > 0,
        "project": await db.projects.count_documents({"user_id": uid}) > 0,
        "page_published": bool(u.get("public_published")),
        "identity": bool(branding.get("company_name")),
    }
