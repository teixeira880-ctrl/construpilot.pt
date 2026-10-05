"""Stair Engine — cálculo e verificação de escadas adaptado às normas PT.

Normas aplicadas:
  - RGEU art. 42º–48º (dimensões mínimas, pé-direito, patamares)
  - REH (Regulamento Edificações Habitação) — larguras mínimas
  - RSCIE — vias evacuação (DL 220/2008 + Portaria 1532/2008)
  - EN 1992-1-1 §9.10 — armaduras escadas betão armado
  - EN 1991-1-1 Anexo A — ações cargas em escadas
  - DL 163/2006 — acessibilidade (dec-lei acessibilidade pessoas mobilidade condicionada)
"""
from engines.stair_engine.calculator import calculate_stair, StairInputs

__all__ = ["calculate_stair", "StairInputs"]
