"""Subscrição de processos por técnico parceiro (Lote N3 + endurecimento N5).

- Catálogo real guardado em Mongo (`tecnicos_parceiros`), gerido pelo admin.
- JSON em disco (`backend/data/tecnicos_parceiros.json`) só é usado como fallback
  (deve estar vazio em produção).
- Permite subscrição por técnico **customizado** indicado pelo próprio requerente.
- Token com expiração (30 dias) e proteção contra reutilização.
- Notificação por e-mail via Resend (engines.emailer); modo degradado se não configurado.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.db import db

log = logging.getLogger("autorizacao.subscricao")

COLLECTION_PEDIDOS = "autorizacao_subscricoes"
COLLECTION_TECNICOS = "tecnicos_parceiros"
CATALOGO_PATH = Path(__file__).resolve().parents[2] / "data" / "tecnicos_parceiros.json"
TOKEN_VALIDADE_DIAS = 30

ESPECIALIDADES = (
    "arquitetura", "engenheiro_estruturas", "engenheiro_civil",
    "engenheiro_eletrotecnico", "engenheiro_mecanico", "coordenador_projeto",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ser(doc: Dict[str, Any]) -> Dict[str, Any]:
    if not doc:
        return {}
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _carregar_fallback_json() -> List[Dict[str, Any]]:
    try:
        data = json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


# --------------------------------------------------------------------- catálogo

async def listar_tecnicos(especialidade: Optional[str] = None,
                           regiao: Optional[str] = None,
                           incluir_inativos: bool = False) -> List[Dict[str, Any]]:
    """Lista os técnicos reais a partir do Mongo. Fallback: JSON em disco (idealmente vazio em prod)."""
    cursor = db[COLLECTION_TECNICOS].find({})
    docs = [t async for t in cursor]
    if not docs:
        docs = _carregar_fallback_json()
    out: List[Dict[str, Any]] = []
    for t in docs:
        if not incluir_inativos and t.get("ativo") is False:
            continue
        if especialidade and t.get("especialidade") != especialidade:
            continue
        if regiao and regiao.lower() not in (t.get("regiao") or "").lower():
            continue
        out.append(_ser(t))
    return out


# Compat: a função antiga era sync e lia JSON — mantém-se para quem a importe.
def carregar_tecnicos() -> List[Dict[str, Any]]:
    return _carregar_fallback_json()


def filtrar_tecnicos(especialidade: Optional[str] = None,
                     regiao: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for t in carregar_tecnicos():
        if especialidade and t.get("especialidade") != especialidade:
            continue
        if regiao and regiao.lower() not in (t.get("regiao") or "").lower():
            continue
        out.append(t)
    return out


async def tecnico_por_id(tecnico_id: str) -> Optional[Dict[str, Any]]:
    """Procura em Mongo primeiro; cai para JSON apenas se Mongo estiver vazio."""
    doc = await db[COLLECTION_TECNICOS].find_one({"id": tecnico_id})
    if doc:
        return _ser(doc)
    for t in carregar_tecnicos():
        if t.get("id") == tecnico_id:
            return t
    return None


async def criar_tecnico(data: Dict[str, Any]) -> Dict[str, Any]:
    tid = data.get("id") or f"tec_{secrets.token_hex(5)}"
    doc = {
        "id": tid,
        "nome": data.get("nome") or "",
        "email": data.get("email") or data.get("email_contacto") or "",
        "email_contacto": data.get("email") or data.get("email_contacto") or "",
        "telefone": data.get("telefone") or "",
        "ordem": data.get("ordem") or "OA",
        "numero": data.get("numero") or "",
        "especialidade": data.get("especialidade") or "arquitetura",
        "regiao": data.get("regiao") or "",
        "preco_indicativo_eur": data.get("preco_indicativo_eur") or 0,
        "prazo_dias": data.get("prazo_dias") or 7,
        "ativo": True if data.get("ativo") is None else bool(data.get("ativo")),
        "created_at": _now(),
    }
    await db[COLLECTION_TECNICOS].insert_one(dict(doc))
    return _ser(doc)


async def atualizar_tecnico(tecnico_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = ("nome", "email", "email_contacto", "telefone", "ordem", "numero",
               "especialidade", "regiao", "preco_indicativo_eur", "prazo_dias", "ativo")
    upd = {k: patch[k] for k in allowed if k in patch}
    if "email" in upd and not upd.get("email_contacto"):
        upd["email_contacto"] = upd["email"]
    upd["updated_at"] = _now()
    res = await db[COLLECTION_TECNICOS].find_one_and_update(
        {"id": tecnico_id}, {"$set": upd}, return_document=True,
    )
    return _ser(res) if res else None


async def eliminar_tecnico(tecnico_id: str) -> bool:
    res = await db[COLLECTION_TECNICOS].delete_one({"id": tecnico_id})
    return bool(getattr(res, "deleted_count", 0))


# --------------------------------------------------------------------- email

async def _enviar_email_subscricao(para: str, link: str, requerente: Optional[str],
                                    descricao: Optional[str]) -> bool:
    """Envia o email ao técnico via Resend. Degrada silenciosamente se não configurado."""
    if not para or "@" not in para:
        return False
    try:
        from engines.emailer import send_email, wrap_html
    except Exception:  # noqa: BLE001
        log.warning("emailer indisponível — e-mail não enviado")
        return False
    assunto = "Pedido de subscrição de processo de autorização de obras — ConstruPilot"
    body_html = (
        f"<p>Olá,</p>"
        f"<p>{requerente or 'Um utilizador'} partilhou consigo um processo de "
        f"autorização de obras preparado na ConstruPilot e solicita a sua subscrição "
        f"técnica (termo de responsabilidade, art.º 10.º do RJUE).</p>"
        f"<p><strong>Resumo da operação:</strong> {descricao or 'ver no processo'}.</p>"
        f"<p>Pode rever o processo e assinar aqui:</p>"
        f'<p style="text-align:center;margin:24px 0"><a href="{link}" '
        f'style="background:#111;color:#fff;padding:12px 20px;border-radius:8px;'
        f'text-decoration:none">Rever e subscrever o processo</a></p>'
        f'<p><a href="{link}">{link}</a></p>'
        f"<p>Este link é válido por {TOKEN_VALIDADE_DIAS} dias. "
        f"Se não reconhecer este pedido, pode ignorar este e-mail.</p>"
    )
    try:
        html = wrap_html("Pedido de subscrição", body_html, cta_url=link,
                         cta_label="Rever e subscrever o processo")
    except Exception:  # noqa: BLE001
        html = f"<html><body>{body_html}</body></html>"
    try:
        res = await send_email(para, assunto, html,
                                text=f"{requerente or 'Um utilizador'} partilhou consigo um processo "
                                     f"de autorização de obras. Abra: {link} (válido {TOKEN_VALIDADE_DIAS} dias).")
        return bool((res or {}).get("ok", True))
    except Exception as e:  # noqa: BLE001
        log.warning("Falha ao enviar email de subscrição: %s", e)
        return False


# --------------------------------------------------------------------- pedidos

async def criar_pedido_subscricao(
    dossier: Dict[str, Any],
    tecnico_id: Optional[str] = None,
    requerente_email: Optional[str] = None,
    requerente_nome: Optional[str] = None,
    tecnico_custom: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Cria o pedido. Aceita um `tecnico_id` do catálogo OU um `tecnico_custom`
    (indicado pelo próprio requerente — nome + email + especialidade + numero opcional).
    """
    tecnico: Optional[Dict[str, Any]] = None
    if tecnico_id:
        tecnico = await tecnico_por_id(tecnico_id)
    if tecnico is None and tecnico_custom:
        nome = (tecnico_custom.get("nome") or "").strip()
        email = (tecnico_custom.get("email") or "").strip()
        if not nome or "@" not in email:
            raise ValueError("tecnico_custom_invalido")
        tecnico = {
            "id": f"custom_{secrets.token_hex(5)}",
            "nome": nome,
            "email": email,
            "email_contacto": email,
            "ordem": tecnico_custom.get("ordem") or "",
            "numero": tecnico_custom.get("numero") or "",
            "especialidade": tecnico_custom.get("especialidade") or "arquitetura",
            "regiao": tecnico_custom.get("regiao") or "",
            "origem": "indicado_pelo_requerente",
        }
    if tecnico is None:
        raise ValueError("tecnico_desconhecido")

    token = secrets.token_urlsafe(32)
    agora = _now()
    doc = {
        "signing_token": token,
        "tecnico": tecnico,
        "dossier": dossier,
        "requerente_email": requerente_email,
        "requerente_nome": requerente_nome,
        "estado": "pendente",
        "created_at": agora,
        "expires_at": agora + timedelta(days=TOKEN_VALIDADE_DIAS),
        "signed_at": None,
    }
    await db[COLLECTION_PEDIDOS].insert_one(dict(doc))
    log.info("Pedido criado: tecnico=%s email=%s token=%s",
             tecnico.get("id"), tecnico.get("email") or tecnico.get("email_contacto"),
             token[:12] + "…")

    # Link público para subscrever (apenas path — o host é determinado no cliente)
    link_relativo = f"/subscrever/{token}"
    descricao = f"{dossier.get('procedimento', '')} — {dossier.get('titulo_regra', '')}".strip(" —")
    enviado = await _enviar_email_subscricao(
        tecnico.get("email") or tecnico.get("email_contacto") or "",
        f"https://construpilot.pt{link_relativo}",
        requerente_nome,
        descricao or None,
    )
    return {
        "signing_token": token,
        "tecnico": tecnico,
        "link_subscrever": link_relativo,
        "email_enviado": enviado,
        "expires_at": doc["expires_at"].isoformat(),
    }


async def ler_pedido_por_token(token: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLLECTION_PEDIDOS].find_one({"signing_token": token})
    if not doc:
        return None
    expires_at = doc.get("expires_at")
    if expires_at and isinstance(expires_at, datetime) and _now() > expires_at:
        return {"error": "expirado", "expires_at": expires_at.isoformat()}
    if doc.get("signed_at") is not None:
        return {"error": "ja_assinado", "signed_at": (doc.get("signed_at").isoformat()
                                                         if isinstance(doc.get("signed_at"), datetime)
                                                         else doc.get("signed_at"))}
    return _ser(doc)


async def registar_termo_responsabilidade(
    token: str,
    nome: str,
    ordem: str,
    numero: str,
    especialidade: str,
    assinatura_b64: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> Dict[str, Any]:
    # Validações defensivas antes do find_one_and_update
    existente = await db[COLLECTION_PEDIDOS].find_one({"signing_token": token})
    if not existente:
        return {"ok": False, "error": "token_invalido"}
    expires_at = existente.get("expires_at")
    if expires_at and isinstance(expires_at, datetime) and _now() > expires_at:
        return {"ok": False, "error": "expirado"}
    if existente.get("signed_at") is not None:
        return {"ok": False, "error": "ja_assinado"}

    termo = {
        "nome": nome, "ordem": ordem, "numero": numero,
        "especialidade": especialidade, "assinatura_b64": assinatura_b64,
        "observacoes": observacoes, "assinado_em": _now(),
    }
    agora = _now()
    res = await db[COLLECTION_PEDIDOS].find_one_and_update(
        {"signing_token": token, "signed_at": None},
        {"$set": {"estado": "subscrito", "termo_responsabilidade": termo,
                  "signed_at": agora, "subscribed_at": agora}},
        return_document=True,
    )
    if not res:
        return {"ok": False, "error": "token_invalido_ou_ja_subscrito"}
    return {"ok": True, "termo": {**termo, "assinado_em": termo["assinado_em"].isoformat()}}
