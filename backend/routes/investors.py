import csv
import io
import uuid
from datetime import datetime, timezone

from core.db import db
from core.security import admin_user
from engines.pdf_pitch import DECK_MANIFEST, deck_asset_response
from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/investors", tags=["investors"])


class DeckRequestIn(BaseModel):
    name: str = ""
    email: EmailStr
    fund: str = ""
    note: str = ""


class DeckRequestOut(BaseModel):
    ok: bool
    download_url: str
    powerpoint_url: str


@router.post("/deck-request", response_model=DeckRequestOut)
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
    return DeckRequestOut(
        ok=True,
        download_url="/api/investors/pitch-deck.pdf",
        powerpoint_url="/api/investors/pitch-deck.pptx",
    )


@router.get("/deck-requests.csv", dependencies=[Depends(admin_user)])
async def deck_requests_csv():
    """Export CSV (admin) des investisseurs ayant téléchargé le pitch deck."""
    rows = await db.deck_downloads.find({}, {"_id": 0}).sort("created_at", -1).to_list(5000)
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    wr.writerow(["Data", "Nome", "E-mail", "Fundo / sociedade", "Nota", "IP", "Referer"])
    for r in rows:
        wr.writerow([
            (r.get("created_at") or "")[:19].replace("T", " "),
            r.get("name", ""), r.get("email", ""), r.get("fund", ""),
            r.get("note", ""), r.get("ip", ""), r.get("referer", ""),
        ])
    data = buf.getvalue().encode("utf-8-sig")
    return Response(content=data, media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=leads-investidores.csv"})


@router.api_route("/pitch-deck.pdf", methods=["GET", "HEAD"])
async def pitch_deck_pdf():
    """PDF fidèle du PowerPoint fourni, conservant l'URL publique existante."""
    return deck_asset_response("ConstruPilot_PitchDeck.pdf", "application/pdf")


@router.api_route("/pitch-deck.pptx", methods=["GET", "HEAD"])
async def pitch_deck_powerpoint():
    return deck_asset_response(
        "ConstruPilot_PitchDeck.pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        inline=False,
    )


class DeckInfo(BaseModel):
    source_filename: str
    source_sha256: str
    page_count: int
    width: int
    height: int


@router.get("/pitch-deck", response_model=DeckInfo)
async def pitch_deck_info():
    return DeckInfo(**{key: DECK_MANIFEST[key] for key in DeckInfo.model_fields})


@router.api_route("/pitch-deck/slides/{page}.webp", methods=["GET", "HEAD"])
async def pitch_deck_slide(page: int = Path(ge=1, le=DECK_MANIFEST["page_count"])):
    return deck_asset_response(f"slides/{page}.webp", "image/webp")
