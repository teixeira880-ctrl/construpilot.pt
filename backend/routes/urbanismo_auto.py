"""Rotas do piloto automático de licenciamento — para particulares e profissionais (basta ter sessão).

POST /urbanismo-auto/pedidos            pedido simples → trabalho em segundo plano (etapas visíveis)
GET  /urbanismo-auto/pedidos/{job_id}   estado do trabalho
GET  /urbanismo-auto/processos/{pid}    processo + resumo + coerência
POST /urbanismo-auto/processos/{pid}/refazer   respostas às perguntas (área, tipologia…) → recalcula tudo
PATCH /urbanismo-auto/processos/{pid}/materiais  fachada / cobertura / caixilharia (3D, memória, render)
GET  /urbanismo-auto/processos/{pid}/modelo3d    geometria exata para o visualizador 3D
POST /urbanismo-auto/processos/{pid}/render      imagem fotorrealista a partir da vista 3D (mesmas medidas)
POST /urbanismo-auto/zona             zona edificável de uma parcela desenhada no mapa (mesma regra do motor)
GET  /urbanismo-auto/processos/{pid}/streetview.jpg  fotografia real da rua virada para o terreno (Street View)
GET  /urbanismo-auto/processos/{pid}/desenhos/{n}.png · pecas-desenhadas.pdf · export.zip
"""
from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.nom_fichier import content_disposition, nom_document
from engines.urbanismo_pt import pdf as UP, regras as R
from engines.urbanismo_pt.auto import coerencia as C
from engines.urbanismo_pt.auto import pecas_auto as PA
from engines.urbanismo_pt.auto import pipeline as P

log = logging.getLogger(__name__)
router = APIRouter(prefix="/urbanismo-auto", tags=["urbanismo-auto"])
_TASKS: set = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RequerenteIn(BaseModel):
    nome: str = Field(default="", max_length=160)
    nif: str = Field(default="", max_length=20)
    morada: str = Field(default="", max_length=240)
    telefone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)


class PedidoIn(BaseModel):
    texto: str = Field(default="", max_length=2000)
    morada: str = Field(default="", max_length=300)
    tipologia: Optional[str] = Field(default=None, pattern="^[Tt]?[0-6]$")
    pisos: Optional[int] = Field(default=None, ge=1, le=2)
    garagem: Optional[bool] = None
    lugares: Optional[int] = Field(default=None, ge=0, le=3)
    escritorio: Optional[bool] = None
    fachada: Optional[str] = Field(default=None, max_length=80)
    cobertura: Optional[str] = Field(default=None, max_length=40)
    caixilharia: Optional[str] = Field(default=None, max_length=40)
    area_terreno_m2: Optional[float] = Field(default=None, gt=20, le=200_000)
    area_casa_m2: Optional[float] = Field(default=None, gt=20, le=2_000)
    frente_m: Optional[float] = Field(default=None, gt=3, le=500)
    artigo_matricial: Optional[str] = Field(default=None, max_length=80)
    descricao_predial: Optional[str] = Field(default=None, max_length=80)
    requerente: Optional[RequerenteIn] = None
    forcar_estudo: Optional[bool] = None
    # editor de implantação (mapa): limites da parcela [[lat, lon], …], limite da frente e centro da casa [lat, lon];
    # casa_centro_latlon = [] repõe a posição automática
    parcela_latlon: Optional[List[List[float]]] = Field(default=None, max_length=200)
    frente_idx: Optional[int] = Field(default=None, ge=0, le=199)
    casa_centro_latlon: Optional[List[float]] = Field(default=None, max_length=2)


class MateriaisIn(BaseModel):
    fachada: Optional[str] = Field(default=None, max_length=80)
    cobertura: Optional[str] = Field(default=None, max_length=40)
    caixilharia: Optional[str] = Field(default=None, max_length=40)


class RenderIn(BaseModel):
    imagem_b64: str = Field(min_length=100, max_length=12_000_000)
    ambiente: str = Field(default="", max_length=300)


# ------------------------------------------------------------------ execução e gravação
def _doc(user_id: str, processo: Dict[str, Any], pid: Optional[str] = None) -> Dict[str, Any]:
    return {**processo, "processo_id": pid or "urb_" + uuid.uuid4().hex[:12], "user_id": user_id, "pecas": {},
            "validacao": None, "status": "rascunho", "created_at": _now(), "updated_at": _now()}


async def executar_e_gravar(pedido: Dict[str, Any], user: Dict[str, Any], pid: Optional[str] = None, emit=None) -> Dict[str, Any]:
    """Usado pela página, pelo Assistente BTP e pela Aurora: o mesmo caminho para todos."""
    r = await P.executar(pedido, emit=emit)
    if not r.get("ok"):
        return P.resumo_publico(r)
    doc = _doc(user["user_id"], r["processo"], pid)
    if pid:
        old = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": user["user_id"]}, {"_id": 0, "created_at": 1, "pecas": 1})
        doc["created_at"] = (old or {}).get("created_at") or doc["created_at"]
        doc["pecas"] = (old or {}).get("pecas") or {}
        await db.urbanismo_processos.replace_one({"processo_id": pid, "user_id": user["user_id"]}, doc, upsert=True)
    else:
        await db.urbanismo_processos.insert_one(dict(doc))
    return P.resumo_publico(r, doc["processo_id"])


async def _owned(pid: str, uid: str) -> Dict[str, Any]:
    d = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": uid}, {"_id": 0})
    if not d or not d.get("auto"):
        raise HTTPException(404, "Processo automático não encontrado.")
    return d


def _sem_pesados(d: Dict[str, Any]) -> Dict[str, Any]:
    a = dict(d.get("auto") or {})
    if a.get("orto"):
        a["orto"] = {k: v for k, v in a["orto"].items() if k != "b64"} | {"disponivel": bool(a["orto"].get("b64"))}
    return {**{k: v for k, v in d.items() if k not in ("auto", "user_id")}, "auto": a}


@router.post("/pedidos")
async def criar_pedido(body: PedidoIn, user=Depends(current_user)) -> dict:
    pedido = {k: v for k, v in body.model_dump(exclude_none=True).items() if v != ""}
    if body.requerente:
        pedido["requerente"] = body.requerente.model_dump()
    if not (pedido.get("texto") or pedido.get("morada")):
        raise HTTPException(422, "Escreva o que pretende e a morada do terreno.")
    job_id = "auto_" + uuid.uuid4().hex[:12]
    await db.urbanismo_auto_jobs.insert_one({"job_id": job_id, "user_id": user["user_id"], "estado": "a_correr",
                                             "etapas": [], "created_at": _now(), "pedido": {k: v for k, v in pedido.items() if k != "requerente"}})

    async def emit(etapa, detalhe):
        await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$push": {"etapas": {"etapa": etapa, "detalhe": str(detalhe)[:300],
                                                                                          "at": _now()}}})

    async def run():
        try:
            res = await executar_e_gravar(pedido, user, emit=emit)
            await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$set": {"estado": "concluido", "resultado": res,
                                                                                 "finished_at": _now()}})
        except Exception as e:  # noqa: BLE001
            log.exception("piloto automático falhou")
            await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$set": {"estado": "erro", "erro": str(e)[:300]}})
    t = asyncio.create_task(run())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"job_id": job_id, "etapas_previstas": P.ETAPAS}


@router.get("/pedidos/{job_id}")
async def estado_pedido(job_id: str, user=Depends(current_user)) -> dict:
    j = await db.urbanismo_auto_jobs.find_one({"job_id": job_id, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    if not j:
        raise HTTPException(404, "Pedido não encontrado.")
    return {**j, "etapas_previstas": P.ETAPAS}


@router.get("/processos")
async def listar(user=Depends(current_user)) -> dict:
    docs = await db.urbanismo_processos.find({"user_id": user["user_id"], "auto": {"$exists": True}},
                                             {"_id": 0, "processo_id": 1, "title": 1, "created_at": 1, "status": 1}).sort("created_at", -1).to_list(100)
    return {"processos": docs}


@router.get("/processos/{pid}")
async def obter(pid: str, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    verif = R.verificar(d)
    coer = C.verificar(d, verif)
    return {"processo": _sem_pesados(d), "verificacao": verif, "coerencia": coer,
            "desenhos": [{"n": i, "code": x["code"], "title": x["title"]} for i, x in enumerate(await run_in_threadpool(UP.desenhos, d, verif))],
            "catalogo_materiais": {"fachada": PA.MATERIAIS_FACHADA, "cobertura": PA.MATERIAIS_COBERTURA, "caixilharia": PA.CAIXILHARIA}}


@router.post("/processos/{pid}/refazer")
async def refazer(pid: str, body: PedidoIn, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    novo = {k: v for k, v in body.model_dump(exclude_none=True).items() if v not in ("", None) and k != "requerente"}
    pedido = {**(d["auto"].get("pedido") or {}), **novo}
    pedido["requerente"] = (body.requerente.model_dump() if body.requerente else d.get("requerente")) or {}
    for k in ("fachada", "cobertura", "caixilharia"):
        pedido.setdefault(k, (d["auto"].get("materiais") or {}).get(k))
    return await executar_e_gravar(pedido, user, pid=pid)


@router.patch("/processos/{pid}/materiais")
async def materiais(pid: str, body: MateriaisIn, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    m = dict(d["auto"].get("materiais") or {})
    if body.fachada:
        m["fachada"] = PA.material_fachada(body.fachada)
    if body.cobertura in PA.MATERIAIS_COBERTURA:
        m["cobertura"] = body.cobertura
    if body.caixilharia in PA.CAIXILHARIA:
        m["caixilharia"] = body.caixilharia
    d["auto"]["materiais"] = m
    verif = R.verificar(d)
    mem = PA.memoria_descritiva(d, verif)
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"$set": {"auto.materiais": m, "memoria_texto": mem, "updated_at": _now()}})
    return {"ok": True, "materiais": m, "rotulos": {"fachada": PA.MATERIAIS_FACHADA.get(m.get("fachada")),
                                                    "cobertura": PA.MATERIAIS_COBERTURA.get(m.get("cobertura")),
                                                    "caixilharia": PA.CAIXILHARIA.get(m.get("caixilharia"))}}


def modelo3d(d: Dict[str, Any]) -> Dict[str, Any]:
    from engines.urbanismo_pt import volumes as V
    a = d["auto"]
    vol = d["volume"]
    hh = V.heights(vol)
    soleira = (a.get("implantacao") or {}).get("cota_soleira_m")
    topo = a.get("topografia") or {}
    grid = [{"x": g["x"], "y": g["y"], "z": round(g["z"] - soleira, 3)} for g in topo.get("grelha", [])] if soleira and topo.get("ok") else []
    vols = []
    for p in V.building_polygons(vol):
        vols.append({"nome": p["name"], "anexo": p["annexe"], "pts": p["pts"],
                     "altura_m": p["h_m"] or (hh["altura_fachada_m"] if not p["annexe"] else 3.0),
                     "cobertura": "plana" if p["annexe"] else hh["roof_type"],
                     "altura_cobertura_m": 0.0 if p["annexe"] else hh["roof_h_m"]})
    return {"terreno": a["terreno"]["poligono_m"], "volumes": vols, "pisos": hh["levels"], "piso_a_piso_m": hh["storey_h_m"],
            "vaos": a.get("vaos") or [], "materiais": a.get("materiais") or {}, "terreno_grelha": grid,
            "azimutes": a["terreno"].get("azimutes"), "plantas": a.get("plantas"),
            "nota": "Medidas exatas do processo (mesmos dados das peças desenhadas)."}


@router.get("/processos/{pid}/modelo3d")
async def get_modelo3d(pid: str, user=Depends(current_user)) -> dict:
    return modelo3d(await _owned(pid, user["user_id"]))


@router.post("/processos/{pid}/render")
async def render(pid: str, body: RenderIn, user=Depends(current_user)) -> dict:
    """Imagem fotorrealista a partir da vista 3D exata: o modelo de imagem só aplica materiais, luz e envolvente."""
    d = await _owned(pid, user["user_id"])
    from engines import image_studio
    m = d["auto"].get("materiais") or {}
    raw = body.imagem_b64.split(",", 1)[-1]
    try:
        ref = base64.b64decode(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "Imagem inválida.")
    prompt = (
        "Photorealistic architectural visualization of THIS exact house. Keep the geometry 100% identical to the reference "
        "image: same volumes, proportions, roof shape and pitch, number of floors, window and door positions and sizes, garage, "
        "camera angle and framing. Do not add or remove any window, floor, balcony or volume. Only replace the flat colours with "
        f"real materials: facade = {PA.MATERIAIS_FACHADA.get(m.get('fachada'), 'white render')}; "
        f"roof = {PA.MATERIAIS_COBERTURA.get(m.get('cobertura'), 'red clay tiles')}; "
        f"window frames = {PA.CAIXILHARIA.get(m.get('caixilharia'), 'anthracite aluminium')}. "
        "Natural daylight, soft shadows, realistic glass reflections, a simple garden with lawn and granite paving, "
        f"landscape of the Minho region of northern Portugal. {body.ambiente}".strip())
    imgs = await image_studio.generate(prompt=prompt, provider="gemini", reference_images=[ref], number=1,
                                       feature="licenciamento_render", session_id=pid)
    data, mime = imgs[0]
    return {"ok": True, "imagem_b64": base64.b64encode(data).decode(), "mime": mime,
            "nota": "Imagem ilustrativa gerada sobre a vista 3D exata; as medidas de referência são as das peças desenhadas."}


class ZonaIn(BaseModel):
    parcela_latlon: List[List[float]] = Field(min_length=3, max_length=200)
    frente_idx: int = Field(default=0, ge=0, le=199)
    frontal_m: float = Field(default=5.0, ge=0, le=50)
    lateral_m: float = Field(default=3.0, ge=0, le=50)
    tardoz_m: float = Field(default=6.0, ge=0, le=50)


@router.post("/zona")
async def zona(body: ZonaIn, user=Depends(current_user)) -> dict:
    """Zona onde se pode construir (a mesma regra do motor de implantação), para desenhar no mapa."""
    from shapely.geometry import Polygon, box
    from engines.urbanismo_pt.auto import terreno as T
    pu = T.anel_utilizador(body.parcela_latlon, body.frente_idx)
    if not pu:
        raise HTTPException(422, "Os limites do terreno cruzam-se ou a área é demasiado pequena.")
    la0, lo0 = pu["anel_latlon"][0]
    ter = T.construir_terreno({"lat": la0, "lon": lo0}, None, None, parcela_user=pu)
    parcel = Polygon(ter["poligono_m"])
    minx, miny, maxx, maxy = parcel.bounds
    z = parcel.buffer(-body.lateral_m, join_style=2).intersection(
        box(minx - 1, miny + body.frontal_m, maxx + 1, maxy - body.tardoz_m))
    ref, loc = ter["_ref"], ter["_local"]
    aneis = []
    for g in (getattr(z, "geoms", None) or [z]):
        if g.is_empty or g.geom_type != "Polygon":
            continue
        aneis.append([list(loc.ll(*ref.para_en(x, y))) for x, y in list(g.exterior.coords)[:-1]])
    return {"zona_latlon": aneis, "area_m2": round(z.area, 1), "area_terreno_m2": ter["area_m2"]}


@router.get("/processos/{pid}/streetview.jpg")
async def streetview(pid: str, user=Depends(current_user)):
    """Fotografia real da rua virada para o terreno (Google Street View Static API, imagem oficial do Google)."""
    import math
    import os
    from engines.urbanismo_pt.auto import geo as G
    d = await _owned(pid, user["user_id"])
    key = (os.environ.get("GOOGLE_MAPS_API_KEY") or "").strip()
    pts = (d["auto"].get("terreno") or {}).get("poligono_latlon") or []
    if not key or not pts:
        raise HTTPException(404, "Fotografia de rua indisponível (serviço do Google não configurado).")
    lat = sum(p[0] for p in pts) / len(pts)
    lon = sum(p[1] for p in pts) / len(pts)
    st, meta = await G._fetch("GET", f"{G.GMAPS}/streetview/metadata",
                              {"location": f"{lat},{lon}", "radius": 120, "source": "outdoor", "key": key}, None, "json")
    if not meta or meta.get("status") != "OK":
        raise HTTPException(404, "Não há fotografias de rua do Google junto a este terreno.")
    plat, plon = meta["location"]["lat"], meta["location"]["lng"]
    dy, dx = lat - plat, (lon - plon) * math.cos(math.radians(lat))
    heading = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    st, img = await G._fetch("GET", f"{G.GMAPS}/streetview", {"size": "640x400", "pano": meta["pano_id"], "heading": f"{heading:.0f}",
                                                              "fov": 80, "pitch": 2, "key": key}, None, "bytes")
    if not img or img[:2] != b"\xff\xd8":
        raise HTTPException(502, "O Google não devolveu a fotografia de rua.")
    return Response(content=img, media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400", "X-Streetview-Data": str(meta.get("date") or ""),
                             "X-Streetview-Copyright": str(meta.get("copyright") or "© Google")})


@router.get("/processos/{pid}/desenhos/{n}.png")
async def desenho(pid: str, n: int, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    ds = await run_in_threadpool(UP.desenhos, d, None)
    if not 0 <= n < len(ds):
        raise HTTPException(404, "Desenho inexistente.")
    return Response(content=ds[n]["png"], media_type="image/png")


@router.get("/processos/{pid}/pecas-desenhadas.pdf")
async def pecas_pdf(pid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    data = await run_in_threadpool(lambda: UP.pecas_desenhadas_pdf(d, UP.desenhos(d, None)))
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Pecas-desenhadas", d.get("title")), inline=True)})


def _anexar_relatorio(zbytes: bytes, d: Dict[str, Any], coer: Dict[str, Any]) -> bytes:
    import io
    import zipfile
    a = d.get("auto") or {}
    linhas = ["RELATÓRIO DO PILOTO AUTOMÁTICO — ConstruPilot", "", "Fontes de dados:"]
    linhas += [f" - {f['fonte']}" + (f" ({f['url']})" if f.get("url") else "") for f in a.get("fontes", [])]
    linhas += ["", "Hipóteses assumidas (a confirmar):"] + [f" - {x}" for x in a.get("pressupostos", [])] or [" - nenhuma"]
    linhas += ["", "Avisos:"] + ([f" - {x}" for x in a.get("avisos", [])] or [" - nenhum"])
    linhas += ["", "Decisões de projeto:"] + [f" - {x}" for x in (a.get("implantacao") or {}).get("decisoes", [])]
    linhas += ["", f"Controlo de coerência entre motores: {coer['aprovados']}/{coer['total']} verificações aprovadas"]
    linhas += [f" [{'OK' if c['ok'] else 'FALHA'}] {c['descricao']}: esperado {c['esperado']}, obtido {c['obtido']}" for c in coer["checks"]]
    linhas += ["", "O levantamento topográfico, os projetos de especialidades e os termos de responsabilidade dos técnicos "
               "(art.º 10.º do RJUE) são obrigatórios antes da submissão à câmara municipal."]
    buf = io.BytesIO(zbytes)
    with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr("06_relatorio_piloto_automatico.txt", "\n".join(linhas))
    return buf.getvalue()


@router.get("/processos/{pid}/export.zip")
async def exportar(pid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    verif = R.verificar(d)
    coer = C.verificar(d, verif)
    if not coer["ok"]:
        raise HTTPException(409, "O processo tem incoerências entre motores — corrija antes de exportar: "
                                 + "; ".join(f["descricao"] for f in coer["falhas"][:3]))
    falta = (d.get("auto") or {}).get("por_confirmar") or []
    if falta:
        raise HTTPException(409, "Ainda não foi possível confirmar com dados oficiais: " + ", ".join(falta)
                                 + ". Use «Refazer» para voltar a consultar antes de exportar.")
    data = await run_in_threadpool(UP.export_zip, d, verif, [])
    data = _anexar_relatorio(data, d, coer)
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": content_disposition(nom_document("Processo-licenciamento", d.get("title"), ext="zip"))})
