"""Endpoint public : logo d'entreprise servi en image (pour les e-mails).

Gmail et la plupart des clients mail bloquent les images en data:base64.
On sert donc le logo via une URL HTTPS publique référencée dans les e-mails.
"""
import base64

from fastapi import APIRouter, HTTPException, Response

from core.db import db

router = APIRouter(tags=["branding"])


async def _resolve_logo_b64(user_id: str) -> str | None:
    u = await db.users.find_one({"user_id": user_id},
                                {"_id": 0, "brand_logo_b64": 1, "organization_id": 1})
    if not u:
        return None
    b64 = u.get("brand_logo_b64")
    if not b64 and u.get("organization_id"):
        org = await db.organizations.find_one(
            {"org_id": u["organization_id"]}, {"_id": 0, "brand_logo_b64": 1})
        b64 = (org or {}).get("brand_logo_b64")
    return b64


@router.get("/branding/{user_id}/logo")
async def company_logo(user_id: str):
    b64 = await _resolve_logo_b64(user_id)
    if not b64:
        raise HTTPException(404, "Aucun logo")
    ctype, data = "image/png", b64
    if data.startswith("data:"):
        head, _, payload = data.partition(",")
        if ":" in head and ";" in head:
            ctype = head.split(":", 1)[1].split(";", 1)[0] or ctype
        data = payload
    try:
        raw = base64.b64decode(data)
    except Exception:
        raise HTTPException(404, "Logo invalide")
    return Response(content=raw, media_type=ctype,
                    headers={"Cache-Control": "public, max-age=3600"})
