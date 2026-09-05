"""Analyse ferraillage IA + bordereau acier + conversion commandable + bons de commande.
Module « Analyse technique & Approvisionnement IA » — Phase 1 (Acier)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, rebar

router = APIRouter(prefix="/pro/steel", tags=["steel"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _get_plan(plan_id: str, user_id: str) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return p


@router.post("/{plan_id}/analyze")
async def analyze(plan_id: str, user=Depends(current_user)) -> dict:
    p = await _get_plan(plan_id, user["user_id"])
    images = [pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")][:4]
    if not images:
        raise HTTPException(422, "Aucune image de plan à analyser")
    data = await ai.analyze_rebar(images)
    lines = rebar.enrich_lines(data.get("lines") or [])
    treillis = data.get("treillis") or []
    s = rebar.summary(lines, treillis)
    doc = {
        "plan_id": plan_id, "user_id": user["user_id"], "filename": p.get("filename"),
        "scale_detected": data.get("scale_detected"),
        "scale_confidence": data.get("scale_confidence"),
        "element_count": int(data.get("element_count") or 1),
        "notes": data.get("notes"), "lines": lines, "treillis": treillis,
        "summary": s, "updated_at": _now(),
    }
    await db.steel_analyses.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                       {"$set": doc, "$setOnInsert": {"created_at": _now()}},
                                       upsert=True)
    return doc


@router.get("/{plan_id}")
async def get_analysis(plan_id: str, user=Depends(current_user)) -> dict:
    d = await db.steel_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not d:
        raise HTTPException(404, "Aucune analyse acier pour ce plan")
    return d


class SaveIn(BaseModel):
    lines: list[dict] = Field(default_factory=list)
    treillis: list[dict] = Field(default_factory=list)


@router.put("/{plan_id}")
async def save_analysis(plan_id: str, body: SaveIn, user=Depends(current_user)) -> dict:
    lines = rebar.enrich_lines(body.lines)
    s = rebar.summary(lines, body.treillis)
    await db.steel_analyses.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"lines": lines, "treillis": body.treillis, "summary": s, "updated_at": _now()}})
    return {"lines": lines, "treillis": body.treillis, "summary": s}


class OrderIn(BaseModel):
    loss_pct: float = Field(default=7.0, ge=0, le=50)
    bar_length_m: float = Field(default=12.0, gt=0, le=18)
    element_count: int = Field(default=1, ge=1, le=999)
    supplier_id: str | None = None
    project: str | None = None


def _scaled(d: dict, count: int):
    """Multiplie les quantités par le nombre d'éléments identiques (ex. « Nombre : 2 »)."""
    c = max(1, int(count or 1))
    lines = [{**ln, "ml": round(float(ln.get("ml") or 0) * c, 1)} for ln in (d.get("lines") or [])]
    treillis = [{**t, "panels": (int(t.get("panels") or 0) * c) if t.get("panels") else t.get("panels")}
                for t in (d.get("treillis") or [])]
    return lines, treillis


@router.post("/{plan_id}/commandable")
async def commandable(plan_id: str, body: OrderIn, user=Depends(current_user)) -> dict:
    d = await db.steel_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not d:
        raise HTTPException(404, "Analyse acier introuvable")
    lines, treillis = _scaled(d, body.element_count)
    conv = rebar.to_commandable(lines, treillis,
                                {"loss_pct": body.loss_pct, "bar_length_m": body.bar_length_m})
    conv["element_count"] = max(1, int(body.element_count or 1))
    supplier = None
    if body.supplier_id:
        supplier = await db.suppliers.find_one(
            {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0})
    return {"commandable": conv, "supplier": supplier, "csv": rebar.to_csv(conv["items"])}


@router.post("/{plan_id}/order")
async def create_order(plan_id: str, body: OrderIn, user=Depends(current_user)) -> dict:
    """Crée un bon de commande (validation humaine préalable côté UI). Pas d'envoi API auto."""
    d = await db.steel_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not d:
        raise HTTPException(404, "Analyse acier introuvable")
    lines, treillis = _scaled(d, body.element_count)
    conv = rebar.to_commandable(lines, treillis,
                                {"loss_pct": body.loss_pct, "bar_length_m": body.bar_length_m})
    supplier = await db.suppliers.find_one(
        {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0}) if body.supplier_id else None
    order = {
        "order_id": "cmd_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
        "plan_id": plan_id, "project": body.project, "type": "acier",
        "supplier": supplier, "items": conv["items"], "status": "brouillon",
        "created_at": _now(),
    }
    await db.material_orders.insert_one(order)
    order.pop("_id", None)
    order["csv"] = rebar.to_csv(conv["items"])
    return order
