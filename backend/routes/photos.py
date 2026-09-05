"""Routes pour la galerie photos avant/après par projet."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Response

from core.db import db
from core.security import current_user
from engines import storage

router = APIRouter(prefix="/projects", tags=["photos"])

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_KIND = {"before", "after", "progress"}


async def _get_owned(project_id: str, user: dict) -> None:
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "project_id": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")


def _now():
    return datetime.now(timezone.utc).isoformat()


@router.post("/{project_id}/photos")
async def upload_photo(project_id: str,
                       file: UploadFile = File(...),
                       kind: str = Form("before"),
                       lot: str = Form(""),
                       caption: str = Form(""),
                       user=Depends(current_user)):
    await _get_owned(project_id, user)
    if kind not in ALLOWED_KIND:
        raise HTTPException(status_code=400, detail="Type invalide (before|after|progress)")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Fichier vide")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop lourd (max 10 Mo)")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg").lower()
    ext = ext if ext in {"jpg", "jpeg", "png", "webp", "heic", "heif"} else "jpg"
    path = f"{storage.APP_NAME}/projects/{project_id}/photos/{uuid.uuid4().hex}.{ext}"
    ctype = file.content_type or storage.mime_for(file.filename or "", "image/jpeg")
    try:
        result = storage.put_object(path, data, ctype)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upload impossible: {e}")
    photo = {
        "photo_id": f"ph_{uuid.uuid4().hex[:10]}",
        "storage_path": result.get("path") or path,
        "content_type": ctype,
        "size": result.get("size") or len(data),
        "kind": kind,
        "lot": lot or None,
        "caption": caption or None,
        "uploaded_by": user["user_id"],
        "created_at": _now(),
    }
    await db.projects.update_one({"project_id": project_id},
                                 {"$push": {"photos": photo},
                                  "$set": {"updated_at": _now()}})
    return photo


@router.get("/{project_id}/photos")
async def list_photos(project_id: str, user=Depends(current_user)) -> dict:
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "photos": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return {"photos": p.get("photos", [])}


@router.get("/{project_id}/photos/{photo_id}/download")
async def download_photo(project_id: str, photo_id: str, user=Depends(current_user)):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "photos": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    photo = next((ph for ph in p.get("photos", []) if ph.get("photo_id") == photo_id), None)
    if not photo:
        raise HTTPException(status_code=404, detail="Photo introuvable")
    try:
        data, ctype = storage.get_object(photo["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Lecture impossible: {e}")
    return Response(content=data,
                    media_type=photo.get("content_type") or ctype,
                    headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/{project_id}/photos/{photo_id}")
async def delete_photo(project_id: str, photo_id: str, user=Depends(current_user)) -> dict:
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "photos": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if not any(ph.get("photo_id") == photo_id for ph in p.get("photos", [])):
        raise HTTPException(status_code=404, detail="Photo introuvable")
    await db.projects.update_one({"project_id": project_id},
                                 {"$pull": {"photos": {"photo_id": photo_id}},
                                  "$set": {"updated_at": _now()}})
    return {"ok": True}
