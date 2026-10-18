# Defeitos intencionais na fixture Moradia Martins

Esta fixture é sintética e contém 5 defeitos propositadamente colocados para
validar os checks determinísticos do BET-PT Agent.

| # | Defeito | Página | Check esperado | Severidade |
|---|---------|--------|----------------|------------|
| 1 | Portão de garagem contado 2× (R/C + Cave) | arquitectura.pdf p.1 e p.2 | GEO-002 | grave |
| 2 | Nembo entre janelas com largura ≤ 0 (abertura sobreposta) | arquitectura.pdf p.1 | GEO-001 | grave |
| 3 | Sótão com cota ambígua "1.70 a 2.20 m" | arquitectura.pdf p.3 | SEM-002 ou pergunta on-the-fly | grave |
| 4 | Escada com abertura 1.20 m para delta_h = 3.00 m (não cabe) | arquitectura.pdf p.4 | GEO-004 | bloqueante |
| 5 | Cotas parciais 3.00 + 4.00 = 7.00 mas total declarado 7.50 | arquitectura.pdf p.1 | GEO-007 | grave |

Também inclui, no brief.json, um pedido fora de âmbito ("análise térmica REH")
para validar SEM-005 (aviso).

Nenhum destes defeitos são bugs do gerador — são defeitos **deliberados** para
testar que o pipeline os detecta.
