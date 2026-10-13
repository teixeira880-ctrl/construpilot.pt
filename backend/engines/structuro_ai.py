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
    "Tu es un assistant de LECTURE pour un logiciel de structure (BTP). Tu lis une description "
    "de bâtiment en français et tu en extrais UNIQUEMENT les faits DÉCLARÉS par l'auteur. "
    "Interdits absolus : n'invente jamais de résistance de matériau, de section, de charge, de "
    "portance de sol, de dimension non écrite, ni de conclusion de calcul. Si une information "
    "n'est pas écrite, ne la déduis pas (l'époque ne donne aucune résistance). "
    "Réponds STRICTEMENT en JSON valide, sans texte autour."
)

_EXTRACT_PROMPT = (
    "Description:\n'''{desc}'''\n\n"
    "Renvoie ce JSON :\n"
    '{{"facts":[{{"text":"<fait déclaré court>"}}],'
    '"declared":{{'
    '"epoque":"<ex: vers 1850 ou null>",'
    '"niveaux":"<ex: 2 niveaux sur cave ou null>",'
    '"murs":"<ex: pierre ~50 cm ou null>",'
    '"planchers":"<ex: bois ou null>",'
    '"ouverture":"<ex: ~2,40 m séjour/cuisine ou null>"}}}}\n'
    "Chaque fait doit être littéralement présent ou clairement impliqué par le texte. "
    "N'ajoute aucune donnée non écrite."
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
        (r"(vers|en|autour de|circa)?\s*(1[6-9]\d{2}|20\d{2})", "Époque déclarée : {m}"),
        (r"(\d+)\s*niveau", "{m} niveau(x) déclaré(s)"),
        (r"(pierre|brique|pis[ée]|moellon|torchis|pan de bois)", "Murs déclarés : {m}"),
        (r"(plancher[s]?\s+(?:bois|béton|béton|métal|acier))", "{m}"),
        (r"(ouverture|baie|tr[ée]mie)", "Ouverture/baie mentionnée"),
    ]
    for pat, tpl in patterns:
        mm = re.search(pat, d, re.IGNORECASE)
        if mm:
            facts.append({"text": tpl.format(m=mm.group(0).strip())})
    if not facts:
        facts = [{"text": "Description reçue — aucun fait structuré détecté automatiquement."}]
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
