"""Rotas BIM — modelo IFC 4.3 gerado a partir de uma planta já lida no módulo Plantas.

Sem IA: o modelo é construído de forma determinística a partir da geometria validada pelo
utilizador (estrutura detetada/corrigida + divisões + calibração). Os GlobalId são estáveis entre
gerações, para que cálculos, orçamentos e comentários fiquem ligados aos mesmos elementos.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from functools import partial
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.nom_fichier import content_disposition, nom_document, sujet_plan
from engines.plan_verified_floor import PAGE_FIELDS, verified_structure

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bim", tags=["bim"])

IFC_MEDIA_TYPE = "application/x-step"
MAX_IFC_BYTES = 80 * 1024 * 1024


def _bim():
    try:
        from engines import bim_core
    except ImportError as e:  # ifcopenshell em falta no servidor
        logger.error("bim_core indisponível: %s", e)
        raise HTTPException(503, "Módulo BIM indisponível neste servidor (ifcopenshell não instalado).") from e
    return bim_core


async def _load_model(plan_id: str, page_index: int, user: dict, params: dict):
    bim = _bim()
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structure": 1, "calibrations": 1, "rooms": 1, "filename": 1, "name": 1,
         "original_filename": 1, "project_name": 1, "cad_import": 1, "kind": 1,
         **{f"pages.{name}": 1 for name in PAGE_FIELDS}})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    calib = (p.get("calibrations") or {}).get(str(page_index)) or {}
    ppm = calib.get("pixels_per_meter")
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index", 0) == page_index]
    corrected = verified_structure(p, page_index)
    options = dict(rooms=rooms, plan_id=plan_id, page_index=page_index, storey_name=f"Piso {page_index}", params=params)
    try:
        model = bim.from_takeoff(corrected, ppm, origin_structure=structure, **options)
    except bim.ModelError as e:
        raise HTTPException(422, str(e)) from e
    # Cópia editada no editor BIM (opções ou prompt): passa a ser o modelo deste piso até ser reposta a planta lida.
    saved = await db.bim_models.find_one({"plan_id": plan_id, "page_index": page_index, "user_id": user["user_id"]}, {"_id": 0, "model": 1})
    if saved and saved.get("model"):
        from engines.bim_core import edicao
        saved_model = edicao.de_dict(saved["model"])
        model = (edicao.reconcile_pdf_outline(saved_model, bim.from_takeoff(structure, ppm, **options), model)
                 if corrected.get("verified_outline") else saved_model)
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


@router.get("/takeoffs/{plan_id}/{page_index}/analysis")
async def bim_analysis(plan_id: str, page_index: int,
                       wall_height: float | None = _Q["wall_height"], voile_ep: float | None = _Q["voile_ep"],
                       cloison_ep: float | None = _Q["cloison_ep"], dalle_ep: float | None = _Q["dalle_ep"],
                       poutre_l: float | None = _Q["poutre_l"], poutre_h: float | None = _Q["poutre_h"],
                       imposed_kn_m2: float | None = Query(None, ge=0, le=20, description="Sobrecarga (kN/m²)"),
                       finishes_kn_m2: float | None = Query(None, ge=0, le=10, description="Revestimentos (kN/m²)"),
                       partitions_kn_m2: float | None = Query(None, ge=0, le=5, description="Divisórias (kN/m²)"),
                       fck: float | None = Query(None, ge=20, le=50, description="fck do betão (MPa)"),
                       user=Depends(current_user)) -> dict:
    """Pré-dimensionamento do pórtico (vigas e pilares) para cargas verticais, por elemento IFC (GUID)."""
    from engines.bim_core import analysis as A

    params = _params(wall_height, voile_ep, cloison_ep, dalle_ep, poutre_l, poutre_h)
    bim, model, _ = await _load_model(plan_id, page_index, user, params)
    loads = {"imposed_kn_m2": imposed_kn_m2, "finishes_kn_m2": finishes_kn_m2,
             "partitions_kn_m2": partitions_kn_m2, "fck": fck}
    try:
        result = await run_in_threadpool(A.analyze, model, loads)
    except A.AnalysisError as e:
        raise HTTPException(422, str(e)) from e
    except ImportError as e:
        raise HTTPException(503, "Solver estrutural indisponível neste servidor (PyNiteFEA não instalado).") from e
    return {"plan_id": plan_id, "page_index": page_index, **result}


# ------------------------------------------------------------------------------------------------ editor do modelo
class ModelSelection(BaseModel):
    grupo: Literal["walls", "openings", "slabs", "columns", "beams", "footings", "spaces"]
    id: str = Field(min_length=1, max_length=160)


class ModelOps(BaseModel):
    ops: list[dict] = Field(default_factory=list, max_length=200)
    texto: str = Field(default="", max_length=4000)
    selecao: ModelSelection | None = None


def _edit_key(plan_id: str, page_index: int, user: dict) -> dict:
    return {"plan_id": plan_id, "page_index": page_index, "user_id": user["user_id"]}


async def _interpret_free_text(frase, model, selection):
    from engines.bet_core.reader import PROVIDERS, _provider_order
    from engines.bim_core import prompt

    names = [name for name in _provider_order() if name in ("claude", "openai")] or ["claude", "openai"]
    models = {"claude": os.environ.get("ANTHROPIC_MODEL_HAIKU", "claude-haiku-4-5-20251001"),
              "openai": os.environ.get("OPENAI_MODEL_FAST", "gpt-4o-mini")}
    return await prompt.interpret(frase, model, selection, [partial(PROVIDERS[name], model=models[name]) for name in names])


@router.get("/takeoffs/{plan_id}/{page_index}/modelo")
async def bim_model(plan_id: str, page_index: int, user=Depends(current_user)) -> dict:
    """Modelo editável do piso (paredes, vãos, lajes…) em JSON: o da planta lida, ou a cópia já editada."""
    from engines.bim_core import edicao

    _, model, _ = await _load_model(plan_id, page_index, user, _params(None, None, None, None, None, None))
    doc = await db.bim_models.find_one(_edit_key(plan_id, page_index, user), {"_id": 0, "historico": 1, "anteriores": 1}) or {}
    return {"modelo": edicao.para_dict(model), "editado": bool(doc), "historico": (doc.get("historico") or [])[-50:],
            "pode_desfazer": bool(doc.get("anteriores"))}


@router.post("/takeoffs/{plan_id}/{page_index}/modelo/ops")
async def bim_model_ops(plan_id: str, page_index: int, body: ModelOps, user=Depends(current_user)) -> dict:
    """Aplica operações de edição (lista `ops`) e/ou frases correntes (`texto`) ao modelo do piso e guarda o resultado.
    Cada operação recusada volta com o motivo; as frases não percebidas voltam em `nao_percebido`."""
    from engines.bim_core import edicao, prompt

    bim, model, plan = await _load_model(plan_id, page_index, user, _params(None, None, None, None, None, None))
    selecao = body.selecao.model_dump() if body.selecao else None
    frases, resto, esclarecimentos = edicao.interpretar_selecao(body.texto, model, selecao)
    interpretado_ia = False
    if resto and not (esclarecimentos or body.ops):
        alternativas, perguntas = await _interpret_free_text(body.texto, model, selecao)
        if alternativas or perguntas:
            frases, resto, esclarecimentos = alternativas, [], perguntas
            interpretado_ia = True
    ops = list(body.ops) + frases
    if not ops and not resto and not esclarecimentos:
        raise HTTPException(422, "Indique operações ou um pedido em texto.")
    novo, feito, erros = edicao.aplicar(model, ops)
    if interpretado_ia and erros:
        return {"modelo": edicao.para_dict(model), "feito": [], "erros": erros, "esclarecimentos": esclarecimentos,
                "nao_percebido": resto, "interpretado_ia": True, "editado": False}
    if feito and any(op.get("op") in prompt.GEOMETRY_OPS for op in ops):
        try:
            _, ifc_errors = await run_in_threadpool(_build, bim, novo, sujet_plan(plan) or "Projeto ConstruPilot")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to verify edited BIM for plan=%s page=%s", plan_id, page_index)
            ifc_errors = ["build"]
        if ifc_errors:
            return {"modelo": edicao.para_dict(model), "feito": [],
                    "erros": ["A alteração não passou a verificação IFC. A edição anterior foi mantida."],
                    "esclarecimentos": esclarecimentos, "nao_percebido": resto, "interpretado_ia": interpretado_ia, "editado": False}
    if feito:
        key = _edit_key(plan_id, page_index, user)
        doc = await db.bim_models.find_one(key, {"_id": 0, "anteriores": 1, "historico": 1}) or {}
        agora = datetime.now(timezone.utc).isoformat()
        await db.bim_models.update_one(key, {"$set": {
            "model": edicao.para_dict(novo), "updated_at": agora,
            "anteriores": ((doc.get("anteriores") or []) + [edicao.para_dict(model)])[-20:],
            "historico": ((doc.get("historico") or []) + [{"quando": agora, "feito": feito}])[-200:]}}, upsert=True)
    return {"modelo": edicao.para_dict(novo), "feito": feito, "erros": erros,
            "esclarecimentos": esclarecimentos, "nao_percebido": resto,
            "interpretado_ia": interpretado_ia, "editado": bool(feito)}


@router.post("/takeoffs/{plan_id}/{page_index}/modelo/desfazer")
async def bim_model_undo(plan_id: str, page_index: int, user=Depends(current_user)) -> dict:
    """Volta ao modelo anterior à última edição (até 20 passos)."""
    key = _edit_key(plan_id, page_index, user)
    doc = await db.bim_models.find_one(key, {"_id": 0, "anteriores": 1}) or {}
    anteriores = doc.get("anteriores") or []
    if not anteriores:
        raise HTTPException(409, "Não há edições para desfazer.")
    agora = datetime.now(timezone.utc).isoformat()
    doc_h = await db.bim_models.find_one(key, {"_id": 0, "historico": 1}) or {}
    await db.bim_models.update_one(key, {"$set": {
        "model": anteriores[-1], "anteriores": anteriores[:-1], "updated_at": agora,
        "historico": ((doc_h.get("historico") or []) + [{"quando": agora, "feito": ["Última edição desfeita."]}])[-200:]}})
    return {"modelo": anteriores[-1], "pode_desfazer": len(anteriores) > 1}


@router.delete("/takeoffs/{plan_id}/{page_index}/modelo")
async def bim_model_reset(plan_id: str, page_index: int, user=Depends(current_user)) -> dict:
    """Apaga a cópia editada: o piso volta a ser o da planta lida."""
    r = await db.bim_models.delete_one(_edit_key(plan_id, page_index, user))
    return {"reposto": bool(r.deleted_count)}


def _analyze_ifc(data: bytes, storey: int | None, loads: dict) -> dict:
    from engines.bim_core import ifc_reader as IR

    f = IR.open_ifc(data)
    model, storeys, result = IR.analyze_storey(f, storey, loads)
    st = storeys[model.page_index]
    return {"origin": "ifc", "schema": f.schema, "storey": st, "storeys": storeys,
            "model_counts": model.counts(), "model_warnings": model.warnings, **result}


@router.post("/ifc/analysis")
async def bim_ifc_analysis(file: UploadFile = File(..., description="Ficheiro IFC (Revit, Archicad, Tekla…)"),
                           storey: int | None = Query(None, ge=0, description="Índice do piso; omisso = piso com mais vigas e pilares"),
                           imposed_kn_m2: float | None = Query(None, ge=0, le=20, description="Sobrecarga (kN/m²)"),
                           finishes_kn_m2: float | None = Query(None, ge=0, le=10, description="Revestimentos (kN/m²)"),
                           partitions_kn_m2: float | None = Query(None, ge=0, le=5, description="Divisórias (kN/m²)"),
                           fck: float | None = Query(None, ge=20, le=50, description="fck do betão (MPa)"),
                           user=Depends(current_user)) -> dict:
    """Pré-dimensionamento do pórtico de um piso de um IFC externo; resultados pelos GlobalId do próprio ficheiro.

    O ficheiro não é guardado: é lido em memória, calculado e descartado."""
    bim = _bim()
    data = await file.read(MAX_IFC_BYTES + 1)
    if len(data) > MAX_IFC_BYTES:
        raise HTTPException(413, "IFC demasiado grande para o cálculo em linha (máx. 80 MB).")
    from engines.bim_core import analysis as A

    loads = {"imposed_kn_m2": imposed_kn_m2, "finishes_kn_m2": finishes_kn_m2,
             "partitions_kn_m2": partitions_kn_m2, "fck": fck}
    try:
        return await run_in_threadpool(_analyze_ifc, data, storey, loads)
    except (bim.ModelError, A.AnalysisError) as e:
        raise HTTPException(422, str(e)) from e
    except ImportError as e:
        raise HTTPException(503, "Solver estrutural indisponível neste servidor.") from e
