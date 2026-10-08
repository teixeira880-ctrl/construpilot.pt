"""Preços oficiais Gemini + conversão USD→EUR (Fase B).

Fonte: Google AI pricing — Fev 2026.
Conversão: taxa fixa via env `EUR_USD_RATE` (default 0.92), sem
dependências externas (decisão 1a confirmada pelo utilizador).
"""
from __future__ import annotations

import os
from typing import Any

# Preços USD por 1 milhão de tokens.
# Nota: `thinking` (thoughts_token_count) é facturado como OUTPUT no Gemini
# Pro — por isso o valor "out" é usado também para thoughts.
PRECOS_USD_POR_1M: dict[str, dict[str, float]] = {
    "gemini-pro-latest":        {"in": 1.25,  "out": 10.00},
    "gemini-3.1-pro-preview":   {"in": 1.25,  "out": 10.00},
    "gemini-2.5-pro":           {"in": 1.25,  "out": 10.00},
    "gemini-flash-latest":      {"in": 0.075, "out": 0.30},
    "gemini-2.5-flash":         {"in": 0.075, "out": 0.30},
    "gemini-1.5-flash":         {"in": 0.075, "out": 0.30},
}
# Factor para tokens em cache (desconto padrão ~75% nos modelos Gemini).
PRECOS_CACHE_FACTOR = 0.25


def taxa_eur_usd() -> float:
    """Lê `EUR_USD_RATE` do ambiente; default 0.92."""
    try:
        return float(os.environ.get("EUR_USD_RATE", "0.92"))
    except (TypeError, ValueError):
        return 0.92


def _tabela_para(modelo: str) -> dict[str, float]:
    """Devolve a tabela de preços para o modelo; fallback para Pro."""
    return PRECOS_USD_POR_1M.get(modelo) or PRECOS_USD_POR_1M["gemini-pro-latest"]


def custo_eur(
    modelo: str,
    *,
    tokens_input: int = 0,
    tokens_output: int = 0,
    thinking_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Custo total EUR arredondado a 6 casas decimais.

    * `tokens_output` + `thinking_tokens` → facturados como OUTPUT.
    * `cached_tokens` → facturados como INPUT com desconto 75%.
    * `tokens_input` NÃO inclui `cached_tokens` (são contabilizados em
      separado pelo SDK).
    """
    t = _tabela_para(modelo)
    taxa = taxa_eur_usd()
    custo_usd = (
        (tokens_input / 1_000_000.0) * t["in"]
        + (cached_tokens / 1_000_000.0) * t["in"] * PRECOS_CACHE_FACTOR
        + ((tokens_output + thinking_tokens) / 1_000_000.0) * t["out"]
    )
    return round(custo_usd * taxa, 6)


def extrair_usage(response_or_chunk: Any) -> dict[str, int]:
    """Lê `usage_metadata` de uma resposta/chunk do SDK `google-genai`.

    Devolve sempre um dict com chaves fixas (defaults a 0) mesmo quando
    o SDK não devolve usage (ex.: streaming parcial).
    """
    out = {
        "prompt_token_count": 0,
        "candidates_token_count": 0,
        "thoughts_token_count": 0,
        "cached_content_token_count": 0,
        "total_token_count": 0,
    }
    usage = getattr(response_or_chunk, "usage_metadata", None)
    if not usage:
        return out
    for k in list(out.keys()):
        v = getattr(usage, k, None)
        if isinstance(v, int):
            out[k] = v
    return out


def acumular_usage(acc: dict[str, int], novo: dict[str, int]) -> dict[str, int]:
    """Soma campo-a-campo (mutando `acc` e devolvendo)."""
    for k, v in novo.items():
        acc[k] = int(acc.get(k, 0)) + int(v or 0)
    return acc


def novo_acumulador() -> dict[str, int]:
    """Cria um dict zerado para `acumular_usage`."""
    return {
        "prompt_token_count": 0,
        "candidates_token_count": 0,
        "thoughts_token_count": 0,
        "cached_content_token_count": 0,
        "total_token_count": 0,
    }


__all__ = [
    "PRECOS_USD_POR_1M",
    "PRECOS_CACHE_FACTOR",
    "taxa_eur_usd",
    "custo_eur",
    "extrair_usage",
    "acumular_usage",
    "novo_acumulador",
]
