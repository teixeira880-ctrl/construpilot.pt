"""Rotas « Planos de execução — Eletricidade e Canalização » (ofertas Pro e Pro Business).

Sem IA: o motor é determinístico e parte da geometria já lida e validada pelo utilizador no módulo Plantas.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from engines.access import require_level
from engines.mep import generate, recompute
from engines.mep import render as R
from engines.mep.adapter import AdapterError, from_takeoff
from engines.mep.pdf import build_pdf
from engines.mep.quantities import price
from engines.mep.rules import rules_for

router = APIRouter(prefix="/mep", tags=["mep"], dependencies=[Depends(require_level("pro"))])

from routes.auth import current_user  # noqa: E402
from engines.nom_fichier import content_disposition, nom_document, sujet_lisible

DEFAULT_COUNTRY = os.environ.get("MEP_COUNTRY", "pt").lower()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid() -> str:
    return "mep_" + uuid.uuid4().hex[:12]


class LevelIn(BaseModel):
    page_index: int = 0
    name: str | None = None
    elevation_m: float | None = None
    height_m: float | None = 2.5
    origin: list[float] | None = None


class FromPlanIn(BaseModel):
    plan_id: str
    country: str | None = None
    levels: list[LevelIn] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    title: str | None = None


class FromInputIn(BaseModel):
    input: dict
    title: str | None = None


class LayoutIn(BaseModel):
    points: list[dict] | None = None
    equipment: list[dict] | None = None


def _public(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


async def _save(user_id: str, study: dict, title: str, plan_id: str | None = None) -> dict:
    doc = {"study_id": _sid(), "user_id": user_id, "plan_id": plan_id, "title": title[:160],
           "created_at": _now(), "updated_at": _now(), "version": 1, **study}
    await db.mep_studies.insert_one({**doc})
    return _public(doc)


async def _get(study_id: str, user_id: str) -> dict:
    doc = await db.mep_studies.find_one({"study_id": study_id, "user_id": user_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Estudo não encontrado")
    return doc


@router.post("/studies")
async def create_from_plan(body: FromPlanIn, user=Depends(current_user)) -> dict:
    plan = await db.plans_takeoff.find_one(
        {"plan_id": body.plan_id, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1, "rooms": 1, "calibrations": 1, "structure": 1, "mep_fixtures": 1})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")
    try:
        data = from_takeoff(plan, [lv.model_dump(exclude_none=True) for lv in body.levels] or None,
                            (body.country or DEFAULT_COUNTRY), body.options)
        study = generate(data)
    except (AdapterError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    return await _save(user["user_id"], study, body.title or f"Planos de execução — {plan.get('filename') or ''}",
                       body.plan_id)


@router.post("/studies/from-input")
async def create_from_input(body: FromInputIn, user=Depends(current_user)) -> dict:
    # Limite defensivo: a entrada livre do motor fica razoável (payload gigante).
    import json as _json
    if len(_json.dumps(body.input, default=str)) > 2_000_000:
        raise HTTPException(413, "Dados de entrada demasiado volumosos")
    data = {**body.input, "country": (body.input.get("country") or DEFAULT_COUNTRY)}
    try:
        study = generate(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return await _save(user["user_id"], study, body.title or (data.get("project") or {}).get("name") or "Estudo de instalações")


@router.get("/studies")
async def list_studies(user=Depends(current_user)) -> dict:
    rows = await db.mep_studies.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "study_id": 1, "title": 1, "plan_id": 1, "country": 1, "summary": 1, "created_at": 1,
         "updated_at": 1, "version": 1}).sort("updated_at", -1).to_list(100)
    return {"studies": rows}


@router.get("/studies/{study_id}")
async def get_study(study_id: str, user=Depends(current_user)) -> dict:
    return await _get(study_id, user["user_id"])


@router.put("/studies/{study_id}/layout")
async def update_layout(study_id: str, body: LayoutIn, user=Depends(current_user)) -> dict:
    """O profissional move / acrescenta / apaga pontos: tudo é recalculado
    (circuitos, proteções, comprimentos, controlos, quantidades) sobre a SUA implantação."""
    doc = await _get(study_id, user["user_id"])
    for p in body.points or []:
        p.setdefault("source", "user")
    study = recompute(doc, {"points": body.points, "equipment": body.equipment})
    patch = {**study, "updated_at": _now(), "version": int(doc.get("version", 1)) + 1}
    await db.mep_studies.update_one({"study_id": study_id, "user_id": user["user_id"]}, {"$set": patch})
    return {**doc, **patch}


@router.post("/studies/{study_id}/price")
async def price_study(study_id: str, user=Depends(current_user)) -> dict:
    """Preços EXCLUSIVAMENTE da biblioteca de preços da empresa."""
    from routes.company_library import get_user_library
    doc = await _get(study_id, user["user_id"])
    library = await get_user_library(user["user_id"])
    totals = price(doc["quantities"], library)
    await db.mep_studies.update_one({"study_id": study_id, "user_id": user["user_id"]},
                                    {"$set": {"quantities": doc["quantities"], "pricing": totals,
                                              "updated_at": _now()}})
    return {"quantities": doc["quantities"], "pricing": totals}


@router.get("/studies/{study_id}/svg")
async def study_svg(study_id: str, layer: str = Query("elec", pattern="^(elec|plumb|unifilar)$"),
                    level: str | None = None, user=Depends(current_user)) -> Response:
    doc = await _get(study_id, user["user_id"])
    level_id = level or doc["levels"][0]["id"]
    if layer != "unifilar" and level_id not in {lv["id"] for lv in doc["levels"]}:
        raise HTTPException(404, "Piso desconhecido")
    if layer == "elec":
        scene = R.elec_scene(doc, level_id)
    elif layer == "plumb":
        scene = R.plumb_scene(doc, level_id, rules_for(doc["country"]))
    else:
        scene = R.unifilar_scene(doc)
    return Response(scene.to_svg(title=f"{layer} {level_id}"), media_type="image/svg+xml")


def _mep_sujet(doc: dict) -> str | None:
    title = doc.get("title") or ""
    return sujet_lisible(doc.get("project_name"), title.split("—")[-1] if "—" in title else title, doc.get("name"))


@router.get("/studies/{study_id}/pdf")
async def study_pdf(study_id: str, user=Depends(current_user)) -> Response:
    doc = await _get(study_id, user["user_id"])
    pdf = build_pdf(doc)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Planos-execucao-instalacoes", _mep_sujet(doc), doc.get("updated_at")))})


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str, user=Depends(current_user)) -> dict:
    r = await db.mep_studies.delete_one({"study_id": study_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Estudo não encontrado")
    return {"ok": True}
