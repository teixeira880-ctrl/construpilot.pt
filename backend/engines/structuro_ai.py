"""StructuroPilot — IA de LECTURE/RÉDACTION uniquement (Claude via clé Emergent).

L'IA extrait des FAITS DÉCLARÉS d'une description libre et aide à formuler le
questionnaire. Elle n'a JAMAIS le droit de produire une résistance, une section,
une charge ou une conclusion structurelle. Toute sortie IA est tracée source="declaration"
(fait rapporté par l'utilisateur) et reste à confirmer. Repli déterministe si LLM indisponible.
"""
from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv

load_dotenv()

_MODEL = ("anthropic", "claude-sonnet-4-6")

_SYSTEM = (
    "És um assistente de LEITURA para um software de estruturas (construção). Lês uma descrição de edifício e extrais APENAS os factos DECLARADOS pelo autor. Proibições absolutas: nunca inventes resistência de material, secção, carga, capacidade resistente do solo, dimensão não escrita, nem conclusão de cálculo. Se uma informação não estiver escrita, não a deduzas (a época não dá nenhuma resistência). Responde ESTRITAMENTE em JSON válido, sem texto à volta."
)

_EXTRACT_PROMPT = (
    "Description:\n\'\'\'{desc}\'\'\'\n\nDevolve este JSON (textos em português europeu):\n{{\"facts\":[{{\"text\":\"<facto declarado curto>\"}}],\"declared\":{{\"epoque\":\"<ex.: cerca de 1850 ou null>\",\"niveaux\":\"<ex.: 2 pisos sobre cave ou null>\",\"murs\":\"<ex.: pedra ~50 cm ou null>\",\"planchers\":\"<ex.: madeira ou null>\",\"ouverture\":\"<ex.: ~2,40 m sala/cozinha ou null>\"}}}}\nCada facto deve estar literalmente presente ou claramente implícito no texto. Não acrescentes nenhum dado não escrito."
)


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _fallback_extract(description: str) -> dict:
    """Repli purement textuel : on ne garde que des bribes littérales, source=declaration."""
    d = description or ""
    facts = []
    patterns = [
        (r"(vers|en|autour de|circa)?\s*(1[6-9]\d{2}|20\d{2})", "Época declarada: {m}"),
        (r"(\d+)\s*niveau", "{m} niveau(x) déclaré(s)"),
        (r"(pierre|brique|pis[ée]|moellon|torchis|pan de bois)", "Paredes declaradas: {m}"),
        (r"(plancher[s]?\s+(?:bois|béton|béton|métal|acier))", "{m}"),
        (r"(ouverture|baie|tr[ée]mie)", "Abertura/vão mencionado"),
    ]
    for pat, tpl in patterns:
        mm = re.search(pat, d, re.IGNORECASE)
        if mm:
            facts.append({"text": tpl.format(m=mm.group(0).strip())})
    if not facts:
        facts = [{"text": "Descrição recebida — nenhum facto estruturado detetado automaticamente."}]
    return {"facts": facts, "declared": {}}


async def extract_facts(description: str) -> dict:
    """Extrait les faits déclarés via Claude (lecture seule). Repli déterministe si échec."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key or not (description or "").strip():
        return {**_fallback_extract(description), "source_engine": "fallback"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(api_key=key, session_id="structuro-extract",
                       system_message=_SYSTEM).with_model(*_MODEL)
        resp = await chat.send_message(UserMessage(text=_EXTRACT_PROMPT.format(desc=description[:6000])))
        parsed = _extract_json(resp if isinstance(resp, str) else str(resp))
        if not parsed or "facts" not in parsed:
            return {**_fallback_extract(description), "source_engine": "fallback"}
        facts = [{"text": str(f.get("text", "")).strip()[:300]}
                 for f in (parsed.get("facts") or []) if f.get("text")]
        return {"facts": facts[:20], "declared": parsed.get("declared") or {},
                "source_engine": "claude"}
    except Exception:
        return {**_fallback_extract(description), "source_engine": "fallback"}
