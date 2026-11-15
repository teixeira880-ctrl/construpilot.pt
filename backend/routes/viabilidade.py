"""Viabilidade construtiva de um terreno — avaliação preliminar automática, relatório PDF e ligação BIM (IFC).

POST /viabilidade/avaliar                 terreno (anel ou terreno guardado) + PDM + edifício → avaliação completa
POST /viabilidade/relatorio.pdf           a mesma avaliação em relatório PDF (com a marca da empresa)
POST /viabilidade/terreno.ifc             IFC 4 georreferenciado: terreno (MDT), limite, zona livre e implantação
POST /viabilidade/modelo                  carrega o IFC do projeto → pegada, pisos e altura (para implantar esse edifício)
POST /viabilidade/modelo-implantado.ifc   o IFC do projeto georreferenciado na implantação recomendada
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.nom_fichier import content_disposition
from engines.viabilidade_pt import bim as BM
from engines.viabilidade_pt import relatorio as RL
from engines.viabilidade_pt import servico as SV

log = logging.getLogger(__name__)
router = APIRouter(prefix="/viabilidade", tags=["viabilidade"])

_RES: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()       # resultados completos (com a grelha) para PDF / IFC
_MOD: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()       # IFC do utilizador carregados (bytes + leitura)
_MAX_RES, _MAX_MOD = 16, 8
MAX_IFC = 80 * 1024 * 1024


class EdificioIn(BaseModel):
    largura_m: Optional[float] = Field(default=None, gt=2, le=200)
    profundidade_m: Optional[float] = Field(default=None, gt=2, le=200)
    n_pisos: Optional[int] = Field(default=None, ge=1, le=30)


class AvaliarIn(BaseModel):
    terreno_id: Optional[str] = Field(default=None, max_length=40)
    anel_latlon: Optional[List[List[float]]] = Field(default=None, min_length=3, max_length=2000)
    nome: str = Field(default="", max_length=120)
    pdm: Dict[str, Any] = Field(default_factory=dict)
    edificio: Optional[EdificioIn] = None
    modelo_id: Optional[str] = Field(default=None, max_length=40)


def _guardar(cache: OrderedDict, k: str, v: Dict[str, Any], mx: int) -> None:
    cache[k] = v
    cache.move_to_end(k)
    while len(cache) > mx:
        cache.popitem(last=False)


async def _anel(body: AvaliarIn, uid: str) -> tuple:
    if body.terreno_id:
        d = await db.terrenos.find_one({"terreno_id": body.terreno_id, "user_id": uid}, {"_id": 0, "anel_latlon": 1, "nome": 1})
        if not d:
            raise HTTPException(404, "Terreno não encontrado.")
        return d["anel_latlon"], body.nome or d.get("nome") or "Terreno"
    if not body.anel_latlon:
        raise HTTPException(422, "Indique o terreno (desenhado ou guardado).")
    return body.anel_latlon, body.nome or "Terreno"


def _modelo(mid: Optional[str], uid: str) -> Optional[Dict[str, Any]]:
    if not mid:
        return None
    m = _MOD.get(f"{uid}:{mid}")
    if not m:
        raise HTTPException(410, "O modelo IFC já não está em memória: volte a carregá-lo.")
    return m


async def _avaliacao(body: AvaliarIn, user) -> Dict[str, Any]:
    uid = user["user_id"]
    anel, nome = await _anel(body, uid)
    mod = _modelo(body.modelo_id, uid)
    ed = body.edificio.model_dump() if body.edificio else None
    k = uid + ":" + hashlib.sha1(json.dumps({"a": anel, "p": body.pdm, "e": ed, "m": body.modelo_id}, sort_keys=True,
                                            default=str).encode()).hexdigest()[:20]
    if k in _RES and time.time() - _RES[k]["_ts"] < 3600:
        _RES.move_to_end(k)
        return _RES[k]
    try:
        res = await SV.avaliar(anel, body.pdm, ed, (mod or {}).get("leitura"))
    except SV.ViabilidadeErro as e:
        raise HTTPException(422, str(e))
    except Exception:  # noqa: BLE001
        log.exception("viabilidade: erro inesperado")
        raise HTTPException(500, "Falha na avaliação do terreno. Tente novamente.")
    res["_ts"] = time.time()
    res["_nome"] = nome
    _guardar(_RES, k, res, _MAX_RES)
    if body.terreno_id:
        v = res["viabilidade"]
        await db.terrenos.update_one({"terreno_id": body.terreno_id, "user_id": uid}, {"$set": {
            "viabilidade": {"classificacao": v["classificacao"], "rotulo": v["rotulo"], "indice": v["indice"],
                            "sintese": v["sintese"], "em": datetime.now(timezone.utc).isoformat()}}})
    return res


async def _empresa(uid: str) -> Optional[Dict[str, str]]:
    try:
        from routes.plans_common import _resolve_branding
        b = await _resolve_branding(uid) or {}
        return {"nome": b.get("company_name") or "ConstruPilot", "cor": b.get("accent_color")}
    except Exception:  # noqa: BLE001
        return None


def _seguro(nome: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nome)[:60] or "terreno"


@router.post("/avaliar")
async def avaliar(body: AvaliarIn, user=Depends(current_user)) -> dict:
    return SV.publico(await _avaliacao(body, user))


@router.post("/relatorio.pdf")
async def relatorio(body: AvaliarIn, user=Depends(current_user)):
    res = await _avaliacao(body, user)
    emp = await _empresa(user["user_id"])
    import asyncio
    dados = await asyncio.to_thread(RL.pdf, res, res.get("_nome") or "", emp)
    return Response(content=dados, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(f"viabilidade_{_seguro(res.get('_nome') or '')}.pdf")})


@router.post("/terreno.ifc")
async def terreno_ifc(body: AvaliarIn, user=Depends(current_user)):
    res = await _avaliacao(body, user)
    it = res["_interno"]
    import asyncio
    try:
        dados = await asyncio.to_thread(BM.ifc_terreno, it["r"], it["mascara"], it["anel_tm"], SV.publico(res),
                                        res.get("_nome") or "Terreno", it["impl"], it["zona_livre_tm"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    return Response(content=dados, media_type="application/x-step",
                    headers={"Content-Disposition": content_disposition(f"terreno_{_seguro(res.get('_nome') or '')}.ifc")})


@router.post("/modelo")
async def carregar_modelo(ficheiro: UploadFile = File(...), user=Depends(current_user)) -> dict:
    dados = await ficheiro.read(MAX_IFC + 1)
    if len(dados) > MAX_IFC:
        raise HTTPException(413, "IFC demasiado grande (máximo 80 MB).")
    import asyncio
    try:
        leitura = await asyncio.to_thread(BM.ler_modelo_ifc, dados)
    except Exception as e:  # noqa: BLE001 — ModelError, ValueError ou IFC ilegível
        raise HTTPException(422, f"Não foi possível ler o IFC: {str(e)[:200]}")
    mid = uuid.uuid4().hex[:12]
    _guardar(_MOD, f"{user['user_id']}:{mid}", {"bytes": dados, "leitura": leitura, "nome": ficheiro.filename or "modelo.ifc"},
             _MAX_MOD)
    return {"modelo_id": mid, "nome": ficheiro.filename, **{k: v for k, v in leitura.items() if k != "pisos"},
            "pisos": leitura.get("pisos")}


@router.post("/modelo-implantado.ifc")
async def modelo_implantado(body: AvaliarIn, user=Depends(current_user)):
    if not body.modelo_id:
        raise HTTPException(422, "Carregue primeiro o IFC do projeto.")
    mod = _modelo(body.modelo_id, user["user_id"])
    res = await _avaliacao(body, user)
    impl = res["implantacao"]
    if not impl.get("ok"):
        raise HTTPException(422, impl.get("nota") or "Sem implantação possível no terreno.")
    import asyncio
    try:
        dados = await asyncio.to_thread(BM.georreferenciar_ifc, mod["bytes"], impl, mod["leitura"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, f"Não foi possível georreferenciar o IFC: {str(e)[:200]}")
    base = (mod.get("nome") or "modelo").rsplit(".", 1)[0]
    return Response(content=dados, media_type="application/x-step",
                    headers={"Content-Disposition": content_disposition(f"{_seguro(base)}_implantado.ifc")})
