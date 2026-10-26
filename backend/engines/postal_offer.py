"""Company-wide postal allowance: 20 launch letters paid by ConstruPilot, then prepaid credits or Stripe checkout.

One Mongo document per company holds an atomic counter: `count` demo slots consumed, `credits` prepaid
letters, `sends` details. Unknown outcomes keep their slot; confirmed rejections release it.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.db import db
from core.permissions import require_feature

log = logging.getLogger(__name__)

DEMO_LIMIT = 20
QUOTA_ALERT_AT = 15
UNIT_NET_CENTS = 2000
VAT_RATE = 20
ACTIVE = ("reserved", "used", "unknown")
PACKS = {"pack5": 5, "pack10": 10}
Kind = Literal["demo", "credit", "paid"]


def gross(net_cents: int) -> int:
    return round(net_cents * (100 + VAT_RATE) / 100)


class PostalPack(BaseModel):
    pack_id: str
    letters: int
    amount_net_cents: int
    amount_gross_cents: int


class PostalOffer(BaseModel):
    phase: Literal["demo", "paid"]
    scope: Literal["company"] = "company"
    demo_limit: int = DEMO_LIMIT
    demo_remaining: int
    remaining: int
    used: int = 0
    credits: int = 0
    eligible: bool = True
    next_kind: Literal["demo", "credit", "checkout"]
    status: Literal["available", "reserved", "used", "unknown"]
    customer_amount_cents: int
    customer_amount_net_cents: int
    vat_rate: int = VAT_RATE
    currency: Literal["EUR"] = "EUR"
    operator_pays_postage: bool
    paid_enabled: Literal[True] = True
    unit_price_net_cents: int = UNIT_NET_CENTS
    unit_price_gross_cents: int = gross(UNIT_NET_CENTS)
    packs: list[PostalPack] = [PostalPack(pack_id=k, letters=n, amount_net_cents=n * UNIT_NET_CENTS,
                                          amount_gross_cents=gross(n * UNIT_NET_CENTS)) for k, n in PACKS.items()]
    payment_provider: Literal["stripe"] = "stripe"


def company_key(user: dict) -> str:
    require_feature(user, "dashboard")
    org_id = user.get("organization_id")
    return f"org:{org_id}" if org_id else f"solo:{user['user_id']}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _exhausted(message):
    return HTTPException(409, {"code": "postal_demo_exhausted", "message": message})


async def _migrate_legacy(key: str):
    """Single-letter documents ({_id, postal_id, status}) become counter documents."""
    legacy = await db.postal_demo_allowances.find_one({"_id": key, "count": {"$exists": False}})
    if not legacy:
        return
    entry = {k: legacy.get(k) for k in ("postal_id", "user_id", "opp_id", "status", "created_at", "updated_at") if legacy.get(k)}
    entry["kind"] = "demo"
    active = entry.get("status") in ACTIVE
    await db.postal_demo_allowances.update_one({"_id": key, "count": {"$exists": False}}, {
        "$set": {"count": 1 if active else 0, "credits": 0, "sends": [entry] if active else [], "migrated_at": _now()},
        "$unset": {"postal_id": "", "user_id": "", "opp_id": "", "status": ""}})


def _offer(record: dict) -> PostalOffer:
    used = max(0, int(record.get("count") or 0))
    credits = max(0, int(record.get("credits") or 0))
    demo_remaining = max(0, DEMO_LIMIT - used)
    statuses = {s.get("status") for s in record.get("sends") or []}
    if demo_remaining:
        kind, status = "demo", "available"
    elif credits:
        kind, status = "credit", "available"
    else:
        kind = "checkout"
        status = "reserved" if "reserved" in statuses else "unknown" if "unknown" in statuses else "used"
    amount_net = UNIT_NET_CENTS if kind == "checkout" else 0
    return PostalOffer(phase="demo" if demo_remaining else "paid", demo_remaining=demo_remaining,
                       remaining=demo_remaining + credits, used=used, credits=credits, next_kind=kind, status=status,
                       customer_amount_cents=gross(amount_net), customer_amount_net_cents=amount_net,
                       operator_pays_postage=kind == "demo")


async def offer_for(user: dict) -> PostalOffer:
    key = company_key(user)
    await _migrate_legacy(key)
    record = await db.postal_demo_allowances.find_one({"_id": key}, {"_id": 0, "count": 1, "credits": 1, "sends": 1}) or {}
    return _offer(record)


async def require_available(user: dict) -> PostalOffer:
    """Quotes are always allowed: a company without free letters or credits pays per letter."""
    return await offer_for(user)


async def _push_entry(key: str, entry: dict, query: dict, update: dict) -> bool:
    result = await db.postal_demo_allowances.update_one({"_id": key, **query}, {**update, "$push": {"sends": entry}})
    return bool(result.matched_count)


async def reserve(user: dict, postal_id: str, opp_id: str, kind: Kind = "demo", session_id: str | None = None) -> None:
    key = company_key(user)
    await _migrate_legacy(key)
    entry = {"postal_id": postal_id, "user_id": user["user_id"], "opp_id": opp_id, "kind": kind,
             "status": "reserved", "created_at": _now()}
    if session_id:
        entry["session_id"] = session_id
    if kind == "demo":
        if await _push_entry(key, entry, {"count": {"$lt": DEMO_LIMIT}}, {"$inc": {"count": 1}}):
            await _maybe_alert_admins(user, key)
            return
        try:
            await db.postal_demo_allowances.insert_one({"_id": key, "count": 1, "credits": 0, "sends": [entry], "created_at": _now()})
        except DuplicateKeyError:
            raise _exhausted(f'Os {DEMO_LIMIT} envios oferecidos à sua empresa já foram utilizados ou reservados. Nenhum novo envio foi desencadeado.')
        return
    if kind == "credit":
        if not await _push_entry(key, entry, {"credits": {"$gt": 0}}, {"$inc": {"credits": -1}}):
            raise HTTPException(409, {"code": "postal_payment_required", "message":
                "Nenhum crédito de correio disponível. Pague este envio ou compre um pack de créditos."})
        return
    if not await _push_entry(key, entry, {}, {}):
        try:
            await db.postal_demo_allowances.insert_one({"_id": key, "count": 0, "credits": 0, "sends": [entry], "created_at": _now()})
        except DuplicateKeyError:
            await _push_entry(key, entry, {}, {})


async def settle(user: dict, postal_id: str, status: str) -> None:
    key = company_key(user)
    record = await db.postal_demo_allowances.find_one({"_id": key, "sends.postal_id": postal_id}, {"_id": 0, "sends": 1})
    entry = next((s for s in (record or {}).get("sends") or [] if s.get("postal_id") == postal_id), None)
    if not entry:
        return
    kind = entry.get("kind", "demo")
    query = {"_id": key, "sends.postal_id": postal_id}
    if status == "rejected":
        if kind == "demo":
            await db.postal_demo_allowances.update_one(query, {"$inc": {"count": -1}, "$pull": {"sends": {"postal_id": postal_id}}})
        elif kind == "credit":
            await db.postal_demo_allowances.update_one(query, {"$inc": {"credits": 1}, "$pull": {"sends": {"postal_id": postal_id}}})
        else:
            # A paid letter refused by the provider is compensated with one prepaid credit.
            await db.postal_demo_allowances.update_one(query, {"$inc": {"credits": 1}, "$set": {
                "sends.$.status": "rejected", "sends.$.compensated_credit": True, "sends.$.updated_at": _now()}})
        return
    await db.postal_demo_allowances.update_one(query, {"$set": {
        "sends.$.status": "used" if status == "submitted" else "unknown", "sends.$.updated_at": _now()}})


async def add_credits(user: dict, letters: int, *, session_id: str, reason: str = "pack_purchase") -> int:
    key = company_key(user)
    await _migrate_legacy(key)
    purchase = {"purchase_id": "pcr_" + secrets.token_hex(6), "letters": letters, "session_id": session_id,
                "reason": reason, "user_id": user["user_id"], "created_at": _now()}
    result = await db.postal_demo_allowances.update_one({"_id": key}, {"$inc": {"credits": letters}, "$push": {"credit_purchases": purchase}})
    if not result.matched_count:
        try:
            await db.postal_demo_allowances.insert_one({"_id": key, "count": 0, "credits": letters, "sends": [],
                                                        "credit_purchases": [purchase], "created_at": _now()})
        except DuplicateKeyError:
            await db.postal_demo_allowances.update_one({"_id": key}, {"$inc": {"credits": letters}, "$push": {"credit_purchases": purchase}})
    record = await db.postal_demo_allowances.find_one({"_id": key}, {"_id": 0, "credits": 1})
    return int((record or {}).get("credits") or 0)


async def _company_label(user: dict) -> str:
    org_id = user.get("organization_id")
    if org_id:
        org = await db.organizations.find_one({"org_id": org_id}, {"_id": 0, "name": 1})
        if org and org.get("name"):
            return org["name"]
    return user.get("name") or user.get("email") or user["user_id"]


async def _maybe_alert_admins(user: dict, key: str) -> None:
    """Fires once per company when the demo quota reaches QUOTA_ALERT_AT letters."""
    flagged = await db.postal_demo_allowances.update_one(
        {"_id": key, "count": {"$gte": QUOTA_ALERT_AT}, "quota_alert_sent": {"$ne": True}},
        {"$set": {"quota_alert_sent": True, "quota_alert_at": _now()}})
    if not flagged.matched_count:
        return
    try:
        label = await _company_label(user)
        message = (f'Quota de correio: {label} atingiu {QUOTA_ALERT_AT}/{DEMO_LIMIT} envios oferecidos (custo suportado pelo ConstruPilot). Passagem a pagamento após o {DEMO_LIMIT}e envoi.')
        admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1, "email": 1}).to_list(50)
        for admin in admins:
            await db.notifications.insert_one({"notif_id": "n_" + secrets.token_hex(5), "user_id": admin["user_id"],
                "type": "postal_quota_alert", "company_key": key, "message": message, "url": "/admin?tab=postal",
                "created_at": _now(), "read": False})
        await _email_admins(admins, label, message)
    except Exception:
        log.exception("Postal quota alert failed for %s", key)


async def _email_admins(admins: list[dict], label: str, message: str) -> None:
    from engines.emailer import send_email
    html = (f'<p>Olá,</p><p>{message}</p><p>Empresa: <b>{label}</b><br>Preço após a quota: {UNIT_NET_CENTS / 100:.2f} € s/ IVA por envio ({gross(UNIT_NET_CENTS) / 100:.2f} € c/ IVA) ou packs de créditos.</p><p>— ConstruPilot</p>')
    for admin in admins:
        if admin.get("email"):
            try:
                await send_email(admin["email"], f'⚠️ Quota de correio {QUOTA_ALERT_AT}/{DEMO_LIMIT} — {label}', html)
            except Exception as exc:
                log.warning("Quota alert email failed for %s: %s", admin["email"], exc)
