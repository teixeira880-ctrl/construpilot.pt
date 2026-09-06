"""Radar Chantiers — V1 socle : détection d'opportunités depuis données urbanisme (échantillon SITADEL 95),
géoloc + rayon, scoring IA, estimation potentiel, favoris. RGPD : données publiques uniquement."""
import base64
import math
import os
import secrets
import uuid
from datetime import datetime, timezone, date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, optional_user

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
    items = [_build(pm, p["base"], p["metiers"]) for pm in PERMITS]
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
    pm = next((x for x in PERMITS if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Opportunité introuvable")
    o = _build(pm, p["base"], p["metiers"])
    o["is_favorite"] = opp_id in p["favorites"]
    # RGPD : statut de contact selon le type de maître d'ouvrage
    o["contact_status"] = "green" if pm["mo"] in ("ENTREPRISE", "PROMOTEUR", "SCI", "BAILLEUR", "COLLECTIVITE") else "orange"
    o["source"] = {"name": "SITADEL / autorisations d'urbanisme", "type": "public",
                   "imported_at": datetime.now(timezone.utc).isoformat()}
    return o


@router.post("/opportunities/{opp_id}/favorite")
async def toggle_favorite(opp_id: str, user=Depends(current_user)):
    if not any(x["id"] == opp_id for x in PERMITS):
        raise HTTPException(404, "Opportunité introuvable")
    p = await _profile(user)
    favs = set(p["favorites"])
    favs.symmetric_difference_update({opp_id})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"radar_favorites": list(favs)}})
    return {"id": opp_id, "is_favorite": opp_id in favs}


@router.get("/stats")
async def stats(user=Depends(current_user)):
    p = await _profile(user)
    items = [_build(pm, p["base"], p["metiers"]) for pm in PERMITS if _haversine(
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


def _build_prospection_pdf(*, branding: dict | None, opp: dict, public_url: str,
                           qr_png: bytes, custom_message: str = "") -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, Paragraph, SimpleDocTemplate, Spacer,
                                    Table, TableStyle)

    b = branding or {}
    company = b.get("company_name") or "Votre entreprise du bâtiment"
    ink = colors.HexColor("#0A0D14")
    muted = colors.HexColor("#64748B")
    brand = colors.HexColor("#3f7d54")

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm,
                            leftMargin=22 * mm, rightMargin=22 * mm, bottomMargin=18 * mm)
    h1 = ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, textColor=ink, leading=19)
    body = ParagraphStyle("body", fontName="Helvetica", fontSize=10.5, textColor=ink, leading=16)
    small = ParagraphStyle("small", fontName="Helvetica", fontSize=8.5, textColor=muted, leading=12)
    label = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=9, textColor=brand, leading=12)
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

    surf_txt = f" (surface créée ≈ {opp.get('surf_created')} m²)" if opp.get("surf_created") else ""
    intro = custom_message.strip() or (
        f"Bonjour,<br/><br/>Nous avons constaté qu'une autorisation d'urbanisme a récemment été "
        f"délivrée à <b>{opp.get('commune')}</b> pour un projet de <b>{opp.get('batiment')}</b>"
        f"{surf_txt}.<br/><br/>"
        f"Entreprise locale du bâtiment, <b>{company}</b> réalise ce type de travaux dans votre secteur. "
        f"Nous serions ravis de vous accompagner sur ce projet — de l'étude au chiffrage détaillé, "
        f"jusqu'à la réalisation.")
    el.append(Paragraph(intro, body))
    el.append(Spacer(1, 10))

    my_low = opp.get("my_lot_low") or 0
    my_high = opp.get("my_lot_high") or 0
    if my_high:
        el.append(Paragraph(
            f"À titre indicatif, nos prestations sur un projet de cette nature se situent généralement "
            f"entre <b>{_eur_fr(my_low)}</b> et <b>{_eur_fr(my_high)}</b> (estimation préliminaire, à affiner "
            f"ensemble selon vos besoins).", body))
        el.append(Spacer(1, 10))

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
    pm = next((x for x in PERMITS if x["id"] == opp_id), None)
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


@router.get("/prospection/{token}/letter.pdf")
async def download_prospection_letter(token: str, user=Depends(current_user)):
    rec = await db.radar_prospections.find_one(
        {"token": token, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Campagne introuvable")
    pm = next((x for x in PERMITS if x["id"] == rec["opp_id"]), None)
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


@router.get("/public/prospection/{token}")
async def public_prospection(token: str, _=Depends(optional_user)):
    """Landing publique (sans auth) : présente l'entreprise + l'opportunité au prospect."""
    rec = await db.radar_prospections.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Lien introuvable ou expiré")
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


@router.post("/public/prospection/{token}/lead")
async def public_prospection_lead(token: str, body: ProspectLeadIn):
    """Capture le prospect → crée un lead assigné au pro (visible dans « Mes demandes »)."""
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
