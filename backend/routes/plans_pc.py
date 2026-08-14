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
from engines.pc_export import (build_deposit_invoice_pdf, build_pc_docx,
                               build_pc_pdf, build_purchase_order_pdf)
from engines.pc_study import (CREW_SIZE, DEFAULT_MARGIN_PCT, HOURLY_RATE_EUR,
                              PC_UNIT_PRICES, analyze_pc_page,
                              build_purchase_order_items, build_study,
                              compute_study_costing, merge_pc_analyses,
                              merge_unit_prices, schedule_with_dates)
from routes.plans_common import _now, _resolve_branding, router

logger = logging.getLogger(__name__)

MAX_PC_PAGES = 8

# Router séparé (prefix /pc) : réglages utilisateur + pixel de tracking public
pc_router = APIRouter(prefix="/pc", tags=["pc-study"])


async def _load_pc_settings(user_id: str) -> dict:
    doc = await db.pc_settings.find_one({"user_id": user_id}, {"_id": 0})
    return doc or {}


DEFAULT_DEPOSIT_PCT = 30.0
DEFAULT_DEPOSIT_REMINDER_DAYS = 3


async def _next_invoice_no(user_id: str) -> str:
    """Numérotation séquentielle des factures d'acompte, par pro et par année."""
    from datetime import datetime, timezone
    from pymongo import ReturnDocument
    year = datetime.now(timezone.utc).year
    c = await db.counters.find_one_and_update(
        {"_id": f"pc_deposit_invoice_{user_id}_{year}"},
        {"$inc": {"seq": 1}}, upsert=True,
        return_document=ReturnDocument.AFTER)
    return f"AC-{year}-{int(c['seq']):04d}"


async def _pc_owner_id(plan_id: str, user: dict, write: bool = False) -> str:
    """Propriétaire du plan — accès accordé au propriétaire et à son équipe (org).

    write=True : refuse les collègues si le propriétaire est en lecture seule."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id}, {"_id": 0, "user_id": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    owner_id = p["user_id"]
    if owner_id == user["user_id"]:
        return owner_id
    org = user.get("organization_id")
    if not org:
        raise HTTPException(404, "Plan introuvable")
    owner = await db.users.find_one({"user_id": owner_id},
                                    {"_id": 0, "organization_id": 1})
    if not owner or owner.get("organization_id") != org:
        raise HTTPException(404, "Plan introuvable")
    settings = await _load_pc_settings(owner_id)
    if settings.get("team_share") is False:
        raise HTTPException(403, "Partage équipe désactivé par le propriétaire de l'étude")
    if write and settings.get("team_can_edit") is not True:
        raise HTTPException(403, "Lecture seule — le propriétaire n'autorise pas "
                                 "la modification de ses études par l'équipe")
    return owner_id


async def _team_members(owner_id: str) -> list[dict]:
    """Collègues (même organisation) du propriétaire — pour les notifications équipe."""
    owner = await db.users.find_one({"user_id": owner_id},
                                    {"_id": 0, "organization_id": 1})
    org = (owner or {}).get("organization_id")
    if not org:
        return []
    if (await _load_pc_settings(owner_id)).get("team_share") is False:
        return []
    rows = await db.users.find({"organization_id": org},
                               {"_id": 0, "user_id": 1, "email": 1, "name": 1}).to_list(50)
    return [r for r in rows if r["user_id"] != owner_id and r.get("email")][:10]


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
    owner_id = await _pc_owner_id(plan_id, user, write=True)
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id},
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
    settings = await _load_pc_settings(owner_id)
    study = build_study(merged, overrides, rooms_surface,
                        pages_analyzed=[i for i, _ in images],
                        settings=settings)
    if p.get("pc_study"):
        await _archive_pc_version(plan_id, owner_id, p["pc_study"], "analyse")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"pc_study": study, "updated_at": _now()}})
    return study


@router.get("/{plan_id}/pc-study")
async def get_pc_study(plan_id: str, user=Depends(current_user)) -> dict:
    await _pc_owner_id(plan_id, user)
    p = await db.plans_takeoff.find_one({"plan_id": plan_id}, {"_id": 0, "pc_study": 1})
    return {"pc_study": (p or {}).get("pc_study")}


@router.post("/{plan_id}/pc-study/recompute")
async def recompute_pc_study(plan_id: str, user=Depends(current_user)) -> dict:
    """Recalcule devis + planning avec les réglages actuels (sans rappel IA)."""
    p = await _plan_and_study(plan_id, user, write=True)
    owner_id = p["user_id"]
    study = p["pc_study"]
    await _archive_pc_version(plan_id, owner_id, study, "recalcul")
    settings = await _load_pc_settings(owner_id)
    prices = merge_unit_prices(settings.get("unit_prices"))
    crew = int(settings.get("crew_size") or CREW_SIZE)
    rate = float(settings.get("hourly_rate_eur") or HOURLY_RATE_EUR)
    margin = settings.get("margin_pct")
    margin = DEFAULT_MARGIN_PCT if margin is None else float(margin)
    computed, planning, levels = compute_study_costing(
        study["inputs"], None, prices, margin, crew, rate)
    study.update(**computed,
                 planning=planning,
                 levels_breakdown=levels,
                 custom_pricing=bool(settings.get("unit_prices")),
                 recomputed_at=_now())
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"pc_study": study, "updated_at": _now()}})
    return study


@router.get("/{plan_id}/pc-study/history")
async def get_pc_history(plan_id: str, user=Depends(current_user)) -> dict:
    """Versions archivées de l'étude (comparaison de l'évolution des prix)."""
    await _pc_owner_id(plan_id, user)
    rows = await db.pc_study_history.find(
        {"plan_id": plan_id},
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
    p = await _plan_and_study(plan_id, user)
    p["plan_id"] = plan_id
    settings = await _load_pc_settings(p["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    lvl, items, ref = _order_context(p, level, prices)
    branding = await _resolve_branding(p["user_id"])
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

    p = await _plan_and_study(plan_id, user, write=True)
    p["plan_id"] = plan_id
    settings = await _load_pc_settings(p["user_id"])
    prices = merge_unit_prices(settings.get("unit_prices"))
    lvl, items, ref = _order_context(p, body.level_index, prices)
    branding = await _resolve_branding(p["user_id"])
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
        {"plan_id": plan_id},
        {"$push": {"sent_reports": {"$each": [{
            "kind": "purchase_order", "to_email": body.supplier_email,
            "sent_at": _now(), "ref": ref, "level": lvl["name"], "total_ht": total,
        }], "$slice": -20}}})
    return {"ok": True, "sent_to": body.supplier_email, "ref": ref,
            "total_ht": total, "items": len(items)}


async def _plan_and_study(plan_id: str, user: dict, write: bool = False) -> dict:
    await _pc_owner_id(plan_id, user, write=write)
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id},
        {"_id": 0, "filename": 1, "pc_study": 1, "user_id": 1})
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
    p = await _plan_and_study(plan_id, user)
    branding = await _resolve_branding(p["user_id"])
    pdf = build_pc_pdf(p, p["pc_study"], branding, start_date=_valid_date(start))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="etude-pc-{plan_id}.pdf"'})


@router.get("/{plan_id}/pc-study/docx")
async def export_pc_docx(plan_id: str, start: str | None = None,
                         user=Depends(current_user)):
    p = await _plan_and_study(plan_id, user)
    branding = await _resolve_branding(p["user_id"])
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

    p = await _plan_and_study(plan_id, user, write=True)
    study = p["pc_study"]
    branding = await _resolve_branding(p["user_id"])
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
    sign_token = "pcs_" + secrets.token_hex(8)
    frontend = (os.getenv("FRONTEND_URL") or "").rstrip("/")
    if frontend:
        html_body += (
            f'<p style="margin:18px 0"><a href="{frontend}/etude/{sign_token}" '
            'style="background:#FF5A00;color:#ffffff;padding:11px 24px;'
            'border-radius:4px;text-decoration:none;font-weight:bold">'
            "Consulter et accepter l'étude en ligne</a></p>")
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
        {"plan_id": plan_id},
        {"$push": {"sent_reports": {"$each": [{
            "kind": "pc_study", "to_email": body.to_email, "sent_at": _now(),
            "ttc": t.get("ttc"), "beton_m3": t.get("beton_m3"),
            "track_id": track_id, "opened": False, "sign_token": sign_token,
        }], "$slice": -20}}})
    return {"ok": True, "sent_to": body.to_email, "ttc": t.get("ttc"),
            "track_id": track_id, "sign_token": sign_token}


# ---- Réglages étude PC (prix unitaires, équipe, taux horaire) ------------

class PcSettingsIn(BaseModel):
    unit_prices: dict | None = None
    crew_size: int | None = Field(default=None, ge=1, le=12)
    hourly_rate_eur: float | None = Field(default=None, ge=20, le=150)
    margin_pct: float | None = Field(default=None, ge=0, le=200)
    deposit_pct: float | None = Field(default=None, ge=0, le=100)
    deposit_reminder_days: int | None = Field(default=None, ge=0, le=30)
    weekly_report: bool | None = None
    team_share: bool | None = None
    team_can_edit: bool | None = None
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
                         "margin_pct": DEFAULT_MARGIN_PCT,
                         "deposit_pct": DEFAULT_DEPOSIT_PCT,
                         "deposit_reminder_days": DEFAULT_DEPOSIT_REMINDER_DAYS,
                         "weekly_report": True,
                         "team_share": True,
                         "team_can_edit": False,
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
           "margin_pct": body.margin_pct, "deposit_pct": body.deposit_pct,
           "deposit_reminder_days": body.deposit_reminder_days,
           "weekly_report": body.weekly_report, "team_share": body.team_share,
           "team_can_edit": body.team_can_edit,
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
    for m in await _team_members(p["user_id"]):
        try:
            await send_email(
                m["email"], f"👀 Étude ouverte (équipe) · {filename}",
                wrap_html("Étude ouverte — équipe",
                          f"<p><b>{_html.escape(client)}</b> vient d'ouvrir l'étude "
                          f"« {_html.escape(filename)} » d'un membre de votre équipe.</p>"))
        except Exception as e:
            logger.warning(f"pc open team notify fail: {e}")


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


async def _send_deposit_reminder(p: dict, s: dict, pct: float, amount: float) -> None:
    import html as _html
    from engines.emailer import send_email, wrap_html

    branding = await _resolve_branding(p["user_id"])
    company = (branding or {}).get("company_name") or "ConstruPilot"
    filename = p.get("filename") or "permis de construire"
    frontend = (os.getenv("FRONTEND_URL") or "").rstrip("/")
    link = f"{frontend}/etude/{s['sign_token']}" if frontend else None
    await send_email(
        s["to_email"],
        f"Rappel — acompte de {amount} € à régler · {filename}",
        wrap_html(
            "Votre chantier n'attend plus que l'acompte",
            f"<p>Bonjour {_html.escape(s.get('accepted_by') or '')},</p>"
            f"<p>Vous avez accepté l'étude gros œuvre du chantier "
            f"« {_html.escape(filename)} » — il ne reste que l'acompte de "
            f"<b>{pct:g} %</b>, soit <b>{amount} €</b>, à régler par carte "
            "bancaire pour lancer les travaux.</p>"
            f"<p>Le paiement est sécurisé (Stripe) et votre facture d'acompte "
            f"vous sera envoyée automatiquement.<br/>{_html.escape(company)}</p>",
            cta_url=link, cta_label="Régler l'acompte en ligne"))


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

    # Relance d'acompte : étude acceptée mais acompte non versé après N jours
    dep_sent = 0
    dep_candidates = await db.plans_takeoff.find(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "accepted": True,
                                         "deposit_paid": {"$ne": True},
                                         "deposit_reminder_sent": {"$ne": True}}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
         "pc_study.totals": 1, "sent_reports": 1}).to_list(200)
    for p in dep_candidates:
        uid = p["user_id"]
        if uid not in settings_cache:
            settings_cache[uid] = await _load_pc_settings(uid)
        st = settings_cache[uid]
        pct = st.get("deposit_pct")
        pct = DEFAULT_DEPOSIT_PCT if pct is None else float(pct)
        ddays = st.get("deposit_reminder_days")
        ddays = DEFAULT_DEPOSIT_REMINDER_DAYS if ddays is None else int(ddays)
        if pct <= 0 or ddays <= 0:
            continue
        ttc = float((p.get("pc_study", {}).get("totals") or {}).get("ttc") or 0)
        amount = round(ttc * pct / 100.0, 2)
        cutoff = (now - timedelta(days=ddays)).isoformat()
        for s in p.get("sent_reports") or []:
            if (s.get("kind") != "pc_study" or not s.get("accepted")
                    or s.get("deposit_paid") or s.get("deposit_reminder_sent")
                    or not s.get("sign_token") or not s.get("to_email")
                    or amount < 1
                    or (s.get("accepted_at") or "9999") > cutoff):
                continue
            try:
                await _send_deposit_reminder(p, s, pct, amount)
                await db.plans_takeoff.update_one(
                    {"plan_id": p["plan_id"],
                     "sent_reports.sign_token": s["sign_token"]},
                    {"$set": {"sent_reports.$.deposit_reminder_sent": True,
                              "sent_reports.$.deposit_reminder_at": _now()}})
                dep_sent += 1
            except Exception as e:
                logger.warning(f"pc deposit reminder {p['plan_id']}: {e}")
                failed += 1
    return {"sent": sent, "failed": failed, "skipped": skipped,
            "candidates": len(plans), "deposit_reminders": dep_sent,
            "deposit_candidates": len(dep_candidates)}


@pc_router.post("/reminders/run")
async def trigger_pc_reminders(user=Depends(admin_user)) -> dict:
    """Endpoint admin pour lancer manuellement les relances d'études PC."""
    return await _run_pc_reminders()


# ---- Météo chantier (Open-Meteo, sans clé) --------------------------------

@pc_router.get("/weather")
async def pc_weather(city: str, user=Depends(current_user)) -> dict:
    from engines.pc_weather import get_forecast
    if not city.strip():
        raise HTTPException(422, "Ville requise")
    return await get_forecast(city.strip()[:60])


# ---- Réponses négoces sur les bons de commande ----------------------------

class PoResponseIn(BaseModel):
    ref: str = Field(max_length=40)
    status: str = Field(default="en_attente", pattern="^(en_attente|recu|retenu)$")
    quoted_ht: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=300)


@router.post("/{plan_id}/purchase-orders/response")
async def record_po_response(plan_id: str, body: PoResponseIn,
                             user=Depends(current_user)) -> dict:
    await _pc_owner_id(plan_id, user, write=True)
    r = await db.plans_takeoff.update_one(
        {"plan_id": plan_id,
         "sent_reports": {"$elemMatch": {"kind": "purchase_order",
                                         "ref": body.ref}}},
        {"$set": {"sent_reports.$.status": body.status,
                  "sent_reports.$.quoted_ht": body.quoted_ht,
                  "sent_reports.$.response_notes": body.notes,
                  "sent_reports.$.response_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, "Bon de commande introuvable")
    return {"ok": True, "ref": body.ref, "status": body.status}


# ---- Acceptation de l'étude en ligne (page publique /etude/{token}) --------

@pc_router.get("/sign/{token}")
async def get_pc_sign(token: str) -> dict:
    """Vue publique de l'étude pour acceptation client (résumé, sans détails privés)."""
    p = await db.plans_takeoff.find_one(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "sign_token": token}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1, "pc_study": 1,
         "sent_reports.$": 1})
    if not p or not p.get("pc_study"):
        raise HTTPException(404, "Lien invalide ou expiré")
    entry = (p.get("sent_reports") or [{}])[0]
    study = p["pc_study"]
    branding = await _resolve_branding(p["user_id"])
    t = study.get("totals") or {}
    settings = await _load_pc_settings(p["user_id"])
    dep_pct = settings.get("deposit_pct")
    dep_pct = DEFAULT_DEPOSIT_PCT if dep_pct is None else float(dep_pct)
    dep_amount = round((t.get("ttc") or 0) * dep_pct / 100.0, 2) if dep_pct > 0 else 0.0
    return {
        "filename": p.get("filename"),
        "company": (branding or {}).get("company_name"),
        "generated_at": study.get("generated_at"),
        "demandes": (study.get("demandes") or [])[:5],
        # totaux "client" uniquement — jamais le coût de revient ni la marge
        "totals": {k: t.get(k) for k in ("ht", "tva", "ttc", "beton_m3",
                                         "acier_kg", "briques_u")},
        "lots": [{"lot": l["lot"],
                  "total": round(sum(ln["total"] for ln in l["lines"]), 2)}
                 for l in study.get("lots") or []],
        "planning": {"total_days": (study.get("planning") or {}).get("total_days"),
                     "total_weeks": (study.get("planning") or {}).get("total_weeks")},
        "accepted": bool(entry.get("accepted")),
        "accepted_at": entry.get("accepted_at"),
        "accepted_by": entry.get("accepted_by"),
        "deposit": {"pct": dep_pct, "amount": dep_amount,
                    "paid": bool(entry.get("deposit_paid")),
                    "paid_at": entry.get("deposit_at"),
                    "paid_amount": entry.get("deposit_amount"),
                    "invoice_no": entry.get("deposit_invoice_no")},
    }


class PcAcceptIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)


@pc_router.post("/sign/{token}/accept")
async def accept_pc_study(token: str, body: PcAcceptIn) -> dict:
    p = await db.plans_takeoff.find_one(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "sign_token": token}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1, "sent_reports.$": 1})
    if not p:
        raise HTTPException(404, "Lien invalide ou expiré")
    entry = (p.get("sent_reports") or [{}])[0]
    if entry.get("accepted"):
        return {"ok": True, "already": True, "accepted_at": entry.get("accepted_at")}
    now = _now()
    await db.plans_takeoff.update_one(
        {"sent_reports.sign_token": token},
        {"$set": {"sent_reports.$.accepted": True,
                  "sent_reports.$.accepted_at": now,
                  "sent_reports.$.accepted_by": body.name.strip(),
                  "sent_reports.$.opened": True,
                  "sent_reports.$.opened_at": entry.get("opened_at") or now}})
    try:
        import html as _html
        from engines.emailer import send_email, wrap_html
        u = await db.users.find_one({"user_id": p["user_id"]},
                                    {"_id": 0, "email": 1})
        filename = p.get("filename") or "permis de construire"
        if u and u.get("email"):
            await send_email(
                u["email"],
                f"✅ Étude acceptée par {body.name.strip()} · {filename}",
                wrap_html("Étude acceptée !",
                          f"<p><b>{_html.escape(body.name.strip())}</b> vient d'accepter "
                          f"l'étude gros œuvre du chantier « {_html.escape(filename)} ». "
                          "Vous pouvez lancer les commandes matériaux.</p>"))
        for m in await _team_members(p["user_id"]):
            await send_email(
                m["email"],
                f"✅ Étude acceptée (équipe) · {filename}",
                wrap_html("Étude acceptée — équipe",
                          f"<p><b>{_html.escape(body.name.strip())}</b> vient d'accepter "
                          f"l'étude « {_html.escape(filename)} » d'un membre de votre "
                          "équipe. Retrouvez-la dans le tableau de bord PC.</p>"))
    except Exception as e:
        logger.warning(f"pc accept notify fail {token}: {e}")
    return {"ok": True, "accepted_at": now}


# ---- Acompte en ligne (Stripe Checkout, page publique) ---------------------

class PcDepositCheckoutIn(BaseModel):
    origin_url: str = Field(max_length=200)


@pc_router.post("/sign/{token}/deposit/checkout")
async def pc_deposit_checkout(token: str, body: PcDepositCheckoutIn) -> dict:
    """Crée la session Stripe pour l'acompte (public — lien de signature)."""
    import stripe
    p = await db.plans_takeoff.find_one(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "sign_token": token}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
         "pc_study.totals": 1, "sent_reports.$": 1})
    if not p or not p.get("pc_study"):
        raise HTTPException(404, "Lien invalide ou expiré")
    entry = (p.get("sent_reports") or [{}])[0]
    if not entry.get("accepted"):
        raise HTTPException(400, "Acceptez d'abord l'étude avant de verser l'acompte")
    if entry.get("deposit_paid"):
        raise HTTPException(400, "L'acompte a déjà été réglé — merci !")
    settings = await _load_pc_settings(p["user_id"])
    pct = settings.get("deposit_pct")
    pct = DEFAULT_DEPOSIT_PCT if pct is None else float(pct)
    if pct <= 0:
        raise HTTPException(400, "Le paiement d'acompte en ligne est désactivé")
    ttc = float((p["pc_study"].get("totals") or {}).get("ttc") or 0)
    amount_cents = int(round(ttc * pct))  # € TTC × pct % → centimes
    if amount_cents < 100:
        raise HTTPException(400, "Montant d'acompte invalide")
    origin = body.origin_url.rstrip("/")
    filename = (p.get("filename") or "étude gros œuvre")[:80]
    try:
        session = stripe.checkout.Session.create(
            line_items=[{"price_data": {
                "currency": "eur",
                "product_data": {"name": f"Acompte {pct:g} % — {filename}"},
                "unit_amount": amount_cents}, "quantity": 1}],
            mode="payment",
            success_url=f"{origin}/etude/{token}?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/etude/{token}",
            metadata={"type": "pc_deposit", "sign_token": token,
                      "plan_id": p["plan_id"]})
    except Exception:
        logger.exception("stripe pc deposit checkout")
        raise HTTPException(502, "Paiement indisponible — réessayez plus tard")
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": p["user_id"], "plan_id": p["plan_id"],
        "sign_token": token, "type": "pc_deposit", "amount_cents": amount_cents,
        "currency": "eur", "mode": "payment", "status": "initiated",
        "payment_status": "pending", "created_at": _now(), "updated_at": _now()})
    return {"url": session.url, "session_id": session.id,
            "amount": round(amount_cents / 100.0, 2)}


async def _apply_pc_deposit(rec: dict) -> None:
    """Marque l'acompte payé (idempotent), génère la facture d'acompte
    et l'envoie au client + notifie le pro et son équipe."""
    token = rec.get("sign_token")
    amount = round((rec.get("amount_cents") or 0) / 100.0, 2)
    paid_at = _now()
    r = await db.plans_takeoff.update_one(
        {"sent_reports": {"$elemMatch": {"sign_token": token,
                                         "deposit_paid": {"$ne": True}}}},
        {"$set": {"sent_reports.$.deposit_paid": True,
                  "sent_reports.$.deposit_amount": amount,
                  "sent_reports.$.deposit_at": paid_at,
                  "sent_reports.$.deposit_session_id": rec.get("session_id")}})
    if not r.modified_count:
        return
    try:
        import html as _html
        from engines.emailer import send_email, send_email_with_pdf, wrap_html
        p = await db.plans_takeoff.find_one(
            {"sent_reports.sign_token": token},
            {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
             "pc_study.totals": 1, "sent_reports": 1})
        if not p:
            return
        entry = next((s for s in p.get("sent_reports") or []
                      if s.get("sign_token") == token), {})
        filename = p.get("filename") or "permis de construire"

        # Facture d'acompte acquittée
        invoice_no = await _next_invoice_no(p["user_id"])
        await db.plans_takeoff.update_one(
            {"sent_reports.sign_token": token},
            {"$set": {"sent_reports.$.deposit_invoice_no": invoice_no}})
        settings = await _load_pc_settings(p["user_id"])
        pct = settings.get("deposit_pct")
        pct = DEFAULT_DEPOSIT_PCT if pct is None else float(pct)
        branding = await _resolve_branding(p["user_id"])
        pdf = None
        try:
            pdf = build_deposit_invoice_pdf(p, branding, {
                "invoice_no": invoice_no, "amount": amount, "pct": pct,
                "total_ttc": (p.get("pc_study", {}).get("totals") or {}).get("ttc"),
                "paid_at": paid_at, "session_id": rec.get("session_id"),
                "client_name": entry.get("accepted_by"),
                "client_email": entry.get("to_email")})
        except Exception:
            logger.exception("pc deposit invoice pdf")

        # Email client : facture jointe
        if entry.get("to_email") and pdf:
            company = (branding or {}).get("company_name") or "ConstruPilot"
            await send_email_with_pdf(
                entry["to_email"],
                f"Votre facture d'acompte {invoice_no} · {filename}",
                wrap_html("Facture d'acompte — merci !",
                          f"<p>Bonjour {_html.escape(entry.get('accepted_by') or '')},</p>"
                          f"<p>Nous avons bien reçu votre acompte de <b>{amount} €</b> "
                          f"pour le chantier « {_html.escape(filename)} ». "
                          f"Votre facture d'acompte <b>{invoice_no}</b> est en pièce "
                          "jointe.</p>"
                          f"<p>À très vite pour le lancement des travaux !<br/>"
                          f"{_html.escape(company)}</p>"),
                pdf, filename=f"facture-acompte-{invoice_no}.pdf")

        # Notification pro + équipe (facture jointe si dispo)
        html = wrap_html(
            "Acompte encaissé",
            f"<p>Bonne nouvelle : un acompte de <b>{amount} €</b> vient d'être réglé "
            f"par carte pour l'étude « {_html.escape(filename)} ». "
            f"Facture <b>{invoice_no}</b> envoyée au client — "
            "vous pouvez lancer le chantier !</p>")
        subject = f"💶 Acompte de {amount} € reçu · {filename}"
        u = await db.users.find_one({"user_id": p["user_id"]}, {"_id": 0, "email": 1})
        if u and u.get("email"):
            if pdf:
                await send_email_with_pdf(u["email"], subject, html, pdf,
                                          filename=f"facture-acompte-{invoice_no}.pdf")
            else:
                await send_email(u["email"], subject, html)
        for m in await _team_members(p["user_id"]):
            await send_email(m["email"], f"💶 Acompte reçu (équipe) · {filename}", html)
    except Exception as e:
        logger.warning(f"pc deposit notify fail {token}: {e}")


@pc_router.get("/sign/{token}/deposit/invoice")
async def pc_deposit_invoice(token: str):
    """Facture d'acompte en PDF (public — accessible depuis la page de signature)."""
    p = await db.plans_takeoff.find_one(
        {"sent_reports": {"$elemMatch": {"kind": "pc_study", "sign_token": token}}},
        {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1,
         "pc_study.totals": 1, "sent_reports.$": 1})
    if not p:
        raise HTTPException(404, "Lien invalide ou expiré")
    entry = (p.get("sent_reports") or [{}])[0]
    if not entry.get("deposit_paid") or not entry.get("deposit_invoice_no"):
        raise HTTPException(400, "Aucun acompte réglé pour cette étude")
    settings = await _load_pc_settings(p["user_id"])
    pct = settings.get("deposit_pct")
    pct = DEFAULT_DEPOSIT_PCT if pct is None else float(pct)
    branding = await _resolve_branding(p["user_id"])
    pdf = build_deposit_invoice_pdf(p, branding, {
        "invoice_no": entry["deposit_invoice_no"],
        "amount": entry.get("deposit_amount") or 0, "pct": pct,
        "total_ttc": (p.get("pc_study", {}).get("totals") or {}).get("ttc"),
        "paid_at": entry.get("deposit_at"),
        "session_id": entry.get("deposit_session_id"),
        "client_name": entry.get("accepted_by"),
        "client_email": entry.get("to_email")})
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="facture-acompte-'
                 f'{entry["deposit_invoice_no"]}.pdf"'})


@pc_router.get("/deposit/status/{session_id}")
async def pc_deposit_status(session_id: str) -> dict:
    """Statut public du paiement d'acompte (polling au retour de Stripe)."""
    rec = await db.payment_transactions.find_one(
        {"session_id": session_id, "type": "pc_deposit"}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Session inconnue")
    if rec.get("payment_status") != "paid":
        import stripe
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" or s.status == "complete":
                upd = await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid",
                              "stripe_payment_intent_id": s.payment_intent,
                              "updated_at": _now()}})
                rec = await db.payment_transactions.find_one(
                    {"session_id": session_id}, {"_id": 0})
                if upd.modified_count:
                    await _apply_pc_deposit(rec)
            elif s.status == "expired":
                await db.payment_transactions.update_one(
                    {"session_id": session_id},
                    {"$set": {"status": "expired", "payment_status": "expired",
                              "updated_at": _now()}})
                rec["payment_status"] = "expired"
        except Exception as e:
            logger.warning(f"pc deposit status poll {session_id}: {e}")
    return {"session_id": session_id, "status": rec.get("status"),
            "payment_status": rec.get("payment_status"),
            "amount": round((rec.get("amount_cents") or 0) / 100.0, 2)}


# ---- Tableau de bord des études PC ----------------------------------------

def _study_row(p: dict) -> dict:
    sends = [s for s in p.get("sent_reports") or [] if s.get("kind") == "pc_study"]
    orders = [s for s in p.get("sent_reports") or []
              if s.get("kind") == "purchase_order"]
    status = "générée"
    if sends:
        status = "envoyée"
    if any(s.get("reminder_sent") for s in sends):
        status = "relancée"
    if any(s.get("opened") for s in sends):
        status = "ouverte"
    if any(s.get("accepted") for s in sends):
        status = "acceptée"
    if any(s.get("deposit_paid") for s in sends):
        status = "acompte versé"
    st = p.get("pc_study") or {}
    t = st.get("totals") or {}
    return {
        "plan_id": p["plan_id"], "filename": p.get("filename"),
        "generated_at": st.get("generated_at"),
        "ttc": t.get("ttc"), "beton_m3": t.get("beton_m3"),
        "acier_kg": t.get("acier_kg"),
        "total_days": (st.get("planning") or {}).get("total_days"),
        "custom_pricing": bool(st.get("custom_pricing")),
        "status": status, "sends": len(sends), "orders": len(orders),
        "last_sent_to": sends[-1].get("to_email") if sends else None,
        "deposit_amount": round(sum(s.get("deposit_amount") or 0 for s in sends), 2),
    }


_DASH_PROJ = {"_id": 0, "plan_id": 1, "filename": 1, "user_id": 1,
              "sent_reports": 1, "pc_study.totals": 1,
              "pc_study.generated_at": 1, "pc_study.custom_pricing": 1,
              "pc_study.planning.total_days": 1}


@pc_router.get("/dashboard")
async def pc_dashboard(user=Depends(current_user)) -> dict:
    uids = {user["user_id"]}
    names: dict[str, str] = {}
    org = user.get("organization_id")
    if org:
        rows = await db.users.find(
            {"organization_id": org},
            {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(200)
        share = {s["user_id"]: s.get("team_share")
                 for s in await db.pc_settings.find(
                     {"user_id": {"$in": [r["user_id"] for r in rows]}},
                     {"_id": 0, "user_id": 1, "team_share": 1}).to_list(200)}
        for r in rows:
            if r["user_id"] == user["user_id"] or share.get(r["user_id"]) is not False:
                uids.add(r["user_id"])
                names[r["user_id"]] = r.get("name") or r.get("email") or ""
    plans = await db.plans_takeoff.find(
        {"user_id": {"$in": list(uids)}, "pc_study": {"$exists": True}},
        _DASH_PROJ).to_list(200)
    studies = []
    for p in plans:
        row = _study_row(p)
        row["is_own"] = p["user_id"] == user["user_id"]
        row["owner_name"] = None if row["is_own"] else names.get(p["user_id"])
        studies.append(row)
    studies.sort(key=lambda x: x.get("generated_at") or "", reverse=True)
    return {"studies": studies}


# ---- Rapport hebdo automatique (email du lundi) ----------------------------

async def _send_weekly_pc_report_email(u: dict, rows: list[dict]) -> None:
    import html as _html
    from engines.emailer import send_email, wrap_html

    accepted = [r for r in rows if r["status"] in ("acceptée", "acompte versé")]
    opened = [r for r in rows if r["status"] == "ouverte"]
    to_chase = [r for r in rows if r["status"] in ("envoyée", "relancée")]
    pipeline = round(sum(r.get("ttc") or 0 for r in rows), 2)
    deposits = round(sum(r.get("deposit_amount") or 0 for r in rows), 2)

    def _eur(x: float) -> str:
        return f"{x:,.0f}".replace(",", " ") + " €"

    trs = "".join(
        f'<tr><td style="padding:6px;border-bottom:1px solid #eee">'
        f'{_html.escape((r.get("filename") or r["plan_id"])[:60])}</td>'
        f'<td style="padding:6px;border-bottom:1px solid #eee">{r["status"]}</td>'
        f'<td style="padding:6px;border-bottom:1px solid #eee;text-align:right">'
        f'{_eur(r.get("ttc") or 0)}</td>'
        f'<td style="padding:6px;border-bottom:1px solid #eee">'
        f'{_html.escape(r.get("last_sent_to") or "—")}</td></tr>'
        for r in rows[:20])
    frontend = (os.getenv("FRONTEND_URL") or "").rstrip("/")
    cta = (f'<p style="margin:18px 0"><a href="{frontend}/etudes-pc" '
           'style="background:#FF5A00;color:#ffffff;padding:11px 24px;'
           'border-radius:4px;text-decoration:none;font-weight:bold">'
           "Ouvrir le tableau de bord PC</a></p>") if frontend else ""
    name = _html.escape(u.get("name") or "")
    html = wrap_html(
        "Rapport hebdo — Études PC",
        f"<p>Bonjour {name},</p>"
        f"<p>Le point du lundi sur vos <b>{len(rows)} études PC</b> :</p>"
        f"<ul><li><b>{len(accepted)}</b> acceptée(s)</li>"
        f"<li><b>{len(opened)}</b> ouverte(s) par le client mais pas encore "
        "signée(s) — à rappeler</li>"
        f"<li><b>{len(to_chase)}</b> envoyée(s) sans réponse — à relancer</li>"
        f"<li>Pipeline total : <b>{_eur(pipeline)} TTC</b>"
        + (f" · acomptes encaissés : <b>{_eur(deposits)}</b>" if deposits else "")
        + "</li></ul>"
        '<table style="width:100%;border-collapse:collapse;font-size:13px">'
        '<tr><th style="text-align:left;padding:6px">Chantier</th>'
        '<th style="text-align:left;padding:6px">Statut</th>'
        '<th style="text-align:right;padding:6px">TTC</th>'
        '<th style="text-align:left;padding:6px">Client</th></tr>'
        f"{trs}</table>{cta}")
    await send_email(
        u["email"],
        f"📊 Rapport hebdo PC — {len(rows)} études, {len(to_chase)} à relancer",
        html)


async def _run_pc_weekly_reports() -> dict:
    """Job du lundi : un email récapitulatif des études PC à chaque professionnel."""
    plans = await db.plans_takeoff.find(
        {"pc_study": {"$exists": True}}, _DASH_PROJ).to_list(500)
    by_user: dict[str, list[dict]] = {}
    for p in plans:
        by_user.setdefault(p["user_id"], []).append(p)
    sent, failed, skipped = 0, 0, 0
    for uid, ps in by_user.items():
        settings = await _load_pc_settings(uid)
        if settings.get("weekly_report") is False:
            skipped += 1
            continue
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "email": 1, "name": 1})
        if not u or not u.get("email"):
            skipped += 1
            continue
        try:
            await _send_weekly_pc_report_email(u, [_study_row(p) for p in ps])
            sent += 1
        except Exception as e:
            logger.warning(f"pc weekly report {uid}: {e}")
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": skipped,
            "users": len(by_user)}


@pc_router.post("/weekly-report/run")
async def trigger_pc_weekly_reports(user=Depends(admin_user)) -> dict:
    """Endpoint admin : lance le rapport hebdo pour tous les pros."""
    return await _run_pc_weekly_reports()


@pc_router.post("/weekly-report/send-me")
async def send_my_weekly_report(user=Depends(current_user)) -> dict:
    """Envoie immédiatement son rapport hebdo à l'utilisateur courant."""
    plans = await db.plans_takeoff.find(
        {"user_id": user["user_id"], "pc_study": {"$exists": True}},
        _DASH_PROJ).to_list(200)
    if not plans:
        raise HTTPException(400, "Aucune étude PC à résumer")
    if not user.get("email"):
        raise HTTPException(400, "Aucun email sur votre compte")
    try:
        await _send_weekly_pc_report_email(user, [_study_row(p) for p in plans])
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Envoi de l'email impossible — réessayez plus tard")
    return {"ok": True, "studies": len(plans), "sent_to": user["email"]}
