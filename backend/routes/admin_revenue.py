"""Revenue Dashboard Admin — KPIs financiers agrégés.

Calcule sur la base des collections `entitlements` (abos actifs), `plans` (prix mensuel/annuel),
`payment_transactions` (one-time + subscription), `users` (signups), `leads` (funnel).

Toutes les valeurs monétaires sont en EUR (cents pour l'API interne, conversion euros dans la réponse).
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from fastapi import APIRouter, Depends

from core.db import db
from core.security import admin_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-revenue"], prefix="/admin/revenue")


def _now():
    return datetime.now(timezone.utc)


def _iso(d):
    return d.isoformat()


async def _monthly_from_plan(plan: dict) -> float:
    """Renvoie le revenu mensuel normalisé (en €) pour un plan."""
    amt = (plan.get("amount_cents") or 0) / 100.0
    interval = plan.get("interval")
    if interval == "year":
        return amt / 12.0
    if interval == "month":
        return amt
    return 0.0


@router.get("/kpis")
async def revenue_kpis(admin=Depends(admin_user)):
    now = _now()
    plans = await db.plans.find({}, {"_id": 0}).to_list(200)
    plan_by_id = {p["plan_id"]: p for p in plans}

    # Actifs = paying subs (exclut free/trial)
    ents = await db.entitlements.find({}, {"_id": 0}).to_list(10000)
    paying = [e for e in ents if (e.get("status") in ("active",))
              and (plan_by_id.get(e.get("plan_id"), {}).get("amount_cents", 0) > 0)]
    trialing = [e for e in ents if e.get("status") == "trialing"]

    # MRR = Σ monthly-normalized revenue
    mrr = 0.0
    per_plan = defaultdict(lambda: {"count": 0, "mrr": 0.0})
    for e in paying:
        pl = plan_by_id.get(e.get("plan_id"))
        if not pl:
            continue
        m = await _monthly_from_plan(pl)
        mrr += m
        per_plan[pl["plan_id"]]["count"] += 1
        per_plan[pl["plan_id"]]["mrr"] += m
        per_plan[pl["plan_id"]]["name"] = pl.get("name")

    arr = mrr * 12
    paying_count = len(paying)
    arpu = (mrr / paying_count) if paying_count else 0.0

    # LTV avec churn estimé — sans historique churn suffisant on prend 5% mensuel
    churn = 0.05
    ltv = (arpu / churn) if arpu else 0.0

    # CAC réel non tracké — laissé à 0 sauf override manuel via ENV
    cac = 0.0

    # New subs this month + one-time
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ms_iso = _iso(month_start)
    new_subs_month = sum(1 for e in paying if (e.get("started_at") or "") >= ms_iso)

    # Payments this month total (subs + Project Pass)
    payments = await db.payment_transactions.find(
        {"status": "paid", "paid_at": {"$gte": ms_iso}},
        {"_id": 0, "amount_cents": 1, "plan_id": 1}
    ).to_list(10000)
    revenue_this_month_eur = sum((p.get("amount_cents") or 0) for p in payments) / 100.0

    # Funnel (30 derniers jours)
    d30 = now - timedelta(days=30)
    d30_iso = _iso(d30)
    signups_30 = await db.users.count_documents({"created_at": {"$gte": d30_iso}})
    trials_30 = await db.entitlements.count_documents(
        {"status": "trialing", "started_at": {"$gte": d30_iso}})
    paid_30 = await db.payment_transactions.count_documents(
        {"status": "paid", "paid_at": {"$gte": d30_iso}})
    leads_30 = await db.leads.count_documents({"created_at": {"$gte": d30_iso}})

    return {
        "generated_at": _iso(now),
        "currency": "EUR",
        "mrr_eur": round(mrr, 2),
        "arr_eur": round(arr, 2),
        "arpu_eur": round(arpu, 2),
        "ltv_eur": round(ltv, 2),
        "cac_eur": round(cac, 2),
        "assumed_monthly_churn": churn,
        "paying_subs": paying_count,
        "trialing_subs": len(trialing),
        "new_paying_this_month": new_subs_month,
        "revenue_this_month_eur": round(revenue_this_month_eur, 2),
        "per_plan": sorted(
            [{"plan_id": k, **v, "mrr": round(v["mrr"], 2)} for k, v in per_plan.items()],
            key=lambda x: -x["mrr"],
        ),
        "funnel_30d": {
            "signups": signups_30,
            "trials_started": trials_30,
            "paid_transactions": paid_30,
            "leads": leads_30,
            "signup_to_trial_pct": round((trials_30 / signups_30 * 100) if signups_30 else 0.0, 1),
            "trial_to_paid_pct": round((paid_30 / trials_30 * 100) if trials_30 else 0.0, 1),
        },
    }


@router.get("/timeseries")
async def revenue_timeseries(days: int = 90, admin=Depends(admin_user)):
    """Renvoie les revenus quotidiens (paiements confirmés) sur les N derniers jours."""
    days = min(max(days, 7), 365)
    now = _now()
    start = now - timedelta(days=days)
    start_iso = _iso(start)

    payments = await db.payment_transactions.find(
        {"status": "paid", "paid_at": {"$gte": start_iso}},
        {"_id": 0, "amount_cents": 1, "paid_at": 1, "plan_id": 1}
    ).to_list(20000)

    by_day = defaultdict(lambda: {"revenue_eur": 0.0, "count": 0})
    for p in payments:
        day = (p.get("paid_at") or "")[:10]
        if not day:
            continue
        by_day[day]["revenue_eur"] += (p.get("amount_cents") or 0) / 100.0
        by_day[day]["count"] += 1

    # Fill missing days for a smooth chart
    series = []
    for i in range(days + 1):
        d = (start + timedelta(days=i)).date().isoformat()
        bucket = by_day.get(d, {"revenue_eur": 0.0, "count": 0})
        series.append({"day": d, "revenue_eur": round(bucket["revenue_eur"], 2),
                       "count": bucket["count"]})
    return {"days": days, "series": series}
