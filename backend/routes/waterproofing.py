"""Métré étanchéité IA + bordereau par couche + commandable (module Approvisionnement)."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, waterproofing

router = APIRouter(prefix="/pro/waterproofing", tags=["waterproofing"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _plan(plan_id, uid):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": uid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    return p


@router.post("/{plan_id}/analyze")
async def analyze(plan_id: str, user=Depends(current_user)) -> dict:
    p = await _plan(plan_id, user["user_id"])
    images = [pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")][:4]
    if not images:
        raise HTTPException(422, "Nenhuma imagem de planta")
    d = await ai.analyze_waterproofing(images)
    comp = waterproofing.compute(d.get("surface_m2"), d.get("perimeter_m"), d.get("releve_h_m"),
                                 d.get("system_type"), d.get("layers"), d.get("confidence", 0.8),
                                 regions=d.get("regions"))
    doc = {"plan_id": plan_id, "user_id": user["user_id"], "filename": p.get("filename"),
           "scale_detected": d.get("scale_detected"), "scale_confidence": d.get("scale_confidence"),
           "surface_m2": d.get("surface_m2"), "perimeter_m": d.get("perimeter_m"),
           "releve_h_m": d.get("releve_h_m"), "system_type": comp["system_type"],
           "singular": d.get("singular") or [], "regions": d.get("regions") or [],
           "compute": comp, "notes": d.get("notes"), "updated_at": _now()}
    await db.waterproofing_analyses.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                               {"$set": doc, "$setOnInsert": {"created_at": _now()}},
                                               upsert=True)
    return doc


@router.get("/{plan_id}")
async def get_analysis(plan_id: str, user=Depends(current_user)) -> dict:
    d = await db.waterproofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                                 {"_id": 0})
    if not d:
        raise HTTPException(404, "Nenhuma análise de impermeabilização")
    return d


class Recompute(BaseModel):
    surface_m2: float = Field(ge=0)
    perimeter_m: float = Field(default=0, ge=0)
    releve_h_m: float = Field(default=0.5, ge=0)
    system_type: str = "bicouche"
    recouvrement_pct: float = Field(default=10, ge=0, le=50)
    loss_pct: float = Field(default=5, ge=0, le=50)


@router.post("/{plan_id}/recompute")
async def recompute(plan_id: str, body: Recompute, user=Depends(current_user)) -> dict:
    d = await db.waterproofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                                 {"_id": 0})
    if not d:
        raise HTTPException(404, "Análise não encontrada")
    layers = (d.get("compute") or {}).get("items") or []
    layer_names = [{"name": it["designation"]} for it in layers]
    comp = waterproofing.compute(body.surface_m2, body.perimeter_m, body.releve_h_m,
                                 body.system_type, layer_names, 0.8,
                                 {"recouvrement_pct": body.recouvrement_pct, "loss_pct": body.loss_pct},
                                 regions=d.get("regions"))
    await db.waterproofing_analyses.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"compute": comp, "surface_m2": body.surface_m2, "perimeter_m": body.perimeter_m,
                  "releve_h_m": body.releve_h_m, "system_type": comp["system_type"], "updated_at": _now()}})
    return {"compute": comp, "csv": waterproofing.to_csv(comp["items"])}


class OrderIn(BaseModel):
    supplier_id: str | None = None
    project: str | None = None


@router.post("/{plan_id}/order")
async def create_order(plan_id: str, body: OrderIn, user=Depends(current_user)) -> dict:
    d = await db.waterproofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                                 {"_id": 0})
    if not d:
        raise HTTPException(404, "Análise de impermeabilização não encontrada")
    items = (d.get("compute") or {}).get("items") or []
    supplier = await db.suppliers.find_one(
        {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0}) \
        if body.supplier_id else None
    import uuid
    order = {"order_id": "cmd_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
             "plan_id": plan_id, "project": body.project, "type": "etancheite",
             "supplier": supplier, "items": items, "status": "brouillon", "created_at": _now()}
    await db.material_orders.insert_one(order)
    order.pop("_id", None)
    order["csv"] = waterproofing.to_csv(items)
    return order
