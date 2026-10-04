"""Smoke test individual: Claude · OpenAI · Perplexity.

Corre: cd /app/backend && python -m scripts.test_ai_providers_e2e

NUNCA imprime API keys. Mostra apenas: provider · model · latency · primeiros 150 chars.
"""
from __future__ import annotations

import asyncio
import sys
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from engines.ai_providers.router import ai_router  # noqa: E402
from engines.ai_providers.base import AIProviderError  # noqa: E402


async def test_claude() -> int:
    p = ai_router.claude
    if not p:
        print("[claude] NOT CONFIGURED — skipping")
        return 1
    try:
        r = await p.ask(
            prompt="Qual é o pé-direito mínimo em habitação segundo o RGEU? Resposta curta em PT-PT.",
            system="És assistente técnico BTP. Responde em PT-PT, 2-3 linhas.",
            max_tokens=200, temperature=0.2,
        )
        print(f"[claude] OK | model={r.model} | latency={r.latency_ms}ms | "
              f"text_len={len(r.text)} | tokens_in={r.usage.input_tokens} out={r.usage.output_tokens}")
        print(f"         preview: {r.text[:150].replace(chr(10),' ')}")
        return 0 if not r.is_empty else 2
    except AIProviderError as e:
        print(f"[claude] FAIL · code={e.code} status={e.status_code} retriable={e.retriable}")
        return 3


async def test_openai() -> int:
    p = ai_router.openai_coach
    if not p:
        print("[openai] NOT CONFIGURED — skipping")
        return 1
    try:
        r = await p.ask(
            prompt="Qual é o pé-direito mínimo em habitação segundo o RGEU? Resposta curta em PT-PT.",
            system="És assistente técnico BTP. Responde em PT-PT, 2-3 linhas.",
            max_tokens=200, temperature=0.2,
        )
        print(f"[openai] OK | model={r.model} | latency={r.latency_ms}ms | "
              f"text_len={len(r.text)} | tokens_in={r.usage.input_tokens} out={r.usage.output_tokens}")
        print(f"         preview: {r.text[:150].replace(chr(10),' ')}")
        return 0 if not r.is_empty else 2
    except AIProviderError as e:
        print(f"[openai] FAIL · code={e.code} status={e.status_code} retriable={e.retriable}")
        return 3


async def test_perplexity() -> int:
    p = ai_router.perplexity
    if not p:
        print("[perplexity] NOT CONFIGURED — skipping")
        return 1
    try:
        r = await p.ask(
            prompt="Qual o preço médio atual (2026) do cimento Portland CEM II em Portugal? "
                   "Indica fontes.",
            system=None, max_tokens=400, temperature=0.1,
        )
        print(f"[perplexity] OK | model={r.model} | latency={r.latency_ms}ms | "
              f"text_len={len(r.text)} | citations={len(r.citations)} | "
              f"tokens_in={r.usage.input_tokens} out={r.usage.output_tokens}")
        print(f"             preview: {r.text[:150].replace(chr(10),' ')}")
        if r.citations:
            print(f"             fonts (max 3):")
            for c in r.citations[:3]:
                print(f"               · {c.url}")
        return 0 if (not r.is_empty) else 2
    except AIProviderError as e:
        print(f"[perplexity] FAIL · code={e.code} status={e.status_code} retriable={e.retriable}")
        return 3


async def main() -> int:
    rc1 = await test_claude()
    rc2 = await test_openai()
    rc3 = await test_perplexity()
    print()
    print("=" * 60)
    print(f"RESUMO: claude rc={rc1} · openai rc={rc2} · perplexity rc={rc3}")
    print("=" * 60)
    return max(rc1, rc2, rc3)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
