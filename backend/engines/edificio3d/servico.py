"""Edifício 3D georreferenciado — fila de trabalhos, armazenamento e execução do Blender.

Dois modos de execução, ambos com os programas REAIS:
  • servidor — se o Blender estiver disponível neste servidor (módulo «bpy» ou BLENDER_BIN):
               o backend corre o motor Blender e guarda GLB + renders.
  • worker   — um PC com Blender (e opcionalmente ArcGIS Pro) corre worker_local.py, que vai buscar
               trabalhos a esta API, executa Blender → ArcGIS Pro e devolve os ficheiros produzidos.
Os trabalhos que pedem ArcGIS Pro vão sempre para o worker (o ArcGIS Pro só existe em Windows).
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorGridFSBucket

from core.db import db

log = logging.getLogger(__name__)
AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT_BLENDER = os.path.join(AQUI, "blender_edificio.py")
COL = "edificio3d_jobs"
_SEM = asyncio.Semaphore(1)
_TASKS: set = set()

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".glb": "model/gltf-binary",
        ".json": "application/json", ".blend": "application/octet-stream", ".slpk": "application/octet-stream",
        ".aprx": "application/octet-stream", ".zip": "application/zip"}


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def bucket() -> AsyncIOMotorGridFSBucket:
    return AsyncIOMotorGridFSBucket(db, bucket_name="edificio3d")


def blender_no_servidor() -> Optional[List[str]]:
    """Comando para correr o motor neste servidor, ou None se não houver Blender."""
    if os.environ.get("EDIFICIO3D_SERVIDOR", "1") == "0":
        return None
    binario = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    if binario:
        return [binario, "-b", "--factory-startup", "-P", SCRIPT_BLENDER, "--"]
    if importlib.util.find_spec("bpy") is not None:
        return [sys.executable, SCRIPT_BLENDER]
    return None


# ------------------------------------------------------------------ ficheiros (GridFS)
async def guardar_ficheiro(job_id: str, nome: str, dados: bytes) -> None:
    b = bucket()
    async for f in b.find({"filename": f"{job_id}/{nome}"}):
        await b.delete(f._id)
    ext = os.path.splitext(nome)[1].lower()
    await b.upload_from_stream(f"{job_id}/{nome}", dados, metadata={"job_id": job_id, "nome": nome,
                                                                    "mime": MIME.get(ext, "application/octet-stream")})
    await db[COL].update_one({"job_id": job_id}, {"$addToSet": {"ficheiros": nome}, "$set": {"atualizado_em": agora()}})


async def ler_ficheiro(job_id: str, nome: str) -> Optional[bytes]:
    try:
        s = await bucket().open_download_stream_by_name(f"{job_id}/{nome}")
        return await s.read()
    except Exception:
        return None


async def etapa(job_id: str, texto: str, estado: Optional[str] = None) -> None:
    upd: Dict[str, Any] = {"$push": {"etapas": {"t": agora(), "texto": texto[:400]}}, "$set": {"atualizado_em": agora()}}
    if estado:
        upd["$set"]["estado"] = estado
    await db[COL].update_one({"job_id": job_id}, upd)


# ------------------------------------------------------------------ preparação geográfica
async def preparar_geo(job_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Morada→coordenadas, altitude real e ortofotomapa (antes da intervenção)."""
    from engines.urbanismo_pt.auto import geo as G
    if (params.get("latitude") is None or params.get("longitude") is None) and params.get("morada"):
        g = await G.geocode(params["morada"])
        if g.get("ok"):
            params["latitude"], params["longitude"] = g["data"]["lat"], g["data"]["lon"]
            await etapa(job_id, f"Morada localizada ({g.get('fonte')}): {g['data']['lat']:.6f}, {g['data']['lon']:.6f}")
    if params.get("latitude") is None:
        raise ValueError("coordenadas em falta")
    lat, lon = float(params["latitude"]), float(params["longitude"])
    if params.get("altitude_m") is None:
        try:
            e = await G.elevacoes([(lat, lon)])
            if e.get("ok") and e["data"]["z"] and e["data"]["z"][0] is not None:
                params["altitude_m"] = round(float(e["data"]["z"][0]), 2)
                params["fonte_altitude"] = e.get("fonte")
                await etapa(job_id, f"Altitude do terreno: {params['altitude_m']} m ({e.get('fonte')})")
        except Exception as ex:  # noqa: BLE001
            log.warning("edificio3d altitude: %s", ex)
    try:
        o = await G.ortofoto(lat, lon, meia_largura_m=60.0, px=1024)
        if o.get("ok"):
            await guardar_ficheiro(job_id, "ortofoto.png", o["data"]["png"])
            bb = [float(x) for x in o["data"]["bbox"].split(",")]
            lado = (bb[3] - bb[1]) * 111_320.0
            params["ortofoto_lado_m"] = round(lado, 2)
            params["fonte_ortofoto"] = o.get("fonte")
            await etapa(job_id, f"Ortofotomapa obtido ({o.get('fonte')}, {lado:.0f} m de lado)")
        else:
            await etapa(job_id, "Ortofotomapa indisponível — terreno genérico no Blender")
    except Exception as ex:  # noqa: BLE001
        log.warning("edificio3d ortofoto: %s", ex)
    return params


# ------------------------------------------------------------------ execução no servidor
def _correr_blender(cmd: List[str], params: Dict[str, Any], orto: Optional[bytes]) -> Dict[str, Any]:
    tmp = tempfile.mkdtemp(prefix="cp_ed3d_")
    try:
        p = dict(params)
        if orto:
            op = os.path.join(tmp, "ortofoto.png")
            with open(op, "wb") as f:
                f.write(orto)
            p["ortofoto_path"] = op
        pp = os.path.join(tmp, "parametros.json")
        with open(pp, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        out = os.path.join(tmp, "out")
        r = subprocess.run(cmd + [pp, out], capture_output=True, text=True,
                           timeout=int(os.environ.get("EDIFICIO3D_TIMEOUT_S", "1500")))
        man_p = os.path.join(out, "manifesto.json")
        if r.returncode != 0 or not os.path.exists(man_p):
            raise RuntimeError(f"Blender falhou (código {r.returncode}): {(r.stderr or r.stdout)[-1500:]}")
        with open(man_p, encoding="utf-8") as f:
            man = json.load(f)
        ficheiros = {}
        for nome in os.listdir(out):
            with open(os.path.join(out, nome), "rb") as f:
                ficheiros[nome] = f.read()
        return {"manifesto": man, "ficheiros": ficheiros}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def executar_no_servidor(job_id: str) -> None:
    j = await db[COL].find_one({"job_id": job_id}, {"_id": 0})
    cmd = blender_no_servidor()
    if not j or not cmd:
        return
    async with _SEM:
        try:
            await etapa(job_id, "Blender a modelar o edifício (geometria, materiais, renders Cycles)…", "a_processar")
            orto = await ler_ficheiro(job_id, "ortofoto.png")
            r = await asyncio.to_thread(_correr_blender, cmd, j["params"], orto)
            for nome, dados in r["ficheiros"].items():
                await guardar_ficheiro(job_id, nome, dados)
            g = r["manifesto"].get("geometria", {})
            await etapa(job_id, f"Blender concluído: {g.get('vertices')} vértices, {g.get('faces')} faces, "
                                f"{len(r['manifesto'].get('imagens', {}))} renders, GLB exportado")
            await db[COL].update_one({"job_id": job_id}, {"$set": {
                "estado": "concluido", "modo": "servidor", "manifesto": r["manifesto"], "concluido_em": agora()}})
        except Exception as ex:  # noqa: BLE001
            log.exception("edificio3d servidor")
            await db[COL].update_one({"job_id": job_id}, {"$set": {"estado": "erro", "erro": str(ex)[:1500]}})


async def criar_trabalho(user_id: str, params: Dict[str, Any], usar_arcgis: bool) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex[:16]
    doc = {"job_id": job_id, "user_id": user_id, "nome": params.get("nome") or "Edifício 3D", "params": params,
           "usar_arcgis": usar_arcgis, "estado": "a_preparar", "etapas": [], "ficheiros": [],
           "criado_em": agora(), "atualizado_em": agora()}
    await db[COL].insert_one(dict(doc))

    async def fluxo():
        try:
            p = await preparar_geo(job_id, dict(params))
            servidor = blender_no_servidor() is not None and not usar_arcgis
            await db[COL].update_one({"job_id": job_id}, {"$set": {
                "params": p, "estado": "em_fila", "modo": "servidor" if servidor else "worker"}})
            if servidor:
                await executar_no_servidor(job_id)
            else:
                await etapa(job_id, "Em fila para o posto Blender" + (" + ArcGIS Pro" if usar_arcgis else ""))
        except Exception as ex:  # noqa: BLE001
            await db[COL].update_one({"job_id": job_id}, {"$set": {"estado": "erro", "erro": str(ex)[:800]}})

    t = asyncio.create_task(fluxo())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    doc.pop("_id", None)
    return doc
