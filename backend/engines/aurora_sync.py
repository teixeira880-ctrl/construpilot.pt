"""Sincronização automática ConstruPilot → Aurora Company API V1.

Fail-safe: se Aurora não estiver configurado ou o pedido falhar, o utilizador
NUNCA vê erro — apenas se regista um warning silencioso e a operação principal
prossegue. Aurora nunca deve bloquear o fluxo core do ConstruPilot.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from engines.aurora_client import (
    AuroraCompanyClient,
    AuroraConfig,
    AuroraKeyIdInvalid,
    AuroraNotConfigured,
)

logger = logging.getLogger("aurora.sync")


# --------------------------------------------------------------------------
# Mapeamento ConstruPilot → schema Aurora company-project-upsert.v1
# --------------------------------------------------------------------------
def _iso(v: Any) -> str | None:
    if not v:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


_STATUS_MAP = {
    "draft": "planning",
    "planning": "planning",
    "planned": "planning",
    "active": "active",
    "in_progress": "active",
    "ongoing": "active",
    "on_hold": "on_hold",
    "paused": "on_hold",
    "completed": "completed",
    "finished": "completed",
    "closed": "completed",
    "archived": "archived",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def _map_status(raw: Any) -> str:
    if not raw:
        return "active"
    return _STATUS_MAP.get(str(raw).lower().strip(), "active")


def _progress_percent(doc: dict[str, Any]) -> int:
    """Compute % done a partir do dict `progress` do ConstruPilot.
    Formato: {"lot_key": "todo"|"in_progress"|"done"}.
    """
    # Se o próprio doc já traz progress_percent numérico, respeita.
    for key in ("progress_percent", "progress_pct"):
        if key in doc and isinstance(doc[key], (int, float)):
            return int(max(0, min(100, doc[key])))
    prog = doc.get("progress")
    if isinstance(prog, dict) and prog:
        done = sum(1 for v in prog.values() if str(v).lower() == "done")
        total = len(prog)
        if total > 0:
            return int(round(done * 100 / total))
    return 0


def _location(doc: dict[str, Any]) -> dict[str, Any] | None:
    city = doc.get("city")
    region = doc.get("region")
    country = doc.get("country")
    postal = doc.get("postal_code")
    if not (city or region or country or postal):
        return None
    return {
        "city": city, "region": region,
        "country": country, "postal_code": postal,
    }


def _project_to_aurora_payload(doc: dict[str, Any]) -> dict[str, Any]:
    """Mapeia doc `db.projects` (ConstruPilot) → payload Aurora upsert.

    Nota: `location` e `financials` do schema Aurora têm formatos ainda por
    documentar (todos os experimentos devolveram 422). Enquanto o schema não
    for confirmado, esses dados vão dentro de `extensions.location_raw` /
    `extensions.financials_raw` para não bloquear a sincronização.
    """
    est = doc.get("estimation") or {}
    budget = doc.get("budget") or est.get("total_avg")
    loc = _location(doc)
    financials_raw = None
    if budget:
        financials_raw = {"budget_amount": float(budget), "currency": "EUR"}
    return {
        "project_id": str(doc.get("project_id") or doc.get("_id") or doc.get("id")),
        "name": doc.get("name") or "Sem nome",
        "status": _map_status(doc.get("status")),
        "progress_percent": _progress_percent(doc),
        "project_type": doc.get("project_type"),
        "area_m2": (float(doc["surface"]) if doc.get("surface") is not None else None),
        "planned_start": _iso(doc.get("planned_start") or doc.get("start_date")),
        "planned_end": _iso(doc.get("planned_end") or doc.get("end_date")),
        "source_updated_at": _iso(doc.get("updated_at") or doc.get("created_at")),
        "extensions": {
            "building_type": doc.get("building_type"),
            "condition": doc.get("condition"),
            "construction_year": doc.get("construction_year"),
            "finish_level": doc.get("finish_level"),
            "lots": doc.get("lots"),
            "construpilot_user_id": doc.get("user_id"),
            "location_raw": loc,
            "financials_raw": financials_raw,
        },
    }


# --------------------------------------------------------------------------
# Public API — sync assíncrona (usar em rotas via fire_and_forget)
# --------------------------------------------------------------------------
async def sync_project_to_aurora(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Executa POST /projects/upsert. Devolve dict com o entity_id ou `None`.

    Fail-safe: em caso de erro ou config em falta, apenas escreve warning e
    devolve `None`. Nunca propaga exceção.
    """
    try:
        if not AuroraConfig().configured:
            return None
        payload = _project_to_aurora_payload(doc)
        client = AuroraCompanyClient()
        r = await client.upsert_project(payload)
        if r.status_code >= 400:
            logger.warning(
                "aurora upsert failed status=%s pid=%s",
                r.status_code, payload.get("project_id"),
            )
            return None
        try:
            body = r.json()
        except Exception:  # noqa: BLE001
            body = {}
        proj = body.get("project") or {}
        return {
            "aurora_entity_id": proj.get("aurora_entity_id"),
            "version": proj.get("version"),
            "status": r.status_code,
        }
    except (AuroraNotConfigured, AuroraKeyIdInvalid):
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("aurora sync silenced error: %s", type(e).__name__)
        return None


def sync_project_fire_and_forget(doc: dict[str, Any]) -> None:
    """Agenda a sync sem bloquear a rota principal.

    Chamar imediatamente após um insert/update bem sucedido em `db.projects`.
    Não `await`ar — a corrotina corre em segundo plano.
    """
    if not AuroraConfig().configured:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(sync_project_to_aurora(doc))
    except RuntimeError:
        # Sem event loop — fallback silencioso (ex.: chamado de um sync script)
        try:
            asyncio.run(sync_project_to_aurora(doc))
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        logger.warning("aurora schedule error: %s", type(e).__name__)
