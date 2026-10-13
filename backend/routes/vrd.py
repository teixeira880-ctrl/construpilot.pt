"""Analyse VRD IA + bordereau réseaux/tranchées + commandable + bon de commande.
Module « Analyse technique & Approvisionnement IA » — Phase 3 (VRD)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, vrd

router = APIRouter(prefix="/pro/vrd", tags=["vrd"])


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _plan(plan_id, uid):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": uid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    return p


@router.get("/networks")
async def networks() -> dict:
    return {"items": [{"key": k, "label": v["label"], "pipe": v["pipe"],
                       "larg": v["larg"], "prof": v["prof"]}
                      for k, v in vrd.NETWORKS.items()]}


@router.post("/{plan_id}/analyze")
async def analyze(plan_id: str, user=Depends(current_user)) -> dict:
    p = await _plan(plan_id, user["user_id"])
    images = [pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")][:4]
    if not images:
        raise HTTPException(422, "Nenhuma imagem de planta")
    d = await ai.analyze_vrd(images)
    nets = d.get("networks") or []
    comp = vrd.compute(nets)
    doc = {"plan_id": plan_id, "user_id": user["user_id"], "filename": p.get("filename"),
           "scale_detected": d.get("scale_detected"), "scale_confidence": d.get("scale_confidence"),
           "networks": nets, "compute": comp, "notes": d.get("notes"), "updated_at": _now()}
    await db.vrd_analyses.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                     {"$set": doc, "$setOnInsert": {"created_at": _now()}},
                                     upsert=True)
    return doc


@router.get("/{plan_id}")
async def get_analysis(plan_id: str, user=Depends(current_user)) -> dict:
    d = await db.vrd_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Nenhuma análise de redes exteriores")
    return d


class NetIn(BaseModel):
    key: str
    length_ml: float = Field(default=0, ge=0)
    larg_m: float = Field(default=0.4, ge=0)
    prof_m: float = Field(default=0.8, ge=0)
    confidence: float = 0.9
    bbox: list[float] | None = None


class Recompute(BaseModel):
    networks: list[NetIn] = Field(default_factory=list)
    loss_pct: float = Field(default=5, ge=0, le=50)


@router.post("/{plan_id}/recompute")
async def recompute(plan_id: str, body: Recompute, user=Depends(current_user)) -> dict:
    d = await db.vrd_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Análise não encontrada")
    nets = [n.model_dump() for n in body.networks]
    comp = vrd.compute(nets, {"loss_pct": body.loss_pct})
    await db.vrd_analyses.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"networks": nets, "compute": comp, "updated_at": _now()}})
    return {"compute": comp, "csv": vrd.to_csv(comp["items"])}


class OrderIn(BaseModel):
    supplier_id: str | None = None
    project: str | None = None


@router.post("/{plan_id}/order")
async def create_order(plan_id: str, body: OrderIn, user=Depends(current_user)) -> dict:
    d = await db.vrd_analyses.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Análise de redes exteriores não encontrada")
    items = (d.get("compute") or {}).get("items") or []
    supplier = await db.suppliers.find_one(
        {"supplier_id": body.supplier_id, "user_id": user["user_id"]}, {"_id": 0}) \
        if body.supplier_id else None
    order = {"order_id": "cmd_" + uuid.uuid4().hex[:12], "user_id": user["user_id"],
             "plan_id": plan_id, "project": body.project, "type": "vrd",
             "supplier": supplier, "items": items, "status": "brouillon", "created_at": _now()}
    await db.material_orders.insert_one(order)
    order.pop("_id", None)
    order["csv"] = vrd.to_csv(items)
    return order
