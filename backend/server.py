import os
import logging
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from core.db import db, client  # noqa: E402
from core.security import hash_password, new_user_id  # noqa: E402
from engines import storage, alerting  # noqa: E402
from routes import (auth as auth_routes, estimation_routes, tools, prices, projects,
                    ai_routes, leads, admin, photos, billing, revenue,
                    phase4, phase5, phase6, phase7, share, admin_revenue,
                    plans as plans_routes)  # noqa: E402

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

app = FastAPI(title="ConstruPilot API")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"app": "ConstruPilot", "tagline": "Estimez, Comparez, Construisez.",
            "status": "ok"}


api_router.include_router(auth_routes.router)
api_router.include_router(estimation_routes.router)
api_router.include_router(tools.router)
api_router.include_router(prices.router)
api_router.include_router(projects.router)
api_router.include_router(ai_routes.router)
api_router.include_router(leads.router)
api_router.include_router(admin.router)
api_router.include_router(photos.router)
api_router.include_router(billing.router)
api_router.include_router(revenue.router)
api_router.include_router(phase4.router)
api_router.include_router(phase5.router)
api_router.include_router(phase6.router)
api_router.include_router(phase7.router)
api_router.include_router(share.router)
api_router.include_router(admin_revenue.router)
api_router.include_router(plans_routes.router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ADMIN_EMAIL = "admin@construpilot.fr"
DEMO_EMAIL = "demo@construpilot.fr"


@app.on_event("startup")
async def seed():
    # Nettoyage des anciens comptes (renommage marque)
    await db.users.delete_many({"email": {"$in": ["admin@cmrenov.fr", "demo@cmrenov.fr"]}})

    for email, name, role, pw in ((ADMIN_EMAIL, "Admin ConstruPilot", "admin", "Construpilot2026!"),
                                  (DEMO_EMAIL, "Client Démo", "user", "Demo2026!")):
        existing = await db.users.find_one({"email": email})
        doc = {"email": email, "name": name, "role": role, "plan": "pro" if role == "admin" else "premium",
               "password_hash": hash_password(pw), "auth_provider": "password", "picture": None}
        if existing:
            await db.users.update_one({"email": email}, {"$set": doc})
        else:
            await db.users.insert_one({**doc, "user_id": new_user_id(),
                                       "created_at": datetime.now(timezone.utc).isoformat()})
    await db.projects.create_index("project_id")
    await db.projects.create_index("user_id")
    await db.price_history.create_index("query")
    await db.entitlements.create_index("user_id")
    await db.entitlements.create_index("stripe_subscription_id")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.plans.create_index("plan_id", unique=True)
    try:
        storage.init_storage()
    except Exception as e:
        logger.warning(f"Storage init skipped: {e}")

    # Seed plans + feature flags (idempotent)
    from engines.monetization_catalog import DEFAULT_PLANS, DEFAULT_FEATURE_FLAGS
    from engines import monetization
    for plan in DEFAULT_PLANS:
        exists = await db.plans.find_one({"plan_id": plan["plan_id"]})
        if not exists:
            await db.plans.insert_one(plan)
    # Migration prix pro (12/02/2026) : Pro 49→99€ · Pro Business 99→199€
    PRICE_MIGRATION = {
        "pro_monthly": 9900, "pro_yearly": 99000,
        "pro_business_monthly": 19900, "pro_business_yearly": 199000,
    }
    for plan_id, cents in PRICE_MIGRATION.items():
        await db.plans.update_one({"plan_id": plan_id}, {"$set": {"amount_cents": cents}})
    if not await db.feature_flags.find_one({"_id": "global"}):
        await db.feature_flags.insert_one({"_id": "global", **DEFAULT_FEATURE_FLAGS})

    # Affiliate configs seed (idempotent)
    try:
        from engines import affiliate
        await affiliate.seed_affiliate_configs()
    except Exception as e:
        logger.warning(f"Affiliate seed skipped: {e}")

    # Sync catalogue Stripe (best effort — n'échoue pas si Stripe indispo)
    try:
        await monetization.ensure_stripe_catalog()
    except Exception as e:
        logger.warning(f"Stripe catalog sync skipped: {e}")

    # Vérification quotidienne des alertes prix (tous les jours à 08:00 UTC)
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(alerting.check_all_alerts,
                      CronTrigger(hour=8, minute=0),
                      id="daily_price_alerts", max_instances=1, coalesce=True)
    # Snapshot quotidien des prix des queries surveillées (à 03:00 UTC)
    async def snapshot_watched():
        from engines import price_search
        queries = await db.price_alerts.distinct("query", {"active": True})
        for q in queries[:50]:
            try:
                res = await price_search.search(q, 20)
                day = datetime.now(timezone.utc).date().isoformat()
                for r in res.get("results", []):
                    if not r.get("price"):
                        continue
                    exists = await db.price_history_daily.find_one(
                        {"query": q.lower(), "supplier_key": r.get("supplier_key"), "day": day})
                    if exists:
                        continue
                    await db.price_history_daily.insert_one({
                        "query": q.lower(), "supplier_key": r.get("supplier_key"),
                        "supplier": r.get("supplier"), "price": r.get("price"),
                        "product": r.get("product"), "day": day,
                        "at": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                logger.warning(f"Snapshot failed for '{q}': {e}")
    scheduler.add_job(snapshot_watched, CronTrigger(hour=3, minute=0),
                      id="daily_price_snapshot", max_instances=1, coalesce=True)
    # Digest hebdomadaire lundi 09:00 UTC
    from engines import retention
    scheduler.add_job(retention.send_weekly_digests,
                      CronTrigger(day_of_week="mon", hour=9, minute=0),
                      id="weekly_digest", max_instances=1, coalesce=True)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started (daily price alerts @ 08:00 UTC)")

    logger.info("ConstruPilot backend prêt")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
