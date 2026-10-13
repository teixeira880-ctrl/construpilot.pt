"""Routes admin — Apify (scraping on-demand : leads, appels d'offres, veille prix).

Le token Apify reste côté backend. Modèle : démarrer un run, puis interroger
l'état via /jobs/{job_id} ; à la fin on récupère les items et on les persiste
éventuellement dans `apify_results`.
"""
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user
from engines import apify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/apify", tags=["admin-apify"],
                   dependencies=[Depends(admin_user)])

ACTOR_RE = re.compile(r"^[A-Za-z0-9_.~/-]{1,200}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/presets")
async def presets() -> dict:
    """Cas d'usage préconfigurés (défauts code + overrides admin) + état du token."""
    import os
    merged = await _merged_presets()
    return {"configured": bool(os.environ.get("APIFY_API_TOKEN")), "presets": merged}


async def _merged_presets() -> dict:
    """Fusionne les presets du code avec les overrides enregistrés en base."""
    import copy
    merged = copy.deepcopy(apify.PRESETS)
    async for ov in db.apify_presets.find({}, {"_id": 0}):
        key = ov.get("key")
        if key in merged:
            if ov.get("actor_id"):
                merged[key]["actor_id"] = ov["actor_id"]
            if isinstance(ov.get("input"), dict):
                merged[key]["input"] = ov["input"]
            merged[key]["customized"] = True
    return merged


class PresetBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)


@router.put("/presets/{key}")
async def save_preset(key: str, body: PresetBody, admin=Depends(admin_user)) -> dict:
    """Enregistre un override de preset (hashtags, ville, catégories, URLs…) sans toucher au code."""
    if key not in apify.PRESETS:
        raise HTTPException(404, "Preset inconnu")
    if not ACTOR_RE.match(body.actor_id):
        raise HTTPException(400, "Identifiant d'Actor invalide")
    await db.apify_presets.update_one(
        {"key": key},
        {"$set": {"key": key, "actor_id": body.actor_id, "input": body.input,
                  "updated_by": (admin or {}).get("email") or (admin or {}).get("user_id"),
                  "updated_at": _now()}},
        upsert=True)
    return {"ok": True, "presets": await _merged_presets()}


@router.delete("/presets/{key}")
async def reset_preset(key: str) -> dict:
    """Réinitialise un preset à sa valeur par défaut (supprime l'override)."""
    await db.apify_presets.delete_one({"key": key})
    return {"ok": True, "presets": await _merged_presets()}


class RunBody(BaseModel):
    actor_id: str = Field(min_length=1, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict)
    use_case: str = ""
    max_items: int = Field(default=50, ge=1, le=1000)
    persist: bool = False
    emails_only: bool = True


@router.post("/run")
async def run(body: RunBody, admin=Depends(admin_user)) -> dict:
    """Démarre un run d'Actor Apify et enregistre un job interrogeable."""
    if not ACTOR_RE.match(body.actor_id):
        raise HTTPException(400, "Identifiant d'Actor invalide")
    try:
        started = await apify.start_run(body.actor_id, body.input)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(502, str(e))
    job = {
        "job_id": "apf_" + secrets.token_hex(6),
        "run_id": started["id"],
        "dataset_id": started.get("datasetId"),
        "status": started.get("status") or "RUNNING",
        "actor_id": body.actor_id,
        "use_case": body.use_case[:40],
        "max_items": body.max_items,
        "persist": body.persist,
        "emails_only": body.emails_only,
        "count": 0,
        "fetched": False,
        "created_by": (admin or {}).get("email") or (admin or {}).get("user_id"),
        "created_at": _now(),
    }
    await db.apify_jobs.insert_one({**job})
    return {k: job[k] for k in ("job_id", "run_id", "status", "actor_id", "use_case")}


@router.get("/jobs/{job_id}")
async def job_status(job_id: str) -> dict:
    """Interroge l'état du run ; à la réussite, récupère/persiste les items une fois."""
    job = await db.apify_jobs.find_one({"job_id": job_id}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Job introuvable")
    if job["status"] not in apify.TERMINAL:
        try:
            run_info = await apify.get_run(job["run_id"])
        except ValueError as e:
            raise HTTPException(502, str(e))
        job["status"] = run_info["status"] or job["status"]
        if run_info.get("datasetId"):
            job["dataset_id"] = run_info["datasetId"]
        await db.apify_jobs.update_one(
            {"job_id": job_id},
            {"$set": {"status": job["status"], "dataset_id": job.get("dataset_id")}})

    items: list[dict] = []
    if job["status"] == "SUCCEEDED":
        if job.get("fetched"):
            rec = await db.apify_results.find_one({"job_id": job_id}, {"_id": 0, "items": 1})
            items = (rec or {}).get("items", [])
        elif job.get("dataset_id"):
            try:
                raw = await apify.get_dataset_items(job["dataset_id"], job["max_items"])
            except ValueError as e:
                raise HTTPException(502, str(e))
            if job.get("use_case") == "leads":
                try:
                    from engines.bridge import upsert_artisans_from_items
                    added = await upsert_artisans_from_items(raw, source=job["actor_id"])
                    await db.apify_jobs.update_one(
                        {"job_id": job_id}, {"$set": {"artisans_added": added}})
                except Exception:  # noqa: BLE001
                    pass
            items = apify.extract_emails(raw) if job.get("emails_only") else raw
            await db.apify_jobs.update_one(
                {"job_id": job_id}, {"$set": {"fetched": True, "count": len(items)}})
            if job.get("persist"):
                await db.apify_results.insert_one({
                    "job_id": job_id, "actor_id": job["actor_id"], "use_case": job.get("use_case"),
                    "items": items, "count": len(items),
                    "created_by": job.get("created_by"), "created_at": _now()})

    return {"job_id": job_id, "status": job["status"], "count": len(items),
            "persisted": bool(job.get("persist")), "items": items}


@router.get("/history")
async def history(limit: int = 20) -> dict:
    """Derniers runs Apify (sans les items)."""
    rows = await db.apify_jobs.find(
        {}, {"_id": 0, "job_id": 1, "actor_id": 1, "use_case": 1, "status": 1,
             "count": 1, "persist": 1, "created_by": 1, "created_at": 1}
    ).sort("created_at", -1).to_list(min(limit, 100))
    return {"jobs": rows}
