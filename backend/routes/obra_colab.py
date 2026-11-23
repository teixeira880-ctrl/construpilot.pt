"""Obra colaborativa (assinatura por obra) — API.

Mesmas rotas servidas a dois públicos, com a mesma matriz de acessos (engines/obra_colab.py):
  * titular da conta que abriu a obra ........ /api/chantiers/{chantier_id}/colab/...
  * intervenientes convidados (portal) ....... /api/portal/{ref}/colab/...

Blocos: intervenientes e perfis · caixa de planos e visto · aprovação de subempreiteiros ·
autos de medição · planeamento · ata semanal.

Regra de separação: uma empresa só lê e escreve os seus próprios autos, contratos, pedidos de
subempreiteiros e cronograma. O filtro é aplicado no servidor em todas as listagens e leituras.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user, pro_required
from core.uploads import ALLOWED_CAD, ALLOWED_DOCUMENT, ALLOWED_IMAGE, ALLOWED_OFFICE, validate_upload
from engines import obra_colab as oc
from engines import storage
from routes import portal as portal_routes
from routes.chantiers import _get as get_chantier_owned

logger = logging.getLogger(__name__)

pro_router = APIRouter(prefix="/chantiers", tags=["obra-colab-pro"], dependencies=[Depends(pro_required)])
portal_router = APIRouter(prefix="/portal", tags=["obra-colab-portal"])

ALLOWED_PLANO = ALLOWED_DOCUMENT + ALLOWED_IMAGE + ALLOWED_CAD
ALLOWED_PECA = ALLOWED_DOCUMENT + ALLOWED_IMAGE + ALLOWED_OFFICE
MAX_FILE_MB = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


# ------------------------------------------------------------------ contexto (quem atua, em que obra)
class Ctx:
    def __init__(self, chantier: dict, kind: str, actor_id: str, name: str, roles: set[str],
                 empresa_id: Optional[str]):
        self.chantier = chantier
        self.cid = chantier["chantier_id"]
        self.kind = kind                # "owner" | "participant"
        self.actor_id = actor_id
        self.name = name
        self.roles = roles
        self.empresa_id = empresa_id    # só para o perfil empresa (= participant_id)

    @property
    def role(self) -> str:
        """Perfil apresentado. Para o titular: o perfil declarado, senão «gestor»."""
        for r in oc.ROLES:
            if r in self.roles:
                return r
        return oc.GESTOR

    def can(self, cap: str) -> bool:
        return any(oc.can(r, cap) for r in self.roles)

    def need(self, cap: str) -> None:
        if not self.can(cap):
            raise HTTPException(403, "O seu perfil nesta obra não permite esta ação.")

    def scope(self, resource: str) -> dict:
        """Filtro Mongo da listagem de um recurso para este ator."""
        base = {"chantier_id": self.cid}
        if oc.GESTOR in self.roles:
            return base
        f = oc.scope_filter(self.role, resource, self.empresa_id)
        return {**base, **f} if f else base

    def sees(self, resource: str, record: dict) -> bool:
        if oc.GESTOR in self.roles:
            return True
        return oc.may_see_record(self.role, resource, self.empresa_id, record)

    def who(self) -> dict:
        return {"id": self.actor_id, "nome": self.name, "perfil": self.role}


async def _settings(cid: str) -> dict:
    s = await db.obra_colab_settings.find_one({"chantier_id": cid}, {"_id": 0})
    return s or {"chantier_id": cid, "owner_role": None, "limite_subcontratacao_pct": None,
                 "tolerancia_avanco_pct": 5.0, "regulamento": None}


async def ctx_pro(chantier_id: str, user=Depends(current_user)) -> Ctx:
    chantier = await get_chantier_owned(chantier_id, user["user_id"])
    s = await _settings(chantier_id)
    roles = {oc.GESTOR}
    if s.get("owner_role") in oc.ROLES:
        roles.add(s["owner_role"])
    return Ctx(chantier, "owner", user["user_id"], user.get("name") or user.get("email") or "Titular", roles, None)


async def ctx_portal(ref: str, p=Depends(portal_routes.current_participant)) -> Ctx:
    portal_routes._require_ref(p, ref)
    chantier = await portal_routes._chantier_of(p)
    role = oc.role_of_participant(p)
    return Ctx(chantier, "participant", p["participant_id"], p.get("name") or p["email"], {role},
               p["participant_id"] if role == oc.EMPRESA else None)


async def _empresas(cid: str) -> list[dict]:
    rows = await db.chantier_participants.find({"chantier_id": cid, "status": {"$ne": "revoked"}},
                                               {"_id": 0, "invite_token_hash": 0}).to_list(500)
    return [{"empresa_id": r["participant_id"], "nome": r.get("name") or r["email"], "lote": r.get("lot") or ""}
            for r in rows if oc.role_of_participant(r) == oc.EMPRESA]


async def _empresa_nome(cid: str, empresa_id: Optional[str]) -> str:
    if not empresa_id:
        return ""
    p = await db.chantier_participants.find_one({"participant_id": empresa_id, "chantier_id": cid}, {"_id": 0})
    return (p or {}).get("name") or (p or {}).get("email") or ""


# ------------------------------------------------------------------ ficheiros
async def _store(cid: str, kind: str, owner_id: str, file: UploadFile, allowed: list[str]) -> dict:
    file = await validate_upload(file, allowed, max_mb=MAX_FILE_MB)
    data = await file.read()
    if not data:
        raise HTTPException(400, "Ficheiro vazio.")
    path = f"{storage.APP_NAME}/colab/{cid}/{kind}/{owner_id}/{secrets.token_hex(8)}_{file.filename}"
    try:
        await asyncio.to_thread(storage.put_object, path, data, file.content_type or "application/octet-stream")
    except Exception as e:  # noqa: BLE001
        logger.warning("obra_colab upload failed: %s", e)
        raise HTTPException(503, "O armazenamento de ficheiros está indisponível. Tente novamente.") from e
    return {"path": path, "filename": file.filename, "content_type": file.content_type or "application/octet-stream",
            "size": len(data), "uploaded_at": _now()}


async def _download(meta: dict) -> Response:
    try:
        data, ctype = await asyncio.to_thread(storage.get_object, meta["path"])
    except Exception as e:  # noqa: BLE001
        logger.warning("obra_colab download failed: %s", e)
        raise HTTPException(503, "O armazenamento de ficheiros está indisponível. Tente novamente.") from e
    return Response(content=data, media_type=meta.get("content_type") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{meta.get("filename") or "ficheiro"}"'})


def _pub(d: Optional[dict]) -> dict:
    d = dict(d or {})
    d.pop("_id", None)
    return d


# ------------------------------------------------------------------ modelos
class SettingsIn(BaseModel):
    owner_role: Optional[Literal["dono_obra", "fiscalizacao", "arquiteto", "empresa"]] = None
    limite_subcontratacao_pct: Optional[float] = Field(None, ge=0, le=100)
    tolerancia_avanco_pct: float = Field(5.0, ge=0, le=50)


class IntervenienteIn(BaseModel):
    perfil: Literal["dono_obra", "fiscalizacao", "arquiteto", "empresa"]
    email: EmailStr
    nome: str = Field("", max_length=120)
    lote: str = Field("", max_length=80)


class PerfilIn(BaseModel):
    perfil: Literal["dono_obra", "fiscalizacao", "arquiteto", "empresa"]
    nome: Optional[str] = Field(None, max_length=120)
    lote: Optional[str] = Field(None, max_length=80)


class PlanoEditIn(BaseModel):
    titulo: str = Field(..., min_length=1, max_length=160)
    tipo: Literal["arquitetura", "execucao", "caderno_encargos", "outro"] = "execucao"
    especialidade: str = Field("", max_length=80)


class AnotacaoIn(BaseModel):
    texto: str = Field(..., min_length=1, max_length=2000)


class VistoIn(BaseModel):
    decisao: Literal["visto", "visto_com_observacoes", "recusado"]
    observacoes: str = Field("", max_length=4000)


class CompararIn(BaseModel):
    plano_a: str
    plano_b: str
    foco: str = Field("", max_length=400)


class RegItemIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=60, pattern=r"^[a-z0-9_]+$")
    label: str = Field(..., min_length=1, max_length=200)
    obrigatorio: bool = True
    tem_validade: bool = False
    ativo: bool = True


class RegulamentoIn(BaseModel):
    itens: list[RegItemIn] = Field(..., max_length=60)


class SubIn(BaseModel):
    nome: str = Field(..., min_length=1, max_length=160)
    nif: str = Field("", max_length=20)
    trabalhos: str = Field("", max_length=1000)
    valor: float = Field(0, ge=0, le=1e10)


class SubDecisaoIn(BaseModel):
    decisao: Literal["aprovado", "aprovado_com_reservas", "recusado"]
    reservas: str = Field("", max_length=4000)
    motivos: str = Field("", max_length=4000)


class ContratoLinhaIn(BaseModel):
    ref: str = Field(..., min_length=1, max_length=40)
    designacao: str = Field("", max_length=300)
    unidade: str = Field("", max_length=12)
    quantidade: float = Field(..., ge=0, le=1e9)
    preco_unitario: float = Field(..., ge=0, le=1e9)


class ContratoIn(BaseModel):
    titulo: str = Field("", max_length=200)
    linhas: list[ContratoLinhaIn] = Field(..., min_length=1, max_length=2000)


class AutoLinhaIn(BaseModel):
    ref: str = Field(..., min_length=1, max_length=40)
    quantidade_periodo: float = Field(..., ge=-1e9, le=1e9)
    preco_unitario: Optional[float] = Field(None, ge=0, le=1e9)
    valor: Optional[float] = Field(None, ge=-1e12, le=1e12)
    designacao: str = Field("", max_length=300)
    unidade: str = Field("", max_length=12)


class AutoIn(BaseModel):
    numero: Optional[int] = Field(None, ge=1, le=9999)
    periodo: str = Field(..., min_length=4, max_length=20)   # ex.: 2026-11
    linhas: list[AutoLinhaIn] = Field(..., max_length=2000)
    total_declarado: Optional[float] = None
    observacoes: str = Field("", max_length=2000)


class AutoDecisaoIn(BaseModel):
    aprovar: bool
    motivo: str = Field("", max_length=4000)


class TarefaIn(BaseModel):
    tarefa_id: Optional[str] = Field(None, max_length=40)
    titulo: str = Field(..., min_length=1, max_length=200)
    inicio: str = Field(..., min_length=10, max_length=10)
    fim: str = Field(..., min_length=10, max_length=10)


class CronogramaIn(BaseModel):
    tarefas: list[TarefaIn] = Field(..., max_length=500)


class AvancoTarefaIn(BaseModel):
    tarefa_id: str
    avanco_pct: float = Field(..., ge=0, le=100)
    nota: str = Field("", max_length=1000)


class AvancoIn(BaseModel):
    data_reuniao: str = Field(..., min_length=10, max_length=10)
    tarefas: list[AvancoTarefaIn] = Field(..., min_length=1, max_length=500)


class AtaLinhaIn(BaseModel):
    empresa_id: Optional[str] = None            # None = ponto geral
    ponto: str = Field(..., min_length=1, max_length=2000)
    ata_origem: Optional[int] = Field(None, ge=1, le=9999)
    estado: Literal["", "atraso", "importante", "memoria"] = ""
    fechado: bool = False


class AtaIn(BaseModel):
    data: str = Field(..., min_length=10, max_length=10)
    presentes: str = Field("", max_length=2000)
    resumo: str = Field("", max_length=6000)
    linhas: list[AtaLinhaIn] = Field(default_factory=list, max_length=1000)


# ------------------------------------------------------------------ lógica partilhada pelos dois públicos
async def _overview(ctx: Ctx) -> dict:
    s = await _settings(ctx.cid)
    parts = await db.chantier_participants.find({"chantier_id": ctx.cid, "status": {"$ne": "revoked"}},
                                                {"_id": 0, "invite_token_hash": 0}).to_list(500)
    inter = [{"participant_id": p["participant_id"], "nome": p.get("name") or p["email"],
              "perfil": oc.role_of_participant(p), "perfil_label": oc.ROLE_LABELS[oc.role_of_participant(p)],
              "lote": p.get("lot") or "", "estado": p.get("status"),
              **({"email": p["email"]} if oc.GESTOR in ctx.roles else {})} for p in parts]
    return {
        "obra": {"chantier_id": ctx.cid, "nome": ctx.chantier.get("name"), "ref": ctx.chantier.get("ref")},
        "eu": {**ctx.who(), "perfil_label": oc.ROLE_LABELS[ctx.role], "empresa_id": ctx.empresa_id,
               "gestor": oc.GESTOR in ctx.roles},
        "capacidades": {cap: ctx.can(cap) for cap in oc.CAPS},
        "intervenientes": inter,
        "definicoes": {"owner_role": s.get("owner_role"), "limite_subcontratacao_pct": s.get("limite_subcontratacao_pct"),
                       "tolerancia_avanco_pct": s.get("tolerancia_avanco_pct", 5.0)} if oc.GESTOR in ctx.roles else None,
        "contadores": {
            "planos": await db.obra_planos.count_documents({"chantier_id": ctx.cid}),
            "planos_sem_visto": await db.obra_planos.count_documents({"chantier_id": ctx.cid, "visto_estado": "pendente"}),
            "subs_pendentes": (await db.obra_subs.count_documents({**ctx.scope("subs"), "estado": "submetido"})
                               if ctx.can("subs.ver") else None),
            "autos_pendentes": (await db.obra_autos.count_documents(
                {**ctx.scope("autos"), "estado": {"$in": ["submetido", "validado_fiscalizacao"]}})
                if ctx.can("autos.ver") else None),
            "atas": await db.obra_atas.count_documents(
                {"chantier_id": ctx.cid, **({} if ctx.can("atas.editar") or oc.GESTOR in ctx.roles else {"publicada": True})}),
        },
    }


# ---- caixa de planos
async def _plano(ctx: Ctx, plano_id: str) -> dict:
    p = await db.obra_planos.find_one({"plano_id": plano_id, "chantier_id": ctx.cid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Plano não encontrado.")
    return p


async def _planos_list(ctx: Ctx) -> dict:
    ctx.need("planos.ver")
    rows = await db.obra_planos.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    return {"planos": rows}


async def _plano_create(ctx: Ctx, file: UploadFile, titulo: str, tipo: str, especialidade: str) -> dict:
    ctx.need("planos.carregar")
    if tipo not in ("arquitetura", "execucao", "caderno_encargos", "outro"):
        raise HTTPException(400, "Tipo de peça desconhecido.")
    plano_id = _id("pln")
    meta = await _store(ctx.cid, "planos", plano_id, file, ALLOWED_PLANO if tipo != "caderno_encargos" else ALLOWED_PECA)
    doc = {"plano_id": plano_id, "chantier_id": ctx.cid, "titulo": (titulo or meta["filename"]).strip()[:160], "tipo": tipo,
           "especialidade": (especialidade or "").strip()[:80], "empresa_id": ctx.empresa_id,
           "empresa_nome": await _empresa_nome(ctx.cid, ctx.empresa_id), "carregado_por": ctx.who(),
           "versoes": [{"versao": 1, **meta, "por": ctx.who()}], "versao_atual": 1,
           "visto_estado": "pendente" if tipo == "execucao" else "nao_aplicavel", "vistos": [], "anotacoes": [],
           "created_at": _now(), "updated_at": _now()}
    await db.obra_planos.insert_one(dict(doc))
    return doc


async def _plano_nova_versao(ctx: Ctx, plano_id: str, file: UploadFile) -> dict:
    p = await _plano(ctx, plano_id)
    autor = p.get("carregado_por", {}).get("id") == ctx.actor_id
    if not (ctx.can("planos.modificar") or (ctx.can("planos.carregar") and autor)):
        raise HTTPException(403, "Só o autor do plano ou um administrador da obra pode carregar uma nova versão.")
    n = int(p.get("versao_atual") or 1) + 1
    meta = await _store(ctx.cid, "planos", plano_id, file, ALLOWED_PLANO if p["tipo"] != "caderno_encargos" else ALLOWED_PECA)
    upd = {"versao_atual": n, "updated_at": _now()}
    if p["tipo"] == "execucao":
        upd["visto_estado"] = "pendente"   # uma nova versão anula o visto anterior
    await db.obra_planos.update_one({"plano_id": plano_id}, {"$set": upd, "$push": {"versoes": {"versao": n, **meta, "por": ctx.who()}}})
    return await _plano(ctx, plano_id)


async def _plano_edit(ctx: Ctx, plano_id: str, body: PlanoEditIn) -> dict:
    ctx.need("planos.modificar")
    p = await _plano(ctx, plano_id)
    upd = {"titulo": body.titulo.strip(), "tipo": body.tipo, "especialidade": body.especialidade.strip(), "updated_at": _now()}
    if body.tipo != p["tipo"]:
        upd["visto_estado"] = "pendente" if body.tipo == "execucao" else "nao_aplicavel"
    await db.obra_planos.update_one({"plano_id": plano_id}, {"$set": upd})
    return await _plano(ctx, plano_id)


async def _plano_delete(ctx: Ctx, plano_id: str) -> dict:
    ctx.need("planos.modificar")
    await _plano(ctx, plano_id)
    await db.obra_planos.delete_one({"plano_id": plano_id, "chantier_id": ctx.cid})
    return {"ok": True}


async def _plano_file(ctx: Ctx, plano_id: str, versao: Optional[int]) -> Response:
    ctx.need("planos.ver")
    p = await _plano(ctx, plano_id)
    v = versao or p.get("versao_atual") or 1
    meta = next((x for x in p.get("versoes") or [] if int(x.get("versao") or 0) == int(v)), None)
    if not meta:
        raise HTTPException(404, "Versão não encontrada.")
    return await _download(meta)


async def _plano_anotar(ctx: Ctx, plano_id: str, body: AnotacaoIn) -> dict:
    ctx.need("planos.anotar")
    await _plano(ctx, plano_id)
    nota = {"anotacao_id": _id("ano"), "texto": body.texto.strip(), "por": ctx.who(), "at": _now()}
    await db.obra_planos.update_one({"plano_id": plano_id}, {"$push": {"anotacoes": nota}, "$set": {"updated_at": _now()}})
    return await _plano(ctx, plano_id)


async def _plano_visto(ctx: Ctx, plano_id: str, body: VistoIn) -> dict:
    ctx.need("planos.visto")
    p = await _plano(ctx, plano_id)
    if p["tipo"] != "execucao":
        raise HTTPException(400, "O visto aplica-se aos planos de execução.")
    if body.decisao != "visto" and not body.observacoes.strip():
        raise HTTPException(400, "Indique as observações que justificam esta decisão.")
    visto = {"decisao": body.decisao, "observacoes": body.observacoes.strip(), "por": ctx.who(),
             "versao": p.get("versao_atual") or 1, "at": _now()}
    await db.obra_planos.update_one({"plano_id": plano_id}, {"$push": {"vistos": visto},
                                                             "$set": {"visto_estado": body.decisao, "updated_at": _now()}})
    return await _plano(ctx, plano_id)


FOCO_POR_TIPOS = {
    frozenset({"execucao", "arquitetura"}): "Verificar se o plano de execução respeita o plano de arquitetura: cotas, "
                                            "vãos, implantação, níveis e elementos em falta ou a mais.",
    frozenset({"execucao", "caderno_encargos"}): "Verificar se o plano de execução cumpre as cláusulas técnicas do "
                                                 "caderno de encargos: materiais, espessuras, classes e especificações.",
    frozenset({"execucao"}): "Comparar duas versões ou dois planos de execução: diferenças de cotas, elementos "
                             "acrescentados, removidos ou deslocados.",
}


async def _plano_comparar(ctx: Ctx, body: CompararIn, owner_user_id: str) -> dict:
    ctx.need("planos.comparar")
    a, b = await _plano(ctx, body.plano_a), await _plano(ctx, body.plano_b)
    foco = body.foco.strip() or FOCO_POR_TIPOS.get(frozenset({a["tipo"], b["tipo"]}), "Comparação completa dos dois documentos.")

    async def as_doc(p: dict) -> dict:
        meta = next(x for x in p["versoes"] if int(x["versao"]) == int(p["versao_atual"]))
        d: dict = {"label": f"{p['tipo']} — {p['titulo']} (v{p['versao_atual']})", "filename": meta["filename"]}
        if meta["content_type"] not in ALLOWED_DOCUMENT + ALLOWED_IMAGE:
            raise HTTPException(400, f"«{p['titulo']}»: a comparação por IA aceita PDF e imagens. Carregue uma versão em PDF.")
        data, _ = await asyncio.to_thread(storage.get_object, meta["path"])
        if meta["content_type"] in ALLOWED_DOCUMENT:
            d["pdf_bytes"] = data
        else:
            from engines.doc_compare import image_to_b64
            d["image_b64"] = image_to_b64(data)
        return d

    try:
        from engines.doc_compare import compare_documents
        result = await compare_documents(user_id=owner_user_id, project_id=None, doc_a=await as_doc(a), doc_b=await as_doc(b),
                                         focus=foco, individual=False, lang="pt")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("obra_colab compare failed: %s", e)
        raise HTTPException(503, "A comparação por IA não ficou disponível desta vez. Nenhum resultado foi registado.") from e
    rec = {"comparacao_id": _id("cmp"), "chantier_id": ctx.cid, "plano_a": a["plano_id"], "plano_b": b["plano_id"],
           "titulo_a": a["titulo"], "titulo_b": b["titulo"], "foco": foco, "resultado": result, "por": ctx.who(), "at": _now()}
    await db.obra_comparacoes.insert_one(dict(rec))
    return rec


# ---- regulamento e subempreiteiros
async def _regulamento(cid: str) -> list[dict]:
    s = await _settings(cid)
    return s.get("regulamento") or [dict(i, ativo=True) for i in oc.DEFAULT_REGULAMENTO]


async def _contrato(cid: str, empresa_id: Optional[str]) -> Optional[dict]:
    if not empresa_id:
        return None
    return await db.obra_contratos.find_one({"chantier_id": cid, "empresa_id": empresa_id}, {"_id": 0})


def _contrato_total(c: Optional[dict]) -> Optional[float]:
    if not c:
        return None
    return round(sum(float(l["quantidade"]) * float(l["preco_unitario"]) for l in c.get("linhas") or []), 2)


async def _sub_view(cid: str, s: dict) -> dict:
    st = await _settings(cid)
    controlo = oc.check_sub_request(s, await _regulamento(cid), hoje=_today(),
                                    valor_contrato_empresa=_contrato_total(await _contrato(cid, s.get("empresa_id"))),
                                    limite_subcontratacao_pct=st.get("limite_subcontratacao_pct"))
    return {**_pub(s), "controlo": controlo}


async def _sub(ctx: Ctx, sub_id: str) -> dict:
    s = await db.obra_subs.find_one({"sub_id": sub_id, "chantier_id": ctx.cid}, {"_id": 0})
    if not s or not ctx.sees("subs", s):
        raise HTTPException(404, "Pedido não encontrado.")   # 404 e não 403: não revela que existe
    return s


async def _subs_list(ctx: Ctx) -> dict:
    ctx.need("subs.ver")
    rows = await db.obra_subs.find(ctx.scope("subs"), {"_id": 0}).sort("updated_at", -1).to_list(1000)
    if not ctx.can("subs.submeter"):
        rows = [r for r in rows if r.get("estado") != "rascunho"]   # os rascunhos são só da empresa
    return {"pedidos": [await _sub_view(ctx.cid, r) for r in rows], "regulamento": await _regulamento(ctx.cid)}


async def _sub_create(ctx: Ctx, body: SubIn) -> dict:
    ctx.need("subs.submeter")
    doc = {"sub_id": _id("sub"), "chantier_id": ctx.cid, "empresa_id": ctx.empresa_id,
           "empresa_nome": await _empresa_nome(ctx.cid, ctx.empresa_id), **body.model_dump(), "documentos": [],
           "estado": "rascunho", "decisao": None, "historico": [], "created_at": _now(), "updated_at": _now()}
    await db.obra_subs.insert_one(dict(doc))
    return await _sub_view(ctx.cid, doc)


async def _sub_add_doc(ctx: Ctx, sub_id: str, key: str, validade: str, file: UploadFile) -> dict:
    ctx.need("subs.submeter")
    s = await _sub(ctx, sub_id)
    if s["estado"] not in ("rascunho", "submetido", "aprovado_com_reservas"):
        raise HTTPException(409, "Este pedido já foi decidido: já não aceita documentos.")
    if key not in {i["key"] for i in await _regulamento(ctx.cid)}:
        raise HTTPException(400, "Este documento não consta do regulamento desta obra.")
    meta = await _store(ctx.cid, "subs", sub_id, file, ALLOWED_PECA)
    docs = [d for d in s.get("documentos") or [] if d.get("key") != key]
    docs.append({"key": key, "validade": (validade or "")[:10], **meta, "por": ctx.who()})
    await db.obra_subs.update_one({"sub_id": sub_id}, {"$set": {"documentos": docs, "updated_at": _now()}})
    return await _sub_view(ctx.cid, await _sub(ctx, sub_id))


async def _sub_submit(ctx: Ctx, sub_id: str) -> dict:
    ctx.need("subs.submeter")
    s = await _sub(ctx, sub_id)
    if s["estado"] != "rascunho":
        raise HTTPException(409, "Este pedido já foi submetido.")
    await db.obra_subs.update_one({"sub_id": sub_id}, {"$set": {"estado": "submetido", "submetido_at": _now(), "updated_at": _now()},
                                                       "$push": {"historico": {"acao": "submetido", "por": ctx.who(), "at": _now()}}})
    return await _sub_view(ctx.cid, await _sub(ctx, sub_id))


async def _sub_doc_file(ctx: Ctx, sub_id: str, key: str) -> Response:
    ctx.need("subs.ver")
    s = await _sub(ctx, sub_id)
    meta = next((d for d in s.get("documentos") or [] if d.get("key") == key), None)
    if not meta:
        raise HTTPException(404, "Documento não encontrado.")
    return await _download(meta)


async def _sub_decide(ctx: Ctx, sub_id: str, body: SubDecisaoIn) -> dict:
    ctx.need("subs.decidir")
    s = await _sub(ctx, sub_id)
    if s["estado"] not in ("submetido", "aprovado_com_reservas"):
        raise HTTPException(409, "Este pedido não está à espera de decisão.")
    err = oc.validate_sub_decision(body.decisao, body.reservas, body.motivos)
    if err:
        raise HTTPException(400, err)
    view = await _sub_view(ctx.cid, s)
    if body.decisao == "aprovado" and not view["controlo"]["conforme"]:
        raise HTTPException(409, "O pedido não cumpre o regulamento: aprove com reservas ou recuse. "
                                 + " · ".join(view["controlo"]["motivos"][:5]))
    decisao = {"decisao": body.decisao, "reservas": body.reservas.strip(), "motivos": body.motivos.strip(),
               "controlo_no_momento": view["controlo"], "por": ctx.who(), "at": _now()}
    await db.obra_subs.update_one({"sub_id": sub_id}, {"$set": {"estado": body.decisao, "decisao": decisao, "updated_at": _now()},
                                                       "$push": {"historico": {"acao": body.decisao, "por": ctx.who(), "at": _now()}}})
    return await _sub_view(ctx.cid, await _sub(ctx, sub_id))


# ---- contratos e autos de medição
async def _contratos_list(ctx: Ctx) -> dict:
    ctx.need("contratos.ver")
    rows = await db.obra_contratos.find(ctx.scope("contratos"), {"_id": 0}).to_list(500)
    return {"contratos": [{**r, "total": _contrato_total(r)} for r in rows]}


async def _contrato_save(ctx: Ctx, empresa_id: str, body: ContratoIn) -> dict:
    ctx.need("contratos.gerir")
    if empresa_id not in {e["empresa_id"] for e in await _empresas(ctx.cid)}:
        raise HTTPException(404, "Empresa não encontrada nesta obra.")
    refs = [l.ref for l in body.linhas]
    if len(set(refs)) != len(refs):
        raise HTTPException(400, "Há artigos com a mesma referência no contrato.")
    if await db.obra_autos.count_documents({"chantier_id": ctx.cid, "empresa_id": empresa_id,
                                            "estado": {"$in": list(oc.AUTOS_QUE_CONTAM)}}):
        raise HTTPException(409, "Já existem autos sobre este contrato: registe um adicional em vez de o substituir.")
    doc = {"chantier_id": ctx.cid, "empresa_id": empresa_id, "empresa_nome": await _empresa_nome(ctx.cid, empresa_id),
           "titulo": body.titulo.strip(), "linhas": [l.model_dump() for l in body.linhas], "por": ctx.who(), "updated_at": _now()}
    if await db.obra_contratos.find_one({"chantier_id": ctx.cid, "empresa_id": empresa_id}, {"_id": 1}):
        await db.obra_contratos.update_one({"chantier_id": ctx.cid, "empresa_id": empresa_id}, {"$set": doc})
    else:
        await db.obra_contratos.insert_one(dict(doc))
    return {**doc, "total": _contrato_total(doc)}


async def _avanco_empresa(cid: str, empresa_id: str) -> Optional[float]:
    c = await db.obra_cronogramas.find_one({"chantier_id": cid, "empresa_id": empresa_id}, {"_id": 0})
    if not c or not c.get("avancos"):
        return None   # sem registo da fiscalização não há avanço de referência
    return oc.cronograma_summary(c.get("tarefas") or [], _today())["avanco_pct"]


async def _auto(ctx: Ctx, auto_id: str) -> dict:
    a = await db.obra_autos.find_one({"auto_id": auto_id, "chantier_id": ctx.cid}, {"_id": 0})
    if not a or not ctx.sees("autos", a):
        raise HTTPException(404, "Auto não encontrado.")
    return a


async def _autos_list(ctx: Ctx) -> dict:
    ctx.need("autos.ver")
    rows = await db.obra_autos.find(ctx.scope("autos"), {"_id": 0}).sort("created_at", -1).to_list(2000)
    return {"autos": rows}


async def _auto_create(ctx: Ctx, body: AutoIn) -> dict:
    ctx.need("autos.carregar")
    contrato = await _contrato(ctx.cid, ctx.empresa_id)
    if not contrato:
        raise HTTPException(409, "Ainda não há orçamento contratado registado para a sua empresa nesta obra. "
                                 "Peça ao dono de obra para o registar.")
    anteriores = await db.obra_autos.find({"chantier_id": ctx.cid, "empresa_id": ctx.empresa_id,
                                           "estado": {"$in": list(oc.AUTOS_QUE_CONTAM)}}, {"_id": 0}).to_list(2000)
    st = await _settings(ctx.cid)
    numero = body.numero or (max([int(a.get("numero") or 0) for a in anteriores], default=0) + 1)
    auto_in = {**body.model_dump(), "numero": numero}
    controlo = oc.check_auto(auto_in, contrato, anteriores,
                             avanco_registado_pct=await _avanco_empresa(ctx.cid, ctx.empresa_id),
                             tolerancia_avanco_pct=float(st.get("tolerancia_avanco_pct") or 5.0))
    doc = {"auto_id": _id("auto"), "chantier_id": ctx.cid, "empresa_id": ctx.empresa_id,
           "empresa_nome": await _empresa_nome(ctx.cid, ctx.empresa_id), "numero": numero, "periodo": body.periodo.strip(),
           "linhas": [l.model_dump() for l in body.linhas], "total_declarado": body.total_declarado,
           "observacoes": body.observacoes.strip(), "controlo": controlo, "estado": "submetido", "ficheiro": None,
           "historico": [{"acao": "submetido", "por": ctx.who(), "at": _now()}], "created_at": _now(), "updated_at": _now()}
    await db.obra_autos.insert_one(dict(doc))
    return doc


async def _auto_attach(ctx: Ctx, auto_id: str, file: UploadFile) -> dict:
    ctx.need("autos.carregar")
    a = await _auto(ctx, auto_id)
    if a["estado"] != "submetido":
        raise HTTPException(409, "Este auto já está em validação: já não pode ser alterado.")
    meta = await _store(ctx.cid, "autos", auto_id, file, ALLOWED_PECA)
    await db.obra_autos.update_one({"auto_id": auto_id}, {"$set": {"ficheiro": meta, "updated_at": _now()}})
    return await _auto(ctx, auto_id)


async def _auto_file(ctx: Ctx, auto_id: str) -> Response:
    ctx.need("autos.ver")
    a = await _auto(ctx, auto_id)
    if not a.get("ficheiro"):
        raise HTTPException(404, "Este auto não tem ficheiro anexado.")
    return await _download(a["ficheiro"])


async def _auto_decide(ctx: Ctx, auto_id: str, body: AutoDecisaoIn) -> dict:
    a = await _auto(ctx, auto_id)
    novo = next((n for n in (oc.next_auto_state(a["estado"], r, body.aprovar) for r in ctx.roles) if n), None)
    if not novo:
        raise HTTPException(403, "Não é a sua vez de validar este auto (ordem: fiscalização, depois dono de obra).")
    if not body.aprovar and not body.motivo.strip():
        raise HTTPException(400, "Indique o motivo da rejeição.")
    passo = {"acao": novo, "motivo": body.motivo.strip(), "por": ctx.who(), "at": _now()}
    await db.obra_autos.update_one({"auto_id": auto_id}, {"$set": {"estado": novo, "updated_at": _now()},
                                                          "$push": {"historico": passo}})
    return await _auto(ctx, auto_id)


# ---- planeamento
async def _cronogramas_list(ctx: Ctx) -> dict:
    ctx.need("cronograma.ver")
    rows = await db.obra_cronogramas.find(ctx.scope("cronograma"), {"_id": 0}).to_list(500)
    return {"cronogramas": [{**r, **oc.cronograma_summary(r.get("tarefas") or [], _today())} for r in rows]}


async def _cronograma_save(ctx: Ctx, body: CronogramaIn) -> dict:
    ctx.need("cronograma.carregar")
    for t in body.tarefas:
        if not oc._as_date(t.inicio) or not oc._as_date(t.fim) or t.fim < t.inicio:
            raise HTTPException(400, f"Datas inválidas na tarefa «{t.titulo}».")
    atual = await db.obra_cronogramas.find_one({"chantier_id": ctx.cid, "empresa_id": ctx.empresa_id}, {"_id": 0})
    antigas = {t["tarefa_id"]: t for t in (atual or {}).get("tarefas") or []}
    tarefas = []
    for t in body.tarefas:
        tid = t.tarefa_id if t.tarefa_id in antigas else _id("tar")
        old = antigas.get(tid, {})
        tarefas.append({"tarefa_id": tid, "titulo": t.titulo.strip(), "inicio": t.inicio, "fim": t.fim,
                        "avanco_pct": old.get("avanco_pct", 0), "nota": old.get("nota", "")})
    doc = {"chantier_id": ctx.cid, "empresa_id": ctx.empresa_id, "empresa_nome": await _empresa_nome(ctx.cid, ctx.empresa_id),
           "tarefas": tarefas, "updated_at": _now()}
    if atual:
        await db.obra_cronogramas.update_one({"chantier_id": ctx.cid, "empresa_id": ctx.empresa_id}, {"$set": doc})
    else:
        await db.obra_cronogramas.insert_one({**doc, "avancos": []})
    r = await db.obra_cronogramas.find_one({"chantier_id": ctx.cid, "empresa_id": ctx.empresa_id}, {"_id": 0})
    return {**r, **oc.cronograma_summary(r["tarefas"], _today())}


async def _cronograma_avanco(ctx: Ctx, empresa_id: str, body: AvancoIn) -> dict:
    ctx.need("cronograma.registar_avanco")
    c = await db.obra_cronogramas.find_one({"chantier_id": ctx.cid, "empresa_id": empresa_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Esta empresa ainda não carregou o seu cronograma.")
    novos = {t.tarefa_id: t for t in body.tarefas}
    desconhecidas = set(novos) - {t["tarefa_id"] for t in c["tarefas"]}
    if desconhecidas:
        raise HTTPException(400, "Tarefa desconhecida neste cronograma.")
    tarefas = [{**t, "avanco_pct": novos[t["tarefa_id"]].avanco_pct, "nota": novos[t["tarefa_id"]].nota.strip()}
               if t["tarefa_id"] in novos else t for t in c["tarefas"]]
    registo = {"data_reuniao": body.data_reuniao, "por": ctx.who(), "at": _now(),
               "tarefas": [t.model_dump() for t in body.tarefas]}
    await db.obra_cronogramas.update_one({"chantier_id": ctx.cid, "empresa_id": empresa_id},
                                         {"$set": {"tarefas": tarefas, "updated_at": _now()}, "$push": {"avancos": registo}})
    r = await db.obra_cronogramas.find_one({"chantier_id": ctx.cid, "empresa_id": empresa_id}, {"_id": 0})
    return {**r, **oc.cronograma_summary(r["tarefas"], _today())}


# ---- ata semanal
async def _ata(ctx: Ctx, ata_id: str) -> dict:
    a = await db.obra_atas.find_one({"ata_id": ata_id, "chantier_id": ctx.cid}, {"_id": 0})
    editor = ctx.can("atas.editar")
    if not a or (not a.get("publicada") and not editor and oc.GESTOR not in ctx.roles):
        raise HTTPException(404, "Ata não encontrada.")
    return a


async def _atas_list(ctx: Ctx) -> dict:
    ctx.need("atas.ver")
    q: dict = {"chantier_id": ctx.cid}
    if not ctx.can("atas.editar") and oc.GESTOR not in ctx.roles:
        q["publicada"] = True
    rows = await db.obra_atas.find(q, {"_id": 0}).sort("numero", -1).to_list(500)
    nomes = {e["empresa_id"]: e["nome"] for e in await _empresas(ctx.cid)}
    out = []
    for a in rows:
        a = oc.ata_for_role(a, ctx.role if oc.GESTOR not in ctx.roles else oc.GESTOR, ctx.empresa_id)
        a["linhas"] = [{**l, "empresa_nome": nomes.get(l.get("empresa_id"), "") if l.get("empresa_id") else "Geral",
                        "estado_label": oc.ATA_ESTADO_LABEL.get(l.get("estado") or "", "")} for l in a.get("linhas") or []]
        out.append(a)
    return {"atas": out, "estados": oc.ATA_ESTADO_LABEL}


async def _ata_draft(ctx: Ctx) -> dict:
    ctx.need("atas.editar")
    ultima = await db.obra_atas.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("numero", -1).to_list(1)
    anterior = ultima[0] if ultima else None
    numero = int((anterior or {}).get("numero") or 0) + 1
    empresas = await _empresas(ctx.cid)
    cron = {}
    async for c in db.obra_cronogramas.find({"chantier_id": ctx.cid}, {"_id": 0}):
        cron[c["empresa_id"]] = oc.cronograma_summary(c.get("tarefas") or [], _today())
    vistos: dict[str, list[str]] = {}
    async for p in db.obra_planos.find({"chantier_id": ctx.cid, "visto_estado": "pendente"}, {"_id": 0}):
        if p.get("empresa_id"):
            vistos.setdefault(p["empresa_id"], []).append(p["titulo"])
    autos: dict[str, int] = {}
    async for a in db.obra_autos.find({"chantier_id": ctx.cid, "estado": {"$in": ["submetido", "validado_fiscalizacao"]}}, {"_id": 0}):
        autos[a["empresa_id"]] = autos.get(a["empresa_id"], 0) + 1
    return {"numero": numero, "data": _today().isoformat(),
            "linhas": oc.draft_ata(numero, anterior, empresas, cron, vistos, autos), "empresas": empresas}


async def _ata_save(ctx: Ctx, body: AtaIn, ata_id: Optional[str]) -> dict:
    ctx.need("atas.editar")
    validas = {e["empresa_id"] for e in await _empresas(ctx.cid)}
    for l in body.linhas:
        if l.empresa_id and l.empresa_id not in validas:
            raise HTTPException(400, "Uma linha refere uma empresa que não pertence a esta obra.")
    if ata_id:
        a = await _ata(ctx, ata_id)
        if a.get("publicada"):
            raise HTTPException(409, "Uma ata publicada já não pode ser alterada: corrija na ata seguinte.")
        numero = a["numero"]
    else:
        ultima = await db.obra_atas.find({"chantier_id": ctx.cid}, {"_id": 0}).sort("numero", -1).to_list(1)
        numero = int((ultima[0] if ultima else {}).get("numero") or 0) + 1
        ata_id = _id("ata")
    linhas = [{**l.model_dump(), "ata_origem": l.ata_origem or numero} for l in body.linhas]
    doc = {"ata_id": ata_id, "chantier_id": ctx.cid, "numero": numero, "data": body.data, "presentes": body.presentes.strip(),
           "resumo": body.resumo.strip(), "linhas": linhas, "por": ctx.who(), "updated_at": _now()}
    if await db.obra_atas.find_one({"ata_id": ata_id}, {"_id": 1}):
        await db.obra_atas.update_one({"ata_id": ata_id}, {"$set": doc})
    else:
        await db.obra_atas.insert_one({**doc, "publicada": False, "fotos": [], "created_at": _now()})
    return _pub(await db.obra_atas.find_one({"ata_id": ata_id}, {"_id": 0}))


async def _ata_publish(ctx: Ctx, ata_id: str) -> dict:
    ctx.need("atas.editar")
    await _ata(ctx, ata_id)
    await db.obra_atas.update_one({"ata_id": ata_id}, {"$set": {"publicada": True, "publicada_at": _now()}})
    return _pub(await db.obra_atas.find_one({"ata_id": ata_id}, {"_id": 0}))


async def _ata_foto(ctx: Ctx, ata_id: str, file: UploadFile, legenda: str) -> dict:
    ctx.need("atas.editar")
    a = await _ata(ctx, ata_id)
    if a.get("publicada"):
        raise HTTPException(409, "Uma ata publicada já não pode ser alterada.")
    meta = await _store(ctx.cid, "atas", ata_id, file, ALLOWED_IMAGE)
    foto = {"foto_id": _id("fot"), "legenda": (legenda or "").strip()[:200], **meta}
    await db.obra_atas.update_one({"ata_id": ata_id}, {"$push": {"fotos": foto}})
    return foto


async def _ata_foto_file(ctx: Ctx, ata_id: str, foto_id: str) -> Response:
    ctx.need("atas.ver")
    a = await _ata(ctx, ata_id)
    meta = next((f for f in a.get("fotos") or [] if f.get("foto_id") == foto_id), None)
    if not meta:
        raise HTTPException(404, "Fotografia não encontrada.")
    return await _download(meta)


# ------------------------------------------------------------------ registo das rotas nos dois routers
def _mount(router: APIRouter, base: str, dep) -> None:
    b = base + "/colab"

    @router.get(b)
    async def overview(ctx: Ctx = Depends(dep)):
        return await _overview(ctx)

    # caixa de planos
    @router.get(b + "/planos")
    async def planos(ctx: Ctx = Depends(dep)):
        return await _planos_list(ctx)

    @router.post(b + "/planos", status_code=201)
    async def plano_create(file: UploadFile = File(...), titulo: str = Form(""), tipo: str = Form("execucao"),
                           especialidade: str = Form(""), ctx: Ctx = Depends(dep)):
        return _pub(await _plano_create(ctx, file, titulo, tipo, especialidade))

    @router.post(b + "/planos/comparar")
    async def plano_comparar(body: CompararIn, ctx: Ctx = Depends(dep)):
        return _pub(await _plano_comparar(ctx, body, ctx.chantier["user_id"]))

    @router.post(b + "/planos/{plano_id}/versoes")
    async def plano_versao(plano_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(dep)):
        return await _plano_nova_versao(ctx, plano_id, file)

    @router.put(b + "/planos/{plano_id}")
    async def plano_edit(plano_id: str, body: PlanoEditIn, ctx: Ctx = Depends(dep)):
        return await _plano_edit(ctx, plano_id, body)

    @router.delete(b + "/planos/{plano_id}")
    async def plano_delete(plano_id: str, ctx: Ctx = Depends(dep)):
        return await _plano_delete(ctx, plano_id)

    @router.get(b + "/planos/{plano_id}/ficheiro")
    async def plano_file(plano_id: str, versao: Optional[int] = None, ctx: Ctx = Depends(dep)):
        return await _plano_file(ctx, plano_id, versao)

    @router.post(b + "/planos/{plano_id}/anotacoes")
    async def plano_anotar(plano_id: str, body: AnotacaoIn, ctx: Ctx = Depends(dep)):
        return await _plano_anotar(ctx, plano_id, body)

    @router.post(b + "/planos/{plano_id}/visto")
    async def plano_visto(plano_id: str, body: VistoIn, ctx: Ctx = Depends(dep)):
        return await _plano_visto(ctx, plano_id, body)

    # subempreiteiros
    @router.get(b + "/subs")
    async def subs(ctx: Ctx = Depends(dep)):
        return await _subs_list(ctx)

    @router.post(b + "/subs", status_code=201)
    async def sub_create(body: SubIn, ctx: Ctx = Depends(dep)):
        return await _sub_create(ctx, body)

    @router.post(b + "/subs/{sub_id}/documentos")
    async def sub_doc(sub_id: str, key: str = Form(...), validade: str = Form(""), file: UploadFile = File(...),
                      ctx: Ctx = Depends(dep)):
        return await _sub_add_doc(ctx, sub_id, key, validade, file)

    @router.get(b + "/subs/{sub_id}/documentos/{key}")
    async def sub_doc_file(sub_id: str, key: str, ctx: Ctx = Depends(dep)):
        return await _sub_doc_file(ctx, sub_id, key)

    @router.post(b + "/subs/{sub_id}/submeter")
    async def sub_submit(sub_id: str, ctx: Ctx = Depends(dep)):
        return await _sub_submit(ctx, sub_id)

    @router.post(b + "/subs/{sub_id}/decisao")
    async def sub_decide(sub_id: str, body: SubDecisaoIn, ctx: Ctx = Depends(dep)):
        return await _sub_decide(ctx, sub_id, body)

    @router.get(b + "/regulamento")
    async def regulamento(ctx: Ctx = Depends(dep)):
        ctx.need("subs.ver")
        return {"itens": await _regulamento(ctx.cid)}

    @router.put(b + "/regulamento")
    async def regulamento_save(body: RegulamentoIn, ctx: Ctx = Depends(dep)):
        ctx.need("subs.regulamento")
        keys = [i.key for i in body.itens]
        if len(set(keys)) != len(keys):
            raise HTTPException(400, "Há requisitos repetidos no regulamento.")
        itens = [i.model_dump() for i in body.itens]
        s = await _settings(ctx.cid)
        s["regulamento"] = itens
        await _save_settings(ctx.cid, s)
        return {"itens": itens}

    # contratos e autos
    @router.get(b + "/contratos")
    async def contratos(ctx: Ctx = Depends(dep)):
        return await _contratos_list(ctx)

    @router.put(b + "/contratos/{empresa_id}")
    async def contrato_save(empresa_id: str, body: ContratoIn, ctx: Ctx = Depends(dep)):
        return await _contrato_save(ctx, empresa_id, body)

    @router.get(b + "/autos")
    async def autos(ctx: Ctx = Depends(dep)):
        return await _autos_list(ctx)

    @router.post(b + "/autos", status_code=201)
    async def auto_create(body: AutoIn, ctx: Ctx = Depends(dep)):
        return _pub(await _auto_create(ctx, body))

    @router.post(b + "/autos/{auto_id}/ficheiro")
    async def auto_attach(auto_id: str, file: UploadFile = File(...), ctx: Ctx = Depends(dep)):
        return await _auto_attach(ctx, auto_id, file)

    @router.get(b + "/autos/{auto_id}/ficheiro")
    async def auto_file(auto_id: str, ctx: Ctx = Depends(dep)):
        return await _auto_file(ctx, auto_id)

    @router.post(b + "/autos/{auto_id}/decisao")
    async def auto_decide(auto_id: str, body: AutoDecisaoIn, ctx: Ctx = Depends(dep)):
        return await _auto_decide(ctx, auto_id, body)

    # planeamento
    @router.get(b + "/cronogramas")
    async def cronogramas(ctx: Ctx = Depends(dep)):
        return await _cronogramas_list(ctx)

    @router.put(b + "/cronograma")
    async def cronograma_save(body: CronogramaIn, ctx: Ctx = Depends(dep)):
        return await _cronograma_save(ctx, body)

    @router.post(b + "/cronogramas/{empresa_id}/avanco")
    async def cronograma_avanco(empresa_id: str, body: AvancoIn, ctx: Ctx = Depends(dep)):
        return await _cronograma_avanco(ctx, empresa_id, body)

    # atas
    @router.get(b + "/atas")
    async def atas(ctx: Ctx = Depends(dep)):
        return await _atas_list(ctx)

    @router.post(b + "/atas/rascunho")
    async def ata_draft(ctx: Ctx = Depends(dep)):
        return await _ata_draft(ctx)

    @router.post(b + "/atas", status_code=201)
    async def ata_create(body: AtaIn, ctx: Ctx = Depends(dep)):
        return await _ata_save(ctx, body, None)

    @router.put(b + "/atas/{ata_id}")
    async def ata_update(ata_id: str, body: AtaIn, ctx: Ctx = Depends(dep)):
        return await _ata_save(ctx, body, ata_id)

    @router.post(b + "/atas/{ata_id}/publicar")
    async def ata_publish(ata_id: str, ctx: Ctx = Depends(dep)):
        return await _ata_publish(ctx, ata_id)

    @router.post(b + "/atas/{ata_id}/fotos", status_code=201)
    async def ata_foto(ata_id: str, file: UploadFile = File(...), legenda: str = Form(""), ctx: Ctx = Depends(dep)):
        return await _ata_foto(ctx, ata_id, file, legenda)

    @router.get(b + "/atas/{ata_id}/fotos/{foto_id}")
    async def ata_foto_file(ata_id: str, foto_id: str, ctx: Ctx = Depends(dep)):
        return await _ata_foto_file(ctx, ata_id, foto_id)


async def _save_settings(cid: str, s: dict) -> None:
    s = {k: v for k, v in s.items() if k != "_id"}
    s["chantier_id"] = cid
    s["updated_at"] = _now()
    if await db.obra_colab_settings.find_one({"chantier_id": cid}, {"_id": 1}):
        await db.obra_colab_settings.update_one({"chantier_id": cid}, {"$set": s})
    else:
        await db.obra_colab_settings.insert_one(dict(s))


_mount(pro_router, "/{chantier_id}", ctx_pro)
_mount(portal_router, "/{ref}", ctx_portal)


# ------------------------------------------------------------------ só o titular: definições e intervenientes
@pro_router.put("/{chantier_id}/colab/definicoes")
async def save_definicoes(body: SettingsIn, ctx: Ctx = Depends(ctx_pro)) -> dict:
    s = await _settings(ctx.cid)
    s.update(body.model_dump())
    await _save_settings(ctx.cid, s)
    return {"ok": True, **body.model_dump()}


@pro_router.post("/{chantier_id}/colab/intervenientes", status_code=201)
async def add_interveniente(chantier_id: str, body: IntervenienteIn, user=Depends(current_user)) -> dict:
    """Convida um interveniente com um dos quatro perfis. Reutiliza o convite do portal (e-mail + código)."""
    legacy = "subcontractor" if body.perfil == oc.EMPRESA else "client"
    created = await portal_routes.invite_participant(
        chantier_id, portal_routes.ParticipantIn(role=legacy, email=body.email, name=body.nome, lot=body.lote), user)
    await db.chantier_participants.update_one({"participant_id": created["participant_id"]},
                                              {"$set": {"colab_role": body.perfil, "updated_at": _now()}})
    return {**created, "colab_role": body.perfil, "perfil_label": oc.ROLE_LABELS[body.perfil]}


@pro_router.put("/{chantier_id}/colab/intervenientes/{participant_id}")
async def set_perfil(participant_id: str, body: PerfilIn, ctx: Ctx = Depends(ctx_pro)) -> dict:
    p = await db.chantier_participants.find_one({"participant_id": participant_id, "chantier_id": ctx.cid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Interveniente não encontrado.")
    antigo = oc.role_of_participant(p)
    if antigo == oc.EMPRESA and body.perfil != oc.EMPRESA and await db.obra_autos.count_documents(
            {"chantier_id": ctx.cid, "empresa_id": participant_id}):
        raise HTTPException(409, "Esta empresa já tem autos nesta obra: o perfil não pode ser alterado.")
    upd: dict = {"colab_role": body.perfil, "updated_at": _now()}
    if body.nome is not None:
        upd["name"] = body.nome.strip()
    if body.lote is not None:
        upd["lot"] = body.lote.strip()
    await db.chantier_participants.update_one({"participant_id": participant_id}, {"$set": upd, "$inc": {"session_version": 0}})
    return {"ok": True, "perfil": body.perfil, "perfil_label": oc.ROLE_LABELS[body.perfil]}
