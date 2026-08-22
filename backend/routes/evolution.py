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
                  "ai_enabled": False, "ai_budget_calls": 30,
                  "max_evolution_mode": False,
                  "nightly_enabled": False, "nightly_email": None}


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
    nightly_enabled: bool | None = None
    nightly_email: str | None = None


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

    # Tests IA réels (opt-in, plafonnés) — coût maîtrisé par ai_budget_calls.
    if cfg.get("ai_enabled") and cfg.get("ai_budget_calls", 0) > 0:
        ai_res = await evolution.run_ai_batch(cfg["ai_budget_calls"], level, body.seed)
        result.update(ai_res)
        if ai_res.get("ai_accuracy") is not None:
            # intègre l'IA au fitness (poids 10 %) et aux clusters
            result["fitness_score"] = round(result["fitness_score"] * 0.9 + ai_res["ai_accuracy"] * 100 * 0.1, 2)
            result["failure_clusters"] = (result["failure_clusters"] + ai_res["ai_failure_clusters"])[:25]

    gen = await db.evolution_runs.count_documents({}) + 1
    result["generation"] = gen
    await db.evolution_runs.insert_one({**result})
    result.pop("_id", None)
    return result


async def run_nightly() -> dict | None:
    """Lot nocturne planifié + e-mail du rapport (Fitness + nouveaux clusters). Job scheduler."""
    cfg = await _config()
    if not cfg.get("nightly_enabled"):
        return None
    prev = await db.evolution_runs.find_one({}, {"_id": 0, "failure_clusters": 1},
                                            sort=[("created_at", -1)])
    prev_keys = {c["cluster"] for c in (prev or {}).get("failure_clusters", [])}

    size = cfg.get("batch_size", 2000)
    level = cfg.get("level", 2)
    if cfg.get("max_evolution_mode"):
        size = min(20000, size * 4); level = max(level, 4)
    result = await run_in_threadpool(evolution.run_batch, size, level, None)
    if cfg.get("ai_enabled") and cfg.get("ai_budget_calls", 0) > 0:
        result.update(await evolution.run_ai_batch(cfg["ai_budget_calls"], level, None))
    result["generation"] = await db.evolution_runs.count_documents({}) + 1
    result["nightly"] = True
    await db.evolution_runs.insert_one({**result})

    new_clusters = [c for c in result.get("failure_clusters", []) if c["cluster"] not in prev_keys]
    to = cfg.get("nightly_email")
    if to:
        await _send_report_email(to, result, new_clusters)
    result.pop("_id", None)
    return {"sent_to": to, "new_clusters": len(new_clusters), "fitness": result["fitness_score"]}


async def _send_report_email(to: str, run: dict, new_clusters: list) -> None:
    from engines.emailer import send_email, wrap_company_html
    acc = run.get("accuracy", {})
    rows = "".join(f"<tr><td style='padding:4px 8px'>{k}</td>"
                   f"<td style='padding:4px 8px;text-align:right'><b>{round(v*100)}%</b></td></tr>"
                   for k, v in acc.items())
    ai_line = (f"<p>Tests IA : <b>{run.get('ai_passed')}/{run.get('ai_calls')}</b> "
               f"(précision {round((run.get('ai_accuracy') or 0)*100)}%)</p>"
               if run.get("ai_calls") else "")
    clusters_html = ("<ul>" + "".join(f"<li>{c['cluster']} — <b>{c['count']}</b></li>"
                                      for c in new_clusters[:10]) + "</ul>") if new_clusters else "<p>Aucun nouveau cluster d'échec 🎉</p>"
    body = (f"<h2>Rapport nocturne — AI Evolution Lab</h2>"
            f"<p>Génération <b>#{run['generation']}</b> · {run['size']} tests · niveau {run['level']}</p>"
            f"<p style='font-size:20px'>Fitness Score : <b style='color:#FF5A00'>{run['fitness_score']}</b> / 100</p>"
            f"<p>Taux de réussite : <b>{round(run['pass_rate']*100)}%</b> ({run['passed']}/{run['size']})</p>"
            f"{ai_line}"
            f"<h3>Précision par catégorie</h3><table>{rows}</table>"
            f"<h3>Nouveaux clusters d'échecs</h3>{clusters_html}")
    html = wrap_company_html("Rapport nocturne AI Evolution Lab", body, company_name="ConstruPilot")
    try:
        await send_email(to, f"[ConstruPilot] Rapport nocturne — Fitness {run['fitness_score']}/100", html)
    except Exception:  # noqa: BLE001
        pass


@router.post("/send-report")
async def send_report_now(user=Depends(admin_user)) -> dict:
    cfg = await _config()
    to = cfg.get("nightly_email") or user.get("email")
    last = await db.evolution_runs.find_one({}, {"_id": 0}, sort=[("created_at", -1)])
    if not last:
        raise HTTPException(409, "Aucun lot exécuté — lancez d'abord un lot.")
    await _send_report_email(to, last, last.get("failure_clusters", []))
    return {"ok": True, "sent_to": to}


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
