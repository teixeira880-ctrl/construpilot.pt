"""Geometria v3 nas plantas: leitura automática das divisões e paredes, confiança por divisão, correções do utilizador.

  POST /api/takeoffs/{plan_id}/geometria?page_index=0   → análise completa da página (guardada em `geometria_v3`)
  GET  /api/takeoffs/{plan_id}/geometria?page_index=0   → última análise guardada
  POST /api/takeoffs/{plan_id}/geometria/correcao       → correção do utilizador (guardada também como dado de treino)
  POST /api/takeoffs/{plan_id}/geometria/aplicar        → as divisões escolhidas passam a divisões da planta (rooms)
  GET  /api/admin/geometria/correcoes                   → exportação das correções (admin) para treinar o modelo

Nada é publicado nem orçamentado automaticamente: a análise propõe, o utilizador aplica.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user, current_user
from routes.plans_common import _now, router

logger = logging.getLogger(__name__)
admin_router = APIRouter(tags=["admin"], prefix="/admin/geometria")


async def _pagina_completa(p: dict, page_index: int, user_id: str) -> dict:
    """Página com TODOS os traços: os documentos guardados cortam os vetores a 8000 (limite Mongo); relemos a fonte."""
    page = dict(p["pages"][page_index])
    kind = p.get("kind")
    try:
        if kind == "pdf" and (page.get("vectors_truncated") or not page.get("vectors")):
            from engines.plan_refresh import extract_page_geometry
            from engines.plan_sources import load_plan_source
            src = await load_plan_source(db, p["plan_id"], user_id)
            if src:
                import base64
                geo = await asyncio.to_thread(extract_page_geometry, base64.b64decode(src["data_b64"]), page_index, float(page.get("dpi") or 72) / 72)
                page.update({k: v for k, v in geo.items() if k in ("vectors", "text_blocks", "pdf_dimensions")})
        elif kind == "dxf" and page.get("vectors_truncated"):
            from engines.plan_dxf import process_dxf
            from engines.plan_sources import load_cad_source
            filename = p.get("filename") or "plan.dxf"
            data = await load_cad_source(db, p["plan_id"], user_id, "converted_dxf" if filename.lower().endswith(".dwg") else "original")
            if data:
                parsed = await asyncio.to_thread(process_dxf, data, filename.rsplit(".", 1)[0] + ".dxf")
                page.update({k: v for k, v in parsed["pages"][0].items() if k in ("vectors", "dxf_dimensions", "text_blocks")})
    except HTTPException:
        raise
    except Exception:  # a página guardada continua utilizável: a análise indica os traços em falta
        logger.exception("geometria: releitura da fonte falhou (%s)", p.get("plan_id"))
    return page


@router.post("/{plan_id}/geometria")
async def geometria_analisar(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    from engines.geometria.servico import analisar_pagina
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "plan_id": 1, "kind": 1, "filename": 1, "pages": 1, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    if page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Página desconhecida")
    page = await _pagina_completa(p, page_index, user["user_id"])
    calib = (p.get("calibrations") or {}).get(str(page_index))
    try:
        res = await asyncio.to_thread(analisar_pagina, page, p.get("kind") or "pdf", calib)
    except Exception:
        logger.exception("geometria: análise falhou (%s p%s)", plan_id, page_index)
        raise HTTPException(500, "Análise geométrica impossível nesta página")
    res["page_index"] = page_index
    res["analisado_em"] = _now()
    await db.plans_takeoff.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                      {"$set": {f"geometria_v3.{page_index}": res}})
    return res


@router.get("/{plan_id}/geometria")
async def geometria_ultima(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, f"geometria_v3.{page_index}": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    res = (p.get("geometria_v3") or {}).get(str(page_index))
    if not res:
        raise HTTPException(404, "Ainda sem análise geométrica nesta página")
    return res


class CorrecaoIn(BaseModel):
    page_index: int = Field(0, ge=0)
    tipo: Literal["falta", "nao_existe", "forma_errada", "mal_identificado", "area_errada", "escala_errada"]
    divisao_id: str | None = Field(None, max_length=16)
    nome_correto: str | None = Field(None, max_length=120)
    area_correta_m2: float | None = Field(None, gt=0, lt=100000)
    poligono_px: list[list[float]] | None = Field(None, max_length=400)
    comentario: str | None = Field(None, max_length=1000)


@router.post("/{plan_id}/geometria/correcao")
async def geometria_correcao(plan_id: str, body: CorrecaoIn, user=Depends(current_user)):
    """A correção fica junto da planta e numa coleção de treino (sem a imagem: só a referência e a geometria)."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "kind": 1, f"geometria_v3.{body.page_index}": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    analise = (p.get("geometria_v3") or {}).get(str(body.page_index)) or {}
    lida = next((d for d in analise.get("divisoes", []) if d.get("id") == body.divisao_id), None) if body.divisao_id else None
    if body.divisao_id and not lida:
        raise HTTPException(404, "Divisão desconhecida nesta análise")
    reg = {"correcao_id": secrets.token_hex(8), "plan_id": plan_id, "user_id": user["user_id"], "page_index": body.page_index,
           "tipo": body.tipo, "divisao_id": body.divisao_id, "nome_correto": body.nome_correto,
           "area_correta_m2": body.area_correta_m2, "poligono_px": body.poligono_px, "comentario": body.comentario,
           "lida": {k: lida.get(k) for k in ("nome", "area_m2", "poligono_px", "nivel")} if lida else None,
           "fonte": analise.get("fonte"), "versao": analise.get("versao"), "kind": p.get("kind"),
           "escala_u_por_m": (analise.get("escala") or {}).get("u_por_m"), "criado_em": _now()}
    await db.geometria_correcoes.insert_one(dict(reg))
    await db.plans_takeoff.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                      {"$push": {f"geometria_v3_correcoes.{body.page_index}": {k: v for k, v in reg.items() if k != "user_id"}}})
    return {"ok": True, "correcao_id": reg["correcao_id"]}


class AplicarIn(BaseModel):
    page_index: int = Field(0, ge=0)
    divisoes: list[str] = Field(default_factory=list, max_length=500)
    substituir_automaticas: bool = True


@router.post("/{plan_id}/geometria/aplicar")
async def geometria_aplicar(plan_id: str, body: AplicarIn, user=Depends(current_user)):
    """Cria as divisões da planta (rooms) a partir da análise, com origem e confiança guardadas em cada uma.
    Só substitui as divisões criadas antes por esta mesma função; as divisões desenhadas à mão ficam intactas."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "rooms": 1, "calibrations": 1, f"geometria_v3.{body.page_index}": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    analise = (p.get("geometria_v3") or {}).get(str(body.page_index))
    if not analise or not analise.get("ok"):
        raise HTTPException(409, "Analise primeiro a página")
    if (analise.get("escala") or {}).get("estado") in ("conflito", "desconhecida"):
        raise HTTPException(409, "Escala por confirmar: calibre a página antes de aplicar as divisões")
    from engines import geometry as G
    ppm = analise.get("px_por_m")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    novo_calib = None
    if not calib:
        if not ppm:
            raise HTTPException(409, "Escala por confirmar: calibre a página antes de aplicar as divisões")
        novo_calib = {"pixels_per_meter": ppm, "meters_per_pixel": 1 / ppm, "source": "geometria_v3",
                      "escala_estado": (analise.get("escala") or {}).get("estado"), "created_at": _now()}
        calib = novo_calib
    elif ppm and abs(calib["pixels_per_meter"] - ppm) / ppm > .015:
        raise HTTPException(409, "A calibração da página difere da escala lida no desenho (> 1,5 %): reanalise ou recalibre")
    escolhidas = [d for d in analise["divisoes"] if not body.divisoes or d["id"] in body.divisoes]
    rooms = [r for r in (p.get("rooms") or []) if not (body.substituir_automaticas and r.get("origem") == "geometria_v3"
                                                        and r.get("page_index", 0) == body.page_index)]
    for d in escolhidas:
        m = G.room_measurements(d["poligono_px"], calib["pixels_per_meter"], 2.5)
        rooms.append({"room_id": "room_" + secrets.token_hex(4), "page_index": body.page_index, "name": d["nome"],
                      "points": d["poligono_px"], "openings": [], "surface_m2": m["surface_m2"], "perimeter_m": m["perimeter_m"],
                      "ceiling_area_m2": m["ceiling_area_m2"], "ceiling_height_m": m["ceiling_height_m"], "floor_thickness_m": .15,
                      "volume_m3": round(m["surface_m2"] * 2.5, 3), "wall_area_gross_m2": m["wall_area_gross_m2"],
                      "wall_area_net_m2": m["wall_area_gross_m2"], "openings_area_m2": 0.0,
                      "origem": "geometria_v3", "confianca": d["nivel"], "confianca_motivos": d.get("motivos", []),
                      "versao_motor": analise.get("versao"), "created_at": _now()})
    upd = {"rooms": rooms, "updated_at": _now()}
    if novo_calib:
        upd[f"calibrations.{body.page_index}"] = novo_calib
    await db.plans_takeoff.update_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"$set": upd})
    from routes.plans_common import _snapshot
    await _snapshot(plan_id, user["user_id"], "geometria_v3_aplicar", {"divisoes": len(escolhidas)})
    return {"ok": True, "aplicadas": len(escolhidas), "total_divisoes": len(rooms), "calibracao_criada": bool(novo_calib)}


@admin_router.get("/correcoes")
async def geometria_correcoes_export(limit: int = Query(500, ge=1, le=5000), _=Depends(admin_user)):
    """Correções acumuladas (sem dados pessoais além do id do plano) — o conjunto de treino do futuro modelo."""
    itens = [c async for c in db.geometria_correcoes.find({}, {"_id": 0, "user_id": 0}).sort("criado_em", -1).limit(limit)]
    por_tipo = {}
    for c in itens:
        por_tipo[c["tipo"]] = por_tipo.get(c["tipo"], 0) + 1
    return {"total": len(itens), "por_tipo": por_tipo, "correcoes": itens}
