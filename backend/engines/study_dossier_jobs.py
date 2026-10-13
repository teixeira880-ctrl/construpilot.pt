"""Persistent, owner-scoped PC study jobs; page navigation never cancels work."""
import asyncio
import base64
import copy
import json
import logging
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.db import db
from engines.study_dossier import StudyError, build_dossier, fingerprint

log = logging.getLogger(__name__)
ACTIVE = ("queued", "running", "committing")
MAX_PAGES = 64
LEASE_SECONDS = 45


def now():
    return datetime.now(timezone.utc)


def public(job):
    return {k: job.get(k) for k in ("job_id", "plan_id", "status", "progress", "error", "created_at", "updated_at", "cancel_requested")}


def selection(pages, requested):
    ids = list(range(len(pages))) if requested is None else list(dict.fromkeys(requested))
    if not ids or len(ids) > MAX_PAGES:
        raise HTTPException(422, f'Selecione entre 1 e {MAX_PAGES} páginas; nenhuma página é retirada silenciosamente.')
    if any(type(i) is not int or i < 0 or i >= len(pages) for i in ids):
        raise HTTPException(422, "Número de página inválido")
    return ids


async def study_settings(owner_id, saved=None):
    from routes.plans_pc import _load_pc_settings
    from routes.plans_common import _resolve_branding
    from core.fiscal import policy_for
    settings = await _load_pc_settings(owner_id)
    branding = await _resolve_branding(owner_id)
    country = (saved or {}).get("country") or (branding or {}).get("country")
    policy = policy_for(country)
    return {"country": country, "vat_rate": (saved or {}).get("vat_rate", policy["default_rate"]),
            "dossier_unit_prices": settings.get("dossier_unit_prices") or {},
            "vat_assumed": (saved or {}).get("vat_assumed", True)}


async def enqueue_study(plan_id, body, user):
    from routes.plans_pc import _pc_owner_id
    if user.get("active") is False or user.get("company_active") is False:
        raise HTTPException(403, "Conta desativada")
    owner_id = await _pc_owner_id(plan_id, user, write=True)
    plan = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": owner_id},
                                        {"_id": 0, "pages.index": 1, "updated_at": 1})
    indices = selection((plan or {}).get("pages") or [], body.get("pages"))
    request = str(body.get("request") or "Estrutura e alvenarias, cave ou desvão sanitário se existir, rebocos e alvenaria de vedação; exclui cobertura e acabamentos.")[:2000]
    digest = fingerprint({"indices": indices, "request": request})
    active_key = f"{owner_id}:{plan_id}"
    old = await db.pc_study_jobs.find_one({"active_key": active_key, "active": True}, {"_id": 0})
    if old:
        if old["payload_hash"] != digest:
            raise HTTPException(409, "Já está em curso um estudo diferente sobre esta planta")
        return public(old)
    request_id = str(body.get("request_id") or uuid.uuid4().hex)[:80]
    ident = "pcj_" + fingerprint([user["user_id"], plan_id, request_id])[:28]
    previous = await db.pc_study_jobs.find_one({"job_id": ident, "user_id": user["user_id"]}, {"_id": 0})
    if previous:
        if previous["payload_hash"] != digest:
            raise HTTPException(409, "Identificador de pedido já utilizado")
        return public(previous)
    timestamp = now().isoformat()
    job = {"job_id": ident, "user_id": user["user_id"], "owner_id": owner_id, "plan_id": plan_id,
           "active_key": active_key, "active": True, "payload_hash": digest,
           "indices": indices, "request": request, "status": "queued", "created_at": timestamp,
           "updated_at": timestamp, "expected_updated_at": plan.get("updated_at"),
           "progress": {"phase": "Em espera", "completed_pages": 0, "total_pages": len(indices)},
           "cancel_requested": False, "error": None}
    try:
        await db.pc_study_jobs.insert_one(copy.deepcopy(job))
    except DuplicateKeyError:
        old = await db.pc_study_jobs.find_one({"active_key": active_key, "active": True}, {"_id": 0})
        if old and old.get("payload_hash") == digest:
            return public(old)
        raise HTTPException(409, "Já está em curso um estudo") from None
    return public(job)


async def owned_job(job_id, user):
    job = await db.pc_study_jobs.find_one({"job_id": job_id, "user_id": user["user_id"]}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Estudo não encontrado")
    return job


async def finish(job, status, error=None):
    result = await db.pc_study_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": {"$in": ["running", "committing"]}},
        {"$set": {"status": status, "active": False, "error": error, "updated_at": now().isoformat()}, "$unset": {"lease_until": ""}})
    if result.matched_count and status in ("completed", "failed", "interrupted"):
        await db.notifications.update_one({"user_id": job["user_id"], "pc_job_id": job["job_id"]}, {"$setOnInsert": {
            "notif_id": "n_"+job["job_id"], "title": "Estudo e orçamento disponíveis" if status == "completed" else "Estudo a retomar",
            "message": "Consulte as medições, hipóteses e preços." if status == "completed" else (error or "Traitement interrompu"),
            "link": f"/plan?open={job['plan_id']}&study=1", "type": "study", "read": False, "created_at": now().isoformat()}}, upsert=True)


async def run_job(job):
    from routes.plans_pc import _pc_owner_id
    from engines.expenses.context import bind
    from engines.plan_sources import load_plan_source
    from engines.study_dossier_ai import analyze_dossier
    user = await db.users.find_one({"user_id": job["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user or user.get("active") is False or user.get("company_active") is False:
        raise StudyError("Conta indisponível")
    owner = await _pc_owner_id(job["plan_id"], user, write=True)
    bind(user)
    plan = await db.plans_takeoff.find_one({"plan_id": job["plan_id"], "user_id": owner}, {"_id": 0})
    if not plan or plan.get("updated_at") != job["expected_updated_at"]:
        raise StudyError("A planta mudou desde o pedido; relance sobre a versão atual")
    source = await load_plan_source(db, job["plan_id"], owner)
    pdf = base64.b64decode(source["data_b64"]) if source else None
    async def cancelled():
        fresh = await db.pc_study_jobs.find_one({"job_id": job["job_id"], "worker": job["worker"]}, {"_id": 0})
        return not fresh or fresh.get("status") != "running" or fresh.get("cancel_requested")
    async def progress(value):
        await db.pc_study_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": "running"},
                                       {"$set": {"progress": value, "updated_at": now().isoformat()}})
    spec, coverage, analyses = await analyze_dossier(plan.get("pages") or [], job["indices"], pdf_bytes=pdf,
                                                    request=job["request"], progress=progress, cancelled=cancelled)
    await progress({"phase": "Cálculo e controlo do orçamento", "completed_pages": len(job["indices"]), "total_pages": len(job["indices"])})
    settings = await study_settings(owner)
    # The project country, when actually read, proposes the fiscal regime visibly.
    if not settings.get("country") and spec.get("country") in ("FR", "PT"):
        from core.fiscal import policy_for
        settings.update(country=spec["country"], vat_rate=policy_for(spec["country"])["default_rate"])
    study = build_dossier(spec, page_count=len(plan.get("pages") or []), settings=settings, coverage=coverage,
                          source={"filename": plan.get("filename"), "sha256": (source or {}).get("sha256"), "plan_id": job["plan_id"]})
    study["page_analyses"] = analyses
    if len(json.dumps(study, ensure_ascii=False).encode()) > 10_000_000:
        raise StudyError("Estudo demasiado volumoso para um único processo")
    if await cancelled():
        raise asyncio.CancelledError()
    # Permission and source generation are checked again before the only write.
    await _pc_owner_id(job["plan_id"], user, write=True)
    current_source = await db.plan_sources.find_one({"plan_id": job["plan_id"], "user_id": owner}, {"_id": 0, "sha256": 1})
    if (current_source or {}).get("sha256") != (source or {}).get("sha256"):
        raise StudyError("O ficheiro de origem mudou durante o estudo")
    claim = await db.pc_study_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"],
        "status": "running", "cancel_requested": False, "lease_until": {"$gt": now()}},
        {"$set": {"status": "committing", "progress.phase": "Registo do resultado"}})
    if not claim.matched_count:
        raise asyncio.CancelledError()
    study["job_id"] = job["job_id"]
    result = await db.plans_takeoff.update_one({"plan_id": job["plan_id"], "user_id": owner,
                                             "updated_at": job["expected_updated_at"]},
        {"$set": {"pc_study": study, "updated_at": now().isoformat()}})
    if not result.matched_count:
        raise StudyError("O processo foi modificado durante o estudo; as modificações existentes são conservadas")
    if plan.get("pc_study"):
        await db.pc_study_history.insert_one({"plan_id": job["plan_id"], "user_id": owner,
            "saved_at": now().isoformat(), "source": "dossier", "study": plan["pc_study"],
            "ht": (plan["pc_study"].get("totals") or {}).get("ht"), "ttc": (plan["pc_study"].get("totals") or {}).get("ttc")})


async def worker():
    while True:
        job = None
        try:
            await db.pc_study_jobs.update_many({"status": {"$in": ["running", "committing"]}, "lease_until": {"$lt": now()}},
                {"$set": {"status": "interrupted", "active": False, "error": "Servidor interrompido; relance o estudo. Nenhuma nova chamada IA automática.", "updated_at": now().isoformat()}})
            job = await db.pc_study_jobs.find_one_and_update({"status": "queued", "cancel_requested": False},
                {"$set": {"status": "running", "worker": uuid.uuid4().hex, "lease_until": now()+timedelta(seconds=LEASE_SECONDS)}},
                sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
            if not job:
                await asyncio.sleep(2)
                continue
            task = asyncio.create_task(run_job(job))
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=5)
                    fresh = await db.pc_study_jobs.find_one({"job_id": job["job_id"], "worker": job["worker"]}, {"_id": 0})
                    if not fresh or fresh.get("cancel_requested") or fresh.get("status") not in ("running", "committing"):
                        task.cancel()
                    await db.pc_study_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": {"$in": ["running", "committing"]}},
                        {"$set": {"lease_until": now()+timedelta(seconds=LEASE_SECONDS)}})
                await task
                await finish(job, "completed")
            except asyncio.CancelledError:
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
                stopping = bool(asyncio.current_task().cancelling())
                await finish(job, "interrupted" if stopping else "cancelled")
                if stopping:
                    raise
            except Exception as exc:
                msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc) if isinstance(exc, StudyError) else "Estudo não concluído; as suas peças e o seu estudo anterior são conservados."
                log.warning("PC job failed: %s", type(exc).__name__)
                await finish(job, "failed", msg[:500])
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("PC worker unavailable: %s", type(exc).__name__)
            await asyncio.sleep(5)


async def start_workers():
    await db.pc_study_jobs.create_index("job_id", unique=True)
    await db.pc_study_jobs.create_index("active_key", unique=True, partialFilterExpression={"active": True})
    await db.pc_study_jobs.create_index([("user_id", 1), ("status", 1)])
    return [asyncio.create_task(worker())]
