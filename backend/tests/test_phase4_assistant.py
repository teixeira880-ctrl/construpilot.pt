"""Phase 4 P3 — Assistant IA (Claude Sonnet 4.5) via emergentintegrations.

Tests marqués `slow` : ils appellent la vraie API Anthropic via EMERGENT_LLM_KEY
et peuvent prendre 3-15 s par test. Assertions volontairement souples.
"""
import os
import uuid

import pytest

from stair_engine.assistant import chat_with_assistant


pytestmark = pytest.mark.slow


def _need_key():
    if not os.environ.get("EMERGENT_LLM_KEY"):
        pytest.skip("EMERGENT_LLM_KEY manquant — skipping assistant tests")


@pytest.mark.asyncio
async def test_full_request_triggers_engine():
    _need_key()
    conv = str(uuid.uuid4())
    r = await chat_with_assistant(
        conv,
        "Hauteur 2.80m, reculement 4.5m, largeur dispo 1.2m, largeur souhaitée 900mm. "
        "Trouve-moi le meilleur escalier.",
        history=[],
    )
    assert r.conversation_id == conv
    assert isinstance(r.reply_text, str) and len(r.reply_text) > 20
    # Le LLM doit avoir appelé au moins un outil
    called = [c["tool"] for c in r.referenced_engine_calls]
    assert any(t in ("optimize_stair", "calculate_straight") for t in called), \
        f"Aucun outil moteur appelé — appels: {called}"
    # Au moins 1 solution capturée si optimize a été appelé
    if "optimize_stair" in called:
        assert len(r.computed_solutions) >= 1


@pytest.mark.asyncio
async def test_incomplete_request_asks_clarification():
    _need_key()
    conv = str(uuid.uuid4())
    r = await chat_with_assistant(
        conv,
        "Je veux un escalier.",
        history=[],
    )
    # Pas de tool call attendu — il doit demander plus d'infos
    assert isinstance(r.reply_text, str) and len(r.reply_text) > 10
    # Vérifie qu'il n'a pas calculé
    assert not r.computed_solutions
    # Idéalement il pose une question — heuristique large : présence d'un ? ou d'un mot-clé
    text = r.reply_text.lower()
    has_question = "?" in r.reply_text or any(
        kw in text for kw in ("hauteur", "reculement", "trémie", "précis", "dimension", "espace")
    )
    assert has_question, f"L'assistant n'a pas demandé de clarification: {r.reply_text}"


@pytest.mark.asyncio
async def test_theoretical_question_no_engine_call():
    _need_key()
    conv = str(uuid.uuid4())
    r = await chat_with_assistant(
        conv,
        "C'est quoi la formule de Blondel exactement ?",
        history=[],
    )
    assert isinstance(r.reply_text, str) and len(r.reply_text) > 20
    # Aucun appel moteur nécessaire pour une info théorique
    assert r.referenced_engine_calls == []
    # La réponse doit mentionner 2h+g ou blondel
    text = r.reply_text.lower()
    assert ("blondel" in text) or ("2h" in text) or ("2 h" in text)


@pytest.mark.asyncio
async def test_history_preserved_over_turns():
    _need_key()
    conv = str(uuid.uuid4())
    h: list[dict] = []
    r1 = await chat_with_assistant(conv, "Je m'appelle Julien.", history=h)
    h += [
        {"role": "user", "content": "Je m'appelle Julien."},
        {"role": "assistant", "content": r1.reply_text},
    ]
    r2 = await chat_with_assistant(conv, "Ma hauteur est 2.80m.", history=h)
    h += [
        {"role": "user", "content": "Ma hauteur est 2.80m."},
        {"role": "assistant", "content": r2.reply_text},
    ]
    r3 = await chat_with_assistant(
        conv,
        "Comment je m'appelle et quelle hauteur j'ai dit ?",
        history=h,
    )
    text = r3.reply_text.lower()
    assert "julien" in text, f"Prénom oublié: {r3.reply_text}"
    assert "2.80" in text or "2,80" in text or "2800" in text or "280" in text, \
        f"Hauteur oubliée: {r3.reply_text}"
