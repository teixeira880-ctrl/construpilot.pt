"""Rotas do Solver BTP · ConstruPilot (PT).

- POST /api/btp-solver/solve      · análise completa síncrona
- GET  /api/btp-solver/history    · últimas análises do utilizador
- GET  /api/btp-solver/{id}       · detalhe de uma análise
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.btp_solver import solve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/btp-solver", tags=["btp-solver"])


class SolveIn(BaseModel):
    description: str = Field(..., min_length=10, max_length=4000)
    region: Optional[str] = Field(None, max_length=80)
    tipo_edificio: Optional[str] = Field(None, max_length=80)
    surface_m2: Optional[float] = Field(None, gt=0, lt=100000)
    idade_anos: Optional[int] = Field(None, ge=0, le=1000)
    urgencia: Optional[str] = Field(None, max_length=80)
    orcamento_max_eur: Optional[float] = Field(None, ge=0, le=100_000_000)
    project_id: Optional[str] = Field(None, max_length=60)


@router.post("/solve")
async def solve_problem(body: SolveIn, request: Request, user=Depends(current_user)):
    """Resolve um problema BTP: diagnóstico + soluções + gráficos.

    Chamada síncrona — devolve o resultado completo (p99 ~ 20 s com Opus 5.5).
    """
    context = {
        "region": body.region,
        "tipo_edificio": body.tipo_edificio,
        "surface_m2": body.surface_m2,
        "idade_anos": body.idade_anos,
        "urgencia": body.urgencia,
        "orcamento_max_eur": body.orcamento_max_eur,
    }
    try:
        resp = await solve(description=body.description, context=context)
    except Exception:
        logger.exception("btp_solver falhou para user=%s", user.get("user_id"))
        raise HTTPException(503, "Análise temporariamente indisponível. Tente novamente dentro de alguns instantes.") from None

    doc = resp.model_dump()
    doc.update({
        "user_id": user["user_id"],
        "project_id": body.project_id,
        "status": "done",
        "description": body.description,
        "context": context,
        "created_at": datetime.now(timezone.utc),
    })
    await db.btp_analyses.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("created_at", None)
    return doc


@router.get("/history")
async def history(limit: int = 20, user=Depends(current_user)):
    """Últimas análises do utilizador (sem o payload pesado de gráficos)."""
    items = await db.btp_analyses.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "user_id": 0, "created_at": 0, "charts": 0, "action_plan": 0, "references": 0},
    ).sort("generated_at_iso", -1).to_list(max(1, min(limit, 100)))
    return {"items": items}


@router.get("/{problem_id}")
async def detail(problem_id: str, user=Depends(current_user)):
    doc = await db.btp_analyses.find_one(
        {"problem_id": problem_id, "user_id": user["user_id"]},
        {"_id": 0, "user_id": 0, "created_at": 0},
    )
    if not doc:
        raise HTTPException(404, "Análise não encontrada.")
    return doc
