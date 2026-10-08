"""Migração PT-PT dos planos em `db.plans` (Fase H — complemento).

Idempotente: faz upsert dos campos de texto (name, tagline,
description, features, badge) a partir de `DEFAULT_PLANS` para cada
plano existente em `db.plans`. Preserva campos operacionais (
`stripe_product_id`, `stripe_price_id`, `active`, etc).

Executar:
    python -m scripts.translate_plans_db
    # ou
    python scripts/translate_plans_db.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger("scripts.translate_plans_db")


# Campos de texto que devem ser sempre sobrescritos pelo catálogo PT-PT.
# Os restantes (stripe ids, lookup_key, amount_cents, quotas, sort_order,
# active, highlight) são preservados — a BD é source-of-truth operacional.
CAMPOS_TRADUZIVEIS = (
    "name", "tagline", "description", "features", "badge",
)


async def traduzir() -> None:
    from core.db import db  # noqa: WPS433
    from engines.monetization_catalog import DEFAULT_PLANS  # noqa: WPS433

    por_plan_id = {p["plan_id"]: p for p in DEFAULT_PLANS}
    actualizados = 0
    inseridos = 0
    inalterados = 0

    existentes = await db.plans.find({}, {"_id": 0}).to_list(500)
    ids_bd = {p["plan_id"] for p in existentes}

    # Actualiza existentes
    for existente in existentes:
        pid = existente.get("plan_id")
        novo = por_plan_id.get(pid)
        if not novo:
            logger.info("plano %s não está no catálogo PT-PT — ignorado", pid)
            continue
        patch = {k: novo[k] for k in CAMPOS_TRADUZIVEIS if k in novo}
        # Idempotência: só actualiza se algum campo mudou
        r = await db.plans.update_one(
            {"plan_id": pid, "$or": [
                {k: {"$ne": v}} for k, v in patch.items()
            ] or [{"plan_id": pid}]},
            {"$set": patch},
        )
        if r.modified_count > 0:
            actualizados += 1
        else:
            inalterados += 1

    # Insere planos que faltam na BD
    for novo in DEFAULT_PLANS:
        if novo["plan_id"] in ids_bd:
            continue
        await db.plans.update_one(
            {"plan_id": novo["plan_id"]},
            {"$setOnInsert": novo},
            upsert=True,
        )
        inseridos += 1

    total = await db.plans.count_documents({})
    logger.info(
        "Migração concluída — actualizados=%d, inseridos=%d, inalterados=%d, total=%d",
        actualizados, inseridos, inalterados, total,
    )


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv  # noqa: WPS433
        load_dotenv(_BACKEND_DIR / ".env")
    except ImportError:
        pass
    if not os.environ.get("MONGO_URL"):
        os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    if not os.environ.get("DB_NAME"):
        os.environ.setdefault("DB_NAME", "test_database")
    asyncio.run(traduzir())
