"""Module RH — pointage chantier (selfie + GPS), heures, validation, doutes de chantier.
Réservé au plan Pro Business côté employeur. Les ouvriers ont un compte (role='worker')."""
import base64
import uuid
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, Query
from pydantic import BaseModel, EmailStr

from core.db import db
from core.security import current_user, hash_password, new_user_id
from engines import storage
from engines.monetization import require_pro_business

router = APIRouter(prefix="/hr", tags=["hr"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _require_employer(user: dict) -> None:
    await require_pro_business(user)


def _require_worker(user: dict) -> None:
    if user.get("role") != "worker":
        raise HTTPException(403, "Réservé aux comptes ouvriers")


def _employer_id_of(user: dict) -> str:
    """Pour un employeur = son user_id ; pour un ouvrier = son employer_id."""
    return user["user_id"] if user.get("role") != "worker" else user.get("employer_id")


def _public_worker(u: dict) -> dict:
    return {
        "worker_id": u["user_id"], "name": u.get("name"), "email": u.get("email"),
        "poste": u.get("poste"), "hourly_rate": u.get("hourly_rate"),
        "active": u.get("active", True), "created_at": u.get("created_at"),
    }


async def _decode_and_store_selfie(data_url: str, employer_id: str, worker_id: str) -> str:
    if not data_url or "base64," not in data_url:
        raise HTTPException(400, "Selfie manquant ou invalide")
    header, b64 = data_url.split("base64,", 1)
    ext = "png" if "image/png" in header else "jpg"
    try:
        raw = base64.b64decode(b64)
    except Exception:
        raise HTTPException(400, "Selfie illisible")
    if len(raw) > 6 * 1024 * 1024:
        raise HTTPException(413, "Selfie trop volumineux (max 6 Mo)")
    path = f"{storage.APP_NAME}/hr/{employer_id}/{worker_id}/{uuid.uuid4().hex}.{ext}"
    ct = storage.MIME.get(ext, "image/jpeg")
    result = await asyncio.to_thread(storage.put_object, path, raw, ct)
    stored = result.get("path", path)
    await db.hr_files.insert_one({
        "storage_path": stored, "content_type": ct, "size": result.get("size", len(raw)),
        "employer_id": employer_id, "worker_id": worker_id,
        "is_deleted": False, "created_at": _now(),
    })
    return stored


# ============================ EMPLOYEUR — OUVRIERS ============================

class WorkerIn(BaseModel):
    name: str
    email: EmailStr
    password: str
    poste: str | None = None
    hourly_rate: float | None = None


class WorkerUpdate(BaseModel):
    name: str | None = None
    poste: str | None = None
    hourly_rate: float | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    password: str


@router.post("/workers")
async def create_worker(body: WorkerIn, user=Depends(current_user)):
    await _require_employer(user)
    email = body.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "Un compte existe déjà avec cet email")
    if len(body.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (min 6 caractères)")
    doc = {
        "user_id": new_user_id(), "email": email, "name": body.name.strip(),
        "password_hash": hash_password(body.password), "picture": None,
        "role": "worker", "plan": "free", "auth_provider": "password",
        "employer_id": user["user_id"], "poste": (body.poste or "").strip() or None,
        "hourly_rate": body.hourly_rate, "active": True,
        "must_change_password": True, "created_at": _now(),
    }
    await db.users.insert_one(doc)
    return _public_worker(doc)


@router.get("/workers")
async def list_workers(user=Depends(current_user)):
    await _require_employer(user)
    rows = await db.users.find(
        {"role": "worker", "employer_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return [_public_worker(r) for r in rows]


async def _get_owned_worker(worker_id: str, employer_id: str) -> dict:
    w = await db.users.find_one({"user_id": worker_id, "role": "worker",
                                 "employer_id": employer_id}, {"_id": 0})
    if not w:
        raise HTTPException(404, "Ouvrier introuvable")
    return w


@router.patch("/workers/{worker_id}")
async def update_worker(worker_id: str, body: WorkerUpdate, user=Depends(current_user)):
    await _require_employer(user)
    await _get_owned_worker(worker_id, user["user_id"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.users.update_one({"user_id": worker_id}, {"$set": updates})
    return _public_worker(await _get_owned_worker(worker_id, user["user_id"]))


@router.post("/workers/{worker_id}/reset-password")
async def reset_worker_password(worker_id: str, body: PasswordReset, user=Depends(current_user)):
    await _require_employer(user)
    await _get_owned_worker(worker_id, user["user_id"])
    if len(body.password) < 6:
        raise HTTPException(400, "Mot de passe trop court (min 6 caractères)")
    await db.users.update_one({"user_id": worker_id},
                              {"$set": {"password_hash": hash_password(body.password),
                                        "must_change_password": True}})
    return {"ok": True}


@router.delete("/workers/{worker_id}")
async def deactivate_worker(worker_id: str, user=Depends(current_user)):
    await _require_employer(user)
    await _get_owned_worker(worker_id, user["user_id"])
    await db.users.update_one({"user_id": worker_id}, {"$set": {"active": False}})
    return {"ok": True}


# ============================ OUVRIER — POINTAGE ============================

class ClockIn(BaseModel):
    project_id: str
    selfie: str
    lat: float | None = None
    lng: float | None = None
    accuracy: float | None = None


class ClockOut(BaseModel):
    selfie: str
    lat: float | None = None
    lng: float | None = None
    accuracy: float | None = None


@router.get("/me/projects")
async def my_projects(user=Depends(current_user)):
    _require_worker(user)
    emp = user.get("employer_id")
    rows = await db.projects.find({"user_id": emp}, {"_id": 0, "project_id": 1,
                                                     "name": 1, "address": 1}) \
        .sort("created_at", -1).to_list(200)
    return rows


@router.get("/me/status")
async def my_status(user=Depends(current_user)):
    _require_worker(user)
    open_ts = await db.hr_timesheets.find_one(
        {"worker_id": user["user_id"], "status": "open"}, {"_id": 0})
    return {"open": open_ts}


@router.post("/clock-in")
async def clock_in(body: ClockIn, user=Depends(current_user)):
    _require_worker(user)
    emp = user.get("employer_id")
    if await db.hr_timesheets.find_one({"worker_id": user["user_id"], "status": "open"}):
        raise HTTPException(409, "Vous avez déjà un pointage en cours. Terminez-le d'abord.")
    proj = await db.projects.find_one({"project_id": body.project_id, "user_id": emp},
                                      {"_id": 0, "name": 1})
    if not proj:
        raise HTTPException(404, "Chantier introuvable")
    selfie_path = await _decode_and_store_selfie(body.selfie, emp, user["user_id"])
    entry = {
        "entry_id": f"ts_{uuid.uuid4().hex[:12]}", "worker_id": user["user_id"],
        "worker_name": user.get("name"), "employer_id": emp,
        "project_id": body.project_id, "project_name": proj.get("name"),
        "clock_in": _now(), "clock_out": None, "hours": None, "status": "open",
        "selfie_in": selfie_path, "selfie_out": None,
        "gps_in": {"lat": body.lat, "lng": body.lng, "accuracy": body.accuracy},
        "gps_out": None, "created_at": _now(),
    }
    await db.hr_timesheets.insert_one(entry)
    entry.pop("_id", None)
    return entry


@router.post("/clock-out")
async def clock_out(body: ClockOut, user=Depends(current_user)):
    _require_worker(user)
    ts = await db.hr_timesheets.find_one({"worker_id": user["user_id"], "status": "open"},
                                         {"_id": 0})
    if not ts:
        raise HTTPException(404, "Aucun pointage en cours")
    selfie_path = await _decode_and_store_selfie(body.selfie, ts["employer_id"], user["user_id"])
    out = datetime.now(timezone.utc)
    start = datetime.fromisoformat(ts["clock_in"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    hours = round((out - start).total_seconds() / 3600, 2)
    await db.hr_timesheets.update_one(
        {"entry_id": ts["entry_id"]},
        {"$set": {"clock_out": out.isoformat(), "hours": hours, "status": "pending",
                  "selfie_out": selfie_path,
                  "gps_out": {"lat": body.lat, "lng": body.lng, "accuracy": body.accuracy}}})
    return await db.hr_timesheets.find_one({"entry_id": ts["entry_id"]}, {"_id": 0})


@router.get("/me/timesheets")
async def my_timesheets(user=Depends(current_user)):
    _require_worker(user)
    return await db.hr_timesheets.find({"worker_id": user["user_id"]}, {"_id": 0}) \
        .sort("clock_in", -1).to_list(200)


# ============================ EMPLOYEUR — POINTAGES & VALIDATION ============================

class ValidateIn(BaseModel):
    status: str  # 'validated' | 'rejected'
    note: str | None = None


@router.get("/timesheets")
async def list_timesheets(user=Depends(current_user), worker_id: str | None = None,
                          project_id: str | None = None, status: str | None = None,
                          date_from: str | None = None, date_to: str | None = None):
    await _require_employer(user)
    q: dict = {"employer_id": user["user_id"]}
    if worker_id:
        q["worker_id"] = worker_id
    if project_id:
        q["project_id"] = project_id
    if status:
        q["status"] = status
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59"
        q["clock_in"] = rng
    return await db.hr_timesheets.find(q, {"_id": 0}).sort("clock_in", -1).to_list(1000)


@router.post("/timesheets/{entry_id}/validate")
async def validate_timesheet(entry_id: str, body: ValidateIn, user=Depends(current_user)):
    await _require_employer(user)
    if body.status not in ("validated", "rejected"):
        raise HTTPException(400, "Statut invalide")
    ts = await db.hr_timesheets.find_one({"entry_id": entry_id,
                                          "employer_id": user["user_id"]}, {"_id": 0})
    if not ts:
        raise HTTPException(404, "Pointage introuvable")
    if ts.get("status") == "open":
        raise HTTPException(400, "Pointage encore en cours (non terminé)")
    await db.hr_timesheets.update_one(
        {"entry_id": entry_id},
        {"$set": {"status": body.status, "validation_note": body.note,
                  "validated_by": user["user_id"], "validated_at": _now()}})
    return await db.hr_timesheets.find_one({"entry_id": entry_id}, {"_id": 0})


@router.get("/dashboard")
async def hr_dashboard(user=Depends(current_user), date_from: str | None = None,
                       date_to: str | None = None):
    await _require_employer(user)
    q: dict = {"employer_id": user["user_id"], "status": {"$ne": "open"}}
    if date_from or date_to:
        rng = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to + "T23:59:59"
        q["clock_in"] = rng
    rows = await db.hr_timesheets.find(q, {"_id": 0}).to_list(5000)
    by_worker: dict = {}
    by_project: dict = {}
    total_hours = 0.0
    pending = 0
    for r in rows:
        h = r.get("hours") or 0
        total_hours += h
        if r.get("status") == "pending":
            pending += 1
        w = r.get("worker_id")
        bw = by_worker.setdefault(w, {"worker_id": w, "worker_name": r.get("worker_name"),
                                      "hours": 0.0, "entries": 0, "validated_hours": 0.0})
        bw["hours"] += h
        bw["entries"] += 1
        if r.get("status") == "validated":
            bw["validated_hours"] += h
        p = r.get("project_id")
        bp = by_project.setdefault(p, {"project_id": p, "project_name": r.get("project_name"),
                                       "hours": 0.0, "entries": 0})
        bp["hours"] += h
        bp["entries"] += 1
    for d in (*by_worker.values(), *by_project.values()):
        d["hours"] = round(d["hours"], 2)
        if "validated_hours" in d:
            d["validated_hours"] = round(d["validated_hours"], 2)
    return {
        "total_hours": round(total_hours, 2), "entries": len(rows), "pending": pending,
        "by_worker": sorted(by_worker.values(), key=lambda x: -x["hours"]),
        "by_project": sorted(by_project.values(), key=lambda x: -x["hours"]),
    }


# ============================ COMMENTAIRES / DOUTES DE CHANTIER ============================

class NoteIn(BaseModel):
    project_id: str | None = None
    type: str = "comment"  # 'comment' | 'question'
    message: str


class ReplyIn(BaseModel):
    reply: str


@router.post("/site-notes")
async def create_note(body: NoteIn, user=Depends(current_user)):
    _require_worker(user)
    if not body.message.strip():
        raise HTTPException(400, "Message vide")
    proj_name = None
    if body.project_id:
        p = await db.projects.find_one({"project_id": body.project_id}, {"_id": 0, "name": 1})
        proj_name = (p or {}).get("name")
    doc = {
        "note_id": f"note_{uuid.uuid4().hex[:12]}", "employer_id": user.get("employer_id"),
        "worker_id": user["user_id"], "worker_name": user.get("name"),
        "project_id": body.project_id, "project_name": proj_name,
        "type": body.type if body.type in ("comment", "question") else "comment",
        "message": body.message.strip(), "status": "open", "reply": None,
        "created_at": _now(),
    }
    await db.hr_notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/me/site-notes")
async def my_notes(user=Depends(current_user)):
    _require_worker(user)
    return await db.hr_notes.find({"worker_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)


@router.get("/site-notes")
async def list_notes(user=Depends(current_user), status: str | None = None):
    await _require_employer(user)
    q: dict = {"employer_id": user["user_id"]}
    if status:
        q["status"] = status
    return await db.hr_notes.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.post("/site-notes/{note_id}/reply")
async def reply_note(note_id: str, body: ReplyIn, user=Depends(current_user)):
    await _require_employer(user)
    n = await db.hr_notes.find_one({"note_id": note_id, "employer_id": user["user_id"]},
                                   {"_id": 0})
    if not n:
        raise HTTPException(404, "Message introuvable")
    await db.hr_notes.update_one(
        {"note_id": note_id},
        {"$set": {"reply": body.reply.strip(), "status": "answered",
                  "replied_at": _now()}})
    return await db.hr_notes.find_one({"note_id": note_id}, {"_id": 0})


# ============================ SELFIE (image protégée) ============================

@router.get("/selfie")
async def get_selfie(path: str = Query(...), user=Depends(current_user)):
    rec = await db.hr_files.find_one({"storage_path": path, "is_deleted": False}, {"_id": 0})
    if not rec:
        raise HTTPException(404, "Image introuvable")
    # Accès : l'employeur propriétaire, ou l'ouvrier concerné
    role = user.get("role")
    allowed = (rec.get("worker_id") == user["user_id"]) or \
              (role != "worker" and rec.get("employer_id") == user["user_id"]) or \
              (role == "admin")
    if not allowed:
        raise HTTPException(403, "Accès refusé")
    data, ct = await asyncio.to_thread(storage.get_object, path)
    return Response(content=data, media_type=rec.get("content_type", ct))
