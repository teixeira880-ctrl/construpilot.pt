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
    leads: int = 0                    # leads saisis manuellement
    revenue: float = 0                # CA attribué (€)
    status: str = "active"            # active | paused | ended
    lead_source: str = ""             # tag CRM (source des leads) pour attribution auto
    start_date: str | None = None
    end_date: str | None = None


async def _real_leads_count(lead_source: str) -> int:
    """Nombre de leads CRM dont le champ `source` correspond au tag de la campagne."""
    if not lead_source:
        return 0
    return await db.leads.count_documents({"source": lead_source})


def _enrich(row: dict, real: int) -> dict:
    """Ajoute leads réels (CRM) + CPL réel à une campagne."""
    row["real_leads"] = real
    spend = row.get("spend", 0)
    row["real_cpl"] = round(spend / real, 2) if real else None
    return row


def _period(row: dict) -> str:
    return (row.get("start_date") or row.get("created_at") or "")[:7]


def _match(row: dict, platform: str, month: str) -> bool:
    if platform and row.get("platform") != platform:
        return False
    if month and _period(row) != month:
        return False
    return True


@router.get("/campaigns")
async def list_campaigns(platform: str = "", month: str = "", user=Depends(current_user)):
    rows = await db.ad_campaigns.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(500)
    rows = [r for r in rows if _match(r, platform, month)]
    for r in rows:
        _enrich(r, await _real_leads_count(r.get("lead_source", "")))
    return rows


@router.get("/filters")
async def ads_filters(user=Depends(current_user)):
    """Options de filtre disponibles (plateformes + mois) pour le dashboard pub."""
    rows = await db.ad_campaigns.find({"user_id": user["user_id"]},
                                      {"_id": 0, "platform": 1, "start_date": 1,
                                       "created_at": 1}).to_list(500)
    platforms = sorted({r.get("platform") for r in rows if r.get("platform")})
    months = sorted({_period(r) for r in rows if _period(r)}, reverse=True)
    return {"platforms": platforms, "months": months}


@router.get("/lead-sources")
async def lead_sources(user=Depends(current_user)):
    """Sources de leads disponibles dans le CRM (pour l'attribution des campagnes)."""
    sources = await db.leads.distinct("source")
    return [s for s in sources if s]


@router.get("/channels")
async def channels(user=Depends(current_user)):
    """Répartition des leads/inscrits par canal d'acquisition (UTM)."""
    pipe = [{"$group": {"_id": {"$ifNull": ["$utm_source", ""]}, "leads": {"$sum": 1}}},
            {"$sort": {"leads": -1}}]
    rows = await db.leads.aggregate(pipe).to_list(100)
    out = []
    for r in rows:
        src = (r["_id"] or "direct").lower()
        out.append({"channel": src, "leads": r["leads"]})
    return out


@router.post("/campaigns")
async def create_campaign(body: CampaignIn, user=Depends(current_user)):
    doc = {"campaign_id": f"ad_{uuid.uuid4().hex[:12]}", "user_id": user["user_id"],
           **body.model_dump(), "created_at": _now()}
    await db.ad_campaigns.insert_one(doc)
    doc.pop("_id", None)
    return _enrich(doc, await _real_leads_count(body.lead_source))


@router.put("/campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, body: CampaignIn, user=Depends(current_user)):
    r = await db.ad_campaigns.find_one({"campaign_id": campaign_id, "user_id": user["user_id"]},
                                       {"_id": 0, "campaign_id": 1})
    if not r:
        raise HTTPException(404, "Campagne introuvable")
    await db.ad_campaigns.update_one({"campaign_id": campaign_id}, {"$set": body.model_dump()})
    doc = await db.ad_campaigns.find_one({"campaign_id": campaign_id}, {"_id": 0})
    return _enrich(doc, await _real_leads_count(doc.get("lead_source", "")))


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, user=Depends(current_user)):
    await db.ad_campaigns.delete_one({"campaign_id": campaign_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.get("/summary")
async def ads_summary(platform: str = "", month: str = "", user=Depends(current_user)):
    rows = await db.ad_campaigns.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    rows = [r for r in rows if _match(r, platform, month)]
    spend = sum(r.get("spend", 0) for r in rows)
    budget = sum(r.get("budget", 0) for r in rows)
    leads = sum(r.get("leads", 0) for r in rows)
    revenue = sum(r.get("revenue", 0) for r in rows)
    real_leads = 0
    by_platform: dict = {}
    for r in rows:
        rl = await _real_leads_count(r.get("lead_source", ""))
        real_leads += rl
        p = by_platform.setdefault(r.get("platform", "other"),
                                   {"platform": r.get("platform", "other"), "spend": 0,
                                    "leads": 0, "real_leads": 0, "revenue": 0})
        p["spend"] += r.get("spend", 0)
        p["leads"] += r.get("leads", 0)
        p["real_leads"] += rl
        p["revenue"] += r.get("revenue", 0)
    return {
        "campaigns": len(rows),
        "total_budget": round(budget, 2),
        "total_spend": round(spend, 2),
        "total_leads": leads,
        "total_real_leads": real_leads,
        "total_revenue": round(revenue, 2),
        "cpl": round(spend / leads, 2) if leads else None,
        "real_cpl": round(spend / real_leads, 2) if real_leads else None,
        "roas": round(revenue / spend, 2) if spend else None,
        "by_platform": list(by_platform.values()),
    }
