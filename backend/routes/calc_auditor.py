"""Route admin — Auditeur de cohérence des calculs.

Lance l'audit (à la demande) et expose les résultats. L'audit compare les prix de
référence des moteurs déterministes au marché (Perplexity). Zéro hallucination :
les prix de marché viennent du web avec citations, les écarts sont signalés.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import admin_user
from engines import calc_auditor

router = APIRouter(prefix="/admin/calc-audit", tags=["calc-audit"],
                   dependencies=[Depends(admin_user)])


@router.post("/run")
async def run_now() -> dict:
    """Démarre une audit en arrière-plan. Renvoie l'audit en cours s'il y en a déjà une."""
    if not calc_auditor._pplx_configured():
        raise HTTPException(400, "Perplexity non configuré (PERPLEXITY_API_KEY).")
    running = await db.calc_audits.find_one({"status": "running"}, {"_id": 0, "audit_id": 1})
    if running:
        return {"audit_id": running["audit_id"], "status": "running", "already": True}
    audit_id = await calc_auditor._create_run("admin", calc_auditor.DEFAULT_THRESHOLD_PCT)
    asyncio.create_task(calc_auditor._execute_run(audit_id, calc_auditor.DEFAULT_THRESHOLD_PCT))
    return {"audit_id": audit_id, "status": "running"}


@router.get("/latest")
async def latest() -> dict:
    doc = await db.calc_audits.find_one({}, {"_id": 0}, sort=[("started_at", -1)])
    overrides = await calc_auditor.list_overrides()
    return {"audit": doc, "configured": calc_auditor._pplx_configured(),
            "threshold_pct": calc_auditor.DEFAULT_THRESHOLD_PCT,
            "overrides": {o["code"]: o for o in overrides}}


class CodeIn(BaseModel):
    code: str


@router.post("/apply")
async def apply(body: CodeIn, admin=Depends(admin_user)) -> dict:
    """Confirme un écart : le prix de marché devient le nouveau prix de référence du auditeur."""
    try:
        doc = await calc_auditor.apply_override(body.code, admin.get("user_id"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "override": doc}


@router.post("/revert")
async def revert(body: CodeIn) -> dict:
    ok = await calc_auditor.revert_override(body.code)
    if not ok:
        raise HTTPException(404, "Aucune correction à annuler pour cet article")
    return {"ok": True, "code": body.code}


@router.get("/history")
async def history() -> dict:
    rows = await db.calc_audits.find(
        {}, {"_id": 0, "items": 0}).sort("started_at", -1).limit(30).to_list(30)
    return {"runs": rows}
