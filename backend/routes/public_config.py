"""Endpoint público `/api/config` — expõe sinalizadores de funcionalidades
controlados por variáveis de ambiente (nenhum segredo é devolvido).
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["config"])


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def radar_enabled() -> bool:
    return _flag("RADAR_ENABLED", True)


def postal_enabled() -> bool:
    return _flag("POSTAL_ENABLED", False)


@router.get("/config")
async def get_public_config() -> dict:
    """Devolve apenas sinalizadores públicos — sem credenciais nem endpoints internos."""
    return {
        "radar_enabled": radar_enabled(),
        "postal_enabled": postal_enabled(),
        "country": os.environ.get("APP_COUNTRY", "PT"),
    }
