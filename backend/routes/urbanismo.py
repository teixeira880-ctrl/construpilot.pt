"""Rotas «Urbanismo» (.pt) — editor de volumes, peças desenhadas, quadro de áreas e verificação do PDM.

Processo persistente por utilizador Pro: terreno, enquadramento, parâmetros do plano municipal
(introduzidos pelo utilizador), volumes → planta de implantação, corte, alçado e axonometria
(determinísticos), verificação PDM / RGEU / Código Civil e procedimento RJUE (motor existente
engines.autorizacao_obras_pt). Validação prévia por técnico através de ligação com token.

Sem IA obrigatória: só a memória descritiva pode ser redigida pela IA, a pedido, com texto neutro
de recurso quando a IA não está disponível. Sem chamadas de rede para gerar desenhos ou PDFs.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from core.uploads import ALLOWED_DOCUMENT, ALLOWED_IMAGE, validate_upload
from engines import object_storage as obj
from engines.access import require_level
from engines.nom_fichier import content_disposition, nom_document
from engines.urbanismo_pt import exemplo, pdf as UP, regras as R, volumes as V

router = APIRouter(prefix="/urbanismo", tags=["urbanismo"], dependencies=[Depends(require_level("pro"))])
public_router = APIRouter(prefix="/publico/urbanismo-validacao", tags=["urbanismo-publico"])

PECA_MAX_MB = 25
PECA_TIPOS = ["application/pdf", "image/png", "image/jpeg", "image/webp"]
DESENHOS = {"planta-implantacao": "PLANTA_IMPLANTACAO", "corte": "CORTES", "alcado": "ALCADOS", "axonometria": "AXONOMETRIA"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ modelos ----
class TerrenoIn(BaseModel):
    morada: str = Field(default="", max_length=240)
    codigo_postal: str = Field(default="", max_length=20)
    concelho: str = Field(default="", max_length=80)
    freguesia: str = Field(default="", max_length=120)
    artigo_matricial: str = Field(default="", max_length=80)
    descricao_predial: str = Field(default="", max_length=80)
    area_terreno_m2: Optional[float] = Field(default=None, ge=0, le=10_000_000)


class RequerenteIn(BaseModel):
    nome: str = Field(default="", max_length=160)
    nif: str = Field(default="", max_length=20)
    morada: str = Field(default="", max_length=240)
    telefone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)


class EnquadramentoIn(BaseModel):
    zona_protegida: bool = False
    imovel_classificado: bool = False
    confina_via_publica: bool = False
    tem_edificacao_principal: bool = False
    tem_pdm_com_parametros: bool = False
    tem_loteamento_pip: bool = False
    zona_urbana_consolidada: bool = False
    area_construcao_existente_m2: Optional[float] = Field(default=None, ge=0, le=1_000_000)


class PdmIn(BaseModel):
    plano: str = Field(default="", max_length=300)
    classe_espaco: str = Field(default="", max_length=300)
    fonte_artigos: str = Field(default="", max_length=300)
    iu_max: Optional[float] = Field(default=None, ge=0, le=50)
    io_max_pct: Optional[float] = Field(default=None, ge=0, le=100)
    altura_fachada_max_m: Optional[float] = Field(default=None, ge=0, le=500)
    altura_total_max_m: Optional[float] = Field(default=None, ge=0, le=500)
    n_pisos_max: Optional[int] = Field(default=None, ge=0, le=200)
    afastamento_frontal_min_m: Optional[float] = Field(default=None, ge=0, le=500)
    afastamento_lateral_min_m: Optional[float] = Field(default=None, ge=0, le=500)
    afastamento_tardoz_min_m: Optional[float] = Field(default=None, ge=0, le=500)
    lugares_por_fogo: Optional[float] = Field(default=None, ge=0, le=20)
    lugares_por_100m2: Optional[float] = Field(default=None, ge=0, le=50)
    altura_muro_max_m: Optional[float] = Field(default=None, ge=0, le=50)
    afastamento_piscina_min_m: Optional[float] = Field(default=None, ge=0, le=100)


class BlockIn(BaseModel):
    name: str = Field(default="Anexo", max_length=40)
    l_m: float = Field(default=4, ge=0.5, le=200)
    w_m: float = Field(default=3, ge=0.5, le=200)
    x_m: float = Field(default=0, ge=0, le=1000)
    y_m: float = Field(default=0, ge=0, le=1000)
    h_m: Optional[float] = Field(default=None, ge=0, le=30)


class VolumeIn(BaseModel):
    shape: str = Field(default="rectangle", pattern="^(rectangle|L|T)$")
    plot_l_m: float = Field(default=20, ge=1, le=1000)
    plot_w_m: float = Field(default=15, ge=1, le=1000)
    footprint_l_m: float = Field(default=8, ge=1, le=500)
    footprint_w_m: float = Field(default=6, ge=1, le=500)
    wing_l_m: float = Field(default=0, ge=0, le=500)
    wing_w_m: float = Field(default=0, ge=0, le=500)
    levels: int = Field(default=1, ge=1, le=20)
    storey_h_m: float = Field(default=2.8, ge=2.0, le=8.0)
    espessura_laje_m: float = Field(default=0.30, ge=0, le=1.0)
    total_h_m: float = Field(default=0, ge=0, le=200)
    roof_type: str = Field(default="duas_aguas", pattern="^(duas_aguas|uma_agua|plana)$")
    setback_front_m: float = Field(default=5, ge=0, le=500)
    setback_side_m: float = Field(default=3, ge=0, le=500)
    blocks: list[BlockIn] = Field(default_factory=list, max_length=6)
    uso: str = Field(default="habitacao", pattern="^(habitacao|comercio|apoio)$")
    n_fogos: Optional[int] = Field(default=None, ge=0, le=1000)
    lugares_previstos: Optional[int] = Field(default=None, ge=0, le=5000)
    area_construcao_m2: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    distancia_alinhamento_fronteiro_m: Optional[float] = Field(default=None, ge=0, le=1000)


class ProcessoIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    tipo_obra: str = Field(default="moradia_nova", pattern="^(moradia_nova|ampliacao|anexo|piscina|muro)$")
    requerente: RequerenteIn = Field(default_factory=RequerenteIn)
    terreno: TerrenoIn = Field(default_factory=TerrenoIn)
    enquadramento: EnquadramentoIn = Field(default_factory=EnquadramentoIn)
    pdm: PdmIn = Field(default_factory=PdmIn)
    parametros: dict = Field(default_factory=dict)
    volume: Optional[VolumeIn] = None


class ProcessoPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    tipo_obra: Optional[str] = Field(default=None, pattern="^(moradia_nova|ampliacao|anexo|piscina|muro)$")
    requerente: Optional[RequerenteIn] = None
    terreno: Optional[TerrenoIn] = None
    enquadramento: Optional[EnquadramentoIn] = None
    pdm: Optional[PdmIn] = None
    parametros: Optional[dict] = None
    memoria_texto: Optional[str] = Field(default=None, max_length=12000)


_PARAM_NUM = ("comprimento_m", "altura_m", "portao_largura_m", "portao_posicao_m", "largura_m",
              "profundidade_m", "distancia_limites_m", "cobertura_h_m")
_PARAM_BOOL = ("capeamento", "portao", "cobertura")
_PARAM_SEL = {"implantacao": set(V.IMPLANTACOES_MURO), "material": set(V.MATERIAIS_MURO), "subtipo": {"vedacao", "suporte"}}


def _clean_params(p: dict | None) -> dict:
    """Parâmetros de muro / piscina: só chaves conhecidas, números ≥ 0, sem valores inventados."""
    out: dict = {}
    for k, v in (p or {}).items():
        if k in _PARAM_NUM:
            try:
                f = float(v)
                if 0 <= f <= 1000:
                    out[k] = f
            except (TypeError, ValueError):
                continue
        elif k in _PARAM_BOOL:
            out[k] = bool(v)
        elif k in _PARAM_SEL and v in _PARAM_SEL[k]:
            out[k] = v
    return out


def _volume_dict(body: VolumeIn) -> dict:
    vol = body.model_dump()
    vol["blocks"] = [b for b in vol.get("blocks") or []]
    return vol


# ------------------------------------------------------------------ helpers ----
async def _owned(pid: str, user_id: str) -> dict:
    d = await db.urbanismo_processos.find_one({"processo_id": pid, "user_id": user_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Processo não encontrado.")
    return d


async def _set(pid: str, user_id: str, patch: dict) -> None:
    patch["updated_at"] = _now()
    await db.urbanismo_processos.update_one({"processo_id": pid, "user_id": user_id}, {"$set": patch})


def _checklist(d: dict, verif: dict) -> dict:
    pecas = d.get("pecas") or {}
    proc = verif["rjue"]["procedimento"]
    gerados = {"PLANTA_IMPLANTACAO", "CORTES", "ALCADOS", "AXONOMETRIA", "QUADRO_AREAS", "MEMORIA", "ESTIMATIVA", "FICHA_ESTATISTICA"}
    if d.get("tipo_obra") in R.TIPOS_EDIFICIO and not d.get("volume"):
        gerados -= {"PLANTA_IMPLANTACAO", "CORTES", "ALCADOS", "AXONOMETRIA", "QUADRO_AREAS"}
    items = []
    for p in R.pecas_exigidas(proc, d.get("tipo_obra")):
        carregada = p["code"] in pecas
        auto = p["origem"] == "auto" and p["code"] in gerados
        items.append({**p, "carregada": carregada, "gerada": auto and not carregada, "ok": carregada or auto})
    falta = [i for i in items if i["required"] and not i["ok"]]
    return {"procedimento": proc, "procedimento_label": R.PROCEDIMENTO_LABEL.get(proc, proc), "items": items,
            "em_falta": falta, "completo": not falta, "fonte": R.FONTES["PORTARIA_71A_2024"]}


def _public(d: dict) -> dict:
    out = {k: d.get(k) for k in ("processo_id", "title", "tipo_obra", "requerente", "terreno", "enquadramento", "pdm",
                                 "parametros", "volume", "memoria_texto", "status", "created_at", "updated_at")}
    verif = R.verificar(d)
    out["tipo_obra_label"] = R.TIPOS_OBRA.get(d.get("tipo_obra"), d.get("tipo_obra"))
    out["verificacao"] = verif
    out["checklist"] = _checklist(d, verif)
    out["pecas"] = [{"code": k, **{kk: vv for kk, vv in v.items() if kk != "storage_path"}} for k, v in (d.get("pecas") or {}).items()]
    val = d.get("validacao")
    out["validacao"] = {k: val.get(k) for k in ("status", "tecnico_nome", "tecnico_email", "share_url", "signatario",
                                                "ordem", "numero_inscricao", "comentario", "decided_at", "email_sent")} if val else None
    return out


def _new_doc(user_id: str, body: dict) -> dict:
    vol = body.get("volume")
    return {"processo_id": "urb_" + uuid.uuid4().hex[:12], "user_id": user_id,
            "title": (body.get("title") or "Processo").strip(), "tipo_obra": body.get("tipo_obra") or "moradia_nova",
            "requerente": body.get("requerente") or {}, "terreno": body.get("terreno") or {},
            "enquadramento": body.get("enquadramento") or {}, "pdm": body.get("pdm") or {},
            "parametros": _clean_params(body.get("parametros")), "volume": vol,
            "memoria_texto": None, "pecas": {}, "validacao": None, "status": "rascunho",
            "created_at": _now(), "updated_at": _now()}


# ------------------------------------------------------------------ configuração ----
@router.get("/config")
async def config(user=Depends(current_user)) -> dict:
    return {"tipos_obra": R.TIPOS_OBRA, "tipos_edificio": sorted(R.TIPOS_EDIFICIO), "usos": R.USOS,
            "coberturas": V.ROOF_TYPES, "pdm_campos": R.PDM_CAMPOS, "materiais_muro": V.MATERIAIS_MURO,
            "implantacoes_muro": V.IMPLANTACOES_MURO, "fontes": R.FONTES, "procedimentos": R.PROCEDIMENTO_LABEL,
            "pecas": {k: {"label": v[0], "origem": v[1]} for k, v in R.PECAS.items()}, "aviso": R.AVISO,
            "pagina_rjue": "/particulares/autorizacao-obras"}


@router.post("/verificar")
async def verificar_sem_gravar(body: ProcessoIn, user=Depends(current_user)) -> dict:
    """Verificação imediata (sem persistência) — útil para pré-visualizar antes de gravar."""
    d = body.model_dump()
    d["parametros"] = _clean_params(d.get("parametros"))
    return R.verificar(d)


# ------------------------------------------------------------------ processos ----
@router.post("/processos")
async def criar(body: ProcessoIn, user=Depends(current_user)) -> dict:
    d = _new_doc(user["user_id"], body.model_dump())
    await db.urbanismo_processos.insert_one(dict(d))
    return _public(d)


@router.post("/processos/exemplo")
async def criar_exemplo(user=Depends(current_user)) -> dict:
    """Cria o processo de exemplo fictício (funciona sem rede nem IA)."""
    ex = ProcessoIn(**exemplo.processo_exemplo()).model_dump()
    d = _new_doc(user["user_id"], ex)
    await db.urbanismo_processos.insert_one(dict(d))
    return _public(d)


@router.get("/processos")
async def listar(user=Depends(current_user)) -> dict:
    docs = await db.urbanismo_processos.find({"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(200)
    out = []
    for x in docs:
        try:
            proc = R.verificar(x)["rjue"]["procedimento"]
        except Exception:  # noqa: BLE001
            proc = None
        out.append({"processo_id": x["processo_id"], "title": x.get("title"), "tipo_obra": x.get("tipo_obra"),
                    "tipo_obra_label": R.TIPOS_OBRA.get(x.get("tipo_obra"), x.get("tipo_obra")),
                    "procedimento": proc, "procedimento_label": R.PROCEDIMENTO_LABEL.get(proc, proc),
                    "status": x.get("status"), "created_at": x.get("created_at")})
    return {"processos": out}


@router.get("/processos/{pid}")
async def obter(pid: str, user=Depends(current_user)) -> dict:
    return _public(await _owned(pid, user["user_id"]))


@router.patch("/processos/{pid}")
async def atualizar(pid: str, body: ProcessoPatch, user=Depends(current_user)) -> dict:
    await _owned(pid, user["user_id"])
    patch: dict = {}
    data = body.model_dump(exclude_unset=True)
    for k in ("title", "tipo_obra", "requerente", "terreno", "enquadramento", "pdm", "memoria_texto"):
        if k in data and data[k] is not None:
            patch[k] = data[k].strip() if isinstance(data[k], str) else data[k]
    if data.get("parametros") is not None:
        patch["parametros"] = _clean_params(data["parametros"])
    await _set(pid, user["user_id"], patch)
    return _public(await _owned(pid, user["user_id"]))


@router.delete("/processos/{pid}")
async def eliminar(pid: str, user=Depends(current_user)) -> dict:
    await _owned(pid, user["user_id"])
    await db.urbanismo_processos.delete_one({"processo_id": pid, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/processos/{pid}/volume")
async def gravar_volume(pid: str, body: VolumeIn, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    if d.get("tipo_obra") not in R.TIPOS_EDIFICIO:
        raise HTTPException(422, "O editor de volumes aplica-se a construções (moradia, ampliação, anexo).")
    vol = _volume_dict(body)
    if vol["total_h_m"] <= 0:
        vol["total_h_m"] = round(vol["levels"] * vol["storey_h_m"] + (0 if vol["roof_type"] == "plana" else 2.0), 2)
    if vol["total_h_m"] < vol["levels"] * vol["storey_h_m"]:
        raise HTTPException(422, "A altura total não pode ser inferior à altura da fachada (pisos × altura piso a piso).")
    await _set(pid, user["user_id"], {"volume": vol})
    return _public(await _owned(pid, user["user_id"]))


# ------------------------------------------------------------------ desenhos e PDFs ----
def _need_volume(d: dict):
    if d.get("tipo_obra") in R.TIPOS_EDIFICIO and not d.get("volume"):
        raise HTTPException(422, "Defina primeiro os volumes (dimensões do terreno e da construção).")


@router.get("/processos/{pid}/desenhos/{nome}.png")
async def desenho_png(pid: str, nome: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    code = DESENHOS.get(nome)
    if not code:
        raise HTTPException(404, "Desenho desconhecido.")
    _need_volume(d)
    drawings = await run_in_threadpool(UP.desenhos, d, None)
    dw = next((x for x in drawings if x["code"] == code), None)
    if not dw:
        raise HTTPException(422, "Desenho não disponível para este tipo de obra.")
    return Response(content=dw["png"], media_type="image/png")


@router.get("/processos/{pid}/quadro.pdf")
async def quadro_pdf(pid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    _need_volume(d)
    data = await run_in_threadpool(UP.quadro_pdf, d, R.verificar(d))
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Quadro-de-areas", d.get("title")), inline=True)})


@router.get("/processos/{pid}/pecas-desenhadas.pdf")
async def pecas_desenhadas_pdf(pid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    _need_volume(d)
    data = await run_in_threadpool(lambda: UP.pecas_desenhadas_pdf(d, UP.desenhos(d, None)))
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(nom_document("Pecas-desenhadas", d.get("title")), inline=True)})


async def _uploaded(d: dict) -> list[dict]:
    out = []
    for code, p in (d.get("pecas") or {}).items():
        try:
            content, _ct = await run_in_threadpool(obj.get_object, p["storage_path"])
            out.append({"code": code, "filename": p.get("filename") or code, "data": content})
        except Exception:  # noqa: BLE001 — peça ilegível: omitida do ZIP
            continue
    return out


async def _zip(d: dict) -> bytes:
    _need_volume(d)
    up = await _uploaded(d)
    return await run_in_threadpool(UP.export_zip, d, R.verificar(d), up)


@router.get("/processos/{pid}/export.zip")
async def exportar(pid: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    data = await _zip(d)
    await _set(pid, user["user_id"], {"status": "exportado"})
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": content_disposition(nom_document("Processo-urbanismo", d.get("title"), ext="zip"))})


# ------------------------------------------------------------------ memória descritiva (IA opcional) ----
@router.post("/processos/{pid}/memoria")
async def gerar_memoria(pid: str, user=Depends(current_user)) -> dict:
    """Redige a memória descritiva (IA do módulo de autorização; texto neutro se indisponível). Opcional e editável."""
    from engines.autorizacao_obras_pt.dossier import gerar_memoria_descritiva
    d = await _owned(pid, user["user_id"])
    verif = R.verificar(d)
    texto = await gerar_memoria_descritiva(verif["rjue"]["respostas"], verif["rjue"])
    await _set(pid, user["user_id"], {"memoria_texto": texto})
    return {"ok": True, "memoria_texto": texto}


# ------------------------------------------------------------------ peças carregadas ----
@router.post("/processos/{pid}/pecas/{code}")
async def carregar_peca(pid: str, code: str, file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    if code not in R.PECAS:
        raise HTTPException(422, "Peça desconhecida.")
    file = await validate_upload(file, [t for t in PECA_TIPOS if t in ALLOWED_IMAGE + ALLOWED_DOCUMENT], max_mb=PECA_MAX_MB)
    data = await file.read()
    ct = file.content_type or "application/octet-stream"
    ext = "pdf" if ct == "application/pdf" else ct.split("/")[-1].replace("jpeg", "jpg")
    path = f"{obj.APP_NAME}/urbanismo/{user['user_id']}/{pid}/{code}.{ext}"
    try:
        res = await run_in_threadpool(obj.put_object, path, data, ct)
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "Armazenamento indisponível — tente novamente.")
    pecas = dict(d.get("pecas") or {})
    pecas[code] = {"filename": file.filename or f"{code}.{ext}", "content_type": ct, "size": len(data),
                   "storage_path": (res or {}).get("path", path), "uploaded_at": _now()}
    await _set(pid, user["user_id"], {"pecas": pecas})
    return {"ok": True, "peca": {"code": code, **{k: v for k, v in pecas[code].items() if k != "storage_path"}}}


@router.delete("/processos/{pid}/pecas/{code}")
async def remover_peca(pid: str, code: str, user=Depends(current_user)) -> dict:
    d = await _owned(pid, user["user_id"])
    pecas = dict(d.get("pecas") or {})
    pecas.pop(code, None)
    await _set(pid, user["user_id"], {"pecas": pecas})
    return {"ok": True}


@router.get("/processos/{pid}/pecas/{code}/ficheiro")
async def descarregar_peca(pid: str, code: str, user=Depends(current_user)):
    d = await _owned(pid, user["user_id"])
    p = (d.get("pecas") or {}).get(code)
    if not p:
        raise HTTPException(404, "Peça não carregada.")
    content, ct = await run_in_threadpool(obj.get_object, p["storage_path"])
    return Response(content=content, media_type=p.get("content_type") or ct,
                    headers={"Content-Disposition": content_disposition(p.get("filename") or code, inline=True)})


# ------------------------------------------------------------------ validação por técnico ----
class ValidacaoIn(BaseModel):
    tecnico_nome: str = Field(min_length=2, max_length=120)
    tecnico_email: EmailStr
    mensagem: str = Field(default="", max_length=800)


@router.post("/processos/{pid}/validacao")
async def pedir_validacao(pid: str, body: ValidacaoIn, user=Depends(current_user)) -> dict:
    """Cria uma ligação para um técnico (arquiteto / engenheiro) rever o processo e validar ou emitir reservas.

    Não substitui o termo de responsabilidade do autor do projeto (art.º 10.º do RJUE) — esse fluxo
    existe no módulo «Autorização de obras» (subscrição técnica).
    """
    d = await _owned(pid, user["user_id"])
    token = secrets.token_urlsafe(24)
    share = f"/urbanismo/validacao/{token}"
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    link = f"{base}{share}" if base.startswith("http") else share
    await db.urbanismo_validacoes.delete_many({"processo_id": pid, "user_id": user["user_id"], "status": "pendente"})
    val = {"token": token, "processo_id": pid, "user_id": user["user_id"], "status": "pendente",
           "tecnico_nome": body.tecnico_nome.strip(), "tecnico_email": str(body.tecnico_email).lower(),
           "mensagem": body.mensagem.strip(), "signatario": None, "ordem": None, "numero_inscricao": None,
           "comentario": None, "decided_at": None, "created_at": _now(), "share_url": share}
    await db.urbanismo_validacoes.insert_one(dict(val))
    sent = False
    try:
        from engines.emailer import send_email, wrap_html
        html = wrap_html("Processo de urbanismo para revisão",
                         f"<p>Olá {val['tecnico_nome']},</p><p>Foi-lhe pedido que reveja o processo «{d.get('title')}» "
                         f"({R.TIPOS_OBRA.get(d.get('tipo_obra'), '')}) preparado na ConstruPilot.</p>"
                         + (f"<p><i>{val['mensagem']}</i></p>" if val["mensagem"] else "")
                         + "<p>Pode consultar o quadro de áreas, descarregar as peças e validar ou emitir reservas.</p>",
                         cta_url=link if link.startswith("http") else None, cta_label="Rever o processo")
        await send_email(val["tecnico_email"], f"Revisão de processo de urbanismo — {d.get('title')}", html)
        sent = True
    except Exception:  # noqa: BLE001 — o e-mail é um extra; a ligação continua válida
        sent = False
    val["email_sent"] = sent
    await _set(pid, user["user_id"], {"validacao": {k: v for k, v in val.items() if k not in ("token", "user_id")}})
    return {"ok": True, "status": "pendente", "email_sent": sent, "share_url": share, "share_link": link}


async def _validacao(token: str) -> tuple[dict, dict]:
    v = await db.urbanismo_validacoes.find_one({"token": token}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Ligação de validação inválida ou expirada.")
    d = await db.urbanismo_processos.find_one({"processo_id": v["processo_id"], "user_id": v["user_id"]}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Processo não encontrado.")
    return v, d


@public_router.get("/{token}")
async def ver_validacao(token: str) -> dict:
    v, d = await _validacao(token)
    verif = R.verificar(d)
    return {"status": v["status"], "tecnico_nome": v["tecnico_nome"], "mensagem": v.get("mensagem"),
            "processo": d.get("title"), "tipo_obra_label": R.TIPOS_OBRA.get(d.get("tipo_obra")),
            "concelho": (d.get("terreno") or {}).get("concelho"),
            "procedimento_label": R.PROCEDIMENTO_LABEL.get(verif["rjue"]["procedimento"]),
            "quadro": verif["quadro"], "verificacoes": verif["verificacoes"], "resumo": verif["resumo"],
            "parametros_em_falta": verif["parametros_em_falta"],
            "signatario": v.get("signatario"), "ordem": v.get("ordem"), "numero_inscricao": v.get("numero_inscricao"),
            "comentario": v.get("comentario"), "decided_at": v.get("decided_at"), "aviso": R.AVISO,
            "export_url": f"/publico/urbanismo-validacao/{token}/export.zip"}


@public_router.get("/{token}/export.zip")
async def exportar_validacao(token: str):
    _v, d = await _validacao(token)
    data = await _zip(d)
    return Response(content=data, media_type="application/zip", headers={
        "Content-Disposition": content_disposition(nom_document("Processo-urbanismo", d.get("title"), ext="zip"))})


class AssinarIn(BaseModel):
    signatario: str = Field(min_length=2, max_length=120)
    ordem: str = Field(default="", max_length=40)
    numero_inscricao: str = Field(default="", max_length=40)
    decisao: str = Field(pattern="^(validar|reservas)$")
    comentario: str = Field(default="", max_length=1500)


@public_router.post("/{token}/assinar")
async def assinar_validacao(token: str, body: AssinarIn) -> dict:
    v, d = await _validacao(token)
    if v["status"] != "pendente":
        raise HTTPException(409, "Este pedido já foi respondido.")
    if body.decisao == "reservas" and not body.comentario.strip():
        raise HTTPException(422, "Indique as reservas ou o motivo.")
    status = "validado" if body.decisao == "validar" else "reservas"
    patch = {"status": status, "signatario": body.signatario.strip(), "ordem": body.ordem.strip(),
             "numero_inscricao": body.numero_inscricao.strip(), "comentario": body.comentario.strip(), "decided_at": _now()}
    await db.urbanismo_validacoes.update_one({"token": token}, {"$set": patch})
    val = {**(d.get("validacao") or {}), **patch}
    await db.urbanismo_processos.update_one({"processo_id": d["processo_id"], "user_id": d["user_id"]},
                                            {"$set": {"validacao": val, "updated_at": _now()}})
    try:
        from engines.emailer import send_email, wrap_html
        pro = await db.users.find_one({"user_id": d["user_id"]}, {"_id": 0, "email": 1})
        if pro and pro.get("email"):
            lab = "validado" if status == "validado" else "com reservas"
            await send_email(pro["email"], f"Processo de urbanismo {lab} — {d.get('title')}",
                             wrap_html(f"Processo {lab}", f"<p>{patch['signatario']} respondeu ao pedido de revisão do processo "
                                       f"«{d.get('title')}»: {lab}.</p>" + (f"<p>Comentário: {patch['comentario']}</p>" if patch["comentario"] else "")))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "status": status}
