"""Edifício 3D georreferenciado — Blender (modelo 3D real) + ArcGIS Pro (implantação geográfica).

Utilizador (sessão):
  GET  /edificio3d/sistema                       → onde corre o Blender / ArcGIS (servidor, postos ligados)
  POST /edificio3d/projetos                      → coordenadas + parâmetros → trabalho
  GET  /edificio3d/projetos                      → lista
  GET  /edificio3d/projetos/{id}                 → estado, etapas, manifesto Blender e ArcGIS
  GET  /edificio3d/projetos/{id}/ficheiros/{n}   → GLB, renders, ortofoto, .blend, .slpk…
Posto de trabalho (cabeçalho X-Worker-Token = EDIFICIO3D_WORKER_TOKEN):
  POST /edificio3d/worker/proximo · POST /edificio3d/worker/{id}/etapa
  GET  /edificio3d/worker/{id}/ficheiros/{n}     · POST /edificio3d/worker/{id}/ficheiros/{n}
  POST /edificio3d/worker/{id}/concluir
Administração:
  GET  /edificio3d/kit-worker.zip                → scripts para instalar no PC com Blender / ArcGIS Pro
"""
from __future__ import annotations

import io
import os
import re
import secrets
import zipfile
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user, current_user
from engines.edificio3d import servico as S

router = APIRouter(prefix="/edificio3d", tags=["edificio3d"])
NOME_OK = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


class ProjetoIn(BaseModel):
    nome: str = Field(default="Edifício contemporâneo", max_length=120)
    morada: str = Field(default="", max_length=300)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    altitude_m: Optional[float] = Field(default=None, ge=-100, le=9000)
    azimute_fachada_graus: float = Field(default=180.0, ge=0, lt=360)
    largura_m: float = Field(default=12.0, ge=5, le=40)
    profundidade_m: float = Field(default=9.0, ge=5, le=30)
    pisos: int = Field(default=2, ge=1, le=4)
    pe_direito_m: float = Field(default=3.0, ge=2.5, le=4.5)
    inclinacao_telhado_graus: float = Field(default=30.0, ge=10, le=50)
    beiral_m: float = Field(default=0.6, ge=0.2, le=1.5)
    usar_arcgis: bool = False
    qualidade: str = Field(default="normal", pattern="^(rapida|normal|alta)$")


QUAL = {"rapida": {"largura_px": 960, "altura_px": 640, "amostras": 24},
        "normal": {"largura_px": 1400, "altura_px": 933, "amostras": 48},
        "alta": {"largura_px": 1920, "altura_px": 1280, "amostras": 128}}


def _publico(j: Dict[str, Any]) -> Dict[str, Any]:
    j = {k: v for k, v in j.items() if k not in ("_id", "user_id", "worker_token")}
    return j


@router.get("/sistema", summary="Edifício 3D: Blender/ArcGIS Pro disponíveis (servidor e postos)")
async def sistema(user=Depends(current_user)) -> Dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    lim = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
    postos = await db.edificio3d_workers.find({"visto_em": {"$gte": lim}}, {"_id": 0, "nome": 1, "blender": 1,
                                                                           "arcgis": 1, "visto_em": 1}).to_list(20)
    return {"blender_servidor": S.blender_no_servidor() is not None,
            "postos": postos,
            "arcgis_disponivel": any(p.get("arcgis") for p in postos),
            "blender_disponivel": S.blender_no_servidor() is not None or any(p.get("blender") for p in postos)}


@router.post("/projetos", summary="Edifício 3D: gerar edifício 3D georreferenciado (Blender, renders, GLB, ArcGIS)")
async def criar(body: ProjetoIn, user=Depends(current_user)) -> Dict[str, Any]:
    if body.latitude is None and not body.morada.strip():
        raise HTTPException(422, "Indique as coordenadas (latitude/longitude) ou a morada.")
    p = body.model_dump()
    usar_arcgis = p.pop("usar_arcgis")
    p["render"] = QUAL[p.pop("qualidade")]
    j = await S.criar_trabalho(user["user_id"], p, usar_arcgis)
    return _publico(j)


@router.get("/projetos", summary="Edifício 3D: listar projetos 3D da conta")
async def listar(user=Depends(current_user)) -> Dict[str, Any]:
    it = await db[S.COL].find({"user_id": user["user_id"]}, {"_id": 0, "job_id": 1, "nome": 1, "estado": 1,
                                                            "criado_em": 1, "params.latitude": 1, "params.longitude": 1}
                              ).sort("criado_em", -1).to_list(50)
    return {"projetos": it}


async def _meu(job_id: str, user) -> Dict[str, Any]:
    q = {"job_id": job_id} if user.get("role") == "admin" else {"job_id": job_id, "user_id": user["user_id"]}
    j = await db[S.COL].find_one(q, {"_id": 0})
    if not j:
        raise HTTPException(404, "Projeto não encontrado")
    return j


@router.get("/projetos/{job_id}", summary="Edifício 3D: estado, etapas, renders e manifesto de um projeto")
async def obter(job_id: str, user=Depends(current_user)) -> Dict[str, Any]:
    return _publico(await _meu(job_id, user))


@router.get("/projetos/{job_id}/ficheiros/{nome}")
async def ficheiro(job_id: str, nome: str, user=Depends(current_user)):
    if not NOME_OK.match(nome):
        raise HTTPException(400, "nome inválido")
    await _meu(job_id, user)
    dados = await S.ler_ficheiro(job_id, nome)
    if dados is None:
        raise HTTPException(404, "ficheiro não encontrado")
    ext = os.path.splitext(nome)[1].lower()
    return Response(dados, media_type=S.MIME.get(ext, "application/octet-stream"),
                    headers={"Cache-Control": "private, max-age=3600",
                             "Content-Disposition": f'inline; filename="{nome}"'})


class FotoIn(BaseModel):
    vista: str = Field(pattern="^[a-z_]{3,40}$")
    ambiente: str = Field(default="", max_length=300)


@router.post("/projetos/{job_id}/fotorrealista", summary="Edifício 3D: acabamento fotorrealista sobre um render Blender (vista)")
async def fotorrealista(job_id: str, body: FotoIn, user=Depends(current_user)) -> Dict[str, Any]:
    """Acabamento fotorrealista (motor de imagem ConstruPilot) SOBRE um render real do Blender.

    O render Blender é a referência obrigatória: a geometria, o enquadramento e as medidas vêm dele.
    O resultado é guardado à parte (ia_<vista>.*) e o render original fica sempre disponível.
    """
    await _meu(job_id, user)
    try:
        return await S.gerar_fotorrealista(job_id, body.vista, body.ambiente)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


# ------------------------------------------------------------------ posto de trabalho (worker)
def _worker(x_worker_token: Optional[str] = Header(default=None)) -> str:
    esperado = os.environ.get("EDIFICIO3D_WORKER_TOKEN", "")
    if not esperado or not x_worker_token or not secrets.compare_digest(esperado, x_worker_token):
        raise HTTPException(401, "token do posto inválido")
    return x_worker_token


class ProximoIn(BaseModel):
    nome: str = Field(default="posto", max_length=80)
    blender: bool = True
    arcgis: bool = False


@router.post("/worker/proximo")
async def worker_proximo(body: ProximoIn, _t=Depends(_worker)) -> Dict[str, Any]:
    await db.edificio3d_workers.update_one({"nome": body.nome}, {"$set": {
        "nome": body.nome, "blender": body.blender, "arcgis": body.arcgis, "visto_em": S.agora()}}, upsert=True)
    q: Dict[str, Any] = {"estado": "em_fila", "modo": "worker"}
    if not body.arcgis:
        q["usar_arcgis"] = {"$ne": True}
    j = await db[S.COL].find_one_and_update(q, {"$set": {"estado": "a_processar", "posto": body.nome,
                                                         "atualizado_em": S.agora()}},
                                            sort=[("criado_em", 1)], projection={"_id": 0, "user_id": 0})
    return {"trabalho": j}


class EtapaIn(BaseModel):
    texto: str = Field(max_length=400)


@router.post("/worker/{job_id}/etapa")
async def worker_etapa(job_id: str, body: EtapaIn, _t=Depends(_worker)):
    await S.etapa(job_id, body.texto)
    return {"ok": True}


@router.get("/worker/{job_id}/ficheiros/{nome}")
async def worker_ler(job_id: str, nome: str, _t=Depends(_worker)):
    if not NOME_OK.match(nome):
        raise HTTPException(400, "nome inválido")
    d = await S.ler_ficheiro(job_id, nome)
    if d is None:
        raise HTTPException(404, "ficheiro não encontrado")
    return Response(d, media_type="application/octet-stream")


@router.post("/worker/{job_id}/ficheiros/{nome}")
async def worker_enviar(job_id: str, nome: str, request: Request, _t=Depends(_worker)):
    if not NOME_OK.match(nome):
        raise HTTPException(400, "nome inválido")
    dados = await request.body()
    if len(dados) > 200 * 1024 * 1024:
        raise HTTPException(413, "ficheiro demasiado grande")
    await S.guardar_ficheiro(job_id, nome, dados)
    return {"ok": True, "bytes": len(dados)}


class ConcluirIn(BaseModel):
    ok: bool
    manifesto: Dict[str, Any] = Field(default_factory=dict)
    arcgis: Dict[str, Any] = Field(default_factory=dict)
    erro: str = Field(default="", max_length=4000)


@router.post("/worker/{job_id}/concluir")
async def worker_concluir(job_id: str, body: ConcluirIn, _t=Depends(_worker)):
    upd = {"estado": "concluido" if body.ok else "erro", "manifesto": body.manifesto, "concluido_em": S.agora()}
    if body.arcgis:
        upd["arcgis"] = body.arcgis
    if body.erro:
        upd["erro"] = body.erro
    await db[S.COL].update_one({"job_id": job_id}, {"$set": upd})
    await S.etapa(job_id, "Concluído no posto de trabalho" if body.ok else f"Erro no posto: {body.erro[:200]}")
    return {"ok": True}


@router.get("/kit-worker.zip")
async def kit_worker(_a=Depends(admin_user)):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ("blender_edificio.py", "arcgis_implantacao.py", "worker_local.py", "LEIA-ME.md", "iniciar_worker.bat"):
            p = os.path.join(S.AQUI, n)
            if os.path.exists(p):
                z.write(p, f"construpilot_edificio3d/{n}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="construpilot_edificio3d_worker.zip"'})
