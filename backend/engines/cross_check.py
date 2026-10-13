"""Croisement multi-IA (« croisement de données ») pour l'assistant Aurora.

Interroge en parallèle plusieurs modèles INDÉPENDANTS (ChatGPT / Gemini Pro / Claude)
sur la même question factuelle BTP, et renvoie leurs avis bruts + d'éventuelles
sources web officielles (Perplexity). L'assistant (Claude orchestrateur) réconcilie
ensuite : consensus, divergences explicites, et ce qui reste à vérifier.
Objectif zéro-hallucination : aucune valeur n'est inventée, les désaccords sont montrés.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

# Modèles croisés : (provider, model, libellé affiché). Un même fournisseur n'apparaît
# qu'une fois pour garder trois avis réellement indépendants.
_MODELS = [
    ("openai", os.environ.get("CROSS_CHECK_OPENAI_MODEL", "gpt-5.6-terra"), "ChatGPT (GPT-5.6)"),
    ("gemini", os.environ.get("CROSS_CHECK_GEMINI_MODEL", "gemini-3.1-pro-preview"), "Gemini Pro"),
    ("anthropic", os.environ.get("CROSS_CHECK_CLAUDE_MODEL", "claude-sonnet-4-6"), "Claude Sonnet"),
]

_SYSTEM = (
    "Tu es un expert technique et réglementaire du BTP en France (DTU, normes AFNOR, "
    "Eurocodes, RE2020). Réponds de façon FACTUELLE et CONCISE (150 mots max). "
    "ZÉRO HALLUCINATION : si une donnée clé manque pour conclure, dis-le explicitement "
    "au lieu de l'inventer. Termine par une ligne « Certitude : élevée / moyenne / faible »."
)

_TIMEOUT = float(os.environ.get("CROSS_CHECK_TIMEOUT", "60"))


async def _one(provider: str, model: str, label: str, system: str, prompt: str) -> dict:
    from engines.ai import _call_provider
    try:
        out = await asyncio.wait_for(
            _call_provider(provider, model, system, prompt, None, None, "cross_check"), _TIMEOUT)
        answer = (out or "").strip()
        if not answer:
            return {"model": label, "ok": False, "answer": None, "error": "réponse vide"}
        return {"model": label, "ok": True, "answer": answer}
    except Exception as exc:  # noqa: BLE001
        logger.warning("cross_check %s a échoué : %s", label, type(exc).__name__)
        return {"model": label, "ok": False, "answer": None, "error": "indisponible"}


async def cross_check(question: str, context: str = "", include_web: bool = False) -> dict:
    """Interroge plusieurs IA indépendantes + (option) le web, et renvoie leurs avis bruts.

    Retour : { ok, question, opinions:[{model,ok,answer}], web?:{answer,sources}, instruction }.
    """
    question = (question or "").strip()
    if not question:
        return {"ok": False, "error": "Question vide : préciser ce qui doit être croisé."}
    prompt = question + (f"\n\nContexte fourni :\n{context.strip()}" if (context or "").strip() else "")

    tasks = [_one(p, m, lbl, _SYSTEM, prompt) for p, m, lbl in _MODELS]
    opinions = list(await asyncio.gather(*tasks))

    web = None
    if include_web:
        try:
            from engines.btp_assistant_router import web_search, web_search_enabled
            if web_search_enabled():
                ws = await web_search(question)
                if ws.get("answer"):
                    web = {"answer": ws["answer"], "sources": ws.get("sources", [])}
        except Exception:  # noqa: BLE001
            web = None

    ok_count = sum(1 for o in opinions if o["ok"])
    return {
        "ok": ok_count >= 2,
        "question": question,
        "models_queried": [o["model"] for o in opinions],
        "opinions": opinions,
        "web": web,
        "instruction": (
            "Compare ces avis INDÉPENDANTS. Présente d'abord un CONSENSUS clair (ce sur quoi "
            "les IA s'accordent), puis liste explicitement les DIVERGENCES (chiffres, règles, "
            "conditions) et enfin ce qui reste À VÉRIFIER. N'ajoute aucune donnée au-delà de "
            "ces avis ; si elles se contredisent, signale-le sans trancher arbitrairement."
            + (" Cite les sources web officielles fournies." if web else "")
        ),
    }
