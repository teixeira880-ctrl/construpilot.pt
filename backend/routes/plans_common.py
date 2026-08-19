"""Common helpers + routers for the plans/takeoffs module.

Refactor iter53 : `routes/plans.py` a été découpé en modules focalisés
(crud, analysis, render, export). Ce fichier hébergeait initialement 2385 lignes.

Ce module contient :
- Les deux routers partagés (`router` pour /takeoffs, `quote_router` pour /quotes)
- Les constantes globales (uploads, prefixes)
- Les helpers partagés : `_now`, `_snapshot`, `_plan_summary`, `_resolve_branding`,
  `_build_quote_and_pdf`, `_diff_rooms`
- Le générateur de token portail client `build_client_portal_token`
"""
from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from core.db import db

logger = logging.getLogger(__name__)

# ---- Routers ------------------------------------------------------------
router = APIRouter(tags=["plans"], prefix="/takeoffs")
quote_router = APIRouter(tags=["quotes"], prefix="/quotes")

# ---- Constants ----------------------------------------------------------
MAX_UPLOAD_MB = 20
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp",
                 "application/dxf", "image/vnd.dxf", "application/acad", "image/vnd.dwg"}

# ID prefixes (not secrets — pass through to caller for prefix-based routing)
SIG_TOKEN_PREFIX = "sig_"    # noqa: S105 - identifier prefix
QUOTE_SEND_PREFIX = "qs_"    # noqa: S105 - identifier prefix


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Snapshots (auto-history) ------------------------------------------

async def _snapshot(plan_id: str, user_id: str, action: str, meta: dict | None = None,
                    label: str | None = None) -> None:
    """Sauvegarde un instantané du plan avant/après une mutation (auto-history)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "rooms": 1, "calibrations": 1, "pages.level_index": 1,
         "pages.level_label": 1, "pages.index": 1}
    )
    if not p:
        return
    snap = {
        "snapshot_id": "snap_" + secrets.token_hex(6),
        "plan_id": plan_id, "user_id": user_id,
        "action": action, "meta": meta or {},
        "label": (label or "").strip()[:80] or None,
        "created_at": _now(),
        "rooms": p.get("rooms") or [],
        "calibrations": p.get("calibrations") or {},
        "page_levels": [{"index": pg.get("index"),
                         "level_index": pg.get("level_index"),
                         "level_label": pg.get("level_label")} for pg in (p.get("pages") or [])],
    }
    await db.plans_takeoff_history.insert_one(snap)
    # Cap : garde les 50 derniers snapshots par plan
    old = await db.plans_takeoff_history.find(
        {"plan_id": plan_id, "user_id": user_id}, {"_id": 1}
    ).sort("created_at", -1).skip(50).to_list(200)
    if old:
        await db.plans_takeoff_history.delete_many({"_id": {"$in": [o["_id"] for o in old]}})


def _plan_summary(p: dict) -> dict:
    """Enlève les image_png_b64 pour un payload léger (list & detail)."""
    pages_light = [
        {k: v for k, v in pg.items() if k != "image_png_b64"}
        for pg in (p.get("pages") or [])
    ]
    return {
        "plan_id": p["plan_id"],
        "filename": p.get("filename"),
        "kind": p.get("kind"),
        "page_count": p.get("page_count"),
        "detected_scale_denominator": p.get("detected_scale_denominator"),
        "calibrations": p.get("calibrations", {}),
        "rooms": p.get("rooms", []),
        "ai_analysis": p.get("ai_analysis"),
        "project_id": p.get("project_id"),
        "pages": pages_light,
        "annotations": p.get("annotations", {}),
        "measurements": p.get("measurements", []),
        "structure": p.get("structure", {}),
        "sent_reports": p.get("sent_reports", []),
        "pc_study": p.get("pc_study"),
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
    }


# ---- Branding resolution -----------------------------------------------

async def _resolve_branding(user_id: str) -> dict | None:
    """Récupère branding : prefer org branding si user en fait partie.
    Ajoute toujours la photo de profil uploadée (data URL) si présente."""
    u = await db.users.find_one({"user_id": user_id},
                                 {"_id": 0, "organization_id": 1, "picture": 1,
                                  "brand_company_name": 1, "brand_contact_line": 1,
                                  "brand_company_email": 1,
                                  "brand_siret": 1, "brand_vat": 1,
                                  "brand_address": 1, "brand_city": 1,
                                  "brand_postal": 1, "brand_country": 1,
                                  "brand_logo_b64": 1, "brand_certifications": 1})
    if not u:
        return None
    photo = u.get("picture") if (u.get("picture") or "").startswith("data:image") else None
    if u.get("organization_id"):
        org = await db.organizations.find_one({"org_id": u["organization_id"]},
                                                {"_id": 0, "brand_company_name": 1,
                                                 "brand_contact_line": 1, "brand_logo_b64": 1,
                                                 "brand_company_email": 1,
                                                 "brand_siret": 1, "brand_vat": 1,
                                                 "brand_address": 1, "brand_city": 1,
                                                 "brand_postal": 1, "brand_country": 1,
                                                 "brand_certifications": 1})
        if org and any(org.get(k) for k in ("brand_company_name", "brand_contact_line",
                                              "brand_logo_b64", "brand_certifications")):
            return {"company_name": org.get("brand_company_name"),
                    "contact_line": org.get("brand_contact_line"),
                    "company_email": org.get("brand_company_email"),
                    "logo_b64": org.get("brand_logo_b64"),
                    "siret": org.get("brand_siret"),
                    "vat": org.get("brand_vat"),
                    "address": org.get("brand_address"),
                    "city": org.get("brand_city"),
                    "postal_code": org.get("brand_postal"),
                    "country": org.get("brand_country"),
                    "certifications": org.get("brand_certifications") or [],
                    "profile_photo_b64": photo}
    if any(u.get(k) for k in ("brand_company_name", "brand_contact_line", "brand_logo_b64",
                              "brand_certifications")):
        return {"company_name": u.get("brand_company_name"),
                "contact_line": u.get("brand_contact_line"),
                "company_email": u.get("brand_company_email"),
                "logo_b64": u.get("brand_logo_b64"),
                "siret": u.get("brand_siret"),
                "vat": u.get("brand_vat"),
                "address": u.get("brand_address"),
                "city": u.get("brand_city"),
                "postal_code": u.get("brand_postal"),
                "country": u.get("brand_country"),
                "certifications": u.get("brand_certifications") or [],
                "profile_photo_b64": photo}
    if photo:
        return {"company_name": None, "contact_line": None, "logo_b64": None,
                "certifications": [], "profile_photo_b64": photo}
    return None


# ---- Boîte e-mail entreprise (SMTP) ------------------------------------

async def get_mailbox_config(user_id: str) -> dict | None:
    """Config SMTP de l'entreprise (mot de passe déchiffré) si connectée + vérifiée.

    Résolution : config perso de l'utilisateur d'abord, sinon config de son org.
    """
    from engines.mailbox_smtp import decrypt_secret

    def _extract(doc: dict) -> dict | None:
        if not doc or not doc.get("smtp_verified"):
            return None
        enc = doc.get("smtp_password_enc")
        if not (doc.get("smtp_host") and doc.get("smtp_email") and enc):
            return None
        try:
            pwd = decrypt_secret(enc)
        except Exception:  # noqa: BLE001
            return None
        return {"host": doc["smtp_host"], "port": doc.get("smtp_port"),
                "security": doc.get("smtp_security", "ssl"),
                "email": doc["smtp_email"], "password": pwd,
                "from_name": doc.get("smtp_from_name")}

    u = await db.users.find_one(
        {"user_id": user_id},
        {"_id": 0, "organization_id": 1, "smtp_host": 1, "smtp_port": 1,
         "smtp_security": 1, "smtp_email": 1, "smtp_password_enc": 1,
         "smtp_from_name": 1, "smtp_verified": 1}) or {}
    cfg = _extract(u)
    if cfg:
        return cfg
    if u.get("organization_id"):
        org = await db.organizations.find_one(
            {"org_id": u["organization_id"]},
            {"_id": 0, "smtp_host": 1, "smtp_port": 1, "smtp_security": 1,
             "smtp_email": 1, "smtp_password_enc": 1, "smtp_from_name": 1,
             "smtp_verified": 1}) or {}
        return _extract(org)
    return None


async def deliver_email(user_id: str, to: str, subject: str, html: str,
                        pdf_bytes: bytes | None = None, filename: str = "document.pdf",
                        extra_attachments: list[dict] | None = None,
                        reply_to: str | None = None, from_name: str | None = None,
                        cc: str | None = None) -> dict:
    """Envoie via le SMTP entreprise si connecté (copie auto dans « Envoyés »),
    sinon via Resend. Retourne {ok, id, via, error?}."""
    attachments: list[dict] = []
    if pdf_bytes is not None:
        attachments.append({"filename": filename, "content": pdf_bytes,
                            "content_type": "application/pdf"})
    for att in extra_attachments or []:
        attachments.append(att)

    cfg = await get_mailbox_config(user_id)
    if cfg:
        from engines.mailbox_smtp import smtp_send
        try:
            res = await smtp_send(cfg, to, subject, html, cc=cc, reply_to=reply_to,
                                  from_name=from_name, attachments=attachments)
            return {"ok": True, "id": res.get("id"), "via": "smtp"}
        except Exception as e:  # noqa: BLE001
            logger.warning("SMTP entreprise échoué (%s) — fallback Resend : %s", user_id, e)

    from engines.emailer import send_email, send_email_with_pdf
    if attachments:
        first = attachments[0]
        res = await send_email_with_pdf(
            to, subject, html, first["content"], filename=first["filename"],
            cc=cc, extra_attachments=attachments[1:] or None,
            reply_to=reply_to, from_name=from_name)
    else:
        res = await send_email(to, subject, html, reply_to=reply_to, from_name=from_name)
    return {"ok": True, "id": res.get("id"), "via": "resend"}




# ---- Quote build (used by export routes) -------------------------------

def _add_quote_line(items: list[dict], name: str, qty: float, unit: str,
                    mat_unit_eur: float, labour_unit_eur: float) -> None:
    if qty <= 0:
        return
    mat_total = round(qty * mat_unit_eur, 2)
    lab_total = round(qty * labour_unit_eur, 2)
    items.append({
        "name": name, "quantity": round(qty, 2), "unit": unit,
        "unit_material": mat_unit_eur, "unit_labour": labour_unit_eur,
        "material_total": mat_total, "labour_total": lab_total,
        "total": round(mat_total + lab_total, 2),
    })


async def _build_quote_and_pdf(plan_id: str, user_id: str, finish: str,
                                floor_material: str, include_paint: bool,
                                include_placo: bool, include_floor: bool,
                                include_skirting: bool) -> tuple[dict, bytes]:
    """Construit le quote (dict) + le PDF bytes. Réutilisé par download & send-quote."""
    from engines.pdf_takeoff import build_quote_pdf
    from engines.catalog import LOTS_BY_KEY

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "pages.image_png_b64": 0}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    if not rooms:
        raise HTTPException(400, "Aucune pièce mesurée sur ce plan.")

    total_floor = sum(r.get("surface_m2", 0) for r in rooms)
    total_ceiling = sum(r.get("ceiling_area_m2", 0) for r in rooms)
    total_walls_net = sum(r.get("wall_area_net_m2", 0) for r in rooms)
    total_perim = sum(r.get("perimeter_m", 0) for r in rooms)

    mat_key = ("mat_eco" if finish == "eco"
                else "mat_premium" if finish == "premium" else "mat_std")
    line_items: list[dict] = []

    if include_placo:
        placo = LOTS_BY_KEY.get("placo")
        if placo:
            _add_quote_line(line_items, "Plâtrerie / Placo (murs + plafonds)",
                             total_walls_net + total_ceiling, "m²",
                             placo.get(mat_key, 17), placo.get("labour", 26))
    if include_paint:
        peint = LOTS_BY_KEY.get("peinture")
        if peint:
            _add_quote_line(line_items, "Peinture (murs + plafonds)",
                             total_walls_net + total_ceiling, "m²",
                             peint.get(mat_key, 8), peint.get("labour", 16))
    if include_floor:
        lot_key = "carrelage" if floor_material.lower() in ("carrelage", "tile") else "parquet"
        lot = LOTS_BY_KEY.get(lot_key)
        if lot:
            _add_quote_line(line_items, f"Sol : {lot['name']}", total_floor, "m²",
                             lot.get(mat_key, 35), lot.get("labour", 26))
    if include_skirting:
        door_count = sum(len([o for o in r.get("openings", [])
                              if (o.get("kind") or o.get("type") or "").lower().startswith("port")])
                         for r in rooms)
        _add_quote_line(line_items, "Plinthes (ml)",
                         total_perim - 1.8 * door_count, "ml", 5.0, 6.0)

    subtotal_mat = round(sum(li["material_total"] for li in line_items), 2)
    subtotal_lab = round(sum(li["labour_total"] for li in line_items), 2)
    subtotal = round(subtotal_mat + subtotal_lab, 2)
    tva_rate = 0.10
    tva = round(subtotal * tva_rate, 2)
    ttc = round(subtotal + tva, 2)

    quote = {
        "plan_id": plan_id, "filename": p.get("filename"), "finish": finish,
        "floor_material": floor_material,
        "totals": {"floor_m2": round(total_floor, 2),
                    "ceiling_m2": round(total_ceiling, 2),
                    "walls_net_m2": round(total_walls_net, 2),
                    "perimeter_m": round(total_perim, 2)},
        "line_items": line_items,
        "subtotal_material": subtotal_mat,
        "subtotal_labour": subtotal_lab,
        "subtotal_ht": subtotal,
        "tva_rate": tva_rate, "tva": tva, "total_ttc": ttc,
    }
    branding = await _resolve_branding(user_id)
    from routes.reviews import get_reviews_for_user
    reviews = await get_reviews_for_user(user_id)
    pdf_bytes = build_quote_pdf(quote, branding=branding, reviews=reviews)
    return quote, pdf_bytes


# ---- Rooms diff (used by analysis routes) ------------------------------

def _norm_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _diff_rooms(rooms_b: list[dict], rooms_a: list[dict], tol: float = 5.0) -> dict:
    """Diff pur entre 2 listes de rooms — utilisé par plans-compare & snapshot-compare."""
    by_name_b: dict = {}
    for r in rooms_b:
        by_name_b.setdefault(_norm_name(r.get("name")), []).append(r)
    matched_after = set()

    added, removed, modified, unchanged = [], [], [], []
    for ra in rooms_a:
        name_norm = _norm_name(ra.get("name"))
        if name_norm in by_name_b and by_name_b[name_norm]:
            rb = by_name_b[name_norm].pop(0)
            matched_after.add(id(ra))
            sb = rb.get("surface_m2", 0)
            sa = ra.get("surface_m2", 0)
            delta_pct = abs(sa - sb) / sb * 100 if sb else 100
            entry = {
                "name": ra.get("name"),
                "surface_before_m2": sb, "surface_after_m2": sa,
                "delta_m2": round(sa - sb, 2),
                "delta_pct": round(delta_pct, 1),
                "perimeter_before_m": rb.get("perimeter_m", 0),
                "perimeter_after_m": ra.get("perimeter_m", 0),
            }
            (unchanged if delta_pct <= tol else modified).append(entry)
    for lst in by_name_b.values():
        for rb in lst:
            removed.append({"name": rb.get("name"), "surface_m2": rb.get("surface_m2", 0),
                            "perimeter_m": rb.get("perimeter_m", 0)})
    for ra in rooms_a:
        if id(ra) not in matched_after:
            added.append({"name": ra.get("name"), "surface_m2": ra.get("surface_m2", 0),
                          "perimeter_m": ra.get("perimeter_m", 0)})

    total_b = sum(r.get("surface_m2", 0) for r in rooms_b)
    total_a = sum(r.get("surface_m2", 0) for r in rooms_a)
    return {
        "delta_surface_m2": round(total_a - total_b, 2),
        "delta_surface_pct": round((total_a - total_b) / total_b * 100, 2) if total_b else 0,
        "added": added, "removed": removed,
        "modified": modified, "unchanged": unchanged,
        "surface_tolerance_pct": tol,
        "total_before_m2": round(total_b, 2), "total_after_m2": round(total_a, 2),
    }


# ---- Client portal token -----------------------------------------------

def build_client_portal_token(email: str) -> str:
    """Génère un token portail signé pour cet email (à envoyer dans les emails devis)."""
    from routes.emails import _sign
    import base64
    email_b64 = base64.urlsafe_b64encode(email.lower().encode()).decode()
    return f"{email_b64}.{_sign(email.lower())}"
