"""PDF exports + Quote sending + Templates + Multi-quote + Tracking +
Notifications + Signature client + Client portal + Reminders scheduler.

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user, current_user
from engines import geometry as G

from routes.plans_common import (
    QUOTE_SEND_PREFIX, SIG_TOKEN_PREFIX,
    _build_quote_and_pdf, _now, _resolve_branding,
    build_client_portal_token, quote_router, router,
)

logger = logging.getLogger(__name__)

REMINDER_DELAY_DAYS = 5


# ============ PDF EXPORT MÉTRÉ ============

def _aggregate_export_levels(rooms: list[dict], pages: list[dict]) -> list[dict]:
    """Reconstitue les niveaux à partir des pages+rooms (comme /takeoff)."""
    page_level = {pg.get("index"): {"index": pg.get("level_index"),
                                     "label": pg.get("level_label")}
                  for pg in pages}
    by_level: dict = {}
    for r in rooms:
        info = page_level.get(r.get("page_index"), {"index": None, "label": None})
        key = f"{info['index'] if info['index'] is not None else 'none'}"
        bucket = by_level.setdefault(key, {
            "level_index": info["index"],
            "level_label": info["label"] or "Sans niveau",
            "rooms": [], "totals": {"floor_m2": 0, "walls_net_m2": 0, "perimeter_m": 0}})
        bucket["rooms"].append(r)
        bucket["totals"]["floor_m2"] += r.get("surface_m2", 0)
        bucket["totals"]["walls_net_m2"] += r.get("wall_area_net_m2", 0)
        bucket["totals"]["perimeter_m"] += r.get("perimeter_m", 0)
    for b in by_level.values():
        for k in b["totals"]:
            b["totals"][k] = round(b["totals"][k], 2)
    return sorted(by_level.values(),
                  key=lambda x: (x["level_index"] is None,
                                 x["level_index"] if x["level_index"] is not None else 99))


def _takeoff_materials(rooms: list[dict], floor_material: str,
                       totals: dict) -> dict:
    """Compute the metric materials block used by the takeoff PDF."""
    doors_est = 2 * len(rooms)  # heuristique
    return {
        "floor": G.floor_quantity(totals["floor_m2"], floor_material),
        "paint": G.paint_liters(totals["walls_net_m2"] + totals["ceiling_m2"]),
        "placo": G.placo_quantity(totals["walls_net_m2"] + totals["ceiling_m2"]),
        "skirting": G.skirting_length_m(totals["perimeter_m"], doors_est * 0.9),
    }


@router.get("/{plan_id}/pdf")
async def export_takeoff_pdf(plan_id: str, include_materials: bool = True,
                              floor_material: str = "parquet",
                              user=Depends(current_user)):
    """Génère et renvoie le PDF de métré du plan (streaming binaire)."""
    from fastapi.responses import Response
    from engines.pdf_takeoff import build_takeoff_pdf

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages.image_png_b64": 0}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")

    rooms = p.get("rooms") or []
    pages = p.get("pages") or []
    totals = {
        "floor_m2": round(sum(r.get("surface_m2", 0) for r in rooms), 2),
        "ceiling_m2": round(sum(r.get("ceiling_area_m2", 0) for r in rooms), 2),
        "walls_gross_m2": round(sum(r.get("wall_area_gross_m2", 0) for r in rooms), 2),
        "walls_net_m2": round(sum(r.get("wall_area_net_m2", 0) for r in rooms), 2),
        "perimeter_m": round(sum(r.get("perimeter_m", 0) for r in rooms), 2),
    }

    takeoff = {
        "room_count": len(rooms), "rooms": rooms,
        "levels": _aggregate_export_levels(rooms, pages),
        "totals": totals,
    }
    materials = _takeoff_materials(rooms, floor_material, totals) if (include_materials and rooms) else None
    plan_light = {"plan_id": p.get("plan_id"), "filename": p.get("filename"),
                  "page_count": p.get("page_count", 1)}
    branding = await _resolve_branding(user["user_id"])

    # Vague B (iter58) — enrichir le PDF avec les modèles appliqués aux pièces
    preset_ids = list({r.get("preset_id") for r in rooms if r.get("preset_id")})
    presets_by_id: dict = {}
    if preset_ids:
        async for preset in db.tool_presets.find(
            {"preset_id": {"$in": preset_ids}, "user_id": user["user_id"]}, {"_id": 0}
        ):
            presets_by_id[preset["preset_id"]] = preset

    pdf_bytes = build_takeoff_pdf(plan_light, takeoff, materials,
                                   branding=branding, presets_by_id=presets_by_id)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="metre-{plan_id}.pdf"'}
    )


# ============ PDF DEVIS ============

@router.get("/{plan_id}/quote-pdf")
async def export_quote_pdf(plan_id: str, finish: str = "std",
                            floor_material: str = "carrelage",
                            include_paint: bool = True, include_placo: bool = True,
                            include_floor: bool = True, include_skirting: bool = True,
                            user=Depends(current_user)):
    """Génère un PDF Devis complet : main d'œuvre + matériaux pré-remplis depuis le takeoff."""
    from fastapi.responses import Response
    _q, pdf_bytes = await _build_quote_and_pdf(
        plan_id, user["user_id"], finish, floor_material,
        include_paint, include_placo, include_floor, include_skirting)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="devis-{plan_id}.pdf"'}
    )


# ============ SEND QUOTE (email + tracking + optional TVA + optional video) ============

class SendQuoteIn(BaseModel):
    client_email: str
    client_name: str | None = None
    client_address: str | None = None
    work_address: str | None = None
    message: str | None = None
    subject: str | None = None
    intro: str | None = None
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True
    cc_self: bool = True
    include_tva_attestation: bool = False
    attach_latest_video: bool = False


def _build_send_quote_html(*, hello: str, intro_html: str, custom_html: str,
                          ttc: float, portal_url: str, company: str, contact: str,
                          pixel_tag: str) -> str:
    """Assemble the HTML body of the devis email."""
    return (
        f"<p>{hello}</p>"
        f"{intro_html}"
        f"{custom_html}"
        f"<div style='background:#FF5A00;color:white;padding:16px 22px;border-radius:6px;"
        f"font-size:18px;font-weight:700;text-align:center;letter-spacing:1px'>"
        f"Total TTC : {ttc:,.2f} €</div>"
        f"<p style='margin-top:16px'>Ce document est un devis estimatif indicatif "
        f"(TVA 10 % rénovation logement &gt; 2 ans). Nous restons à votre disposition "
        f"pour toute question ou visite technique.</p>"
        f"<div style='margin-top:24px;padding:16px;background:#f8fafc;border-radius:6px;"
        f"border-left:3px solid #FF5A00'>"
        f"<p style='margin:0 0 6px;font-weight:700;font-size:13px'>📁 Votre espace devis</p>"
        f"<p style='margin:0 0 10px;font-size:12px;color:#64748B'>"
        f"Retrouvez tous vos devis reçus (celui-ci et les précédents) "
        f"dans votre espace personnel sécurisé :</p>"
        f"<a href='{portal_url}' style='color:#FF5A00;font-weight:700;text-decoration:none;font-size:13px'>"
        f"→ Ouvrir mon espace devis</a>"
        f"</div>"
        f"<p style='color:#666;font-size:12px;margin-top:24px'>"
        f"{company}<br/>{contact}</p>"
        f"{pixel_tag}"
    )


def _build_tva_attachment(quote: dict, body: SendQuoteIn, company: str,
                          contact: str, branding: dict) -> dict:
    """Build the TVA attestation PDF attachment payload."""
    from engines.pdf_takeoff import build_tva_attestation_pdf
    work_desc_parts = [li["name"] for li in quote.get("line_items", [])]
    work_desc = " ; ".join(work_desc_parts) if work_desc_parts else "Travaux de rénovation"
    client_addr = (body.client_address or "").strip()
    work_addr = (body.work_address or client_addr or "").strip()
    tva_pdf = build_tva_attestation_pdf(
        client_name=body.client_name or "",
        client_address=client_addr,
        work_address=work_addr,
        work_description=work_desc,
        company_name=company,
        company_address=contact or "",
        branding=branding, tva_rate=quote.get("tva_rate", 0.10),
    )
    return {
        "filename": f"attestation-tva-{quote['plan_id']}.pdf",
        "content": tva_pdf,
        "content_type": "application/pdf",
    }


async def _maybe_attach_latest_video(plan_id: str, user_id: str) -> tuple[dict | None, str | None]:
    """Return (attachment_dict, video_id) if a recent MP4 fits under 20 MB — else (None, None)."""
    latest = await db.plan_videos_3d.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        sort=[("created_at", -1)],
    )
    if not latest:
        return None, None
    from engines.video_tour import get_video_path
    vpath = get_video_path(latest.get("video_id", ""))
    if not vpath:
        return None, None
    try:
        mp4_bytes = vpath.read_bytes()
    except Exception as e:
        logger.warning(f"failed to read video: {e}")
        return None, None
    if len(mp4_bytes) > 20 * 1024 * 1024:
        logger.warning(f"video too large to attach: {len(mp4_bytes)} bytes")
        return None, None
    return ({
        "filename": f"tour-3d-{plan_id}.mp4",
        "content": mp4_bytes,
        "content_type": "video/mp4",
    }, latest["video_id"])


@router.post("/{plan_id}/send-quote")
async def send_quote(plan_id: str, body: SendQuoteIn, user=Depends(current_user)):
    """Envoie le PDF Devis directement au client par email + copie au sender + log."""
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", body.client_email or ""):
        raise HTTPException(400, "Email client invalide.")

    quote, pdf_bytes = await _build_quote_and_pdf(
        plan_id, user["user_id"], body.finish, body.floor_material,
        body.include_paint, body.include_placo, body.include_floor, body.include_skirting)

    if body.include_tva_attestation and not (body.client_address or "").strip():
        raise HTTPException(400,
            "Adresse client requise pour joindre l'attestation TVA.")

    branding = await _resolve_branding(user["user_id"]) or {}
    sender_u = await db.users.find_one({"user_id": user["user_id"]},
                                         {"_id": 0, "name": 1, "email": 1})
    company = branding.get("company_name") or (sender_u or {}).get("name") or "ConstruPilot"
    contact = branding.get("contact_line") or ""

    ttc = quote.get("total_ttc", 0)
    finish_label = {"eco": "Éco", "std": "Standard", "premium": "Premium"}.get(
        body.finish, "Standard")

    from engines.emailer import send_email_with_pdf, wrap_html
    hello = f"Bonjour {body.client_name}," if body.client_name else "Bonjour,"
    intro_html = (f"<p>{body.intro}</p>" if body.intro
                   else "<p>Veuillez trouver ci-joint votre <b>devis estimatif</b>"
                        f" ({finish_label}) élaboré depuis votre plan.</p>")
    custom_html = f"<p>{body.message}</p>" if body.message else ""
    log_id = QUOTE_SEND_PREFIX + secrets.token_hex(6)

    backend_public = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("FRONTEND_URL") or ""
    pixel_tag = (f'<img src="{backend_public}/api/quotes/track/open/{log_id}" '
                 f'width="1" height="1" alt="" style="display:block" />'
                 if backend_public else "")
    portal_token = build_client_portal_token(body.client_email or "")
    portal_url = (f"{os.getenv('FRONTEND_URL', 'https://construpilot.fr').rstrip('/')}"
                  f"/mes-devis?token={portal_token}")

    inner = _build_send_quote_html(
        hello=hello, intro_html=intro_html, custom_html=custom_html,
        ttc=ttc, portal_url=portal_url, company=company, contact=contact,
        pixel_tag=pixel_tag,
    )
    subject = (body.subject or "").strip()[:180] or f"Devis · {company}"
    html = wrap_html(subject, inner)

    extra_attachments: list[dict] = []
    if body.include_tva_attestation:
        extra_attachments.append(_build_tva_attachment(quote, body, company, contact, branding))
        # Ajoute la mention dans le message
        inner_with_att = inner.replace(
            "Ce document est un devis estimatif indicatif",
            "Vous trouverez également jointe l'<b>attestation TVA à taux réduit</b> "
            "à nous retourner signée avant la facturation. Ce document est un "
            "devis estimatif indicatif"
        )
        html = wrap_html(subject, inner_with_att)

    attached_video_id: str | None = None
    if body.attach_latest_video:
        video_att, attached_video_id = await _maybe_attach_latest_video(
            plan_id, user["user_id"])
        if video_att:
            extra_attachments.append(video_att)
            html = html.replace(
                "Total TTC :",
                "<p style='margin:0 0 12px;font-size:13px;color:#FF5A00;"
                "font-weight:700'>🎬 Un tour vidéo 3D de votre projet est "
                "joint à cet email — regardez-le pour visualiser votre "
                "chantier avant travaux.</p>Total TTC :",
                1,
            )

    email_status = "sent"
    email_id = None
    error = None
    try:
        cc = (sender_u or {}).get("email") if body.cc_self else None
        res = await send_email_with_pdf(body.client_email, subject,
                                          html, pdf_bytes,
                                          filename=f"devis-{plan_id}.pdf", cc=cc,
                                          extra_attachments=extra_attachments)
        email_id = res.get("id")
    except Exception as e:
        logger.warning(f"Send quote email failed: {e}")
        email_status = "failed"
        error = str(e)

    log = {
        "log_id": log_id,
        "plan_id": plan_id, "user_id": user["user_id"],
        "client_email": body.client_email, "client_name": body.client_name,
        "client_address": body.client_address, "work_address": body.work_address,
        "cc": (sender_u or {}).get("email") if body.cc_self else None,
        "total_ttc": ttc, "finish": body.finish, "floor_material": body.floor_material,
        "subject": subject, "intro": body.intro, "message": body.message,
        "include_tva_attestation": body.include_tva_attestation,
        "attach_latest_video": body.attach_latest_video,
        "attached_video_id": attached_video_id,
        "email_status": email_status, "email_id": email_id, "error": error,
        "created_at": _now(),
        "opened": False, "open_count": 0,
        "signed": False,
        "reminder_sent": False,
    }
    await db.quote_sends.insert_one(log)
    return {"ok": email_status == "sent", "email_status": email_status,
            "email_id": email_id, "log_id": log["log_id"], "total_ttc": ttc}


@router.get("/{plan_id}/quote-sends")
async def list_quote_sends(plan_id: str, user=Depends(current_user)):
    """Historique des envois de devis pour ce plan."""
    docs = await db.quote_sends.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"plan_id": plan_id, "sends": docs}


# ============ WORKFLOW : Plan → Estimation → Devis ============

class TakeoffEstimateIn(BaseModel):
    project_type: str = "renovation_complete"
    finish_level: str = "standard"
    country: str = "FR"
    region: str | None = "idf"
    building_type: str = "maison"
    condition: str = "bon"
    construction_year: int | None = None


@router.post("/{plan_id}/estimate-from-takeoff")
async def estimate_from_takeoff(plan_id: str, body: TakeoffEstimateIn,
                                 user=Depends(current_user)):
    """Envoie automatiquement la surface mesurée du plan à l'estimateur."""
    from engines.estimation import estimate as estim_run

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    if not rooms:
        raise HTTPException(400, "Aucune pièce mesurée sur ce plan.")

    surface = round(sum(r.get("surface_m2", 0) for r in rooms), 2)
    if surface <= 0:
        raise HTTPException(400, "Surface mesurée invalide.")

    est = estim_run(
        project_type=body.project_type, surface=surface,
        finish=body.finish_level, country=body.country, region=body.region,
        building_type=body.building_type, condition=body.condition,
        construction_year=body.construction_year,
    )

    proj = {
        "project_id": "proj_" + secrets.token_hex(6),
        "user_id": user["user_id"], "plan_id": plan_id,
        "name": p.get("filename") or "Projet depuis plan",
        "source": "plan_takeoff",
        "surface": surface, "room_count": len(rooms),
        "estimation": est,
        "created_at": _now(),
    }
    await db.projects.insert_one(proj)

    return {"ok": True, "project_id": proj["project_id"],
            "plan_id": plan_id, "surface_m2": surface,
            "room_count": len(rooms),
            "estimation": est,
            "is_renovation": "renovation" in body.project_type.lower()}


# ============ REMINDERS ============

def _build_reminder_html(*, hello: str, ttc: float, sign_url: str,
                        portal_url: str, company: str) -> str:
    return (
        f"<p>{hello}</p>"
        f"<p>Nous nous permettons un petit rappel : votre devis "
        f"(<b>{ttc:,.2f} € TTC</b>) est toujours disponible "
        f"pour votre signature.</p>"
        f"<p>Il vous suffit d'un clic pour valider :</p>"
        f"<p style='text-align:center;margin:24px 0'>"
        f"<a href='{sign_url}' style='background:#FF5A00;color:white;"
        f"padding:14px 28px;border-radius:6px;text-decoration:none;"
        f"font-weight:700;font-size:16px'>Signer le devis</a></p>"
        f"<p style='text-align:center;margin:8px 0 24px'>"
        f"<a href='{portal_url}' style='color:#64748B;font-size:12px;"
        f"text-decoration:underline'>Voir tous mes devis dans mon espace</a></p>"
        f"<p>Nous restons à votre disposition pour toute question ou ajustement.</p>"
        f"<p style='color:#666;font-size:12px;margin-top:24px'>"
        f"Cordialement,<br/>{company}</p>"
    )


async def _ensure_signature_token(log: dict) -> str:
    """Return an existing signature token or create+persist a new one."""
    token = log.get("signature_token")
    if token:
        return token
    token = SIG_TOKEN_PREFIX + secrets.token_urlsafe(18)
    await db.quote_sends.update_one({"log_id": log["log_id"]},
        {"$set": {"signature_token": token,
                  "signature_token_created_at": _now()}})
    return token


async def _send_single_reminder(c: dict) -> None:
    from engines.emailer import send_email, wrap_html
    branding = await _resolve_branding(c["user_id"]) or {}
    company = branding.get("company_name") or "ConstruPilot"
    hello = f"Bonjour {c['client_name']}," if c.get("client_name") else "Bonjour,"
    token = await _ensure_signature_token(c)
    sign_url = f"{os.getenv('FRONTEND_URL', '')}/sign/{token}"
    portal_token = build_client_portal_token(c.get("client_email") or "")
    portal_url = (f"{os.getenv('FRONTEND_URL', 'https://construpilot.fr').rstrip('/')}"
                  f"/mes-devis?token={portal_token}")
    inner = _build_reminder_html(hello=hello, ttc=c.get("total_ttc", 0),
                                  sign_url=sign_url, portal_url=portal_url,
                                  company=company)
    await send_email(c["client_email"], f"Rappel : votre devis · {company}",
                      wrap_html(f"Rappel devis · {company}", inner))
    await db.quote_sends.update_one({"log_id": c["log_id"]},
        {"$set": {"reminder_sent": True, "reminder_sent_at": _now()}})
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(5),
        "user_id": c["user_id"], "type": "reminder_sent",
        "log_id": c["log_id"],
        "message": f"Rappel envoyé à {c['client_email']} (devis non signé "
                   f"depuis {REMINDER_DELAY_DAYS} j).",
        "created_at": _now(), "read": False,
    })


async def _run_reminders() -> dict:
    """Envoie un rappel aux devis ouverts mais non signés depuis > 5 jours."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=REMINDER_DELAY_DAYS)).isoformat()
    candidates = await db.quote_sends.find(
        {"opened": True, "signed": False, "reminder_sent": {"$ne": True},
         "opened_at": {"$lte": cutoff}, "email_status": "sent"},
        {"_id": 0, "log_id": 1, "user_id": 1, "client_email": 1, "client_name": 1,
         "total_ttc": 1, "signature_token": 1, "plan_id": 1, "subject": 1}
    ).to_list(200)

    sent, failed = 0, 0
    for c in candidates:
        try:
            await _send_single_reminder(c)
            sent += 1
        except Exception as e:
            logger.warning(f"reminder for {c.get('log_id')} failed: {e}")
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": 0,
            "candidates": len(candidates)}


@quote_router.post("/reminders/run")
async def trigger_reminders(user=Depends(admin_user)):
    """Endpoint admin pour lancer manuellement le job de rappels."""
    return await _run_reminders()


# ============ QUOTE TEMPLATES ============

class QuoteTemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True
    is_shared: bool = False


@quote_router.post("/templates")
async def create_quote_template(body: QuoteTemplateIn, user=Depends(current_user)):
    tpl_id = "qtpl_" + secrets.token_hex(5)
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1}) or {}
    org_id = u.get("organization_id") if body.is_shared else None
    doc = {
        "template_id": tpl_id, "user_id": user["user_id"],
        "organization_id": org_id,
        "name": body.name.strip()[:80],
        "finish": body.finish, "floor_material": body.floor_material,
        "include_paint": body.include_paint, "include_placo": body.include_placo,
        "include_floor": body.include_floor, "include_skirting": body.include_skirting,
        "created_at": _now(),
    }
    await db.quote_templates.insert_one(doc)
    return {"ok": True, "template_id": tpl_id, **{k: v for k, v in doc.items() if k != "_id"}}


@quote_router.get("/templates")
async def list_quote_templates(user=Depends(current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1}) or {}
    org_id = u.get("organization_id")
    query = {"$or": [{"user_id": user["user_id"]}]}
    if org_id:
        query["$or"].append({"organization_id": org_id})
    docs = await db.quote_templates.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"templates": docs}


@quote_router.delete("/templates/{template_id}")
async def delete_quote_template(template_id: str, user=Depends(current_user)):
    tpl = await db.quote_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Modèle introuvable")
    if tpl.get("user_id") != user["user_id"]:
        raise HTTPException(403, "Réservé au créateur du modèle")
    await db.quote_templates.delete_one({"template_id": template_id})
    return {"ok": True}


# ============ MULTI-PLAN QUOTE PDF ============

class MultiQuoteIn(BaseModel):
    plan_ids: list[str] = Field(min_length=1, max_length=20)
    project_name: str | None = None
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True


@quote_router.post("/multi-pdf")
async def export_multi_quote_pdf(body: MultiQuoteIn, user=Depends(current_user)):
    """Génère un PDF Devis projet consolidé pour plusieurs plans."""
    from fastapi.responses import Response
    from engines.pdf_takeoff import build_project_quote_pdf

    sub_quotes = []
    for pid in body.plan_ids:
        try:
            q, _pdf = await _build_quote_and_pdf(
                pid, user["user_id"], body.finish, body.floor_material,
                body.include_paint, body.include_placo,
                body.include_floor, body.include_skirting,
            )
            sub_quotes.append(q)
        except HTTPException as e:
            if e.status_code == 400:
                continue
            raise
    if not sub_quotes:
        raise HTTPException(400, "Aucun plan n'a de pièce mesurée.")

    def _sum(key: str) -> float:
        return round(sum(q.get(key, 0) for q in sub_quotes), 2)

    project = {
        "project_name": (body.project_name or "Projet ConstruPilot").strip(),
        "plan_count": len(sub_quotes),
        "sub_quotes": sub_quotes,
        "totals": {
            "floor_m2": round(sum(q["totals"]["floor_m2"] for q in sub_quotes), 2),
            "ceiling_m2": round(sum(q["totals"]["ceiling_m2"] for q in sub_quotes), 2),
            "walls_net_m2": round(sum(q["totals"]["walls_net_m2"] for q in sub_quotes), 2),
            "perimeter_m": round(sum(q["totals"]["perimeter_m"] for q in sub_quotes), 2),
        },
        "subtotal_material": _sum("subtotal_material"),
        "subtotal_labour": _sum("subtotal_labour"),
        "subtotal_ht": _sum("subtotal_ht"),
        "tva_rate": 0.10,
        "tva": _sum("tva"),
        "total_ttc": _sum("total_ttc"),
        "finish": body.finish, "floor_material": body.floor_material,
    }
    branding = await _resolve_branding(user["user_id"])
    pdf_bytes = build_project_quote_pdf(project, branding=branding)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="devis-projet-{secrets.token_hex(3)}.pdf"'}
    )


# ============ TRACKING & NOTIFICATIONS ============

@quote_router.get("/track/open/{log_id}", include_in_schema=False)
async def track_quote_open(log_id: str):
    """Pixel de tracking : marque le devis comme ouvert (idempotent)."""
    from fastapi.responses import Response
    pixel = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04" \
            b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02" \
            b"D\x01\x00;"
    try:
        log = await db.quote_sends.find_one({"log_id": log_id},
                                             {"_id": 0, "opened": 1,
                                              "user_id": 1, "client_email": 1})
        if log and not log.get("opened"):
            await db.quote_sends.update_one(
                {"log_id": log_id},
                {"$set": {"opened": True, "opened_at": _now()},
                 "$inc": {"open_count": 1}}
            )
            await db.notifications.insert_one({
                "notif_id": "n_" + secrets.token_hex(5),
                "user_id": log["user_id"],
                "type": "quote_opened", "log_id": log_id,
                "message": f"Le client ({log.get('client_email')}) a ouvert votre devis.",
                "created_at": _now(), "read": False,
            })
        elif log:
            await db.quote_sends.update_one({"log_id": log_id},
                                             {"$inc": {"open_count": 1},
                                              "$set": {"last_opened_at": _now()}})
    except Exception as e:
        logger.warning(f"tracking pixel fail {log_id}: {e}")
    return Response(content=pixel, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@quote_router.get("/notifications/me")
async def list_notifications(user=Depends(current_user)):
    docs = await db.notifications.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    unread = sum(1 for d in docs if not d.get("read"))
    return {"unread": unread, "notifications": docs}


@quote_router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, user=Depends(current_user)):
    await db.notifications.update_one(
        {"notif_id": notif_id, "user_id": user["user_id"]},
        {"$set": {"read": True, "read_at": _now()}}
    )
    return {"ok": True}


@quote_router.post("/notifications/read-all")
async def mark_all_notifications_read(user=Depends(current_user)):
    """Marque toutes les notifs comme lues."""
    res = await db.notifications.update_many(
        {"user_id": user["user_id"], "read": False},
        {"$set": {"read": True, "read_at": _now()}}
    )
    return {"ok": True, "marked": res.modified_count}


@quote_router.get("/sends/all")
async def list_all_quote_sends(user=Depends(current_user)):
    """Suivi Devis : tous les devis envoyés par l'utilisateur, plan_ids agrégés."""
    docs = await db.quote_sends.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "signature_b64": 0}
    ).sort("created_at", -1).limit(200).to_list(200)

    plan_ids = list({d["plan_id"] for d in docs})
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1}
    ).to_list(500) if plan_ids else []
    filenames = {p["plan_id"]: p.get("filename") for p in plans}
    for d in docs:
        d["plan_filename"] = filenames.get(d["plan_id"])

    stats = {"sent": len(docs),
             "opened": sum(1 for d in docs if d.get("opened")),
             "signed": sum(1 for d in docs if d.get("signed")),
             "not_opened": sum(1 for d in docs
                                if not d.get("opened") and not d.get("signed"))}
    stats["total_ttc_signed"] = round(sum(d.get("total_ttc", 0) for d in docs
                                           if d.get("signed")), 2)
    stats["total_ttc_pipeline"] = round(sum(d.get("total_ttc", 0) for d in docs
                                              if not d.get("signed")), 2)
    return {"sends": docs, "stats": stats}


# ============ SIGNATURE CLIENT ============

@router.post("/{plan_id}/quote-sends/{log_id}/signature-link")
async def create_signature_link(plan_id: str, log_id: str, user=Depends(current_user)):
    """Génère un lien public unique pour que le client signe le devis."""
    log = await db.quote_sends.find_one(
        {"log_id": log_id, "plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not log:
        raise HTTPException(404, "Envoi de devis introuvable")
    token = SIG_TOKEN_PREFIX + secrets.token_urlsafe(18)
    await db.quote_sends.update_one(
        {"log_id": log_id},
        {"$set": {"signature_token": token, "signature_token_created_at": _now()}}
    )
    frontend_url = os.getenv("FRONTEND_URL") or ""
    return {"ok": True, "token": token,
            "url": f"{frontend_url}/sign/{token}" if frontend_url else f"/sign/{token}"}


@quote_router.get("/client-portal/{token}")
async def client_portal(token: str):
    """Portail public client — liste tous les devis reçus pour un email donné."""
    from routes.emails import _sign
    import hmac
    import base64
    if "." not in token:
        raise HTTPException(400, "Lien invalide")
    email_b64, sig = token.rsplit(".", 1)
    try:
        email = base64.urlsafe_b64decode(email_b64.encode()).decode()
    except Exception:
        raise HTTPException(400, "Lien invalide")
    if not hmac.compare_digest(sig, _sign(email.lower())):
        raise HTTPException(400, "Lien invalide ou expiré")

    cursor = db.quote_sends.find(
        {"client_email": email.lower()},
        {"_id": 0, "log_id": 1, "plan_id": 1, "user_id": 1,
         "client_name": 1, "total_ttc": 1, "sent_at": 1, "signed": 1,
         "signed_at": 1, "opened_at": 1, "signature_token": 1, "finish": 1,
         "floor_material": 1, "company_snapshot": 1}
    ).sort("sent_at", -1).limit(200)
    docs = await cursor.to_list(200)

    for d in docs:
        pro = await db.users.find_one({"user_id": d["user_id"]},
                                       {"_id": 0, "name": 1, "email": 1})
        b = await _resolve_branding(d["user_id"]) or {}
        d["pro_name"] = b.get("company_name") or (pro or {}).get("name") or "ConstruPilot Pro"
        d["pro_email"] = (pro or {}).get("email")
        d.pop("user_id", None)
        d.pop("company_snapshot", None)

    return {"email": email, "count": len(docs), "quotes": docs}


@quote_router.get("/public/sign/{token}")
async def get_signature_page_data(token: str):
    """Endpoint public : récupère le résumé du devis à signer."""
    log = await db.quote_sends.find_one(
        {"signature_token": token},
        {"_id": 0, "plan_id": 1, "user_id": 1, "client_email": 1, "client_name": 1,
         "total_ttc": 1, "finish": 1, "floor_material": 1, "log_id": 1,
         "signed": 1, "signed_at": 1}
    )
    if not log:
        raise HTTPException(404, "Lien invalide ou expiré")
    branding = await _resolve_branding(log["user_id"]) or {}
    return {
        "log_id": log["log_id"], "plan_id": log["plan_id"],
        "client_email": log.get("client_email"), "client_name": log.get("client_name"),
        "total_ttc": log.get("total_ttc"),
        "finish": log.get("finish"), "floor_material": log.get("floor_material"),
        "signed": bool(log.get("signed")),
        "signed_at": log.get("signed_at"),
        "company_name": branding.get("company_name"),
        "contact_line": branding.get("contact_line"),
    }


class SignatureIn(BaseModel):
    signature_b64: str = Field(min_length=100, max_length=200_000)
    signer_name: str = Field(min_length=2, max_length=120)


def _build_pro_signature_email(pro_name: str, signer: str, ttc: float,
                                client_email: str) -> str:
    ttc_html = (f" — <strong>{int(ttc):,} € TTC</strong>".replace(",", " ")
                if ttc else "")
    return (
        f"<div style='font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px'>"
        f"<div style='background:hsl(24,96%,55%);color:white;padding:20px;border-radius:6px 6px 0 0'>"
        f"<h1 style='margin:0;font-size:22px'>✍️ Devis signé</h1></div>"
        f"<div style='border:1px solid #eee;border-top:none;padding:24px;border-radius:0 0 6px 6px'>"
        f"<p>Bonjour {pro_name or ''},</p>"
        f"<p><strong>{signer}</strong> vient de signer votre devis{ttc_html}.</p>"
        f"<p>Client : <em>{client_email}</em><br/>"
        f"Date : {_now()[:10]}</p>"
        f"<p style='margin-top:24px'>"
        f"<a href='https://construpilot.fr/devis' "
        f"style='background:hsl(24,96%,55%);color:white;padding:12px 24px;"
        f"text-decoration:none;border-radius:4px;font-weight:600;display:inline-block'>"
        f"Voir le devis signé</a></p>"
        f"<p style='margin-top:32px;color:#888;font-size:12px'>"
        f"ConstruPilot · Estimez. Comparez. Construisez.</p>"
        f"</div></div>"
    )


async def _notify_pro_on_signature(log: dict, signer: str, client_email: str) -> None:
    """Best-effort push + email notifications to the pro."""
    try:
        from routes.phase7 import notify_user
        total = log.get("total_ttc") or 0
        title = "✍️ Devis signé !"
        push_body = (f"{signer} vient de signer votre devis"
                     + (f" ({int(total):,} € TTC)".replace(",", " ") if total else ""))
        await notify_user(log["user_id"], title, push_body, "/devis")
    except Exception as e:
        logger.warning(f"Push signature notify failed: {e}")
    try:
        from engines import emailer
        pro = await db.users.find_one({"user_id": log["user_id"]},
                                       {"_id": 0, "email": 1, "name": 1})
        if pro and pro.get("email"):
            html = _build_pro_signature_email(pro.get("name") or "", signer,
                                                log.get("total_ttc", 0), client_email)
            await emailer.send_email(pro["email"], f"✍️ {signer} a signé votre devis", html)
    except Exception as e:
        logger.warning(f"Email signature notify failed: {e}")


@quote_router.post("/public/sign/{token}")
async def submit_signature(token: str, body: SignatureIn):
    """Endpoint public : le client soumet sa signature (image base64)."""
    log = await db.quote_sends.find_one({"signature_token": token},
                                          {"_id": 0, "log_id": 1, "user_id": 1,
                                           "signed": 1, "client_email": 1,
                                           "plan_id": 1, "client_name": 1,
                                           "total_ttc": 1})
    if not log:
        raise HTTPException(404, "Lien invalide")
    if log.get("signed"):
        raise HTTPException(400, "Ce devis a déjà été signé")
    b64_clean = body.signature_b64.split(",")[-1]
    signer = body.signer_name.strip()[:120]
    client_email = log.get("client_email") or ""
    await db.quote_sends.update_one(
        {"log_id": log["log_id"]},
        {"$set": {"signed": True, "signed_at": _now(),
                   "signer_name": signer,
                   "signature_b64": b64_clean}}
    )
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(5),
        "user_id": log["user_id"], "type": "quote_signed", "log_id": log["log_id"],
        "message": f"{signer} a signé le devis ({client_email}).",
        "created_at": _now(), "read": False,
    })
    await _notify_pro_on_signature(log, signer, client_email)
    return {"ok": True, "signed_at": _now()}


@quote_router.get("/public/sign/{token}/pdf")
async def get_signed_quote_pdf(token: str):
    """Renvoie le PDF Devis avec le bloc signature intégré."""
    from fastapi.responses import Response
    from engines.pdf_takeoff import build_quote_pdf
    log = await db.quote_sends.find_one({"signature_token": token}, {"_id": 0})
    if not log:
        raise HTTPException(404, "Lien invalide")
    plan_id = log["plan_id"]
    user_id = log["user_id"]

    quote, _pdf = await _build_quote_and_pdf(
        plan_id, user_id, log.get("finish", "std"),
        log.get("floor_material", "carrelage"),
        True, True, True, True,
    )
    branding = await _resolve_branding(user_id)
    signature = None
    if log.get("signed"):
        signature = {"b64": log.get("signature_b64"),
                     "name": log.get("signer_name"),
                     "at": log.get("signed_at"),
                     "client_email": log.get("client_email")}
    pdf_bytes = build_quote_pdf(quote, branding=branding, signature=signature)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="devis-signe-{plan_id}.pdf"'}
    )
