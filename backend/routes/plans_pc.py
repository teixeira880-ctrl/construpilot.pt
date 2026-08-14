"""Étude Permis de Construire (PC) — routes : analyse IA + devis gros œuvre."""
from __future__ import annotations

import asyncio
import logging
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from engines.pc_export import build_pc_docx, build_pc_pdf
from engines.pc_study import (CREW_SIZE, HOURLY_RATE_EUR, PC_UNIT_PRICES,
                              analyze_pc_page, build_study, compute_gros_oeuvre,
                              compute_planning, merge_pc_analyses,
                              merge_unit_prices)
from routes.plans_common import _now, _resolve_branding, router

logger = logging.getLogger(__name__)

MAX_PC_PAGES = 8

# Router séparé (prefix /pc) : réglages utilisateur + pixel de tracking public
pc_router = APIRouter(prefix="/pc", tags=["pc-study"])


async def _load_pc_settings(user_id: str) -> dict:
    doc = await db.pc_settings.find_one({"user_id": user_id}, {"_id": 0})
    return doc or {}


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
    settings = await _load_pc_settings(user["user_id"])
    study = build_study(merged, overrides, rooms_surface,
                        pages_analyzed=[i for i, _ in images],
                        settings=settings)
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


@router.post("/{plan_id}/pc-study/recompute")
async def recompute_pc_study(plan_id: str, user=Depends(current_user)) -> dict:
    """Recalcule devis + planning avec les réglages actuels (sans rappel IA)."""
    p = await _plan_and_study(plan_id, user["user_id"])
    study = p["pc_study"]
    settings = await _load_pc_settings(user["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    crew = int(settings.get("crew_size") or CREW_SIZE)
    rate = float(settings.get("hourly_rate_eur") or HOURLY_RATE_EUR)
    computed = compute_gros_oeuvre(study["inputs"], None, prices)
    study.update(**computed,
                 planning=compute_planning(computed["lots"], crew, rate),
                 custom_pricing=bool(settings.get("unit_prices")),
                 recomputed_at=_now())
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"pc_study": study, "updated_at": _now()}})
    return study


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
    track_id = "pct_" + secrets.token_hex(6)
    backend_public = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("FRONTEND_URL") or ""
    if backend_public:
        html_body += (f'<img src="{backend_public}/api/pc/track/{track_id}" '
                      'width="1" height="1" alt="" style="display:block" />')
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
            "track_id": track_id, "opened": False,
        }], "$slice": -20}}})
    return {"ok": True, "sent_to": body.to_email, "ttc": t.get("ttc"),
            "track_id": track_id}


# ---- Réglages étude PC (prix unitaires, équipe, taux horaire) ------------

class PcSettingsIn(BaseModel):
    unit_prices: dict | None = None
    crew_size: int | None = Field(default=None, ge=1, le=12)
    hourly_rate_eur: float | None = Field(default=None, ge=20, le=150)


@pc_router.get("/settings")
async def get_pc_settings(user=Depends(current_user)) -> dict:
    settings = await _load_pc_settings(user["user_id"])
    return {"settings": settings or None,
            "defaults": {"unit_prices": PC_UNIT_PRICES,
                         "crew_size": CREW_SIZE,
                         "hourly_rate_eur": HOURLY_RATE_EUR}}


@pc_router.put("/settings")
async def save_pc_settings(body: PcSettingsIn, user=Depends(current_user)) -> dict:
    prices = None
    if body.unit_prices:
        prices = {}
        for k, v in body.unit_prices.items():
            if k not in PC_UNIT_PRICES or not isinstance(v, dict):
                continue
            try:
                prices[k] = {"mat": max(0.0, float(v.get("mat", PC_UNIT_PRICES[k]["mat"]))),
                             "mo": max(0.0, float(v.get("mo", PC_UNIT_PRICES[k]["mo"])))}
            except (TypeError, ValueError):
                continue
    doc = {"user_id": user["user_id"], "unit_prices": prices,
           "crew_size": body.crew_size, "hourly_rate_eur": body.hourly_rate_eur,
           "updated_at": _now()}
    await db.pc_settings.update_one({"user_id": user["user_id"]},
                                    {"$set": doc}, upsert=True)
    return {"ok": True, "settings": {k: v for k, v in doc.items() if k != "user_id"}}


@pc_router.delete("/settings")
async def reset_pc_settings(user=Depends(current_user)) -> dict:
    await db.pc_settings.delete_one({"user_id": user["user_id"]})
    return {"ok": True}


# ---- Pixel de tracking d'ouverture (public, comme les devis) -------------

_PIXEL = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
          b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D"
          b"\x01\x00;")


@pc_router.get("/track/{track_id}", include_in_schema=False)
async def track_pc_open(track_id: str):
    """Pixel : marque l'étude PC comme ouverte par le client (idempotent)."""
    try:
        await db.plans_takeoff.update_one(
            {"sent_reports": {"$elemMatch": {"track_id": track_id,
                                             "opened": {"$ne": True}}}},
            {"$set": {"sent_reports.$.opened": True,
                      "sent_reports.$.opened_at": _now()}})
    except Exception as e:
        logger.warning(f"pc tracking pixel fail {track_id}: {e}")
    return Response(content=_PIXEL, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
