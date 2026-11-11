"""Endpoints admin para gestão de contas demo Web Summit.

- `POST /api/admin/demo/reset` → reset manual on-demand dos dados demo.
- `GET  /api/admin/demo/status` → estado da configuração (nomes de env OK/missing, nunca valores).

Protegido por admin_user — a conta demo nunca pode aceder (não tem role=admin).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from core.db import db
from core.security import admin_user
from core.websummit_seed_pt import (
    is_websummit_demo_configured,
    reset_websummit_demo_data_pt,
)

router = APIRouter(prefix="/admin/demo", tags=["admin-demo"])


@router.post("/reset")
async def admin_demo_reset(user=Depends(admin_user)) -> dict:
    """Reset manual dos dados sintéticos. Só admin real pode chamar."""
    summary = await reset_websummit_demo_data_pt(db)
    return {"ok": True, "summary": summary}


@router.get("/status")
async def admin_demo_status(user=Depends(admin_user)) -> dict:
    """Diagnóstico: contas demo existem? Config env OK? Nenhum valor sensível."""
    cfg = is_websummit_demo_configured()
    pro_user = await db.users.find_one(
        {"is_demo": True, "demo_source": "websummit_2026", "account_type": "pro"},
        {"user_id": 1, "email": 1, "plan": 1},
    )
    part_user = await db.users.find_one(
        {"is_demo": True, "demo_source": "websummit_2026", "account_type": "particulier"},
        {"user_id": 1, "email": 1, "plan": 1},
    )
    return {
        "config": cfg,
        "pro_account_exists": bool(pro_user),
        "particular_account_exists": bool(part_user),
        "pro_email": pro_user.get("email") if pro_user else None,
        "particular_email": part_user.get("email") if part_user else None,
    }


# ---------------------------------------------------------------------------
# Empresa de demonstração « Teste Websummit » (conta Pro Business completa)
# ---------------------------------------------------------------------------

@router.get("/teste-websummit/status")
async def teste_websummit_status(user=Depends(admin_user)) -> dict:
    """Estado do seed (contagens por módulo, erros de API). Nunca devolve palavras-passe."""
    st = await db.demo_seed_state.find_one({"_id": "teste_websummit"}, {"_id": 0}) or {"status": "absent"}
    owner = await db.users.find_one({"email": "teste.websummit@construpilot.pt"}, {"_id": 0, "user_id": 1, "organization_id": 1})
    return {**st, "owner_exists": bool(owner), "organization_id": (owner or {}).get("organization_id")}


@router.post("/teste-websummit/reseed")
async def teste_websummit_reseed(request: Request, user=Depends(admin_user)) -> dict:
    """Apaga APENAS os dados da empresa Teste Websummit e recria tudo (em segundo plano, ~1 min)."""
    import asyncio
    from core.demo_tws.seed import run_seed
    from core.security import hash_password, new_user_id
    request.app.state.tws_reseed_task = asyncio.create_task(
        run_seed(request.app, db, hash_password, new_user_id, force=True))
    return {"ok": True, "started": True, "status_url": "/api/admin/demo/teste-websummit/status"}
