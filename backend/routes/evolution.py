"""ConstruPilot AI Evolution Lab — routes admin (toggle, lancement de lots, dashboard)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from core.db import db
from core.security import admin_user
from engines import evolution

router = APIRouter(prefix="/admin/evolution", tags=["evolution"],
                   dependencies=[Depends(admin_user)])

DEFAULT_CONFIG = {"enabled": False, "level": 2, "batch_size": 2000,
                  "ai_enabled": False, "ai_budget_calls": 50,
                  "max_evolution_mode": False}


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _config() -> dict:
    doc = await db.app_settings.find_one({"_id": "evolution"}) or {}
    cfg = {**DEFAULT_CONFIG, **{k: v for k, v in doc.items() if k != "_id"}}
    return cfg


@router.get("/config")
async def get_config() -> dict:
    return await _config()


class ConfigIn(BaseModel):
    enabled: bool | None = None
    level: int | None = Field(default=None, ge=1, le=6)
    batch_size: int | None = Field(default=None, ge=1, le=20000)
    ai_enabled: bool | None = None
    ai_budget_calls: int | None = Field(default=None, ge=0, le=5000)
    max_evolution_mode: bool | None = None


@router.put("/config")
async def set_config(body: ConfigIn) -> dict:
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.app_settings.update_one({"_id": "evolution"}, {"$set": upd}, upsert=True)
    return await _config()


class RunIn(BaseModel):
    size: int | None = Field(default=None, ge=1, le=20000)
    level: int | None = Field(default=None, ge=1, le=6)
    seed: int | None = None


@router.post("/run")
async def run(body: RunIn) -> dict:
    cfg = await _config()
    if not cfg["enabled"]:
        raise HTTPException(409, "Evolution Lab désactivé — activez-le d'abord dans la configuration.")
    size = body.size or cfg["batch_size"]
    level = body.level or cfg["level"]
    if cfg.get("max_evolution_mode"):
        size = min(20000, size * 4)
        level = max(level, 4)
    # Tests déterministes (aucun appel LLM) → exécutés dans un thread pour ne pas bloquer.
    result = await run_in_threadpool(evolution.run_batch, size, level, body.seed)

    gen = await db.evolution_runs.count_documents({}) + 1
    result["generation"] = gen
    await db.evolution_runs.insert_one({**result})
    result.pop("_id", None)
    return result


@router.get("/runs")
async def runs(limit: int = 30) -> dict:
    cur = db.evolution_runs.find({}, {"_id": 0, "per_category": 0}).sort("created_at", -1).limit(min(limit, 100))
    return {"items": await cur.to_list(100)}


@router.get("/dashboard")
async def dashboard() -> dict:
    cfg = await _config()
    total = await db.evolution_runs.count_documents({})
    last = await db.evolution_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    recent = await db.evolution_runs.find({}, {"_id": 0, "generation": 1, "fitness_score": 1,
                                               "pass_rate": 1, "created_at": 1}) \
        .sort("created_at", 1).to_list(200)
    # agrégat volume de tests
    agg = await db.evolution_runs.aggregate([
        {"$group": {"_id": None, "tests": {"$sum": "$size"}, "passed": {"$sum": "$passed"}}}
    ]).to_list(1)
    tests_total = (agg[0]["tests"] if agg else 0)
    passed_total = (agg[0]["passed"] if agg else 0)
    return {
        "config": cfg,
        "runs_total": total,
        "tests_total": tests_total,
        "passed_total": passed_total,
        "global_pass_rate": round(passed_total / tests_total, 4) if tests_total else None,
        "personas": len(evolution.PERSONAS),
        "project_types": len(evolution.PROJECT_TYPES),
        "categories": evolution.CATEGORIES,
        "current_generation": total,
        "champion": last,               # dernière config = champion courant (sandbox)
        "last_run": last,
        "evolution_graph": [{"generation": r.get("generation"), "fitness": r.get("fitness_score"),
                             "pass_rate": r.get("pass_rate")} for r in recent],
    }
