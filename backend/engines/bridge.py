"""Agent Ponte B2B↔B2C : croise chaque lead (particulier) avec la base d'artisans
(collecte Apify Google Maps) du même département et envoie une invitation ciblée.

Déclenchement : temps réel (à la création du lead) + lot quotidien (filet de sécurité).
Anti-spam / RGPD : plafond par lead, cooldown par artisan, lien de désinscription,
identification de l'entreprise. Le token Apify n'intervient pas ici (base déjà peuplée).
"""
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DEFAULTS = {"enabled": True, "min_budget": 3000, "max_per_lead": 5, "cooldown_days": 30,
            "founder_name": "", "founder_phone": "", "site_url": ""}
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _frontend() -> str:
    return (os.getenv("FRONTEND_URL") or "https://construpilot.pt").rstrip("/")


def _dept(postal_code: str | None) -> str | None:
    m = re.search(r"\b(\d{5})\b", postal_code or "")
    if not m:
        return None
    cp = m.group(1)
    d = cp[:2]
    if d == "20":
        return "2A" if cp[:3] in ("200", "201") else "2B"
    if d in ("97", "98"):
        return cp[:3]
    return d


async def get_settings() -> dict:
    from core.db import db
    doc = await db.app_settings.find_one({"key": "bridge"}, {"_id": 0}) or {}
    return {**DEFAULTS, **{k: doc[k] for k in DEFAULTS if k in doc}}


async def set_settings(patch: dict) -> dict:
    from core.db import db
    clean = {k: patch[k] for k in DEFAULTS if k in patch and patch[k] is not None}
    await db.app_settings.update_one({"key": "bridge"}, {"$set": {"key": "bridge", **clean}}, upsert=True)
    return await get_settings()


# ---------------------------------------------------------------- base artisans

def _artisan_from_item(it: dict, source: str) -> dict | None:
    """Mappe un résultat Google Maps (compass/crawler-google-places) → fiche artisan.

    Ne retourne une fiche que si un e-mail est disponible (nécessaire pour le contact).
    """
    emails = it.get("emails") or []
    email = ""
    if isinstance(emails, list) and emails:
        email = str(emails[0]).lower()
    if not email:
        found = _EMAIL_RE.findall(str(it.get("website") or "") + " " + str(it.get("email") or ""))
        email = found[0].lower() if found else ""
    if not email:
        return None
    postal = str(it.get("postalCode") or it.get("postal_code") or "")
    cats = it.get("categories") or []
    trade = it.get("categoryName") or (cats[0] if cats else "") or ""
    return {
        "email": email,
        "name": str(it.get("title") or it.get("name") or "")[:160],
        "city": str(it.get("city") or "")[:120],
        "postal_code": postal[:10],
        "department": _dept(postal) or _dept(str(it.get("address") or "")),
        "trade": str(trade)[:120],
        "phone": str(it.get("phone") or it.get("phoneNumber") or "")[:40],
        "website": str(it.get("website") or it.get("url") or "")[:300],
        "source": source,
    }


async def upsert_artisans_from_items(items: list[dict], source: str = "apify") -> int:
    """Alimente la collection `artisans` depuis des résultats Apify. Déduplique par e-mail."""
    from core.db import db
    n = 0
    for it in items or []:
        a = _artisan_from_item(it, source)
        if not a or not a.get("department"):
            continue
        existing = await db.artisans.find_one({"email": a["email"]}, {"_id": 1})
        if existing:
            await db.artisans.update_one({"email": a["email"]}, {"$set": {
                k: a[k] for k in ("name", "city", "postal_code", "department", "trade", "phone", "website")
                if a[k]}})
        else:
            await db.artisans.insert_one({
                **a, "opt_out": False, "unsub_token": secrets.token_urlsafe(16),
                "last_contacted_at": None, "created_at": _now().isoformat()})
            n += 1
    return n


# ---------------------------------------------------------------- e-mail artisan

_TRADE_MAP = {
    "salle de bain": "remodelação de casa de banho", "sdb": "remodelação de casa de banho",
    "cuisine": "remodelação de cozinha", "toiture": "obras de cobertura", "couverture": "obras de cobertura",
    "maçon": "maçonnerie", "maconnerie": "maçonnerie", "façade": "reabilitação de fachada",
    "isolation": "isolation", "électricit": "électricité", "plomberie": "plomberie",
    "peinture": "peinture", "carrelage": "carrelage", "menuiserie": "menuiserie",
    "extension": "extension", "rénovation": "rénovation", "renovation": "rénovation",
}


def _work_type(lead: dict, snap: dict) -> str:
    """Déduit un type de travaux lisible depuis la demande (pour l'objet de l'e-mail)."""
    hay = " ".join(str(x) for x in [
        lead.get("description", ""), snap.get("name", ""),
        " ".join(snap.get("lots", []) or [])]).lower()
    for key, label in _TRADE_MAP.items():
        if key in hay:
            return label
    name = snap.get("name") or (snap.get("lots") or [None])[0]
    if name:
        return str(name)[:48]
    return "rénovation"


def _outreach_subject(work_type: str, city: str) -> str:
    return f'Uma obra de {work_type} à {city} para si (sem comissão)'


def _outreach_html(artisan_name: str, city: str, work_type: str, budget: int | None,
                   founder_name: str, founder_phone: str, site_url: str, unsub_url: str) -> str:
    hello = f'Olá {artisan_name},' if artisan_name else "Bom dia,"
    montant = f"{budget:,.0f} €".replace(",", " ") if budget else "não indicado"
    signup = f"{site_url or _frontend()}/inscription?utm_source=email&utm_medium=bridge&utm_campaign=lead_match"
    site = site_url or _frontend()
    phone_line = (f'ou ligue-me para o <b>{founder_phone}</b> ' if founder_phone else "")
    signer = founder_name or "A equipa ConstruPilot"
    p = 'style="margin:0 0 14px"'
    return f'''<!doctype html><html><body style="margin:0;background:#f5f5f7;font-family:Arial,Helvetica,sans-serif;color:#1a1d20">\n<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:28px 0"><tr><td align="center">\n<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">\n<tr><td style="padding:22px 28px 10px;border-bottom:3px solid #FF5A00">\n  <div style="font-size:20px;font-weight:800">ConstruPilot</div></td></tr>\n<tr><td style="padding:26px 28px;font-size:15px;line-height:1.65;color:#1a1d20">\n  <p {p}>{hello}</p>\n  <p {p}>Um particular situado em <b>{city}</b> acabou de utilizar a nossa plataforma para estimar\n  obras de <b>{work_type}</b>. O orçamento estimado é de cerca de <b>{montant}</b>.</p>\n  <p {p}>Como estamos a lançar a nossa rede na sua zona, procuro um profissional fiável para lhe\n  transferir este contacto. <b>Não cobro nenhuma comissão sobre a obra.</b></p>\n  <p {p}>A única condição?</p>\n  <p {p}>Criar uma conta gratuita no nosso software <a href="{signup}" style="color:#FF5A00;font-weight:bold">ConstruPilot</a>\n  e utilizar a nossa ferramenta para enviar o seu orçamento final a este cliente. Demora 10 minutos e permite-lhe\n  testar o nosso sistema (que faz a medição automática em planta e gera orçamentos conformes).</p>\n  <p {p}>Este tipo de obra interessa-lhe neste momento?</p>\n  <p {p}>Se sim, responda simplesmente a este e-mail {phone_line}para que lhe transfira os contactos\n  do cliente e lhe mostre como enviar o orçamento.</p>\n  <p style="margin:22px 0 2px">Até breve,</p>\n  <p style="margin:0;font-weight:bold">{signer}</p>\n  <p style="margin:0;color:#64748B;font-size:13px">Fundador, ConstruPilot</p>\n  <p style="margin:2px 0 0"><a href="{site}" style="color:#FF5A00;font-size:13px">{site.replace('https://', '').replace('http://', '')}</a></p>\n</td></tr>\n<tr><td style="padding:14px 28px;background:#fafafa;color:#94A3B8;font-size:11px;line-height:1.5">\n  ConstruPilot — plataforma de estimativa e contacto entre clientes e profissionais da construção · Patente FR261104.\n  Recebe este e-mail porque o seu estabelecimento está referenciado publicamente na sua zona.\n  <a href="{unsub_url}" style="color:#94A3B8">Cancelar a subscrição</a>.\n</td></tr>\n</table></td></tr></table></body></html>'''


# ---------------------------------------------------------------- agent

async def process_lead_bridge(lead: dict) -> dict:
    """Croise un lead avec les artisans du même département et envoie les invitations."""
    from core.db import db
    from engines.emailer import send_email

    st = await get_settings()
    if not st["enabled"]:
        return {"skipped": "disabled"}
    if lead.get("bridge_processed_at"):
        return {"skipped": "already_processed"}

    snap = lead.get("project_snapshot") or {}
    budget = lead.get("budget") or snap.get("estimation")
    try:
        budget = float(budget) if budget is not None else None
    except (TypeError, ValueError):
        budget = None
    if budget is not None and budget < st["min_budget"]:
        await db.leads.update_one({"lead_id": lead["lead_id"]},
                                  {"$set": {"bridge_processed_at": _now().isoformat(),
                                            "bridge_result": "below_budget"}})
        return {"skipped": "below_budget"}

    dept = lead.get("department") or _dept(lead.get("postal_code")) or _dept(lead.get("address"))
    if not dept:
        await db.leads.update_one({"lead_id": lead["lead_id"]},
                                  {"$set": {"bridge_processed_at": _now().isoformat(),
                                            "bridge_result": "no_department"}})
        return {"skipped": "no_department"}

    cutoff = (_now() - timedelta(days=st["cooldown_days"])).isoformat()
    candidates = await db.artisans.find({
        "department": dept, "opt_out": {"$ne": True},
        "$or": [{"last_contacted_at": None}, {"last_contacted_at": {"$lt": cutoff}}],
    }, {"_id": 0}).limit(st["max_per_lead"] * 3).to_list(st["max_per_lead"] * 3)

    city_label = snap.get("city") or lead.get("city") or (f'a sua zona ({dept})')
    work_type = _work_type(lead, snap)
    subject = _outreach_subject(work_type, city_label)
    sent = 0
    for a in candidates:
        if sent >= st["max_per_lead"]:
            break
        already = await db.artisan_outreach.find_one(
            {"artisan_email": a["email"], "lead_id": lead["lead_id"]}, {"_id": 1})
        if already:
            continue
        unsub = f"{_frontend_backend_unsub(a['unsub_token'])}"
        try:
            await send_email(a["email"], subject,
                             _outreach_html(a.get("name", ""), city_label, work_type,
                                            int(budget) if budget else None,
                                            st["founder_name"], st["founder_phone"],
                                            st["site_url"], unsub),
                             from_name=st["founder_name"] or "ConstruPilot")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Bridge email failed {a['email']}: {e}")
            continue
        await db.artisan_outreach.insert_one({
            "artisan_email": a["email"], "lead_id": lead["lead_id"], "department": dept,
            "sent_at": _now().isoformat()})
        await db.artisans.update_one({"email": a["email"]},
                                     {"$set": {"last_contacted_at": _now().isoformat()}})
        sent += 1

    await db.leads.update_one({"lead_id": lead["lead_id"]},
                              {"$set": {"bridge_processed_at": _now().isoformat(),
                                        "bridge_result": f"sent:{sent}"}})
    return {"lead_id": lead["lead_id"], "department": dept, "sent": sent}


def _frontend_backend_unsub(token: str) -> str:
    """Lien public de désinscription (servi par le backend)."""
    base = (os.getenv("REACT_APP_BACKEND_URL") or _frontend()).rstrip("/")
    return f"{base}/api/bridge/u/{token}"


async def run_bridge_batch(limit: int = 200) -> dict:
    """Traite les leads récents non encore traités par l'agent (filet de sécurité quotidien)."""
    from core.db import db
    st = await get_settings()
    if not st["enabled"]:
        return {"skipped": "disabled"}
    since = (_now() - timedelta(days=3)).isoformat()
    leads = await db.leads.find({
        "created_at": {"$gte": since}, "bridge_processed_at": {"$exists": False},
        "email": {"$exists": True},
    }, {"_id": 0}).limit(limit).to_list(limit)
    total_sent = 0
    for lead in leads:
        res = await process_lead_bridge(lead)
        total_sent += res.get("sent", 0)
    out = {"leads": len(leads), "emails_sent": total_sent, "at": _now().isoformat()}
    logger.info(f"Bridge batch: {out}")
    return out


async def bridge_stats() -> dict:
    from core.db import db
    week = (_now() - timedelta(days=7)).isoformat()
    by_dept = await db.artisans.aggregate([
        {"$match": {"opt_out": {"$ne": True}}},
        {"$group": {"_id": "$department", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 15}]).to_list(15)
    return {
        "artisans_total": await db.artisans.count_documents({}),
        "artisans_active": await db.artisans.count_documents({"opt_out": {"$ne": True}}),
        "artisans_by_department": [{"department": d["_id"], "count": d["n"]} for d in by_dept if d["_id"]],
        "outreach_total": await db.artisan_outreach.count_documents({}),
        "outreach_last_7d": await db.artisan_outreach.count_documents({"sent_at": {"$gte": week}}),
        "leads_processed": await db.leads.count_documents({"bridge_processed_at": {"$exists": True}}),
    }
