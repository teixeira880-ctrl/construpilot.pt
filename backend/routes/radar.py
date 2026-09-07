"""Radar Chantiers — V1 socle : détection d'opportunités depuis données urbanisme (échantillon SITADEL 95),
géoloc + rayon, scoring IA, estimation potentiel, favoris. RGPD : données publiques uniquement."""
import asyncio
import base64
import csv
import io
import math
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import admin_user, current_user, optional_user

router = APIRouter(prefix="/radar", tags=["radar"])


def _frontend_url() -> str:
    return (os.getenv("FRONTEND_URL") or "https://construpilot.fr").rstrip("/")

# Base commerciale par défaut (Pontoise, 95) si l'entreprise n'a pas défini de zone
DEFAULT_BASE = {"lat": 49.0503, "lon": 2.1010, "label": "Pontoise (95)"}

METIER_LOTS = {
    "terrassement": (55, 90), "vrd": (40, 70), "fondations": (95, 140),
    "gros_oeuvre": (170, 240), "maconnerie": (150, 210), "charpente": (70, 110),
    "couverture": (60, 95), "etancheite": (45, 75), "isolation": (40, 70),
    "facade": (50, 85), "menuiserie": (90, 150), "plomberie": (55, 90),
    "chauffage": (60, 100), "electricite": (55, 95), "placo": (35, 60),
    "peinture": (30, 55), "carrelage": (40, 70), "renovation_complete": (900, 1500),
}
METIER_LABELS = {
    "terrassement": "Terrassement", "vrd": "VRD", "fondations": "Fondations",
    "gros_oeuvre": "Gros œuvre", "maconnerie": "Maçonnerie", "charpente": "Charpente",
    "couverture": "Couverture", "etancheite": "Étanchéité", "isolation": "Isolation",
    "facade": "Façade", "menuiserie": "Menuiserie", "plomberie": "Plomberie",
    "chauffage": "Chauffage", "electricite": "Électricité", "placo": "Placo",
    "peinture": "Peinture", "carrelage": "Carrelage", "renovation_complete": "Rénovation complète",
}

# Échantillon réel-plausible de permis (dept 95, Val-d'Oise) — source publique : SITADEL / permis de construire
PERMITS = [
    {"id": "CP-2026-95731", "num": "PC 095 500 26 R0071", "type": "Permis de construire", "nature": "neuf",
     "commune": "Pontoise", "cp": "95000", "dep": "95", "lat": 49.0510, "lon": 2.1020,
     "batiment": "Maison individuelle R+1", "surf_created": 187, "logements": 1,
     "date_depot": "2026-05-12", "date_auth": "2026-06-18", "statut": "Autorisé", "mo": "PARTICULIER"},
    {"id": "CP-2026-95402", "num": "PC 095 127 26 R0033", "type": "Permis de construire", "nature": "neuf",
     "commune": "Cergy", "cp": "95000", "dep": "95", "lat": 49.0360, "lon": 2.0780,
     "batiment": "Immeuble collectif R+3", "surf_created": 1240, "logements": 18,
     "date_depot": "2026-05-28", "date_auth": "2026-06-22", "statut": "Autorisé", "mo": "PROMOTEUR"},
    {"id": "CP-2026-95588", "num": "DP 095 306 26 R0210", "type": "Déclaration préalable", "nature": "renovation",
     "commune": "Osny", "cp": "95520", "dep": "95", "lat": 49.0700, "lon": 2.0700,
     "batiment": "Extension maison", "surf_created": 42, "logements": 1,
     "date_depot": "2026-06-01", "date_auth": "2026-06-20", "statut": "Autorisé", "mo": "PARTICULIER"},
    {"id": "CP-2026-95119", "num": "PC 095 018 26 R0009", "type": "Permis de construire", "nature": "neuf",
     "commune": "Éragny", "cp": "95610", "dep": "95", "lat": 49.0170, "lon": 2.0900,
     "batiment": "Maison individuelle plain-pied", "surf_created": 132, "logements": 1,
     "date_depot": "2026-06-05", "date_auth": "2026-06-24", "statut": "Autorisé", "mo": "PARTICULIER"},
    {"id": "CP-2026-95903", "num": "PC 095 572 26 R0142", "type": "Permis de construire", "nature": "neuf",
     "commune": "Saint-Ouen-l'Aumône", "cp": "95310", "dep": "95", "lat": 49.0430, "lon": 2.1150,
     "batiment": "Bâtiment d'activité / logistique", "surf_created": 2100, "logements": 0,
     "date_depot": "2026-04-20", "date_auth": "2026-06-10", "statut": "Autorisé", "mo": "ENTREPRISE"},
    {"id": "CP-2026-95260", "num": "PC 095 476 26 R0055", "type": "Permis de construire", "nature": "renovation",
     "commune": "Pontoise", "cp": "95300", "dep": "95", "lat": 49.0490, "lon": 2.0980,
     "batiment": "Réhabilitation logements SCI", "surf_created": 380, "logements": 5,
     "date_depot": "2026-05-15", "date_auth": "2026-06-19", "statut": "Autorisé", "mo": "SCI"},
    {"id": "CP-2026-95744", "num": "PC 095 252 26 R0088", "type": "Permis de construire", "nature": "neuf",
     "commune": "Jouy-le-Moutier", "cp": "95280", "dep": "95", "lat": 49.0130, "lon": 2.0380,
     "batiment": "Maison individuelle R+1", "surf_created": 156, "logements": 1,
     "date_depot": "2026-06-08", "date_auth": "2026-06-25", "statut": "Autorisé", "mo": "PARTICULIER"},
    {"id": "CP-2026-95611", "num": "PA 095 500 26 R0004", "type": "Permis d'aménager", "nature": "neuf",
     "commune": "Vauréal", "cp": "95490", "dep": "95", "lat": 49.0320, "lon": 2.0330,
     "batiment": "Lotissement 8 lots", "surf_created": 960, "logements": 8,
     "date_depot": "2026-03-30", "date_auth": "2026-05-30", "statut": "Autorisé", "mo": "COLLECTIVITE"},
    {"id": "CP-2026-95055", "num": "DP 095 127 26 R0301", "type": "Déclaration préalable", "nature": "renovation",
     "commune": "Cergy", "cp": "95000", "dep": "95", "lat": 49.0400, "lon": 2.0600,
     "batiment": "Rénovation énergétique pavillon", "surf_created": 0, "logements": 1,
     "date_depot": "2026-06-10", "date_auth": "2026-06-26", "statut": "Autorisé", "mo": "PARTICULIER"},
    {"id": "CP-2026-95820", "num": "PC 095 018 26 R0021", "type": "Permis de construire", "nature": "neuf",
     "commune": "Pierrelaye", "cp": "95480", "dep": "95", "lat": 49.0180, "lon": 2.1550,
     "batiment": "Maison individuelle R+1", "surf_created": 204, "logements": 1,
     "date_depot": "2026-06-12", "date_auth": "2026-06-27", "statut": "Autorisé", "mo": "PARTICULIER"},
]

METIER_MAP = {
    "neuf": ["terrassement", "fondations", "gros_oeuvre", "maconnerie", "charpente",
             "couverture", "menuiserie", "plomberie", "electricite", "isolation", "carrelage", "peinture"],
    "renovation": ["maconnerie", "isolation", "menuiserie", "plomberie", "electricite",
                   "placo", "carrelage", "peinture", "renovation_complete"],
}


def _haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(h)), 1)


def _lots_for(permit):
    return METIER_MAP.get(permit["nature"], METIER_MAP["neuf"])


def _estimate(permit):
    """Estimation préliminaire par lot (fourchette €), basée sur la surface créée."""
    surf = max(permit.get("surf_created") or 0, 30)
    lots = []
    for m in _lots_for(permit):
        lo, hi = METIER_LOTS[m]
        lots.append({"metier": m, "label": METIER_LABELS[m],
                     "low": int(surf * lo), "high": int(surf * hi)})
    total_low = sum(l["low"] for l in lots)
    total_high = sum(l["high"] for l in lots)
    return lots, total_low, total_high


def _score(permit, distance_km, company_metiers, my_lot_low):
    s = 0.0
    s += max(0, 30 - distance_km) / 30 * 30          # proximité (30)
    days = (date.today() - date.fromisoformat(permit["date_auth"])).days
    s += max(0, 45 - days) / 45 * 20                  # récence (20)
    surf = permit.get("surf_created") or 0
    s += min(surf, 300) / 300 * 15                     # ampleur (15)
    if any(m in _lots_for(permit) for m in company_metiers):
        s += 20                                        # adéquation métier (20)
    s += min(my_lot_low, 80000) / 80000 * 15           # potentiel (15)
    return int(max(1, min(100, round(s))))


def _build(permit, base, company_metiers):
    dist = _haversine(base["lat"], base["lon"], permit["lat"], permit["lon"])
    lots, tlo, thi = _estimate(permit)
    my = [l for l in lots if l["metier"] in company_metiers] or lots
    my_low = sum(l["low"] for l in my)
    my_high = sum(l["high"] for l in my)
    score = _score(permit, dist, company_metiers, my_low)
    return {**permit, "distance_km": dist, "lots": lots,
            "estimate_low": tlo, "estimate_high": thi,
            "my_lot_low": my_low, "my_lot_high": my_high,
            "score": score, "metier_labels": METIER_LABELS}


async def _get_permits():
    """Permis réels importés (db.radar_permits) s'ils existent, sinon échantillon mock."""
    docs = await db.radar_permits.find({}, {"_id": 0}).to_list(3000)
    return docs if docs else PERMITS


async def _profile(user):
    u = await db.users.find_one({"user_id": user["user_id"]},
                                {"_id": 0, "radar_km": 1, "radar_metiers": 1,
                                 "radar_favorites": 1, "radar_base": 1})
    u = u or {}
    return {"km": u.get("radar_km", 30),
            "metiers": u.get("radar_metiers") or ["gros_oeuvre", "maconnerie", "fondations", "terrassement"],
            "favorites": u.get("radar_favorites") or [],
            "base": u.get("radar_base") or DEFAULT_BASE}


@router.get("/profile")
async def get_profile(user=Depends(current_user)):
    p = await _profile(user)
    return {**p, "metier_options": [{"key": k, "label": v} for k, v in METIER_LABELS.items()]}


class ProfileIn(BaseModel):
    km: int | None = None
    metiers: list[str] | None = None
    base: dict | None = None


@router.put("/profile")
async def put_profile(body: ProfileIn, user=Depends(current_user)):
    upd = {}
    if body.km is not None:
        upd["radar_km"] = max(5, min(200, body.km))
    if body.metiers is not None:
        upd["radar_metiers"] = [m for m in body.metiers if m in METIER_LABELS][:20]
    if body.base is not None and "lat" in body.base:
        upd["radar_base"] = {"lat": float(body.base["lat"]), "lon": float(body.base["lon"]),
                             "label": str(body.base.get("label", ""))[:80]}
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return await get_profile(user)


@router.get("/opportunities")
async def list_opportunities(km: int | None = None, metier: str | None = None, favorites: bool = False,
                             user=Depends(current_user)):
    p = await _profile(user)
    radius = km or p["km"]
    permits = await _get_permits()
    items = [_build(pm, p["base"], p["metiers"]) for pm in permits]
    items = [x for x in items if x["distance_km"] <= radius]
    if metier:
        items = [x for x in items if metier in x["lots"] or any(l["metier"] == metier for l in x["lots"])]
    if favorites:
        items = [x for x in items if x["id"] in p["favorites"]]
    for x in items:
        x["is_favorite"] = x["id"] in p["favorites"]
    items.sort(key=lambda x: x["score"], reverse=True)
    return {"base": p["base"], "radius_km": radius, "count": len(items), "opportunities": items}


@router.get("/opportunities/{opp_id}")
async def get_opportunity(opp_id: str, user=Depends(current_user)):
    p = await _profile(user)
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    o = _build(pm, p["base"], p["metiers"])
    o["is_favorite"] = opp_id in p["favorites"]
    # RGPD : statut de contact selon le type de maître d'ouvrage
    o["contact_status"] = "green" if pm["mo"] in ("ENTREPRISE", "PROMOTEUR", "SCI", "BAILLEUR", "COLLECTIVITE") else "orange"
    o["source"] = {"name": "SITADEL / autorisations d'urbanisme", "type": "public",
                   "imported_at": datetime.now(timezone.utc).isoformat()}
    company = await _company_name(user["user_id"])
    o["suggested_message"] = _default_intro_plain(o, company)
    return o


@router.post("/opportunities/{opp_id}/favorite")
async def toggle_favorite(opp_id: str, user=Depends(current_user)):
    permits = await _get_permits()
    if not any(x["id"] == opp_id for x in permits):
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    favs = set(p["favorites"])
    favs.symmetric_difference_update({opp_id})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"radar_favorites": list(favs)}})
    return {"id": opp_id, "is_favorite": opp_id in favs}


@router.get("/stats")
async def stats(user=Depends(current_user)):
    p = await _profile(user)
    permits = await _get_permits()
    items = [_build(pm, p["base"], p["metiers"]) for pm in permits if _haversine(
        p["base"]["lat"], p["base"]["lon"], pm["lat"], pm["lon"]) <= p["km"]]
    strong = [x for x in items if x["score"] >= 85]
    return {"detected": len(items), "strong": len(strong),
            "potential_ttc": sum(x["my_lot_high"] for x in items),
            "favorites": len(p["favorites"])}



# =====================================================================
# Prospection : courrier personnalisé + QR code → landing → capture CRM
# =====================================================================

def _qr_png_bytes(url: str) -> bytes:
    import qrcode
    qr = qrcode.QRCode(version=None, box_size=8, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A0D14", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _eur_fr(v) -> str:
    return f"{int(v or 0):,}".replace(",", "\u202f") + " €"


async def _company_name(user_id: str) -> str:
    from routes.plans_common import _resolve_branding
    b = await _resolve_branding(user_id) or {}
    return b.get("company_name") or "notre entreprise"


def _default_intro_plain(opp: dict, company: str) -> str:
    surf_txt = f" (surface créée ≈ {opp.get('surf_created')} m²)" if opp.get("surf_created") else ""
    low, high = opp.get("my_lot_low") or 0, opp.get("my_lot_high") or 0
    price = ""
    if high:
        price = (f"\n\nÀ titre indicatif, nos prestations sur un projet de cette nature se situent "
                 f"généralement entre {_eur_fr(low)} et {_eur_fr(high)} "
                 f"(estimation préliminaire, à affiner ensemble selon vos besoins).")
    return (
        f"Bonjour,\n\nNous avons constaté qu'une autorisation d'urbanisme a récemment été délivrée à "
        f"{opp.get('commune')} pour un projet de {opp.get('batiment')}{surf_txt}.\n\n"
        f"Entreprise locale du bâtiment, {company} réalise ce type de travaux dans votre secteur. "
        f"Nous serions ravis de vous accompagner sur ce projet — de l'étude au chiffrage détaillé, "
        f"jusqu'à la réalisation." + price)


def _build_prospection_pdf(*, branding: dict | None, opp: dict, public_url: str,
                           qr_png: bytes, custom_message: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    b = branding or {}
    company = b.get("company_name") or "Votre entreprise du bâtiment"
    ink = colors.HexColor("#0A0D14")
    muted = colors.HexColor("#64748B")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm,
                            leftMargin=22 * mm, rightMargin=22 * mm, bottomMargin=18 * mm)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, textColor=ink, leading=19)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, textColor=ink, leading=16)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, textColor=muted, leading=12)
    el = []

    # En-tête entreprise
    header_lines = [f"<b>{company}</b>"]
    if b.get("contact_line"):
        header_lines.append(b["contact_line"])
    addr = " · ".join([x for x in [b.get("address"), b.get("postal_code"), b.get("city")] if x])
    if addr:
        header_lines.append(addr)
    fisc = " · ".join([x for x in [
        f"SIRET {b['siret']}" if b.get("siret") else "",
        f"TVA {b['vat']}" if b.get("vat") else ""] if x])
    if fisc:
        header_lines.append(fisc)
    el.append(Paragraph("<br/>".join(header_lines), small))
    el.append(Spacer(1, 14))

    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    el.append(Paragraph(f"À l'attention du maître d'ouvrage<br/>{opp.get('commune')} ({opp.get('cp')})",
                        body))
    el.append(Spacer(1, 6))
    el.append(Paragraph(f"{opp.get('city') or opp.get('commune')}, le {today}", small))
    el.append(Spacer(1, 14))

    el.append(Paragraph(f"Objet : votre projet « {opp.get('batiment')} »", h1))
    el.append(Spacer(1, 10))

    msg = (custom_message or "").strip() or _default_intro_plain(opp, company)
    for para in msg.split("\n\n"):
        if para.strip():
            el.append(Paragraph(para.strip().replace("\n", "<br/>"), body))
            el.append(Spacer(1, 8))
    el.append(Spacer(1, 2))

    el.append(Paragraph(
        "Pour recevoir <b>gratuitement et sans engagement</b> une première estimation personnalisée, "
        "scannez le QR code ci-contre ou rendez-vous sur le lien indiqué. Cela ne prend qu'une minute.",
        body))
    el.append(Spacer(1, 6))

    # QR + lien
    qr_img = Image(BytesIO(qr_png), width=34 * mm, height=34 * mm)
    link_cell = Paragraph(
        f"<b>Demandez votre estimation :</b><br/><font color='#3f7d54'>{public_url}</font><br/><br/>"
        f"<font size=8 color='#64748B'>Réf. opportunité {opp.get('id')}</font>", body)
    t = Table([[qr_img, link_cell]], colWidths=[38 * mm, 118 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (1, 0), (1, 0), 10)]))
    el.append(t)
    el.append(Spacer(1, 14))

    el.append(Paragraph("Dans l'attente de votre retour, nous vous prions d'agréer, Madame, Monsieur, "
                        "l'expression de nos salutations distinguées.", body))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f"<b>{company}</b>", body))
    el.append(Spacer(1, 16))
    el.append(Paragraph(
        "Information issue de données publiques d'autorisations d'urbanisme (SITADEL). "
        "Ce courrier est une proposition commerciale. Conformément au RGPD, vous pouvez vous opposer "
        "à toute prospection en nous contactant.", small))

    doc.build(el)
    return buf.getvalue()


async def _pro_branding_and_user(user_id: str):
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user_id)
    u = await db.users.find_one({"user_id": user_id},
                                {"_id": 0, "name": 1, "email": 1}) or {}
    return branding, u


class ProspectionIn(BaseModel):
    message: str = ""


@router.post("/opportunities/{opp_id}/prospection")
async def create_prospection(opp_id: str, body: ProspectionIn, user=Depends(current_user)):
    """Crée (ou réutilise) une campagne de prospection : courrier PDF + QR + landing publique."""
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])

    existing = await db.radar_prospections.find_one(
        {"user_id": user["user_id"], "opp_id": opp_id}, {"_id": 0})
    if existing:
        token = existing["token"]
    else:
        token = "rop_" + secrets.token_urlsafe(9)
        await db.radar_prospections.insert_one({
            "token": token, "user_id": user["user_id"], "opp_id": opp_id,
            "opp_snapshot": {k: opp.get(k) for k in (
                "id", "commune", "cp", "batiment", "type", "nature", "surf_created",
                "my_lot_low", "my_lot_high", "estimate_low", "estimate_high")},
            "message": (body.message or "").strip()[:2000],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "lead_count": 0})

    if body.message and existing:
        await db.radar_prospections.update_one(
            {"token": token}, {"$set": {"message": body.message.strip()[:2000]}})

    public_url = f"{_frontend_url()}/prospection/{token}"
    branding, _ = await _pro_branding_and_user(user["user_id"])
    qr_png = _qr_png_bytes(public_url)
    pdf = _build_prospection_pdf(branding=branding, opp=opp, public_url=public_url,
                                 qr_png=qr_png, custom_message=(body.message or ""))
    return {
        "token": token,
        "public_url": public_url,
        "qr_b64": "data:image/png;base64," + base64.b64encode(qr_png).decode(),
        "letter_b64": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
        "opp": {"id": opp["id"], "commune": opp["commune"], "batiment": opp["batiment"]},
    }


class AiLetterIn(BaseModel):
    tone: Literal["formel", "chaleureux", "direct", "commercial"] = "formel"
    length: Literal["court", "moyen", "long"] = "moyen"


_TONE_HINT = {
    "formel": "ton formel et professionnel, vouvoiement, registre soutenu",
    "chaleureux": "ton chaleureux et humain, proche et rassurant, vouvoiement",
    "direct": "ton direct et concis, orienté action, sans fioritures",
    "commercial": "ton commercial et persuasif, met en avant les bénéfices et crée l'envie",
}
_LEN_HINT = {"court": "environ 90 à 130 mots", "moyen": "environ 150 à 220 mots",
             "long": "environ 250 à 320 mots"}


@router.post("/opportunities/{opp_id}/prospection/ai")
async def ai_letter(opp_id: str, body: AiLetterIn, user=Depends(current_user)):
    """Rédige avec l'IA (Claude) le corps d'un courrier de prospection sur-mesure."""
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    company = await _company_name(user["user_id"])
    tone = _TONE_HINT.get(body.tone, _TONE_HINT["formel"])
    length = _LEN_HINT.get(body.length, _LEN_HINT["moyen"])
    system = (
        "Tu es un expert en prospection commerciale pour les entreprises du bâtiment en France. "
        "Tu rédiges le CORPS d'un courrier de prospection en français, prêt à être posté, adressé "
        "au maître d'ouvrage d'un projet de construction/rénovation détecté via les autorisations "
        "d'urbanisme publiques. Règles STRICTES : commence par « Bonjour, ». N'invente jamais de chiffres "
        "précis ni de fausses références. N'inclus PAS l'en-tête entreprise, ni la date, ni l'adresse du "
        "destinataire, ni la formule de politesse finale, ni la signature (ils sont ajoutés automatiquement). "
        "N'inclus PAS de lien ni de QR code (ajoutés automatiquement). Reste crédible, local et non intrusif "
        "(RGPD)."
    )
    price = ""
    if opp.get("my_lot_high"):
        price = (f"- Fourchette indicative de nos prestations : {_eur_fr(opp['my_lot_low'])} à "
                 f"{_eur_fr(opp['my_lot_high'])}\n")
    prompt = (
        f"Rédige le corps du courrier ({length}), {tone}.\n\n"
        f"Informations :\n"
        f"- Entreprise expéditrice : {company}\n"
        f"- Projet détecté : {opp.get('batiment')} ({opp.get('nature')})\n"
        f"- Commune : {opp.get('commune')} ({opp.get('cp')})\n"
        f"- Surface créée : {opp.get('surf_created') or 'n.c.'} m²\n"
        f"{price}"
        f"\nObjectif : proposer notre accompagnement et inviter à demander une estimation gratuite "
        f"et sans engagement, sans être insistant. Termine le corps par une phrase invitant à la prise "
        f"de contact, SANS formule de politesse finale ni signature."
    )
    from engines.ai import _complete
    try:
        text = await asyncio.wait_for(_complete(system, prompt, feature="radar_letter"), timeout=30)
    except asyncio.TimeoutError:
        raise HTTPException(504, "La rédaction IA a pris trop de temps, réessayez.")
    return {"message": (text or "").strip()}


@router.get("/prospection/{token}/letter.pdf")
async def download_prospection_letter(token: str, user=Depends(current_user)):
    rec = await db.radar_prospections.find_one(
        {"token": token, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Campagne introuvable")
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == rec["opp_id"]), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    public_url = f"{_frontend_url()}/prospection/{token}"
    branding, _ = await _pro_branding_and_user(user["user_id"])
    pdf = _build_prospection_pdf(branding=branding, opp=opp, public_url=public_url,
                                 qr_png=_qr_png_bytes(public_url),
                                 custom_message=rec.get("message", ""))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="courrier-{token}.pdf"'})


# ========= Envoi postal (Merci Facteur) =========

class PostalRecipient(BaseModel):
    nom: str
    societe: str = ""
    adresse1: str
    adresse2: str = ""
    cp: str
    ville: str
    pays: str = "france"


class PostalSendIn(BaseModel):
    recipient: PostalRecipient
    mode: Literal["normal", "suivi", "lrar"] = "normal"


def _sender_from_branding(b: dict, fallback_name: str) -> dict:
    return {"nom": (b.get("company_name") or fallback_name or "Entreprise")[:38], "societe": "",
            "adresse1": (b.get("address") or "Adresse non renseignée")[:38], "adresse2": "",
            "cp": str(b.get("postal_code") or "00000")[:10], "ville": (b.get("city") or "—")[:38],
            "pays": "france"}


@router.get("/postal/status")
async def postal_status(_=Depends(current_user)):
    from engines import mercifacteur as mf
    return {"configured": mf.configured(), "modes": list(mf.MODES)}


@router.get("/postal/price")
async def postal_price(mode: Literal["normal", "suivi", "lrar"] = "normal", _=Depends(current_user)):
    from engines import mercifacteur as mf
    if not mf.configured():
        raise HTTPException(503, "Envoi postal non configuré")
    try:
        res = await mf.postage_price(mode=mode, pages=1)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Tarif indisponible : {str(e)[:120]}")
    aff = ((res.get("affranchissement") or {}).get("FRANCE") or {}).get("amount") or 0
    content_ttc = (res.get("content") or {}).get("totalContentTtc") or 0
    return {"mode": mode, "postage": float(aff), "content_ttc": float(content_ttc),
            "total_ttc": round(float(aff) + float(content_ttc), 2)}


@router.post("/prospection/{token}/postal")
async def postal_send(token: str, body: PostalSendIn, user=Depends(current_user)):
    """Poste physiquement le courrier de prospection via Merci Facteur (facturé au compte)."""
    from engines import mercifacteur as mf
    if not mf.configured():
        raise HTTPException(503, "Envoi postal non configuré")
    rec = await db.radar_prospections.find_one({"token": token, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Campagne introuvable")
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == rec["opp_id"]), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    public_url = f"{_frontend_url()}/prospection/{token}"
    branding, u = await _pro_branding_and_user(user["user_id"])
    if not (branding.get("address") and branding.get("postal_code") and branding.get("city")):
        raise HTTPException(400, "Renseignez l'adresse de votre entreprise (Mon compte → Marque) : elle sert d'expéditeur.")
    pdf = _build_prospection_pdf(branding=branding, opp=opp, public_url=public_url,
                                 qr_png=_qr_png_bytes(public_url), custom_message=rec.get("message", ""))
    recipient = body.recipient.model_dump()
    try:
        res = await mf.send_letter(pdf, sender=_sender_from_branding(branding, u.get("name", "")),
                                   recipient=recipient, mode=body.mode, filename=f"courrier-{token}")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Envoi postal refusé : {str(e)[:200]}")
    envoi = res.get("envoi_id")
    if isinstance(envoi, list):
        envoi = envoi[0] if envoi else None
    doc = {"postal_id": "post_" + secrets.token_hex(5), "token": token, "user_id": user["user_id"],
           "opp_id": rec["opp_id"], "envoi_id": envoi, "mode": body.mode,
           "price": res.get("price"), "recipient": recipient, "status": "submitted",
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.radar_postal.insert_one(dict(doc))
    await db.radar_prospections.update_one({"token": token}, {"$inc": {"postal_count": 1}})
    return doc


@router.get("/prospection/{token}/postal")
async def postal_list(token: str, refresh: bool = False, user=Depends(current_user)):
    from engines import mercifacteur as mf
    sends = await db.radar_postal.find({"token": token, "user_id": user["user_id"]},
                                       {"_id": 0}).sort("created_at", -1).to_list(50)
    if refresh and mf.configured():
        for s in sends:
            if not s.get("envoi_id"):
                continue
            try:
                tr = await mf.tracking(int(s["envoi_id"]))
                upd = {"tracking": tr, "status": (tr.get("statutPrintEnvoi") or tr.get("lastState")
                                                   or s.get("status") or "submitted")}
                s.update(upd)
                await db.radar_postal.update_one({"postal_id": s["postal_id"]}, {"$set": upd})
            except Exception:  # noqa: BLE001
                continue
    return {"sends": sends}



@router.get("/public/prospection/{token}")
async def public_prospection(token: str, request: Request, _=Depends(optional_user)):
    """Landing publique (sans auth) : présente l'entreprise + l'opportunité au prospect."""
    rec = await db.radar_prospections.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Lien introuvable ou expiré")
    ua = (request.headers.get("user-agent") or "").lower()
    bots = ("bot", "crawl", "spider", "facebookexternalhit", "whatsapp", "slack",
            "telegram", "discord", "preview", "embedly", "twitter")
    if not any(b in ua for b in bots):  # ne pas gonfler les ouvertures avec les aperçus de lien
        await db.radar_prospections.update_one(
            {"token": token},
            {"$inc": {"open_count": 1}, "$set": {"last_open_at": datetime.now(timezone.utc).isoformat()}})
    branding, u = await _pro_branding_and_user(rec["user_id"])
    b = branding or {}
    snap = rec.get("opp_snapshot") or {}
    return {
        "token": token,
        "company": {
            "name": b.get("company_name") or u.get("name") or "Entreprise du bâtiment",
            "contact_line": b.get("contact_line"),
            "city": b.get("city"),
            "logo_b64": b.get("logo_b64"),
            "verified": bool(b.get("verified")),
            "certifications": b.get("certifications") or [],
        },
        "opportunity": {
            "commune": snap.get("commune"),
            "batiment": snap.get("batiment"),
            "surf_created": snap.get("surf_created"),
            "my_lot_low": snap.get("my_lot_low"),
            "my_lot_high": snap.get("my_lot_high"),
        },
    }


class ProspectLeadIn(BaseModel):
    name: str = ""
    email: EmailStr
    phone: str = ""
    message: str = ""
    website: str = ""  # honeypot anti-bot (doit rester vide)


_RATE_IDX_READY = False


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _rate_limited(ip: str, *, limit: int = 5, window: int = 600) -> bool:
    """Anti-spam partagé (multi-workers/pods) via MongoDB + index TTL."""
    global _RATE_IDX_READY
    if not _RATE_IDX_READY:
        try:
            await db.radar_rate_hits.create_index("at", expireAfterSeconds=window)
        except Exception:
            pass
        _RATE_IDX_READY = True
    now = datetime.now(timezone.utc)
    await db.radar_rate_hits.insert_one({"ip": ip, "at": now})
    cutoff = now - timedelta(seconds=window)
    n = await db.radar_rate_hits.count_documents({"ip": ip, "at": {"$gte": cutoff}})
    return n > limit


@router.post("/public/prospection/{token}/lead")
async def public_prospection_lead(token: str, body: ProspectLeadIn, request: Request):
    """Capture le prospect → crée un lead assigné au pro (visible dans « Mes demandes »)."""
    # Honeypot : un bot remplira ce champ caché → on ignore silencieusement.
    if (body.website or "").strip():
        return {"ok": True}
    if await _rate_limited(_client_ip(request)):
        raise HTTPException(429, "Trop de demandes, réessayez dans quelques minutes.")
    rec = await db.radar_prospections.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Lien introuvable ou expiré")
    pro_id = rec["user_id"]
    snap = rec.get("opp_snapshot") or {}
    # Anti-doublon : même e-mail déjà capté pour cette campagne → on ne recrée pas
    dup = await db.leads.find_one(
        {"radar_token": token, "email": str(body.email).lower()}, {"_id": 1})
    if dup:
        return {"ok": True, "duplicate": True}
    pro = await db.users.find_one({"user_id": pro_id}, {"_id": 0, "name": 1, "email": 1}) or {}
    now = datetime.now(timezone.utc).isoformat()
    lead = {
        "lead_id": f"lead_{uuid.uuid4().hex[:10]}",
        "user_id": None,
        "name": body.name, "email": str(body.email).lower(), "phone": body.phone,
        "address": snap.get("commune") or "", "postal_code": snap.get("cp") or "",
        "description": (body.message or "").strip()
        or f"Prospect Radar Chantiers — projet « {snap.get('batiment')} » à {snap.get('commune')}.",
        "budget": None, "availability": "",
        "source": "radar_prospection", "radar_token": token, "radar_opp_id": rec.get("opp_id"),
        "project_snapshot": None,
        "status": "nouveau", "created_at": now,
        "assigned_to": pro_id, "assigned_to_name": pro.get("name") or pro.get("email"),
        "assigned_at": now, "auto_assigned": True, "candidates": [], "handling_status": None,
    }
    from routes.leads import _dept_from_text
    lead["department"] = _dept_from_text(lead["postal_code"], lead["address"], lead["description"])
    await db.leads.insert_one(lead)
    await db.radar_prospections.update_one({"token": token}, {"$inc": {"lead_count": 1}})
    try:
        await db.notifications.insert_one({
            "notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": pro_id,
            "type": "lead_assigned", "lead_id": lead["lead_id"],
            "message": f"Nouveau prospect Radar : {body.name or body.email} ({snap.get('commune')})",
            "created_at": now, "read": False})
    except Exception:
        pass
    try:
        from engines.emailer import send_email, wrap_html
        if pro.get("email"):
            html = wrap_html(
                "Nouveau prospect via Radar Chantiers",
                f"<p>Bonjour,</p><p>Un prospect a répondu à votre courrier de prospection pour "
                f"« {snap.get('batiment')} » à {snap.get('commune')} :</p>"
                f"<p><b>{body.name or '—'}</b><br/>{body.email}<br/>{body.phone or ''}</p>"
                f"<p>{lead['description']}</p>",
                cta_url=f"{_frontend_url()}/mes-demandes", cta_label="Voir mes demandes")
            await send_email(pro["email"], "Nouveau prospect Radar Chantiers — ConstruPilot", html)
    except Exception:
        pass
    return {"ok": True}



# =====================================================================
# Suivi des campagnes (ouvertures / scans QR + réponses par courrier)
# =====================================================================

@router.get("/campaigns")
async def list_campaigns(user=Depends(current_user)):
    recs = await db.radar_prospections.find(
        {"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    out = []
    total_opens = total_leads = 0
    for r in recs:
        snap = r.get("opp_snapshot") or {}
        opens = int(r.get("open_count", 0))
        leads = int(r.get("lead_count", 0))
        total_opens += opens
        total_leads += leads
        out.append({
            "token": r["token"], "opp_id": r.get("opp_id"),
            "commune": snap.get("commune"), "batiment": snap.get("batiment"),
            "public_url": f"{_frontend_url()}/prospection/{r['token']}",
            "open_count": opens, "lead_count": leads,
            "created_at": r.get("created_at"), "last_open_at": r.get("last_open_at"),
        })
    return {"count": len(out), "total_opens": total_opens, "total_leads": total_leads,
            "campaigns": out}


# =====================================================================
# Import SITADEL réel (admin) → db.radar_permits (sinon échantillon mock)
# =====================================================================

def _norm_date(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return date.today().isoformat()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(v[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return date.today().isoformat()


def _norm_nature(v: str) -> str:
    t = (v or "").lower()
    if any(k in t for k in ("rénov", "renov", "réhab", "rehab", "transform", "extension", "amenag", "aménag")):
        return "renovation"
    return "neuf"


_MO_ALIASES = {
    "particulier": "PARTICULIER", "personne physique": "PARTICULIER",
    "promoteur": "PROMOTEUR", "sci": "SCI", "entreprise": "ENTREPRISE",
    "société": "ENTREPRISE", "societe": "ENTREPRISE", "bailleur": "BAILLEUR",
    "hlm": "BAILLEUR", "collectivité": "COLLECTIVITE", "collectivite": "COLLECTIVITE",
    "commune": "COLLECTIVITE", "état": "COLLECTIVITE", "etat": "COLLECTIVITE",
}


def _norm_mo(v: str) -> str:
    t = (v or "").strip().lower()
    for k, val in _MO_ALIASES.items():
        if k in t:
            return val
    return "PARTICULIER"


def _pick(row: dict, *keys):
    low = {(k or "").strip().lower(): v for k, v in row.items()}
    for k in keys:
        val = low.get(k)
        if val not in (None, ""):
            return str(val).strip()
    return ""


async def _geocode(query: str):
    try:
        import httpx
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get("https://api-adresse.data.gouv.fr/search/",
                            params={"q": query, "limit": 1})
            feats = (r.json() or {}).get("features") or []
            if feats:
                lon, lat = feats[0]["geometry"]["coordinates"]
                return float(lat), float(lon)
    except Exception:
        pass
    return None


def _to_int(v) -> int:
    try:
        return int(float(str(v).replace(",", ".").strip()))
    except (ValueError, TypeError):
        return 0


async def _row_to_permit(row: dict, idx: int):
    commune = _pick(row, "commune", "comm", "nom_commune", "ville")
    cp = _pick(row, "cp", "code_postal", "postal_code")
    dep = _pick(row, "dep", "departement", "dept") or cp[:2]
    lat = _pick(row, "lat", "latitude")
    lon = _pick(row, "lon", "lng", "longitude")
    adresse = _pick(row, "adresse", "address")
    if lat and lon:
        coords = (float(lat.replace(",", ".")), float(lon.replace(",", ".")))
    else:
        q = " ".join([x for x in [adresse, cp, commune] if x]) or commune
        coords = await _geocode(q) if q else None
    if not coords:
        return None
    num = _pick(row, "num", "num_dau", "numero", "reference")
    pid = _pick(row, "id") or (num.replace(" ", "") if num else f"SITADEL-{idx}")
    typ = _pick(row, "type", "type_dau") or "Permis de construire"
    nature = _norm_nature(_pick(row, "nature", "nature_projet", "nature_projet_declaree", "type"))
    batiment = _pick(row, "batiment", "libelle", "projet", "description") or typ
    return {
        "id": pid, "num": num or pid, "type": typ, "nature": nature,
        "commune": commune or "—", "cp": cp or "", "dep": dep or "",
        "adresse": adresse or "",
        "lat": round(coords[0], 6), "lon": round(coords[1], 6),
        "batiment": batiment,
        "surf_created": _to_int(_pick(row, "surf_created", "surface", "surface_taxable", "surface_creee")),
        "logements": _to_int(_pick(row, "logements", "nb_lgt", "nb_lgt_tot_crees")),
        "date_depot": _norm_date(_pick(row, "date_depot", "date_depot_dau")),
        "date_auth": _norm_date(_pick(row, "date_auth", "date_autorisation", "date_reelle_autorisation")),
        "statut": _pick(row, "statut", "etat") or "Autorisé",
        "mo": _norm_mo(_pick(row, "mo", "maitre_ouvrage", "moa", "demandeur")),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/admin/import-sitadel")
async def import_sitadel(file: UploadFile = File(...), replace: bool = True,
                         _=Depends(admin_user)):
    """Importe un fichier SITADEL (CSV) dans db.radar_permits. Géocodage BAN si lat/lon absents.
    Colonnes reconnues (insensible casse) : commune, cp, dep, lat, lon, adresse, num, type,
    nature, batiment, surf_created, logements, date_depot, date_auth, statut, mo."""
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    delim = ";" if text.splitlines()[0].count(";") >= text.splitlines()[0].count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    inserted, skipped = 0, 0
    MAX_ROWS = 8000
    if replace:
        await db.radar_permits.delete_many({})
    for i, row in enumerate(reader):
        if i >= MAX_ROWS:
            break
        permit = await _row_to_permit(row, i)
        if not permit:
            skipped += 1
            continue
        await db.radar_permits.update_one({"id": permit["id"]}, {"$set": permit}, upsert=True)
        inserted += 1
    total = await db.radar_permits.count_documents({})
    return {"ok": True, "inserted": inserted, "skipped": skipped, "total_in_db": total,
            "source": "db.radar_permits"}


@router.get("/admin/permits/count")
async def permits_count(_=Depends(admin_user)):
    n = await db.radar_permits.count_documents({})
    return {"count": n, "using": "db.radar_permits" if n else "mock (échantillon 95)"}


@router.delete("/admin/permits")
async def clear_permits(_=Depends(admin_user)):
    res = await db.radar_permits.delete_many({})
    return {"ok": True, "deleted": res.deleted_count, "using": "mock (échantillon 95)"}
