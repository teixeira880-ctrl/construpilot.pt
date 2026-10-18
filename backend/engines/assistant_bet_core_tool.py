"""Adaptador do bet_core assistant_tool para o Assistente BTP `.pt`.

Expõe:
    - BET_CORE_TOOLS, BET_CORE_TOOL_NAMES, BET_CORE_INSTRUCTIONS: schemas e
      instruções do `engines/bet_core/assistant_tool.py` sem modificação.
    - run_bet_core_tool(name, args, user, conv, allowed_doc_fn):
      wrapper que injecta:
        * `doc_loader` → lê `db.assistant_docs` reutilizando a função
          `_allowed_doc` do `routes/assistant.py` (suporta documentos chunked
          e verifica ownership `user_id == user.id`).
        * `branding_loader` → prioriza `routes.company_page.pdf_customization`
          se existir, senão campos `brand_*` do utilizador em `db.users`.

Zero toque em `engines/bet_core/` (código do fetch mantido imutável).
"""
from __future__ import annotations

import base64
import logging
from typing import Awaitable, Callable, Optional

from core.db import db
from engines.bet_core.assistant_tool import (
    INSTRUCTIONS as BET_CORE_INSTRUCTIONS,
    TOOL_NAMES as BET_CORE_TOOL_NAMES,
    TOOLS as BET_CORE_TOOLS,
    execute as _bet_core_execute,
)

log = logging.getLogger("assistant.bet_core")


# ---------------------------------------------------------------------------
# Branding loader `.pt`
# ---------------------------------------------------------------------------

async def _pt_branding_loader(_db, user_id: str) -> Optional[dict]:
    """Branding da empresa `.pt`.

    Preferência:
    1. `routes.company_page.pdf_customization(user_id)` — identidade canónica
       Pro / Pro Business usada pelo resto do produto.
    2. Fallback: campos `brand_*` do documento `db.users`.

    Devolve None se nenhuma identidade existir → o dossier sai com as cores
    ConstruPilot (comportamento default do bet_core).
    """
    b: dict = {}
    # 1. customização canónica
    try:
        from routes.company_page import pdf_customization
        pdfc = await pdf_customization(user_id)
        if pdfc:
            b.update({k: v for k, v in pdfc.items() if v})
    except Exception:  # noqa: BLE001
        log.debug("pdf_customization não disponível, fallback brand_* no users doc")

    # 2. fallback: campos brand_* no doc utilizador
    try:
        u = await _db.users.find_one(
            {"user_id": user_id},
            {
                "_id": 0,
                "brand_company_name": 1,
                "brand_contact_line": 1,
                "brand_logo_b64": 1,
                "brand_company_email": 1,
                "brand_siret": 1,
                "brand_vat": 1,
                "brand_nif": 1,
                "brand_alvara": 1,
                "brand_address": 1,
                "brand_city": 1,
                "brand_postal": 1,
                "brand_accent_color": 1,
                "brand_footer_text": 1,
            },
        ) or {}
        brand_fields = {k[6:]: v for k, v in u.items() if k.startswith("brand_") and v}
        if "postal" in brand_fields:
            brand_fields["postal_code"] = brand_fields.pop("postal")
        for k, v in brand_fields.items():
            b.setdefault(k, v)
    except Exception:  # noqa: BLE001
        log.debug("sem campos brand_* no users doc, dossier sai sem logo")

    return b or None


# ---------------------------------------------------------------------------
# Doc loader `.pt`
# ---------------------------------------------------------------------------

AllowedDocFn = Callable[[str, str, bool], Awaitable[dict]]


def _make_pt_doc_loader(allowed_doc_fn: AllowedDocFn) -> Callable[..., Awaitable[list]]:
    """Factory do `doc_loader` esperado por `bet_core.assistant_tool.execute`.

    Reutiliza a verificação de ownership + suporte a chunking do
    `_allowed_doc` do `routes/assistant.py` (mesma lógica que todas as outras
    tools do Assistente, para consistência).
    """

    async def loader(_db, ids: list[str], user_id: str) -> list:
        out: list = []
        for did in ids:
            d = await allowed_doc_fn(did, user_id, True)
            mime = (d.get("mime") or "").lower()
            if mime != "application/pdf":
                raise ValueError(
                    f"{d.get('filename') or did} não é PDF — apenas PDFs de plantas são lidos pelo estudo BET."
                )
            data = d.get("data_b64")
            if not data:
                raise ValueError(f"Documento {did} sem dados utilizáveis.")
            out.append((d.get("filename") or did, base64.b64decode(data)))
        return out

    return loader


# ---------------------------------------------------------------------------
# Entrypoint do Assistente
# ---------------------------------------------------------------------------

async def run_bet_core_tool(
    name: str,
    args: dict,
    user: dict,
    conv: dict,
    allowed_doc_fn: AllowedDocFn,
) -> dict:
    """Entrypoint chamado por `routes/assistant.py::_exec_tool`.

    Reservado a contas profissionais — o filtro vive em `tools_for(user)`
    (não entra na lista para `individual`). Mantemos adicionalmente um
    guard defensivo aqui para evitar bypass caso o schema seja chamado
    directamente.
    """
    if user.get("account_type") == "particulier":
        return {
            "error": "Estudo BET completo reservado a contas profissionais.",
            "status": "falhou",
        }
    doc_loader = _make_pt_doc_loader(allowed_doc_fn)
    return await _bet_core_execute(
        name,
        args,
        user,
        conv,
        db,
        doc_loader=doc_loader,
        branding_loader=_pt_branding_loader,
    )


__all__ = [
    "BET_CORE_TOOLS",
    "BET_CORE_TOOL_NAMES",
    "BET_CORE_INSTRUCTIONS",
    "run_bet_core_tool",
]
