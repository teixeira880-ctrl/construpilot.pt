from fastapi import APIRouter
from fastapi.responses import Response

from engines.pdf_pitch import build_pitch_deck_pdf

router = APIRouter(prefix="/investors", tags=["investors"])


@router.get("/pitch-deck.pdf")
async def pitch_deck_pdf():
    """PDF public du pitch deck investisseurs (page /investisseurs)."""
    pdf = build_pitch_deck_pdf()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="ConstruPilot-Pitch-Deck.pdf"'},
    )
