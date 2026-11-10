"""Rotas do acompanhamento de cálculo ao vivo (/api/calc-live) — só a conta CLT Rezult.

GET  /calc-live/acesso              → {"acesso": bool} (o menu e a página escondem-se sem acesso)
GET  /calc-live/runs                → últimas execuções (resumo)
GET  /calc-live/runs/{run_id}?desde=N → execução + eventos com seq > N (sondagem incremental a cada 2 s)
DELETE /calc-live/runs/{run_id}     → apaga uma execução da lista
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from core.db import db
from core.security import current_user
from engines import calc_live as CL

router = APIRouter(prefix="/calc-live", tags=["calc-live"])


def _so_clt(user=Depends(current_user)):
    if not CL.is_clt(user):
        raise HTTPException(403, "Página reservada à conta CLT Rezult.")
    return user


@router.get("/acesso")
async def acesso(user=Depends(current_user)) -> dict:
    return {"acesso": CL.is_clt(user)}


@router.get("/runs")
async def listar(user=Depends(_so_clt)) -> dict:
    cur = db.calc_live_runs.find({"user_id": user["user_id"]}, {"_id": 0, "eventos": 0}).sort("started_at", -1).limit(30)
    return {"runs": [CL.resumo_run(r) async for r in cur]}


@router.get("/runs/{run_id}")
async def ler(run_id: str, desde: int = Query(0, ge=0), user=Depends(_so_clt)) -> dict:
    r = await db.calc_live_runs.find_one({"run_id": run_id, "user_id": user["user_id"]}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Execução não encontrada.")
    eventos = sorted((e for e in r.get("eventos") or [] if (e.get("seq") or 0) > desde), key=lambda e: e.get("seq") or 0)
    return {**CL.resumo_run(r), "eventos": eventos}


@router.delete("/runs/{run_id}")
async def apagar(run_id: str, user=Depends(_so_clt)) -> dict:
    res = await db.calc_live_runs.delete_one({"run_id": run_id, "user_id": user["user_id"]})
    return {"ok": bool(res.deleted_count)}
