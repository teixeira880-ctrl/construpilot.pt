"""Flag de ativação da venda do processo de autorização de obras (Lote N4).

Guardado em `app_settings` com chave «autorizacao_obras».
Por defeito a venda está DESATIVADA (sale_enabled=False); apenas um administrador pode ativar.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from core.db import db

KEY = "autorizacao_obras"

DEFAULT: Dict[str, Any] = {
    "sale_enabled": False,
    "price_eur": 39,
    "currency": "eur",
    "included_in_pro": True,
    "included_in_business": True,
    "stripe_product_name": "Processo de autorização de obras (ConstruPilot)",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_settings() -> Dict[str, Any]:
    doc = await db.app_settings.find_one({"key": KEY})
    value = (doc or {}).get("value") or {}
    return {**DEFAULT, **value}


async def set_settings(patch: Dict[str, Any], admin_user_id: str = "admin") -> Dict[str, Any]:
    cur = await get_settings()
    allowed = ("sale_enabled", "price_eur", "currency", "included_in_pro",
               "included_in_business", "stripe_product_name")
    nxt = dict(cur)
    for k in allowed:
        if k in patch:
            nxt[k] = patch[k]
    # Validação simples
    if isinstance(nxt.get("price_eur"), (int, float)) and nxt["price_eur"] < 0:
        nxt["price_eur"] = DEFAULT["price_eur"]
    await db.app_settings.update_one(
        {"key": KEY},
        {"$set": {"key": KEY, "value": nxt, "updated_by": admin_user_id, "updated_at": _now()}},
        upsert=True,
    )
    return nxt
