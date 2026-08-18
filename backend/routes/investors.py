import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

from core.db import db
from engines.pdf_pitch import build_pitch_deck_pdf

router = APIRouter(prefix="/investors", tags=["investors"])


class DeckRequestIn(BaseModel):
    name: str = ""
    email: EmailStr
    fund: str = ""
    note: str = ""


@router.post("/deck-request")
async def deck_request(body: DeckRequestIn, request: Request):
    """Journalise une demande de pitch deck (lead investisseur) puis renvoie l'URL du PDF."""
    doc = {
        "download_id": f"deck_{uuid.uuid4().hex[:10]}",
        "name": body.name.strip(),
        "email": str(body.email).lower().strip(),
        "fund": body.fund.strip(),
        "note": body.note.strip(),
        "ip": (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
              or (request.client.host if request.client else ""),
        "user_agent": request.headers.get("user-agent", "")[:300],
        "referer": request.headers.get("referer", "")[:300],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.deck_downloads.insert_one(doc)
    return {"ok": True, "download_url": "/api/investors/pitch-deck.pdf"}


@router.get("/pitch-deck.pdf")
async def pitch_deck_pdf():
    """PDF public du pitch deck investisseurs (page /investisseurs)."""
    pdf = build_pitch_deck_pdf()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="ConstruPilot-Pitch-Deck.pdf"'},
    )
