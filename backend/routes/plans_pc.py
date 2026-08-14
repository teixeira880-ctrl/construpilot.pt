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
from core.security import admin_user, current_user
from engines.pc_export import (build_pc_docx, build_pc_pdf,
                               build_purchase_order_pdf)
from engines.pc_study import (CREW_SIZE, HOURLY_RATE_EUR, PC_UNIT_PRICES,
                              analyze_pc_page, build_purchase_order_items,
                              build_study, compute_gros_oeuvre,
                              compute_levels_breakdown, compute_planning,
                              merge_pc_analyses, merge_unit_prices,
                              schedule_with_dates)
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


async def _archive_pc_version(plan_id: str, user_id: str, study: dict,
                              source: str) -> None:
    """Historise la version courante avant remplacement (comparaison des prix)."""
    t = study.get("totals") or {}
    pl = study.get("planning") or {}
    await db.pc_study_history.insert_one({
        "plan_id": plan_id, "user_id": user_id, "saved_at": _now(),
        "source": source, "custom_pricing": bool(study.get("custom_pricing")),
        "ht": t.get("ht"), "ttc": t.get("ttc"), "tva": t.get("tva"),
        "beton_m3": t.get("beton_m3"), "acier_kg": t.get("acier_kg"),
        "briques_u": t.get("briques_u"), "total_days": pl.get("total_days")})


@router.post("/{plan_id}/pc-study")
async def run_pc_study(plan_id: str, body: PcStudyIn, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "rooms": 1, "pc_study": 1})
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
    if p.get("pc_study"):
        await _archive_pc_version(plan_id, user["user_id"], p["pc_study"], "analyse")
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
    await _archive_pc_version(plan_id, user["user_id"], study, "recalcul")
    settings = await _load_pc_settings(user["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    crew = int(settings.get("crew_size") or CREW_SIZE)
    rate = float(settings.get("hourly_rate_eur") or HOURLY_RATE_EUR)
    computed = compute_gros_oeuvre(study["inputs"], None, prices)
    study.update(**computed,
                 planning=compute_planning(computed["lots"], crew, rate),
                 levels_breakdown=compute_levels_breakdown(study["inputs"], prices),
                 custom_pricing=bool(settings.get("unit_prices")),
                 recomputed_at=_now())
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"pc_study": study, "updated_at": _now()}})
    return study


@router.get("/{plan_id}/pc-study/history")
async def get_pc_history(plan_id: str, user=Depends(current_user)) -> dict:
    """Versions archivées de l'étude (comparaison de l'évolution des prix)."""
    rows = await db.pc_study_history.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}).sort("saved_at", -1).to_list(20)
    return {"history": rows}


# ---- Bon de commande fournisseur (par niveau) ------------------------------

def _order_context(p: dict, level_index: int, prices: dict) -> tuple[dict, list[dict], str]:
    lb = (p["pc_study"].get("levels_breakdown") or [])
    if not (0 <= level_index < len(lb)):
        raise HTTPException(400, "Niveau inconnu — relancez l'analyse ou le recalcul")
    level = lb[level_index]
    items = build_purchase_order_items(level, prices)
    if not items:
        raise HTTPException(400,
                            "Aucun matériau à commander sur ce niveau — recalculez "
                            "l'étude pour régénérer les données")
    ref = f"BC-{p['plan_id'][-6:].upper()}-N{level_index}-{_now()[:10].replace('-', '')}"
    return level, items, ref


@router.get("/{plan_id}/pc-study/purchase-order")
async def download_purchase_order(plan_id: str, level: int = 0,
                                  supplier: str = "", notes: str = "",
                                  user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user["user_id"])
    p["plan_id"] = plan_id
    settings = await _load_pc_settings(user["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    lvl, items, ref = _order_context(p, level, prices)
    branding = await _resolve_branding(user["user_id"])
    pdf = build_purchase_order_pdf(p, lvl["name"], items, branding, ref,
                                   supplier_name=supplier[:80], notes=notes[:500])
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="{ref}.pdf"'})


class PcOrderSendIn(BaseModel):
    level_index: int = Field(ge=0, le=10)
    supplier_email: EmailStr
    supplier_name: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=500)


@router.post("/{plan_id}/pc-study/purchase-order/send")
async def send_purchase_order(plan_id: str, body: PcOrderSendIn,
                              user=Depends(current_user)) -> dict:
    import html as _html
    from engines.emailer import send_email_with_pdf, wrap_html

    p = await _plan_and_study(plan_id, user["user_id"])
    p["plan_id"] = plan_id
    settings = await _load_pc_settings(user["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    lvl, items, ref = _order_context(p, body.level_index, prices)
    branding = await _resolve_branding(user["user_id"])
    pdf = build_purchase_order_pdf(p, lvl["name"], items, branding, ref,
                                   supplier_name=body.supplier_name,
                                   notes=body.notes)
    company = (branding or {}).get("company_name") or user.get("name") or "ConstruPilot"
    total = round(sum(it["total"] for it in items), 2)
    notes_html = ""
    if body.notes.strip():
        notes_html = ("<p><b>Notes :</b><br/>"
                      f"{_html.escape(body.notes.strip()).replace(chr(10), '<br/>')}</p>")
    html_body = (
        f"<p>Bonjour{' ' + _html.escape(body.supplier_name) if body.supplier_name else ''},</p>"
        f"<p>Veuillez trouver ci-joint notre <b>bon de commande {ref}</b> pour la phase "
        f"« {_html.escape(lvl['name'])} » de notre chantier "
        f"« {_html.escape(p.get('filename') or 'construction')} » — "
        f"{len(items)} articles, total indicatif <b>{total} € HT</b>.</p>"
        f"{notes_html}"
        "<p>Merci de nous confirmer vos tarifs, disponibilités et délais de livraison "
        f"en répondant à cet email ({_html.escape(user.get('email') or '')}).<br/>"
        f"{_html.escape(company)}</p>")
    try:
        await send_email_with_pdf(
            body.supplier_email, f"Bon de commande {ref} · {company}",
            wrap_html(f"Bon de commande {ref}", html_body),
            pdf, filename=f"{ref}.pdf")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Envoi de l'email impossible — réessayez plus tard")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$push": {"sent_reports": {"$each": [{
            "kind": "purchase_order", "to_email": body.supplier_email,
            "sent_at": _now(), "ref": ref, "level": lvl["name"], "total_ht": total,
        }], "$slice": -20}}})
    return {"ok": True, "sent_to": body.supplier_email, "ref": ref,
            "total_ht": total, "items": len(items)}


async def _plan_and_study(plan_id: str, user_id: str) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "filename": 1, "pc_study": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    if not p.get("pc_study"):
        raise HTTPException(400, "Aucune étude PC — lancez d'abord l'analyse")
    return p


DEFAULT_REMINDER_DAYS = 3


def _valid_date(s: str | None) -> str | None:
    if not s:
        return None
    from datetime import date
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


@router.get("/{plan_id}/pc-study/pdf")
async def export_pc_pdf(plan_id: str, start: str | None = None,
                        user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user["user_id"])
    branding = await _resolve_branding(user["user_id"])
    pdf = build_pc_pdf(p, p["pc_study"], branding, start_date=_valid_date(start))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="etude-pc-{plan_id}.pdf"'})


@router.get("/{plan_id}/pc-study/docx")
async def export_pc_docx(plan_id: str, start: str | None = None,
                         user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user["user_id"])
    branding = await _resolve_branding(user["user_id"])
    docx = build_pc_docx(p, p["pc_study"], branding, start_date=_valid_date(start))
    return Response(
        content=docx,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition":
                 f'attachment; filename="etude-pc-{plan_id}.docx"'})


class PcSendIn(BaseModel):
    to_email: EmailStr
    message: str = Field(default="", max_length=2000)
    start_date: str | None = None


@router.post("/{plan_id}/pc-study/send")
async def send_pc_study(plan_id: str, body: PcSendIn, user=Depends(current_user)) -> dict:
    """Envoie l'étude PC (PDF joint) au client, avec un mot personnalisé."""
    import html as _html
    from engines.emailer import send_email_with_pdf, wrap_html

    p = await _plan_and_study(plan_id, user["user_id"])
    study = p["pc_study"]
    branding = await _resolve_branding(user["user_id"])
    start = _valid_date(body.start_date)
    pdf = build_pc_pdf(p, study, branding, start_date=start)

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
    if start and pl.get("phases"):
        sched = schedule_with_dates(pl, start)
        d0, d1 = sched[0]["work_start"], sched[-1]["cure_end"]
        recap += (f"<p>Démarrage prévu le <b>{d0[8:10]}/{d0[5:7]}/{d0[0:4]}</b> — "
                  f"fin de chantier estimée le <b>{d1[8:10]}/{d1[5:7]}/{d1[0:4]}</b>.</p>")
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
    reminder_days: int | None = Field(default=None, ge=0, le=30)
    notify_on_open: str | None = Field(default=None,
                                       pattern="^(email|sms|both|off)$")
    notify_phone: str | None = Field(default=None, max_length=20)


@pc_router.get("/settings")
async def get_pc_settings(user=Depends(current_user)) -> dict:
    settings = await _load_pc_settings(user["user_id"])
    return {"settings": settings or None,
            "defaults": {"unit_prices": PC_UNIT_PRICES,
                         "crew_size": CREW_SIZE,
                         "hourly_rate_eur": HOURLY_RATE_EUR,
                         "reminder_days": DEFAULT_REMINDER_DAYS,
                         "notify_on_open": "email"}}


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
           "reminder_days": body.reminder_days,
           "notify_on_open": body.notify_on_open,
           "notify_phone": (body.notify_phone or "").strip() or None,
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


async def _notify_study_opened(track_id: str) -> None:
    """Prévient le pro (email et/ou SMS) à la 1ʳᵉ ouverture de son étude par le client."""
    import html as _html
    from engines.emailer import send_email, wrap_html

    p = await db.plans_takeoff.find_one(
        {"sent_reports.track_id": track_id},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
         "sent_reports.$": 1})
    if not p:
        return
    entry = (p.get("sent_reports") or [{}])[0]
    settings = await _load_pc_settings(p["user_id"])
    mode = settings.get("notify_on_open") or "email"
    if mode == "off":
        return
    u = await db.users.find_one({"user_id": p["user_id"]},
                                {"_id": 0, "email": 1, "name": 1})
    filename = p.get("filename") or "permis de construire"
    client = entry.get("to_email") or "votre client"
    if mode in ("email", "both") and u and u.get("email"):
        html = wrap_html(
            "Votre étude vient d'être ouverte",
            f"<p>Bonjour {_html.escape(u.get('name') or '')},</p>"
            f"<p>Bonne nouvelle : <b>{_html.escape(client)}</b> vient d'ouvrir "
            f"l'étude gros œuvre du chantier « {_html.escape(filename)} ».</p>"
            "<p>C'est le bon moment pour le rappeler.</p>")
        await send_email(u["email"],
                         f"👀 {client} a ouvert votre étude · {filename}", html)
    if mode in ("sms", "both") and settings.get("notify_phone"):
        from engines.alerting import _send_sms
        _send_sms(settings["notify_phone"],
                  f"ConstruPilot : {client} vient d'ouvrir votre étude gros œuvre "
                  f"({filename}). Rappelez-le pendant qu'il est dessus !")


@pc_router.get("/track/{track_id}", include_in_schema=False)
async def track_pc_open(track_id: str):
    """Pixel : marque l'étude PC comme ouverte par le client (idempotent)."""
    try:
        r = await db.plans_takeoff.update_one(
            {"sent_reports": {"$elemMatch": {"track_id": track_id,
                                             "opened": {"$ne": True}}}},
            {"$set": {"sent_reports.$.opened": True,
                      "sent_reports.$.opened_at": _now()}})
        if r.modified_count:
            try:
                await _notify_study_opened(track_id)
            except Exception as e:
                logger.warning(f"pc open notify fail {track_id}: {e}")
    except Exception as e:
        logger.warning(f"pc tracking pixel fail {track_id}: {e}")
    return Response(content=_PIXEL, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


# ---- Relance automatique si l'étude n'est pas ouverte ---------------------

async def _send_pc_reminder(p: dict, s: dict) -> None:
    import html as _html
    from engines.emailer import send_email_with_pdf, wrap_html

    branding = await _resolve_branding(p["user_id"])
    company = (branding or {}).get("company_name") or "ConstruPilot"
    pdf = build_pc_pdf(p, p["pc_study"], branding)
    t = (p["pc_study"].get("totals") or {})
    filename = p.get("filename") or "permis de construire"
    html_body = (
        "<p>Bonjour,</p>"
        f"<p>Petit rappel : l'<b>étude gros œuvre</b> de votre projet "
        f"« {_html.escape(filename)} » vous attend. Vous la trouverez de nouveau "
        "en pièce jointe de cet email.</p>"
        f"<p><b>{t.get('beton_m3', 0)} m³</b> de béton · "
        f"<b>{t.get('acier_kg', 0)} kg</b> d'aciers — "
        f"Total <b>{t.get('ttc', 0)} € TTC</b>.</p>"
        f"<p>N'hésitez pas à répondre à cet email pour toute question.<br/>{_html.escape(company)}</p>")
    backend_public = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("FRONTEND_URL") or ""
    if backend_public and s.get("track_id"):
        html_body += (f'<img src="{backend_public}/api/pc/track/{s["track_id"]}" '
                      'width="1" height="1" alt="" style="display:block" />')
    await send_email_with_pdf(
        s["to_email"], f"Rappel — Étude gros œuvre · {filename}",
        wrap_html("Rappel — Étude gros œuvre", html_body),
        pdf, filename=f"etude-pc-{p['plan_id']}.pdf")


async def _run_pc_reminders() -> dict:
    """Job : relance les études PC envoyées mais jamais ouvertes après N jours."""
    from datetime import datetime, timedelta, timezone

    plans = await db.plans_takeoff.find(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "opened": {"$ne": True},
                                         "reminder_sent": {"$ne": True},
                                         "track_id": {"$exists": True}}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
         "pc_study": 1, "sent_reports": 1}).to_list(200)
    settings_cache: dict[str, dict] = {}
    sent, failed, skipped = 0, 0, 0
    now = datetime.now(timezone.utc)
    for p in plans:
        uid = p["user_id"]
        if uid not in settings_cache:
            settings_cache[uid] = await _load_pc_settings(uid)
        days = settings_cache[uid].get("reminder_days")
        days = DEFAULT_REMINDER_DAYS if days is None else int(days)
        if days <= 0:
            skipped += 1
            continue
        cutoff = (now - timedelta(days=days)).isoformat()
        for s in p.get("sent_reports") or []:
            if (s.get("kind") != "pc_study" or s.get("opened")
                    or s.get("reminder_sent") or not s.get("track_id")
                    or (s.get("sent_at") or "9999") > cutoff):
                continue
            try:
                await _send_pc_reminder(p, s)
                await db.plans_takeoff.update_one(
                    {"plan_id": p["plan_id"],
                     "sent_reports.track_id": s["track_id"]},
                    {"$set": {"sent_reports.$.reminder_sent": True,
                              "sent_reports.$.reminder_at": _now()}})
                sent += 1
            except Exception as e:
                logger.warning(f"pc reminder {p['plan_id']}/{s.get('track_id')}: {e}")
                failed += 1
    return {"sent": sent, "failed": failed, "skipped": skipped,
            "candidates": len(plans)}


@pc_router.post("/reminders/run")
async def trigger_pc_reminders(user=Depends(admin_user)) -> dict:
    """Endpoint admin pour lancer manuellement les relances d'études PC."""
    return await _run_pc_reminders()
