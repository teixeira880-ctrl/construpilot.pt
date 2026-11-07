"""Configuração do BIM Studio (exclusivo ConstruPilot Portugal).

Todas as variáveis têm prefixo ``BIM_`` e só existem no ambiente PT.
O módulo fica DESLIGADO se o mercado do código não for Portugal (proteção
contra uma fusão acidental no repositório francês).
"""
from __future__ import annotations

import os

from core.market import SITE_COUNTRY


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def ifcopenshell_available() -> bool:
    import importlib.util
    return importlib.util.find_spec("ifcopenshell") is not None


def enabled() -> bool:
    """Interruptor geral. Rollback instantâneo: BIM_STUDIO_ENABLED=0."""
    if SITE_COUNTRY != "PT":
        return False
    if not ifcopenshell_available():
        return False
    raw = os.environ.get("BIM_STUDIO_ENABLED")
    if raw is None:
        # Por defeito: ligado em preview/dev, DESLIGADO em produção até aprovação explícita.
        from core.environment import is_relaxed
        return is_relaxed()
    return raw.strip().lower() in ("1", "true", "yes", "on")


MAX_UPLOAD_MB = _int("BIM_MAX_UPLOAD_MB", 200)
MAX_CONCURRENT_JOBS = max(1, _int("BIM_MAX_CONCURRENT_JOBS", 1))
JOB_TIMEOUT_S = _int("BIM_JOB_TIMEOUT_S", 900)
WORKER_MEMORY_MB = _int("BIM_WORKER_MEMORY_MB", 3072)
WORKER_CPU_S = _int("BIM_WORKER_CPU_S", 900)
WORKER_OUTPUT_MB = _int("BIM_WORKER_OUTPUT_MB", 1024)
WORKER_THREADS = max(1, _int("BIM_WORKER_THREADS", 1))
MAX_ELEMENTS = _int("BIM_MAX_ELEMENTS", 60000)
MAX_TRIANGLES = _int("BIM_MAX_TRIANGLES", 4_000_000)
MAX_MODELS_PER_TENANT = _int("BIM_MAX_MODELS_PER_TENANT", 200)
SIGNED_URL_TTL_S = _int("BIM_SIGNED_URL_TTL_S", 600)
# "emergent" (Object Storage privado) ou "local" (dev/testes)
STORAGE_BACKEND = os.environ.get("BIM_STORAGE", "emergent").strip().lower()
LOCAL_STORAGE_DIR = os.environ.get("BIM_LOCAL_STORAGE_DIR", "/tmp/construpilot_bim_storage")
WORK_DIR = os.environ.get("BIM_WORK_DIR", "/tmp/construpilot_bim_work")
# Prefixo de armazenamento exclusivo PT (nunca partilha caminhos com a França)
STORAGE_PREFIX = "pt/bim"


def url_secret() -> str:
    s = os.environ.get("BIM_URL_SECRET") or os.environ.get("JWT_SECRET") or ""
    if not s:
        from core.environment import is_relaxed
        if is_relaxed():
            return "dev-only-bim-secret"
        raise RuntimeError("BIM_URL_SECRET/JWT_SECRET em falta")
    return s
