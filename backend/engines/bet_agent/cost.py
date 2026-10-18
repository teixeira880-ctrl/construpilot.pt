"""Metering de custos Claude por dossier.

Capturar `input_tokens`, `output_tokens`, `cache_read_tokens` em cada chamada
API, converter em €uros e acumular. Alertar se exceder o limite por dossier.

Preços (EUR/1M tokens) — tabela interna, actualizada manualmente.
Fonte: tabela pública Anthropic traduzida de USD→EUR a 1 USD ≈ 0.92 EUR (6M média 2026-01).

Qualquer discrepância é tolerável porque este metering serve só para o
alerta >€10/dossier; o facturado real vem da conta Anthropic.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from engines.bet_agent.models.summary import CostBreakdown

logger = logging.getLogger(__name__)


# Preços indicativos (EUR por 1 000 000 tokens).
# Formato: {model_id: (input_eur_per_m, output_eur_per_m, cache_read_eur_per_m)}
_PRICING_EUR_PER_M: dict[str, tuple[float, float, float]] = {
    # Claude Opus 5.5  —  aprox 15 USD input, 75 USD output / 1M (ajustar quando
    # tabela oficial 2026 publicar; USD→EUR factor 0.92).
    "claude-opus-5-5": (13.80, 69.00, 1.38),
    # Claude Sonnet 5.5 — aprox 3 USD input, 15 USD output / 1M.
    "claude-sonnet-5-5": (2.76, 13.80, 0.276),
    # Claude Haiku 5.5 — aprox 0.80 USD input, 4 USD output / 1M.
    "claude-haiku-5-5": (0.736, 3.68, 0.0736),
}


def _limit_eur() -> float:
    """Limite por dossier em euros (default 10€, override por env)."""
    try:
        return float(os.environ.get("BET_AGENT_COST_LIMIT_EUR", "10.0"))
    except ValueError:
        return 10.0


@dataclass
class DossierMeter:
    """Acumulador de custo para 1 dossier. Thread-safety: 1 instância por dossier."""

    project_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    _calls: list[dict] = field(default_factory=list)

    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
    ) -> None:
        """Regista uma chamada API. Nunca falha; se modelo desconhecido assume
        preço = Opus (conservador) e flagga no log."""
        self.input_tokens += max(0, input_tokens)
        self.output_tokens += max(0, output_tokens)
        self.cache_read_tokens += max(0, cache_read_tokens)
        pricing = _PRICING_EUR_PER_M.get(model)
        if pricing is None:
            logger.warning(
                "bet_agent cost: modelo desconhecido '%s', usar preço opus-5-5 conservador.",
                model,
            )
            pricing = _PRICING_EUR_PER_M["claude-opus-5-5"]
        self._calls.append({
            "model": model,
            "input": input_tokens,
            "output": output_tokens,
            "cache_read": cache_read_tokens,
            "eur": self._compute_call_eur(pricing, input_tokens, output_tokens, cache_read_tokens),
        })

    @staticmethod
    def _compute_call_eur(
        pricing: tuple[float, float, float],
        inp: int,
        out: int,
        cache: int,
    ) -> float:
        inp_eur_per_m, out_eur_per_m, cache_eur_per_m = pricing
        return (
            inp * inp_eur_per_m / 1_000_000
            + out * out_eur_per_m / 1_000_000
            + cache * cache_eur_per_m / 1_000_000
        )

    def total_eur(self) -> float:
        return sum(call["eur"] for call in self._calls)

    def to_breakdown(self) -> CostBreakdown:
        eur_total = self.total_eur()
        limit = _limit_eur()
        return CostBreakdown(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_read_tokens=self.cache_read_tokens,
            eur_total=round(eur_total, 4),
            eur_limit=limit,
            exceeded_limit=eur_total > limit,
        )

    def calls_detail(self) -> list[dict]:
        """Devolve detalhe das chamadas (ex: para debug/admin)."""
        return list(self._calls)
