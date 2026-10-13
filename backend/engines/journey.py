"""Instrumentation du parcours client : événements réels + comptes réels dédupliqués.

Principe : aucune valeur inventée. Toute métrique non mesurable renvoie `None`
(le front affiche « non mesurable »), jamais 0.
"""
from datetime import datetime, timezone, timedelta

from core.db import db

# Événements du parcours réellement instrumentés côté serveur.
EVENTS = ("signup_completed", "first_value_estimation", "login", "quote_created",
          "subscription_paid", "signup_started")

_SOURCE_KEYS = ("utm_source", "utm_medium", "utm_campaign", "ref", "qr",
                "landing_path", "referrer")


def _clean_source(src: dict | None) -> dict:
    src = src or {}
    return {k: str(src.get(k) or "")[:200] for k in _SOURCE_KEYS if src.get(k)}


def channel_of(source: dict) -> str:
    """Canal déduit de la provenance. « inconnu » est une valeur légitime, pas un défaut caché."""
    if source.get("qr"):
        return "prospectus_qr"
    if source.get("ref"):
        return "parrainage"
    s = (source.get("utm_source") or "").lower()
    m = (source.get("utm_medium") or "").lower()
    if s or m:
        if m in ("cpc", "ppc", "paid", "ads"):
            return f"publicite:{s or 'inconnu'}"
        return f"{m or 'campagne'}:{s or 'inconnu'}"
    ref = (source.get("referrer") or "").lower()
    if "google." in ref or "bing." in ref or "duckduckgo" in ref:
        return "recherche_organique"
    if ref:
        return "site_referent"
    return "inconnu"


async def record_event(event: str, *, user_id: str | None = None,
                       anon_id: str | None = None, source: dict | None = None,
                       props: dict | None = None, once_per_user: bool = False) -> bool:
    """Enregistre un événement. `once_per_user` garantit l'unicité (ex. première valeur)."""
    if event not in EVENTS:
        return False
    if once_per_user and user_id:
        if await db.journey_events.find_one({"event": event, "user_id": user_id}, {"_id": 1}):
            return False
    src = _clean_source(source)
    await db.journey_events.insert_one({
        "event": event,
        "user_id": user_id,
        "anon_id": (anon_id or "")[:64] or None,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "source": src,
        "channel": channel_of(src),
        "props": {k: str(v)[:200] for k, v in (props or {}).items()},
    })
    return True


async def ensure_indexes() -> None:
    await db.journey_events.create_index([("event", 1), ("user_id", 1)])
    await db.journey_events.create_index("occurred_at")


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


async def journey_metrics(days: int = 30) -> dict:
    """Comptes réels + activation + provenance. `None` = non mesurable avec les données actuelles."""
    since = _iso(days)
    instrumented_since = await db.journey_events.find_one({}, {"_id": 0, "occurred_at": 1},
                                                          sort=[("occurred_at", 1)])

    # --- Comptes (source : collection users, hors comptes de test/admin) ---
    test_filter = {"email": {"$not": {"$regex": r"(example\.com|construpilot-qa\.fr|@test\.|\+test|delivered@resend\.dev)"}}}
    existing = await db.users.count_documents(test_filter)
    all_users = await db.users.count_documents({})
    deleted = await db.deleted_accounts.count_documents({})
    admins = await db.users.count_documents({"role": "admin"})
    pros = await db.users.count_documents({**test_filter, "account_type": {"$ne": "particulier"}})
    particuliers = await db.users.count_documents({**test_filter, "account_type": "particulier"})

    # Entreprises distinctes : SIRET renseigné (source déclarative) + organisations
    sirets = await db.users.distinct("siret", {"siret": {"$nin": [None, ""]}})
    orgs = await db.organizations.count_documents({}) if "organizations" in await db.list_collection_names() else None

    # --- Actifs : sessions réelles (user_sessions, created_at en datetime BSON).
    # On ne retient que les comptes qui existent encore et ne sont pas des comptes de test :
    # `user_sessions` contient aussi des sessions orphelines (comptes supprimés) et de tests.
    since_dt = datetime.now(timezone.utc) - timedelta(days=days)
    valid_ids = set(await db.users.distinct("user_id", test_filter))
    session_ids = set(await db.user_sessions.distinct("user_id", {"created_at": {"$gte": since_dt}}))
    ever_session_ids = set(await db.user_sessions.distinct("user_id"))
    total_sessions = await db.user_sessions.count_documents({})
    dated_sessions = await db.user_sessions.count_documents({"created_at": {"$exists": True}})
    active = len(session_ids & valid_ids) if dated_sessions else None
    ever_ids = ever_session_ids & valid_ids
    orphan_sessions = len(ever_session_ids - valid_ids)

    # --- Payants : entitlements actifs (hors phase promo gratuite) ---
    now = datetime.now(timezone.utc).isoformat()
    paying = await db.entitlements.count_documents(
        {"status": "active", "$or": [{"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}]})

    # --- Parcours instrumenté ---
    async def _count(event: str, window: bool = True) -> int:
        q = {"event": event}
        if window:
            q["occurred_at"] = {"$gte": since}
        return await db.journey_events.count_documents(q)

    signups = await _count("signup_completed")
    first_value = await _count("first_value_estimation")
    activation_rate = round(first_value / signups * 100, 1) if signups else None

    # --- Provenance des inscriptions instrumentées ---
    by_channel = await db.journey_events.aggregate([
        {"$match": {"event": "signup_completed", "occurred_at": {"$gte": since}}},
        {"$group": {"_id": "$channel", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]).to_list(30)

    # Comptes créés avant l'instrumentation : provenance non résolue, affichée telle quelle
    total_signups_ever = await db.journey_events.count_documents({"event": "signup_completed"})

    return {
        "generated_at": now,
        "window_days": days,
        "instrumentation_started_at": (instrumented_since or {}).get("occurred_at"),
        "accounts": {
            "existing_excluding_tests": existing,
            "all_rows_in_db": all_users,
            "test_or_internal": all_users - existing,
            "admins": admins,
            "pros": pros,
            "particuliers": particuliers,
            "deleted_since_tracking": deleted,
            "companies_with_siret": len(sirets),
            "organizations": orgs,
        },
        "activity": {
            "active_users_window": active,
            "ever_connected": len(ever_ids),
            "sessions_total": total_sessions,
            "sessions_without_date": total_sessions - dated_sessions,
            "session_holders_not_countable": orphan_sessions,
            "active_definition": f"au moins une session ouverte sur {days} jours (collection user_sessions)",
            "paying_customers": paying,
            "paying_note": "entitlements actifs ; la phase de lancement gratuite (FREE_PROMO_MODE) n'en crée aucun",
        },
        "journey": {
            "signups_window": signups,
            "signups_tracked_total": total_signups_ever,
            "first_value_window": first_value,
            "first_value_definition": "première estimation calculée avec succès (POST /estimation/compute ou /analyse)",
            "activation_rate_pct": activation_rate,
            "accounts_before_instrumentation": max(existing - total_signups_ever, 0),
        },
        "acquisition": [{"channel": r["_id"], "signups": r["n"]} for r in by_channel],
    }
