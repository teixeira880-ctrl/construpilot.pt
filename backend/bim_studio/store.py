"""Acesso à base de dados do BIM Studio, isolamento por organização e auditoria.

Coleções (todas novas, prefixo ``bim_``): bim_models, bim_versions, bim_elements,
bim_overrides, bim_mappings, bim_audit, bim_prefs, bim_quote_traces, bim_finishes.
"""
from __future__ import annotations

from datetime import datetime, timezone

_DB = None


def set_db(db) -> None:
    """Substitui a base de dados (testes)."""
    global _DB
    _DB = db


def get_db():
    if _DB is not None:
        return _DB
    from core.db import db
    return db


def tenant_of(user: dict) -> str:
    """Organização (empresa) do utilizador; profissionais a solo formam o seu próprio tenant."""
    org = user.get("organization_id")
    if org:
        return f"org_{org}"
    return f"usr_{user['user_id']}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def audit(user: dict, action: str, model_id: str | None = None, version: int | None = None,
                **details) -> None:
    try:
        await get_db().bim_audit.insert_one({
            "tenant_id": tenant_of(user), "user_id": user.get("user_id"), "action": action,
            "model_id": model_id, "version": version, "details": details, "at": now(),
        })
    except Exception:  # noqa: BLE001 — a auditoria nunca deve partir o pedido
        pass


async def ensure_indexes() -> None:
    db = get_db()
    await db.bim_models.create_index([("tenant_id", 1), ("model_id", 1)], unique=True)
    await db.bim_versions.create_index([("model_id", 1), ("version", 1)], unique=True)
    await db.bim_versions.create_index([("status", 1), ("created_at", 1)])
    await db.bim_elements.create_index([("model_id", 1), ("version", 1), ("gid", 1)], unique=True)
    await db.bim_elements.create_index([("model_id", 1), ("version", 1), ("category", 1), ("storey_gid", 1)])
    await db.bim_overrides.create_index([("model_id", 1), ("version", 1), ("gid", 1), ("key", 1)], unique=True)
    await db.bim_mappings.create_index([("model_id", 1), ("version", 1), ("group_key", 1)], unique=True)
    await db.bim_finishes.create_index([("model_id", 1), ("version", 1), ("gid", 1)], unique=True)
    await db.bim_audit.create_index([("tenant_id", 1), ("at", -1)])
