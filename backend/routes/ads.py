"""Module Publicité / Marketing — suivi des campagnes publicitaires (dépenses, leads, CPL, ROI)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/ads", tags=["ads"])


def _now():
    return datetime.now(timezone.utc).isoformat()


class CampaignIn(BaseModel):
    name: str
    platform: str = "google"          # google | meta | instagram | linkedin | other
    budget: float = 0                 # budget alloué (€)
    spend: float = 0                  # dépense réelle (€)
    leads: int = 0                    # leads générés
    revenue: float = 0                # CA attribué (€)
    status: str = "active"            # active | paused | ended
    start_date: str | None = None
    end_date: str | None = None


@router.get("/campaigns")
async def list_campaigns(user=Depends(current_user)):
    return await db.ad_campaigns.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)


@router.post("/campaigns")
async def create_campaign(body: CampaignIn, user=Depends(current_user)):
    doc = {"campaign_id": f"ad_{uuid.uuid4().hex[:12]}", "user_id": user["user_id"],
           **body.model_dump(), "created_at": _now()}
    await db.ad_campaigns.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: CampaignIn, user=Depends(current_user)):
    r = await db.ad_campaigns.find_one({"campaign_id": campaign_id, "user_id": user["user_id"]},
                                       {"_id": 0, "campaign_id": 1})
    if not r:
        raise HTTPException(404, "Campagne introuvable")
    await db.ad_campaigns.update_one({"campaign_id": campaign_id}, {"$set": body.model_dump()})
    return await db.ad_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, user=Depends(current_user)):
    await db.ad_campaigns.delete_one({"campaign_id": campaign_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.get("/summary")
async def ads_summary(user=Depends(current_user)):
    rows = await db.ad_campaigns.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    spend = sum(r.get("spend", 0) for r in rows)
    budget = sum(r.get("budget", 0) for r in rows)
    leads = sum(r.get("leads", 0) for r in rows)
    revenue = sum(r.get("revenue", 0) for r in rows)
    by_platform: dict = {}
    for r in rows:
        p = by_platform.setdefault(r.get("platform", "other"),
                                   {"platform": r.get("platform", "other"), "spend": 0, "leads": 0, "revenue": 0})
        p["spend"] += r.get("spend", 0)
        p["leads"] += r.get("leads", 0)
        p["revenue"] += r.get("revenue", 0)
    return {
        "campaigns": len(rows),
        "total_budget": round(budget, 2),
        "total_spend": round(spend, 2),
        "total_leads": leads,
        "total_revenue": round(revenue, 2),
        "cpl": round(spend / leads, 2) if leads else None,
        "roas": round(revenue / spend, 2) if spend else None,
        "by_platform": list(by_platform.values()),
    }
