"""Mecanismo mínimo de subscrição de processos por técnico parceiro (Lote N3).

Fluxo:
  1. Utilizador final clica «Pedir subscrição» → `criar_pedido_subscricao(dossier_id, tecnico_id)`.
  2. É enviado email ao técnico (stub) com link público `/subscrever/{signing_token}`.
  3. Técnico abre, revê o dossier, preenche nome, ordem profissional, número, assinatura.
  4. Backend regista o Termo de Responsabilidade (art.º 10.º do RJUE).

Nada é persistido fora da coleção `autorizacao_subscricoes` (não altera lotes anteriores).
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.db import db

COLLECTION = "autorizacao_subscricoes"
CATALOGO_PATH = Path(__file__).resolve().parents[2] / "data" / "tecnicos_parceiros.json"


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


# --------------------------------------------------------------------- catálogo

def carregar_tecnicos() -> List[Dict[str, Any]]:
    try:
        return json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def tecnico_por_id(tecnico_id: str) -> Optional[Dict[str, Any]]:
    for t in carregar_tecnicos():
        if t.get("id") == tecnico_id:
            return t
    return None


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


# --------------------------------------------------------------------- pedidos

async def criar_pedido_subscricao(
    dossier: Dict[str, Any],
    tecnico_id: str,
    requerente_email: Optional[str] = None,
) -> Dict[str, Any]:
    tecnico = tecnico_por_id(tecnico_id)
    if not tecnico:
        raise ValueError("tecnico_desconhecido")
    token = secrets.token_urlsafe(32)
    doc = {
        "signing_token": token,
        "tecnico": tecnico,
        "dossier": dossier,
        "requerente_email": requerente_email,
        "estado": "pendente",
        "created_at": _now(),
    }
    await db[COLLECTION].insert_one(doc)
    # «Envio» de email ao técnico — stub registado no log, para evitar dependência de SMTP real
    try:
        import logging
        logging.getLogger("autorizacao.subscricao").info(
            "Pedido de subscrição criado: tecnico=%s email=%s token=%s",
            tecnico.get("id"), tecnico.get("email_contacto"), token[:12] + "…",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"signing_token": token, "tecnico": tecnico}


async def ler_pedido_por_token(token: str) -> Optional[Dict[str, Any]]:
    doc = await db[COLLECTION].find_one({"signing_token": token})
    return _ser(doc) if doc else None


async def registar_termo_responsabilidade(
    token: str,
    nome: str,
    ordem: str,
    numero: str,
    especialidade: str,
    assinatura_b64: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> Dict[str, Any]:
    termo = {
        "nome": nome, "ordem": ordem, "numero": numero,
        "especialidade": especialidade, "assinatura_b64": assinatura_b64,
        "observacoes": observacoes, "assinado_em": _now(),
    }
    res = await db[COLLECTION].find_one_and_update(
        {"signing_token": token, "estado": {"$ne": "subscrito"}},
        {"$set": {"estado": "subscrito", "termo_responsabilidade": termo,
                  "subscribed_at": _now()}},
        return_document=True,
    )
    if not res:
        return {"ok": False, "error": "token_invalido_ou_ja_subscrito"}
    return {"ok": True, "termo": {**termo, "assinado_em": termo["assinado_em"].isoformat()}}
