"""Módulo de urbanismo ConstruPilot (.pt) — editor de volumes, peças desenhadas e verificação de parâmetros.

- volumes.py : geometria determinística (polígonos em metros) e desenhos esquemáticos PNG
  (planta de implantação, corte, alçado principal, axonometria; muros de vedação; piscinas).
- regras.py  : quadro de áreas, verificação dos parâmetros do PDM introduzidos pelo utilizador,
  normas nacionais (RGEU, Código Civil) e enquadramento RJUE (reutiliza engines.autorizacao_obras_pt).
- pdf.py     : quadro de áreas e verificação (PDF A4), peças desenhadas (PDF A3) e exportação ZIP.
- exemplo.py : processo de exemplo fictício (funciona sem rede).

Nenhum valor municipal é inventado: os parâmetros do PDM são sempre introduzidos pelo utilizador.
"""
