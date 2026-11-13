"""Rotas BIM — modelo IFC 4.3 gerado a partir de uma planta já lida no módulo Plantas.

Sem IA: o modelo é construído de forma determinística a partir da geometria validada pelo
utilizador (estrutura detetada/corrigida + divisões + calibração). Os GlobalId são estáveis entre
gerações, para que cálculos, orçamentos e comentários fiquem ligados aos mesmos elementos.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from core.db import db
from core.security import current_user
from engines.nom_fichier import content_disposition, nom_document, sujet_plan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bim", tags=["bim"])

IFC_MEDIA_TYPE = "application/x-step"


def _bim():
    try:
        from engines import bim_core  # noqa: PLC0415
    except ImportError as e:  # ifcopenshell em falta no servidor
        logger.error("bim_core indisponível: %s", e)
        raise HTTPException(503, "Módulo BIM indisponível neste servidor (ifcopenshell não instalado).") from e
    return bim_core


async def _load_model(plan_id: str, page_index: int, user: dict, params: dict):
    bim = _bim()
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structure": 1, "calibrations": 1, "rooms": 1, "filename": 1, "name": 1,
         "original_filename": 1, "project_name": 1, "cad_import": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    calib = (p.get("calibrations") or {}).get(str(page_index)) or {}
    ppm = calib.get("pixels_per_meter")
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index", 0) == page_index]
    try:
        model = bim.from_takeoff(structure, ppm, rooms=rooms, plan_id=plan_id, page_index=page_index,
                                 storey_name=f"Piso {page_index}", params=params)
    except bim.ModelError as e:
        raise HTTPException(422, str(e)) from e
    return bim, model, p


def _params(wall_height, voile_ep, cloison_ep, dalle_ep, poutre_l, poutre_h) -> dict:
    return {"wall_height": wall_height, "voile_ep": voile_ep, "cloison_ep": cloison_ep,
            "dalle_ep": dalle_ep, "poutre_l": poutre_l, "poutre_h": poutre_h}


def _build(bim, model, project_name: str):
    f = bim.build_ifc(model, project_name=project_name)
    errors = bim.validate(f)
    return f, errors


_Q = {
    "wall_height": Query(None, gt=1.5, le=12, description="Pé-direito estrutural (m)"),
    "voile_ep": Query(None, gt=0.05, le=1.0, description="Espessura das paredes resistentes (m)"),
    "cloison_ep": Query(None, gt=0.03, le=0.5, description="Espessura das divisórias (m)"),
    "dalle_ep": Query(None, gt=0.05, le=1.0, description="Espessura da laje quando não está na planta (m)"),
    "poutre_l": Query(None, gt=0.1, le=1.5, description="Largura das vigas (m)"),
    "poutre_h": Query(None, gt=0.1, le=2.5, description="Altura das vigas (m)"),
}


@router.get("/takeoffs/{plan_id}/{page_index}/summary")
async def bim_summary(plan_id: str, page_index: int,
                      wall_height: float | None = _Q["wall_height"], voile_ep: float | None = _Q["voile_ep"],
                      cloison_ep: float | None = _Q["cloison_ep"], dalle_ep: float | None = _Q["dalle_ep"],
                      poutre_l: float | None = _Q["poutre_l"], poutre_h: float | None = _Q["poutre_h"],
                      user=Depends(current_user)) -> dict:
    """Elementos IFC (GUID, classe, quantidades), totais e avisos — sem descarregar o ficheiro."""
    params = _params(wall_height, voile_ep, cloison_ep, dalle_ep, poutre_l, poutre_h)
    bim, model, p = await _load_model(plan_id, page_index, user, params)
    f, errors = await run_in_threadpool(_build, bim, model, sujet_plan(p) or "Projeto ConstruPilot")
    summary = bim.summarize(f)
    return {"plan_id": plan_id, "page_index": page_index, "schema": bim.SCHEMA,
            "params": model.params, "counts": model.counts(), "warnings": model.warnings,
            "valid": not errors, "validation_errors": errors[:50], **summary}


@router.get("/takeoffs/{plan_id}/{page_index}/ifc")
async def bim_ifc(plan_id: str, page_index: int,
                  wall_height: float | None = _Q["wall_height"], voile_ep: float | None = _Q["voile_ep"],
                  cloison_ep: float | None = _Q["cloison_ep"], dalle_ep: float | None = _Q["dalle_ep"],
                  poutre_l: float | None = _Q["poutre_l"], poutre_h: float | None = _Q["poutre_h"],
                  inline: bool = False, user=Depends(current_user)) -> Response:
    """Ficheiro IFC 4.3 do piso (abre no Revit, Archicad, BIMcollab, Solibri e no visualizador ConstruPilot)."""
    params = _params(wall_height, voile_ep, cloison_ep, dalle_ep, poutre_l, poutre_h)
    bim, model, p = await _load_model(plan_id, page_index, user, params)
    subject = sujet_plan(p)
    f, errors = await run_in_threadpool(_build, bim, model, subject or "Projeto ConstruPilot")
    if errors:
        # Nunca entregar um IFC fora do esquema: seria rejeitado pelos programas dos parceiros.
        logger.error("IFC inválido plan=%s page=%s: %s", plan_id, page_index, errors[:5])
        raise HTTPException(500, "O modelo IFC gerado não passou a validação do esquema.")
    data = f.to_string().encode("utf-8")
    name = nom_document("Modelo-BIM", subject, ext="ifc", ref=f"piso-{page_index}")
    return Response(content=data, media_type=IFC_MEDIA_TYPE, headers={
        "Content-Disposition": content_disposition(name, inline=inline),
        "Cache-Control": "no-store"})
