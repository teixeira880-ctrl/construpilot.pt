"""Étude Permis de Construire (PC) — routes : analyse IA + devis gros œuvre."""
from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from engines.pc_export import build_pc_docx, build_pc_pdf
from engines.pc_study import analyze_pc_page, build_study, merge_pc_analyses
from routes.plans_common import _now, _resolve_branding, router

logger = logging.getLogger(__name__)

MAX_PC_PAGES = 8


class PcStudyIn(BaseModel):
    pages: list[int] | None = None
    wall_height_m: float | None = None
    levels: int | None = None
    perimeter_m: float | None = None
    refends_m: float | None = None
    surface_m2: float | None = None


@router.post("/{plan_id}/pc-study")
async def run_pc_study(plan_id: str, body: PcStudyIn, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "rooms": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if not pages:
        raise HTTPException(400, "Aucune page à analyser")

    indices = body.pages if body.pages else list(range(len(pages)))
    indices = [i for i in indices if 0 <= i < len(pages)][:MAX_PC_PAGES]
    images = [(i, pages[i].get("image_png_b64")) for i in indices
              if pages[i].get("image_png_b64")]
    if not images:
        raise HTTPException(500, "Images des pages manquantes")

    analyses = await asyncio.gather(
        *[asyncio.wait_for(analyze_pc_page(img), timeout=90) for _, img in images],
        return_exceptions=True)
    analyses = [a if isinstance(a, dict) else {"error": f"timeout/erreur: {type(a).__name__}",
                                               "confidence": 0.0} for a in analyses]
    merged = merge_pc_analyses(list(analyses))
    if merged["pages_ok"] == 0:
        first_err = next((a.get("error") for a in analyses if a.get("error")), "IA indisponible")
        raise HTTPException(502, f"Analyse IA échouée sur toutes les pages : {first_err}")

    rooms_surface = round(sum(float(r.get("surface_m2") or 0)
                              for r in (p.get("rooms") or [])), 2)
    overrides = {k: v for k, v in body.dict().items() if k != "pages"}
    study = build_study(merged, overrides, rooms_surface,
                        pages_analyzed=[i for i, _ in images])
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"pc_study": study, "updated_at": _now()}})
    return study


@router.get("/{plan_id}/pc-study")
async def get_pc_study(plan_id: str, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pc_study": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return {"pc_study": p.get("pc_study")}


async def _plan_and_study(plan_id: str, user_id: str) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "filename": 1, "pc_study": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    if not p.get("pc_study"):
        raise HTTPException(400, "Aucune étude PC — lancez d'abord l'analyse")
    return p


@router.get("/{plan_id}/pc-study/pdf")
async def export_pc_pdf(plan_id: str, user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user["user_id"])
    branding = await _resolve_branding(user["user_id"])
    pdf = build_pc_pdf(p, p["pc_study"], branding)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="etude-pc-{plan_id}.pdf"'})


@router.get("/{plan_id}/pc-study/docx")
async def export_pc_docx(plan_id: str, user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user["user_id"])
    branding = await _resolve_branding(user["user_id"])
    docx = build_pc_docx(p, p["pc_study"], branding)
    return Response(
        content=docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f'attachment; filename="etude-pc-{plan_id}.docx"'})


class PcSendIn(BaseModel):
    to_email: EmailStr
    message: str = Field(default="", max_length=2000)


@router.post("/{plan_id}/pc-study/send")
async def send_pc_study(plan_id: str, body: PcSendIn, user=Depends(current_user)) -> dict:
    """Envoie l'étude PC (PDF joint) au client, avec un mot personnalisé."""
    import html as _html
    from engines.emailer import send_email_with_pdf, wrap_html

    p = await _plan_and_study(plan_id, user["user_id"])
    study = p["pc_study"]
    branding = await _resolve_branding(user["user_id"])
    pdf = build_pc_pdf(p, study, branding)

    t = study.get("totals") or {}
    pl = study.get("planning") or {}
    filename = p.get("filename") or "permis de construire"
    perso = _html.escape(body.message.strip()).replace("\n", "<br/>")
    intro = f"<p>{perso}</p>" if perso else ""
    recap = (f"<p><b>{t.get('beton_m3', 0)} m³</b> de béton · "
             f"<b>{t.get('acier_kg', 0)} kg</b> d'aciers · "
             f"<b>{t.get('briques_u', 0)}</b> briques isobrique — "
             f"Total <b>{t.get('ttc', 0)} € TTC</b>.</p>")
    if pl.get("total_days"):
        recap += (f"<p>Durée de chantier estimée : <b>{pl['total_days']} jours</b> "
                  f"({pl['total_weeks']} semaines), équipe de {pl['crew_size']}.</p>")
    html_body = (
        intro +
        "<p>Veuillez trouver ci-joint l'<b>étude gros œuvre</b> établie à partir du "
        f"permis de construire « {_html.escape(filename)} » : quantités de béton, "
        "aciers, briques et devis détaillé par corps d'état.</p>" + recap)
    html = wrap_html("Étude gros œuvre — Permis de construire", html_body)
    try:
        await send_email_with_pdf(
            body.to_email, f"Étude gros œuvre — {filename}",
            html, pdf, filename=f"etude-pc-{plan_id}.pdf")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Envoi de l'email impossible — réessayez plus tard")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$push": {"sent_reports": {"$each": [{
            "kind": "pc_study", "to_email": body.to_email, "sent_at": _now(),
            "ttc": t.get("ttc"), "beton_m3": t.get("beton_m3"),
        }], "$slice": -20}}})
    return {"ok": True, "sent_to": body.to_email, "ttc": t.get("ttc")}
