"""Routes de l'offre commerciale B2B : catalogue public, consommation, checkout, contact Enterprise.

Garde-fous :
  * Enterprise : jamais de prix, jamais de checkout (400 si demandé).
  * Checkout fermé tant que COMMERCIAL_CHECKOUT_ENABLED != true (503 checkout_not_open).
  * Clé Stripe live refusée tant que STRIPE_LIVE_ALLOWED != true.
  * Le prix est TOUJOURS résolu côté serveur depuis le catalogue (le client n'envoie que
    la clé du plan et l'intervalle) → impossible de modifier le montant depuis le navigateur.
  * success/cancel URL construites depuis une liste blanche d'origines (pas d'open redirect).
"""

import hashlib
import html
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.rate_limit import limiter
from core.security import admin_user, current_user
from engines import commercial_plans as cp
from engines import usage_meter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/commercial", tags=["commercial"])

DEFAULT_ORIGIN = {"fr": "https://construpilot.fr", "pt": "https://construpilot.pt"}
PRICING_PATH = {"fr": "/tarifs", "pt": "/planos"}
DEFAULT_SALES_EMAIL = {"fr": "info@construpilot.fr", "pt": "info@construpilot.pt"}
FREE_MAIL_DOMAINS = {"gmail.com", "hotmail.com", "hotmail.fr", "outlook.com", "outlook.fr", "yahoo.com",
                     "yahoo.fr", "live.com", "live.fr", "icloud.com", "sapo.pt", "free.fr", "orange.fr",
                     "laposte.net", "aol.com", "gmx.com", "proton.me", "protonmail.com"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def allowed_origins() -> list[str]:
    raw = os.environ.get("COMMERCIAL_ALLOWED_ORIGINS") or os.environ.get("APP_ORIGIN") or ""
    items = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    base = DEFAULT_ORIGIN[cp.market()]
    return items or [base, base.replace("https://", "https://www.")]


def safe_origin(requested: str | None) -> str:
    req = (requested or "").strip().rstrip("/")
    allowed = allowed_origins()
    return req if req in allowed else allowed[0]


# ---------------------------------------------------------------- catalogue public

@router.get("/plans")
async def commercial_plans() -> dict:
    cat = cp.public_catalog()
    cat["checkout_open"] = cp.checkout_open() and cp.live_charges_allowed()
    return cat


# ---------------------------------------------------------------- consommation

@router.get("/usage")
async def my_usage(user=Depends(current_user)) -> dict:
    return await usage_meter.snapshot(user)


# ---------------------------------------------------------------- checkout

class CommercialCheckoutIn(BaseModel):
    plan: Literal["solo", "professional", "business", "enterprise"]
    interval: Literal["month", "year"] = "month"
    origin_url: str | None = None


async def _audit(user_id: str | None, action: str, data: dict) -> None:
    try:
        await db.billing_audit.insert_one({"user_id": user_id, "action": action, "data": data,
                                           "at": _now().isoformat()})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"billing_audit insert failed: {e}")


async def _ensure_plan_doc(pid: str) -> dict:
    plan = await db.plans.find_one({"plan_id": pid}, {"_id": 0})
    if plan:
        return plan
    doc = next(d for d in cp.db_plan_docs() if d["plan_id"] == pid)
    await db.plans.update_one({"plan_id": pid}, {"$setOnInsert": doc}, upsert=True)
    return doc


@router.post("/checkout")
async def commercial_checkout(body: CommercialCheckoutIn, user=Depends(current_user)) -> dict:
    if body.plan == "enterprise" or not cp.PLANS[body.plan]["checkout"]:
        raise HTTPException(400, {"code": "contact_sales", "message": "Enterprise : contact commercial uniquement."})
    if not cp.checkout_open():
        raise HTTPException(503, {"code": "checkout_not_open",
                                  "message": "La souscription en ligne ouvre prochainement."})
    if not cp.live_charges_allowed():
        raise HTTPException(503, {"code": "live_charges_blocked",
                                  "message": "Paiements réels non autorisés sur cet environnement."})
    from engines import monetization
    active = await monetization.user_active_plan(user["user_id"])
    ent = (active or {}).get("entitlement") or {}
    if ent.get("kind") == "subscription" and ent.get("stripe_subscription_id"):
        # Un abonnement existe déjà : changement d'offre via le portail (proratisation Stripe),
        # jamais un second abonnement en parallèle.
        raise HTTPException(409, {"code": "use_portal", "current_plan_id": ent.get("plan_id"),
                                  "message": "Vous avez déjà un abonnement : modifiez-le depuis le portail."})
    pid = cp.plan_id(body.plan, body.interval)
    plan = await _ensure_plan_doc(pid)
    expected = cp.price_cents(body.plan, body.interval)
    if plan.get("amount_cents") != expected:  # garde-fou : la DB ne peut pas dériver du catalogue
        await db.plans.update_one({"plan_id": pid}, {"$set": {"amount_cents": expected}})
        plan["amount_cents"] = expected
    origin = safe_origin(body.origin_url)
    extra = {"automatic_tax": {"enabled": True}, "tax_id_collection": {"enabled": True},
             "billing_address_collection": "required",
             "customer_update": {"name": "auto", "address": "auto"}}
    try:
        await monetization.ensure_plan_price(plan)
        result = await monetization.create_checkout(user, plan, origin, None, extra=extra)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("commercial checkout failed")
        raise HTTPException(502, {"code": "payment_provider_error", "message": str(e)[:200]})
    await _audit(user["user_id"], "checkout.created", {"plan_id": pid, "amount_cents": expected,
                                                        "session_id": result.get("session_id")})
    return {"url": result["url"], "session_id": result["session_id"]}


@router.post("/portal")
async def commercial_portal(request: Request, user=Depends(current_user)) -> dict:
    import stripe
    if not user.get("stripe_customer_id"):
        raise HTTPException(404, {"code": "no_billing_account"})
    origin = safe_origin(request.headers.get("origin"))
    session = stripe.billing_portal.Session.create(customer=user["stripe_customer_id"],
                                                   return_url=f"{origin}{PRICING_PATH[cp.market()]}")
    await _audit(user["user_id"], "portal.opened", {})
    return {"url": session.url}


# ---------------------------------------------------------------- contact Enterprise

class EnterpriseLeadIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    company: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str = Field(default="", max_length=40)
    country: str = Field(min_length=2, max_length=60)
    employees: Literal["1-10", "11-50", "51-200", "201-500", "500+"]
    projects: Literal["<20", "20-100", "100-500", "500+"]
    features: list[str] = Field(default_factory=list, max_length=20)
    message: str = Field(default="", max_length=4000)
    consent: bool
    lang: Literal["fr", "pt", "en", "uk"] = "fr"
    website: str = ""          # honeypot : doit rester vide
    elapsed_ms: int = 0        # temps passé sur le formulaire (anti-bot)
    submission_id: str = Field(default="", max_length=64)


ALLOWED_INTEREST = {"takeoff", "quotes", "site", "costs", "teams", "integrations", "erp", "api",
                    "multi_company", "sla", "onboarding", "bim", "other"}
_PHONE_RE = re.compile(r"^[+()\d][\d\s().-]{5,38}$")

_OK_MSG = {"fr": "Merci. Notre équipe commerciale vous recontacte sous 2 jours ouvrés.",
           "pt": "Obrigado. A nossa equipa comercial entrará em contacto consigo em 2 dias úteis.",
           "en": "Thank you. Our sales team will contact you within 2 business days.",
           "uk": "Дякуємо. Наша команда продажів зв'яжеться з вами протягом 2 робочих днів."}


def _lead_email_html(d: dict) -> str:
    e = {k: html.escape(str(v)) if not isinstance(v, list) else ", ".join(html.escape(x) for x in v)
         for k, v in d.items()}
    rows = "".join(f"<tr><td style='padding:4px 12px 4px 0;color:#666'>{k}</td><td>{e.get(k, '')}</td></tr>"
                   for k in ("name", "company", "email", "phone", "country", "employees", "projects",
                             "features", "lang"))
    return (f"<h2>Nouveau contact Enterprise ({html.escape(cp.market().upper())})</h2>"
            f"<table>{rows}</table><p><b>Message</b></p><p style='white-space:pre-wrap'>{e.get('message', '')}</p>")


@router.post("/enterprise-lead")
@limiter.limit("5/hour")
async def enterprise_lead(body: EnterpriseLeadIn, request: Request, response: Response) -> dict:
    lang = body.lang
    # Honeypot / bot trop rapide : réponse identique à un succès, rien n'est stocké ni envoyé.
    if body.website.strip() or (0 < body.elapsed_ms < 2500):
        logger.info("enterprise lead dropped (anti-spam)")
        return {"ok": True, "message": _OK_MSG[lang]}
    if not body.consent:
        raise HTTPException(422, {"code": "consent_required"})
    if body.phone and not _PHONE_RE.match(body.phone.strip()):
        raise HTTPException(422, {"code": "invalid_phone"})
    email = body.email.lower().strip()
    domain = email.split("@", 1)[1]
    features = [f for f in body.features if f in ALLOWED_INTEREST]
    dedup_key = hashlib.sha256(f"{email}|{body.company.strip().lower()}".encode()).hexdigest()[:32]
    since = (_now() - timedelta(hours=24)).isoformat()
    dup = await db.commercial_leads.find_one(
        {"$or": [{"dedup_key": dedup_key, "created_at": {"$gt": since}},
                 *([{"submission_id": body.submission_id}] if body.submission_id else [])]},
        {"_id": 0, "lead_id": 1})
    if dup:
        return {"ok": True, "lead_id": dup["lead_id"], "duplicate": True, "message": _OK_MSG[lang]}
    doc = {
        "lead_id": "lead_" + secrets.token_hex(8), "market": cp.market(), "source": "pricing_enterprise",
        "name": body.name.strip(), "company": body.company.strip(), "email": email,
        "phone": body.phone.strip(), "country": body.country.strip(), "employees": body.employees,
        "projects": body.projects, "features": features, "message": body.message.strip(), "lang": lang,
        "professional_email": domain not in FREE_MAIL_DOMAINS,
        "consent": {"given": True, "at": _now().isoformat(), "policy": "/confidentialite"
                    if cp.market() == "fr" else "/privacidade"},
        "dedup_key": dedup_key, "submission_id": body.submission_id or None,
        "status": "new", "created_at": _now().isoformat(),
        # RGPD : durée de conservation d'un prospect non converti (3 ans, recommandation CNIL).
        "retain_until": (_now() + timedelta(days=3 * 365)).isoformat(),
    }
    await db.commercial_leads.insert_one(dict(doc))
    to = os.environ.get("COMMERCIAL_SALES_EMAIL") or DEFAULT_SALES_EMAIL[cp.market()]
    notified = False
    try:
        from engines import emailer
        await emailer.send_email(to, f"[Enterprise] {doc['company'][:80]}", _lead_email_html(doc),
                                 reply_to=email)
        notified = True
    except Exception as e:  # noqa: BLE001 — le lead est stocké même si l'e-mail échoue
        logger.warning(f"enterprise lead notification failed: {e}")
    await db.commercial_leads.update_one({"lead_id": doc["lead_id"]}, {"$set": {"notified": notified}})
    return {"ok": True, "lead_id": doc["lead_id"], "message": _OK_MSG[lang]}


# ---------------------------------------------------------------- options (admin, après accord client)

class AddonCreditIn(BaseModel):
    account_id: str = Field(min_length=3, max_length=80)
    addon: Literal["pages_500", "extra_seat"]
    quantity: int = Field(ge=1, le=50)
    customer_consent_ref: str = Field(min_length=3, max_length=200)  # n° de devis / e-mail d'accord


@router.post("/admin/addons/credit")
async def credit_addon(body: AddonCreditIn, admin=Depends(admin_user)) -> dict:
    """Crédite une option vendue. Exige une référence d'accord explicite du client : aucune option
    n'est jamais ajoutée ni facturée automatiquement."""
    if body.addon == "pages_500":
        res = await usage_meter.credit_pages_pack(body.account_id, body.quantity, admin["user_id"])
    else:
        owner = await db.organizations.find_one({"owner_user_id": body.account_id}, {"_id": 0, "org_id": 1})
        if not owner:
            raise HTTPException(404, {"code": "no_organization"})
        pid, _ = await usage_meter.account_plan({"owner_user_id": body.account_id, "org_id": None})
        parsed = cp.parse_plan_id(pid)
        if not parsed or parsed[0] not in cp.ADDONS["extra_seat"]["available_for"]:
            raise HTTPException(400, {"code": "addon_not_available_for_plan"})
        await db.organizations.update_one({"org_id": owner["org_id"]}, {"$inc": {"extra_seats": body.quantity}})
        res = {"extra_seats_added": body.quantity}
    await _audit(admin["user_id"], "addon.credited", {**body.model_dump(), **res})
    return {"ok": True, **res}
