"""Testes fallback e enrichment do router AI.

Testes:
  1. Claude com key inválida → fallback OpenAI (via patch do env no router).
  2. Ambos falham → CoachUnavailableError + insert em coach_failures.
  3. Pergunta com palavra-chave de atualidade → Perplexity injectado.
  4. Pergunta sem palavra-chave → Perplexity NÃO chamado.

Corre: cd /app/backend && python -m scripts.test_coach_fallback
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from engines.ai_providers.base import AIProviderError  # noqa: E402
from engines.ai_providers.router import ai_router, needs_web_search  # noqa: E402
from engines.coach_ai import coach_ask, CoachUnavailableError  # noqa: E402


async def t1_claude_ok() -> int:
    print("\n[1] Claude disponível → deve usar Claude")
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ai_router.reset()
    res = await coach_ask(
        project_id=None, user_message="Pé-direito mínimo RGEU?",
        conversation_history=[], user_id="user_test_fallback", db=db,
    )
    assert res["provider"] == "claude", f"Esperava claude, obtive {res['provider']}"
    print(f"    ✓ provider={res['provider']} model={res['model']} len={len(res['text'])}")
    return 0


async def t2_claude_fails_fallback_openai() -> int:
    print("\n[2] Claude com erro → fallback OpenAI")
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ai_router.reset()
    _ = ai_router.claude  # força carregamento
    # Patch do método ask do Claude para levantar erro retriable
    fail = AsyncMock(side_effect=AIProviderError(
        "Simulated Claude down", provider="claude", code="simulated",
        status_code=503, retriable=True,
    ))
    with patch.object(ai_router._claude, "ask", fail):
        res = await coach_ask(
            project_id=None, user_message="Pé-direito mínimo RGEU?",
            conversation_history=[], user_id="user_test_fallback", db=db,
        )
    assert res["provider"] == "openai", f"Esperava openai, obtive {res['provider']}"
    print(f"    ✓ provider={res['provider']} model={res['model']} len={len(res['text'])}")
    return 0


async def t3_both_fail_raises() -> int:
    print("\n[3] Ambos falham → CoachUnavailableError + insert coach_failures")
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    await db.coach_failures.delete_many({"user_id": "user_test_both_fail"})
    ai_router.reset()
    _ = ai_router.claude
    _ = ai_router.openai_coach
    fail_claude = AsyncMock(side_effect=AIProviderError(
        "sim claude", provider="claude", code="simulated", retriable=True))
    fail_openai = AsyncMock(side_effect=AIProviderError(
        "sim openai", provider="openai", code="simulated", retriable=True))
    fake_email = AsyncMock(return_value={"ok": True})
    with patch.object(ai_router._claude, "ask", fail_claude), \
         patch.object(ai_router._openai_coach, "ask", fail_openai), \
         patch("engines.coach_ai.send_email", fake_email, create=True), \
         patch("engines.emailer.send_email", fake_email):
        try:
            await coach_ask(
                project_id=None, user_message="Qualquer",
                conversation_history=[], user_id="user_test_both_fail", db=db,
            )
            print("    ✗ Devia ter levantado CoachUnavailableError")
            return 1
        except CoachUnavailableError as e:
            assert e.primary_meta.get("provider") == "claude"
            assert e.fallback_meta.get("provider") == "openai"
            print(f"    ✓ excepção levantada · primary={e.primary_meta.get('code')}"
                  f" fallback={e.fallback_meta.get('code')}")
    doc = await db.coach_failures.find_one({"user_id": "user_test_both_fail"})
    assert doc, "falha não gravada em coach_failures"
    print(f"    ✓ coach_failures doc={doc['failure_id']}")
    print(f"    ✓ email admin called={fake_email.call_count}x")
    await db.coach_failures.delete_many({"user_id": "user_test_both_fail"})
    return 0


async def t4_web_search_trigger() -> int:
    print("\n[4] Palavra-chave 'preço' → Perplexity activado")
    assert needs_web_search("Qual o preço atual do cimento?") is True
    assert needs_web_search("Qual o preço médio?") is True
    assert needs_web_search("Explica o pé-direito mínimo") is False
    assert needs_web_search("O que é o RGEU?") is False
    print("    ✓ needs_web_search detecta correctamente")

    # Chamada real: pergunta com 'preço atual' → deve enriquecer
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    ai_router.reset()
    res = await coach_ask(
        project_id=None,
        user_message="Qual o preço atual do cimento Portland CEM II em Portugal (2026)?",
        conversation_history=[], user_id="user_test_web", db=db,
    )
    print(f"    ✓ web_enriched={res['web_enriched']} citations={len(res['citations'])}")
    print(f"    ✓ reply preview: {res['text'][:150].replace(chr(10),' ')}")
    assert res["web_enriched"], "Pergunta com 'preço atual' devia ter enrich=True"
    return 0


async def main() -> int:
    results = []
    for fn in (t1_claude_ok, t2_claude_fails_fallback_openai,
               t3_both_fail_raises, t4_web_search_trigger):
        try:
            rc = await fn()
            results.append((fn.__name__, rc))
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ FAIL: {type(e).__name__}: {e}")
            results.append((fn.__name__, 9))
    print("\n" + "=" * 60)
    for name, rc in results:
        print(f"  {name}: {'OK' if rc == 0 else 'FAIL'}")
    print("=" * 60)
    return max(r for _, r in results)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
