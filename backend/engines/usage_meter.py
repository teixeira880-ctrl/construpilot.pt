"""Mesure de consommation et application des limites des offres commerciales (2026-11).

Compte de facturation = propriétaire de l'organisation (les membres consomment sur le
compte de leur entreprise), sinon l'utilisateur lui-même.

Mode (variable ``PLAN_LIMITS_MODE``) :
  * ``off``      — rien n'est mesuré ni bloqué ;
  * ``observe``  — on mesure, on journalise les dépassements, on ne bloque JAMAIS ;
  * ``enforce``  — (défaut, décision 2026-11-09 « ne jamais perdre d'argent ») on mesure et on
    bloque (HTTP 402) au-delà de la limite.

Garde-fou de coût IA (toutes offres, y compris historiques et gratuites) : le coût IA estimé
d'un compte sur le mois ne peut jamais dépasser un budget dérivé de ce qu'il paie
(voir ``ai_budget_micros``). Au-delà, les nouveaux appels IA sont refusés (402
``ai_budget_reached``) ; les données et les fonctions sans IA restent accessibles.

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
    m = (os.environ.get("PLAN_LIMITS_MODE") or "enforce").strip().lower()
    return m if m in ("off", "observe", "enforce") else "enforce"


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
    """(plan_id actif du propriétaire, limites commerciales ou None). Inclut les utilisateurs
    supplémentaires achetés (organizations.extra_seats)."""
    from engines import monetization
    active = await monetization.user_active_plan(account["owner_user_id"])
    pid = ((active or {}).get("entitlement") or {}).get("plan_id")
    limits = cp.limits_for_plan_id(pid)
    if limits and account.get("org_id"):
        org = await db.organizations.find_one({"org_id": account["org_id"]}, {"_id": 0, "extra_seats": 1}) or {}
        limits["seats"] += int(org.get("extra_seats") or 0)
    return pid, limits


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


# ====================================================================== garde-fou de coût IA
# Prix publics de référence, USD par million de tokens (entrée, sortie). Surchargeables via
# AI_PRICE_TABLE='{"sonnet":[3,15],...}'. Clé = sous-chaîne du nom de modèle (première trouvée).
# USD comptés 1:1 en EUR (sur-estimation volontaire tant que 1 € > 1 $).
DEFAULT_PRICES = [
    ("haiku", (1.0, 5.0)), ("sonnet", (3.0, 15.0)), ("opus", (5.0, 25.0)), ("fable", (15.0, 75.0)),
    ("mythos", (15.0, 75.0)), ("gpt-4o-mini", (0.15, 0.6)), ("mini", (0.4, 1.6)), ("gpt", (2.5, 10.0)),
    ("o3", (2.0, 8.0)), ("flash", (0.3, 2.5)), ("gemini", (1.25, 10.0)), ("image", (0.0, 40.0)),
]
FALLBACK_PRICE = (15.0, 75.0)       # modèle inconnu : on compte au plus cher
PER_CALL_FLOOR_MICROS = 20_000       # appel sans compteur de tokens : 0,02 € minimum
PER_IMAGE_MICROS = 80_000            # image générée : 0,08 €
# Part du revenu mensuel HT qu'un compte peut consommer en IA (le reste couvre Stripe,
# stockage, infrastructure et marge). Plans commerciaux : 70 %. Plans historiques : 100 %
# (équilibre, jamais de perte). Sans abonnement (gratuit / promo / bêta) : budget fixe.
COMMERCIAL_BUDGET_RATIO = float(os.environ.get("AI_BUDGET_RATIO_COMMERCIAL", "0.70"))
LEGACY_BUDGET_RATIO = float(os.environ.get("AI_BUDGET_RATIO_LEGACY", "1.0"))
FREE_BUDGET_EUR = float(os.environ.get("FREE_AI_BUDGET_EUR", "3"))
STRIPE_FEE_RATIO = 0.03              # commission de paiement estimée, déduite du revenu


def _price_table() -> list:
    raw = os.environ.get("AI_PRICE_TABLE")
    if raw:
        try:
            import json
            return [(k, tuple(v)) for k, v in json.loads(raw).items()] + DEFAULT_PRICES
        except Exception:  # noqa: BLE001
            logger.warning("AI_PRICE_TABLE invalide, prix par défaut utilisés")
    return DEFAULT_PRICES


def estimate_cost_micros(model: str | None, units: dict | None) -> int:
    """Coût estimé d'un appel en micro-euros (1 € = 1 000 000)."""
    units = units or {}
    name = (model or "").lower()
    price_in, price_out = next((p for k, p in _price_table() if k in name), FALLBACK_PRICE)
    tin, tout = units.get("input_tokens"), units.get("output_tokens")
    cost = 0
    if isinstance(tin, (int, float)) or isinstance(tout, (int, float)):
        cost = int((tin or 0) * price_in + (tout or 0) * price_out)  # $/M tokens × tokens = micro-$
    cost = max(cost, PER_CALL_FLOOR_MICROS if units.get("calls") else 0)
    cost += int(units.get("images") or 0) * PER_IMAGE_MICROS
    return cost


async def note_ai_cost(user_id: str | None, model: str | None, units: dict | None) -> None:
    """Ajoute le coût estimé d'un appel IA au compte (jamais bloquant)."""
    if not user_id or mode() == "off":
        return
    try:
        acc = await billing_account({"user_id": user_id})
        per = period()
        await db.usage_monthly.update_one(
            {"_id": f"{acc['account_id']}:{per}"},
            {"$inc": {"ai_cost_micros": estimate_cost_micros(model, units)},
             "$setOnInsert": {"account_id": acc["account_id"], "period": per, "pages": 0, "bonus_pages": 0}},
            upsert=True)
        _budget_cache.pop(acc["account_id"], None)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"note_ai_cost skipped: {e}")


async def monthly_revenue_cents(account: dict) -> tuple[int, float]:
    """(revenu mensuel HT en centimes, ratio de budget) pour le propriétaire du compte."""
    from engines import monetization
    active = await monetization.user_active_plan(account["owner_user_id"])
    ent = (active or {}).get("entitlement") or {}
    pid = ent.get("plan_id")
    parsed = cp.parse_plan_id(pid)
    if parsed:
        key, interval = parsed
        cents = cp.price_cents(key, interval)
        return (cents // 12 if interval == "year" else cents), COMMERCIAL_BUDGET_RATIO
    if pid and not ent.get("free_promo"):
        plan = (active or {}).get("plan") or await db.plans.find_one({"plan_id": pid}, {"_id": 0}) or {}
        cents = int(plan.get("amount_cents") or 0)
        if plan.get("interval") == "year":
            cents //= 12
        elif plan.get("kind") == "one_time":
            cents //= 3  # pass ponctuel : étalé sur sa durée d'usage typique (3 mois)
        return cents, LEGACY_BUDGET_RATIO
    return 0, 0.0


_budget_cache: dict[str, tuple[float, int, int]] = {}


async def ai_budget(account: dict) -> dict:
    """{'budget_micros', 'spent_micros'} du mois (cache 60 s)."""
    import time
    hit = _budget_cache.get(account["account_id"])
    if hit and time.monotonic() - hit[0] < 60:
        return {"budget_micros": hit[1], "spent_micros": hit[2]}
    cents, ratio = await monthly_revenue_cents(account)
    doc = await _usage_doc(account["account_id"], period())
    if cents > 0:
        budget = int(cents * (1 - STRIPE_FEE_RATIO) * ratio * 10_000)  # centimes → micro-euros
    else:
        budget = int(FREE_BUDGET_EUR * 1_000_000)
    budget += int(doc.get("bonus_ai_budget_micros", 0))  # packs achetés
    spent = int(doc.get("ai_cost_micros", 0))
    _budget_cache[account["account_id"]] = (time.monotonic(), budget, spent)
    return {"budget_micros": budget, "spent_micros": spent}


async def check_ai_budget(user_id: str | None) -> None:
    """Refuse un nouvel appel IA quand le budget du mois est consommé (mode enforce).

    Exemptés : appels sans utilisateur (tâches système) et administrateurs ConstruPilot.
    """
    if not user_id or mode() != "enforce":
        return
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "role": 1}) or {}
    if u.get("role") == "admin":
        return
    acc = await billing_account({"user_id": user_id})
    b = await ai_budget(acc)
    if b["spent_micros"] < b["budget_micros"]:
        return
    per = period()
    first = await db.usage_monthly.update_one(
        {"_id": f"{acc['account_id']}:{per}", "ai_budget_alerted": {"$ne": True}},
        {"$set": {"ai_budget_alerted": True}})
    if first.modified_count:
        await _log_event(acc["account_id"], "ai_budget_reached", {
            "spent_micros": b["spent_micros"], "budget_micros": b["budget_micros"], "period": per})
        try:
            from engines import emailer
            to = os.environ.get("COMMERCIAL_SALES_EMAIL") or (
                "info@construpilot.pt" if cp.market() == "pt" else "info@construpilot.fr")
            await emailer.send_email(
                to, f"[Coûts IA] Budget atteint — compte {acc['account_id']}",
                f"<p>Compte <b>{acc['account_id']}</b> : coût IA estimé {b['spent_micros'] / 1e6:.2f} € "
                f"pour un budget de {b['budget_micros'] / 1e6:.2f} € ({per}). Nouveaux appels IA suspendus "
                f"jusqu'au mois prochain ou à une montée d'offre.</p>")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ai budget alert email failed: {e}")
    raise HTTPException(status_code=402, detail={
        "code": "plan_limit_reached", "resource": "ai_budget",
        "used": b["spent_micros"], "limit": b["budget_micros"], "requested": 0})


async def credit_pages_pack(account_id: str, packs: int = 1, admin_id: str | None = None) -> dict:
    """Crédite N packs de 500 pages sur le mois en cours (après paiement accepté par le client)."""
    addon = cp.ADDONS["pages_500"]
    per = period()
    net = addon["unit_cents"] * (1 - STRIPE_FEE_RATIO)
    budget = int(net * addon["ai_budget_ratio"] * 10_000) * packs
    await db.usage_monthly.update_one(
        {"_id": f"{account_id}:{per}"},
        {"$inc": {"bonus_pages": addon["pages"] * packs, "bonus_ai_budget_micros": budget},
         "$setOnInsert": {"account_id": account_id, "period": per, "pages": 0}}, upsert=True)
    _budget_cache.pop(account_id, None)
    await _log_event(account_id, "addon_pages_credited", {"packs": packs, "by": admin_id, "period": per})
    return {"bonus_pages": addon["pages"] * packs, "bonus_ai_budget_micros": budget}
