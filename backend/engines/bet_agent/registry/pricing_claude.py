"""Tabela de preços Claude — fonte canónica: https://docs.claude.com/pricing

Última consulta: **2026-10-18** (web_search_tool_v2, confirmado por
`platform.claude.com/docs/en/about-claude/pricing` e páginas por-modelo).

Valores em USD por milhão de tokens (MTok). Pricing "global standard"
(não a tier mais cara "US-only inference").

TODO:
    - Refrescar manualmente esta tabela se os preços mudarem.
    - Adicionar Haiku 5.5 quando o preço estiver confirmado no docs oficial
      (tabela de preços da pesquisa inicial não listou Haiku 5.5 com certeza).
    - Confirmar valores em `cache_write_5m` vs `cache_write_1h`.

Fontes consultadas (18-10-2026):
    - https://platform.claude.com/docs/en/about-claude/pricing
    - https://platform.claude.com/docs/en/models/opus-5-5/overview
    - https://platform.claude.com/docs/en/models/sonnet-5-5/overview
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Preços oficiais (USD / MTok)
# ---------------------------------------------------------------------------
#
# Nota: cada chave de cache é um upcharge sobre o preço "normal" dos input
# tokens — a Anthropic cobra separadamente `cache_write` (quando o cache é
# criado) e `cache_read` (quando o cache é reutilizado). Os input tokens não
# cacheados mantêm o preço normal `input`.
#
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {
        "input": 4.00,            # Standard global input, non-cached
        "output": 20.00,
        "cache_write_5m": 5.00,   # 5-min TTL cache write
        "cache_write_1h": 8.00,   # 1-hour TTL cache write
        "cache_read": 0.20,       # Cache hit / refresh
    },
    "claude-sonnet-5-5": {
        "input": 2.00,
        "output": 10.00,
        "cache_write_5m": 2.50,
        "cache_write_1h": 4.00,
        "cache_read": 0.10,
    },
    # Haiku 5.5: valores oficiais ainda não confirmados em docs.claude.com na
    # pesquisa de 2026-10-18. Mantidos aqui como PLACEHOLDER CONSERVADOR com
    # ordem de grandeza de Haiku 4.5. Refrescar antes de activar em produção.
    "claude-haiku-5-5": {  # TODO confirmar em docs.claude.com
        "input": 0.80,
        "output": 4.00,
        "cache_write_5m": 1.00,
        "cache_write_1h": 1.60,
        "cache_read": 0.08,
    },
}

# Data da última actualização desta tabela (atualizar manualmente ao refrescar).
LAST_UPDATED: date = date(2026, 10, 18)

# ---------------------------------------------------------------------------
# Estrutura de usage (compatível com `response.usage` do SDK Anthropic)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Usage:
    """Usage report por chamada API. Campos compatíveis com `anthropic.Message.usage`."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0  # tokens cache_write (5min por default)
    cache_read_input_tokens: int = 0


# ---------------------------------------------------------------------------
# Função pura: calcula custo EUR
# ---------------------------------------------------------------------------

def estimate_cost_eur(
    model: str,
    usage: Usage,
    usd_eur_rate: float = 0.93,
    cache_write_ttl: str = "5m",
) -> float:
    """Estima o custo em EUR de uma chamada Anthropic.

    - `cache_write_ttl` ∈ {"5m", "1h"} — determina qual preço de cache_write usar.
    - Modelo desconhecido → usa a tabela Opus 5.5 (conservador) e devolve custo.
    - Para desconhecido avisa via logger externo (não aqui).
    """
    pricing = PRICING_USD_PER_MTOK.get(model) or PRICING_USD_PER_MTOK["claude-opus-5-5"]
    cache_write_key = "cache_write_1h" if cache_write_ttl == "1h" else "cache_write_5m"

    usd = (
        usage.input_tokens * pricing["input"]
        + usage.output_tokens * pricing["output"]
        + usage.cache_creation_input_tokens * pricing[cache_write_key]
        + usage.cache_read_input_tokens * pricing["cache_read"]
    ) / 1_000_000.0
    return usd * usd_eur_rate


def is_known_model(model: str) -> bool:
    return model in PRICING_USD_PER_MTOK


def available_models() -> list[str]:
    return list(PRICING_USD_PER_MTOK.keys())
