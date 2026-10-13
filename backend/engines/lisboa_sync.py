"""Sincronização dos alvarás de Lisboa (ArcGIS CML) para a coleção
`radar_permits`. Reutiliza o mesmo contrato de `sitadel_sync`
(mesmas chaves em `radar_sync`, mesmos campos em `radar_permits`).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from core.db import db
from engines.lisboa_permits import (
    ARCGIS_FEATURE_URL,
    DATASET_PORTAL_URL,
    SOURCE_NAME,
    official_permit,
    window_start,
)
from engines.radar_filters import FILTER_SCHEMA_VERSION
from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError, PyMongoError

log = logging.getLogger(__name__)
TASKS: set[asyncio.Task] = set()
ACTIVE_ZONES: set[str] = set()
LIMIT = asyncio.Semaphore(2)
INITIAL_ZONES = ["lisboa"]
HTTP_UA = (
    "Mozilla/5.0 (ConstruPilot RadarPT; +https://construpilot.pt) "
    "AppleWebKit/537.36 Chrome/121.0 Safari/537.36"
)


def now() -> datetime:
    return datetime.now(timezone.utc)


async def _fetch_features(window_iso: str) -> list[dict]:
    """Chama o FeatureServer da CML em páginas de 2000, filtra por janela."""
    url = f"{ARCGIS_FEATURE_URL}/query"
    page = 2000
    offset = 0
    out: list[dict] = []
    where = f"DATA_ALVARA >= '{window_iso}'"
    params = {
        "where": where,
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": page,
        "orderByFields": "DATA_ALVARA DESC",
    }
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": HTTP_UA}) as client:
        while True:
            params["resultOffset"] = offset
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
            feats = payload.get("features") or []
            out.extend(feats)
            if len(feats) < page or not payload.get("properties", {}).get("exceededTransferLimit"):
                break
            offset += page
            if offset > 60000:  # salvaguarda — Lisboa tem ~30k alvarás históricos
                break
    return out


async def sync_zone(zone: str, lease_id: str) -> None:
    run_id = secrets.token_hex(12)
    published = False
    try:
        async with LIMIT:
            await db.radar_sync.update_one(
                {"_id": zone, "lease_id": lease_id},
                {"$set": {"stage": "Ligação à CML (ArcGIS)",
                          "lease_until": (now() + timedelta(minutes=15)).isoformat()}},
            )
            window_iso = window_start()
            features = await _fetch_features(window_iso)
            permits: dict[str, dict] = {}
            received = len(features)
            skipped = 0
            for feat in features:
                permit = official_permit(feat)
                if permit is None:
                    skipped += 1
                    continue
                permits[permit["id"]] = permit
            docs = [{**p, "ingest_run": run_id} for p in permits.values()]
            if docs:
                await db.radar_permits.bulk_write(
                    [UpdateOne({"_id": f'{run_id}:{p["id"]}'}, {"$set": p}, upsert=True) for p in docs],
                    ordered=False,
                )
            completed = now().isoformat()
            sources = [{"kind": "cml_official", "dataset_id": "5ae9c60dc8d8c9146a44cc30",
                        "millesime": datetime.now(timezone.utc).strftime("%Y-%m"),
                        "published_at": completed, "coverage_end": window_iso}]
            result = await db.radar_sync.update_one(
                {"_id": zone, "lease_id": lease_id},
                {"$set": {
                    "status": "ready", "active_run": run_id, "count": len(docs),
                    "sources": sources, "last_success_at": completed,
                    "last_checked_at": completed, "window_start": window_iso,
                    "received": received, "skipped": skipped,
                    "unlocated": sum(p.get("lat") is None for p in docs),
                    "filter_schema_version": FILTER_SCHEMA_VERSION,
                    "error": None, "stage": "Terminado",
                }, "$unset": {"lease_until": ""}},
            )
            if result.modified_count:
                published = True
                try:
                    await db.radar_permits.delete_many(
                        {"dep": zone, "source.kind": "cml_official",
                         "ingest_run": {"$ne": run_id}},
                    )
                except PyMongoError:
                    log.warning("Limpeza do snapshot anterior adiada para %s", zone)
            else:
                await db.radar_permits.delete_many({"ingest_run": run_id})
    except Exception as exc:
        message = f"Fonte oficial CML indisponível ({exc.__class__.__name__}). Os últimos dados válidos são conservados."
        log.exception("Sync CML falhou para a zona %s", zone)
        if not published:
            await db.radar_permits.delete_many({"ingest_run": run_id})
        await db.radar_sync.update_one(
            {"_id": zone, "lease_id": lease_id},
            {"$set": {"status": "error", "error": message,
                      "last_checked_at": now().isoformat()},
             "$unset": {"lease_until": ""}},
        )
    finally:
        ACTIVE_ZONES.discard(zone)


async def ensure_sync(zones: list[str], force: bool = False) -> None:
    for zone in zones:
        if zone != "lisboa":
            # Fase 1: apenas Lisboa é suportada; outras zonas serão adicionadas no futuro.
            continue
        if zone in ACTIVE_ZONES:
            continue
        existing = await db.radar_sync.find_one({"_id": zone}, {"_id": 0})
        current = now()
        if existing:
            if existing.get("status") == "running" and existing.get("lease_until", "") > current.isoformat():
                continue
            categories_outdated = existing.get("filter_schema_version") != FILTER_SCHEMA_VERSION
            minutes = 1 if force or categories_outdated or existing.get("status") == "error" else 24 * 60
            if existing.get("status") != "running" and existing.get("last_checked_at", "") > (current - timedelta(minutes=minutes)).isoformat():
                continue
        lease_id = secrets.token_hex(10)
        try:
            lease = await db.radar_sync.find_one_and_update(
                {"_id": zone, "$or": [{"status": {"$ne": "running"}},
                                       {"lease_until": {"$lte": current.isoformat()}}]},
                {"$set": {"department": zone, "status": "running", "lease_id": lease_id,
                          "lease_until": (current + timedelta(minutes=15)).isoformat(),
                          "stage": "Ligação à fonte oficial", "error": None}},
                upsert=True, return_document=ReturnDocument.AFTER, projection={"_id": 0},
            )
        except DuplicateKeyError:
            continue
        if lease:
            ACTIVE_ZONES.add(zone)
            task = asyncio.create_task(sync_zone(zone, lease_id))
            TASKS.add(task)
            task.add_done_callback(TASKS.discard)


async def sync_status(zones: list[str]) -> dict:
    records = await db.radar_sync.find(
        {"department": {"$in": zones}},
        {"_id": 0, "lease_id": 0, "lease_until": 0, "active_run": 0},
    ).to_list(None)
    indexed = {r["department"]: r for r in records}
    return {
        "departments": [indexed.get(z, {"department": z, "status": "not_loaded", "count": 0}) for z in zones],
        "source_name": SOURCE_NAME,
        "source_url": os.environ.get("RADAR_CML_PORTAL_URL") or DATASET_PORTAL_URL,
        "window_start": window_start(),
        "window_end": datetime.now(timezone.utc).date().isoformat(),
    }
