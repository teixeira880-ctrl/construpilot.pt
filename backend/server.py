from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone
import boto3

from stair_engine import (
    DTU_36_3_FR,
    HalfTurnInput,
    QuarterTurnBottomInput,
    QuarterTurnTopInput,
    StairInput,
    StairResult,
    compute_half_turn,
    compute_quarter_turn_bottom,
    compute_quarter_turn_top,
    compute_straight,
)

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Tigris S3-compatible client
s3_client = boto3.client(
    's3',
    endpoint_url=os.environ.get('TIGRIS_ENDPOINT', 'http://localhost:8085'),
    aws_access_key_id=os.environ.get('TIGRIS_ACCESS_KEY_ID', ''),
    aws_secret_access_key=os.environ.get('TIGRIS_SECRET_ACCESS_KEY', ''),
    region_name='auto',
)
TIGRIS_BUCKET = os.environ.get('TIGRIS_BUCKET', 'default-bucket')

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str


# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)

    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()

    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)

    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])

    return status_checks

# ---------------------------------------------------------------------------
# STAIRPILOT — routes moteur de calcul (Phase 0)
# ---------------------------------------------------------------------------

@api_router.post("/calculate/straight", response_model=StairResult)
async def calculate_straight(payload: StairInput) -> StairResult:
    """Calcule un escalier droit béton (moteur déterministe, DTU 36.3)."""
    return compute_straight(payload)


@api_router.post("/calculate/quarter-turn-bottom", response_model=StairResult)
async def calculate_quarter_turn_bottom(payload: QuarterTurnBottomInput) -> StairResult:
    """Calcule un escalier quart tournant bas (mode 'balanced' ou 'straight')."""
    return compute_quarter_turn_bottom(payload)


@api_router.post("/calculate/quarter-turn-top", response_model=StairResult)
async def calculate_quarter_turn_top(payload: QuarterTurnTopInput) -> StairResult:
    """Calcule un escalier quart tournant haut (mode 'balanced' ou 'straight')."""
    return compute_quarter_turn_top(payload)


@api_router.post("/calculate/half-turn", response_model=StairResult)
async def calculate_half_turn(payload: HalfTurnInput) -> StairResult:
    """Calcule un escalier demi-tournant (mode 'balanced' ou 'straight')."""
    return compute_half_turn(payload)


@api_router.get("/norms/fr")
async def get_norms_fr():
    """Retourne les seuils DTU 36.3 utilisés par le moteur (structure configurable)."""
    return DTU_36_3_FR.as_dict()


@api_router.get("/openapi.json", include_in_schema=False)
async def api_openapi():
    """Alias de l'OpenAPI schema sous /api/openapi.json (requis par la spec Phase 0)."""
    return app.openapi()


# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
