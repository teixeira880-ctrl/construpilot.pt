"""Module 6 — Planning de chantier : CPM, équipes, replanification, propositions, OR-Tools, PDF."""
import re
from datetime import date, datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, pro_required
from engines import planning as P
from engines.planning_pdf import build_planning_pdf
from engines.chantier_costs import _lot

router = APIRouter(prefix="/planning", tags=["planning"], dependencies=[Depends(pro_required)])
COLL = db.chantier_plannings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PredIn(BaseModel):
    id: str
    lag: int = 0


class TaskIn(BaseModel):
    id: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=160)
    resource: str = Field("Equipa", max_length=80)
    duration: int = Field(..., ge=1, le=365)
    duration_source: str = "saisie"
    predecessors: list[PredIn] = []
    progress: int = Field(0, ge=0, le=100)
    not_before: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    auto_link: bool = False
    planned_hours: Optional[float] = Field(None, ge=0, le=100000)
    progress_manual: bool = False


class PlanIn(BaseModel):
    start_date: str
    deadline: Optional[str] = None
    holidays: list[str] = []
    workdays: list[int] = [0, 1, 2, 3, 4]
    capacities: dict[str, int] = {}
    client_visible: bool = True
    tasks: list[TaskIn]


class InitIn(BaseModel):
    start_date: Optional[str] = None
    from_quotes: bool = True


class ProgressIn(BaseModel):
    progress: Optional[int] = Field(None, ge=0, le=100)
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    progress_manual: Optional[bool] = None
    planned_hours: Optional[float] = Field(None, ge=0, le=100000)


async def _chantier(cid: str, uid: str) -> dict:
    c = await db.chantiers.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Processo de obra não encontrado")
    return c


async def _quote_lots(cid: str, uid: str) -> list[str]:
    quotes = await db.pro_documents.find({"user_id": uid, "chantier_id": cid, "doc_type": "quote"},
                                         {"_id": 0, "lines": 1, "status": 1}).to_list(200)
    scope = [q for q in quotes if q.get("status") == "signed"] or quotes
    lots, seen = [], set()
    for q in scope:
        for ln in q.get("lines") or []:
            if not (ln.get("designation") or "").strip() or ln.get("kind") in ("section", "subsection", "text", "page_break"):
                continue
            lot = _lot(ln.get("category"))
            if lot not in seen:
                seen.add(lot)
                lots.append(lot)
    return lots


def _norm(s: str) -> str:
    return (s or "").strip().lower()


async def _lot_hours(cid: str, uid: str) -> dict:
    """Heures VALIDÉES pointées (module RH) par lot, avec première date de pointage."""
    c = await db.chantiers.find_one({"chantier_id": cid, "user_id": uid}, {"_id": 0, "name": 1})
    name = (c or {}).get("name") or ""
    q = {"status": "validated", "$or": [{"project_id": cid}, {"project_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}}]}
    rows = await db.hr_timesheets.find(q, {"_id": 0, "hours": 1, "clock_in": 1, "lot": 1}).to_list(5000)
    out: dict = {}
    for r in rows:
        key = _norm(r.get("lot"))
        if not key:
            continue
        g = out.setdefault(key, {"hours": 0.0, "first": None, "entries": 0})
        g["hours"] += float(r.get("hours") or 0)
        g["entries"] += 1
        d = (r.get("clock_in") or "")[:10]
        if d and (g["first"] is None or d < g["first"]):
            g["first"] = d
    return out


def _apply_timesheets(plan: dict, lot_hours: dict) -> list[dict]:
    """Avancement déduit du pointage : heures validées / heures prévues (plafonné à 99 % — la fin reste confirmée par le pro)."""
    synced = []
    for t in plan.get("tasks") or []:
        g = lot_hours.get(_norm(t.get("resource"))) or lot_hours.get(_norm(t.get("name")))
        t["hours_logged"] = round(g["hours"], 2) if g else 0.0
        t["timesheet_entries"] = g["entries"] if g else 0
        planned = float(t.get("planned_hours") or 0)
        if not g or planned <= 0 or t.get("progress_manual") or (t.get("progress") or 0) >= 100:
            t["progress_source"] = "manuel" if t.get("progress_manual") or (t.get("progress") or 0) >= 100 else "aucun"
            continue
        pct = min(99, int(round(g["hours"] * 100 / planned)))
        t["progress"], t["progress_source"] = pct, "pointage"
        if pct > 0 and not t.get("actual_start"):
            t["actual_start"] = g["first"]
        synced.append({"id": t["id"], "progress": pct, "hours": round(g["hours"], 2), "planned": planned})
    return synced


def _compute(plan: dict) -> dict:
    try:
        res = P.compute_schedule(plan)
    except P.PlanningError as e:
        raise HTTPException(422, str(e))
    res.pop("_cal", None)
    for r in res["tasks"]:
        src = next((t for t in plan.get("tasks") or [] if t.get("id") == r["id"]), {})
        r.update({k: src.get(k) for k in ("planned_hours", "hours_logged", "timesheet_entries", "progress_source", "progress_manual")})
    sugg = P.suggestions(plan, res, baseline=plan.get("baseline"))
    return {"schedule": res, "suggestions": sugg}


def _public(plan: dict, computed: dict) -> dict:
    return {"exists": True, **{k: plan.get(k) for k in ("chantier_id", "start_date", "deadline", "holidays", "workdays", "capacities",
                                                       "client_visible", "tasks", "baseline", "created_at", "updated_at", "timesheet_sync")},
            "trades": [n for _, n, _ in P.TRADE_ORDER], **computed}


async def _save(plan: dict) -> dict:
    plan["timesheet_sync"] = _apply_timesheets(plan, await _lot_hours(plan["chantier_id"], plan["user_id"]))
    computed = _compute(plan)
    plan["updated_at"] = _now()
    await COLL.update_one({"chantier_id": plan["chantier_id"], "user_id": plan["user_id"]}, {"$set": plan}, upsert=True)
    return _public(plan, computed)


@router.get("/chantiers/{cid}")
async def get_plan(cid: str, user=Depends(current_user)) -> dict:
    await _chantier(cid, user["user_id"])
    plan = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not plan:
        return {"exists": False, "lots_available": await _quote_lots(cid, user["user_id"]), "trades": [n for _, n, _ in P.TRADE_ORDER]}
    return await _save(plan)  # resynchronise le pointage à chaque lecture


@router.post("/chantiers/{cid}/init")
async def init_plan(cid: str, body: InitIn, user=Depends(current_user)) -> dict:
    await _chantier(cid, user["user_id"])
    lots = await _quote_lots(cid, user["user_id"]) if body.from_quotes else []
    tasks = P.tasks_from_lots(lots)
    plan = {"chantier_id": cid, "user_id": user["user_id"], "start_date": body.start_date or date.today().isoformat(),
            "deadline": None, "holidays": [], "workdays": [0, 1, 2, 3, 4], "capacities": {}, "client_visible": True, "tasks": tasks,
            "baseline": None, "created_at": _now(), "source": "devis" if lots else "vide"}
    out = await _save(plan)
    out["from_lots"] = lots
    return out


@router.put("/chantiers/{cid}")
async def save_plan(cid: str, body: PlanIn, user=Depends(current_user)) -> dict:
    await _chantier(cid, user["user_id"])
    ids = [t.id for t in body.tasks]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Identificadores de tarefas duplicados")
    prev = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0}) or {}
    plan = {**prev, "chantier_id": cid, "user_id": user["user_id"], **body.model_dump(),
            "created_at": prev.get("created_at") or _now()}
    return await _save(plan)


@router.patch("/chantiers/{cid}/tasks/{tid}")
async def task_progress(cid: str, tid: str, body: ProgressIn, user=Depends(current_user)) -> dict:
    plan = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Planeamento não encontrado")
    task = next((t for t in plan["tasks"] if t["id"] == tid), None)
    if not task:
        raise HTTPException(404, "Tarefa não encontrada")
    for k, v in body.model_dump(exclude_none=True).items():
        task[k] = v
    if body.progress is not None and body.progress_manual is None and float(task.get("planned_hours") or 0) > 0:
        task["progress_manual"] = True  # saisie manuelle = priorité sur le pointage
    if body.progress == 100 and not task.get("actual_end"):
        task["actual_end"] = date.today().isoformat()
    if (body.progress or 0) > 0 and not task.get("actual_start"):
        task["actual_start"] = date.today().isoformat()
    return await _save(plan)


@router.post("/chantiers/{cid}/baseline")
async def freeze_baseline(cid: str, user=Depends(current_user)) -> dict:
    plan = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Planeamento não encontrado")
    res = _compute(plan)["schedule"]
    plan["baseline"] = {"frozen_at": _now(), "end_date": res["project"]["end_date"],
                        "tasks": {t["id"]: t["end_date"] for t in res["tasks"]}}
    return await _save(plan)


@router.post("/chantiers/{cid}/optimize")
async def optimize_plan(cid: str, apply: bool = False, user=Depends(current_user)) -> dict:
    plan = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Planeamento não encontrado")
    try:
        opt = P.optimize(plan, time_limit_s=8.0)
    except P.PlanningError as e:
        raise HTTPException(422, str(e))
    if apply and opt.get("ok") and opt.get("gain_days", 0) > 0:
        P.apply_optimized(plan, opt)
        saved = await _save(plan)
        return {"optimization": opt, "applied": True, "plan": saved}
    return {"optimization": opt, "applied": False}


@router.delete("/chantiers/{cid}")
async def delete_plan(cid: str, user=Depends(current_user)) -> dict:
    r = await COLL.delete_one({"chantier_id": cid, "user_id": user["user_id"]})
    return {"ok": True, "deleted": r.deleted_count}


@router.get("/chantiers/{cid}/pdf")
async def plan_pdf(cid: str, user=Depends(current_user)):
    c = await _chantier(cid, user["user_id"])
    plan = await COLL.find_one({"chantier_id": cid, "user_id": user["user_id"]}, {"_id": 0})
    if not plan:
        raise HTTPException(404, "Planeamento não encontrado")
    computed = _compute(plan)
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"])
    pdf = build_planning_pdf(c, plan, computed["schedule"], computed["suggestions"], branding)
    name = f"Planning - {c.get('name', 'chantier')}.pdf".replace("/", "-")
    ascii_name = name.encode("ascii", "ignore").decode() or "Planning.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"})


async def client_view(chantier_id: str) -> Optional[dict]:
    """Vue lecture seule pour l'Espace Client (pas de marges/propositions internes)."""
    plan = await COLL.find_one({"chantier_id": chantier_id}, {"_id": 0})
    if not plan or not plan.get("client_visible", True):
        return None
    try:
        res = P.compute_schedule(plan)
    except P.PlanningError:
        return None
    today = date.today().isoformat()
    tasks = []
    for r in res["tasks"]:
        status = "termine" if r["progress"] >= 100 else "en_cours" if r["progress"] > 0 or (r["start_date"] <= today <= r["end_date"]) else "a_venir" if r["start_date"] > today else "en_retard"
        tasks.append({"id": r["id"], "name": r["name"], "lot": r["resource"], "start_date": r["start_date"], "end_date": r["end_date"],
                      "duration": r["duration"], "progress": r["progress"], "start_idx": r["start_idx"], "end_idx": r["end_idx"], "status": status})
    upcoming = sorted([t for t in tasks if t["status"] == "a_venir"], key=lambda t: t["start_date"])[:3]
    current = [t for t in tasks if t["status"] in ("en_cours", "en_retard")]
    p = res["project"]
    return {"project": {"start_date": p["start_date"], "end_date": p["end_date"], "duration_workdays": p["duration_workdays"], "as_of": today},
            "tasks": tasks, "current": current, "upcoming": upcoming, "updated_at": plan.get("updated_at")}
