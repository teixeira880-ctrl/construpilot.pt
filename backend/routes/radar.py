"""Radar Chantiers — V1 socle : détection d'opportunités depuis données urbanisme (échantillon SITADEL 95),
géoloc + rayon, scoring IA, estimation potentiel, favoris. RGPD : données publiques uniquement."""
import asyncio
import base64
import math
import os
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Literal

from core.db import db
from core.security import admin_user, current_user, optional_user, pro_required
from engines.postal_offer import PostalOffer
from engines.postal_sender import require_sender_branding
from engines.radar_filters import (
    RadarFilters,
    apply_filters,
    classification,
    filter_options,
    query_filters,
)
from engines.radar_zones import (
    DEPARTMENTS,
    department_of,
    filter_zone,
    normalize_departments,
)
from engines.sitadel_permits import window_start
from engines.sitadel_sync import INITIAL_DEPARTMENTS, ensure_sync, sync_status
from engines.sitadel_text import repair_cached_address
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from routes.radar_models import OfficialOpportunity, OfficialOpportunityList

router = APIRouter(prefix="/radar", tags=["radar"])


def _frontend_url() -> str:
    return os.environ["FRONTEND_URL"].rstrip("/")

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
    "terrassement": "Movimentação de terras", "vrd": "VRD", "fondations": "Fondations",
    "gros_oeuvre": "Obra grossa", "maconnerie": "Alvenaria", "charpente": "Carpintaria",
    "couverture": "Cobertura", "etancheite": "Impermeabilização", "isolation": "Isolamento",
    "facade": "Fachada", "menuiserie": "Carpintaria", "plomberie": "Canalização",
    "chauffage": "Aquecimento", "electricite": "Eletricidade", "placo": "Pladur",
    "peinture": "Pintura", "carrelage": "Revestimento cerâmico", "renovation_complete": "Renovação completa",
}

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
    surf = permit.get("surf_created") or 0
    if surf <= 0:
        return [], 0, 0
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
    s += max(0, 30 - (distance_km if distance_km is not None else 30)) / 30 * 30
    days = (datetime.now(timezone.utc).date() - date.fromisoformat(permit["date_auth"])).days if permit.get("date_auth") else 365
    s += max(0, 45 - days) / 45 * 20                  # récence (20)
    surf = permit.get("surf_created") or 0
    s += min(surf, 300) / 300 * 15                     # ampleur (15)
    if any(m in _lots_for(permit) for m in company_metiers):
        s += 20                                        # adéquation métier (20)
    s += min(my_lot_low, 80000) / 80000 * 15           # potentiel (15)
    return int(max(1, min(100, round(s))))


def _build(permit, base, company_metiers):
    dist = _haversine(base["lat"], base["lon"], permit["lat"], permit["lon"]) if permit.get("lat") is not None and permit.get("lon") is not None else None
    lots, tlo, thi = _estimate(permit)
    my = [l for l in lots if l["metier"] in company_metiers] or lots
    my_low = sum(l["low"] for l in my)
    my_high = sum(l["high"] for l in my)
    score = _score(permit, dist, company_metiers, my_low)
    return {**permit, "classification": permit.get("classification") or classification(permit), "dep": department_of(permit), "promoteur": permit.get("promoteur"), "coordonnees_status": permit.get("coordonnees_status") or ("absent" if not permit.get("promoteur") else "partiel"),
            "distance_km": dist, "lots": lots,
            "estimate_low": tlo, "estimate_high": thi,
            "my_lot_low": my_low, "my_lot_high": my_high,
            "score": score, "metier_labels": METIER_LABELS}


async def _get_permits(user=None):
    """Only successfully published official snapshots. Empty really means empty."""
    snapshots = await db.radar_sync.find({"active_run": {"$exists": True}}, {"_id": 0, "active_run": 1}).to_list(None)
    permits = await db.radar_permits.find({"ingest_run": {"$in": [s["active_run"] for s in snapshots]},
        "source.kind": "sitadel_official", "source.verified": True, "is_demo": False,
        "date_auth": {"$gte": window_start(), "$lte": datetime.now(timezone.utc).date().isoformat()}, "statut_code": {"$in": [2, 5]}}, {"_id": 0}).to_list(None)
    for permit in permits:
        repair_cached_address(permit)
        permit["classification"] = classification(permit)
        cj = str((permit.get("promoteur") or {}).get("categorie_juridique") or "")
        if permit.get("mo") == "PARTICULIER" and cj.isdigit() and len(cj) == 4 and not cj.startswith("1"):
            permit["mo"] = _norm_mo(cj)
        elif permit.get("mo") == "PARTICULIER" and permit["classification"]["client_type"] == "inconnu":
            permit["mo"] = "DESCONHECIDO"
    if user:
        contacts = await db.radar_contacts.find({"user_id": user["user_id"], "opp_id": {"$in": [p["id"] for p in permits]}}, {"_id": 0}).to_list(None)
        saved = {c["opp_id"]: c for c in contacts}
        qualifications = await db.radar_qualifications.find({"user_id": user["user_id"], "opp_id": {"$in": [p["id"] for p in permits]}}, {"_id": 0, "user_id": 0}).to_list(None)
        qualified = {item["opp_id"]: item for item in qualifications}
        for permit in permits:
            if permit["id"] in qualified:
                qualification = qualified[permit["id"]]
                permit["qualification"] = qualification
                permit["classification"].update(client_type=qualification["category"], client_source="user_confirmed")
            contact = saved.get(permit["id"])
            if contact and not permit["is_demo"]:
                permit["promoteur"] = contact["contact"]
                permit["contact_provenance"] = contact["provenance"]
            pr = permit.get("promoteur") or {}
            permit["coordonnees_status"] = "complet" if all(pr.get(k) for k in ("nom", "adresse1", "cp", "ville")) else ("partiel" if any(pr.values()) else "absent")
    return permits


async def _profile(user):
    u = await db.users.find_one({"user_id": user["user_id"]},
                                {"_id": 0, "radar_km": 1, "radar_metiers": 1,
                                 "radar_favorites": 1, "radar_base": 1, "radar_zone_mode": 1, "radar_departments": 1, "radar_official_setup": 1, "radar_filters": 1})
    u = u or {}
    return {"km": u.get("radar_km", 30),
            "zone_mode": u.get("radar_zone_mode", "departments") if u.get("radar_official_setup") else "departments",
            "departments": u.get("radar_departments", INITIAL_DEPARTMENTS) if u.get("radar_official_setup") else INITIAL_DEPARTMENTS,
            "metiers": u.get("radar_metiers") or ["gros_oeuvre", "maconnerie", "fondations", "terrassement"],
            "favorites": u.get("radar_favorites") or [],
            "base": u.get("radar_base") or DEFAULT_BASE,
            "filters": RadarFilters.model_validate(u.get("radar_filters") or {}).model_dump()}


@router.get("/profile")
async def get_profile(user=Depends(current_user)):
    p = await _profile(user)
    return {**p, "filter_options": filter_options(), "metier_options": [{"key": k, "label": v} for k, v in METIER_LABELS.items()],
            "department_options": [{"code": code, "name": name} for code, name in sorted(DEPARTMENTS.items())]}


class ProfileIn(BaseModel):
    filters: RadarFilters | None = None
    km: int | None = None
    zone_mode: Literal["radius", "departments"] | None = None
    departments: list[str] | None = None
    metiers: list[str] | None = None
    base: dict | None = None


@router.put("/profile")
async def put_profile(body: ProfileIn, user=Depends(current_user)):
    upd = {}
    if body.filters is not None:
        upd["radar_filters"] = body.filters.model_dump()
    if body.zone_mode is not None:
        upd["radar_zone_mode"] = body.zone_mode
        upd["radar_official_setup"] = True
    if body.departments is not None:
        upd["radar_departments"] = normalize_departments(body.departments)
        upd["radar_official_setup"] = True
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


@router.get("/opportunities", response_model=OfficialOpportunityList)
async def list_opportunities(km: int | None = None, metier: str | None = None, favorites: bool = False,
                             zone_mode: Literal["radius", "departments"] | None = None, departments: str | None = None,
                             work_types: str | None = None, building_types: str | None = None, client_types: str | None = None,
                             page: int = 1, page_size: int = 50,
                             user=Depends(current_user)):
    p = await _profile(user)
    selected_filters = query_filters(p["filters"], work_types=work_types, building_types=building_types, client_types=client_types)
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, "Paginação inválida")
    selected = normalize_departments(departments.split(",")) if departments is not None else p["departments"]
    sync_deps = selected if (zone_mode or p["zone_mode"]) == "departments" else (p["departments"] or INITIAL_DEPARTMENTS)
    await ensure_sync(sync_deps)
    permits = await _get_permits(user)
    items = [_build(pm, p["base"], p["metiers"]) for pm in permits]
    items, zone = filter_zone(items, p, km, zone_mode, departments)
    if metier:
        items = [x for x in items if metier in x["lots"] or any(l["metier"] == metier for l in x["lots"])]
    if favorites:
        items = [x for x in items if x["id"] in p["favorites"]]
    unfiltered_count = len(items)
    items, facets = apply_filters(items, selected_filters)
    for x in items:
        x["is_favorite"] = x["id"] in p["favorites"]
    items.sort(key=lambda x: x["score"], reverse=True)
    points = {}
    for item in items:
        if item.get("lat") is None or item.get("lon") is None:
            continue
        key = (item["lat"], item["lon"])
        if key not in points:
            points[key] = {"lat": item["lat"], "lon": item["lon"], "commune": item.get("map_commune") or f'Commune {item["insee_commune"]}', "id": item["id"], "count": 0, "score": item["score"]}
        points[key]["count"] += 1
    summary = {"detected": len(items), "strong": sum(x["score"] >= 85 for x in items),
               "potential_ttc": sum(x["my_lot_high"] for x in items), "favorites": sum(x["is_favorite"] for x in items)}
    visible_sources = sync_deps
    if zone["zone_mode"] == "radius":
        loaded = await db.radar_sync.find({"active_run": {"$exists": True}}, {"_id": 0, "department": 1}).to_list(None)
        visible_sources = sorted(set(sync_deps + [r["department"] for r in loaded]))
    source_status = await sync_status(visible_sources)
    source_status["radius_scope"] = zone["zone_mode"] == "radius"
    return {"base": p["base"], **zone, "count": len(items), "page": page, "page_size": page_size,
            "opportunities": items[(page - 1) * page_size:page * page_size], "map_points": list(points.values()),
            "stats": summary, "sync": source_status, "data_mode": "official",
            "filters": selected_filters, "facets": facets, "unfiltered_count": unfiltered_count}


@router.get("/opportunities/{opp_id}", response_model=OfficialOpportunity)
async def get_opportunity(opp_id: str, user=Depends(current_user)):
    p = await _profile(user)
    permits = await _get_permits(user)
    pm = next((x for x in permits if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Oportunidade não encontrada")
    o = _build(pm, p["base"], p["metiers"])
    o["is_favorite"] = opp_id in p["favorites"]
    # RGPD : statut de contact selon le type de maître d'ouvrage
    o["contact_status"] = "green" if not pm["is_demo"] and o["coordonnees_status"] == "complet" and pm["mo"] != "PARTICULIER" else "orange"
    o["source"] = pm["source"]
    company = await _company_name(user["user_id"])
    o["suggested_message"] = _default_intro_plain(o, company)
    return o


@router.post("/opportunities/{opp_id}/favorite")
async def toggle_favorite(opp_id: str, user=Depends(current_user)):
    permits = await _get_permits()
    if not any(x["id"] == opp_id for x in permits):
        raise HTTPException(404, "Oportunidade não encontrada")
    p = await _profile(user)
    favs = set(p["favorites"])
    favs.symmetric_difference_update({opp_id})
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"radar_favorites": list(favs)}})
    return {"id": opp_id, "is_favorite": opp_id in favs}


@router.get("/stats")
async def stats(km: int | None = None, zone_mode: Literal["radius", "departments"] | None = None,
                departments: str | None = None, user=Depends(current_user)):
    data = await list_opportunities(km=km, zone_mode=zone_mode, departments=departments, user=user)
    return data["stats"]



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
    return b.get("company_name") or "a nossa empresa"


def _default_intro_plain(opp: dict, company: str) -> str:
    surf_txt = f" (área publicada ≈ {opp.get('surf_created')} m²)" if opp.get("surf_created") else ""
    low, high = opp.get("my_lot_low") or 0, opp.get("my_lot_high") or 0
    price = ""
    if high:
        price = (f'\n\nA título indicativo, os nossos serviços num projeto desta natureza situam-se geralmente entre {_eur_fr(low)} et {_eur_fr(high)} (estimativa preliminar, a afinar em conjunto consoante as suas necessidades).')
    return (
        f"Olá,\n\nVerificámos que foi recentemente emitida uma licença de obras a {opp.get('commune')} para um projeto de {opp.get('batiment')}{surf_txt}.\n\nEmpresa de construção local, a {company} realiza este tipo de obras na sua zona. Teríamos todo o gosto em acompanhá-lo neste projeto — do estudo à orçamentação detalhada, até à execução." + price)


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
    company = b.get("company_name") or "A sua empresa de construção"
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
        f"Estabelecimento {b['siret']}" if b.get("siret") else "",
        f"IVA {b['vat']}" if b.get("vat") else ""] if x])
    if fisc:
        header_lines.append(fisc)
    el.append(Paragraph("<br/>".join(header_lines), small))
    el.append(Spacer(1, 14))

    today = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    el.append(Paragraph(f"À atenção do dono de obra<br/>{opp.get('commune')} ({opp.get('cp')})",
                        body))
    el.append(Spacer(1, 6))
    el.append(Paragraph(f"{opp.get('city') or opp.get('commune')}, le {today}", small))
    el.append(Spacer(1, 14))

    el.append(Paragraph(f"Assunto: o seu projeto «{opp.get('batiment')} »", h1))
    el.append(Spacer(1, 10))

    msg = (custom_message or "").strip() or _default_intro_plain(opp, company)
    for para in msg.split("\n\n"):
        if para.strip():
            el.append(Paragraph(para.strip().replace("\n", "<br/>"), body))
            el.append(Spacer(1, 8))
    el.append(Spacer(1, 2))

    el.append(Paragraph(
        "Para receber <b>gratuitamente e sem compromisso</b> uma primeira estimativa personalizada, digitalize o código QR ao lado ou aceda à ligação indicada. Demora apenas um minuto.",
        body))
    el.append(Spacer(1, 6))

    # QR + lien
    qr_img = Image(BytesIO(qr_png), width=34 * mm, height=34 * mm)
    link_cell = Paragraph(
        f"<b>Peça a sua estimativa:</b><br/><font color='#3f7d54'>{public_url}</font><br/><br/><font size=8 color='#64748B'>Ref. oportunidade {opp.get('id')}</font>", body)
    t = Table([[qr_img, link_cell]], colWidths=[38 * mm, 118 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("LEFTPADDING", (1, 0), (1, 0), 10)]))
    el.append(t)
    el.append(Spacer(1, 14))

    el.append(Paragraph("Aguardando o seu contacto, apresentamos os nossos melhores cumprimentos.", body))
    el.append(Spacer(1, 10))
    el.append(Paragraph(f"<b>{company}</b>", body))
    el.append(Spacer(1, 16))
    el.append(Paragraph(
        "Informação proveniente de dados públicos de licenças de obras. Esta carta é uma proposta comercial. Nos termos do RGPD, pode opor-se a qualquer prospeção contactando-nos.", small))

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
        raise HTTPException(404, "Oportunidade não encontrada")
    if pm.get("is_demo"):
        raise HTTPException(409, "Prospeção desativada para fichas fictícias. Importe uma licença real.")
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
    "formel": "tom formal e profissional, tratamento por «o senhor/a senhora», registo cuidado",
    "chaleureux": "tom caloroso e humano, próximo e tranquilizador, tratamento formal",
    "direct": "tom direto e conciso, orientado para a ação, sem floreados",
    "commercial": "tom comercial e persuasivo, destaca os benefícios e cria vontade",
}
_LEN_HINT = {"court": "cerca de 90 a 130 palavras", "moyen": "cerca de 150 a 220 palavras",
             "long": "cerca de 250 a 320 palavras"}


@router.post("/opportunities/{opp_id}/prospection/ai")
async def ai_letter(opp_id: str, body: AiLetterIn, user=Depends(current_user)):
    """Rédige avec l'IA (Claude) le corps d'un courrier de prospection sur-mesure."""
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == opp_id), None)
    if not pm:
        raise HTTPException(404, "Oportunidade não encontrada")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    company = await _company_name(user["user_id"])
    tone = _TONE_HINT.get(body.tone, _TONE_HINT["formel"])
    length = _LEN_HINT.get(body.length, _LEN_HINT["moyen"])
    system = (
        "És um especialista em prospeção comercial para empresas de construção em Portugal. Redige o CORPO de uma carta de prospeção em português europeu, pronta a ser enviada pelo correio, dirigida ao dono de obra de um projeto de construção/reabilitação detetado através das licenças de obras públicas. Regras ESTRITAS: começa por «Olá,» ou «Exmo.(a) Senhor(a),». Nunca inventes números precisos nem falsas referências. NÃO incluas o cabeçalho da empresa, nem a data, nem a morada do destinatário, nem a fórmula de cortesia final, nem a assinatura (são acrescentados automaticamente). NÃO incluas ligações nem código QR (acrescentados automaticamente). Mantém-te credível, local e não intrusivo (RGPD)."
    )
    price = ""
    if opp.get("my_lot_high"):
        price = (f"- Intervalo indicativo dos nossos serviços: {_eur_fr(opp['my_lot_low'])} à {_eur_fr(opp['my_lot_high'])}\n")
    prompt = (
        f"Redige o corpo da carta ({length}), {tone}.\n\nInformações:\n- Empresa remetente: {company}\n- Projeto detetado: {opp.get('batiment')} ({opp.get('nature')})\n- Commune : {opp.get('commune')} ({opp.get('cp')})\n- Área criada: {opp.get('surf_created') or 'n.c.'} m²\n{price}\nObjetivo: propor o nosso acompanhamento e convidar a pedir uma estimativa gratuita e sem compromisso, sem ser insistente. Termina o corpo com uma frase que convide ao contacto, SEM fórmula de cortesia final nem assinatura."
    )
    from engines.ai import _complete
    try:
        text = await asyncio.wait_for(_complete(system, prompt, feature="radar_letter"), timeout=30)
    except asyncio.TimeoutError:
        raise HTTPException(504, "A redação IA demorou demasiado, tente novamente.")
    return {"message": (text or "").strip()}


@router.get("/prospection/{token}/letter.pdf")
async def download_prospection_letter(token: str, user=Depends(current_user)):
    rec = await db.radar_prospections.find_one(
        {"token": token, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Campanha não encontrada")
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == rec["opp_id"]), None)
    if not pm:
        raise HTTPException(404, "Oportunidade não encontrada")
    if pm.get("is_demo"):
        raise HTTPException(409, "Carta desativada para uma ficha fictícia.")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    public_url = f"{_frontend_url()}/prospection/{token}"
    branding, _ = await _pro_branding_and_user(user["user_id"])
    pdf = _build_prospection_pdf(branding=branding, opp=opp, public_url=public_url,
                                 qr_png=_qr_png_bytes(public_url),
                                 custom_message=rec.get("message", ""))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="carta-{token}.pdf"'})


# ========= Envoi postal (Merci Facteur) =========

class PostalRecipient(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    nom: str = Field(min_length=1, max_length=160)
    societe: str = ""
    adresse1: str = Field(min_length=1, max_length=200)
    adresse2: str = ""
    cp: str = Field(min_length=1, max_length=12)
    ville: str = Field(min_length=1, max_length=100)
    pays: str = "france"


class PostalQuoteIn(BaseModel):
    recipient: PostalRecipient
    mode: Literal["normal", "suivi", "lrar"] = "normal"
    address_source: Literal["contact", "terrain", "manual"] = "manual"


class PostalSendIn(PostalQuoteIn):
    quote_id: str = Field(min_length=16, max_length=100)
    confirmed: Literal[True]


class PostalRecordOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    postal_id: str
    status: str


class PostalHistoryOut(BaseModel):
    sends: list[PostalRecordOut]
    refresh_error: str | None = None


class PostalStatusOut(BaseModel):
    configured: bool
    modes: list[str]
    offer: PostalOffer


class PostalQuoteOut(BaseModel):
    mode: Literal["normal", "suivi", "lrar"]
    pages: int
    postage: float
    content_ttc: float
    total_ttc: float
    currency: str
    quote_id: str
    expires_at: str
    offer: PostalOffer


def _sender_from_branding(b: dict | None, fallback_name: str) -> dict:
    b = require_sender_branding(b)
    return {"nom": (b.get("company_name") or fallback_name or "Empresa")[:38], "societe": "",
            "adresse1": str(b["address"]).strip()[:38], "adresse2": "",
            "cp": str(b["postal_code"]).strip()[:10], "ville": str(b["city"]).strip()[:38],
            "pays": "france"}


@router.get("/postal/status", response_model=PostalStatusOut)
async def postal_status(user=Depends(pro_required)):
    from engines import mercifacteur as mf
    from engines.postal_offer import offer_for
    offer = await offer_for(user)
    return {"configured": mf.configured(), "modes": list(mf.MODES), "offer": offer.model_dump()}


@router.get("/postal/price")
async def postal_price(mode: Literal["normal", "suivi", "lrar"] = "normal", _=Depends(pro_required)):
    from engines import mercifacteur as mf
    from engines.postal_delivery import provider_http_error
    if not mf.configured():
        raise HTTPException(503, "Envio postal não configurado")
    try:
        return await mf.postage_price(mode=mode, pages=1)
    except mf.PostalProviderError as exc:
        raise provider_http_error(exc)


async def _postal_context(token, user):
    from engines import mercifacteur as mf
    if not mf.configured():
        raise HTTPException(503, "Envio postal não configurado")
    rec = await db.radar_prospections.find_one({"token": token, "user_id": user["user_id"]}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Campanha não encontrada")
    permits = await _get_permits()
    pm = next((x for x in permits if x["id"] == rec["opp_id"]), None)
    if not pm:
        raise HTTPException(404, "Oportunidade não encontrada")
    if pm.get("is_demo"):
        raise HTTPException(409, "Envio proibido para uma ficha fictícia.")
    p = await _profile(user)
    opp = _build(pm, p["base"], p["metiers"])
    public_url = f"{_frontend_url()}/prospection/{token}"
    branding, u = await _pro_branding_and_user(user["user_id"])
    branding = require_sender_branding(branding, organization=bool(user.get("organization_id")))
    return rec, opp, public_url, branding, u


@router.post("/prospection/{token}/postal/quote", response_model=PostalQuoteOut)
async def postal_quote(token: str, body: PostalQuoteIn, user=Depends(pro_required)):
    from engines.postal_delivery import context_digest, create_quote
    rec, opp, url, branding, u = await _postal_context(token, user)
    pdf = _build_prospection_pdf(branding=branding, opp=opp, public_url=url,
        qr_png=_qr_png_bytes(url), custom_message=rec.get("message", ""))
    return await create_quote(user=user, user_id=user["user_id"], token=token, opp_id=rec["opp_id"],
        recipient=body.recipient.model_dump(), mode=body.mode, address_source=body.address_source,
        sender=_sender_from_branding(branding, u.get("name", "")), pdf=pdf,
        context_hash=context_digest(rec.get("message", ""), branding))


@router.post("/prospection/{token}/postal", response_model=PostalRecordOut)
async def postal_send(token: str, body: PostalSendIn, user=Depends(pro_required)):
    from engines.postal_delivery import context_digest, deliver
    rec, _, _, branding, _ = await _postal_context(token, user)
    return await deliver(user=user, user_id=user["user_id"], token=token, quote_id=body.quote_id,
        recipient=body.recipient.model_dump(), mode=body.mode,
        context_hash=context_digest(rec.get("message", ""), branding))


class PostalCheckoutIn(PostalSendIn):
    origin_url: str = Field(min_length=8, max_length=300)


class PostalCreditsCheckoutIn(BaseModel):
    pack_id: str = Field(min_length=3, max_length=20)
    origin_url: str = Field(min_length=8, max_length=300)


@router.post("/prospection/{token}/postal/checkout")
async def postal_checkout(token: str, body: PostalCheckoutIn, user=Depends(pro_required)):
    """Paiement Stripe d'un courrier (20 € HT + TVA) : la lettre part dès le paiement confirmé."""
    from engines.postal_billing import create_letter_checkout
    from engines.postal_delivery import context_digest
    rec, _, _, branding, _ = await _postal_context(token, user)
    return await create_letter_checkout(user=user, token=token, quote_id=body.quote_id,
        recipient=body.recipient.model_dump(), mode=body.mode, origin_url=body.origin_url,
        context_hash=context_digest(rec.get("message", ""), branding))


@router.post("/postal/credits/checkout")
async def postal_credits_checkout(body: PostalCreditsCheckoutIn, user=Depends(pro_required)):
    from engines.postal_billing import create_credits_checkout
    return await create_credits_checkout(user=user, pack_id=body.pack_id, origin_url=body.origin_url)


@router.get("/postal/payment/{session_id}")
async def postal_payment(session_id: str, user=Depends(pro_required)):
    from engines.postal_billing import payment_view
    return await payment_view(user, session_id)


@router.get("/postal/sends")
async def postal_sends(limit: int = 100, user=Depends(pro_required)):
    """Tous les courriers de l'utilisateur avec leur étape de suivi (pour le radar)."""
    sends = await db.radar_postal.find({"user_id": user["user_id"]}, {"_id": 0, "tracking": 0, "history": 0}) \
        .sort("created_at", -1).to_list(min(max(limit, 1), 300))
    return {"sends": sends}


@router.post("/postal/tracking/refresh")
async def postal_tracking_refresh(user=Depends(pro_required)):
    """Actualise le suivi Merci Facteur de tous les courriers non finalisés de l'utilisateur."""
    from engines import postal_tracking
    from engines.postal_tracking import FINAL
    docs = await db.radar_postal.find({"user_id": user["user_id"], "status": "submitted", "envoi_id": {"$ne": None},
                                       "stage": {"$nin": list(FINAL)}}, {"_id": 0}).to_list(100)
    refreshed, errors = 0, 0
    for doc in docs:
        try:
            await postal_tracking.refresh_send(doc)
            refreshed += 1
        except Exception:
            errors += 1
    return {"refreshed": refreshed, "errors": errors}


@router.get("/prospection/{token}/postal", response_model=PostalHistoryOut)
async def postal_list(token: str, refresh: bool = False, user=Depends(pro_required)):
    from engines import mercifacteur as mf
    sends = await db.radar_postal.find({"token": token, "user_id": user["user_id"]},
                                       {"_id": 0, "tracking": 0}).sort("created_at", -1).to_list(50)
    refresh_error = None
    if refresh and mf.configured():
        from engines import postal_tracking
        for s in sends:
            if not s.get("envoi_id") or s.get("stage") in postal_tracking.FINAL:
                continue
            try:
                upd = await postal_tracking.refresh_send(s)
                upd.pop("tracking", None)
                s.update(upd)
            except Exception:
                refresh_error = "Não foi possível atualizar o seguimento postal. O último estado conhecido é conservado."
    return {"sends": sends, "refresh_error": refresh_error}



@router.get("/public/prospection/{token}")
async def public_prospection(token: str, request: Request, _=Depends(optional_user)):
    """Landing publique (sans auth) : présente l'entreprise + l'opportunité au prospect."""
    rec = await db.radar_prospections.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Ligação não encontrada ou expirada")
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
            "name": b.get("company_name") or u.get("name") or "Empresa de construção",
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
        raise HTTPException(429, "Demasiados pedidos, tente novamente dentro de alguns minutos.")
    rec = await db.radar_prospections.find_one({"token": token}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Ligação não encontrada ou expirada")
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
        or f"Prospect Radar Chantiers — projet « {snap.get('batiment')}» para {snap.get('commune')}.",
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
            "message": f"Novo potencial cliente Radar: {body.name or body.email} ({snap.get('commune')})",
            "created_at": now, "read": False})
    except Exception:
        pass
    try:
        from engines.emailer import send_email, wrap_html
        if pro.get("email"):
            html = wrap_html(
                "Novo potencial cliente através do Radar de Obras",
                f"<p>Olá,</p><p>Um potencial cliente respondeu à sua carta de prospeção para «{snap.get('batiment')}» para {snap.get('commune')} :</p><p><b>{body.name or '—'}</b><br/>{body.email}<br/>{body.phone or ''}</p><p>{lead['description']}</p>",
                cta_url=f"{_frontend_url()}/mes-demandes", cta_label="Ver os meus pedidos")
            await send_email(pro["email"], "Novo potencial cliente Radar de Obras — ConstruPilot", html)
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
    "promoteur": "PROMOTOR", "sci": "SCI", "entreprise": "ENTREPRISE",
    "société": "ENTREPRISE", "societe": "ENTREPRISE", "bailleur": "SENHORIO",
    "hlm": "SENHORIO", "collectivité": "COLLECTIVITE", "collectivite": "COLLECTIVITE",
    "commune": "COLLECTIVITE", "état": "COLLECTIVITE", "etat": "COLLECTIVITE",
}


def _norm_mo(v: str) -> str:
    t = (v or "").strip().lower()
    if t.isdigit() and len(t) == 4:
        if t.startswith("1"):
            return "PARTICULIER"
        if t in ("6540", "6541", "6542", "6543", "6544"):
            return "SCI"
        return "COLLECTIVITE" if t.startswith("7") else "ENTREPRISE"
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
    adresse = _pick(row, "adresse", "address") or " ".join(x for x in [_pick(row, "adr_num_ter"), _pick(row, "adr_typevoie_ter"),
                                                                       _pick(row, "adr_libvoie_ter"), _pick(row, "adr_lieudit_ter")] if x).strip()
    cp = cp or _pick(row, "adr_cp_ter")
    commune = commune or _pick(row, "adr_localite_ter")
    # contact du demandeur / promoteur (colonnes SITADEL *_DEM ou colonnes libres)
    dem_nom = _pick(row, "denom_dem", "demandeur_nom", "nom_demandeur", "promoteur", "nom_mo", "raison_sociale")
    dem_adr = _pick(row, "demandeur_adresse", "adresse_demandeur") or " ".join(x for x in [_pick(row, "adr_num_dem"), _pick(row, "adr_typevoie_dem"),
                                                                                             _pick(row, "adr_libvoie_dem"), _pick(row, "adr_lieudit_dem")] if x).strip()
    promoteur = {"nom": dem_nom, "siren": _pick(row, "siren_dem", "siren"), "siret": _pick(row, "siret_dem", "siret"),
                 "categorie_juridique": _pick(row, "cj_dem", "cj"), "adresse1": dem_adr,
                 "cp": _pick(row, "adr_cp_dem", "demandeur_cp", "cp_demandeur"), "ville": _pick(row, "adr_localite_dem", "demandeur_ville", "ville_demandeur"),
                 "email": _pick(row, "email_dem", "demandeur_email", "email"), "telephone": _pick(row, "tel_dem", "demandeur_tel", "telephone")}
    promoteur = promoteur if any(promoteur.values()) else None
    if lat and lon:
        coords = (float(lat.replace(",", ".")), float(lon.replace(",", ".")))
    else:
        q = " ".join([x for x in [adresse, cp, commune] if x]) or commune
        coords = await _geocode(q) if q else None
    if not coords:
        return None
    num = _pick(row, "num", "num_dau", "numero", "reference")
    pid = _pick(row, "id") or (num.replace(" ", "") if num else f"SITADEL-{idx}")
    typ = _pick(row, "type", "type_dau") or "Licença de construção"
    nature = _norm_nature(_pick(row, "nature", "nature_projet", "nature_projet_declaree", "type"))
    batiment = _pick(row, "batiment", "libelle", "projet", "description") or typ
    return {
        "id": pid, "num": num or pid, "type": typ, "nature": nature,
        "commune": commune or "—", "cp": cp or "", "dep": department_of({"dep": dep, "cp": cp}),
        "adresse": adresse or "",
        "lat": round(coords[0], 6), "lon": round(coords[1], 6),
        "batiment": batiment,
        "surf_created": _to_int(_pick(row, "surf_created", "surface", "surface_taxable", "surface_creee")),
        "logements": _to_int(_pick(row, "logements", "nb_lgt", "nb_lgt_tot_crees")),
        "date_depot": _norm_date(_pick(row, "date_depot", "date_depot_dau")),
        "date_auth": _norm_date(_pick(row, "date_auth", "date_autorisation", "date_reelle_autorisation")),
        "statut": _pick(row, "statut", "etat") or "Licenciado",
        "mo": _norm_mo(_pick(row, "mo", "maitre_ouvrage", "moa", "demandeur", "cj_dem")),
        "promoteur": promoteur,
        "coordonnees_status": "complet" if promoteur and promoteur["nom"] and promoteur["adresse1"] and promoteur["cp"] and promoteur["ville"]
        else ("partiel" if promoteur else "absent"),
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/admin/import-sitadel")
async def import_sitadel(file: UploadFile = File(...), replace: bool = True,
                         _=Depends(admin_user)):
    raise HTTPException(410, "A importação manual foi substituída pela sincronização oficial. Nenhum ficheiro pode substituir estas licenças.")


@router.get("/admin/permits/count")
async def permits_count(_=Depends(admin_user)):
    n = len(await _get_permits())
    loaded = await db.radar_sync.find({}, {"_id": 0, "department": 1}).to_list(None)
    departments = sorted(set(INITIAL_DEPARTMENTS + [r["department"] for r in loaded]))
    return {"count": n, "using": "Fonte oficial de licenças", "sync": await sync_status(departments)}


@router.delete("/admin/permits")
async def clear_permits(_=Depends(admin_user)):
    raise HTTPException(409, "A eliminação global das licenças oficiais está desativada. Utilize Atualizar para obter a última publicação.")
