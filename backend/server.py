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
from core.cors_origin import CanonicalOriginMiddleware
from engines.expenses.context import ExpenseContextMiddleware
from routes import admin_expenses
from routes import admin_apify
from routes import admin_learning
from routes import bridge as bridge_routes
from routes import media as media_routes
from routes import presentation
from routes import brochures
from core.security import hash_password, new_user_id  # noqa: E402
from engines import storage, alerting  # noqa: E402
from routes import (auth as auth_routes, estimation_routes, tools, prices, projects,
                    ai_routes, leads, admin, photos, billing, revenue,
                    phase4, phase5, phase6, phase7, share, admin_revenue,
                    referrals as referrals_routes,
                    errors as errors_routes,
                    emails as emails_routes,
                    plans as plans_routes,
                    clients as clients_routes,
                    library as library_routes,
                    documents as documents_routes,
                    reviews as reviews_routes,
                    shared_library as shared_library_routes,
                    param_library as param_library_routes,
                    autoseo as autoseo_routes,
                    ceo as ceo_routes,
                    calc_auditor as calc_auditor_routes,
                    roi as roi_routes,
                    babylovegrowth as blg_routes,
                    newsletter as newsletter_routes,
                    dpgf as dpgf_routes,
                    company_library as company_library_routes,
                    suppliers as suppliers_routes,
                    steel as steel_routes,
                    waterproofing as waterproofing_routes,
                    roofing as roofing_routes,
                    vrd as vrd_routes,
                    appro as appro_routes,
                    help as help_routes,
                    evolution as evolution_routes,
                    einvoicing as einvoicing_routes,
                    resend_webhook as resend_webhook_routes,
                    branding_public as branding_public_routes,
                    notifications as notifications_routes,
                    runway_render as runway_render_routes,
                    tool_presets as tool_presets_routes)  # noqa: E402

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402
from apscheduler.triggers.cron import CronTrigger  # noqa: E402

# Sprint 0 sécurité : rate limiting global (voir core/rate_limit.py).
from core.rate_limit import limiter, rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402
from slowapi.middleware import SlowAPIMiddleware  # noqa: E402

app = FastAPI(title="ConstruPilot API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
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
from routes import trash as trash_routes  # noqa: E402
api_router.include_router(trash_routes.router)
from growth.routes import router as growth_router  # noqa: E402
api_router.include_router(growth_router)
from btp_ai.routes import router as btp_ai_router  # noqa: E402
api_router.include_router(btp_ai_router)
from perplexity_plus.routes import router as pplx_plus_router  # noqa: E402
api_router.include_router(pplx_plus_router)
from btp_solver.routes import router as btp_solver_router  # noqa: E402
api_router.include_router(btp_solver_router)
from plans_pro.routes import router as plans_pro_router  # noqa: E402
api_router.include_router(plans_pro_router)
api_router.include_router(ai_routes.router)
api_router.include_router(leads.router)
api_router.include_router(admin.router)
api_router.include_router(ceo_routes.router)
api_router.include_router(calc_auditor_routes.router)
api_router.include_router(roi_routes.router)
api_router.include_router(photos.router)
from routes import doc_photos as doc_photos_routes  # noqa: E402
api_router.include_router(doc_photos_routes.router)
from routes import quote_templates as quote_templates_routes  # noqa: E402
api_router.include_router(quote_templates_routes.router)
from routes import doc_intel as doc_intel_routes  # noqa: E402
api_router.include_router(doc_intel_routes.router)
from routes import renovation as renovation_routes  # noqa: E402
api_router.include_router(renovation_routes.router)
from routes import structuro as structuro_routes  # noqa: E402
api_router.include_router(structuro_routes.router)
from routes import structuro_bet as structuro_bet_routes  # noqa: E402
api_router.include_router(structuro_bet_routes.router)
from routes import structuro_plan as structuro_plan_routes  # noqa: E402
api_router.include_router(structuro_plan_routes.router)
from routes import structuro_calc as structuro_calc_routes  # noqa: E402
api_router.include_router(structuro_calc_routes.router)
from routes import btp_router as btp_router_routes  # noqa: E402
api_router.include_router(btp_router_routes.router)
api_router.include_router(billing.router)
api_router.include_router(revenue.router)
api_router.include_router(phase4.router)
api_router.include_router(phase5.router)
api_router.include_router(phase6.router)
api_router.include_router(phase7.router)
api_router.include_router(share.router)
api_router.include_router(admin_revenue.router)
api_router.include_router(admin_expenses.router)
api_router.include_router(admin_apify.router)
api_router.include_router(admin_learning.router)
api_router.include_router(bridge_routes.admin_router)
api_router.include_router(bridge_routes.public_router)
api_router.include_router(media_routes.router)
api_router.include_router(presentation.router)
api_router.include_router(brochures.router)
api_router.include_router(plans_routes.router)
api_router.include_router(plans_routes.quote_router)
api_router.include_router(plans_routes.pc_router)
api_router.include_router(plans_routes.cotes_latest_router)
api_router.include_router(tool_presets_routes.router)
api_router.include_router(referrals_routes.router)
api_router.include_router(clients_routes.router)
api_router.include_router(library_routes.router)
api_router.include_router(documents_routes.router)
api_router.include_router(reviews_routes.router)
api_router.include_router(shared_library_routes.router)
api_router.include_router(shared_library_routes.admin_router)
api_router.include_router(param_library_routes.router)
api_router.include_router(param_library_routes.admin_router)
api_router.include_router(errors_routes.router)
api_router.include_router(emails_routes.router)
from routes import hr as hr_routes
api_router.include_router(hr_routes.router)
from routes import ads as ads_routes
from routes import radar as radar_routes
from routes import journey as journey_routes
api_router.include_router(radar_routes.router)
from routes import radar_contacts
api_router.include_router(radar_contacts.router)
from routes import radar_sync
api_router.include_router(radar_sync.router)
from routes import assistant as assistant_routes
api_router.include_router(assistant_routes.router)
api_router.include_router(assistant_routes.public_router)
from routes import agents as agents_routes
api_router.include_router(agents_routes.router)
from routes import marketing as marketing_routes
api_router.include_router(marketing_routes.public_router)
api_router.include_router(ads_routes.router)
from routes import site as site_routes
api_router.include_router(site_routes.router)
from routes import planning as planning_routes
api_router.include_router(planning_routes.router)
from routes import situations as situations_routes
api_router.include_router(situations_routes.router)
from routes import company as company_routes
api_router.include_router(company_routes.router)
from routes import investors as investors_routes
api_router.include_router(investors_routes.router)
api_router.include_router(autoseo_routes.router)
api_router.include_router(blg_routes.router)
api_router.include_router(newsletter_routes.router)
api_router.include_router(dpgf_routes.router)
api_router.include_router(dpgf_routes.public_router)
api_router.include_router(company_library_routes.router)
api_router.include_router(suppliers_routes.router)
api_router.include_router(steel_routes.router)
api_router.include_router(waterproofing_routes.router)
api_router.include_router(roofing_routes.router)
api_router.include_router(vrd_routes.router)
api_router.include_router(appro_routes.router)
from routes import profitability as profitability_routes
api_router.include_router(profitability_routes.router)
from routes import project_quotes as project_quotes_routes
api_router.include_router(project_quotes_routes.router)
api_router.include_router(help_routes.router)
api_router.include_router(help_routes.admin_router)
api_router.include_router(evolution_routes.router)
api_router.include_router(einvoicing_routes.router)
api_router.include_router(resend_webhook_routes.router)
api_router.include_router(branding_public_routes.router)
from routes import company_page as company_page_routes, today as today_routes  # noqa: E402
api_router.include_router(company_page_routes.router)
api_router.include_router(today_routes.router)
from routes import chantiers as chantiers_routes, onboarding as onboarding_routes  # noqa: E402
api_router.include_router(chantiers_routes.router)
api_router.include_router(onboarding_routes.router)
from routes import portal as portal_routes  # noqa: E402
api_router.include_router(portal_routes.pro_router)
api_router.include_router(portal_routes.router)
from routes import portal_chat as portal_chat_routes  # noqa: E402
api_router.include_router(portal_chat_routes.pro_router)
api_router.include_router(portal_chat_routes.router)
from routes import speech as speech_routes  # noqa: E402
api_router.include_router(speech_routes.router)
api_router.include_router(notifications_routes.router)
from routes import assistant_files as assistant_files_routes, assistant_jobs as assistant_jobs_routes
api_router.include_router(assistant_files_routes.router)
api_router.include_router(assistant_jobs_routes.router)
from routes import study_dossier as study_dossier_routes
api_router.include_router(study_dossier_routes.jobs_router)
api_router.include_router(runway_render_routes.router)
api_router.include_router(journey_routes.router)
from routes import stairs as stairs_routes  # noqa: E402
api_router.include_router(stairs_routes.router)
app.include_router(api_router)
app.add_middleware(ExpenseContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    # SEC-002 : allowlist explicite — jamais '*' avec credentials
    allow_origins=[o.strip() for o in os.environ["CORS_ORIGINS"].split(",")
                   if o.strip() and o.strip() != "*"],
    # Domaines de déploiement Emergent (production et prévisualisations)
    allow_origin_regex=r"https://[a-z0-9-]+\.(emergent\.host|preview\.emergentagent\.com)",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CanonicalOriginMiddleware,
                   proxy_origin=os.environ["CORS_PROXY_ORIGIN"],
                   public_origin=os.environ["FRONTEND_URL"].rstrip("/"))

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


ADMIN_EMAIL = "admin@construpilot.fr"
DEMO_EMAIL = "demo@construpilot.fr"
CLIENT_EMAIL = "client@construpilot.fr"
PRO_EMAIL = "pro@construpilot.fr"
COLLEGUE_EMAIL = "collegue@construpilot.fr"

_MERGE_SKIP = {"users", "user_sessions", "known_devices", "login_attempts", "two_fa_codes",
               "password_reset_tokens"}


async def _merge_legacy_admin(db, owner_email: str):
    """One-shot : fusionne l'ancien compte admin (LEGACY_ADMIN_EMAIL) dans le compte définitif."""
    legacy_email = (os.environ.get("LEGACY_ADMIN_EMAIL") or "").lower().strip()
    if not legacy_email or legacy_email == owner_email:
        return
    new = await db.users.find_one({"email": owner_email})
    old = await db.users.find_one({"email": legacy_email})
    if not new or not old or new.get("admin_merged_from") == legacy_email:
        return
    old_id, new_id = old.get("user_id"), new.get("user_id")
    moved = {}
    for coll in await db.list_collection_names():
        if coll in _MERGE_SKIP or coll.startswith("system."):
            continue
        res = await db[coll].update_many({"user_id": old_id}, {"$set": {"user_id": new_id}})
        if res.modified_count:
            moved[coll] = res.modified_count
    carry = {k: v for k, v in old.items()
             if (k.startswith("brand_") or k in ("phone", "company", "siret", "plan"))
             and v not in (None, "") and new.get(k) in (None, "", "free")}
    carry.update({"admin_merged_from": legacy_email, "role": "admin"})
    await db.users.update_one({"email": owner_email}, {"$set": carry})
    await db.users.update_one({"email": legacy_email},
                              {"$set": {"role": "user", "admin_merged_into": owner_email}})
    logger.info("Ancien admin %s fusionné dans %s : %s", legacy_email, owner_email, moved)


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
    try:
        from engines.llm_keys import load_state
        await load_state()
    except Exception as e:
        logger.warning(f"openai key state load skipped: {e}")
    try:
        from growth.jobs import recover_interrupted
        await recover_interrupted()
    except Exception as e:
        logger.warning(f"growth recover skipped: {e}")
    # SEC-001 : comptes de démonstration créés UNIQUEMENT si SEED_DEMO_DATA=true,
    # et le mot de passe d'un compte existant n'est JAMAIS réécrit.
    if os.environ.get("SEED_DEMO_DATA") == "true":
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
    # Compte administrateur définitif (ADMIN_SEED_EMAIL/PASSWORD) — créé uniquement
    # s'il n'existe pas (jamais de réécriture de mot de passe existant), avec un
    # mot de passe provisoire à changer à la première connexion.
    owner_email = (os.environ.get("ADMIN_SEED_EMAIL") or "").lower().strip()
    owner_pwd = os.environ.get("ADMIN_SEED_PASSWORD") or ""
    if owner_email and owner_pwd:
        existing = await db.users.find_one({"email": owner_email})
        if not existing:
            await db.users.insert_one({
                "email": owner_email, "name": "Administrateur", "role": "admin",
                "plan": "premium", "password_hash": hash_password(owner_pwd),
                "auth_provider": "password", "picture": None,
                "user_id": new_user_id(), "must_change_password": True,
                "two_fa_enabled": False, "two_fa_seed_reset": True,
                "created_at": datetime.now(timezone.utc).isoformat()})
            logger.info("Compte admin définitif créé : %s", owner_email)
        else:
            if existing.get("role") != "admin":
                upd = {"role": "admin"}
                if existing.get("plan") in (None, "free"):
                    upd["plan"] = "premium"
                await db.users.update_one({"email": owner_email}, {"$set": upd})
                logger.info("Compte %s promu administrateur définitif", owner_email)
            # One-time : un seed précédent forçait le 2FA à True, ce qui bloquait la
            # connexion (le code email n'est pas toujours délivrable). On repasse le 2FA
            # en OPT-IN (désactivé) une seule fois — l'admin peut le réactiver depuis /compte.
            if not existing.get("two_fa_seed_reset"):
                await db.users.update_one(
                    {"email": owner_email},
                    {"$set": {"two_fa_enabled": False, "two_fa_seed_reset": True}})
        await _merge_legacy_admin(db, owner_email)

    # Second administrateur : info@construpilot.fr (gestion complète du site).
    # Idempotent : promeut le compte existant (même Google) en admin ; le crée
    # avec un mot de passe provisoire s'il n'existe pas ou n'en a pas encore.
    second_admin_email = (os.environ.get("SECOND_ADMIN_EMAIL")
                          or "info@construpilot.fr").lower().strip()
    second_admin_pwd = os.environ.get("SECOND_ADMIN_PASSWORD") or "CP-Admin-2026!"
    sa = await db.users.find_one({"email": second_admin_email})
    if not sa:
        await db.users.insert_one({
            "email": second_admin_email, "name": "Administrateur ConstruPilot",
            "role": "admin", "plan": "premium",
            "password_hash": hash_password(second_admin_pwd),
            "auth_provider": "password", "picture": None,
            "user_id": new_user_id(), "must_change_password": True,
            "two_fa_enabled": False, "two_fa_seed_reset": True,
            "created_at": datetime.now(timezone.utc).isoformat()})
        logger.info("Compte admin secondaire créé : %s", second_admin_email)
    else:
        upd = {}
        if sa.get("role") != "admin":
            upd["role"] = "admin"
        if not sa.get("password_hash"):
            upd["password_hash"] = hash_password(second_admin_pwd)
            upd["must_change_password"] = True
        if upd:
            await db.users.update_one({"email": second_admin_email}, {"$set": upd})
            logger.info("Compte admin secondaire mis à jour : %s", second_admin_email)

    # Troisième administrateur : deboradsmelo@gmail.com (accès complet du site).
    # Idempotent : crée le compte s'il n'existe pas, sinon le promeut admin et
    # (ré)initialise son mot de passe. Override possible via THIRD_ADMIN_EMAIL/PASSWORD.
    third_admin_email = (os.environ.get("THIRD_ADMIN_EMAIL")
                         or "deboradsmelo@gmail.com").lower().strip()
    third_admin_pwd = os.environ.get("THIRD_ADMIN_PASSWORD")  # jamais en dur dans le code
    ta = await db.users.find_one({"email": third_admin_email})
    if not ta and third_admin_pwd:
        await db.users.insert_one({
            "email": third_admin_email, "name": "Debora Smelo",
            "role": "admin", "plan": "premium",
            "password_hash": hash_password(third_admin_pwd),
            "auth_provider": "password", "picture": None,
            "user_id": new_user_id(), "must_change_password": False,
            "two_fa_enabled": False, "two_fa_seed_reset": True,
            "created_at": datetime.now(timezone.utc).isoformat()})
        logger.info("Compte admin tertiaire créé : %s", third_admin_email)
    elif ta:
        upd = {"role": "admin"}
        if not ta.get("password_hash") and third_admin_pwd:
            upd["password_hash"] = hash_password(third_admin_pwd)
        if upd:
            await db.users.update_one({"email": third_admin_email}, {"$set": upd})
            logger.info("Compte admin tertiaire mis à jour : %s", third_admin_email)

    # CM Rénov (contact@cmrenov.com) : propriétaire → administratrice + compte Business.
    # Idempotent : promeut le compte existant sans jamais réécrire le mot de passe.
    cmrenov_email = (os.environ.get("CMRENOV_EMAIL") or "contact@cmrenov.com").lower().strip()
    cm = await db.users.find_one({"email": cmrenov_email})
    if cm:
        upd = {}
        if cm.get("role") != "admin":
            upd["role"] = "admin"
        if cm.get("account_type") != "pro_business":
            upd["account_type"] = "pro_business"
        if upd:
            await db.users.update_one({"email": cmrenov_email}, {"$set": upd})
            logger.info("Compte %s promu admin + Business", cmrenov_email)

    # Unicité stricte de l'e-mail (empêche définitivement 2 comptes avec le même e-mail).
    # best-effort : si des doublons hérités existent, l'index échoue et est ignoré (log).
    try:
        await db.users.create_index("email", unique=True, name="uniq_email")
    except Exception as e:  # noqa: BLE001
        logger.warning("Index unique sur users.email non créé (doublons hérités ?) : %s", e)


    # Migration one-shot : rendus 3D embarqués → collection plan_renders_3d
    # (les images base64 dans plans_takeoff dépassaient la limite BSON 16 Mo).
    async for p in db.plans_takeoff.find({"renders_3d.0": {"$exists": True}},
                                          {"plan_id": 1, "user_id": 1, "renders_3d": 1}):
        docs = [{**r, "plan_id": p["plan_id"], "user_id": p.get("user_id")}
                for r in (p.get("renders_3d") or [])]
        if docs:
            await db.plan_renders_3d.insert_many(docs)
        await db.plans_takeoff.update_one({"_id": p["_id"]}, {"$unset": {"renders_3d": ""}})
        logger.info("Rendus 3D migrés vers plan_renders_3d : %s (%d)", p["plan_id"], len(docs))
    await db.plan_renders_3d.create_index("plan_id")
    # Sprint 1 Perplexity+ : cache TTL 24h sur les réponses Perplexity
    try:
        from perplexity_plus.client import ensure_indexes as _pplx_ensure
        await _pplx_ensure()
    except Exception as _e:
        logger.warning("perplexity_plus index skipped: %s", _e)
    # btp_solver + plans_pro indexes
    await db.btp_problems.create_index([("user_id", 1), ("generated_at_iso", -1)])
    await db.btp_problems.create_index("problem_id", unique=True)
    await db.plans_pro_jobs.create_index([("user_id", 1), ("created_at", -1)])
    await db.plans_pro_jobs.create_index("job_id", unique=True)
    await db.plans_pro_jobs.create_index("created_at", expireAfterSeconds=30 * 86400)
    from engines.journey import ensure_indexes as _journey_indexes
    await _journey_indexes()
    await db.chantiers.create_index("chantier_id", unique=True)
    await db.chantiers.create_index("ref", unique=True, sparse=True)
    await db.chantier_participants.create_index("participant_id", unique=True)
    await db.chantier_participants.create_index([("chantier_ref", 1), ("email", 1)])
    await db.chantier_participants.create_index([("email", 1), ("status", 1)])
    await db.chantier_participants.create_index("invite_token_hash", sparse=True)
    await db.chantier_milestones.create_index([("chantier_id", 1), ("order", 1)])
    await db.portal_otps.create_index("expires_at", expireAfterSeconds=0)
    await db.chantier_messages.create_index([("chantier_id", 1), ("channel", 1), ("created_at", 1)])
    await db.chantier_messages.create_index("message_id", unique=True)
    await db.chantier_issues.create_index([("chantier_id", 1), ("status", 1), ("created_at", -1)])
    await db.chantier_issues.create_index("issue_id", unique=True)
    await db.portal_email_log.create_index("sent_at", expireAfterSeconds=3600)
    await db.site_reports.create_index([("chantier_id", 1), ("published", 1)])
    await db.chantiers.create_index([("user_id", 1), ("updated_at", -1)])
    for coll in (db.pro_documents, db.plans_takeoff, db.plans_pro_jobs, db.btp_problems, db.site_reports):
        await coll.create_index([("user_id", 1), ("chantier_id", 1)], sparse=True)
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=0)
    await db.password_reset_tokens.create_index("token_hash")
    await db.two_fa_codes.create_index("expires_at", expireAfterSeconds=0)
    await db.two_fa_codes.create_index("pending_token")
    await db.cotes_jobs.create_index("job_id")
    await db.cotes_jobs.create_index("created", expireAfterSeconds=86400)
    await db.known_devices.create_index("device_key")
    await db.reviews.create_index("token")
    await db.reviews.create_index("user_id")
    await db.reviews.create_index("log_id")
    await db.clients.create_index("user_id")
    await db.clients.create_index("client_id")
    await db.resend_webhook_events.create_index("svix_id", unique=True)
    await db.quote_sends.create_index("email_id")
    await db.library_items.create_index("user_id")
    await db.library_items.create_index("item_id")
    await db.pro_documents.create_index("user_id")
    await db.pro_documents.create_index("doc_id")
    await db.pro_documents.create_index([("user_id", 1), ("client_id", 1)])
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
    # Migration prix (08/09/2026) : Premium 19€/190€ · Pro 149€/1570€ · Pro Business 249€/2490€
    # + Project Pass 19,90€ → 50€ (accès Plan 2D + 3 rendus 3D offerts)
    PRICE_MIGRATION = {
        "premium_monthly": 1900, "premium_yearly": 19000,
        "pro_monthly": 14900, "pro_yearly": 157000,
        "pro_business_monthly": 24900, "pro_business_yearly": 249000,
        "project_pass": 5000,
    }
    for plan_id, cents in PRICE_MIGRATION.items():
        await db.plans.update_one({"plan_id": plan_id}, {"$set": {"amount_cents": cents}})
    # Project Pass : ajoute les 3 rendus 3D offerts (quota) même si le plan existe déjà en DB
    await db.plans.update_one(
        {"plan_id": "project_pass"},
        {"$set": {"quotas.free_renders_3d": 3}})
    # Migration textes annuels (économies recalculées avec les nouveaux prix)
    YEARLY_COPY = {
        "premium_yearly": {"tagline": "Économisez ~17 %",
                           "description": "Économisez environ 17 % avec l'abonnement annuel.",
                           "features": ["Toutes les fonctionnalités Premium", "Économisez ~17 %"]},
        "pro_yearly": {"tagline": "Économisez ~12 %",
                       "description": "Facturation annuelle (~12 % d'économies)."},
        "pro_business_yearly": {"tagline": "Économisez ~17 %",
                                "description": "Facturation annuelle (~17 % d'économies)."},
    }
    for plan_id, copy in YEARLY_COPY.items():
        await db.plans.update_one({"plan_id": plan_id}, {"$set": copy})
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
    # Suivi quotidien des courriers postaux Merci Facteur (imprimé → posté → distribué / retour)
    from engines import postal_tracking
    scheduler.add_job(postal_tracking.refresh_all, CronTrigger(hour=7, minute=30),
                      id="daily_postal_tracking", max_instances=1, coalesce=True)
    # Email d'incitation Premium / Pro : J+3 après inscription, comptes gratuits, 1 seule fois (10:00 UTC)
    from engines.upsell import run_upsell_emails, run_upsell_j10_emails
    scheduler.add_job(run_upsell_emails, CronTrigger(hour=10, minute=0),
                      id="upsell_j3_emails", max_instances=1, coalesce=True)
    scheduler.add_job(run_upsell_j10_emails, CronTrigger(hour=10, minute=20),
                      id="upsell_j10_emails", max_instances=1, coalesce=True)
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
    # Corbeille : sauvegarde quotidienne complète des devis/factures (03:00 UTC) et alerte 3 jours avant purge (06:00 UTC)
    from engines.trash_jobs import run_daily_snapshot, run_purge_alerts
    scheduler.add_job(run_daily_snapshot, CronTrigger(hour=3, minute=0),
                      id="daily_document_snapshot", max_instances=1, coalesce=True)
    scheduler.add_job(run_purge_alerts, CronTrigger(hour=6, minute=0),
                      id="trash_purge_alerts", max_instances=1, coalesce=True)
    # État du dossier (assistant) : rappel cloche + e-mail la veille de chaque échéance datée (07:00 UTC)
    from engines.deadline_reminders import run_deadline_reminders
    scheduler.add_job(run_deadline_reminders, CronTrigger(hour=7, minute=0),
                      id="deadline_reminders", max_instances=1, coalesce=True)
    # Growth : audits périodiques selon la cadence de chaque projet + publication des contenus programmés (04:30 UTC)
    from growth.jobs import run_scheduled
    scheduler.add_job(run_scheduled, CronTrigger(hour=4, minute=30), id="growth_scheduled", max_instances=1, coalesce=True)
    from growth.autopilot import run_all as growth_autopilot
    scheduler.add_job(growth_autopilot, CronTrigger(hour=6, minute=0), id="growth_autopilot", max_instances=1, coalesce=True)
    # Relance auto des factures impayées (J+7 / J+15) — chaque jour à 09:00 UTC
    scheduler.add_job(documents_routes.run_invoice_reminders,
                      CronTrigger(hour=9, minute=0),
                      id="invoice_reminders", max_instances=1, coalesce=True)
    # Relance J+3 des nouveaux inscrits sans devis — chaque jour à 10:00 UTC
    scheduler.add_job(auth_routes.run_signup_followups,
                      CronTrigger(hour=10, minute=0),
                      id="signup_j3_followups", max_instances=1, coalesce=True)
    # Email publicitaire de bienvenue — J+1 après inscription, 1 seule fois (09:30 UTC)
    from engines.welcome_marketing import run_welcome_marketing_emails
    scheduler.add_job(run_welcome_marketing_emails,
                      CronTrigger(hour=9, minute=30),
                      id="welcome_marketing_j1", max_instances=1, coalesce=True)
    # Agent Ponte B2B↔B2C — lot quotidien (filet de sécurité) à 11:00 UTC
    from engines.bridge import run_bridge_batch
    scheduler.add_job(run_bridge_batch,
                      CronTrigger(hour=11, minute=0),
                      id="bridge_batch_daily", max_instances=1, coalesce=True)
    # Relance J+2 des prospects (leads landing) qui n'ont pas terminé leur estimation
    scheduler.add_job(leads.run_prospect_reminders,
                      "interval", hours=6, id="prospect_j2_reminders",
                      max_instances=1, coalesce=True)
    # Relance des demandes assignées sans réponse depuis > 24 h (pro + admin)
    scheduler.add_job(leads.run_assignment_reminders,
                      "interval", hours=6, id="lead_assignment_reminders",
                      max_instances=1, coalesce=True)
    # Blog SEO : nouveaux articles BabyLoveGrowth toutes les 2 h
    scheduler.add_job(blg_routes.run_scheduled_sync,
                      "interval", hours=2, id="babylovegrowth_sync",
                      max_instances=1, coalesce=True)
    # Résumé mensuel des surcoûts/économies fournisseurs — le 1er de chaque mois à 07:00 UTC
    scheduler.add_job(einvoicing_routes.run_monthly_overspend_reports,
                      CronTrigger(day=1, hour=7, minute=0),
                      id="einvoice_monthly_report", max_instances=1, coalesce=True)
    # Vérification du budget IA (seuil mensuel d'appels) — toutes les heures
    from engines import ai as ai_engine
    scheduler.add_job(ai_engine.check_ai_budget,
                      "interval", hours=1, id="ai_budget_check",
                      max_instances=1, coalesce=True)
    # Alerte pointage oublié (entrée sans sortie > 12h) — chaque jour à 20:00 UTC
    from routes import hr as hr_routes
    scheduler.add_job(hr_routes.run_forgotten_clockouts,
                      CronTrigger(hour=20, minute=0), id="hr_forgotten_clockouts",
                      max_instances=1, coalesce=True)
    # Relance auto des retenues de garantie proches de l'échéance (1 an) — chaque jour 08:30 UTC
    from routes import situations as situations_routes
    scheduler.add_job(situations_routes.run_retention_reminders,
                      CronTrigger(hour=8, minute=30), id="retention_reminders",
                      max_instances=1, coalesce=True)
    from routes import leads as leads_routes
    scheduler.add_job(leads_routes.run_signup_followups,
                      CronTrigger(hour=9, minute=0), id="signup_followups",
                      max_instances=1, coalesce=True)
    # Rapport nocturne AI Evolution Lab (si activé par l'admin) — chaque jour à 03:00 UTC
    from routes import evolution as evolution_routes
    scheduler.add_job(evolution_routes.run_nightly,
                      CronTrigger(hour=3, minute=0), id="evolution_nightly",
                      max_instances=1, coalesce=True)
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
    # Auditeur de cohérence des calculs : prix de référence des moteurs vs marché (Perplexity) — chaque jour 05:00 UTC
    from engines import calc_auditor
    await calc_auditor.ensure_indexes()
    scheduler.add_job(calc_auditor.run_scheduled, CronTrigger(hour=5, minute=0),
                      id="calc_auditor_daily", max_instances=1, coalesce=True)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Scheduler started (daily price alerts @ 08:00 UTC)")

    from engines.assistant_jobs import start_workers
    app.state.assistant_workers = await start_workers()
    from routes.agents import start_agent_workers
    app.state.agent_workers = await start_agent_workers()
    from engines.study_dossier_jobs import start_workers as start_study_workers
    app.state.study_workers = await start_study_workers()
    logger.info("ConstruPilot backend prêt")


@app.on_event("shutdown")
async def shutdown_db_client():
    import asyncio
    workers = (getattr(app.state, "assistant_workers", []) + getattr(app.state, "agent_workers", [])
               + getattr(app.state, "study_workers", []))
    for worker in workers:
        worker.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
    client.close()
