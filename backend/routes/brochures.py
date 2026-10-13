"""Plaquettes et decks : version client personnalisée (pro) et version investisseur (admin).

PDF et PowerPoint, en français, anglais et portugais. Ces documents ne sont pas publiés sur le
site : seul un utilisateur connecté (client) ou un administrateur (investisseur) peut les générer.
"""
from fastapi import APIRouter, Depends, Query, Response

from core.db import db
from core.security import admin_user, current_user
from engines import presentation_pdf, presentation_pptx
from engines.journey import journey_metrics
from routes.plans_common import _resolve_branding

router = APIRouter(prefix="/brochures", tags=["brochures"])

LANG = "^(fr|en|pt)$"
PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


def _file(content: bytes, name: str, mime: str) -> Response:
    return Response(content=content, media_type=mime,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def _investor_context():
    """KPI réels + nombre de documents, mesurés à l'instant de la génération."""
    metrics = await journey_metrics(30)
    docs = await db.pro_documents.count_documents({"doc_type": {"$in": ["quote", "invoice"]}})
    return metrics, docs


@router.get("/plaquette.pdf")
async def client_brochure(lang: str = Query("fr", pattern=LANG), branded: bool = True,
                          prospect: str | None = Query(None, max_length=80),
                          user=Depends(current_user)):
    """Plaquette commerciale, à l'en-tête de l'entreprise abonnée."""
    branding = await _resolve_branding(user["user_id"]) if branded else None
    return _file(presentation_pdf.build_client_pdf(lang, branding, (prospect or "").strip() or None),
                 f"ConstruPilot-plaquette-{lang}.pdf", "application/pdf")


@router.get("/plaquette.pptx")
async def client_deck_pptx(lang: str = Query("fr", pattern=LANG), branded: bool = True,
                           prospect: str | None = Query(None, max_length=80),
                           user=Depends(current_user)):
    """Deck client PowerPoint : page de garde personnalisée et captures d'écran réelles."""
    branding = await _resolve_branding(user["user_id"]) if branded else None
    return _file(
        presentation_pptx.build_client_pptx(lang, branding, (prospect or "").strip() or None),
        f"ConstruPilot-presentation-client-{lang}.pptx", PPTX_MIME)


@router.get("/investisseurs.pdf")
async def investor_deck(lang: str = Query("fr", pattern=LANG), admin=Depends(admin_user)):
    """Présentation investisseur avec les KPI réels mesurés à l'instant de la génération."""
    metrics, docs = await _investor_context()
    budget = None
    try:
        from engines.expenses import cap
        st = await cap.status()
        budget = {"spent_eur": round(float(st.get("spent_eur") or st.get("spent") or 0), 2),
                  "cap_eur": float(st.get("cap_eur") or st.get("cap") or 500)}
    except Exception:  # noqa: BLE001 — le PDF reste générable sans le suivi budgétaire
        budget = None
    return _file(presentation_pdf.build_investor_pdf(lang, metrics, budget, docs),
                 f"ConstruPilot-investisseurs-{lang}.pdf", "application/pdf")


@router.get("/investisseurs.pptx")
async def investor_deck_pptx(lang: str = Query("fr", pattern=LANG), admin=Depends(admin_user)):
    """Deck investisseur PowerPoint : KPI réels, marché, plan d'exploitation de 500 000 €."""
    metrics, docs = await _investor_context()
    return _file(presentation_pptx.build_investor_pptx(lang, metrics, docs),
                 f"ConstruPilot-investisseurs-{lang}.pptx", PPTX_MIME)
