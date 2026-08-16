import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, optional_user

router = APIRouter(prefix="/leads", tags=["leads"])


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
    return doc


@router.get("/mine")
async def my_leads(user=Depends(current_user)):
    return await db.leads.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)
