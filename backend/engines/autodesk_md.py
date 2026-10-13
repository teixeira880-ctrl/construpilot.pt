"""Autodesk Model Derivative: object tree + properties of a CAD/BIM file (DWG/RVT/IFC). Tenant-scoped, cached by file hash.

One translation per (user, file hash): translations consume Autodesk cloud credits and are never resubmitted while a job is pending/unknown.
"""
import asyncio
import base64
import hashlib
import secrets
from collections import Counter
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from core.db import db
from engines import autodesk_storage as storage
from engines.autodesk_client import AutodeskError, config, request

MD_BASE = "https://developer.api.autodesk.com/modelderivative/v2"
SUPPORTED = {"dwg": "AutoCAD (2D : calques, blocs, entités)", "dxf": "DXF", "rvt": "Revit (objets, familles, propriétés)", "ifc": "IFC (classes, propriétés)",
             "nwd": "Navisworks", "dgn": "MicroStation"}
MAX_PROPERTIES = 20000
POLL_SECONDS, POLL_MAX = 6, 40


def _now():
    return datetime.now(timezone.utc).isoformat()


def urn_for(object_id: str) -> str:
    return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")


async def _job(data: bytes, filename: str, user_id: str):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED:
        raise AutodeskError("unsupported_format", f"Format .{ext or '?'} non pris en charge par Model Derivative ici (formats : {', '.join(SUPPORTED)}).", fallback_safe=True)
    digest = hashlib.sha256(data).hexdigest()
    key = hashlib.sha256(f"{user_id}:model-derivative:{digest}".encode()).hexdigest()
    job = {"key": key, "job_id": "md_" + secrets.token_hex(10), "user_id": user_id, "filename": filename, "ext": ext, "input_sha256": digest,
           "status": "preparing", "created_at": _now(), "updated_at": _now()}
    try:
        await db.model_derivative_jobs.insert_one({"_id": key, **job})
        return job, True
    except DuplicateKeyError:
        existing = await db.model_derivative_jobs.find_one({"_id": key, "user_id": user_id}, {"_id": 0})
        if existing and existing["status"] in ("failed_before_submit", "rejected", "failed"):
            await db.model_derivative_jobs.update_one({"_id": key}, {"$set": job})
            return job, True
        return existing, False


async def _update(job, **values):
    values["updated_at"] = _now()
    job.update(values)
    await db.model_derivative_jobs.update_one({"_id": job["key"]}, {"$set": values})


async def _submit(job, data):
    object_key = f"md-{job['job_id']}-input.{job['ext']}"
    try:
        await storage.ensure_bucket()
        await storage.upload_input(object_key, data)
        details = (await request("GET", f"{storage.object_url(object_key)}/details")).json()
        urn = urn_for(details["objectId"])
        await _update(job, object_key=object_key, urn=urn, status="submitting")
    except Exception:  # noqa: BLE001
        await _update(job, status="failed_before_submit", error_code="preparation_failed")
        raise AutodeskError("preparation_failed", "Préparation Autodesk impossible. Aucune traduction n'a été lancée.", fallback_safe=True) from None
    try:
        response = await request("POST", f"{MD_BASE}/designdata/job", json={
            "input": {"urn": urn}, "output": {"formats": [{"type": "svf2", "views": ["2d", "3d"]}]}}, accepted=(201,))
        await _update(job, status="pending", provider_status=response.json().get("result"))
    except AutodeskError as exc:
        await _update(job, status="rejected" if exc.fallback_safe else "unknown", error_code=exc.code)
        raise
    except Exception:  # noqa: BLE001
        await _update(job, status="unknown", error_code="receipt_unavailable")
        raise AutodeskError("pending", "Réponse Autodesk perdue : la traduction n'est pas relancée.") from None


async def _wait_manifest(job):
    for _ in range(POLL_MAX):
        manifest = (await request("GET", f"{MD_BASE}/designdata/{job['urn']}/manifest", accepted=(202,))).json()
        status, progress = manifest.get("status"), manifest.get("progress")
        await _update(job, provider_status=status, progress=progress)
        if status == "success":
            return manifest
        if status in ("failed", "timeout"):
            messages = [m.get("message") for d in manifest.get("derivatives", []) for m in d.get("messages", []) if m.get("message")]
            await _update(job, status="failed", error_code="translation_failed", provider_messages=messages[:5])
            raise AutodeskError("translation_failed", "Autodesk n'a pas pu traduire ce fichier : " + "; ".join(str(m) for m in messages[:2]))
        await asyncio.sleep(POLL_SECONDS)
    raise AutodeskError("translation_pending", "Traduction Autodesk toujours en cours : relancez la lecture plus tard (aucune nouvelle traduction).")


async def _views(urn):
    return (await request("GET", f"{MD_BASE}/designdata/{urn}/metadata")).json().get("data", {}).get("metadata", [])


async def _properties(urn, guid):
    for _ in range(10):
        response = await request("GET", f"{MD_BASE}/designdata/{urn}/metadata/{guid}/properties", params={"forceget": "true"}, accepted=(202,))
        if response.status_code == 200:
            return response.json().get("data", {}).get("collection", [])
        await asyncio.sleep(4)
    return []


def summarize(collection: list[dict], ext: str) -> dict:
    """Counts objects per category/layer and lists property keys; never turns a translated line into a wall."""
    layers, categories, keys = Counter(), Counter(), Counter()
    for obj in collection[:MAX_PROPERTIES]:
        props = obj.get("properties") or {}
        for group, values in props.items():
            if not isinstance(values, dict):
                continue
            for k, v in values.items():
                keys[f"{group}/{k}"] += 1
                if k.lower() in ("layer", "calque"):
                    layers[str(v)] += 1
                if k.lower() in ("category", "catégorie", "ifc type", "type", "famille", "family"):
                    categories[str(v)] += 1
    kind_note = ("Un DWG traduit fournit des entités (lignes, polylignes, blocs, textes) par calque : ce ne sont pas des murs identifiés. "
                 "La classification constructive reste à faire (classify_strokes / lecture)." if ext in ("dwg", "dxf")
                 else "Objets natifs avec propriétés : les catégories/classes sont exploitables telles quelles, dans le périmètre demandé.")
    return {"objects": len(collection), "layers": layers.most_common(40), "categories": categories.most_common(40),
            "property_keys": [k for k, _ in keys.most_common(60)], "note": kind_note}


async def extract(data: bytes, filename: str, *, user_id: str) -> dict:
    """Full path: upload → translation → manifest → views → properties, cached per (user, hash)."""
    config("APS_CLIENT_ID")
    job, fresh = await _job(data, filename, user_id)
    if not fresh and job.get("status") == "success":
        return {**job, "cached": True}
    if not fresh and job.get("status") in ("pending", "submitting", "unknown", "preparing"):
        if job.get("urn") and job["status"] == "pending":
            return await _complete(job)
        raise AutodeskError("pending", "Une traduction de ce fichier est déjà en cours ou incertaine : aucune nouvelle traduction n'est lancée.")
    await _submit(job, data)
    return await _complete(job)


async def _complete(job):
    manifest = await _wait_manifest(job)
    views = [{"guid": v.get("guid"), "name": v.get("name"), "role": v.get("role")} for v in await _views(job["urn"])]
    summaries, sample = [], []
    for view in views[:6]:
        collection = await _properties(job["urn"], view["guid"])
        summaries.append({**view, **summarize(collection, job["ext"])})
        if collection and not sample:
            sample = [{"objectid": o.get("objectid"), "name": o.get("name"), "properties": o.get("properties")} for o in collection[:15]]
    result = {"status": "success", "views": summaries, "sample_objects": sample, "manifest_status": manifest.get("status"),
              "derivatives": [{"name": d.get("name"), "outputType": d.get("outputType"), "status": d.get("status")} for d in manifest.get("derivatives", [])],
              "completed_at": _now(), "format_note": SUPPORTED.get(job["ext"])}
    await _update(job, **result)
    return {**job, "cached": False}
