"""Durable, tenant-scoped DWG conversions. Unknown POSTs are never resubmitted."""
import asyncio
import hashlib
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from core.db import db
from engines import autodesk_storage as storage
from engines.autodesk_client import MAX_BYTES, AutodeskError, api_base, config, request
from engines.autodesk_validation import inspect_dxf
from engines.plan_sources import delete_plan_sources, load_cad_source, save_cad_source
from engines.expenses.context import actor

TERMINAL_FAILURES = {"cancelled", "failedLimitDataSize", "failedLimitProcessingTime", "failedDownload", "failedInstructions", "failedUpload", "failed"}


class ConversionProvenance(BaseModel):
    provider: str = "autodesk"
    status: str = "verified"
    job_id: str
    engine: str
    activity: str
    format_version: str
    units_code: int
    input_sha256: str
    output_sha256: str
    output_size_bytes: int
    entity_count: int
    layer_count: int
    cached: bool = False


def now():
    return datetime.now(timezone.utc)


def pending_error():
    return AutodeskError("conversion_pending", "Conversão Autodesk em curso ou a verificar. Volte a importar o mesmo ficheiro para consultar o resultado, sem lançar uma segunda tarefa.")


async def update(job, **values):
    query = {"_id": job["key"], "attempt_id": job["attempt_id"]}
    if values.get("status") and values["status"] != "success":
        query["status"] = {"$ne": "success"}
    result = await db.cad_conversion_jobs.update_one(query, {"$set": {**values, "updated_at": now()}})
    if not result.matched_count:
        current = await db.cad_conversion_jobs.find_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"_id": 0})
        if current:
            job.update(current)
        return
    job.update(values)


async def claim(data, user_id):
    digest = hashlib.sha256(data).hexdigest()
    key = hashlib.sha256(f"{user_id}:dwg-to-dxf:{digest}".encode()).hexdigest()
    job = {"key": key, "job_id": "aps_" + secrets.token_hex(12), "attempt_id": secrets.token_hex(12),
           "user_id": user_id, "company_id": actor().get("company_id"), "input_sha256": digest, "status": "preparing", "created_at": now(), "updated_at": now(),
           "engine": config("APS_ENGINE"), "activity": config("APS_ACTIVITY_ID")}
    try:
        await db.cad_conversion_jobs.insert_one({"_id": key, **job})
        return job, True
    except DuplicateKeyError:
        existing = await db.cad_conversion_jobs.find_one({"_id": key, "user_id": user_id}, {"_id": 0})
        if not existing:
            raise pending_error()
        # Only preparations which definitely did NOT submit, or expired successes,
        # can be replaced by a new explicit import. Never retry an uncertain POST.
        expired = existing.get("status") == "success" and existing.get("cache_expires_at") and existing["cache_expires_at"].replace(tzinfo=timezone.utc) < now()
        if existing["status"] in {"failed_before_submit", "rejected"} or expired:
            changed = await db.cad_conversion_jobs.update_one({"_id": key, "attempt_id": existing["attempt_id"], "status": existing["status"]},
                {"$set": job, "$unset": {"workitem_id": "", "cache_id": "", "provenance": "", "provider_status": "", "output_upload_key": ""}})
            if changed.modified_count:
                if existing.get("cache_id"):
                    await delete_plan_sources(db, existing["cache_id"], user_id)
                return job, True
        return existing, False


async def prepare_and_submit(job, data):
    prefix = f"jobs/{job['job_id']}"
    await update(job, input_key=f"{prefix}/input.dwg", output_key=f"{prefix}/result.dxf")
    try:
        input_url = await storage.upload_input(job["input_key"], data)
        output = await storage.signed_upload(job["output_key"])
        await update(job, output_upload_key=output["uploadKey"], status="submitting")
    except Exception:  # noqa: BLE001 - every preparation failure is definitively pre-submit.
        await update(job, status="failed_before_submit", error_code="preparation_failed")
        cleaned = await storage.delete_objects(job.get("input_key"), job.get("output_key"))
        await update(job, cleanup_pending=not cleaned)
        raise AutodeskError("preparation_failed", "Preparação Autodesk impossível. Nenhum trabalho AutoCAD foi lançado.", fallback_safe=True) from None
    try:
        response = await request("POST", f"{api_base()}/workitems", json={
            "activityId": config("APS_ACTIVITY_QUALIFIED"),
            "arguments": {"inputFile": {"url": input_url, "verb": "get"},
                          "outputFile": {"url": output["urls"][0], "verb": "put", "localName": "result.dxf"}}})
        result = response.json()
        if not isinstance(result.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", result["id"]):
            raise pending_error()
        await update(job, workitem_id=result["id"], status="pending", provider_status=result.get("status", "pending"))
    except AutodeskError as exc:
        safe = exc.fallback_safe
        await update(job, status="rejected" if safe else "unknown", error_code=exc.code)
        if safe:
            await storage.delete_objects(job.get("input_key"), job.get("output_key"))
        if not safe:
            raise pending_error() from None
        raise
    except Exception:  # noqa: BLE001 - any lost receipt must block duplicate billable work.
        # Lost JSON/DB acknowledgement could hide an accepted, billable task.
        await update(job, status="unknown", error_code="receipt_unavailable")
        raise pending_error() from None


async def poll(job):
    deadline = time.monotonic() + min(300, max(15, int(config("APS_DWG_TIMEOUT_SECONDS"))))
    while time.monotonic() < deadline:
        current = await db.cad_conversion_jobs.find_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"_id": 0})
        if current and current["status"] == "success":
            job.update(current)
            return
        try:
            result = (await request("GET", f"{api_base()}/workitems/{quote(job['workitem_id'], safe='')}")).json()
            status = result.get("status")
            await update(job, provider_status=status)
        except Exception:  # noqa: BLE001 - unreadable status is never treated as permission to retry.
            await update(job, status="unknown", error_code="status_unavailable")
            if job["status"] == "success":
                return
            raise pending_error() from None
        if status == "success":
            await db.cad_conversion_jobs.update_one({"_id": job["key"], "attempt_id": job["attempt_id"], "status": {"$ne": "success"}},
                {"$set": {"status": "finishing", "updated_at": now()}})
            return
        if status in TERMINAL_FAILURES:
            await update(job, status="failed", error_code=status)
            if job["status"] == "success":
                return
            cleaned = await storage.delete_objects(job.get("input_key"), job.get("output_key"))
            await update(job, cleanup_pending=not cleaned)
            raise AutodeskError("terminal_failure", "O AutoCAD não conseguiu exportar este DWG. Nenhum segundo trabalho Autodesk foi lançado.", fallback_safe=True)
        if status not in {"pending", "inprogress"}:
            await update(job, status="unknown", error_code="unknown_status")
            raise pending_error()
        await asyncio.sleep(2)
    await update(job, status="unknown", error_code="poll_deadline")
    if job["status"] == "success":
        return
    # No cancellation race or fallback: a later import polls the SAME WorkItem.
    raise pending_error()


async def finish(job):
    # Multiple requests may poll, but only one may publish/cache the DXF.
    lease_token = secrets.token_hex(12)
    lock = await db.cad_conversion_jobs.update_one({"_id": job["key"], "attempt_id": job["attempt_id"], "status": {"$ne": "success"},
        "$or": [{"finish_lease_until": {"$exists": False}}, {"finish_lease_until": {"$lt": now()}}]},
        {"$set": {"finish_lease_until": now() + timedelta(minutes=5), "finish_lease_token": lease_token}})
    if not lock.modified_count:
        current = await db.cad_conversion_jobs.find_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"_id": 0})
        if current and current["status"] == "success":
            return await cached_result(current)
        raise pending_error()
    cache_id = f"aps-cache-{job['job_id']}-{lease_token}"
    try:
        output = await storage.read_output(job["output_key"], job["output_upload_key"])
        inspected = await asyncio.to_thread(inspect_dxf, output)
        metadata = ConversionProvenance(job_id=job["job_id"], engine=job["engine"], activity=job["activity"],
            input_sha256=job["input_sha256"], **{k: v for k, v in inspected.items() if k in ConversionProvenance.model_fields}).model_dump()
        await save_cad_source(db, cache_id, job["user_id"], "converted_dxf", output)
        expires = now() + timedelta(hours=24)
        await db.plan_cad_sources.update_many({"plan_id": cache_id, "user_id": job["user_id"]}, {"$set": {"expires_at": expires}})
        publication = {"status": "success", "cache_id": cache_id, "cache_expires_at": expires,
                       "provenance": metadata, "updated_at": now(), "cleanup_pending": True}
        published = await db.cad_conversion_jobs.update_one({"_id": job["key"], "attempt_id": job["attempt_id"],
            "finish_lease_token": lease_token, "status": {"$ne": "success"}}, {"$set": publication})
        if not published.modified_count:
            # A newer finisher owns the lease. Its private cache must not be touched.
            current = await db.cad_conversion_jobs.find_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"_id": 0})
            if not current or current.get("cache_id") != cache_id:
                await delete_plan_sources(db, cache_id, job["user_id"])
            if current and current["status"] == "success":
                return await cached_result(current)
            raise pending_error()
        job.update(publication)
        cleaned = await storage.delete_objects(job["input_key"], job["output_key"])
        await update(job, cleanup_pending=not cleaned)
        await db.cad_conversion_jobs.update_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"$unset": {"output_upload_key": ""}})
        return output, metadata
    except AutodeskError as exc:
        if exc.code in {"invalid_dxf", "output_too_large"}:
            await update(job, status="failed", error_code=exc.code)
            await storage.delete_objects(job.get("input_key"), job.get("output_key"))
        raise
    finally:
        await db.cad_conversion_jobs.update_one({"_id": job["key"], "attempt_id": job["attempt_id"], "finish_lease_token": lease_token},
            {"$unset": {"finish_lease_until": "", "finish_lease_token": ""}})


async def cached_result(job):
    cached = await load_cad_source(db, job["cache_id"], job["user_id"], "converted_dxf")
    if cached:
        return cached, {**job["provenance"], "cached": True}
    raise AutodeskError("cache_unavailable", "Resultado Autodesk temporariamente indisponível. Nenhuma nova tarefa foi faturada.")


async def convert(data, *, user_id):
    if not user_id or not isinstance(user_id, str):
        raise AutodeskError("missing_owner", "Conta necessária para a conversão Autodesk.")
    if not data or len(data) > MAX_BYTES or not re.match(rb"AC10[0-9]{2}", data[:6]):
        raise AutodeskError("invalid_input", "Ficheiro DWG vazio, demasiado volumoso ou inválido.")
    config("APS_ACTIVITY_QUALIFIED")
    job, created = await claim(data, user_id)
    if not created and job["status"] == "success":
        return await cached_result(job)
    if not created and job["status"] == "failed":
        raise AutodeskError("terminal_failure", "Este DWG já falhou no AutoCAD. Verifique o desenho antes de uma nova tentativa.", fallback_safe=True)
    if created:
        await prepare_and_submit(job, data)
    if not job.get("workitem_id"):
        raise pending_error()
    await poll(job)
    current = await db.cad_conversion_jobs.find_one({"_id": job["key"], "attempt_id": job["attempt_id"]}, {"_id": 0})
    if current and current["status"] == "success":
        return await cached_result(current)
    return await finish(job)