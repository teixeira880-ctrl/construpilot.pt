"""Rotas do piloto automático de licenciamento — para particulares e profissionais (basta ter sessão).

POST /urbanismo-auto/pedidos            pedido simples → trabalho em segundo plano (etapas visíveis)
GET  /urbanismo-auto/pedidos/{job_id}   estado do trabalho
GET  /urbanismo-auto/processos/{pid}    processo + resumo + coerência
POST /urbanismo-auto/processos/{pid}/refazer   respostas às perguntas (área, tipologia…) → recalcula tudo
PATCH /urbanismo-auto/processos/{pid}/materiais  fachada / cobertura / caixilharia (3D, memória, render)
GET  /urbanismo-auto/processos/{pid}/modelo3d    geometria exata para o visualizador 3D
POST /urbanismo-auto/processos/{pid}/render      imagem fotorrealista a partir da vista 3D (mesmas medidas)
GET  /urbanismo-auto/processos/{pid}/desenhos/{n}.png · pecas-desenhadas.pdf · export.zip
POST /urbanismo-auto/processos/{pid}/imagens     imagens realistas automáticas (vistas exatas → fotorrealistas, antes/depois)
GET  /urbanismo-auto/processos/{pid}/imagens · /imagens/{iid}.jpg
PATCH /urbanismo-auto/processos/{pid}/projeto    alterar qualquer escolha (forma, área, estilo, piscina…) e recalcular tudo
GET  /urbanismo-auto/estilos                     estilos arquitetónicos disponíveis
POST /urbanismo-auto/processos/{pid}/foto-terreno       fotografia real do terreno (para a montagem «depois»)
POST /urbanismo-auto/processos/{pid}/imagens/{iid}/aprovar  o cliente aprova (ou não) uma montagem para o dossier
"""
from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
    frente_m: Optional[float] = Field(default=None, gt=3, le=500)
    artigo_matricial: Optional[str] = Field(default=None, max_length=80)
    descricao_predial: Optional[str] = Field(default=None, max_length=80)
    requerente: Optional[RequerenteIn] = None
    forcar_estudo: Optional[bool] = None
    # v2 — tudo configurável em linguagem simples
    forma: Optional[str] = Field(default=None, pattern="^(retangulo|l|u|t)$")
    area_util_alvo_m2: Optional[float] = Field(default=None, gt=25, le=2000)
    garagem_tipo: Optional[str] = Field(default=None, pattern="^(integrada|exterior)$")
    piscina: Optional[bool] = None
    piscina_l_m: Optional[float] = Field(default=None, ge=3, le=30)
    piscina_w_m: Optional[float] = Field(default=None, ge=2, le=15)
    estilo: Optional[str] = Field(default=None, max_length=40)
    cobertura_tipo: Optional[str] = Field(default=None, pattern="^(plana|duas_aguas|uma_agua)$")


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
        old = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": user["user_id"]},
                                                    {"_id": 0, "created_at": 1, "pecas": 1, "imagens": 1, "imagens_assinatura": 1,
                                                     "foto_terreno": 1})
        doc["created_at"] = (old or {}).get("created_at") or doc["created_at"]
        doc["pecas"] = (old or {}).get("pecas") or {}
        if (old or {}).get("foto_terreno"):
            doc["foto_terreno"] = old["foto_terreno"]
        if (old or {}).get("imagens"):   # imagens antigas mantidas, mas marcadas como desatualizadas se o projeto mudou
            doc["imagens"] = old["imagens"]
            doc["imagens_assinatura"] = old.get("imagens_assinatura")
            doc["imagens_desatualizadas"] = old.get("imagens_assinatura") != (doc.get("auto") or {}).get("assinatura")
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
            "azimutes": a["terreno"].get("azimutes"), "plantas": a.get("plantas"), "piscina": vol.get("piscina"),
            "estilo": a.get("estilo"),
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
    sims = await simulacoes(d)
    data = await run_in_threadpool(lambda: UP.pecas_desenhadas_pdf(d, UP.desenhos(d, None) + sims))
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
    sims = [{"code": x["code"], "filename": x["filename"], "data": x["data"]} for x in await simulacoes(d)]
    data = await run_in_threadpool(UP.export_zip, d, verif, sims)
    data = _anexar_relatorio(data, d, coer)
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": content_disposition(nom_document("Processo-licenciamento", d.get("title"), ext="zip"))})


# ------------------------------------------------------------------ v2: estilos, edição livre, imagens realistas
@router.get("/estilos")
async def estilos(user=Depends(current_user)) -> dict:
    from engines.urbanismo_pt.auto import estilos as E
    return {"estilos": E.lista()}


class ProjetoIn(PedidoIn):
    """Qualquer escolha do projeto (em linguagem simples ou campos): o processo é recalculado de raiz e verificado."""


@router.patch("/processos/{pid}/projeto")
async def editar_projeto(pid: str, body: ProjetoIn, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    novo = {k: v for k, v in body.model_dump(exclude_none=True).items() if v != "" and k != "requerente"}
    texto_novo = novo.pop("texto", "")
    pedido = {**(d["auto"].get("pedido") or {})}
    if texto_novo:   # frase nova: só os dados que ela contém substituem os anteriores
        pedido.update({k: v for k, v in P.interpretar_pedido(texto_novo).items() if k != "morada" or v})
    pedido.update(novo)
    pedido["requerente"] = {**(d.get("requerente") or {}), **((body.requerente.model_dump() if body.requerente else {}))}
    return await asyncio.wait_for(executar_e_gravar(pedido, user, pid=pid), timeout=240)


# Conjunto completo, ao nível das apresentações de promotores: exteriores de dia, piscina, entardecer, aérea, interiores,
# planta de implantação humanizada, antes/depois e (se houver fotografia do terreno) montagem sobre a foto real.
VISTAS_PADRAO = ["perspetiva", "piscina", "frente", "tardoz", "aerea", "perspetiva_entardecer",
                 "interior_sala", "interior_cozinha", "interior_suite", "interior_wc"]
TITULOS_IMG = {"perspetiva": "perspetiva", "frente": "vista da frente", "tardoz": "vista do jardim", "aerea": "vista aérea",
               "piscina": "vista da piscina", "perspetiva_entardecer": "perspetiva ao entardecer",
               "interior_sala": "interior — sala de estar e jantar", "interior_cozinha": "interior — cozinha",
               "interior_suite": "interior — suite", "interior_wc": "interior — instalação sanitária"}
ORDEM_DOSSIER = ["perspetiva", "piscina", "frente", "tardoz", "aerea", "perspetiva_entardecer",
                 "interior_sala", "interior_cozinha", "interior_suite", "interior_wc"]


class ImagensIn(BaseModel):
    vistas: list[str] = Field(default_factory=lambda: list(VISTAS_PADRAO), max_length=14)
    antes_depois: bool = True


def _img_key(uid: str, pid: str, iid: str) -> str:
    return f"urbanismo-auto/{uid}/{pid}/imagens/{iid}.jpg"


def _foto_key(uid: str, pid: str) -> str:
    return f"urbanismo-auto/{uid}/{pid}/foto-terreno.jpg"


async def gerar_imagens(pid: str, user: Dict[str, Any], vistas: Optional[list] = None, antes_depois: bool = True) -> Dict[str, Any]:
    """Gera e guarda as imagens (usado pela página, pelo Assistente e pela Aurora). Nunca levanta exceção por imagem.
    As vistas correm em paralelo (limite de 3 pedidos simultâneos ao fornecedor)."""
    from engines.object_storage import get_object, put_object
    from engines.urbanismo_pt.auto import imagens as IM, interiores as INT, render3d as R3
    d = await _owned(pid, user["user_id"])
    m = modelo3d(d)
    sol = (d["auto"].get("implantacao") or {}).get("fachada_sol") or "frente"
    vistas = list(vistas or VISTAS_PADRAO)
    if not m.get("piscina"):
        vistas = [v for v in vistas if v != "piscina"]
    out: list = []
    sem = asyncio.Semaphore(3)
    exatas: Dict[str, Dict[str, Any]] = {}

    async def guardar(ordem, tipo, vista, jpeg, extra):
        iid = "img_" + uuid.uuid4().hex[:10]
        await run_in_threadpool(put_object, _img_key(user["user_id"], pid, iid), jpeg, "image/jpeg")
        out.append({"id": iid, "tipo": tipo, "vista": vista, "criado": _now(), "_o": ordem, **extra})

    async def exata(v):
        if v not in exatas:
            exatas[v] = await run_in_threadpool(R3.vista, m, v, sol)
        return exatas[v]

    def campos(fr):
        return {k: fr[k] for k in ("fornecedor", "geometria", "verificada", "nota", "tentativas", "qualidade") if k in fr}

    async def exterior(k, v):
        base, luz = IM.VARIANTES.get(v, (v, "dia"))
        ex = await exata(base)
        if v == base:
            await guardar((k, 0), "exata", v, IM._jpeg(ex["png"], 92), {"nota": "Vista 3D exata (medidas do projeto)."})
        async with sem:
            fr = await IM.fotorrealista(d, ex, sessao=pid, luz=luz, nome=v)
        await guardar((k, 1), fr["tipo"], v, fr["jpeg"], campos(fr) | {"iluminacao": luz})

    interiores = {n: (c, p) for n, c, p in INT.escolher(d)}

    async def interior(k, v):
        if v not in interiores:
            return
        c, piso = interiores[v]
        ex = await run_in_threadpool(INT.vista, d, v, c, piso)
        await guardar((k, 0), "exata", v, IM._jpeg(ex["png"], 92),
                      {"nota": f"Vista interior exata — {c['nome']} ({c.get('area_m2')} m², pé-direito {ex['pe_direito_m']} m).",
                       "compartimento": c["nome"]})
        async with sem:
            fr = await IM.fotorrealista(d, ex, sessao=pid, limiar=IM.LIMIAR_INTERIOR, nome=v,
                                        prompt_fn=lambda estrito: INT.prompt_interior(d, v, c, estrito))
        fr["nota"] = fr["nota"] + " Mobiliário e acabamentos interiores são sugestões ilustrativas."
        await guardar((k, 1), fr["tipo"], v, fr["jpeg"], campos(fr) | {"compartimento": c["nome"]})

    tarefas = []
    for k, v in enumerate(vistas):
        if v in R3.VISTAS or v in IM.VARIANTES:
            tarefas.append(exterior(k, v))
        elif v.startswith("interior_"):
            tarefas.append(interior(k, v))
    res = await asyncio.gather(*tarefas, return_exceptions=True)
    for r in res:
        if isinstance(r, BaseException):
            log.warning("vista falhou: %s", type(r).__name__)
    # planta de implantação humanizada (exata, sem IA)
    try:
        jpeg = await run_in_threadpool(IM.implantacao_humanizada, m)
        await guardar((90, 0), "implantacao", "implantacao", jpeg,
                      {"verificada": True, "fornecedor": "render", "nota": "Planta de implantação a cores, à escala; "
                       "vegetação e arranjos exteriores ilustrativos."})
    except Exception as e:  # noqa: BLE001
        log.warning("implantação humanizada falhou: %s", type(e).__name__)
    if antes_depois:
        base = await run_in_threadpool(IM.antes_depois_base, d)
        if base:
            await guardar((91, 0), "antes", "aerea_orto", base["antes"], {"nota": "Ortofotomapa oficial (DGT) — situação existente."})
            await guardar((91, 1), "depois_esquema", "aerea_orto", base["depois_esquema"],
                          {"nota": "Implantação proposta desenhada à escala sobre o ortofotomapa."})
            try:
                img = await IM._gemini(IM.prompt_aerea(d), base["depois_esquema"], pid)
                jpeg, q = IM.acabar(img, 1024)
                await guardar((91, 2), "depois", "aerea_orto", jpeg,
                              {"fornecedor": "gemini", "qualidade": q, "nota": IM.NOTA + " Envolvente: ortofotomapa oficial (DGT)."})
            except Exception as e:  # noqa: BLE001
                log.warning("imagem aérea «depois» falhou: %s", type(e).__name__)
        ft = d.get("foto_terreno")
        if ft:   # montagem sobre a fotografia real do terreno (precisa de aprovação do cliente para entrar no dossier)
            try:
                foto, _ = await run_in_threadpool(get_object, _foto_key(user["user_id"], pid))
                ex = await exata(ft.get("vista_ref") or "perspetiva")
                img = await IM.montagem(d, foto, ex["png"], pid)
                if img:
                    jpeg, q = IM.acabar(img)
                    await guardar((92, 0), "montagem", "foto_terreno", jpeg,
                                  {"fornecedor": "gemini", "qualidade": q, "verificada": False, "aprovada": False,
                                   "nota": "Montagem ilustrativa sobre a fotografia real do terreno. Não é verificável "
                                           "automaticamente: só entra no dossier depois de aprovada por si."})
            except Exception as e:  # noqa: BLE001
                log.warning("montagem sobre a foto do terreno falhou: %s", type(e).__name__)
    out.sort(key=lambda i: i.pop("_o"))
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"$set": {"imagens": out, "imagens_desatualizadas": False,
                                                      "imagens_assinatura": (d.get("auto") or {}).get("assinatura")}})
    return {"ok": True, "processo_id": pid, "imagens": [{k: i[k] for k in ("id", "tipo", "vista")} |
                                                       {"url": f"/api/urbanismo-auto/processos/{pid}/imagens/{i['id']}.jpg",
                                                        "verificada": i.get("verificada", True), "fornecedor": i.get("fornecedor")}
                                                       for i in out],
            "nota": "Imagens ilustrativas sobre a geometria exata do projeto; as fotorrealistas foram verificadas automaticamente "
                    "contra a vista exata. Incluídas no processo (peças desenhadas e ZIP)."}


@router.post("/processos/{pid}/imagens")
async def pedir_imagens(pid: str, body: ImagensIn, user=Depends(current_user)) -> dict:
    await _owned(pid, user["user_id"])
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"$set": {"imagens_job": {"estado": "a_correr", "inicio": _now()}}})

    async def run():
        try:
            r = await gerar_imagens(pid, user, body.vistas, body.antes_depois)
            estado = {"estado": "concluido", "fim": _now(), "n": len(r["imagens"])}
        except Exception as e:  # noqa: BLE001
            log.exception("imagens do processo falharam")
            estado = {"estado": "erro", "erro": str(getattr(e, "detail", e))[:300], "fim": _now()}
        await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]}, {"$set": {"imagens_job": estado}})
    t = asyncio.create_task(run())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"ok": True, "estado": "a_correr", "nota": "As imagens demoram cerca de 2 a 5 minutos."}


FOTO_MAX_BYTES = 15 * 1024 * 1024


@router.post("/processos/{pid}/foto-terreno")
async def enviar_foto_terreno(pid: str, ficheiro: UploadFile = File(...), user=Depends(current_user)) -> dict:
    """Fotografia real do terreno vazio (telemóvel ou drone). É reescrita como JPEG limpo (sem metadados nem conteúdo
    estranho), guardada em armazenamento privado e usada só para a montagem «depois» deste processo."""
    await _owned(pid, user["user_id"])
    raw = await ficheiro.read(FOTO_MAX_BYTES + 1)
    if len(raw) > FOTO_MAX_BYTES:
        raise HTTPException(413, "Fotografia demasiado grande (máximo 15 MB).")
    import io
    from PIL import Image, ImageOps
    try:
        Image.open(io.BytesIO(raw)).verify()
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "O ficheiro não é uma fotografia válida (JPEG, PNG, HEIC convertido…).")
    if min(im.size) < 400:
        raise HTTPException(422, "Fotografia demasiado pequena (mínimo 400 px).")
    im.thumbnail((2400, 2400), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=92)
    from engines.object_storage import put_object
    await run_in_threadpool(put_object, _foto_key(user["user_id"], pid), b.getvalue(), "image/jpeg")
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]},
                                            {"$set": {"foto_terreno": {"enviada": _now(), "largura": im.width,
                                                                       "altura": im.height}}})
    return {"ok": True, "nota": "Fotografia recebida. Volte a criar as imagens para obter a montagem «depois» sobre ela."}


class AprovarIn(BaseModel):
    aprovada: bool = True


@router.post("/processos/{pid}/imagens/{iid}/aprovar")
async def aprovar_imagem(pid: str, iid: str, body: AprovarIn, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    imgs = d.get("imagens") or []
    alvo = next((i for i in imgs if i["id"] == iid), None)
    if not alvo:
        raise HTTPException(404, "Imagem inexistente.")
    if alvo["tipo"] != "montagem":
        raise HTTPException(422, "Só as montagens sobre fotografia precisam de aprovação.")
    alvo["aprovada"] = bool(body.aprovada)
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user["user_id"]}, {"$set": {"imagens": imgs}})
    return {"ok": True, "id": iid, "aprovada": alvo["aprovada"]}


@router.get("/processos/{pid}/imagens")
async def listar_imagens(pid: str, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    return {"job": d.get("imagens_job"), "desatualizadas": bool(d.get("imagens_desatualizadas")),
            "imagens": [{**i, "url": f"/api/urbanismo-auto/processos/{pid}/imagens/{i['id']}.jpg"} for i in d.get("imagens") or []]}


@router.get("/processos/{pid}/imagens/{iid}.jpg")
async def obter_imagem(pid: str, iid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    if not any(i["id"] == iid for i in d.get("imagens") or []):
        raise HTTPException(404, "Imagem inexistente.")
    from engines.object_storage import get_object
    data, _ = await run_in_threadpool(get_object, _img_key(user["user_id"], pid, iid))
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


async def simulacoes(d: Dict[str, Any]) -> list:
    """Imagens para as peças desenhadas e o ZIP: só fotorrealistas VERIFICADAS (exteriores sem verificação → vista exata;
    interiores sem verificação ficam de fora), planta humanizada, antes/depois e montagens APROVADAS pelo cliente."""
    from engines.object_storage import get_object
    escolha = []
    imgs = d.get("imagens") or []
    if d.get("imagens_desatualizadas"):
        return []
    for v in ORDEM_DOSSIER:
        fr = next((i for i in imgs if i["vista"] == v and i["tipo"] == "fotorrealista" and i.get("verificada")), None)
        if not fr and not v.startswith("interior_") and v not in ("perspetiva_entardecer",):
            fr = next((i for i in imgs if i["vista"] == v and i["tipo"] == "exata"), None)
        if fr:
            escolha.append((fr, f"Simulação 3D — {TITULOS_IMG.get(v, v)} (imagem ilustrativa)"))
    i = next((x for x in imgs if x["tipo"] == "implantacao"), None)
    if i:
        escolha.append((i, "Planta de implantação humanizada (vegetação ilustrativa)"))
    for t, tit in (("antes", "Antes — ortofotomapa oficial (DGT)"), ("depois", "Depois — simulação sobre o ortofotomapa (ilustrativa)")):
        i = next((x for x in imgs if x["tipo"] == t), None) or (
            next((x for x in imgs if x["tipo"] == "depois_esquema"), None) if t == "depois" else None)
        if i:
            escolha.append((i, tit))
    for i in imgs:
        if i["tipo"] == "montagem" and i.get("aprovada"):
            escolha.append((i, "Depois — montagem sobre fotografia do terreno (ilustrativa, aprovada pelo requerente)"))
    out = []
    for k, (i, tit) in enumerate(escolha):
        try:
            data, _ = await run_in_threadpool(get_object, _img_key(d["user_id"], d["processo_id"], i["id"]))
        except Exception:  # noqa: BLE001
            continue
        out.append({"code": "SIMULACOES_3D", "title": tit, "filename": f"simulacao_{k + 1:02d}_{i['vista']}.jpg", "png": data,
                    "data": data})
    return out


@router.post("/dossier-completo")
async def dossier_completo(body: PedidoIn, user=Depends(current_user)) -> dict:
    """UMA frase → tudo: processo completo verificado + imagens realistas + ligações para o PDF e o ZIP.
    Pensado para pessoas sem conhecimentos técnicos, para o Assistente e para a Aurora (uma só chamada)."""
    pedido = {k: v for k, v in body.model_dump(exclude_none=True).items() if v != ""}
    if body.requerente:
        pedido["requerente"] = body.requerente.model_dump()
    if not (pedido.get("texto") or pedido.get("morada")):
        raise HTTPException(422, "Escreva o que pretende e a morada do terreno.")
    job_id = "auto_" + uuid.uuid4().hex[:12]
    await db.urbanismo_auto_jobs.insert_one({"job_id": job_id, "user_id": user["user_id"], "estado": "a_correr", "etapas": [],
                                             "created_at": _now(), "tipo": "dossier_completo",
                                             "pedido": {k: v for k, v in pedido.items() if k != "requerente"}})

    async def emit(etapa, detalhe):
        await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$push": {"etapas": {"etapa": etapa, "detalhe": str(detalhe)[:300],
                                                                                          "at": _now()}}})

    async def run():
        try:
            res = await executar_e_gravar(pedido, user, emit=emit)
            if res.get("ok") and res.get("processo_id"):
                pid = res["processo_id"]
                await emit("imagens", "a criar as imagens realistas")
                try:
                    im = await gerar_imagens(pid, user, None, True)
                    res["imagens"] = im["imagens"]
                except Exception as e:  # noqa: BLE001
                    res["imagens_erro"] = str(getattr(e, "detail", e))[:200]
                res["ligacoes"] = {"pagina": f"/urbanismo/processos/{pid}",
                                   "pecas_desenhadas_pdf": f"/api/urbanismo-auto/processos/{pid}/pecas-desenhadas.pdf",
                                   "processo_zip": f"/api/urbanismo-auto/processos/{pid}/export.zip"}
            await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$set": {"estado": "concluido", "resultado": res,
                                                                                 "finished_at": _now()}})
        except Exception as e:  # noqa: BLE001
            log.exception("dossier completo falhou")
            await db.urbanismo_auto_jobs.update_one({"job_id": job_id}, {"$set": {"estado": "erro", "erro": str(e)[:300]}})
    t = asyncio.create_task(run())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"ok": True, "job_id": job_id, "estado": "a_correr", "etapas_previstas": P.ETAPAS + ["imagens"],
            "acompanhar": f"/api/urbanismo-auto/pedidos/{job_id}",
            "nota": "A preparar o processo completo e as imagens (2 a 5 minutos)."}
