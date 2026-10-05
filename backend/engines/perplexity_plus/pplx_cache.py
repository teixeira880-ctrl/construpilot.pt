"""Cache MongoDB TTL 24h para Perplexity Plus."""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from core.db import db

logger = logging.getLogger("pplx_plus.cache")

TTL_SECONDS = 24 * 3600  # 24h


def cache_key(*parts: Any) -> str:
    """SHA256 do payload normalizado."""
    norm = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(norm.encode()).hexdigest()


async def ensure_index() -> None:
    """Garante índice TTL. Idempotente."""
    try:
        await db.pplx_cache.create_index("created_at", expireAfterSeconds=TTL_SECONDS)
    except Exception as e:  # noqa: BLE001
        logger.info("ensure_index pplx_cache: %s", type(e).__name__)


async def cache_get(key: str) -> dict | None:
    doc = await db.pplx_cache.find_one({"_id": key}, {"_id": 0, "payload": 1, "created_at": 1})
    if not doc:
        return None
    return doc.get("payload")


async def cache_set(key: str, payload: dict) -> None:
    doc = {
        "_id": key,
        "payload": payload,
        "created_at": datetime.now(timezone.utc),
    }
    try:
        await db.pplx_cache.replace_one({"_id": key}, doc, upsert=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("cache_set falhou: %s", type(e).__name__)
