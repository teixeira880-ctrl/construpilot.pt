"""Module Suivi de chantier (pack Business) — comptes-rendus, réserves, checklist."""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/site", tags=["site"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid(user):
    return user["user_id"]


# ── Comptes-rendus de visite ──
class ReportIn(BaseModel):
    project: str
    title: str = ""
    notes: str = ""
    lots: list[dict] = []      # [{name, progress}]
    photos: list[str] = []


@router.get("/reports")
async def list_reports(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_reports.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/reports")
async def create_report(body: ReportIn, user=Depends(current_user)):
    doc = {"report_id": "cr_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "created_at": _now()}
    await db.site_reports.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, user=Depends(current_user)):
    await db.site_reports.delete_one({"report_id": report_id, "user_id": _uid(user)})
    return {"ok": True}


# ── Réserves ──
class ReserveIn(BaseModel):
    project: str
    lot: str = ""
    description: str
    company: str = ""


@router.get("/reserves")
async def list_reserves(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_reserves.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)


@router.post("/reserves")
async def create_reserve(body: ReserveIn, user=Depends(current_user)):
    doc = {"reserve_id": "rs_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "status": "open", "created_at": _now(), "lifted_at": None}
    await db.site_reserves.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/reserves/{reserve_id}")
async def toggle_reserve(reserve_id: str, user=Depends(current_user)):
    r = await db.site_reserves.find_one({"reserve_id": reserve_id, "user_id": _uid(user)}, {"_id": 0})
    if not r:
        return {"ok": False}
    lifted = r.get("status") != "lifted"
    await db.site_reserves.update_one(
        {"reserve_id": reserve_id},
        {"$set": {"status": "lifted" if lifted else "open", "lifted_at": _now() if lifted else None}})
    return {"ok": True, "status": "lifted" if lifted else "open"}


@router.delete("/reserves/{reserve_id}")
async def delete_reserve(reserve_id: str, user=Depends(current_user)):
    await db.site_reserves.delete_one({"reserve_id": reserve_id, "user_id": _uid(user)})
    return {"ok": True}


# ── Checklist d'avancement ──
class ChecklistIn(BaseModel):
    project: str
    label: str
    lot: str = ""


@router.get("/checklist")
async def list_checklist(project: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if project:
        q["project"] = project
    return await db.site_checklist.find(q, {"_id": 0}).sort("created_at", 1).to_list(1000)


@router.post("/checklist")
async def create_checklist(body: ChecklistIn, user=Depends(current_user)):
    doc = {"item_id": "ck_" + secrets.token_hex(6), "user_id": _uid(user),
           **body.model_dump(), "done": False, "created_at": _now()}
    await db.site_checklist.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.patch("/checklist/{item_id}")
async def toggle_checklist(item_id: str, user=Depends(current_user)):
    r = await db.site_checklist.find_one({"item_id": item_id, "user_id": _uid(user)}, {"_id": 0, "done": 1})
    if not r:
        return {"ok": False}
    await db.site_checklist.update_one({"item_id": item_id}, {"$set": {"done": not r.get("done")}})
    return {"ok": True, "done": not r.get("done")}


@router.delete("/checklist/{item_id}")
async def delete_checklist(item_id: str, user=Depends(current_user)):
    await db.site_checklist.delete_one({"item_id": item_id, "user_id": _uid(user)})
    return {"ok": True}


@router.get("/projects")
async def list_projects(user=Depends(current_user)):
    uid = _uid(user)
    names = set()
    for coll in (db.site_reports, db.site_reserves, db.site_checklist):
        names.update(await coll.distinct("project", {"user_id": uid}))
    return sorted(n for n in names if n)
