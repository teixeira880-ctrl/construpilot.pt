"""Solver BTP · ConstruPilot (PT).

Diagnóstico + soluções + urgência + gráficos a partir de uma descrição textual.

Portado do FR em 2026-02-04. Adaptações PT:
  - System prompt em PT-PT com normas RGEU / RJUE / Eurocódigos / NP EN / LNEC
  - LLM via `engines.ai_providers.router` (Claude Opus 5.5 + OpenAI fallback)
  - Enrichment Perplexity opcional
  - Preços em EUR com IVA 23 %, mercado PT 2026
"""
from engines.btp_solver.schema import (
    Cause,
    Chart,
    ChartSeries,
    Reference,
    Solution,
    SolutionStep,
    SolverResponse,
)
from engines.btp_solver.solver import solve

__all__ = [
    "solve",
    "SolverResponse",
    "Cause",
    "Solution",
    "SolutionStep",
    "Chart",
    "ChartSeries",
    "Reference",
]
