"""Rotas admin para o BET-PT Agent (L1.8).

Endpoints:
    - POST  /api/admin/bet-agent/run       → corre pipeline sobre PDFs (admin only).
    - GET   /api/admin/bet-agent/costs     → sumário de custos acumulados.
    - GET   /api/admin/bet-agent/runs      → lista dos últimos N dossiers executados.
    - GET   /api/admin/bet-agent/runs/{id} → detalhe de 1 dossier.
    - GET   /api/admin/bet-agent/status    → feature flag + env readiness.

Regras:
    - `admin_user` dependency obrigatória (role=admin). Demo users bloqueados
      pelo `demo_guards.ensure_not_demo` adicional.
    - Nenhuma chamada live ao Claude é feita sem a feature flag
      `BET_AGENT_ENABLED=true` + `ANTHROPIC_API_KEY` presente.
    - Persistência mínima em Mongo: colecção `bet_agent_runs` com snapshot do
      Summary + custo. ObjectIds nunca expostos directamente — sempre `run_id`
      UUID.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

from core.db import db
from core.demo_guards import ensure_not_demo
from core.security import admin_user

from engines.bet_agent import is_enabled as bet_agent_enabled
from engines.bet_agent.agent.client import (
    AnthropicClient,
    AnthropicNotConfigured,
    is_anthropic_available,
)
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.pipeline import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/bet-agent", tags=["admin-bet-agent"])


COLLECTION_RUNS = "bet_agent_runs"


# ---------------------------------------------------------------------------
# Helpers de serialização
# ---------------------------------------------------------------------------

def _summary_to_dict(summary) -> dict[str, Any]:
    """Converte Summary em dict JSON-serializável (sem Pydantic enum raws)."""
    data = summary.model_dump(mode="json")
    # `set` → `list` (model_dump já faz isso em modo json, mas confirmamos)
    data["requested_deliverables"] = list(data.get("requested_deliverables", []))
    data["produced_deliverables"] = list(data.get("produced_deliverables", []))
    data["out_of_scope"] = list(data.get("out_of_scope", []))
    return data


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/status")
async def bet_agent_status(user=Depends(admin_user)) -> dict[str, Any]:
    """Estado operacional (sem valores de segredos). Útil para o painel admin."""
    ensure_not_demo(user, action="admin_read")
    return {
        "feature_flag": bet_agent_enabled(),
        "anthropic_key_present": is_anthropic_available(),
        "reader_model_default": os.environ.get(
            "BET_AGENT_READER_MODEL", "claude-opus-5-5"
        ),
        "verifier_model_default": os.environ.get(
            "BET_AGENT_VERIFIER_MODEL", "claude-opus-5-5"
        ),
        "cost_limit_eur": float(os.environ.get("BET_AGENT_COST_LIMIT_EUR", "10.0")),
    }


# ---------------------------------------------------------------------------
# Run pipeline
# ---------------------------------------------------------------------------

@router.post("/run")
async def bet_agent_run(
    arquitectura: UploadFile = File(..., description="PDF de arquitectura"),
    geotecnico: UploadFile | None = File(None, description="PDF do estudo geotécnico (opcional)"),
    brief_json: str = Form(..., description="JSON stringificado do UserBrief"),
    project_id: str | None = Form(None),
    user=Depends(admin_user),
) -> JSONResponse:
    """Corre o pipeline completo e persiste um snapshot."""
    ensure_not_demo(user, action="bet_agent_run")

    if not bet_agent_enabled():
        raise HTTPException(
            status_code=503,
            detail={"error": "feature_disabled",
                    "message": "BET_AGENT_ENABLED=false — activar via env var."},
        )
    if not is_anthropic_available():
        raise HTTPException(
            status_code=503,
            detail={"error": "anthropic_key_missing",
                    "message": "ANTHROPIC_API_KEY ausente nos segredos."},
        )

    try:
        raw_brief = json.loads(brief_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"brief_json inválido: {exc}") from exc

    run_id = str(uuid.uuid4())
    pid = project_id or f"adhoc-{run_id[:8]}"

    with tempfile.TemporaryDirectory(prefix="bet_agent_") as tdir:
        tpath = Path(tdir)
        arch_file = tpath / "arquitectura.pdf"
        arch_file.write_bytes(await arquitectura.read())
        pdf_paths: list[Path | str] = [arch_file]
        if geotecnico is not None:
            geo_file = tpath / "geotecnico.pdf"
            geo_file.write_bytes(await geotecnico.read())
            pdf_paths.append(geo_file)

        meter = DossierMeter(project_id=pid)

        try:
            # Dois clientes separados: reader + verificador = sessões isoladas.
            client_reader = AnthropicClient()
            client_verifier = AnthropicClient()
        except AnthropicNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        try:
            result = await run_pipeline(
                project_id=pid,
                pdf_paths=pdf_paths,
                raw_brief=raw_brief,
                client_reader=client_reader,
                client_verifier=client_verifier,
                meter=meter,
                enforce_flag=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("bet-agent run failed: %s", exc)
            raise HTTPException(status_code=500, detail={"error": "run_failed",
                                                         "message": str(exc)}) from exc

    doc = {
        "run_id": run_id,
        "project_id": pid,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "admin_user_id": user.get("user_id"),
        "summary": _summary_to_dict(result.summary),
        "pending_questions": result.pending_questions,
        "zoom_requests": result.zoom_requests,
        "reader_turns": result.reader_turns,
        "verifier_turns": result.verifier_turns,
        "verifier_finished": result.verifier_finished,
    }
    try:
        await db[COLLECTION_RUNS].insert_one(dict(doc))
    except Exception as exc:  # noqa: BLE001
        logger.warning("bet-agent persistence failed (non-fatal): %s", exc)

    doc.pop("_id", None)
    return JSONResponse(doc)


# ---------------------------------------------------------------------------
# Costs & runs
# ---------------------------------------------------------------------------

@router.get("/costs")
async def bet_agent_costs(user=Depends(admin_user)) -> dict[str, Any]:
    """Sumário agregado de custos dos últimos 100 dossiers."""
    ensure_not_demo(user, action="admin_read")

    cursor = db[COLLECTION_RUNS].find(
        {}, projection={"_id": 0, "run_id": 1, "project_id": 1,
                        "created_at": 1, "summary.cost": 1,
                        "summary.global_status": 1},
    ).sort("created_at", -1).limit(100)

    docs = await cursor.to_list(length=100)
    total_eur = 0.0
    exceeded_count = 0
    for d in docs:
        cost = (d.get("summary") or {}).get("cost") or {}
        total_eur += float(cost.get("eur_total", 0.0))
        if cost.get("exceeded_limit"):
            exceeded_count += 1

    return {
        "runs_count": len(docs),
        "total_eur": round(total_eur, 4),
        "exceeded_count": exceeded_count,
        "runs": docs,
    }


@router.get("/runs")
async def bet_agent_runs(
    limit: int = 50,
    user=Depends(admin_user),
) -> dict[str, Any]:
    ensure_not_demo(user, action="admin_read")
    cursor = db[COLLECTION_RUNS].find(
        {}, projection={"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(limit, 200)))
    docs = await cursor.to_list(length=limit)
    return {"runs": docs}


@router.get("/runs/{run_id}")
async def bet_agent_run_detail(run_id: str, user=Depends(admin_user)) -> dict[str, Any]:
    ensure_not_demo(user, action="admin_read")
    doc = await db[COLLECTION_RUNS].find_one({"run_id": run_id}, projection={"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="run não encontrado")
    return doc
