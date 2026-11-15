"""Geometria v3 — divisões, paredes e controlos a partir da geometria real da planta (sem IA).

Princípios (iguais para DWG/DXF, PDF vetorial e digitalizações):
  1. A escala vem primeiro e precisa de consenso entre fontes independentes (`escala`).
  2. As divisões são as faces fechadas pelas faces das paredes (`vetor`): mobiliário, hachuras e folhas de porta
     nunca dividem uma divisão; uma divisão nunca toca no exterior do desenho.
  3. Cada divisão traz a sua confiança e as verificações que a sustentam (`coerencia`).
  4. Uma digitalização é primeiro vetorizada (`raster`) e segue exatamente o mesmo caminho.
"""
