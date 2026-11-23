"""Rotas do Estúdio de Projeto — modelo único do edifício ligado a um processo de licenciamento.

GET    /estudio-projeto/processos/{pid}             modelo (guardado, ou criado a partir do processo) + tudo o que deriva dele
PUT    /estudio-projeto/processos/{pid}             guarda o modelo editado
DELETE /estudio-projeto/processos/{pid}             repõe o modelo a partir do processo
POST   /estudio-projeto/derivar                     modelo → derivado (edição em direto, sem guardar)
POST   /estudio-projeto/desenho.svg                 modelo → planta | alçado | corte em SVG (edição em direto)
GET    /estudio-projeto/processos/{pid}/pranchas.pdf   plantas, alçados e cortes do modelo guardado (carimbo do processo)
GET    /estudio-projeto/processos/{pid}/medicoes.csv   medições geométricas (paredes, camadas, vãos, divisões, lajes, cobertura)

O modelo fica numa coleção própria (`urbanismo_estudios`): o processo de licenciamento não é alterado por estas rotas.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import estudio_projeto as EP
from engines.estudio_projeto import desenhos as D
from engines.estudio_projeto.modelo import COBERTURAS, TIPOS_BASE, VAO_BASE
from engines.nom_fichier import content_disposition, nom_document
from routes import urbanismo_auto as UA

router = APIRouter(prefix="/estudio-projeto", tags=["estudio-projeto"])


class ModeloIn(BaseModel):
    modelo: Dict[str, Any]


class DesenhoIn(BaseModel):
    modelo: Dict[str, Any]
    tipo: str = Field(default="planta", pattern="^(planta|alcado|corte)$")
    piso: int = Field(default=0, ge=0, le=5)
    lado: str = Field(default="frente", pattern="^(frente|tardoz|esquerda|direita)$")
    eixo: str = Field(default="x", pattern="^(x|y)$")
    pos: Optional[float] = Field(default=None, ge=-500, le=500)


def _limpo(modelo: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return EP.normalizar(modelo)
    except EP.ErroModelo as e:
        raise HTTPException(422, str(e))


async def _carregar(pid: str, uid: str) -> Dict[str, Any]:
    d = await UA._owned(pid, uid)
    g = await db.urbanismo_estudios.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if g and g.get("modelo"):
        try:
            return {"processo": d, "modelo": EP.normalizar(g["modelo"]), "origem": "guardado", "avisos_origem": [],
                    "updated_at": g.get("updated_at")}
        except EP.ErroModelo:
            pass          # modelo guardado ilegível: volta ao do processo em vez de falhar
    try:
        r = EP.de_processo(d)
    except EP.ErroModelo as e:
        raise HTTPException(409, str(e))
    return {"processo": d, "modelo": r["modelo"], "origem": "processo", "avisos_origem": r["avisos"], "updated_at": None}


def _catalogo() -> Dict[str, Any]:
    from engines.estudio_projeto import materiais as MAT
    return {"tipos_parede": TIPOS_BASE, "vaos": VAO_BASE, "coberturas": list(COBERTURAS), **MAT.catalogo()}


@router.get("/processos/{pid}")
async def obter(pid: str, user=Depends(current_user)) -> dict:
    c = await _carregar(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    return {"modelo": c["modelo"], "derivado": der, "origem": c["origem"], "avisos_origem": c["avisos_origem"],
            "updated_at": c["updated_at"], "catalogo": _catalogo(), "titulo": c["processo"].get("title"),
            "nota": ("O Estúdio parte das medidas do processo. As peças do licenciamento (implantação, quadro de áreas, "
                     "memória) continuam a ser as do processo: o que alterar aqui ainda não as atualiza.")}


@router.put("/processos/{pid}")
async def guardar(pid: str, body: ModeloIn, user=Depends(current_user)) -> dict:
    await UA._owned(pid, user["user_id"])
    m = _limpo(body.modelo)
    der = await run_in_threadpool(EP.derivar, m)
    agora = datetime.now(timezone.utc).isoformat()
    await db.urbanismo_estudios.replace_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"processo_id": pid, "user_id": user["user_id"], "modelo": m, "updated_at": agora},
                                            upsert=True)
    return {"ok": True, "modelo": m, "derivado": der, "updated_at": agora}


@router.delete("/processos/{pid}")
async def repor(pid: str, user=Depends(current_user)) -> dict:
    await UA._owned(pid, user["user_id"])
    await db.urbanismo_estudios.delete_one({"processo_id": pid, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/derivar")
async def derivar(body: ModeloIn, user=Depends(current_user)) -> dict:
    m = _limpo(body.modelo)
    return {"modelo": m, "derivado": await run_in_threadpool(EP.derivar, m)}


def _desenho(m: Dict[str, Any], der: Dict[str, Any], tipo: str, piso: int, lado: str, eixo: str, pos: Optional[float]) -> Dict[str, Any]:
    if tipo == "planta":
        if piso >= len(der["pisos"]):
            raise HTTPException(404, "Piso inexistente.")
        return D.planta(m, der, piso)
    if not der["paredes"]:
        raise HTTPException(409, "Desenhe pelo menos uma parede.")
    return D.alcado(m, der, lado) if tipo == "alcado" else D.corte(m, der, eixo, pos)


@router.post("/desenho.svg")
async def desenho_svg(body: DesenhoIn, user=Depends(current_user)):
    m = _limpo(body.modelo)

    def go():
        der = EP.derivar(m)
        return D.svg(_desenho(m, der, body.tipo, body.piso, body.lado, body.eixo, body.pos))
    return Response(content=await run_in_threadpool(go), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/processos/{pid}/pranchas.pdf")
async def pranchas(pid: str, user=Depends(current_user)):
    from engines.urbanismo_pt import pdf as UP
    c = await _carregar(pid, user["user_id"])

    def go():
        der = EP.derivar(c["modelo"])
        return UP.pecas_desenhadas_pdf(c["processo"], D.pecas_png(c["modelo"], der))
    data = await run_in_threadpool(go)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-pranchas", c["processo"].get("title")), inline=True)})


def medicoes_csv(der: Dict[str, Any]) -> str:
    """Medições com o identificador de cada parede, para a empresa poder conferir no desenho."""
    md = der["medicoes"]
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    n = lambda v: str(v).replace(".", ",")  # noqa: E731
    w.writerow(["ConstruPilot — Estúdio de Projeto — medições geométricas"])
    w.writerow([md["convencao"]])
    w.writerow([])
    w.writerow(["PAREDES", "Piso", "Tipo", "Comprimento no eixo (m)", "Comprimento líquido (m)", "Altura (m)", "Espessura (m)",
                "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)", "Volume (m³)"])
    for p in md["paredes"]:
        w.writerow([p["id"], p["piso"], p["nome_tipo"], n(p["comprimento_eixo_m"]), n(p["comprimento_liquido_m"]), n(p["altura_m"]),
                    n(p["espessura_m"]), n(p["area_bruta_m2"]), n(p["area_vaos_m2"]), n(p["area_liquida_m2"]), n(p["volume_m3"])])
    w.writerow([])
    w.writerow(["CAMADAS POR TIPO DE PAREDE", "Camada", "Espessura (m)", "Área (m²)", "Volume (m³)"])
    for t in md["por_tipo"]:
        for c in t["camadas"]:
            w.writerow([t["nome"], c["material"], n(c["esp_m"]), n(c["area_m2"]), n(c["volume_m3"])])
    w.writerow([])
    w.writerow(["VÃOS", "Largura (m)", "Altura (m)", "Quantidade", "Área (m²)", "Identificadores"])
    for v in md["vaos"]:
        w.writerow([v["tipo"], n(v["largura_m"]), n(v["altura_m"]), v["quantidade"], n(v["area_m2"]), " ".join(v["ids"])])
    w.writerow([])
    w.writerow(["DIVISÕES", "Piso", "Área útil (m²)", "Perímetro (m)", "Paredes da divisão (m²)", "Rodapé (m)"])
    for d in md["divisoes"]:
        w.writerow([d["nome"], d["piso"], n(d["area_m2"]), n(d["perimetro_m"]), n(d["area_paredes_m2"]), n(d["rodape_m"])])
    w.writerow([])
    w.writerow(["LAJES", "Área (m²)", "Espessura (m)", "Volume (m³)"])
    for lj in md["lajes"]:
        w.writerow([lj["nome"], n(lj["area_m2"]), n(lj["espessura_m"]), n(lj["volume_m3"])])
    for t in md["terracos"]:
        w.writerow([f"Terraço sobre {t['sobre']}", n(t["area_m2"]), "", ""])
    w.writerow([])
    w.writerow(["ACABAMENTOS", "Material", "Área (m²)"])
    for ac in md["acabamentos"]:
        w.writerow([ac["elemento"], ac["material"], n(ac["area_m2"])])
    c, f, t = md["cobertura"], md["fachada"], md["totais"]
    w.writerow([])
    w.writerow(["COBERTURA", "Tipo", "Inclinação (°)", "Área real (m²)", "Área em planta (m²)", "Perímetro do beirado (m)", "Empenas (m²)"])
    w.writerow(["", c["tipo"], n(c["inclinacao_graus"]), n(c["area_m2"]), n(c["area_planta_m2"]), n(c["perimetro_beirado_m"]), n(c["empenas_m2"])])
    w.writerow([])
    w.writerow(["FACHADA EXTERIOR", "Perímetro (m)", "Área bruta (m²)", "Vãos (m²)", "Área líquida (m²)"])
    w.writerow(["", n(f["perimetro_m"]), n(f["area_bruta_m2"]), n(f["area_vaos_m2"]), n(f["area_liquida_m2"])])
    w.writerow([])
    w.writerow(["TOTAIS", "Área bruta de construção (m²)", "Área útil (m²)"])
    w.writerow(["", n(t["area_bruta_construcao_m2"]), n(t["area_util_m2"])])
    return buf.getvalue()


@router.get("/processos/{pid}/medicoes.csv")
async def medicoes(pid: str, user=Depends(current_user)):
    c = await _carregar(pid, user["user_id"])
    der = await run_in_threadpool(EP.derivar, c["modelo"])
    data = ("﻿" + medicoes_csv(der)).encode("utf-8")
    return Response(content=data, media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": content_disposition(nom_document("Estudio-medicoes", c["processo"].get("title"), ext="csv"))})
