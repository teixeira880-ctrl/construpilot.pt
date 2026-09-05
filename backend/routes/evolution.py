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
                  "nightly_enabled": False, "nightly_email": None,
                  "alert_enabled": False, "alert_threshold": 90, "alert_email": None,
                  "active_ai_model": "opus", "arena_nightly_enabled": False}


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
    alert_enabled: bool | None = None
    alert_threshold: float | None = Field(default=None, ge=0, le=100)
    alert_email: str | None = None
    active_ai_model: str | None = None
    arena_nightly_enabled: bool | None = None


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
    await _maybe_alert(cfg, result)
    return result


class PromoteIn(BaseModel):
    model_key: str


@router.post("/promote")
async def promote(body: PromoteIn) -> dict:
    if body.model_key not in evolution.EVO_AI_MODELS:
        raise HTTPException(422, "Modèle inconnu")
    await db.app_settings.update_one({"_id": "evolution"},
                                     {"$set": {"active_ai_model": body.model_key}}, upsert=True)
    return {"ok": True, "active_ai_model": body.model_key,
            "note": "Le chatbot d'aide et les tests IA utilisent désormais ce modèle."}


async def _run_nightly_arena(cfg: dict, level: int, to: str | None) -> None:
    """Arène nocturne : compare le modèle actif aux autres ; alerte si un modèle
    plus RAPIDE atteint AU MOINS la même précision que l'actif."""
    active = cfg.get("active_ai_model", "opus")
    n = min(int(cfg.get("ai_budget_calls", 30) or 30), 12)
    base = await evolution.run_ai_batch(n, level, 777, active)
    base_acc = base.get("ai_accuracy") or 0
    base_lat = base.get("ai_avg_latency_s") or 99
    better = []
    for m in evolution.EVO_AI_MODELS:
        if m == active:
            continue
        r = await evolution.run_ai_batch(n, level, 777, m)
        if (r.get("ai_accuracy") or 0) >= base_acc and (r.get("ai_avg_latency_s") or 99) < base_lat:
            better.append({"model": m, "accuracy": r.get("ai_accuracy"),
                           "latency": r.get("ai_avg_latency_s")})
    await db.evolution_compares.insert_one({
        "created_at": _now(), "nightly": True, "active": active,
        "active_accuracy": base_acc, "active_latency": base_lat, "faster_equal": better})
    if better and to:
        from engines.emailer import send_email, wrap_company_html
        rows = "".join(f"<li><b>{b['model']}</b> — précision {round((b['accuracy'] or 0)*100)}% · "
                       f"{b['latency']}s (actuel {active} : {round(base_acc*100)}% · {base_lat}s)</li>"
                       for b in better)
        body = (f"<h2>🏁 Arène nocturne — modèle plus rapide détecté</h2>"
                f"<p>Un ou plusieurs modèles égalent la précision de <b>{active}</b> "
                f"tout en étant plus rapides :</p><ul>{rows}</ul>"
                f"<p>Promouvez-les depuis l'onglet AI Evolution Lab pour réduire coûts/latence.</p>")
        html = wrap_company_html("Arène nocturne ConstruPilot", body, company_name="ConstruPilot")
        try:
            await send_email(to, "[ConstruPilot] 🏁 Un modèle IA plus rapide égale l'actuel", html)
        except Exception:  # noqa: BLE001
            pass



async def _maybe_alert(cfg: dict, result: dict) -> None:
    """Alerte e-mail immédiate si le Fitness Score passe sous le seuil."""
    if not cfg.get("alert_enabled"):
        return
    threshold = float(cfg.get("alert_threshold", 90))
    if result.get("fitness_score", 100) >= threshold:
        return
    to = cfg.get("alert_email") or cfg.get("nightly_email")
    if not to:
        return
    from engines.emailer import send_email, wrap_company_html
    body = (f"<h2 style='color:#dc2626'>⚠️ Alerte régression — AI Evolution Lab</h2>"
            f"<p>Le Fitness Score est tombé à <b>{result['fitness_score']}</b> / 100 "
            f"(seuil d'alerte : {threshold}).</p>"
            f"<p>Génération #{result.get('generation')} · {result['size']} tests · "
            f"réussite {round(result['pass_rate']*100)}%.</p>"
            f"<h3>Principaux clusters d'échecs</h3><ul>"
            + "".join(f"<li>{c['cluster']} — <b>{c['count']}</b></li>"
                      for c in result.get("failure_clusters", [])[:8]) + "</ul>")
    html = wrap_company_html("Alerte régression ConstruPilot", body, company_name="ConstruPilot")
    try:
        await send_email(to, f"[ConstruPilot] ⚠️ Alerte régression — Fitness {result['fitness_score']}/100", html)
    except Exception:  # noqa: BLE001
        pass


class CompareIn(BaseModel):
    ai_calls: int = Field(default=10, ge=1, le=100)
    level: int = Field(default=2, ge=1, le=6)
    champion_model: str = "opus"
    challenger_model: str = "sonnet"
    seed: int | None = 12345


@router.post("/compare")
async def compare(body: CompareIn, user=Depends(admin_user)) -> dict:
    """Arène Champion vs Challenger : mêmes scénarios IA (même seed), 2 modèles comparés."""
    seed = body.seed if body.seed is not None else 12345
    champ = await evolution.run_ai_batch(body.ai_calls, body.level, seed, body.champion_model)
    chall = await evolution.run_ai_batch(body.ai_calls, body.level, seed, body.challenger_model)

    def score(r):
        acc = r.get("ai_accuracy") or 0
        lat = r.get("ai_avg_latency_s") or 99
        return acc * 100 - lat * 0.5  # précision d'abord, vitesse en second

    winner = "champion" if score(champ) >= score(chall) else "challenger"
    await db.evolution_compares.insert_one({
        "created_at": _now(), "seed": seed, "level": body.level, "ai_calls": body.ai_calls,
        "champion": {"model": body.champion_model, **champ},
        "challenger": {"model": body.challenger_model, **chall}, "winner": winner})
    return {"champion": {"model": body.champion_model, **champ},
            "challenger": {"model": body.challenger_model, **chall},
            "winner": winner, "models": list(evolution.EVO_AI_MODELS.keys())}


@router.get("/reports")
async def reports(limit: int = 60, user=Depends(admin_user)) -> dict:
    """Historique des rapports nocturnes + évolution semaine par semaine."""
    import datetime as _dt
    cur = db.evolution_runs.find({"nightly": True}, {"_id": 0, "per_category": 0}) \
        .sort("created_at", -1).limit(min(limit, 200))
    items = await cur.to_list(200)
    weeks = {}
    for r in items:
        try:
            d = _dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            wk = f"{d.isocalendar().year}-S{d.isocalendar().week:02d}"
        except Exception:  # noqa: BLE001
            continue
        w = weeks.setdefault(wk, {"week": wk, "runs": 0, "fit_sum": 0.0, "pass_sum": 0.0})
        w["runs"] += 1
        w["fit_sum"] += r.get("fitness_score", 0)
        w["pass_sum"] += r.get("pass_rate", 0)
    weekly = [{"week": w["week"], "runs": w["runs"],
               "avg_fitness": round(w["fit_sum"] / w["runs"], 2),
               "avg_pass_rate": round(w["pass_sum"] / w["runs"], 4)}
              for w in sorted(weeks.values(), key=lambda x: x["week"])]
    return {"items": items, "weekly": weekly}


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
    await _maybe_alert(cfg, result)
    if cfg.get("arena_nightly_enabled") and cfg.get("ai_enabled"):
        await _run_nightly_arena(cfg, level, to or cfg.get("alert_email"))
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
