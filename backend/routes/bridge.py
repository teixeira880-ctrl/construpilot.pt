"""Routes de l'Agent Ponte B2B↔B2C.

- Admin : stats, réglages, déclenchement manuel du lot.
- Public : désinscription des artisans (lien dans l'e-mail).
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.db import db
from core.security import admin_user
from engines import bridge

admin_router = APIRouter(prefix="/admin/bridge", tags=["admin-bridge"],
                         dependencies=[Depends(admin_user)])
public_router = APIRouter(prefix="/bridge", tags=["bridge"])


@admin_router.get("/stats")
async def stats() -> dict:
    return {"settings": await bridge.get_settings(), **(await bridge.bridge_stats())}


class SettingsBody(BaseModel):
    enabled: bool | None = None
    min_budget: int | None = None
    max_per_lead: int | None = None
    cooldown_days: int | None = None
    founder_name: str | None = None
    founder_phone: str | None = None
    site_url: str | None = None


@admin_router.post("/settings")
async def update_settings(body: SettingsBody) -> dict:
    return await bridge.set_settings(body.model_dump(exclude_none=True))


@admin_router.post("/run-batch")
async def run_batch() -> dict:
    return await bridge.run_bridge_batch()


@admin_router.get("/outreach")
async def outreach(limit: int = 30) -> dict:
    rows = await db.artisan_outreach.find({}, {"_id": 0}).sort("sent_at", -1).to_list(min(limit, 200))
    return {"outreach": rows}


@public_router.get("/u/{token}", response_class=HTMLResponse)
async def unsubscribe(token: str):
    res = await db.artisans.update_one({"unsub_token": token}, {"$set": {"opt_out": True}})
    ok = res.matched_count > 0
    msg = ("A sua subscrição foi cancelada." if ok else "Ligação inválida ou já processada.")
    return HTMLResponse(
        f'<!doctype html><html><body style="font-family:Arial,sans-serif;background:#f5f5f7;\n        display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">\n        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:32px 40px;text-align:center">\n        <div style="font-size:20px;font-weight:800;color:#0A0D14">ConstruPilot</div>\n        <p style="color:#334155;font-size:15px;margin-top:12px">{msg}</p>\n        <p style="color:#94A3B8;font-size:12px">Não voltará a receber convites da nossa parte.</p>\n        </div></body></html>')
