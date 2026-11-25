"""Gestão de obra — API (diário, qualidade e segurança, pedidos de esclarecimento, stock, curva S,
alertas, copiloto, relatório semanal, histórico e webhooks).

Integrada na obra (ficha da obra) e no portal dos intervenientes, com o MESMO contexto e os mesmos perfis
que a Obra colaborativa:
  * titular da conta ........................ /api/chantiers/{chantier_id}/gestao/...
  * intervenientes convidados (portal) ....... /api/portal/{ref}/gestao/...
O stock, o copiloto, o histórico e os custos só existem do lado do titular (dados internos da empresa).
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, pro_required
from engines import obra_gestao as og
from engines import obra_gestao_txt as TX
from engines import storage
from engines import webhooks_saida as wh
from routes import obra_colab as colab
from routes.obra_colab import Ctx, ctx_portal, ctx_pro

logger = logging.getLogger(__name__)

pro_router = APIRouter(prefix="/chantiers", tags=["obra-gestao-pro"], dependencies=[Depends(pro_required)])
portal_router = APIRouter(prefix="/portal", tags=["obra-gestao-portal"])
webhooks_router = APIRouter(prefix="/webhooks-saida", tags=["webhooks-saida"], dependencies=[Depends(pro_required)])

MAX_FOTOS = 30
IMG_TYPES = ["image/png", "image/jpeg", "image/webp"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def _pub(d: Optional[dict]) -> dict:
    d = dict(d or {})
    d.pop("_id", None)
    return d


def _need(ctx: Ctx, cap: str) -> None:
    if not og.can(ctx.roles, cap):
        raise HTTPException(403, TX.T["perfil_recusado"])


def _gestor(ctx: Ctx) -> bool:
    return og.GESTOR in ctx.roles


def _owner(ctx: Ctx) -> str:
    return ctx.chantier["user_id"]


async def _hist(ctx: Ctx, acao: str, ref: str = "", **extra) -> None:
    """Histórico da obra (quem fez o quê, quando). Nunca bloqueia a ação."""
    try:
        tpl = TX.HISTORICO.get(acao, acao)
        await db.obra_historico.insert_one({
            "hist_id": _id("h"), "chantier_id": ctx.cid, "at": _now(), "acao": acao,
            "quem": ctx.who(), "texto": tpl.format(ref=ref, **extra), "ref": ref})
    except Exception as e:  # noqa: BLE001
        logger.info("obra_gestao: histórico não registado: %s", e)


async def _webhook(ctx: Ctx, evento: str, dados: dict) -> None:
    try:
        await wh.disparar(db, _owner(ctx), evento, {"obra": {"id": ctx.cid, "nome": ctx.chantier.get("name"),
                                                             "ref": ctx.chantier.get("ref")}, **dados})
    except Exception as e:  # noqa: BLE001
        logger.info("obra_gestao: webhook não enviado: %s", e)


async def _store_bytes(ctx: Ctx, kind: str, data: bytes, ct: str, filename: str) -> dict:
    path = f"{storage.APP_NAME}/colab/{ctx.cid}/gestao/{kind}/{secrets.token_hex(8)}_{filename}"
    try:
        await asyncio.to_thread(storage.put_object, path, data, ct)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, TX.T["armazenamento"]) from e
    return {"path": path, "filename": filename, "content_type": ct, "size": len(data), "uploaded_at": _now()}


async def _read_file(meta: dict) -> Optional[bytes]:
    try:
        data, _ = await asyncio.to_thread(storage.get_object, meta["path"])
        return data
    except Exception:  # noqa: BLE001
        return None


async def _seq(cid: str, chave: str) -> int:
    """Número sequencial por obra (NC n.º 1, 2, 3… ; PE-001…). Atómico."""
    r = await db.obra_gestao_seq.find_one_and_update({"chantier_id": cid, "chave": chave}, {"$inc": {"n": 1}},
                                                      upsert=True, return_document=True)
    if r is None or "n" not in r:  # alguns simuladores não devolvem o documento após upsert
        r = await db.obra_gestao_seq.find_one({"chantier_id": cid, "chave": chave})
    return int(r["n"])


async def _branding(ctx: Ctx) -> dict:
    try:
        from routes.portal import _pv_branding
        return await _pv_branding(_owner(ctx))
    except Exception:  # noqa: BLE001
        return {}


def _pdf_response(data: bytes, nome: str) -> Response:
    from engines.nom_fichier import content_disposition
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": content_disposition(nome, inline=True)})


# ====================================================================== modelos
class DiarioIn(BaseModel):
    data: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    trabalhos: str = Field("", max_length=8000)
    ocorrencias: str = Field("", max_length=4000)
    entregas: str = Field("", max_length=4000)
    visitas: str = Field("", max_length=4000)
    observacoes: str = Field("", max_length=4000)
    efetivos: list[dict] = Field(default_factory=list, max_length=40)
    usar_meteo: bool = True
    fotos_operarios: list[str] = Field(default_factory=list, max_length=30)   # photo_id dos operários a anexar


class DiarioEditIn(BaseModel):
    trabalhos: Optional[str] = Field(None, max_length=8000)
    ocorrencias: Optional[str] = Field(None, max_length=4000)
    entregas: Optional[str] = Field(None, max_length=4000)
    visitas: Optional[str] = Field(None, max_length=4000)
    observacoes: Optional[str] = Field(None, max_length=4000)
    efetivos: Optional[list[dict]] = Field(None, max_length=40)
    expected_version: int = Field(0, ge=0)


class AssinarIn(BaseModel):
    nome: str = Field(..., min_length=2, max_length=120)
    imagem: str = Field(..., max_length=400_000)       # data URL PNG do traço da assinatura


class TextoIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=4000)


class VistoIn(BaseModel):
    observacao: str = Field("", max_length=2000)


class PublicarIn(BaseModel):
    publicado: bool


class AcaoIn(BaseModel):
    o_que: str = Field("", max_length=600)
    porque: str = Field("", max_length=600)
    quem: str = Field("", max_length=200)
    quem_empresa_id: Optional[str] = Field(None, max_length=60)
    onde: str = Field("", max_length=300)
    quando: str = Field("", max_length=10)
    como: str = Field("", max_length=1000)
    quanto: Optional[float] = Field(None, ge=0, le=10_000_000)


class QseIn(BaseModel):
    tipo: Literal["inspecao", "nao_conformidade", "incidente", "quase_acidente", "dialogo_seguranca", "epi", "ambiente"]
    titulo: str = Field(..., min_length=2, max_length=200)
    descricao: str = Field("", max_length=6000)
    data: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    lote: str = Field("", max_length=120)
    local: str = Field("", max_length=200)
    gravidade: Optional[Literal["baixa", "media", "alta", "critica"]] = None
    empresa_id: Optional[str] = Field(None, max_length=60)
    checklist_modelo: Optional[str] = Field(None, max_length=40)
    checklist: list[dict] = Field(default_factory=list, max_length=120)
    participantes: list[str] = Field(default_factory=list, max_length=200)
    tema: str = Field("", max_length=200)
    dias_baixa: Optional[int] = Field(None, ge=0, le=3650)
    acoes: list[AcaoIn] = Field(default_factory=list, max_length=20)


class QseEditIn(BaseModel):
    titulo: Optional[str] = Field(None, min_length=2, max_length=200)
    descricao: Optional[str] = Field(None, max_length=6000)
    lote: Optional[str] = Field(None, max_length=120)
    local: Optional[str] = Field(None, max_length=200)
    gravidade: Optional[Literal["baixa", "media", "alta", "critica"]] = None
    empresa_id: Optional[str] = Field(None, max_length=60)
    checklist: Optional[list[dict]] = Field(None, max_length=120)
    participantes: Optional[list[str]] = Field(None, max_length=200)
    tema: Optional[str] = Field(None, max_length=200)
    dias_baixa: Optional[int] = Field(None, ge=0, le=3650)


class AcaoEstadoIn(BaseModel):
    estado: Literal["aberta", "em_curso", "feita", "verificada"]
    nota: str = Field("", max_length=1000)


class FecharIn(BaseModel):
    justificacao: str = Field("", max_length=2000)


class RfiIn(BaseModel):
    assunto: str = Field(..., min_length=3, max_length=200)
    pergunta: str = Field(..., min_length=3, max_length=6000)
    lote: str = Field("", max_length=120)
    plano_id: Optional[str] = Field(None, max_length=60)
    destinatario_perfil: Optional[Literal["dono_obra", "fiscalizacao", "arquiteto", "gestor"]] = None
    destinatario_id: Optional[str] = Field(None, max_length=60)
    prazo: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    visibilidade: Literal["todos", "restrito"] = "todos"
    impacto_custo: bool = False
    impacto_prazo: bool = False


class MovimentoIn(BaseModel):
    tipo: Literal["entrada", "saida", "ajuste"]
    material: str = Field(..., min_length=1, max_length=200)
    unidade: str = Field("", max_length=20)
    quantidade: float = Field(..., ge=-1_000_000, le=1_000_000)
    data: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    local: str = Field("", max_length=120)
    nota: str = Field("", max_length=500)


class MinimoIn(BaseModel):
    chave: str = Field(..., max_length=420)
    minimo: Optional[float] = Field(None, ge=0, le=1_000_000)


class RececaoLinhaIn(BaseModel):
    linha: int = Field(..., ge=0, le=2000)
    quantidade: float = Field(..., ge=0, le=1_000_000)
    conforme: bool = True
    nota: str = Field("", max_length=500)


class RececaoIn(BaseModel):
    linhas: list[RececaoLinhaIn] = Field(..., min_length=1, max_length=500)
    data: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    guia_remessa: str = Field("", max_length=80)


class PerguntaIn(BaseModel):
    pergunta: str = Field(..., max_length=2000)


class WebhookIn(BaseModel):
    url: str = Field(..., max_length=500)
    eventos: list[str] = Field(..., min_length=1, max_length=len(wh.EVENTOS))
    ativo: bool = True
    descricao: str = Field("", max_length=120)


# ====================================================================== diário de obra
async def _geo(ctx: Ctx) -> Optional[dict]:
    cfg = await db.obra_gestao_cfg.find_one({"chantier_id": ctx.cid}, {"_id": 0}) or {}
    if cfg.get("geo"):
        return cfg["geo"]
    c = ctx.chantier
    nome = (c.get("city") or "").strip() or (c.get("postal_code") or "").strip()
    if not nome:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as cl:
            g = await cl.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": nome, "count": 1, "language": TX.LANG, "countryCode": TX.PAIS})
            res = (g.json() or {}).get("results") or []
    except Exception as e:  # noqa: BLE001
        logger.info("geocoding falhou: %s", e)
        return None
    if not res:
        return None
    geo = {"lat": res[0]["latitude"], "lon": res[0]["longitude"], "nome": res[0].get("name")}
    await db.obra_gestao_cfg.update_one({"chantier_id": ctx.cid}, {"$set": {"geo": geo}}, upsert=True)
    return geo


async def _meteo(ctx: Ctx, dia: date) -> Optional[dict]:
    """Meteorologia real do dia (Open-Meteo). None se o serviço não responder — nunca se inventa."""
    geo = await _geo(ctx)
    if not geo:
        return None
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as cl:
            r = await cl.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": geo["lat"], "longitude": geo["lon"], "timezone": "auto",
                "daily": "weather_code,temperature_2m_min,temperature_2m_max,precipitation_sum,wind_speed_10m_max",
                "start_date": dia.isoformat(), "end_date": dia.isoformat()})
            daily = (r.json() or {}).get("daily") or {}
    except Exception as e:  # noqa: BLE001
        logger.info("meteo falhou: %s", e)
        return None
    m = og.meteo_do_dia(daily, dia)
    if m:
        m["local"] = geo.get("nome")
        m["obtida_em"] = _now()
    return m


async def _efetivo_auto(ctx: Ctx, dia: date) -> dict:
    """Trabalhadores e horas do ponto (módulo RH) nesse dia, para esta obra."""
    from engines.chantier_scope import labor_scope
    q = await labor_scope(db, ctx.chantier, _owner(ctx))
    q["clock_in"] = {"$regex": f"^{dia.isoformat()}"}
    rows = await db.hr_timesheets.find(q, {"_id": 0, "worker_id": 1, "worker_name": 1, "hours": 1, "status": 1}).to_list(2000)
    horas = 0.0
    for r in rows:
        try:
            horas += float(r.get("hours") or 0)
        except (TypeError, ValueError):
            pass
    nomes = sorted({r.get("worker_name") or "—" for r in rows})
    return {"trabalhadores": len({r.get("worker_id") for r in rows}), "horas": round(horas, 2), "nomes": nomes,
            "pendentes": sum(1 for r in rows if r.get("status") != "validated")}


async def _projetos_rh(ctx: Ctx) -> list[str]:
    rows = await db.projects.find({"user_id": _owner(ctx), "chantier_id": ctx.cid}, {"_id": 0, "project_id": 1}).to_list(200)
    return [r["project_id"] for r in rows if r.get("project_id")] + [ctx.cid]


async def _registos_operarios(ctx: Ctx, dia: date) -> dict:
    ids = await _projetos_rh(ctx)
    base = {"employer_id": _owner(ctx), "project_id": {"$in": ids}, "created_at": {"$regex": f"^{dia.isoformat()}"}}
    notas = await db.hr_notes.find(base, {"_id": 0, "note_id": 1, "worker_name": 1, "type": 1, "message": 1, "created_at": 1}).to_list(200)
    fotos = await db.hr_photos.find(base, {"_id": 0, "photo_id": 1, "worker_name": 1, "caption": 1, "created_at": 1}).to_list(200)
    return {"notas": notas, "fotos": fotos}


async def _entregas(ctx: Ctx, dia: date) -> list[dict]:
    from engines.chantier_scope import purchase_scope
    q = await purchase_scope(db, ctx.chantier, _owner(ctx))
    q["delivery.status"] = {"$in": ["received", "partial"]}
    q["delivery.updated_at"] = {"$regex": f"^{dia.isoformat()}"}
    rows = await db.material_orders.find(q, {"_id": 0, "order_id": 1, "supplier": 1, "delivery": 1}).to_list(100)
    from engines.chantier_costs import supplier_name
    return [{"order_id": r["order_id"], "fornecedor": supplier_name(r), "estado": (r.get("delivery") or {}).get("status")} for r in rows]


async def _diario(ctx: Ctx, diario_id: str) -> dict:
    d = await db.obra_diario.find_one({"diario_id": diario_id, "chantier_id": ctx.cid}, {"_id": 0})
    if not d or (not _gestor(ctx) and not d.get("publicado")):
        raise HTTPException(404, TX.T["nao_encontrado"])
    return d


def _diario_pub(d: dict) -> dict:
    d = _pub(d)
    d["fotos"] = [{"n": i, "filename": f.get("filename"), "origem": f.get("origem")} for i, f in enumerate(d.get("fotos") or [])]
    if d.get("assinatura"):
        d["assinatura"] = {k: v for k, v in d["assinatura"].items() if k != "imagem"}
    return d


async def _snapshot(ctx: Ctx) -> None:
    """Regista o avanço do dia (para a curva S real). Silencioso se não houver planeamento."""
    try:
        sched = await _schedule(ctx)
        if not sched:
            return
        internos = await _custos_internos(ctx)  # mesma ponderação que a curva S
        pesos, _ = og.pesos_tarefas([dict(t) for t in sched["tasks"]], (internos or {}).get("budget_by_lot") or [])
        av = round(sum(pesos[t["id"]] * min(100, max(0, float(t.get("progress") or 0))) for t in sched["tasks"]), 2)
        await db.obra_avanco_snapshots.update_one({"chantier_id": ctx.cid, "data": _today().isoformat()},
                                                  {"$set": {"avanco_pct": av, "at": _now()}}, upsert=True)
    except Exception as e:  # noqa: BLE001
        logger.info("snapshot avanço falhou: %s", e)


# ====================================================================== indicadores (planeamento, custos)
async def _plan(ctx: Ctx) -> Optional[dict]:
    return await db.chantier_plannings.find_one({"chantier_id": ctx.cid, "user_id": _owner(ctx)}, {"_id": 0})


async def _schedule(ctx: Ctx, plan: Optional[dict] = None) -> Optional[dict]:
    from engines import planning as P
    plan = plan or await _plan(ctx)
    if not plan or not plan.get("tasks"):
        return None
    try:
        res = P.compute_schedule(plan, today=_today())
    except Exception as e:  # noqa: BLE001
        logger.info("planeamento não calculado: %s", e)
        return None
    res.pop("_cal", None)
    return res


async def _custos_internos(ctx: Ctx) -> Optional[dict]:
    """Custos da empresa (uso interno: ponderação da curva S). Nunca devolvidos a um interveniente."""
    try:
        from engines.chantier_costs import compute_chantier_costs
        return await compute_chantier_costs(ctx.chantier, _owner(ctx))
    except Exception as e:  # noqa: BLE001
        logger.info("custos não calculados: %s", e)
        return None


async def _custos(ctx: Ctx) -> Optional[dict]:
    """Custos visíveis: só para o titular (margens e custos são dados internos da empresa)."""
    return await _custos_internos(ctx) if _gestor(ctx) else None


async def _custos_datados(ctx: Ctx, costs: dict) -> dict:
    """Custos reais com data: horas validadas × taxa + encomendas comprometidas (data de envio)."""
    rate = (costs.get("labor") or {}).get("rate_used")
    completo = bool((costs.get("labor") or {}).get("complete") and (costs.get("purchases") or {}).get("complete"))
    pontos = []
    if rate:
        for e in costs.get("labor_entries") or []:
            if e.get("status") == "validated" and e.get("hours") is not None and e.get("date"):
                pontos.append((e["date"], float(e["hours"]) * float(rate)))
    ids = [p["order_id"] for p in costs.get("purchase_entries") or [] if p.get("engaged") and p.get("amount") is not None]
    if ids:
        orders = await db.material_orders.find({"order_id": {"$in": ids}}, {"_id": 0, "order_id": 1, "sent_at": 1, "created_at": 1}).to_list(500)
        datas = {o["order_id"]: (o.get("sent_at") or o.get("created_at") or "")[:10] for o in orders}
        for p in costs["purchase_entries"]:
            if p["order_id"] in datas and datas[p["order_id"]]:
                pontos.append((datas[p["order_id"]], float(p["amount"])))
    bac = (costs.get("totals") or {}).get("cost_prev_ht") if (costs.get("totals") or {}).get("coverage", {}).get("complete") else None
    return {"completo": completo and (rate is not None or not costs.get("labor_entries")), "orcamento_custo": bac, "pontos": pontos}


async def _curva(ctx: Ctx) -> dict:
    plan = await _plan(ctx)
    sched = await _schedule(ctx, plan)
    internos = await _custos_internos(ctx)
    snaps = await db.obra_avanco_snapshots.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("data", 1).to_list(2000)
    datados = await _custos_datados(ctx, internos) if (internos and _gestor(ctx)) else None
    res = og.curva_s(sched, (plan or {}).get("baseline"), (internos or {}).get("budget_by_lot") or [], _today(), snaps, datados)
    if not _gestor(ctx):  # o dono / a fiscalização veem o avanço, nunca os custos internos da empresa
        res.pop("orcamento_custo", None)
        res.pop("custo_real_hoje", None)
        res.pop("cpi", None)
        for p in res.get("pontos") or []:
            p.pop("custo_real", None)
            p.pop("custo_real_pct", None)
    return res


async def _alertas(ctx: Ctx) -> list[dict]:
    sched = await _schedule(ctx)
    costs = await _custos(ctx)
    qse = await db.obra_qse.find({"chantier_id": ctx.cid, "estado": {"$ne": "fechado"}}, {"_id": 0}).to_list(2000)
    rfis = await db.obra_rfi.find({"chantier_id": ctx.cid, "estado": "aberto"}, {"_id": 0}).to_list(2000)
    stock = []
    if _gestor(ctx):
        stock = await _stock_saldos(ctx)
    ult = await db.obra_diario.find({"chantier_id": ctx.cid}, {"_id": 0, "data": 1}).sort("data", -1).to_list(1)
    ativo = bool(ult) or ctx.chantier.get("status") in ("en_cours", "em_curso", "in_progress")
    docs = []
    for s in await db.obra_subs.find({"chantier_id": ctx.cid, "estado": "aprovado"}, {"_id": 0}).to_list(300):
        for d in s.get("documentos") or []:
            docs.append({"label": d.get("label") or d.get("key"), "empresa": s.get("empresa_nome") or s.get("nome") or "",
                         "validade": d.get("validade")})
    return og.alertas(hoje=_today(), schedule=sched, lotes=(costs or {}).get("budget_by_lot") if _gestor(ctx) else None,
                      qse=qse, rfis=rfis, stock=stock, ultimo_diario=ult[0]["data"] if ult else None,
                      diario_ativo=ativo, docs_subs=docs)


# ====================================================================== stock
async def _stock_saldos(ctx: Ctx) -> list[dict]:
    movs = await db.obra_stock.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(20000)
    cfg = await db.obra_gestao_cfg.find_one({"chantier_id": ctx.cid}, {"_id": 0}) or {}
    return og.stock_saldos(movs, cfg.get("stock_minimos") or {})


# ====================================================================== rotas partilhadas (titular + portal)
def _mount(router: APIRouter, b: str, dep) -> None:
    g = b + "/gestao"

    @router.get(g)
    async def visao(ctx: Ctx = Depends(dep)):
        partes = await db.chantier_participants.find({"chantier_id": ctx.cid, "status": {"$ne": "revoked"}},
                                                     {"_id": 0, "participant_id": 1, "name": 1, "email": 1, "role": 1,
                                                      "colab_role": 1, "lot": 1}).to_list(500)
        from engines import obra_colab as oc
        intervenientes = [{"id": p["participant_id"], "nome": p.get("name") or p.get("email"), "lote": p.get("lot") or "",
                           "perfil": oc.role_of_participant(p)} for p in partes]
        qse_q = {"chantier_id": ctx.cid, "estado": {"$ne": "fechado"}}
        sc = og.qse_scope(ctx.roles, ctx.empresa_id)
        if sc:
            qse_q.update(sc)
        rfi_q = {"chantier_id": ctx.cid, "estado": "aberto"}
        rs = og.rfi_scope(ctx.roles, ctx.empresa_id, ctx.actor_id)
        if rs:
            rfi_q = {"$and": [rfi_q, rs]}
        return {
            "eu": {**ctx.who(), "gestor": _gestor(ctx), "empresa_id": ctx.empresa_id},
            "capacidades": {**og.capabilities(ctx.roles), "stock": _gestor(ctx), "copiloto": _gestor(ctx), "historico": _gestor(ctx)},
            "obra": {"nome": ctx.chantier.get("name"), "ref": ctx.chantier.get("ref"), "cidade": ctx.chantier.get("city")},
            "intervenientes": intervenientes,
            "contadores": {
                "qse_abertos": await db.obra_qse.count_documents(qse_q) if og.can(ctx.roles, "qse.ver") else 0,
                "rfi_abertos": await db.obra_rfi.count_documents(rfi_q),
                "diario_dias": await db.obra_diario.count_documents(
                    {"chantier_id": ctx.cid, **({} if _gestor(ctx) else {"publicado": True})}) if og.can(ctx.roles, "diario.ver") else 0,
            },
            "referenciais": {
                "qse_tipos": TX.QSE_TIPOS, "gravidade": TX.GRAVIDADE, "qse_estados": TX.QSE_ESTADOS, "acao_estados": TX.ACAO_ESTADOS,
                "campos_5w2h": TX.CAMPOS_5W2H, "lembretes": TX.LEMBRETES, "epi": TX.EPI_ITENS, "dds_temas": TX.DDS_TEMAS,
                "checklists": {k: {"label": v["label"], "itens": v["itens"]} for k, v in TX.CHECKLISTS.items()},
                "tipos_obra": {k: {"label": TX.TIPOS_OBRA_LABEL[k], "fases": v} for k, v in TX.TIPOS_OBRA.items()},
                "rfi_estados": TX.RFI_ESTADOS, "webhook_eventos": list(wh.EVENTOS),
            },
        }

    # ---------------------------------------------------------- diário
    @router.get(g + "/diario")
    async def diario_lista(de: Optional[str] = None, ate: Optional[str] = None, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.ver")
        q: dict = {"chantier_id": ctx.cid}
        if not _gestor(ctx):
            q["publicado"] = True
        if de or ate:
            q["data"] = {k: v for k, v in (("$gte", de), ("$lte", ate)) if v}
        rows = await db.obra_diario.find(q, {"_id": 0}).sort("data", -1).to_list(400)
        return {"itens": [_diario_pub(r) for r in rows]}

    @router.get(g + "/diario/preparar")
    async def diario_preparar(data: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        dia = og.parse_date(data)
        if not dia:
            raise HTTPException(400, TX.T["diario_data"])
        existente = await db.obra_diario.find_one({"chantier_id": ctx.cid, "data": data}, {"_id": 0, "diario_id": 1})
        meteo, efetivo, oper, entregas = await asyncio.gather(_meteo(ctx, dia), _efetivo_auto(ctx, dia),
                                                              _registos_operarios(ctx, dia), _entregas(ctx, dia))
        return {"data": data, "existente": (existente or {}).get("diario_id"), "meteo": meteo, "efetivo_auto": efetivo,
                "operarios": oper, "entregas": entregas}

    @router.post(g + "/diario", status_code=201)
    async def diario_criar(body: DiarioIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        dia = og.parse_date(body.data)
        if not dia:
            raise HTTPException(400, TX.T["diario_data"])
        if dia > _today():
            raise HTTPException(400, TX.T["diario_futuro"])
        if await db.obra_diario.find_one({"chantier_id": ctx.cid, "data": body.data}, {"_id": 1}):
            raise HTTPException(409, TX.T["diario_existe"])
        meteo = await _meteo(ctx, dia) if body.usar_meteo else None
        efetivo = await _efetivo_auto(ctx, dia)
        fotos = []
        if body.fotos_operarios:
            ids = await _projetos_rh(ctx)
            rows = await db.hr_photos.find({"photo_id": {"$in": body.fotos_operarios[:MAX_FOTOS]}, "employer_id": _owner(ctx),
                                            "project_id": {"$in": ids}}, {"_id": 0}).to_list(MAX_FOTOS)
            fotos = [{"path": r["path"], "filename": r.get("caption") or r["photo_id"], "content_type": "image/jpeg",
                      "origem": "operario", "autor": r.get("worker_name"), "uploaded_at": r.get("created_at")} for r in rows if r.get("path")]
        doc = {"diario_id": _id("dia"), "chantier_id": ctx.cid, "data": body.data, "meteo": meteo, "efetivo_auto": efetivo,
               "efetivos": [{"equipa": str(e.get("equipa") or "")[:120], "n": int(e.get("n") or 0)} for e in body.efetivos],
               "trabalhos": body.trabalhos, "ocorrencias": body.ocorrencias, "entregas": body.entregas, "visitas": body.visitas,
               "observacoes": body.observacoes, "fotos": fotos, "estado": "rascunho", "publicado": False, "aditamentos": [],
               "criado_por": ctx.who(), "created_at": _now(), "updated_at": _now(), "versao": 0}
        await db.obra_diario.insert_one(dict(doc))
        await _hist(ctx, "diario.criar", body.data)
        await _snapshot(ctx)
        return _diario_pub(doc)

    @router.get(g + "/diario/{diario_id}")
    async def diario_ver(diario_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.ver")
        return _diario_pub(await _diario(ctx, diario_id))

    @router.put(g + "/diario/{diario_id}")
    async def diario_editar(diario_id: str, body: DiarioEditIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        d = await _diario(ctx, diario_id)
        if d.get("estado") == "assinado":
            raise HTTPException(409, TX.T["diario_assinado"])
        upd = {k: v for k, v in body.model_dump(exclude={"expected_version"}).items() if v is not None}
        if "efetivos" in upd:
            upd["efetivos"] = [{"equipa": str(e.get("equipa") or "")[:120], "n": int(e.get("n") or 0)} for e in upd["efetivos"]]
        upd["updated_at"] = _now()
        r = await db.obra_diario.update_one({"diario_id": diario_id, "estado": "rascunho", "versao": body.expected_version},
                                            {"$set": upd, "$inc": {"versao": 1}})
        if not r.matched_count:
            raise HTTPException(409, TX.T["versao"])
        await _hist(ctx, "diario.editar", d["data"])
        return _diario_pub(await _diario(ctx, diario_id))

    @router.post(g + "/diario/{diario_id}/fotos", status_code=201)
    async def diario_foto(diario_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        d = await _diario(ctx, diario_id)
        if d.get("estado") == "assinado":
            raise HTTPException(409, TX.T["diario_assinado"])
        if len(d.get("fotos") or []) >= MAX_FOTOS:
            raise HTTPException(400, TX.T["foto_limite"])
        meta = await colab._store(ctx.cid, "gestao_diario", ctx.actor_id, file, IMG_TYPES)
        meta["origem"] = "direcao"
        await db.obra_diario.update_one({"diario_id": diario_id, "estado": "rascunho"}, {"$push": {"fotos": meta}, "$set": {"updated_at": _now()}})
        return _diario_pub(await _diario(ctx, diario_id))

    @router.get(g + "/diario/{diario_id}/fotos/{n}")
    async def diario_foto_ver(diario_id: str, n: int, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.ver")
        d = await _diario(ctx, diario_id)
        fotos = d.get("fotos") or []
        if not 0 <= n < len(fotos):
            raise HTTPException(404, TX.T["nao_encontrado"])
        return await colab._download(fotos[n])

    @router.get(g + "/diario/{diario_id}/assinatura")
    async def diario_assinatura_ver(diario_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.ver")
        d = await _diario(ctx, diario_id)
        meta = (d.get("assinatura") or {}).get("imagem")
        if not meta:
            raise HTTPException(404, TX.T["nao_encontrado"])
        return await colab._download(meta)

    @router.post(g + "/diario/{diario_id}/assinar")
    async def diario_assinar(diario_id: str, body: AssinarIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        d = await _diario(ctx, diario_id)
        if d.get("estado") == "assinado":
            raise HTTPException(409, TX.T["diario_assinado"])
        from engines.obra_gestao_pdf import data_url_bytes
        img = data_url_bytes(body.imagem)
        if not img or img[1] != "image/png" or len(img[0]) < 60:
            raise HTTPException(400, TX.T["diario_sem_assinatura"])
        meta = await _store_bytes(ctx, "assinaturas", img[0], "image/png", f"assinatura_{d['data']}.png")
        sig = {"nome": body.nome.strip(), "at": _now(), "por": ctx.who(), "imagem": meta}
        r = await db.obra_diario.update_one({"diario_id": diario_id, "estado": "rascunho"},
                                            {"$set": {"estado": "assinado", "assinatura": sig, "updated_at": _now()}})
        if not r.matched_count:
            raise HTTPException(409, TX.T["diario_assinado"])
        await _hist(ctx, "diario.assinar", d["data"])
        await _webhook(ctx, "diario.assinado", {"data": d["data"], "assinado_por": sig["nome"]})
        await _snapshot(ctx)
        return _diario_pub(await _diario(ctx, diario_id))

    @router.post(g + "/diario/{diario_id}/aditamento", status_code=201)
    async def diario_aditamento(diario_id: str, body: TextoIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        d = await _diario(ctx, diario_id)
        ad = {"texto": body.texto.strip(), "por": ctx.who(), "at": _now()}
        await db.obra_diario.update_one({"diario_id": diario_id}, {"$push": {"aditamentos": ad}})
        await _hist(ctx, "diario.aditamento", d["data"])
        return _diario_pub(await _diario(ctx, diario_id))

    @router.post(g + "/diario/{diario_id}/visto")
    async def diario_visto(diario_id: str, body: VistoIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.visar")
        d = await _diario(ctx, diario_id)
        if d.get("estado") != "assinado":
            raise HTTPException(409, TX.T["diario_nao_assinado"])
        v = {"nome": ctx.name, "por": ctx.who(), "at": _now(), "observacao": body.observacao.strip()}
        await db.obra_diario.update_one({"diario_id": diario_id}, {"$set": {"visto_fiscal": v}})
        await _hist(ctx, "diario.visto", d["data"])
        return _diario_pub(await _diario(ctx, diario_id))

    @router.post(g + "/diario/{diario_id}/publicar")
    async def diario_publicar(diario_id: str, body: PublicarIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.editar")
        d = await _diario(ctx, diario_id)
        await db.obra_diario.update_one({"diario_id": diario_id}, {"$set": {"publicado": body.publicado}})
        await _hist(ctx, "diario.publicar", d["data"])
        return {"ok": True, "publicado": body.publicado}

    @router.get(g + "/diario/{diario_id}/pdf")
    async def diario_pdf(diario_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "diario.ver")
        d = await _diario(ctx, diario_id)
        from engines.obra_gestao_pdf import diario_pdf as build
        fotos = [x for x in await asyncio.gather(*[_read_file(f) for f in (d.get("fotos") or [])[:12]]) if x]
        sig = await _read_file(d["assinatura"]["imagem"]) if (d.get("assinatura") or {}).get("imagem") else None
        pdf = await asyncio.to_thread(build, d, ctx.chantier, await _branding(ctx), fotos, sig)
        from engines.nom_fichier import nom_document
        return _pdf_response(pdf, nom_document(TX.NOME_DOC["diario"], ctx.chantier.get("name"), date=d["data"]))

    # ---------------------------------------------------------- qualidade, segurança e ambiente
    async def _qse(ctx: Ctx, item_id: str) -> dict:
        it = await db.obra_qse.find_one({"item_id": item_id, "chantier_id": ctx.cid}, {"_id": 0})
        if not it or not og.qse_visivel(ctx.roles, ctx.empresa_id, it):
            raise HTTPException(404, TX.T["nao_encontrado"])
        return it

    def _qse_pub(it: dict) -> dict:
        it = _pub(it)
        it["fotos"] = [{"n": i, "filename": f.get("filename")} for i, f in enumerate(it.get("fotos") or [])]
        if it.get("tipo") == "inspecao":
            it["resultado"] = og.inspecao_resultado(it.get("checklist") or [])
        it["acoes_em_atraso"] = len(og.acoes_em_atraso(it, _today()))
        it["ref_label"] = f"{TX.QSE_REF.get(it.get('tipo'), '')} n.º {it.get('numero')}"
        return it

    def _acao_doc(a: AcaoIn) -> dict:
        d = a.model_dump()
        faltas = og.acao_faltas(d)
        if faltas:
            raise HTTPException(400, TX.T["acao_campos"].format(campos=", ".join(faltas)))
        return {**d, "acao_id": _id("ac"), "estado": "aberta", "historico": [], "criada_em": _now()}

    @router.get(g + "/qse")
    async def qse_lista(tipo: Optional[str] = None, estado: Optional[str] = None, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.ver")
        q: dict = {"chantier_id": ctx.cid}
        if tipo in og.QSE_TIPOS:
            q["tipo"] = tipo
        if estado in TX.QSE_ESTADOS:
            q["estado"] = estado
        sc = og.qse_scope(ctx.roles, ctx.empresa_id)
        if sc:
            q.update(sc)
        rows = await db.obra_qse.find(q, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return {"itens": [_qse_pub(r) for r in rows]}

    @router.post(g + "/qse", status_code=201)
    async def qse_criar(body: QseIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.criar")
        checklist = body.checklist
        if body.tipo == "inspecao" and not checklist and body.checklist_modelo:
            checklist = og.checklist_modelo(body.checklist_modelo) or []
        if body.tipo == "epi" and not checklist:
            checklist = [{"item": i, "resultado": None, "obs": ""} for i in TX.EPI_ITENS]
        checklist = [{"item": str(c.get("item") or "")[:300], "resultado": c.get("resultado") if c.get("resultado") in ("ok", "nok", "na") else None,
                      "obs": str(c.get("obs") or "")[:500]} for c in checklist if str(c.get("item") or "").strip()]
        acoes = [_acao_doc(a) for a in body.acoes]
        empresa_id = body.empresa_id
        if og.EMPRESA in ctx.roles and not _gestor(ctx):
            empresa_id = ctx.empresa_id
            for a in acoes:  # uma empresa só se atribui ações a si própria
                a["quem_empresa_id"] = ctx.empresa_id
        numero = await _seq(ctx.cid, "qse")
        doc = {"item_id": _id("qse"), "chantier_id": ctx.cid, "numero": numero, "tipo": body.tipo, "titulo": body.titulo.strip(),
               "descricao": body.descricao, "data": body.data or _today().isoformat(), "lote": body.lote, "local": body.local,
               "gravidade": body.gravidade, "empresa_id": empresa_id, "checklist_modelo": body.checklist_modelo, "checklist": checklist,
               "participantes": [p.strip()[:120] for p in body.participantes if p.strip()], "tema": body.tema,
               "dias_baixa": body.dias_baixa, "acoes": acoes, "fotos": [], "estado": "aberto",
               "autor": {**ctx.who(), "empresa_id": ctx.empresa_id}, "origem": "manual",
               "created_at": _now(), "updated_at": _now()}
        await db.obra_qse.insert_one(dict(doc))
        ref = f"{TX.QSE_REF.get(body.tipo)} n.º {numero}"
        await _hist(ctx, "qse.criar", ref)
        await _webhook(ctx, "qse.criado", {"numero": numero, "tipo": body.tipo, "titulo": doc["titulo"], "gravidade": body.gravidade})
        if body.tipo == "incidente" or body.gravidade == "critica":
            await _webhook(ctx, "alerta.critico", {"numero": numero, "tipo": body.tipo, "titulo": doc["titulo"]})
        return _qse_pub(doc)

    @router.get(g + "/qse/registo.pdf")
    async def qse_registo_pdf(ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.ver")
        q = {"chantier_id": ctx.cid}
        sc = og.qse_scope(ctx.roles, ctx.empresa_id)
        if sc:
            q.update(sc)
        itens = await db.obra_qse.find(q, {"_id": 0}).sort("numero", 1).to_list(3000)
        from engines.obra_gestao_pdf import qse_pdf
        pdf = await asyncio.to_thread(qse_pdf, ctx.chantier, itens, await _branding(ctx))
        from engines.nom_fichier import nom_document
        return _pdf_response(pdf, nom_document(TX.NOME_DOC["qse"], ctx.chantier.get("name")))

    @router.get(g + "/qse/{item_id}")
    async def qse_ver(item_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.ver")
        return _qse_pub(await _qse(ctx, item_id))

    @router.put(g + "/qse/{item_id}")
    async def qse_editar(item_id: str, body: QseEditIn, ctx: Ctx = Depends(dep)):
        it = await _qse(ctx, item_id)
        autor = (it.get("autor") or {}).get("id") == ctx.actor_id
        if not (og.can(ctx.roles, "qse.gerir") or (autor and og.can(ctx.roles, "qse.criar"))):
            raise HTTPException(403, TX.T["perfil_recusado"])
        if it.get("estado") == "fechado":
            raise HTTPException(409, TX.T["qse_fechado"])
        upd = {k: v for k, v in body.model_dump().items() if v is not None}
        if "empresa_id" in upd and not og.can(ctx.roles, "qse.gerir"):
            upd.pop("empresa_id")
        if "checklist" in upd:
            upd["checklist"] = [{"item": str(c.get("item") or "")[:300],
                                 "resultado": c.get("resultado") if c.get("resultado") in ("ok", "nok", "na") else None,
                                 "obs": str(c.get("obs") or "")[:500]} for c in upd["checklist"] if str(c.get("item") or "").strip()]
        if "participantes" in upd:
            upd["participantes"] = [p.strip()[:120] for p in upd["participantes"] if p.strip()]
        upd["updated_at"] = _now()
        await db.obra_qse.update_one({"item_id": item_id}, {"$set": upd})
        await _hist(ctx, "qse.editar", f"{TX.QSE_REF.get(it['tipo'])} n.º {it['numero']}")
        return _qse_pub(await _qse(ctx, item_id))

    @router.post(g + "/qse/{item_id}/fotos", status_code=201)
    async def qse_foto(item_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.criar")
        it = await _qse(ctx, item_id)
        if len(it.get("fotos") or []) >= MAX_FOTOS:
            raise HTTPException(400, TX.T["foto_limite"])
        meta = await colab._store(ctx.cid, "gestao_qse", ctx.actor_id, file, IMG_TYPES)
        await db.obra_qse.update_one({"item_id": item_id}, {"$push": {"fotos": meta}, "$set": {"updated_at": _now()}})
        return _qse_pub(await _qse(ctx, item_id))

    @router.get(g + "/qse/{item_id}/fotos/{n}")
    async def qse_foto_ver(item_id: str, n: int, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.ver")
        it = await _qse(ctx, item_id)
        fotos = it.get("fotos") or []
        if not 0 <= n < len(fotos):
            raise HTTPException(404, TX.T["nao_encontrado"])
        return await colab._download(fotos[n])

    @router.post(g + "/qse/{item_id}/analisar-foto/{n}")
    async def qse_analisar_foto(item_id: str, n: int, ctx: Ctx = Depends(dep)):
        """Análise de segurança/qualidade de uma fotografia por IA — só acrescenta observações, nunca fecha nada."""
        _need(ctx, "qse.criar")
        it = await _qse(ctx, item_id)
        fotos = it.get("fotos") or []
        if not 0 <= n < len(fotos):
            raise HTTPException(404, TX.T["nao_encontrado"])
        data = await _read_file(fotos[n])
        if not data:
            raise HTTPException(503, TX.T["armazenamento"])
        import base64
        from engines import ai
        try:
            raw = await asyncio.wait_for(ai._complete(TX.ANALISE_FOTO_SISTEMA, "Fotografia de obra.", images=[base64.b64encode(data).decode()],
                                                      feature="obra_qse_foto"), 90)
            res = ai._json(raw, {}) or {}
        except Exception as e:  # noqa: BLE001
            logger.info("análise de foto indisponível: %s", e)
            raise HTTPException(503, TX.T["ia_indisponivel"]) from e
        analise = {"n": n, "at": _now(), "perigos": res.get("perigos") or [], "nao_conformidades": res.get("nao_conformidades") or [],
                   "medidas": res.get("medidas") or [], "gravidade": res.get("gravidade"), "confianca": res.get("confianca"), "fonte": "IA"}
        await db.obra_qse.update_one({"item_id": item_id}, {"$push": {"analises_ia": analise}})
        return analise

    @router.post(g + "/qse/{item_id}/acoes", status_code=201)
    async def qse_acao(item_id: str, body: AcaoIn, ctx: Ctx = Depends(dep)):
        it = await _qse(ctx, item_id)
        if it.get("estado") == "fechado":
            raise HTTPException(409, TX.T["qse_fechado"])
        if not (og.can(ctx.roles, "qse.gerir") or ((it.get("autor") or {}).get("id") == ctx.actor_id)):
            raise HTTPException(403, TX.T["perfil_recusado"])
        a = _acao_doc(body)
        if og.EMPRESA in ctx.roles and not _gestor(ctx):
            a["quem_empresa_id"] = ctx.empresa_id
        await db.obra_qse.update_one({"item_id": item_id}, {"$push": {"acoes": a}, "$set": {"estado": "em_tratamento", "updated_at": _now()}})
        await _hist(ctx, "acao.criar", f"{TX.QSE_REF.get(it['tipo'])} n.º {it['numero']}")
        return _qse_pub(await _qse(ctx, item_id))

    @router.patch(g + "/qse/{item_id}/acoes/{acao_id}")
    async def qse_acao_estado(item_id: str, acao_id: str, body: AcaoEstadoIn, ctx: Ctx = Depends(dep)):
        it = await _qse(ctx, item_id)
        if it.get("estado") == "fechado":
            raise HTTPException(409, TX.T["qse_fechado"])
        acoes = it.get("acoes") or []
        a = next((x for x in acoes if x.get("acao_id") == acao_id), None)
        if not a:
            raise HTTPException(404, TX.T["nao_encontrado"])
        gestao = og.can(ctx.roles, "qse.gerir")
        responsavel = bool(ctx.empresa_id) and a.get("quem_empresa_id") == ctx.empresa_id
        if not (gestao or responsavel):
            raise HTTPException(403, TX.T["acao_so_responsavel"])
        if not og.acao_transicao(a.get("estado", "aberta"), body.estado, gestao=gestao, responsavel=responsavel):
            raise HTTPException(409, TX.T["acao_estado"])
        a["historico"] = (a.get("historico") or []) + [{"de": a.get("estado"), "para": body.estado, "nota": body.nota, "por": ctx.who(), "at": _now()}]
        a["estado"] = body.estado
        if body.estado == "feita":
            a["feito_em"] = _now()
        if body.estado == "verificada":
            a["verificado_por"] = ctx.who()
        await db.obra_qse.update_one({"item_id": item_id}, {"$set": {"acoes": acoes, "updated_at": _now()}})
        await _hist(ctx, "acao.estado", f"{TX.QSE_REF.get(it['tipo'])} n.º {it['numero']}", estado=TX.ACAO_ESTADOS[body.estado])
        return _qse_pub(await _qse(ctx, item_id))

    @router.post(g + "/qse/{item_id}/fechar")
    async def qse_fechar(item_id: str, body: FecharIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.gerir")
        it = await _qse(ctx, item_id)
        if not og.pode_fechar(it, body.justificacao):
            raise HTTPException(409, TX.T["qse_fechar_acoes"])
        await db.obra_qse.update_one({"item_id": item_id}, {"$set": {"estado": "fechado", "fecho": {
            "por": ctx.who(), "at": _now(), "justificacao": body.justificacao.strip()}, "updated_at": _now()}})
        await _hist(ctx, "qse.fechar", f"{TX.QSE_REF.get(it['tipo'])} n.º {it['numero']}")
        await _webhook(ctx, "qse.fechado", {"numero": it["numero"], "tipo": it["tipo"], "titulo": it["titulo"]})
        return _qse_pub(await _qse(ctx, item_id))

    @router.post(g + "/qse/{item_id}/reabrir")
    async def qse_reabrir(item_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "qse.gerir")
        it = await _qse(ctx, item_id)
        await db.obra_qse.update_one({"item_id": item_id}, {"$set": {"estado": "em_tratamento" if it.get("acoes") else "aberto",
                                                                    "updated_at": _now()}, "$unset": {"fecho": ""}})
        await _hist(ctx, "qse.reabrir", f"{TX.QSE_REF.get(it['tipo'])} n.º {it['numero']}")
        return _qse_pub(await _qse(ctx, item_id))

    @router.post(g + "/qse/{item_id}/gerar-nc", status_code=201)
    async def qse_gerar_nc(item_id: str, ctx: Ctx = Depends(dep)):
        """Cria uma não conformidade por cada ponto «não ok» de uma inspeção (ligada à inspeção de origem)."""
        _need(ctx, "qse.gerir")
        it = await _qse(ctx, item_id)
        criadas = []
        ja = set(it.get("nc_geradas") or [])
        for c in it.get("checklist") or []:
            if c.get("resultado") != "nok" or c.get("item") in ja:
                continue
            numero = await _seq(ctx.cid, "qse")
            nc = {"item_id": _id("qse"), "chantier_id": ctx.cid, "numero": numero, "tipo": "nao_conformidade",
                  "titulo": c["item"][:200], "descricao": c.get("obs") or "", "data": _today().isoformat(), "lote": it.get("lote", ""),
                  "local": it.get("local", ""), "gravidade": "media", "empresa_id": it.get("empresa_id"), "checklist": [],
                  "participantes": [], "tema": "", "acoes": [], "fotos": [], "estado": "aberto",
                  "autor": {**ctx.who(), "empresa_id": ctx.empresa_id}, "origem": "inspecao", "inspecao_id": item_id,
                  "created_at": _now(), "updated_at": _now()}
            await db.obra_qse.insert_one(dict(nc))
            criadas.append(numero)
            ja.add(c["item"])
        await db.obra_qse.update_one({"item_id": item_id}, {"$set": {"nc_geradas": sorted(ja)}})
        for n in criadas:
            await _hist(ctx, "qse.criar", f"NC n.º {n}")
        return {"criadas": criadas}

    # ---------------------------------------------------------- pedidos de esclarecimento (RFI)
    async def _rfi(ctx: Ctx, rfi_id: str) -> dict:
        q = {"rfi_id": rfi_id, "chantier_id": ctx.cid}
        sc = og.rfi_scope(ctx.roles, ctx.empresa_id, ctx.actor_id)
        r = await db.obra_rfi.find_one({"$and": [q, sc]} if sc else q, {"_id": 0})
        if not r:
            raise HTTPException(404, TX.T["nao_encontrado"])
        return r

    def _rfi_pub(r: dict, ctx: Ctx) -> dict:
        r = _pub(r)
        r["anexos"] = [{"n": i, "filename": a.get("filename")} for i, a in enumerate(r.get("anexos") or [])]
        prazo = og.parse_date(r.get("prazo"))
        r["em_atraso"] = r.get("estado") == "aberto" and prazo is not None and prazo < _today()
        autor = (r.get("autor") or {}).get("id") == ctx.actor_id
        r["pode_responder"] = r.get("estado") != "fechado" and (autor or og.rfi_pode_responder(ctx.roles, ctx.empresa_id, ctx.actor_id, r))
        r["pode_fechar"] = r.get("estado") != "fechado" and (autor or og.can(ctx.roles, "rfi.fechar"))
        return r

    @router.get(g + "/rfi")
    async def rfi_lista(estado: Optional[str] = None, ctx: Ctx = Depends(dep)):
        _need(ctx, "rfi.ver")
        q: dict = {"chantier_id": ctx.cid}
        if estado in TX.RFI_ESTADOS:
            q["estado"] = estado
        sc = og.rfi_scope(ctx.roles, ctx.empresa_id, ctx.actor_id)
        rows = await db.obra_rfi.find({"$and": [q, sc]} if sc else q, {"_id": 0}).sort("created_at", -1).to_list(2000)
        return {"itens": [_rfi_pub(r, ctx) for r in rows]}

    @router.post(g + "/rfi", status_code=201)
    async def rfi_criar(body: RfiIn, ctx: Ctx = Depends(dep)):
        _need(ctx, "rfi.criar")
        dest: dict = {}
        if body.destinatario_id:
            p = await db.chantier_participants.find_one({"participant_id": body.destinatario_id, "chantier_id": ctx.cid,
                                                         "status": {"$ne": "revoked"}}, {"_id": 0, "name": 1, "email": 1})
            if not p:
                raise HTTPException(404, TX.T["nao_encontrado"])
            dest = {"id": body.destinatario_id, "nome": p.get("name") or p.get("email")}
        elif body.destinatario_perfil:
            from engines import obra_colab as oc
            dest = {"perfil": body.destinatario_perfil, "nome": oc.ROLE_LABELS.get(body.destinatario_perfil, body.destinatario_perfil)}
        n = await _seq(ctx.cid, "rfi")
        numero = f"{TX.RFI_PREFIXO}-{n:03d}"
        doc = {"rfi_id": _id("rfi"), "chantier_id": ctx.cid, "numero": numero, "assunto": body.assunto.strip(), "pergunta": body.pergunta,
               "lote": body.lote, "plano_id": body.plano_id, "destinatario": dest, "prazo": body.prazo, "visibilidade": body.visibilidade,
               "impacto": {"custo": body.impacto_custo, "prazo": body.impacto_prazo}, "autor": {**ctx.who(), "empresa_id": ctx.empresa_id},
               "respostas": [], "anexos": [], "estado": "aberto", "created_at": _now(), "updated_at": _now()}
        await db.obra_rfi.insert_one(dict(doc))
        await _hist(ctx, "rfi.criar", numero)
        await _webhook(ctx, "rfi.criado", {"numero": numero, "assunto": doc["assunto"], "prazo": body.prazo})
        return _rfi_pub(doc, ctx)

    @router.get(g + "/rfi/{rfi_id}")
    async def rfi_ver(rfi_id: str, ctx: Ctx = Depends(dep)):
        _need(ctx, "rfi.ver")
        return _rfi_pub(await _rfi(ctx, rfi_id), ctx)

    @router.post(g + "/rfi/{rfi_id}/respostas", status_code=201)
    async def rfi_responder(rfi_id: str, body: TextoIn, ctx: Ctx = Depends(dep)):
        r = await _rfi(ctx, rfi_id)
        if r.get("estado") == "fechado":
            raise HTTPException(409, TX.T["rfi_fechado"])
        autor = (r.get("autor") or {}).get("id") == ctx.actor_id
        if not (og.rfi_pode_responder(ctx.roles, ctx.empresa_id, ctx.actor_id, r) or autor):
            raise HTTPException(403, TX.T["rfi_nao_destinatario"])
        resp = {"texto": body.texto.strip(), "por": ctx.who(), "at": _now(), "e_resposta": not autor}
        upd = {"updated_at": _now()}
        if not autor:
            upd["estado"] = "respondido"
        await db.obra_rfi.update_one({"rfi_id": rfi_id}, {"$push": {"respostas": resp}, "$set": upd})
        await _hist(ctx, "rfi.responder", r["numero"])
        if not autor:
            await _webhook(ctx, "rfi.respondido", {"numero": r["numero"], "assunto": r["assunto"]})
        return _rfi_pub(await _rfi(ctx, rfi_id), ctx)

    @router.post(g + "/rfi/{rfi_id}/fechar")
    async def rfi_fechar(rfi_id: str, ctx: Ctx = Depends(dep)):
        r = await _rfi(ctx, rfi_id)
        if not (og.can(ctx.roles, "rfi.fechar") or (r.get("autor") or {}).get("id") == ctx.actor_id):
            raise HTTPException(403, TX.T["perfil_recusado"])
        await db.obra_rfi.update_one({"rfi_id": rfi_id}, {"$set": {"estado": "fechado", "fechado": {"por": ctx.who(), "at": _now()}}})
        await _hist(ctx, "rfi.fechar", r["numero"])
        return _rfi_pub(await _rfi(ctx, rfi_id), ctx)

    @router.post(g + "/rfi/{rfi_id}/anexos", status_code=201)
    async def rfi_anexo(rfi_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(dep)):
        r = await _rfi(ctx, rfi_id)
        if r.get("estado") == "fechado":
            raise HTTPException(409, TX.T["rfi_fechado"])
        if len(r.get("anexos") or []) >= 20:
            raise HTTPException(400, TX.T["foto_limite"])
        meta = await colab._store(ctx.cid, "gestao_rfi", ctx.actor_id, file, colab.ALLOWED_PLANO)
        meta["por"] = ctx.who()
        await db.obra_rfi.update_one({"rfi_id": rfi_id}, {"$push": {"anexos": meta}})
        return _rfi_pub(await _rfi(ctx, rfi_id), ctx)

    @router.get(g + "/rfi/{rfi_id}/anexos/{n}")
    async def rfi_anexo_ver(rfi_id: str, n: int, ctx: Ctx = Depends(dep)):
        _need(ctx, "rfi.ver")
        r = await _rfi(ctx, rfi_id)
        anexos = r.get("anexos") or []
        if not 0 <= n < len(anexos):
            raise HTTPException(404, TX.T["nao_encontrado"])
        return await colab._download(anexos[n])

    # ---------------------------------------------------------- indicadores
    @router.get(g + "/curva-s")
    async def curva(ctx: Ctx = Depends(dep)):
        _need(ctx, "indicadores.ver")
        await _snapshot(ctx)
        return await _curva(ctx)

    @router.get(g + "/alertas")
    async def alertas_obra(ctx: Ctx = Depends(dep)):
        _need(ctx, "indicadores.ver")
        return {"itens": await _alertas(ctx)}


_mount(pro_router, "/{chantier_id}", ctx_pro)
_mount(portal_router, "/{ref}", ctx_portal)


# ====================================================================== só o titular
async def _ctx_gestor(chantier_id: str, user=Depends(current_user)) -> Ctx:
    ctx = await ctx_pro(chantier_id, user)
    return ctx


@pro_router.get("/{chantier_id}/gestao/qse-operarios")
async def qse_operarios(ctx: Ctx = Depends(_ctx_gestor)):
    """Alertas de segurança enviados pelos operários (app de ponto) ainda não qualificados."""
    ids = await _projetos_rh(ctx)
    notas = await db.hr_notes.find({"employer_id": _owner(ctx), "project_id": {"$in": ids}, "type": "incident",
                                    "qse_item_id": {"$exists": False}}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"itens": notas}


class QualificarIn(BaseModel):
    tipo: Literal["incidente", "quase_acidente", "nao_conformidade", "ambiente"] = "quase_acidente"
    gravidade: Literal["baixa", "media", "alta", "critica"] = "media"


@pro_router.post("/{chantier_id}/gestao/qse-operarios/{note_id}", status_code=201)
async def qse_qualificar(note_id: str, body: QualificarIn, ctx: Ctx = Depends(_ctx_gestor)):
    ids = await _projetos_rh(ctx)
    n = await db.hr_notes.find_one({"note_id": note_id, "employer_id": _owner(ctx), "project_id": {"$in": ids}}, {"_id": 0})
    if not n:
        raise HTTPException(404, TX.T["nao_encontrado"])
    numero = await _seq(ctx.cid, "qse")
    msg = (n.get("message") or "").strip()
    doc = {"item_id": _id("qse"), "chantier_id": ctx.cid, "numero": numero, "tipo": body.tipo, "titulo": msg[:120] or TX.QSE_TIPOS[body.tipo],
           "descricao": msg, "data": (n.get("created_at") or _now())[:10], "lote": "", "local": "", "gravidade": body.gravidade,
           "empresa_id": None, "checklist": [], "participantes": [], "tema": "", "acoes": [], "fotos": [], "estado": "aberto",
           "autor": {"id": n.get("worker_id"), "nome": n.get("worker_name"), "perfil": "operario", "empresa_id": None},
           "origem": "operario", "nota_operario_id": note_id, "created_at": _now(), "updated_at": _now()}
    await db.obra_qse.insert_one(dict(doc))
    await db.hr_notes.update_one({"note_id": note_id}, {"$set": {"qse_item_id": doc["item_id"], "status": "closed"}})
    await _hist(ctx, "qse.criar", f"{TX.QSE_REF.get(body.tipo)} n.º {numero}")
    await _webhook(ctx, "qse.criado", {"numero": numero, "tipo": body.tipo, "titulo": doc["titulo"], "origem": "operario"})
    return {"item_id": doc["item_id"], "numero": numero}


# ---------------------------------------------------------- stock
@pro_router.get("/{chantier_id}/gestao/stock")
async def stock(ctx: Ctx = Depends(_ctx_gestor)):
    movs = await db.obra_stock.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"saldos": await _stock_saldos(ctx), "movimentos": movs}


@pro_router.post("/{chantier_id}/gestao/stock/movimentos", status_code=201)
async def stock_movimento(body: MovimentoIn, ctx: Ctx = Depends(_ctx_gestor)):
    q = body.quantidade
    if body.tipo in ("entrada", "saida") and q <= 0:
        raise HTTPException(400, TX.T["stock_qtd"])
    if body.tipo == "ajuste" and q == 0:
        raise HTTPException(400, TX.T["stock_qtd"])
    if body.tipo == "saida":
        chave = f"{og.norm(body.material)}|{og.norm(body.unidade)}"
        saldo = next((s["saldo"] for s in await _stock_saldos(ctx) if s["chave"] == chave), 0.0)
        if q > saldo + 1e-9:
            raise HTTPException(409, TX.T["stock_negativo"].format(material=body.material, saldo=saldo, unidade=body.unidade))
    doc = {"mov_id": _id("mov"), "chantier_id": ctx.cid, "tipo": body.tipo, "material": body.material.strip(), "unidade": body.unidade.strip(),
           "quantidade": round(q, 3), "data": body.data or _today().isoformat(), "local": body.local, "nota": body.nota,
           "origem": {"tipo": "manual"}, "por": ctx.who(), "created_at": _now()}
    await db.obra_stock.insert_one(dict(doc))
    await _hist(ctx, "stock.movimento", f"{body.tipo} {doc['quantidade']} {doc['unidade']} {doc['material']}")
    return _pub(doc)


@pro_router.put("/{chantier_id}/gestao/stock/minimos")
async def stock_minimo(body: MinimoIn, ctx: Ctx = Depends(_ctx_gestor)):
    key = f"stock_minimos.{body.chave.replace('.', '_')}"
    if body.minimo is None:
        await db.obra_gestao_cfg.update_one({"chantier_id": ctx.cid}, {"$unset": {key: ""}}, upsert=True)
    else:
        await db.obra_gestao_cfg.update_one({"chantier_id": ctx.cid}, {"$set": {key: body.minimo}}, upsert=True)
    return {"saldos": await _stock_saldos(ctx)}


@pro_router.get("/{chantier_id}/gestao/stock/encomendas")
async def stock_encomendas(ctx: Ctx = Depends(_ctx_gestor)):
    from engines.chantier_costs import ENGAGED, supplier_name
    from engines.chantier_scope import purchase_scope
    q = await purchase_scope(db, ctx.chantier, _owner(ctx))
    rows = await db.material_orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    out = []
    for o in rows:
        if o.get("status") not in ENGAGED:
            continue
        rec = o.get("rececoes_obra") or []
        recebido: dict[int, float] = {}
        for r in rec:
            for ln in r.get("linhas") or []:
                recebido[ln["linha"]] = recebido.get(ln["linha"], 0) + float(ln.get("quantidade") or 0)
        linhas = []
        for i, it in enumerate(o.get("items") or []):
            try:
                pedida = float(it.get("qty") or 0)
            except (TypeError, ValueError):
                pedida = 0.0
            linhas.append({"linha": i, "material": it.get("designation"), "unidade": it.get("unit"), "pedida": pedida,
                           "recebida": round(recebido.get(i, 0.0), 3), "em_falta": round(max(0.0, pedida - recebido.get(i, 0.0)), 3)})
        out.append({"order_id": o["order_id"], "fornecedor": supplier_name(o), "estado": o.get("status"),
                    "entrega": (o.get("delivery") or {}).get("status"), "linhas": linhas, "rececoes": len(rec)})
    return {"itens": out}


@pro_router.post("/{chantier_id}/gestao/stock/rececao/{order_id}", status_code=201)
async def stock_rececao(order_id: str, body: RececaoIn, ctx: Ctx = Depends(_ctx_gestor)):
    from engines.chantier_costs import ENGAGED, supplier_name
    from engines.chantier_scope import purchase_scope
    q = {**await purchase_scope(db, ctx.chantier, _owner(ctx)), "order_id": order_id}
    o = await db.material_orders.find_one(q, {"_id": 0})
    if not o:
        raise HTTPException(404, TX.T["encomenda_nao_encontrada"])
    if o.get("status") not in ENGAGED:
        raise HTTPException(409, TX.T["encomenda_estado"])
    items = o.get("items") or []
    recebido: dict[int, float] = {}
    for r in o.get("rececoes_obra") or []:
        for ln in r.get("linhas") or []:
            recebido[ln["linha"]] = recebido.get(ln["linha"], 0) + float(ln.get("quantidade") or 0)
    dia = body.data or _today().isoformat()
    movs, linhas = [], []
    for ln in body.linhas:
        if ln.linha >= len(items):
            raise HTTPException(400, TX.T["nao_encontrado"])
        it = items[ln.linha]
        try:
            pedida = float(it.get("qty") or 0)
        except (TypeError, ValueError):
            pedida = 0.0
        if pedida and recebido.get(ln.linha, 0) + ln.quantidade > pedida * 1.0001 and not ln.nota.strip():
            raise HTTPException(400, TX.T["rececao_excesso"].format(linha=ln.linha + 1, material=it.get("designation")))
        linhas.append(ln.model_dump())
        if ln.quantidade > 0:
            movs.append({"mov_id": _id("mov"), "chantier_id": ctx.cid, "tipo": "entrada", "material": str(it.get("designation") or "").strip(),
                         "unidade": str(it.get("unit") or "").strip(), "quantidade": round(ln.quantidade, 3), "data": dia, "local": "",
                         "nota": ln.nota, "origem": {"tipo": "encomenda", "order_id": order_id, "linha": ln.linha,
                                                     "guia_remessa": body.guia_remessa, "conforme": ln.conforme},
                         "por": ctx.who(), "created_at": _now()})
    total = {i: recebido.get(i, 0) for i in range(len(items))}
    for ln in body.linhas:
        total[ln.linha] = total.get(ln.linha, 0) + ln.quantidade
    completo = all(total.get(i, 0) >= float(items[i].get("qty") or 0) - 1e-9 for i in range(len(items)))
    nao_conf = any(not ln.conforme for ln in body.linhas)
    rec = {"rececao_id": _id("rec"), "data": dia, "guia_remessa": body.guia_remessa, "linhas": linhas, "por": ctx.who(), "at": _now()}
    estado = "issue" if nao_conf else ("received" if completo else "partial")
    await db.material_orders.update_one({"order_id": order_id}, {"$push": {"rececoes_obra": rec},
                                                                 "$set": {"delivery.status": estado, "delivery.updated_at": _now(),
                                                                          "delivery.updated_by": ctx.actor_id},
                                                                 "$inc": {"delivery_version": 1}})
    if movs:
        await db.obra_stock.insert_many([dict(m) for m in movs])
    await _hist(ctx, "stock.rececao", supplier_name(o))
    await _webhook(ctx, "stock.rececao", {"encomenda": order_id, "fornecedor": supplier_name(o), "estado": estado,
                                          "linhas": [{"material": m["material"], "quantidade": m["quantidade"], "unidade": m["unidade"]} for m in movs]})
    return {"estado_entrega": estado, "movimentos": len(movs), "saldos": await _stock_saldos(ctx)}


# ---------------------------------------------------------- copiloto e relatório semanal
async def _contexto_copiloto(ctx: Ctx) -> dict:
    hoje = _today()
    diarios = await db.obra_diario.find({"chantier_id": ctx.cid, "data": {"$gte": (hoje - timedelta(days=21)).isoformat()}},
                                        {"_id": 0, "data": 1, "trabalhos": 1, "ocorrencias": 1, "entregas": 1, "meteo.descricao": 1,
                                         "efetivo_auto.trabalhadores": 1, "efetivo_auto.horas": 1, "estado": 1}).sort("data", -1).to_list(30)
    qse = await db.obra_qse.find({"chantier_id": ctx.cid}, {"_id": 0, "numero": 1, "tipo": 1, "titulo": 1, "gravidade": 1, "estado": 1,
                                                            "data": 1, "acoes.o_que": 1, "acoes.quando": 1, "acoes.estado": 1}).sort("created_at", -1).to_list(80)
    rfis = await db.obra_rfi.find({"chantier_id": ctx.cid}, {"_id": 0, "numero": 1, "assunto": 1, "estado": 1, "prazo": 1,
                                                             "destinatario.nome": 1}).sort("created_at", -1).to_list(60)
    sched = await _schedule(ctx)
    tarefas = [{k: t.get(k) for k in ("name", "start_date", "end_date", "progress", "critical", "late")} for t in (sched or {}).get("tasks") or []]
    curva = await _curva(ctx)
    costs = await _custos(ctx)
    custos = None
    if costs:
        custos = {"totais": costs.get("totals"), "custo_real_conhecido": costs.get("real_cost_known_ht"),
                  "lotes": [{k: lt.get(k) for k in ("lot", "vente_ht", "cost_prev_ht", "real_cost_ht")} for lt in costs.get("budget_by_lot") or []],
                  "previsao": costs.get("forecast")}
    stock = await _stock_saldos(ctx)
    return {"hoje": hoje.isoformat(), "obra": {"nome": ctx.chantier.get("name"), "cidade": ctx.chantier.get("city"),
                                               "estado": ctx.chantier.get("status")},
            "planeamento": {"projeto": (sched or {}).get("project"), "tarefas": tarefas},
            "curva_s": {k: curva.get(k) for k in ("disponivel", "motivo", "previsto_hoje_pct", "real_hoje_pct", "desvio_pp", "spi", "cpi")},
            "custos": custos, "diario": diarios, "qualidade_seguranca": qse, "pedidos_esclarecimento": rfis,
            "stock": [{k: s.get(k) for k in ("material", "unidade", "saldo", "minimo")} for s in stock][:80],
            "alertas": [a["texto"] for a in await _alertas(ctx)]}


@pro_router.post("/{chantier_id}/gestao/copiloto/pergunta")
async def copiloto_pergunta(body: PerguntaIn, ctx: Ctx = Depends(_ctx_gestor)):
    if not body.pergunta.strip():
        raise HTTPException(400, TX.T["pergunta_vazia"])
    dados = await _contexto_copiloto(ctx)
    from engines import ai
    prompt = f"DADOS DA OBRA (JSON):\n{json.dumps(dados, ensure_ascii=False, default=str)[:60000]}\n\nPERGUNTA:\n{body.pergunta.strip()}"
    try:
        resposta = await asyncio.wait_for(ai._complete(TX.COPILOTO_SISTEMA, prompt, feature="obra_copiloto"), 90)
        return {"resposta": resposta.strip(), "fonte": "ia", "dados_usados": list(dados)}
    except Exception as e:  # noqa: BLE001
        logger.info("copiloto: IA indisponível: %s", e)
        hoje = _today()
        de, ate = og.semana_de(hoje)
        d = og.dados_semana(await db.obra_diario.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(400),
                            await db.obra_qse.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(3000),
                            await db.obra_rfi.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(3000), de, ate, hoje)
        return {"resposta": TX.T["ia_indisponivel"] + "\n\n" + og.resumo_texto(d, await _alertas(ctx), await _curva(ctx)), "fonte": "calculo"}


async def _semana(ctx: Ctx, data: Optional[str]) -> tuple[dict, list, dict]:
    hoje = _today()
    ref = og.parse_date(data) or hoje
    de, ate = og.semana_de(ref)
    d = og.dados_semana(await db.obra_diario.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(2000),
                        await db.obra_qse.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(3000),
                        await db.obra_rfi.find({"chantier_id": ctx.cid}, {"_id": 0}).to_list(3000), de, ate, hoje)
    return d, await _alertas(ctx), await _curva(ctx)


@pro_router.post("/{chantier_id}/gestao/copiloto/resumo")
async def copiloto_resumo(data: Optional[str] = None, ctx: Ctx = Depends(_ctx_gestor)):
    d, al, curva = await _semana(ctx, data)
    base = og.resumo_texto(d, al, curva)
    from engines import ai
    fonte = "ia"
    try:
        dados = {"semana": d, "alertas": [a["texto"] for a in al],
                 "curva_s": {k: curva.get(k) for k in ("disponivel", "previsto_hoje_pct", "real_hoje_pct", "desvio_pp", "spi")}}
        texto = (await asyncio.wait_for(ai._complete(TX.RESUMO_SISTEMA, json.dumps(dados, ensure_ascii=False, default=str)[:40000],
                                                     feature="obra_resumo"), 90)).strip()
    except Exception as e:  # noqa: BLE001
        logger.info("resumo: IA indisponível: %s", e)
        texto, fonte = base, "calculo"
    await db.obra_resumos.update_one({"chantier_id": ctx.cid, "semana": d["de"]},
                                     {"$set": {"texto": texto, "fonte": fonte, "at": _now(), "por": ctx.who()}}, upsert=True)
    await _hist(ctx, "copiloto.resumo")
    return {"semana": d["de"], "texto": texto, "fonte": fonte, "dados": d}


@pro_router.get("/{chantier_id}/gestao/relatorio-semanal.pdf")
async def relatorio_semanal(data: Optional[str] = None, ctx: Ctx = Depends(_ctx_gestor)):
    d, al, curva = await _semana(ctx, data)
    r = await db.obra_resumos.find_one({"chantier_id": ctx.cid, "semana": d["de"]}, {"_id": 0})
    from engines.obra_gestao_pdf import relatorio_pdf
    pdf = await asyncio.to_thread(relatorio_pdf, ctx.chantier, d, al, curva, (r or {}).get("texto"), await _branding(ctx))
    from engines.nom_fichier import nom_document
    return _pdf_response(pdf, nom_document(TX.NOME_DOC["relatorio"], ctx.chantier.get("name"), date=d["ate"]))


@pro_router.get("/{chantier_id}/gestao/historico")
async def historico(limite: int = Query(200, ge=1, le=1000), ctx: Ctx = Depends(_ctx_gestor)):
    rows = await db.obra_historico.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("at", -1).to_list(limite)
    return {"itens": rows}


# ====================================================================== webhooks da empresa
@webhooks_router.get("")
async def webhooks_lista(user=Depends(current_user)):
    rows = await db.webhooks_saida.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(10)
    return {"itens": [wh.publico(r) for r in rows], "eventos": list(wh.EVENTOS)}


@webhooks_router.post("", status_code=201)
async def webhooks_criar(body: WebhookIn, user=Depends(current_user)):
    if not wh.url_valida(body.url):
        raise HTTPException(400, TX.T["webhook_url"])
    if await db.webhooks_saida.count_documents({"user_id": user["user_id"]}) >= 5:
        raise HTTPException(400, TX.T["webhook_limite"])
    eventos = [e for e in body.eventos if wh.evento_valido(e)]
    doc = {"hook_id": _id("wh"), "user_id": user["user_id"], "url": body.url, "eventos": eventos, "ativo": body.ativo,
           "descricao": body.descricao, "segredo": wh.novo_segredo(), "envios": 0, "falhas": 0, "created_at": _now()}
    await db.webhooks_saida.insert_one(dict(doc))
    return wh.publico(doc, mostrar_segredo=True)


@webhooks_router.put("/{hook_id}")
async def webhooks_editar(hook_id: str, body: WebhookIn, user=Depends(current_user)):
    if not wh.url_valida(body.url):
        raise HTTPException(400, TX.T["webhook_url"])
    r = await db.webhooks_saida.update_one({"hook_id": hook_id, "user_id": user["user_id"]}, {"$set": {
        "url": body.url, "eventos": [e for e in body.eventos if wh.evento_valido(e)], "ativo": body.ativo, "descricao": body.descricao}})
    if not r.matched_count:
        raise HTTPException(404, TX.T["nao_encontrado"])
    return wh.publico(await db.webhooks_saida.find_one({"hook_id": hook_id}, {"_id": 0}))


@webhooks_router.delete("/{hook_id}")
async def webhooks_apagar(hook_id: str, user=Depends(current_user)):
    r = await db.webhooks_saida.delete_one({"hook_id": hook_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, TX.T["nao_encontrado"])
    return {"ok": True}


@webhooks_router.post("/{hook_id}/testar")
async def webhooks_testar(hook_id: str, user=Depends(current_user)):
    h = await db.webhooks_saida.find_one({"hook_id": hook_id, "user_id": user["user_id"]}, {"_id": 0})
    if not h:
        raise HTTPException(404, TX.T["nao_encontrado"])
    res = await wh.enviar(h, "diario.assinado", {"teste": True})
    await db.webhooks_saida.update_one({"hook_id": hook_id}, {"$set": {"ultimo_envio": res}})
    return res
