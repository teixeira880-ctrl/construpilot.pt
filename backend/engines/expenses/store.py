"""Monetary values use integer millionths; raw provider payloads are never retained."""
import asyncio
import hashlib
import logging
import math
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal

from core.db import db
from engines.expenses.catalog import PROVIDERS, UNITS
from engines.expenses.context import actor

logger = logging.getLogger(__name__)
MICRO = Decimal(1000000)


def now():
    return datetime.now(timezone.utc)


def micros(value):
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError("Non-finite amount")
    return int((number * MICRO).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money(value):
    return format(Decimal(int(value)) / MICRO, "f") if value is not None else None


def identifier(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


def quantities(units):
    output = {}
    for key, value in (units or {}).items():
        if key in UNITS and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
            output[key] = value
    return output


async def upsert_event(*, source, source_id, provider, feature, occurred_at=None, user_id=None, company_id=None,
                       model="", units=None, state="observed", amount=None, currency=None, evidence="unavailable", is_test=False):
    if provider not in PROVIDERS:
        raise ValueError("Unknown expense provider")
    entry_id = identifier(source, source_id)
    record = {"entry_id": entry_id, "provider": provider, "feature": str(feature)[:80], "model": str(model or "")[:120],
              "occurred_at": occurred_at or now(), "user_id": user_id, "company_id": company_id,
              "units": quantities(units), "state": state, "origin": source, "source_ref": str(source_id)[:180],
              "evidence": evidence, "amount_micros": micros(amount) if amount is not None else None,
              "currency": currency if amount is not None else None, "is_test": is_test, "scope": "single", "updated_at": now()}
    # Never overwrite an administrator's confirmation or version during re-import.
    await db.api_expense_events.update_one({"_id": entry_id}, {"$set": record, "$setOnInsert": {"version": 0, "created_at": now()}}, upsert=True)
    return entry_id


async def observe(*, source_id, provider, feature, model="", units=None, state="observed", source="meter"):
    """Best effort: telemetry must never change a provider result or authorization."""
    try:
        await asyncio.wait_for(upsert_event(source=source, source_id=source_id, provider=provider, feature=feature, model=model,
                           units=units, state=state, **actor()), timeout=1)
    except Exception as exc:  # noqa: BLE001 - expense telemetry must not fail business operations.
        logger.warning("Expense observation unavailable (%s)", type(exc).__name__)


async def indexes():
    await db.api_expense_events.create_index([("occurred_at", -1), ("provider", 1)])
    await db.api_expense_events.create_index([("user_id", 1), ("company_id", 1)])
    await db.api_expense_audit.create_index("created_at")


async def audit(admin_id, action, target, previous=None):
    await db.api_expense_audit.insert_one({"actor_id": admin_id, "action": action, "target": target,
                                        "previous": previous, "created_at": now()})