"""Módulo BET-PT Agent — pipeline estrutural híbrido (LLM + determinístico).

ARQUITECTURA (resumo R1):
    1. `brief.py`  — parse e validação do briefing do utilizador (prioridade
       sobre defaults).
    2. `reader.py` — leitura visão+texto das plantas via Claude Opus 5.5, com
       tool-use estrito. **Zero cálculo**, apenas extracção estruturada para
       o `BuildingModel`.
    3. `checks/`   — regras determinísticas (geometria + semântica). Produzem
       `Anomaly` com `source: {page, bbox}`.
    4. `agent/`    — loop reader (ReAct-style), ferramentas e prompts PT-PT.
    5. `summary.py`— resumo honesto, com delta de entregáveis pedidos vs
       produzidos, hipóteses usadas, custo real e `global_status`.
    6. `cost.py`   — metering por chamada Claude e alerta se >€10/dossier.
    7. `registry/` — tabelas estáticas PT (entregáveis, zonas sísmicas).

REGRAS DURAS:
    - Hipóteses do utilizador têm **sempre** prioridade sobre defaults.
    - LLM nunca gera valores estruturais. Só lê/orquestra.
    - Verificador final = sessão nova isolada (Opus 5.5, zero histórico).
    - Rodapé obrigatório em qualquer saída: "pré-dimensionamento, a verificar
      e assinar pelo técnico responsável".
    - Feature flag `BET_AGENT_ENABLED` (default `false`). Fora dessa flag,
      pipeline não arranca.

NÃO MODIFICA os módulos BET existentes (lotes 0-6). Adição isolada.
"""
from __future__ import annotations

import os


def is_enabled() -> bool:
    """True se feature flag `BET_AGENT_ENABLED=true` no ambiente."""
    return (os.environ.get("BET_AGENT_ENABLED") or "").strip().lower() == "true"


__all__ = ["is_enabled"]
