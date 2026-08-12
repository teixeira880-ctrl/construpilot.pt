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
from engines import storage  # noqa: E402
from routes import (auth as auth_routes, estimation_routes, tools, prices, projects,
                    ai_routes, leads, admin, photos)  # noqa: E402

app = FastAPI(title="CMRENOV AI API")
api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"app": "CMRENOV AI", "tagline": "Votre expert travaux, de l'idée au chantier.",
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

ADMIN_EMAIL = "admin@cmrenov.fr"
DEMO_EMAIL = "demo@cmrenov.fr"


@app.on_event("startup")
async def seed():
    for email, name, role, pw in ((ADMIN_EMAIL, "Admin CMRENOV", "admin", "Cmrenov2026!"),
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
    try:
        storage.init_storage()
    except Exception as e:
        logger.warning(f"Storage init skipped: {e}")
    logger.info("CMRENOV AI backend prêt")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
