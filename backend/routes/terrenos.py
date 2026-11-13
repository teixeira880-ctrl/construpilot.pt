"""Terrenos — identificar, medir e analisar prédios sobre fontes oficiais (DGT, eBUPi) e exportar para o BUPi."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.terrenos_pt import analise as A
from engines.terrenos_pt import bupi as B
from engines.terrenos_pt import geometria as GM

log = logging.getLogger(__name__)
router = APIRouter(prefix="/terrenos", tags=["terrenos"])
MAX_TERRENOS = 500


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TerrenoIn(BaseModel):
    nome: str = Field(default="", max_length=120)
    anel_latlon: List[List[float]] = Field(..., min_length=3, max_length=5000)
    origem: str = Field(default="desenho", pattern="^(desenho|gps|importacao|cadastro|rgg)$")
    notas: str = Field(default="", max_length=2000)
    artigo_matricial: str = Field(default="", max_length=60)


class TerrenoPatch(BaseModel):
    nome: Optional[str] = Field(default=None, max_length=120)
    anel_latlon: Optional[List[List[float]]] = Field(default=None, min_length=3, max_length=5000)
    origem: Optional[str] = Field(default=None, pattern="^(desenho|gps|importacao|cadastro|rgg)$")
    notas: Optional[str] = Field(default=None, max_length=2000)
    artigo_matricial: Optional[str] = Field(default=None, max_length=60)


class AnelIn(BaseModel):
    anel_latlon: List[List[float]] = Field(..., min_length=3, max_length=5000)


def _medir(anel) -> Dict[str, Any]:
    try:
        return GM.medir(anel)
    except GM.GeometriaInvalida as e:
        raise HTTPException(422, str(e))


async def _owned(tid: str, uid: str) -> Dict[str, Any]:
    d = await db.terrenos.find_one({"terreno_id": tid, "user_id": uid}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Terreno não encontrado.")
    return d


def _resumo(d: Dict[str, Any]) -> Dict[str, Any]:
    a = d.get("analise") or {}
    caop = ((a.get("caop") or {}).get("data") or {}).get("principal") or {}
    return {k: d.get(k) for k in ("terreno_id", "nome", "origem", "area_m2", "perimetro_m", "centroide", "criado", "atualizado",
                                  "artigo_matricial", "analisado_em")} | {
        "freguesia": caop.get("freguesia"), "concelho": caop.get("concelho"),
        "alertas_criticos": sum(1 for x in a.get("alertas", []) if x.get("nivel") == "critico"),
    }


@router.post("/medir")
async def medir(body: AnelIn, user=Depends(current_user)) -> dict:
    """Área, perímetro e vértices em PT-TM06 (para o painel em direto enquanto desenha)."""
    return _medir(body.anel_latlon)


@router.get("")
async def listar(user=Depends(current_user)) -> dict:
    cur = db.terrenos.find({"user_id": user["user_id"]}, {"_id": 0}).sort("atualizado", -1).limit(MAX_TERRENOS)
    return {"terrenos": [_resumo(d) async for d in cur]}


@router.post("")
async def criar(body: TerrenoIn, user=Depends(current_user)) -> dict:
    m = _medir(body.anel_latlon)
    if await db.terrenos.count_documents({"user_id": user["user_id"]}) >= MAX_TERRENOS:
        raise HTTPException(409, f"Limite de {MAX_TERRENOS} terrenos atingido.")
    now = _now()
    d = {"terreno_id": uuid.uuid4().hex[:16], "user_id": user["user_id"], "nome": body.nome.strip() or "Terreno sem nome",
         "origem": body.origem, "notas": body.notas, "artigo_matricial": body.artigo_matricial.strip(),
         "anel_latlon": m["anel_latlon"], "area_m2": m["area_m2"], "perimetro_m": m["perimetro_m"], "centroide": m["centroide"],
         "geometria": m, "analise": None, "analisado_em": None, "criado": now, "atualizado": now}
    await db.terrenos.insert_one(dict(d))
    return d


@router.get("/{tid}")
async def obter(tid: str, user=Depends(current_user)) -> dict:
    return await _owned(tid, user["user_id"])


@router.put("/{tid}")
async def atualizar(tid: str, body: TerrenoPatch, user=Depends(current_user)) -> dict:
    d = await _owned(tid, user["user_id"])
    upd: Dict[str, Any] = {k: v for k, v in body.model_dump().items() if v is not None and k != "anel_latlon"}
    if body.anel_latlon is not None:
        m = _medir(body.anel_latlon)
        upd.update(anel_latlon=m["anel_latlon"], area_m2=m["area_m2"], perimetro_m=m["perimetro_m"], centroide=m["centroide"],
                   geometria=m, analise=None, analisado_em=None)     # limites mudaram: a análise anterior deixa de valer
    upd["atualizado"] = _now()
    await db.terrenos.update_one({"terreno_id": tid, "user_id": user["user_id"]}, {"$set": upd})
    return {**d, **upd}


@router.delete("/{tid}")
async def apagar(tid: str, user=Depends(current_user)) -> dict:
    r = await db.terrenos.delete_one({"terreno_id": tid, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Terreno não encontrado.")
    return {"ok": True}


@router.post("/{tid}/analise")
async def analisar(tid: str, user=Depends(current_user)) -> dict:
    d = await _owned(tid, user["user_id"])
    try:
        res = await A.analisar(d["anel_latlon"])
    except GM.GeometriaInvalida as e:
        raise HTTPException(422, str(e))
    now = _now()
    await db.terrenos.update_one({"terreno_id": tid, "user_id": user["user_id"]},
                                 {"$set": {"analise": res, "analisado_em": now, "atualizado": now}})
    return {"analise": res, "analisado_em": now}


@router.post("/importar")
async def importar(ficheiro: UploadFile = File(...), user=Depends(current_user)) -> dict:
    """Lê KML/KMZ/GPX/GeoJSON e devolve os polígonos encontrados (não grava: o utilizador confirma no mapa)."""
    dados = await ficheiro.read(GM.MAX_FICHEIRO + 1)
    try:
        return {"poligonos": GM.ler_ficheiro(ficheiro.filename or "", dados)}
    except GM.GeometriaInvalida as e:
        raise HTTPException(422, str(e))


_MIME = {"kml": "application/vnd.google-earth.kml+xml", "geojson": "application/geo+json", "csv": "text/csv; charset=utf-8"}


@router.get("/{tid}/exportar.{fmt}")
async def exportar(tid: str, fmt: str, user=Depends(current_user)):
    if fmt not in _MIME:
        raise HTTPException(404, "Formato não suportado (kml, geojson, csv).")
    d = await _owned(tid, user["user_id"])
    anel = d["anel_latlon"]
    nome = d.get("nome") or "Terreno"
    desc = f"Área {d.get('area_m2', 0):.1f} m² — PT-TM06/ETRS89 — ConstruPilot"
    if fmt == "kml":
        body = GM.para_kml(nome, anel, desc)
    elif fmt == "geojson":
        body = GM.para_geojson(nome, anel, {"area_m2": d.get("area_m2"), "artigo_matricial": d.get("artigo_matricial") or None})
    else:
        body = GM.para_csv_tm06(anel)
    seguro = "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)[:60] or "terreno"
    return Response(content=body.encode("utf-8"), media_type=_MIME[fmt],
                    headers={"Content-Disposition": f'attachment; filename="{seguro}.{fmt}"'})


@router.get("/consulta/ponto")
async def ponto(lat: float, lon: float, user=Depends(current_user)) -> dict:
    """Clique no mapa: RGG do BUPi e prédio cadastrado nesse ponto (com o limite oficial, se existir)."""
    import asyncio
    from engines.urbanismo_pt.auto import geo as G
    if not (GM.PT_LAT[0] <= lat <= GM.PT_LAT[1] and GM.PT_LON[0] <= lon <= GM.PT_LON[1]):
        raise HTTPException(422, "Ponto fora de Portugal.")
    from engines.terrenos_pt import rgg_limite as RL
    rgg, cad, lim = await asyncio.gather(B.rgg_no_ponto(lat, lon), G.cadastro(lat, lon), RL.limite_no_ponto(lat, lon))
    cad_out = None
    if cad.get("ok"):
        ring = cad["data"]["anel_lonlat"]
        cad_out = {"anel_latlon": [[p[1], p[0]] for p in ring], "atributos": cad["data"]["props"], "fonte": cad["fonte"],
                   "url": cad["url"]}
    rgg_lim = None
    if lim.get("ok"):
        rgg_lim = {"anel_latlon": lim["data"]["anel_latlon"], "area_m2": lim["data"]["area_m2"],
                   "sobreposicoes": lim["data"]["sobreposicoes"], "fonte": lim["fonte"], "nota": lim.get("nota")}
    return {"rgg": rgg, "rgg_limite": rgg_lim, "rgg_limite_nota": None if lim.get("ok") else lim.get("nota"),
            "cadastro": cad_out, "cadastro_nota": None if cad.get("ok") else cad.get("nota")}
