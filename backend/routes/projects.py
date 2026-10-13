import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from core.db import db
from core.security import current_user
from engines import estimation, ai, pdf

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    project_type: str = "renovation_complete"
    surface: float = 100
    finish_level: str = "standard"
    country: str = "PT"
    region: str | None = None
    city: str | None = None
    postal_code: str | None = None
    building_type: str = "maison"
    condition: str = "bon"
    construction_year: int | None = None
    budget: float | None = None
    lots: list[str] | None = None
    estimation: dict | None = None
    analysis: dict | None = None


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get(project_id: str, user: dict):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    return p


@router.post("")
async def create_project(body: ProjectIn, user=Depends(current_user)):
    est = body.estimation
    if not est:
        est = estimation.estimate(body.project_type, body.surface, body.finish_level, body.country,
                                  body.region, body.building_type, body.condition,
                                  body.construction_year, body.lots)
        est["planning"] = estimation.planning(est["lots"])
        est["diy_vs_pro"] = estimation.diy_vs_pro(est)
        est["safety_alerts"] = estimation.safety_check(body.description,
                                                       [l["key"] for l in est["lots"]])
    doc = {
        "project_id": f"prj_{uuid.uuid4().hex[:12]}", "user_id": user["user_id"],
        **body.model_dump(exclude={"estimation"}), "estimation": est,
        "budget": body.budget or est["total_avg"],
        "progress": {l["key"]: "todo" for l in est["lots"]},
        "expenses": [], "photos": [], "documents": [], "materials": [], "quotes": [],
        "advice": "", "status": "active", "created_at": _now(), "updated_at": _now(),
    }
    await db.projects.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_projects(user=Depends(current_user)):
    return await db.projects.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)


@router.get("/{project_id}")
async def get_project(project_id: str, user=Depends(current_user)):
    p = await _get(project_id, user)
    from routes.project_quotes import project_artisan_block
    p["artisan"] = await project_artisan_block(p)
    return p


class UpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None
    budget: float | None = None
    city: str | None = None
    region: str | None = None
    progress: dict | None = None
    notes: str | None = None
    materials: list | None = None
    advice: str | None = None
    status: str | None = None
    estimation: dict | None = None


@router.patch("/{project_id}")
async def update_project(project_id: str, body: UpdateIn, user=Depends(current_user)):
    await _get(project_id, user)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["updated_at"] = _now()
    await db.projects.update_one({"project_id": project_id}, {"$set": updates})
    return await _get(project_id, user)


@router.delete("/{project_id}")
async def delete_project(project_id: str, user=Depends(current_user)) -> dict:
    from routes.trash import trash_record
    project = await _get(project_id, user)
    res = await trash_record("project", project, user["user_id"])
    await db.projects.delete_one({"project_id": project_id})
    return res


class ExpenseIn(BaseModel):
    label: str
    amount: float
    lot: str | None = None


@router.post("/{project_id}/expenses")
async def add_expense(project_id: str, body: ExpenseIn, user=Depends(current_user)):
    await _get(project_id, user)
    exp = {"expense_id": f"exp_{uuid.uuid4().hex[:8]}", **body.model_dump(), "date": _now()}
    await db.projects.update_one({"project_id": project_id},
                                 {"$push": {"expenses": exp}, "$set": {"updated_at": _now()}})
    return await budget(project_id, user)


@router.get("/{project_id}/budget")
async def budget(project_id: str, user=Depends(current_user)) -> dict:
    p = await _get(project_id, user)
    initial = float(p.get("budget") or p["estimation"]["total_avg"])
    spent = round(sum(e["amount"] for e in p.get("expenses", [])), 2)
    progress = p.get("progress", {})
    lots = p["estimation"]["lots"]
    done_value = sum(l["total"] for l in lots if progress.get(l["key"]) == "done")
    total_value = sum(l["total"] for l in lots) or 1
    pct_done = done_value / total_value
    forecast = round(spent / pct_done, 2) if pct_done > 0.05 else round(
        max(initial, spent + p["estimation"]["total_avg"] * (1 - pct_done)), 2)
    overrun = round(forecast - initial, 2)
    return {
        "initial": initial, "spent": spent, "remaining": round(initial - spent, 2),
        "forecast": forecast, "overrun": overrun if overrun > 0 else 0,
        "progress_pct": round(pct_done * 100, 1),
        "warning": (f'Risco de excedente de {overrun:,.0f} € detetado: reduza o nível de acabamento ou renegocie um lote.'
                    .replace(",", " ") if overrun > 0 else None),
        "expenses": p.get("expenses", []),
    }


@router.post("/{project_id}/advice")
async def project_advice(project_id: str, user=Depends(current_user)) -> dict:
    p = await _get(project_id, user)
    text = await ai.project_advice(p["estimation"])
    await db.projects.update_one({"project_id": project_id},
                                 {"$set": {"advice": text, "updated_at": _now()}})
    return {"advice": text}


@router.get("/{project_id}/pdf")
async def project_pdf(project_id: str, user=Depends(current_user)):
    p = await _get(project_id, user)
    est = p["estimation"]
    data = pdf.build_estimation_pdf(p, est, est.get("planning") or [], p.get("advice") or "", user)
    safe = "".join(c for c in p["name"] if c.isalnum() or c in " -_").strip() or "projet"
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="Estimation-ConstruPilot-{safe}.pdf"'})


PROGRESS_LABEL = {"todo": "a fazer", "doing": "en cours", "done": "terminé"}


@router.get("/{project_id}/timeline")
async def project_timeline(project_id: str, user=Depends(current_user)) -> dict:
    """Frise chronologique : création + photos + dépenses + lots + leads."""
    p = await _get(project_id, user)
    events: list[dict] = []

    events.append({
        "type": "project", "kind": "created", "at": p.get("created_at"),
        "title": "Projeto criado", "detail": p.get("name"),
        "amount": p.get("estimation", {}).get("total_avg"),
    })

    for ph in p.get("photos", []):
        events.append({
            "type": "photo", "kind": ph.get("kind"), "at": ph.get("created_at"),
            "title": {"before": "Photo AVANT", "after": "Fotografia DEPOIS",
                      "progress": "Fotografia da obra"}.get(ph.get("kind"), "Fotografia"),
            "detail": ph.get("caption") or ph.get("lot") or "",
            "photo_id": ph.get("photo_id"), "lot": ph.get("lot"),
        })

    for e in p.get("expenses", []):
        events.append({
            "type": "expense", "kind": "spent", "at": e.get("date"),
            "title": "Despesa", "detail": e.get("label"),
            "amount": e.get("amount"), "lot": e.get("lot"),
        })

    lots_by_key = {l["key"]: l for l in p.get("estimation", {}).get("lots", [])}
    for key, status in (p.get("progress") or {}).items():
        if status and status != "todo":
            lot_info = lots_by_key.get(key, {})
            events.append({
                "type": "progress", "kind": status,
                "at": p.get("updated_at") or p.get("created_at"),
                "title": f'Lote {PROGRESS_LABEL.get(status, status)}',
                "detail": lot_info.get("name", key),
                "amount": lot_info.get("total") if status == "done" else None,
            })

    leads = await db.leads.find({"project_id": project_id, "user_id": user["user_id"]},
                                {"_id": 0}).to_list(100)
    for l in leads:
        events.append({
            "type": "lead", "kind": l.get("status", "nouveau"),
            "at": l.get("created_at"),
            "title": "Pedido ConstruPilot enviado",
            "detail": f"{l.get('name')} · {l.get('phone') or l.get('email')}",
        })

    events.sort(key=lambda x: x.get("at") or "", reverse=True)
    return {"events": events, "count": len(events)}
