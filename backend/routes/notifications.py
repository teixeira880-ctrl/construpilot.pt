"""Notifications utilisateur (lecture + marquage lu). Web + app mobile « Chantier »."""
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(unread: bool = False, limit: int = 50, user=Depends(current_user)) -> dict:
    q = {"user_id": user["user_id"]}
    if unread:
        q["read"] = {"$ne": True}
    rows = await db.notifications.find(q).sort("created_at", -1).to_list(min(limit, 200))
    items = []
    for r in rows:
        r["id"] = str(r.pop("_id"))
        items.append(r)
    unread_count = await db.notifications.count_documents(
        {"user_id": user["user_id"], "read": {"$ne": True}})
    return {"notifications": items, "unread_count": unread_count}


@router.post("/mark-all-read")
async def mark_all_read(user=Depends(current_user)) -> dict:
    res = await db.notifications.update_many(
        {"user_id": user["user_id"], "read": {"$ne": True}}, {"$set": {"read": True}})
    return {"ok": True, "marked": res.modified_count}


@router.post("/{notif_id}/read")
async def mark_read(notif_id: str, user=Depends(current_user)) -> dict:
    try:
        oid = ObjectId(notif_id)
    except Exception:
        raise HTTPException(400, "Identifiant invalide")
    res = await db.notifications.update_one(
        {"_id": oid, "user_id": user["user_id"]}, {"$set": {"read": True}})
    if not res.matched_count:
        raise HTTPException(404, "Notification introuvable")
    return {"ok": True}
