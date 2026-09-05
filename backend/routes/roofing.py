"""Analyse toiture IA (couverture en pente) + bordereau + conversion commandable + bon de commande.
Module « Analyse technique & Approvisionnement IA » — Phase 2 (Toiture)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, roofing

router = APIRouter(prefix="/pro/roofing", tags=["roofing"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _plan(plan_id, uid):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": uid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return p


@router.get("/materials")
async def materials() -> dict:
    return {"items": [{"key": k, "label": v["label"], "per_m2": v.get("per_m2"),
                       "is_area": v.get("is_area", False)}
                      for k, v in roofing.MATERIALS.items()]}


@router.post("/{plan_id}/analyze")
async def analyze(plan_id: str, material: str = "tuiles_terre_cuite",
                  user=Depends(current_user)) -> dict:
    p = await _plan(plan_id, user["user_id"])
    images = [pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")][:4]
    if not images:
        raise HTTPException(422, "Aucune image de plan")
    d = await ai.analyze_roofing(images)
    lengths = {"faitage_ml": d.get("faitage_ml"), "aretiers_ml": d.get("aretiers_ml"),
               "noues_ml": d.get("noues_ml"), "rives_ml": d.get("rives_ml"),
               "egout_ml": d.get("egout_ml")}
    comp = roofing.compute(d.get("surface_projetee_m2"), d.get("pente_pct"), material,
                           lengths, d.get("confidence", 0.8), regions=d.get("regions"))
    doc = {"plan_id": plan_id, "user_id": user["user_id"], "filename": p.get("filename"),
           "scale_detected": d.get("scale_detected"), "scale_confidence": d.get("scale_confidence"),
           "roof_type": d.get("roof_type"), "material": material,
           "surface_projetee_m2": d.get("surface_projetee_m2"), "pente_pct": d.get("pente_pct"),
           "lengths": lengths, "regions": d.get("regions") or [], "compute": comp,
           "notes": d.get("notes"), "updated_at": _now()}
    await db.roofing_analyses.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"$set": doc, "$setOnInsert": {"created_at": _now()}},
                                         upsert=True)
    return doc


@router.get("/{plan_id}")
async def get_analysis(plan_id: str, user=Depends(current_user)) -> dict:
    d = await db.roofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                           {"_id": 0})
    if not d:
        raise HTTPException(404, "Aucune analyse toiture")
    return d


class Recompute(BaseModel):
    surface_projetee_m2: float = Field(ge=0)
    pente_pct: float = Field(default=35, ge=0, le=200)
    material: str = "tuiles_terre_cuite"
    faitage_ml: float = Field(default=0, ge=0)
    aretiers_ml: float = Field(default=0, ge=0)
    noues_ml: float = Field(default=0, ge=0)
    rives_ml: float = Field(default=0, ge=0)
    egout_ml: float = Field(default=0, ge=0)
    loss_pct: float = Field(default=8, ge=0, le=50)


@router.post("/{plan_id}/recompute")
async def recompute(plan_id: str, body: Recompute, user=Depends(current_user)) -> dict:
    d = await db.roofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                           {"_id": 0})
    if not d:
        raise HTTPException(404, "Analyse introuvable")
    lengths = {"faitage_ml": body.faitage_ml, "aretiers_ml": body.aretiers_ml,
               "noues_ml": body.noues_ml, "rives_ml": body.rives_ml, "egout_ml": body.egout_ml}
    comp = roofing.compute(body.surface_projetee_m2, body.pente_pct, body.material, lengths,
                           0.9, {"loss_pct": body.loss_pct}, regions=d.get("regions"))
    await db.roofing_analyses.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"compute": comp, "surface_projetee_m2": body.surface_projetee_m2,
                  "pente_pct": body.pente_pct, "material": body.material,
                  "lengths": lengths, "updated_at": _now()}})
    return {"compute": comp, "csv": roofing.to_csv(comp["items"])}


class OrderIn(BaseModel):
    supplier_id: str | None = None
    project: str | None = None


@router.post("/{plan_id}/order")
async def create_order(plan_id: str, body: OrderIn, user=Depends(current_user)) -> dict:
    d = await db.roofing_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                           {"_id": 0})
    if not d:
        raise HTTPException(404, "Analyse toiture introuvable")
    items = (d.get("compute") or {}).get("items") or []
    supplier = await db.suppliers.find_one(
        {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0}) \
        if body.supplier_id else None
    order = {"order_id": "cmd_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
             "plan_id": plan_id, "project": body.project, "type": "toiture",
             "supplier": supplier, "items": items, "status": "brouillon", "created_at": _now()}
    await db.material_orders.insert_one(order)
    order.pop("_id", None)
    order["csv"] = roofing.to_csv(items)
    return order
