"""Execução de obra — API: assessor de voz, mapa de avanço por zona (sobre a planta), tesouraria da obra e câmaras.

Integrada na ficha da obra (titular) e no portal dos intervenientes, com o MESMO contexto e os mesmos perfis
que a Obra colaborativa e a Gestão de obra:
  * titular da conta ........................ /api/chantiers/{chantier_id}/execucao/...
  * intervenientes convidados (portal) ....... /api/portal/{ref}/execucao/...   (só leitura: mapa e câmaras partilhadas)
O assessor de voz, a tesouraria e as alterações só existem do lado do titular (dados internos da empresa).

O assessor NUNCA grava sozinho: devolve propostas que o utilizador revê e confirma; a gravação passa pelas rotas
normais (diário, stock, qualidade e segurança, pedidos de esclarecimento, avanço), com as mesmas regras e histórico.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, pro_required
from engines import obra_execucao as ox
from engines import obra_execucao_txt as TX
from engines import obra_gestao as og
from engines import storage
from routes import obra_colab as colab
from routes.obra_colab import Ctx, ctx_portal, ctx_pro

logger = logging.getLogger(__name__)

pro_router = APIRouter(prefix="/chantiers", tags=["obra-execucao-pro"], dependencies=[Depends(pro_required)])
portal_router = APIRouter(prefix="/portal", tags=["obra-execucao-portal"])

LEITURA_MAPA = (og.DONO, og.FISCAL, og.ARQUITETO, og.GESTOR)
LEITURA_CAMARAS = (og.DONO, og.FISCAL, og.GESTOR)
IA_ASSESSOR_DIA = 80          # interpretações por IA por obra e por dia (a interpretação local é ilimitada)
MAX_MOVIMENTOS = 2000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _gestor(ctx: Ctx) -> bool:
    return og.GESTOR in ctx.roles


def _pode(ctx: Ctx, perfis: tuple) -> bool:
    return any(r in perfis for r in ctx.roles)


def _owner(ctx: Ctx) -> str:
    return ctx.chantier["user_id"]


async def _hist(ctx: Ctx, acao: str, ref: str = "", **extra) -> None:
    try:
        texto = TX.HISTORICO.get(acao, acao).format(ref=ref, **extra)
        await db.obra_historico.insert_one({"hist_id": f"h_{secrets.token_hex(6)}", "chantier_id": ctx.cid, "at": _now(),
                                            "acao": acao, "quem": ctx.who(), "texto": texto, "ref": ref})
    except Exception as e:  # noqa: BLE001
        logger.info("obra_execucao: histórico não registado: %s", e)


async def _ctx_gestor(chantier_id: str, user=Depends(current_user)) -> Ctx:
    return await ctx_pro(chantier_id, user)


# ====================================================================== modelos
class InterpretarIn(BaseModel):
    texto: str = Field(..., max_length=ox.MAX_TEXTO + 1)
    data: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    usar_ia: bool = True


class PisoIn(BaseModel):
    piso_id: Optional[str] = Field(None, max_length=40)
    nome: str = Field(..., max_length=80)


class RetIn(BaseModel):
    x: float = Field(..., ge=0, le=100)
    y: float = Field(..., ge=0, le=100)
    w: float = Field(..., gt=0, le=100)
    h: float = Field(..., gt=0, le=100)


class ZonaIn(BaseModel):
    zona_id: Optional[str] = Field(None, max_length=40)
    piso_id: str = Field(..., max_length=40)
    nome: str = Field(..., max_length=80)
    ret: Optional[RetIn] = None
    area_m2: Optional[float] = Field(None, ge=0, le=1_000_000)


class AtividadeIn(BaseModel):
    atividade_id: Optional[str] = Field(None, max_length=40)
    nome: str = Field(..., max_length=80)
    peso: float = Field(1, gt=0, le=100)


class EstruturaIn(BaseModel):
    pisos: list[PisoIn] = Field(default_factory=list, max_length=ox.MAX_PISOS)
    zonas: list[ZonaIn] = Field(default_factory=list, max_length=ox.MAX_ZONAS)
    atividades: list[AtividadeIn] = Field(default_factory=list, max_length=ox.MAX_ATIVIDADES)
    expected_version: int = Field(0, ge=0)


class AvancoItemIn(BaseModel):
    zona_id: str = Field(..., max_length=40)
    atividade_id: str = Field(..., max_length=40)
    pct: float = Field(..., ge=0, le=100)
    nota: str = Field("", max_length=500)


class AvancoIn(BaseModel):
    itens: list[AvancoItemIn] = Field(..., min_length=1, max_length=400)
    origem: Literal["manual", "assessor"] = "manual"


class MovTesIn(BaseModel):
    tipo: Literal["entrada", "saida"]
    valor: float = Field(..., gt=0, le=1e9)
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    realizado: bool = False
    categoria: str = Field("outro", max_length=30)
    descricao: str = Field("", max_length=200)
    contraparte: str = Field("", max_length=120)


class TesCfgIn(BaseModel):
    prazo_fornecedor: int = Field(30, ge=0, le=180)
    saldo_inicial: float = Field(0, ge=-1e9, le=1e9)


class CamaraIn(BaseModel):
    camara_id: Optional[str] = Field(None, max_length=40)
    nome: str = Field("", max_length=80)
    url: str = Field(..., max_length=800)
    tipo: Literal["imagem", "video", "embed"] = "imagem"
    atualizar_s: int = Field(30, ge=5, le=600)
    partilhar: bool = False
    zona: str = Field("", max_length=80)


class CamarasIn(BaseModel):
    camaras: list[CamaraIn] = Field(default_factory=list, max_length=ox.MAX_CAMARAS)


# ====================================================================== mapa: acesso aos dados
async def _mapa(ctx: Ctx) -> dict:
    m = await db.obra_mapa.find_one({"chantier_id": ctx.cid}, {"_id": 0})
    return m or {"chantier_id": ctx.cid, "pisos": [], "zonas": [], "atividades": [], "progresso": {}, "versao": 0}


def _mapa_pub(m: dict, gestor: bool) -> dict:
    pisos = [{k: v for k, v in p.items() if k != "planta"} | {"tem_planta": bool(p.get("planta"))} for p in m.get("pisos") or []]
    prog = {k: {kk: v.get(kk) for kk in ("pct", "at", "por_nome")} for k, v in (m.get("progresso") or {}).items() if isinstance(v, dict)}
    out = {"pisos": pisos, "zonas": m.get("zonas") or [], "atividades": m.get("atividades") or [], "progresso": prog,
           "versao": m.get("versao", 0), "resumo": ox.resumo_mapa(m),
           "modelos": {k: v["label"] for k, v in TX.MODELOS_ATIVIDADES.items()}, "pode_editar": gestor}
    for z in out["resumo"]["zonas"]:
        z["cor"] = ox.cor_avanco(z["avanco"])
    return out


# ====================================================================== rotas partilhadas (titular + portal)
def _mount(router: APIRouter, b: str, dep) -> None:
    g = b + "/execucao"

    @router.get(g)
    async def visao(ctx: Ctx = Depends(dep)):
        ge = _gestor(ctx)
        return {"capacidades": {"mapa.ver": _pode(ctx, LEITURA_MAPA), "mapa.editar": ge, "camaras.ver": _pode(ctx, LEITURA_CAMARAS),
                                "camaras.editar": ge, "assessor": ge, "tesouraria": ge},
                "categorias_tesouraria": TX.CATEGORIAS_TES, "lang": TX.LANG}

    @router.get(g + "/mapa")
    async def mapa_ver(ctx: Ctx = Depends(dep)):
        if not _pode(ctx, LEITURA_MAPA):
            raise HTTPException(403, TX.T["perfil"])
        return _mapa_pub(await _mapa(ctx), _gestor(ctx))

    @router.get(g + "/mapa/planta/{piso_id}")
    async def mapa_planta(piso_id: str, ctx: Ctx = Depends(dep)):
        if not _pode(ctx, LEITURA_MAPA):
            raise HTTPException(403, TX.T["perfil"])
        m = await _mapa(ctx)
        p = next((p for p in m.get("pisos") or [] if p["piso_id"] == piso_id), None)
        if not p:
            raise HTTPException(404, TX.T["piso_nao_encontrado"])
        if not p.get("planta"):
            raise HTTPException(404, TX.T["sem_planta"])
        return await colab._download(p["planta"])

    @router.get(g + "/camaras")
    async def camaras_ver(ctx: Ctx = Depends(dep)):
        if not _pode(ctx, LEITURA_CAMARAS):
            raise HTTPException(403, TX.T["perfil"])
        cfg = await db.obra_gestao_cfg.find_one({"chantier_id": ctx.cid}, {"_id": 0, "camaras": 1}) or {}
        cams = cfg.get("camaras") or []
        if not _gestor(ctx):
            cams = [c for c in cams if c.get("partilhar")]
        return {"itens": cams, "hosts_embed": sorted({h.removeprefix("www.") for h in TX.EMBED_HOSTS})}


_mount(pro_router, "/{chantier_id}", _ctx_gestor)
_mount(portal_router, "/{ref}", ctx_portal)


# ====================================================================== mapa: escrita (titular)
@pro_router.put("/{chantier_id}/execucao/mapa/estrutura")
async def mapa_estrutura(body: EstruturaIn, ctx: Ctx = Depends(_ctx_gestor)):
    m = await _mapa(ctx)
    if m.get("versao", 0) != body.expected_version:
        raise HTTPException(409, TX.T["versao"])
    plantas = {p["piso_id"]: p.get("planta") for p in m.get("pisos") or [] if p.get("planta")}
    pisos = [{**p.model_dump(), **({"planta": plantas[p.piso_id]} if p.piso_id in plantas else {})} for p in body.pisos]
    erro, est = ox.estrutura_valida(pisos, [z.model_dump() for z in body.zonas], [a.model_dump() for a in body.atividades])
    if erro:
        raise HTTPException(422, TX.T["estrutura_invalida"].format(erro=erro))
    zids = {z["zona_id"] for z in est["zonas"]}
    aids = {a["atividade_id"] for a in est["atividades"]}
    prog = {k: v for k, v in (m.get("progresso") or {}).items() if k.split("|")[0] in zids and k.split("|")[-1] in aids}
    q = {"chantier_id": ctx.cid, "versao": body.expected_version} if m.get("versao") else {"chantier_id": ctx.cid}
    novo = {**est, "progresso": prog, "chantier_id": ctx.cid, "updated_at": _now()}
    if m.get("versao"):
        r = await db.obra_mapa.update_one(q, {"$set": novo, "$inc": {"versao": 1}})
        if not r.matched_count:
            raise HTTPException(409, TX.T["versao"])
    else:
        if await db.obra_mapa.find_one({"chantier_id": ctx.cid}, {"_id": 1}):
            raise HTTPException(409, TX.T["versao"])
        await db.obra_mapa.insert_one({**novo, "versao": 1})
    await _hist(ctx, "mapa.estrutura")
    return _mapa_pub(await _mapa(ctx), True)


@pro_router.get("/{chantier_id}/execucao/mapa/modelo/{chave}")
async def mapa_modelo(chave: str, ctx: Ctx = Depends(_ctx_gestor)):
    itens = ox.modelo_atividades(chave)
    if not itens:
        raise HTTPException(404, TX.T["nao_encontrado"])
    return {"atividades": itens}


@pro_router.post("/{chantier_id}/execucao/mapa/planta/{piso_id}", status_code=201)
async def mapa_planta_enviar(piso_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(_ctx_gestor)):
    m = await _mapa(ctx)
    p = next((p for p in m.get("pisos") or [] if p["piso_id"] == piso_id), None)
    if not p:
        raise HTTPException(404, TX.T["piso_nao_encontrado"])
    meta = await colab._store(ctx.cid, "execucao_plantas", ctx.actor_id, file, colab.ALLOWED_IMAGE)
    r = await db.obra_mapa.update_one({"chantier_id": ctx.cid, "pisos.piso_id": piso_id},
                                      {"$set": {"pisos.$.planta": meta, "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, TX.T["piso_nao_encontrado"])
    await _hist(ctx, "mapa.planta", p["nome"])
    return _mapa_pub(await _mapa(ctx), True)


@pro_router.post("/{chantier_id}/execucao/mapa/avanco")
async def mapa_avanco(body: AvancoIn, ctx: Ctx = Depends(_ctx_gestor)):
    m = await _mapa(ctx)
    zonas = {z["zona_id"]: z for z in m.get("zonas") or []}
    ativ = {a["atividade_id"]: a for a in m.get("atividades") or []}
    upd, registos = {}, []
    quem = ctx.who()
    for it in body.itens:
        if it.zona_id not in zonas:
            raise HTTPException(404, TX.T["zona_nao_encontrada"])
        if it.atividade_id not in ativ:
            raise HTTPException(404, TX.T["atividade_nao_encontrada"])
        chave = f"{it.zona_id}|{it.atividade_id}"
        anterior = float(((m.get("progresso") or {}).get(chave) or {}).get("pct") or 0)
        pct = round(it.pct, 1)
        upd[f"progresso.{chave}"] = {"pct": pct, "at": _now(), "por_nome": quem.get("nome"), "nota": it.nota.strip()}
        registos.append({"reg_id": f"av_{secrets.token_hex(6)}", "chantier_id": ctx.cid, "zona_id": it.zona_id,
                         "atividade_id": it.atividade_id, "zona": zonas[it.zona_id]["nome"], "atividade": ativ[it.atividade_id]["nome"],
                         "pct": pct, "anterior": anterior, "nota": it.nota.strip(), "origem": body.origem, "por": quem, "at": _now()})
    r = await db.obra_mapa.update_one({"chantier_id": ctx.cid}, {"$set": {**upd, "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, TX.T["zona_nao_encontrada"])
    await db.obra_mapa_registos.insert_many([dict(x) for x in registos])
    for x in registos[:20]:
        await _hist(ctx, "mapa.avanco", x["zona"], pct=f"{x['pct']:g}", atividade=x["atividade"])
    return _mapa_pub(await _mapa(ctx), True)


@pro_router.get("/{chantier_id}/execucao/mapa/registos")
async def mapa_registos(zona_id: Optional[str] = None, ctx: Ctx = Depends(_ctx_gestor)):
    q = {"chantier_id": ctx.cid, **({"zona_id": zona_id} if zona_id else {})}
    rows = await db.obra_mapa_registos.find(q, {"_id": 0}).sort("at", -1).to_list(300)
    return {"itens": rows}


@pro_router.get("/{chantier_id}/execucao/mapa.pdf")
async def mapa_pdf(ctx: Ctx = Depends(_ctx_gestor)):
    m = await _mapa(ctx)
    plantas = {}
    for p in m.get("pisos") or []:
        if p.get("planta"):
            try:
                data, _ = await asyncio.to_thread(storage.get_object, p["planta"]["path"])
                plantas[p["piso_id"]] = data
            except Exception:  # noqa: BLE001
                pass
    try:
        from routes.portal import _pv_branding
        branding = await _pv_branding(_owner(ctx))
    except Exception:  # noqa: BLE001
        branding = {}
    from engines.obra_execucao_pdf import mapa_pdf as gerar
    pdf = await asyncio.to_thread(gerar, ctx.chantier, m, plantas, branding)
    from engines.nom_fichier import content_disposition
    from fastapi.responses import Response
    nome = f"Mapa de avanço — {ctx.chantier.get('name') or ctx.chantier.get('ref') or 'obra'}.pdf" if TX.LANG == "pt" \
        else f"Carte d'avancement — {ctx.chantier.get('name') or ctx.chantier.get('ref') or 'chantier'}.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": content_disposition(nome, inline=True)})


# ====================================================================== assessor de voz (titular)
async def _quota(ctx: Ctx) -> bool:
    """True se ainda há interpretações por IA disponíveis hoje (orçamento da conta + teto por obra)."""
    try:
        from engines import usage_meter
        await usage_meter.check_ai_budget(_owner(ctx))
    except HTTPException:
        return False
    except Exception as e:  # noqa: BLE001
        logger.info("orçamento IA não verificado: %s", e)
    dia = _today().isoformat()
    r = await db.obra_ia_quota.find_one_and_update({"chantier_id": ctx.cid, "dia": dia, "chave": "assessor"},
                                                   {"$inc": {"n": 1}, "$setOnInsert": {"criado_em": datetime.now(timezone.utc)}},
                                                   upsert=True, return_document=True)
    if r is None or "n" not in r:
        r = await db.obra_ia_quota.find_one({"chantier_id": ctx.cid, "dia": dia, "chave": "assessor"}) or {"n": 1}
    return int(r["n"]) <= IA_ASSESSOR_DIA


@pro_router.post("/{chantier_id}/execucao/assessor/interpretar")
async def assessor_interpretar(body: InterpretarIn, ctx: Ctx = Depends(_ctx_gestor)):
    texto = (body.texto or "").strip()
    if not texto:
        raise HTTPException(400, TX.T["texto_vazio"])
    if len(texto) > ox.MAX_TEXTO:
        raise HTTPException(400, TX.T["texto_longo"])
    data = body.data or _today().isoformat()
    from engines.obra_gestao import stock_saldos
    movs = await db.obra_stock.find({"chantier_id": ctx.cid}, {"_id": 0, "material": 1, "unidade": 1, "tipo": 1, "quantidade": 1, "data": 1}).to_list(20000)
    materiais = [{"material": s["material"], "unidade": s["unidade"]} for s in stock_saldos(movs)]
    m = await _mapa(ctx)
    zonas, atividades = m.get("zonas") or [], m.get("atividades") or []
    local = ox.interpretar_local(texto, materiais, zonas, atividades)
    res, aviso = local, None
    if body.usar_ia:
        if await _quota(ctx):
            try:
                from engines import ai
                prompt = TX.ASSESSOR_PROMPT.format(
                    data=data, texto=texto,
                    materiais=json.dumps([x["material"] + (f" ({x['unidade']})" if x["unidade"] else "") for x in materiais][:300], ensure_ascii=False),
                    zonas=json.dumps([{"zona_id": z["zona_id"], "nome": z["nome"]} for z in zonas][:400], ensure_ascii=False),
                    atividades=json.dumps([{"atividade_id": a["atividade_id"], "nome": a["nome"]} for a in atividades], ensure_ascii=False))
                raw = await asyncio.wait_for(ai._complete(TX.ASSESSOR_SISTEMA, prompt, feature="obra_assessor"), 60)
                ia = ox.normalizar(ai._json(raw, {}), materiais, zonas, atividades, fonte="ia")
                if ia["propostas"]:
                    res = ia
            except Exception as e:  # noqa: BLE001
                logger.info("assessor: IA indisponível, interpretação local: %s", e)
        else:
            aviso = TX.T["quota_ia"]
    await _hist(ctx, "assessor.interpretar", res["fonte"])
    existente = await db.obra_diario.find_one({"chantier_id": ctx.cid, "data": data}, {"_id": 0, "diario_id": 1, "estado": 1, "versao": 1})
    return {**res, "data": data, "texto": texto, "aviso": aviso, "diario_existente": existente,
            "materiais_conhecidos": len(materiais), "zonas": len(zonas)}


# ====================================================================== tesouraria (titular)
async def _tes_cfg(ctx: Ctx) -> dict:
    cfg = await db.obra_gestao_cfg.find_one({"chantier_id": ctx.cid}, {"_id": 0, "tesouraria": 1}) or {}
    return {"prazo_fornecedor": 30, "saldo_inicial": 0.0, **(cfg.get("tesouraria") or {})}


@pro_router.get("/{chantier_id}/execucao/tesouraria")
async def tesouraria(ctx: Ctx = Depends(_ctx_gestor)):
    uid, c = _owner(ctx), ctx.chantier
    from engines.chantier_costs import ENGAGED, item_amount, supplier_name
    from engines.chantier_scope import labor_scope, purchase_scope
    faturas = await db.pro_documents.find({"user_id": uid, "chantier_id": ctx.cid, "doc_type": "invoice", "trashed_at": None},
                                          {"_id": 0, "doc_id": 1, "number": 1, "title": 1, "status": 1, "payments": 1, "remaining_due": 1,
                                           "totals": 1, "due_date": 1, "issue_date": 1}).to_list(1000)
    encomendas = []
    for o in await db.material_orders.find(await purchase_scope(db, c, uid), {"_id": 0}).to_list(500):
        if o.get("status") not in ENGAGED or (not o.get("chantier_id") and o.get("plan_ids")):
            continue
        valores = [item_amount(it) for it in o.get("items") or []]
        if not valores or any(v is None for v in valores):
            continue
        encomendas.append({"order_id": o.get("order_id"), "supplier": supplier_name(o), "amount": round(sum(valores), 2),
                           "sent_at": o.get("sent_at"), "created_at": o.get("created_at"), "delivery": o.get("delivery") or {}})
    horas = [{"hours": t.get("hours"), "date": str(t.get("clock_in") or "")[:10], "status": t.get("status")}
             for t in await db.hr_timesheets.find(await labor_scope(db, c, uid), {"_id": 0, "hours": 1, "clock_in": 1, "status": 1}).to_list(5000)]
    manuais = await db.obra_tesouraria.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("data", 1).to_list(MAX_MOVIMENTOS)
    cfg = await _tes_cfg(ctx)
    taxa = ((c.get("cost_settings") or {}).get("labor_rate"))
    res = ox.tesouraria(faturas, encomendas, horas, manuais, _today(), taxa_horaria=taxa, prazo_fornecedor=int(cfg["prazo_fornecedor"]))
    si = float(cfg.get("saldo_inicial") or 0)
    if si:
        for mm in res["meses"]:
            mm["saldo"] = round(mm["saldo"] + si, 2)
        for k in ("saldo_atual", "saldo_final_previsto"):
            res["kpis"][k] = round(res["kpis"][k] + si, 2)
        if res["kpis"]["pior_saldo"] is not None:
            res["kpis"]["pior_saldo"] = round(res["kpis"]["pior_saldo"] + si, 2)
    return {**res, "movimentos": manuais, "cfg": cfg, "categorias": TX.CATEGORIAS_TES, "taxa_horaria": taxa}


@pro_router.put("/{chantier_id}/execucao/tesouraria/cfg")
async def tesouraria_cfg(body: TesCfgIn, ctx: Ctx = Depends(_ctx_gestor)):
    await db.obra_gestao_cfg.update_one({"chantier_id": ctx.cid}, {"$set": {"tesouraria": body.model_dump()}}, upsert=True)
    return await tesouraria(ctx)


def _mov_doc(body: MovTesIn) -> dict:
    if not ox.parse_date(body.data):
        raise HTTPException(422, TX.T["movimento_invalido"])
    d = body.model_dump()
    if d["categoria"] not in TX.CATEGORIAS_TES:
        d["categoria"] = "outro"
    d["descricao"], d["contraparte"] = d["descricao"].strip(), d["contraparte"].strip()
    return d


@pro_router.post("/{chantier_id}/execucao/tesouraria/movimentos", status_code=201)
async def tes_criar(body: MovTesIn, ctx: Ctx = Depends(_ctx_gestor)):
    if await db.obra_tesouraria.count_documents({"chantier_id": ctx.cid}) >= MAX_MOVIMENTOS:
        raise HTTPException(400, TX.T["movimento_invalido"])
    doc = {"mov_id": f"tes_{secrets.token_hex(6)}", "chantier_id": ctx.cid, **_mov_doc(body), "por": ctx.who(), "created_at": _now()}
    await db.obra_tesouraria.insert_one(dict(doc))
    await _hist(ctx, "tesouraria.criar", doc["descricao"] or doc["categoria"])
    doc.pop("_id", None)
    return doc


@pro_router.put("/{chantier_id}/execucao/tesouraria/movimentos/{mov_id}")
async def tes_editar(mov_id: str, body: MovTesIn, ctx: Ctx = Depends(_ctx_gestor)):
    d = _mov_doc(body)
    r = await db.obra_tesouraria.update_one({"chantier_id": ctx.cid, "mov_id": mov_id}, {"$set": {**d, "updated_at": _now()}})
    if not r.matched_count:
        raise HTTPException(404, TX.T["nao_encontrado"])
    await _hist(ctx, "tesouraria.editar", d["descricao"] or d["categoria"])
    return await db.obra_tesouraria.find_one({"chantier_id": ctx.cid, "mov_id": mov_id}, {"_id": 0})


@pro_router.delete("/{chantier_id}/execucao/tesouraria/movimentos/{mov_id}")
async def tes_apagar(mov_id: str, ctx: Ctx = Depends(_ctx_gestor)):
    d = await db.obra_tesouraria.find_one({"chantier_id": ctx.cid, "mov_id": mov_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, TX.T["nao_encontrado"])
    await db.obra_tesouraria.delete_one({"chantier_id": ctx.cid, "mov_id": mov_id})
    await _hist(ctx, "tesouraria.apagar", d.get("descricao") or d.get("categoria"))
    return {"ok": True}


# ====================================================================== câmaras (titular)
@pro_router.put("/{chantier_id}/execucao/camaras")
async def camaras_guardar(body: CamarasIn, ctx: Ctx = Depends(_ctx_gestor)):
    out, ids = [], set()
    for c in body.camaras:
        erro, cam = ox.camara_valida(c.model_dump())
        if erro:
            raise HTTPException(422, erro)
        if cam["camara_id"] in ids:
            cam["camara_id"] = ox.new_id("cam")
        ids.add(cam["camara_id"])
        out.append(cam)
    await db.obra_gestao_cfg.update_one({"chantier_id": ctx.cid}, {"$set": {"camaras": out}}, upsert=True)
    await _hist(ctx, "camaras.editar")
    return {"itens": out, "hosts_embed": sorted({h.removeprefix("www.") for h in TX.EMBED_HOSTS})}
