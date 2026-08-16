import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, optional_user

router = APIRouter(prefix="/leads", tags=["leads"])


def _welcome_html(name: str) -> str:
    hello = f"Bonjour {name}," if name else "Bonjour,"
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;background:#f5f5f4;padding:24px;">
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e7e5e4;">
<tr><td style="background:#3f7d54;padding:24px 32px;color:#fff;font-size:20px;font-weight:800;">ConstruPilot</td></tr>
<tr><td style="padding:32px;color:#1a1d20;font-size:15px;line-height:1.6;">
<p>{hello}</p>
<p>Merci de votre intérêt pour <strong>ConstruPilot</strong> ! Votre estimation de travaux est à portée de clic.</p>
<p>Décrivez votre projet et obtenez en 30 secondes une estimation détaillée, poste par poste — gratuitement et sans engagement.</p>
<p style="text-align:center;margin:32px 0;">
<a href="https://construpilot.fr/smart-project" style="background:#3f7d54;color:#fff;text-decoration:none;padding:14px 28px;border-radius:8px;font-weight:700;display:inline-block;">Reprendre mon estimation</a>
</p>
<p style="color:#78716c;font-size:13px;">Une question ? Répondez simplement à cet e-mail.</p>
<p style="color:#78716c;font-size:13px;">— L'équipe ConstruPilot</p>
</td></tr>
<tr><td style="background:#fafaf9;padding:16px 32px;color:#a8a29e;font-size:11px;">ConstruPilot — Estimez. Comparez. Construisez. · Brevet FR261104</td></tr>
</table></td></tr></table></body></html>"""


async def _send_welcome(email: str, name: str) -> None:
    try:
        from engines.emailer import send_email
        await send_email(email, "Bienvenue sur ConstruPilot — votre estimation vous attend",
                         _welcome_html(name))
    except Exception:
        pass


class LeadIn(BaseModel):
    name: str = ""
    email: EmailStr
    phone: str = ""
    address: str = ""
    availability: str = ""
    budget: float | None = None
    description: str = ""
    project_id: str | None = None
    source: str = ""
    photos: list[str] = []
    documents: list[dict] = []


@router.post("")
async def create_lead(body: LeadIn, user=Depends(optional_user)):
    project = None
    if body.project_id:
        project = await db.projects.find_one({"project_id": body.project_id}, {"_id": 0})
    doc = {
        "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
        "user_id": user["user_id"] if user else None,
        **body.model_dump(),
        "project_snapshot": {
            "name": project.get("name"), "surface": project.get("surface"),
            "city": project.get("city"), "estimation": project.get("estimation", {}).get("total_avg"),
            "lots": [l["name"] for l in project.get("estimation", {}).get("lots", [])],
            "materials": project.get("materials", []),
        } if project else None,
        "status": "nouveau", "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.leads.insert_one(doc)
    doc.pop("_id", None)
    # E-mail de bienvenue automatique pour les leads venant de la page d'accueil
    if body.email and (body.source or "").startswith("landing"):
        asyncio.create_task(_send_welcome(body.email, body.name))
    return doc


@router.get("/mine")
async def my_leads(user=Depends(current_user)):
    return await db.leads.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)
