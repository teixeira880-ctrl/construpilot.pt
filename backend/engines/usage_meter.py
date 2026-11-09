"""Mesure de consommation et application des limites des offres commerciales (2026-11).

Compte de facturation = propriétaire de l'organisation (les membres consomment sur le
compte de leur entreprise), sinon l'utilisateur lui-même.

Mode (variable ``PLAN_LIMITS_MODE``) :
  * ``off``      — rien n'est mesuré ni bloqué ;
  * ``observe``  — (défaut) on mesure, on journalise les dépassements, on ne bloque JAMAIS ;
  * ``enforce``  — on mesure et on bloque (HTTP 402) au-delà de la limite.

Seuls les comptes sur une offre commerciale (Solo/Professional/Business/Enterprise) ont des
limites : les plans historiques et le mode promo gratuit ne sont jamais bridés ici.
La consommation de pages est idempotente par référence (un même import n'est compté qu'une fois).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException

from core.db import db
from engines import commercial_plans as cp

logger = logging.getLogger(__name__)

INACTIVE_PROJECT_STATUSES = ["archived", "deleted", "trash", "trashed", "completed", "done"]


def mode() -> str:
    m = (os.environ.get("PLAN_LIMITS_MODE") or "observe").strip().lower()
    return m if m in ("off", "observe", "enforce") else "observe"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def period(now: datetime | None = None) -> str:
    return (now or _now()).strftime("%Y-%m")


async def billing_account(user: dict) -> dict:
    """{'account_id', 'owner_user_id', 'org_id', 'member_ids'}."""
    uid = user["user_id"]
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "organization_id": 1, "org_role": 1}) or {}
    org_id = u.get("organization_id") or user.get("organization_id")
    if not org_id:
        return {"account_id": uid, "owner_user_id": uid, "org_id": None, "member_ids": [uid]}
    org = await db.organizations.find_one({"org_id": org_id}, {"_id": 0, "owner_user_id": 1}) or {}
    owner = org.get("owner_user_id") or uid
    members = [m["user_id"] async for m in db.users.find(
        {"organization_id": org_id, "active": {"$ne": False}, "company_active": {"$ne": False}},
        {"_id": 0, "user_id": 1})]
    if owner not in members:
        members.append(owner)
    return {"account_id": owner, "owner_user_id": owner, "org_id": org_id, "member_ids": members}


async def account_plan(account: dict) -> tuple[str | None, dict | None]:
    """(plan_id actif du propriétaire, limites commerciales ou None)."""
    from engines import monetization
    active = await monetization.user_active_plan(account["owner_user_id"])
    pid = ((active or {}).get("entitlement") or {}).get("plan_id")
    return pid, cp.limits_for_plan_id(pid)


async def _usage_doc(account_id: str, per: str) -> dict:
    return await db.usage_monthly.find_one({"_id": f"{account_id}:{per}"}) or {}


async def snapshot(user: dict) -> dict:
    """Consommation courante + limites (pour l'utilisateur et la page « Mon abonnement »)."""
    acc = await billing_account(user)
    pid, limits = await account_plan(acc)
    per = period()
    doc = await _usage_doc(acc["account_id"], per)
    members = acc["member_ids"]
    active_projects = await db.projects.count_documents(
        {"user_id": {"$in": members}, "status": {"$nin": INACTIVE_PROJECT_STATUSES}})
    storage = 0
    async for row in db.plans_takeoff.aggregate([
            {"$match": {"user_id": {"$in": members}}},
            {"$group": {"_id": None, "b": {"$sum": "$size_bytes"}}}]):
        storage = int(row.get("b") or 0)
    used = {"pages_monthly": int(doc.get("pages", 0)), "active_projects": active_projects,
            "seats": len(members), "storage_bytes": storage}
    eff_limits = dict(limits) if limits else None
    if eff_limits and doc.get("bonus_pages"):
        eff_limits["pages_monthly"] += int(doc["bonus_pages"])
    return {"mode": mode(), "period": per, "plan_id": pid,
            "commercial_plan": (cp.parse_plan_id(pid) or (None,))[0] if pid else None,
            "limits": eff_limits, "used": used,
            "ai_calls_month": int(doc.get("ai_calls", 0))}


def _exceeded(resource: str, used: int, limit: int, add: int) -> dict:
    return {"code": "plan_limit_reached", "resource": resource, "used": used,
            "limit": limit, "requested": add}


async def _log_event(account_id: str, kind: str, payload: dict) -> None:
    try:
        await db.usage_events.insert_one({"account_id": account_id, "kind": kind,
                                          "at": _now().isoformat(), **payload})
    except Exception as e:  # noqa: BLE001 — la mesure ne doit jamais casser un flux métier
        logger.warning(f"usage_events insert failed: {e}")


async def _gate(acc: dict, resource: str, used: int, limit: int | None, add: int) -> None:
    if limit is None or limit == cp.UNLIMITED or used + add <= limit:
        return
    detail = _exceeded(resource, used, limit, add)
    await _log_event(acc["account_id"], "limit_exceeded" if mode() == "enforce" else "limit_would_block",
                     detail)
    if mode() == "enforce":
        raise HTTPException(status_code=402, detail=detail)


async def check_new_project(user: dict) -> None:
    if mode() == "off":
        return
    acc = await billing_account(user)
    _, limits = await account_plan(acc)
    if not limits:
        return
    used = await db.projects.count_documents(
        {"user_id": {"$in": acc["member_ids"]}, "status": {"$nin": INACTIVE_PROJECT_STATUSES}})
    await _gate(acc, "active_projects", used, limits["active_projects"], 1)


async def check_new_seat(user: dict) -> None:
    if mode() == "off":
        return
    acc = await billing_account(user)
    _, limits = await account_plan(acc)
    if not limits:
        return
    await _gate(acc, "seats", len(acc["member_ids"]), limits["seats"], 1)


async def check_storage(user: dict, add_bytes: int) -> None:
    if mode() == "off":
        return
    snap = await snapshot(user)
    if not snap["limits"]:
        return
    acc = await billing_account(user)
    await _gate(acc, "storage_bytes", snap["used"]["storage_bytes"], snap["limits"]["storage_bytes"],
                int(add_bytes))


async def consume_pages(user: dict, n_pages: int, ref: str) -> dict:
    """Décompte ``n_pages`` pages techniques. Idempotent sur ``ref`` (ex. plan_id).

    En mode enforce, l'incrément est conditionnel (atomique) : deux imports concurrents ne
    peuvent pas dépasser la limite ensemble.
    """
    n = max(0, int(n_pages or 0))
    if mode() == "off" or n == 0:
        return {"counted": 0}
    acc = await billing_account(user)
    _, limits = await account_plan(acc)
    per = period()
    key = f"{acc['account_id']}:{per}"
    evt_id = f"pages:{acc['account_id']}:{ref}"
    if await db.usage_events.find_one({"_id": evt_id}):
        return {"counted": 0, "duplicate": True}
    await db.usage_monthly.update_one(
        {"_id": key}, {"$setOnInsert": {"account_id": acc["account_id"], "period": per,
                                        "pages": 0, "bonus_pages": 0}}, upsert=True)
    if limits and mode() == "enforce":
        doc = await _usage_doc(acc["account_id"], per)
        cap = limits["pages_monthly"] + int(doc.get("bonus_pages", 0))
        res = await db.usage_monthly.update_one(
            {"_id": key, "pages": {"$lte": cap - n}}, {"$inc": {"pages": n}})
        if res.modified_count == 0:
            await _gate(acc, "pages_monthly", int(doc.get("pages", 0)), cap, n)
    else:
        if limits:
            doc = await _usage_doc(acc["account_id"], per)
            await _gate(acc, "pages_monthly", int(doc.get("pages", 0)),
                        limits["pages_monthly"] + int(doc.get("bonus_pages", 0)), n)
        await db.usage_monthly.update_one({"_id": key}, {"$inc": {"pages": n}})
    try:
        await db.usage_events.insert_one({"_id": evt_id, "account_id": acc["account_id"], "kind": "pages",
                                          "n": n, "ref": ref, "period": per, "at": _now().isoformat()})
    except Exception:  # noqa: BLE001 — course : déjà compté par un appel concurrent
        await db.usage_monthly.update_one({"_id": key}, {"$inc": {"pages": -n}})
        return {"counted": 0, "duplicate": True}
    return {"counted": n}


async def note_ai_call(user_id: str | None) -> None:
    """Compteur d'appels IA par compte et par mois (télémétrie de coût, jamais bloquant)."""
    if not user_id or mode() == "off":
        return
    try:
        acc = await billing_account({"user_id": user_id})
        per = period()
        await db.usage_monthly.update_one(
            {"_id": f"{acc['account_id']}:{per}"},
            {"$inc": {"ai_calls": 1}, "$setOnInsert": {"account_id": acc["account_id"], "period": per,
                                                       "pages": 0, "bonus_pages": 0}},
            upsert=True)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"note_ai_call skipped: {e}")
