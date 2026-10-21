"""Endpoints marketing publics (comparatif concurrentiel + capture de leads)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from engines.comparatif_pdf import build, FULLNAME

public_router = APIRouter(prefix="/public/marketing", tags=["marketing"])


@public_router.get("/comparatif.pdf")
async def comparatif_pdf(vs: str = Query("")):
    """PDF comparatif ConstruPilot, éventuellement ciblé sur un concurrent (vs=obat…)."""
    slug = (vs or "").lower().strip()
    pdf = build(focus=slug if slug in FULLNAME else None)
    name = f"comparatif-construpilot-vs-{slug}.pdf" if slug in FULLNAME else "comparatif-construpilot.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


class LeadIn(BaseModel):
    email: EmailStr
    source: str = Field("comparatif", max_length=60)
    competitor: str = Field("", max_length=60)


@public_router.post("/lead")
async def capture_lead(body: LeadIn) -> dict:
    """Enregistre un lead (email) avant téléchargement du comparatif."""
    await db.marketing_leads.insert_one({
        "email": str(body.email).lower().strip(),
        "source": body.source, "competitor": body.competitor,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"ok": True}

