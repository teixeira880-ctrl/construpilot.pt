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
                    referrals as referrals_routes,
                    errors as errors_routes,
                    emails as emails_routes,
                    plans as plans_routes,
                    tool_presets as tool_presets_routes)  # noqa: E402

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
api_router.include_router(plans_routes.quote_router)
api_router.include_router(plans_routes.pc_router)
api_router.include_router(tool_presets_routes.router)
api_router.include_router(referrals_routes.router)
api_router.include_router(errors_routes.router)
api_router.include_router(emails_routes.router)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    # SEC-002 : allowlist explicite — jamais '*' avec credentials
    allow_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",")
                   if o.strip() and o.strip() != "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

ADMIN_EMAIL = "admin@construpilot.fr"
DEMO_EMAIL = "demo@construpilot.fr"
CLIENT_EMAIL = "client@construpilot.fr"
PRO_EMAIL = "pro@construpilot.fr"
COLLEGUE_EMAIL = "collegue@construpilot.fr"

async def _seed_demo_org():
    """Crée idempotemment l'org 'BTP Demo SAS' avec pro@ owner + collegue@ member."""
    import secrets
    pro = await db.users.find_one({"email": PRO_EMAIL}, {"_id": 0, "user_id": 1})
    col = await db.users.find_one({"email": COLLEGUE_EMAIL}, {"_id": 0, "user_id": 1})
    if not pro or not col:
        return
    org = await db.organizations.find_one({"name": "BTP Demo SAS"})
    if not org:
        org_id = "org_" + secrets.token_hex(6)
        code = "DEMO-2026"
        doc = {
            "org_id": org_id, "org_code": code, "name": "BTP Demo SAS",
            "owner_user_id": pro["user_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "brand_company_name": "BTP Demo SAS",
            "brand_contact_line": "12 rue des Compagnons · 75011 Paris · 01 45 67 89 00 · contact@btp-demo.fr",
            "brand_logo_b64": None,
        }
        await db.organizations.insert_one(doc)
        org = doc
    # Force les membres à être dans l'org (idempotent)
    await db.users.update_one({"email": PRO_EMAIL},
                              {"$set": {"organization_id": org["org_id"], "org_role": "owner",
                                        "joined_org_at": datetime.now(timezone.utc).isoformat()}})
    await db.users.update_one({"email": COLLEGUE_EMAIL},
                              {"$set": {"organization_id": org["org_id"], "org_role": "member",
                                        "joined_org_at": datetime.now(timezone.utc).isoformat()}})




@app.on_event("startup")
async def seed():
    # SEC-001 : comptes de démonstration créés UNIQUEMENT si SEED_DEMO_DATA=true,
    # et le mot de passe d'un compte existant n'est JAMAIS réécrit.
    if os.environ.get("SEED_DEMO_DATA") == "true":
        await db.users.delete_many({"email": {"$in": ["admin@cmrenov.fr", "demo@cmrenov.fr"]}})

        accounts = (
            (ADMIN_EMAIL,     "Admin ConstruPilot", "admin", "premium", "Construpilot2026!"),
            (DEMO_EMAIL,      "Client Démo",        "user",  "premium", "Demo2026!"),
            (CLIENT_EMAIL,    "Alice Particulier",  "user",  "free",    "Client2026!"),
            (PRO_EMAIL,       "Marc BTP (Pro)",     "user",  "premium", "Pro2026!"),
            (COLLEGUE_EMAIL,  "Julie Collègue",     "user",  "free",    "Collegue2026!"),
        )
        for email, name, role, plan, pw in accounts:
            existing = await db.users.find_one({"email": email})
            if existing:
                await db.users.update_one(
                    {"email": email},
                    {"$set": {"name": name, "role": role, "plan": plan}})
            else:
                await db.users.insert_one({
                    "email": email, "name": name, "role": role, "plan": plan,
                    "password_hash": hash_password(pw), "auth_provider": "password",
                    "picture": None, "user_id": new_user_id(),
                    "created_at": datetime.now(timezone.utc).isoformat()})

        # Seed "BTP Demo SAS" — org démo pour montrer le partage de branding
        await _seed_demo_org()

        # Entitlement Pro Business permanent pour les comptes de test (idempotent).
        # Sans lui, les routes /takeoffs renvoient 402 et la suite pytest échoue après un fork.
        for email in (DEMO_EMAIL, PRO_EMAIL):
            u = await db.users.find_one({"email": email}, {"user_id": 1})
            if u and not await db.entitlements.find_one(
                    {"user_id": u["user_id"], "plan_id": "pro_business_monthly", "status": "active"}):
                await db.entitlements.insert_one({
                    "user_id": u["user_id"], "plan_id": "pro_business_monthly",
                    "plan_code": "PRO_BUSINESS_MONTHLY", "kind": "subscription",
                    "audience": "pro", "status": "active",
                    "granted_at": datetime.now(timezone.utc).isoformat(),
                    "source": "seed_demo"})
    else:
        logger.info("SEED_DEMO_DATA désactivé — aucun compte de démonstration créé")
    await db.projects.create_index("project_id")
    await db.projects.create_index("user_id")
    await db.price_history.create_index("query")
    await db.entitlements.create_index("user_id")
    await db.entitlements.create_index("stripe_subscription_id")
    await db.payment_transactions.create_index("session_id", unique=True)
    await db.login_attempts.create_index("identifier")
    try:
        await db.login_attempts.create_index("updated_at", expireAfterSeconds=3600)
    except Exception as e:
        logger.warning(f"login_attempts TTL index skipped: {e}")
    await db.plans.create_index("plan_id", unique=True)
    # Organizations (team branding)
    await db.organizations.create_index("org_id", unique=True)
    await db.organizations.create_index("org_code", unique=True)
    await db.users.create_index("organization_id")
    await db.org_invites.create_index("invite_id", unique=True)
    await db.org_invites.create_index("email")
    # TTL 30 jours sur les erreurs client remontées par l'ErrorBoundary
    try:
        await db.client_errors.create_index("created_at",
                                              expireAfterSeconds=60 * 60 * 24 * 30)
    except Exception as e:
        logger.warning(f"client_errors TTL index skipped: {e}")
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
    # Rappel Auto Devis (toutes les 6 h) : envoie un rappel aux clients qui ont ouvert
    # mais pas signé leur devis depuis > 5 j.
    scheduler.add_job(plans_routes._run_reminders,
                      "interval", hours=6, id="quote_reminders",
                      max_instances=1, coalesce=True)
    # Relance auto Étude PC (toutes les 6 h) : relance les études envoyées mais
    # jamais ouvertes après N jours (réglable par utilisateur, défaut 3 j).
    scheduler.add_job(plans_routes._run_pc_reminders,
                      "interval", hours=6, id="pc_study_reminders",
                      max_instances=1, coalesce=True)
    # Rapport hebdo Études PC — chaque lundi 07:00 UTC (~08-09 h Paris)
    scheduler.add_job(plans_routes._run_pc_weekly_reports,
                      CronTrigger(day_of_week="mon", hour=7, minute=0),
                      id="pc_weekly_report", max_instances=1, coalesce=True)
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
