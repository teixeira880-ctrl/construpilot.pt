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
        * `_translate_pt_output` → aplica `bet_core.i18n.tr(..., lang="pt")`
          sobre questions, anomalies, points e step quando `country=="PT"`;
          zero toque em `engines/bet_core/`.

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
from engines.bet_core.i18n import tr as _tr_bet

log = logging.getLogger("assistant.bet_core")


# ---------------------------------------------------------------------------
# Tradução PT dos campos devolvidos ao Assistente (zero toque em bet_core/)
# ---------------------------------------------------------------------------

# Mapeamento manual para labels que não aparecem no glossário determinístico
# do bet_core (status + rótulos de pipeline). Last-write-wins intencional.
_PT_STATUS_LABELS = {
    "Questions à l'utilisateur": "Questões ao utilizador",
    "En file d'attente": "Em fila de espera",
    "Lecture des plans par IA et relevé du modèle bâtiment":
        "Leitura dos desenhos por IA e levantamento do modelo do edifício",
    "Calculs, plans, devis et contrôle":
        "Cálculos, desenhos, orçamento e verificação",
    "Terminé": "Concluído",
    "Échec": "Falhou",
    "à préciser": "a precisar",
}


def _tr_pt(s):
    """Traduz `s` FR→PT via glossário determinístico do bet_core + overrides."""
    if not isinstance(s, str) or not s:
        return s
    # 1. overrides específicos do boundary (status / step)
    out = _PT_STATUS_LABELS.get(s, s)
    if out != s:
        return out
    # 2. tradução determinística bet_core (templates + glossário)
    try:
        return _tr_bet(s, lang="pt")
    except Exception:  # noqa: BLE001 — tradução é best-effort
        return s


def _translate_pt_output(result: dict) -> dict:
    """Aplica tradução PT aos campos humanos devolvidos a um Assistente .pt.

    Só actua se `result.get("country") == "PT"`. Preserva estrutura, chaves,
    códigos de anomalia e tipos técnicos (números, ids, mimes).
    """
    if not isinstance(result, dict) or result.get("country") != "PT":
        return result
    out = dict(result)
    # Textos de estado / passo
    if "step" in out:
        out["step"] = _tr_pt(out["step"])
    # Perguntas (list[str])
    qs = out.get("questions")
    if isinstance(qs, list):
        out["questions"] = [_tr_pt(q) for q in qs]
    # Pontos de atenção (list[str])
    pts = out.get("points")
    if isinstance(pts, list):
        out["points"] = [_tr_pt(p) for p in pts]
    # Anomalias (list[dict]): traduz message + fix, mantém code/level
    an = out.get("anomalies")
    if isinstance(an, list):
        new_an = []
        for a in an:
            if isinstance(a, dict):
                b = dict(a)
                if "message" in b:
                    b["message"] = _tr_pt(b["message"])
                if "fix" in b and b["fix"]:
                    b["fix"] = _tr_pt(b["fix"])
                new_an.append(b)
            else:
                new_an.append(a)
        out["anomalies"] = new_an
    return out


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
    result = await _bet_core_execute(
        name,
        args,
        user,
        conv,
        db,
        doc_loader=doc_loader,
        branding_loader=_pt_branding_loader,
    )
    # Tradução PT dos campos humanos (questions/anomalies/step/points) quando
    # o estudo é PT. `generate_full_bet_study` devolve só {job_id, status:
    # "running"} e não precisa; `read_full_bet_study` devolve o job completo
    # com country lá dentro — é aí que a tradução faz diferença.
    return _translate_pt_output(result) if isinstance(result, dict) else result


__all__ = [
    "BET_CORE_TOOLS",
    "BET_CORE_TOOL_NAMES",
    "BET_CORE_INSTRUCTIONS",
    "run_bet_core_tool",
    "_translate_pt_output",
    "_tr_pt",
]
