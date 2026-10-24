"""Endpoints publics ROI : PDF « Économies & ROI » + capture de lead du calculateur."""
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from starlette.concurrency import run_in_threadpool

from core.db import db
from core.rate_limit import limiter
from engines.roi_pdf import build_roi_pdf

router = APIRouter(tags=["roi"])


@router.get("/roi/pdf")
async def roi_pdf(ca: float = 500000, materials_pct: float = 40,
                  salaire_brut: float = 2900, charges_pct: float = 42,
                  frais_generes: float = 450, loaded_salary: float | None = None,
                  fte: float | None = None):
    data = await run_in_threadpool(build_roi_pdf, ca, materials_pct, salaire_brut,
                                   charges_pct, frais_generes, loaded_salary, fte)
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="economies-construpilot.pdf"',
                 "Cache-Control": "public, max-age=300"})


class RoiLeadIn(BaseModel):
    email: EmailStr
    company: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=40)
    ca_annual: float = 0
    estimated_monthly: float = 0
    website: str = ""  # honeypot anti-spam


@router.post("/roi/lead", status_code=201)
@limiter.limit("10/hour")
async def roi_lead(body: RoiLeadIn, request: Request, response: Response) -> dict:
    """Capture de lead depuis le calculateur d'économies (page publique)."""
    if body.website.strip():
        return {"ok": True, "lead_id": "spam"}
    now = datetime.now(timezone.utc).isoformat()
    doc = {"lead_id": "roi_" + uuid.uuid4().hex[:10], "email": body.email.strip().lower(),
           "company": body.company.strip(), "phone": body.phone.strip(),
           "ca_annual": float(body.ca_annual or 0), "estimated_monthly": float(body.estimated_monthly or 0),
           "source": "roi_calculator", "status": "new", "created_at": now}
    await db.roi_leads.insert_one(dict(doc))
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1}).to_list(20)
    for a in admins:
        await db.notifications.insert_one({
            "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": a["user_id"], "type": "roi_lead",
            "link": "/admin", "read": False, "created_at": now,
            "message": (f"Lead da calculadora de ROI: {doc['email']} (CA {int(doc['ca_annual'])} €, poupança ~{int(doc['estimated_monthly'])} €/mês)")})
    return {"ok": True, "lead_id": doc["lead_id"]}
