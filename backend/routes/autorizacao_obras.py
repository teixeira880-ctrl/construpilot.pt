"""Rotas do módulo «Autorização de obras» (Lote N1 + N2 + N3 + N4 + endurecimento N5).

Separação clara entre:
  - router         : endpoints públicos (sem auth) — diagnóstico, meta, settings, guia
                     — e endpoints protegidos (require current_user) para IA e dossier
  - router_publico : endpoints de assinatura via token (técnico subscritor, sem auth)
  - router_admin   : endpoints de administração (gate admin_user)
"""
import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.rate_limit import limiter
from core.security import admin_user, current_user, optional_user

from engines.autorizacao_obras_pt.rules import LEI_RJUE, SCENARIOS, diagnosticar
from engines.autorizacao_obras_pt.dossier import (
    checklist_pecas,
    estimativa_e_calendario,
    gerar_dossier,
    gerar_memoria_descritiva,
)
from engines.autorizacao_obras_pt.subscricao import (
    ESPECIALIDADES,
    atualizar_tecnico,
    criar_pedido_subscricao,
    criar_tecnico,
    eliminar_tecnico,
    ler_pedido_por_token,
    listar_tecnicos,
    registar_termo_responsabilidade,
)
from engines.autorizacao_obras_pt.settings import get_settings, set_settings
from engines.autorizacao_obras_pt.guia_pepu import gerar_guia_pepu_pdf

router = APIRouter(prefix="/particulares/autorizacao", tags=["autorizacao-obras"])
router_publico = APIRouter(prefix="/publico/autorizacao", tags=["autorizacao-obras-publico"])
router_admin = APIRouter(prefix="/admin/autorizacao-obras", tags=["autorizacao-obras-admin"],
                          dependencies=[Depends(admin_user)])


# ---------------------------------------------------------------- Diagnóstico (público)

class DiagnosticoIn(BaseModel):
    tipo_obra: str
    subtipo_muro: Optional[str] = None
    area_implantacao_m2: Optional[float] = 0.0
    area_construcao_total_m2: Optional[float] = 0.0
    area_construcao_criada_m2: Optional[float] = 0.0
    altura_m: Optional[float] = 0.0
    indice_implantacao: Optional[float] = None
    afastamento_min_m: Optional[float] = None
    concelho: Optional[str] = None
    freguesia: Optional[str] = None
    confina_via_publica: bool = False
    zona_protegida: bool = False
    imovel_classificado: bool = False
    tem_edificacao_principal: bool = True
    altera_fachada: bool = False
    altera_uso: bool = False
    altera_cobertura: bool = False
    tem_pdm_com_parametros: bool = False
    tem_loteamento_pip: bool = False
    zona_urbana_consolidada: bool = False
    pdm_altura_max_m: Optional[float] = None
    pdm_indice_implantacao: Optional[float] = None
    pdm_afastamento_min_m: Optional[float] = None


@router.get("/meta")
@limiter.limit("60/hour")
async def meta(request: Request, response: Response) -> dict:
    return {"ok": True, "lei_base": LEI_RJUE, "scenarios": SCENARIOS}


@router.post("/diagnostico")
@limiter.limit("30/hour")
async def diagnostico(request: Request, response: Response, body: DiagnosticoIn) -> dict:
    resultado = diagnosticar(body.model_dump())
    return {"ok": True, **resultado}


# ---------------------------------------------------------------- IA / dossier (auth)

class RequerenteIn(BaseModel):
    nome: Optional[str] = ""
    nif: Optional[str] = ""
    morada: Optional[str] = ""
    telefone: Optional[str] = ""
    email: Optional[str] = ""


class PecaIn(BaseModel):
    nome: str
    bytes_b64: Optional[str] = None


class MemoriaPreviewIn(BaseModel):
    respostas: Dict[str, Any] = Field(default_factory=dict)
    diagnostico: Dict[str, Any] = Field(default_factory=dict)


class DossierIn(BaseModel):
    respostas: Dict[str, Any] = Field(default_factory=dict)
    diagnostico: Dict[str, Any] = Field(default_factory=dict)
    requerente: Optional[RequerenteIn] = None
    pecas: List[PecaIn] = Field(default_factory=list)
    memoria_override: Optional[str] = None


@router.post("/memoria/preview")
@limiter.limit("10/hour")
async def memoria_preview(request: Request, response: Response, body: MemoriaPreviewIn,
                           user=Depends(current_user)) -> dict:
    texto = await gerar_memoria_descritiva(body.respostas or {}, body.diagnostico or {})
    return {"ok": True, "memoria_texto": texto}


@router.post("/checklist")
@limiter.limit("60/hour")
async def checklist(request: Request, response: Response, body: MemoriaPreviewIn) -> dict:
    cl = checklist_pecas(body.diagnostico or {}, [])
    return {"ok": True, **cl}


@router.post("/dossier/gerar")
@limiter.limit("5/hour")
async def dossier_gerar(request: Request, response: Response, body: DossierIn,
                         user=Depends(current_user)) -> dict:
    """Gera o dossier completo. Requer sessão iniciada (consumo de IA + PDF)."""
    pecas = []
    for p in body.pecas:
        if p.bytes_b64:
            try:
                pecas.append({"nome": p.nome, "bytes": base64.b64decode(p.bytes_b64)})
            except Exception:  # noqa: BLE001
                pecas.append({"nome": p.nome, "bytes": b""})
        else:
            pecas.append({"nome": p.nome, "bytes": b""})
    requerente = body.requerente.model_dump() if body.requerente else None
    out = await gerar_dossier(body.respostas or {}, body.diagnostico or {},
                               pecas_carregadas=pecas, requerente=requerente,
                               memoria_override=body.memoria_override)
    return {
        "ok": True,
        "version": out["version"],
        "pdf_unico_b64": base64.b64encode(out["pdf_unico"]).decode("ascii"),
        "zip_b64": base64.b64encode(out["zip"]).decode("ascii"),
        "memoria_texto": out["memoria_texto"],
        "checklist": out["checklist"],
        "estimativa": out["estimativa"],
        "ficheiros": out["ficheiros"],
    }


# ---------------------------------------------------------------- Subscrição

@router.get("/tecnicos")
@limiter.limit("30/hour")
async def tecnicos_disponiveis(request: Request, response: Response,
                                 especialidade: Optional[str] = None,
                                 regiao: Optional[str] = None) -> dict:
    lista = await listar_tecnicos(especialidade=especialidade, regiao=regiao)
    return {"ok": True, "tecnicos": lista, "catalogo_vazio": len(lista) == 0}


class PedidoSubscricaoIn(BaseModel):
    tecnico_id: Optional[str] = None
    requerente_nome: Optional[str] = None
    requerente_email: Optional[str] = None
    dossier: Dict[str, Any] = Field(default_factory=dict)
    # Técnico indicado pelo próprio requerente (quando o catálogo não cobre a sua região)
    tecnico_custom: Optional[Dict[str, Any]] = None


@router.post("/subscricao/pedir")
@limiter.limit("20/day")
async def pedir_subscricao(request: Request, response: Response, body: PedidoSubscricaoIn,
                            user=Depends(current_user)) -> dict:
    try:
        res = await criar_pedido_subscricao(
            dossier=body.dossier or {},
            tecnico_id=body.tecnico_id,
            requerente_nome=body.requerente_nome,
            requerente_email=body.requerente_email,
            tecnico_custom=body.tecnico_custom,
        )
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, **res}


class TermoResponsabilidadeIn(BaseModel):
    nome: str
    ordem: str
    numero: str
    especialidade: str
    assinatura_b64: Optional[str] = None
    observacoes: Optional[str] = None


@router_publico.get("/subscrever/{token}")
@limiter.limit("60/hour")
async def ver_pedido_publico(request: Request, response: Response, token: str) -> dict:
    doc = await ler_pedido_por_token(token)
    if not doc:
        return {"ok": False, "error": "token_invalido"}
    if isinstance(doc, dict) and doc.get("error"):
        return {"ok": False, **doc}
    doc.pop("signing_token", None)
    return {"ok": True, "pedido": doc}


@router_publico.post("/subscrever/{token}/termo")
@limiter.limit("10/hour")
async def submeter_termo(request: Request, response: Response, token: str, body: TermoResponsabilidadeIn) -> dict:
    return await registar_termo_responsabilidade(
        token, body.nome, body.ordem, body.numero, body.especialidade,
        body.assinatura_b64, body.observacoes,
    )


# ---------------------------------------------------------------- Flag + pagamento (N4)

@router.get("/settings")
@limiter.limit("60/hour")
async def ver_settings_publicos(request: Request, response: Response) -> dict:
    s = await get_settings()
    return {
        "ok": True,
        "sale_enabled": bool(s.get("sale_enabled")),
        "price_eur": s.get("price_eur", 39),
        "currency": s.get("currency", "eur"),
        "included_in_pro": bool(s.get("included_in_pro", True)),
        "included_in_business": bool(s.get("included_in_business", True)),
    }


class ComprarIn(BaseModel):
    success_url: str
    cancel_url: str


@router.post("/comprar")
@limiter.limit("20/hour")
async def comprar(request: Request, response: Response, body: ComprarIn,
                   user=Depends(current_user)) -> dict:
    s = await get_settings()
    if not s.get("sale_enabled"):
        return {"ok": False, "error": "sale_disabled",
                "mensagem": "Venda do processo de autorização de obras temporariamente desativada."}
    try:
        import os
        import stripe  # type: ignore
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
        if not stripe.api_key:
            return {"ok": False, "error": "stripe_nao_configurado"}
        price_cents = int(round(float(s.get("price_eur", 39)) * 100))
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": s.get("currency", "eur"),
                    "product_data": {"name": s.get("stripe_product_name", "Processo de autorização de obras")},
                    "unit_amount": price_cents,
                },
                "quantity": 1,
            }],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"product": "autorizacao_obras", "user_id": str(user.get("_id") or user.get("id") or "")},
        )
        return {"ok": True, "checkout_url": session.url, "session_id": session.id}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "stripe_erro", "detalhe": str(e)[:200]}


@router.get("/guia-pepu.pdf")
@limiter.limit("60/hour")
async def descarregar_guia_pepu(request: Request, response: Response):
    pdf = gerar_guia_pepu_pdf()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="guia-pepu.pdf"'})


# ---------------------------------------------------------------- Admin: settings + CRUD

class AdminSettingsIn(BaseModel):
    sale_enabled: Optional[bool] = None
    price_eur: Optional[float] = None
    currency: Optional[str] = None
    included_in_pro: Optional[bool] = None
    included_in_business: Optional[bool] = None
    stripe_product_name: Optional[str] = None


@router_admin.get("/settings")
async def admin_ler_settings() -> dict:
    return {"ok": True, "settings": await get_settings()}


@router_admin.put("/settings")
async def admin_gravar_settings(body: AdminSettingsIn, admin=Depends(admin_user)) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    uid = str(admin.get("_id") or admin.get("id") or "admin")
    return {"ok": True, "settings": await set_settings(patch, admin_user_id=uid)}


class TecnicoIn(BaseModel):
    id: Optional[str] = None
    nome: str
    email: EmailStr
    telefone: Optional[str] = ""
    ordem: Optional[str] = "OA"
    numero: Optional[str] = ""
    especialidade: str = "arquitetura"
    regiao: Optional[str] = ""
    preco_indicativo_eur: Optional[float] = 0
    prazo_dias: Optional[int] = 7
    ativo: Optional[bool] = True


class TecnicoPatchIn(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    ordem: Optional[str] = None
    numero: Optional[str] = None
    especialidade: Optional[str] = None
    regiao: Optional[str] = None
    preco_indicativo_eur: Optional[float] = None
    prazo_dias: Optional[int] = None
    ativo: Optional[bool] = None


@router_admin.get("/tecnicos")
async def admin_listar_tecnicos() -> dict:
    lista = await listar_tecnicos(incluir_inativos=True)
    return {"ok": True, "tecnicos": lista, "especialidades": list(ESPECIALIDADES)}


@router_admin.post("/tecnicos")
async def admin_criar_tecnico(body: TecnicoIn) -> dict:
    created = await criar_tecnico(body.model_dump())
    return {"ok": True, "tecnico": created}


@router_admin.put("/tecnicos/{tecnico_id}")
async def admin_atualizar_tecnico(tecnico_id: str, body: TecnicoPatchIn) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await atualizar_tecnico(tecnico_id, patch)
    if not updated:
        return {"ok": False, "error": "nao_encontrado"}
    return {"ok": True, "tecnico": updated}


@router_admin.delete("/tecnicos/{tecnico_id}")
async def admin_eliminar_tecnico(tecnico_id: str) -> dict:
    ok = await eliminar_tecnico(tecnico_id)
    return {"ok": ok, **({} if ok else {"error": "nao_encontrado"})}
