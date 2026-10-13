"""Modèles de devis réutilisables (structure + lignes, sans photos)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/quote-templates", tags=["quote-templates"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemplateIn(BaseModel):
    name: str
    doc_type: str = "quote"
    title: str = ""
    notes: str = ""
    deposit_pct: float = 0
    validity_days: int = 0
    lines: list[dict] = []


def _strip_photos(lines: list[dict]) -> list[dict]:
    out = []
    for l in lines or []:
        l = dict(l)
        l["photos"] = []
        if isinstance(l.get("components"), list):
            l["components"] = [{**dict(c), "photos": []} for c in l["components"]]
        out.append(l)
    return out


@router.post("")
async def create_template(body: TemplateIn, user=Depends(current_user)) -> dict:
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nome do modelo obrigatório")
    rec = {
        "template_id": f"tpl_{uuid.uuid4().hex[:12]}",
        "user_id": user["user_id"],
        "name": name,
        "doc_type": body.doc_type or "quote",
        "title": body.title or "",
        "notes": body.notes or "",
        "deposit_pct": float(body.deposit_pct or 0),
        "validity_days": int(body.validity_days or 0),
        "lines": _strip_photos(body.lines),
        "created_at": _now(),
    }
    await db.devis_templates.insert_one(dict(rec))
    return {k: v for k, v in rec.items() if k != "_id"}


@router.get("")
async def list_templates(user=Depends(current_user)) -> list[dict]:
    cur = db.devis_templates.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    return await cur.to_list(length=200)


@router.get("/{template_id}")
async def get_template(template_id: str, user=Depends(current_user)) -> dict:
    rec = await db.devis_templates.find_one({"template_id": template_id, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    return rec


@router.delete("/{template_id}")
async def delete_template(template_id: str, user=Depends(current_user)) -> dict:
    res = await db.devis_templates.delete_one({"template_id": template_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Modelo não encontrado")
    return {"ok": True}
