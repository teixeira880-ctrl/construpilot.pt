"""Piloto automático de licenciamento (Portugal): de um pedido simples («quero uma autorização de construção na Rua X, Braga»)
ao processo completo — dados do terreno, implantação, plantas, quadro de áreas, verificação, peças escritas e desenhadas, 3D.

Princípios de fiabilidade (iguais aos do motor de urbanismo):
- dados oficiais quando existem (DGT: CAOP, CRUS do PDM, servidões e restrições; altimetria; ortofotomapa);
- quando faltam, hipóteses PRUDENTES, sempre registadas como hipóteses («pressupostos») e nunca escritas como valores municipais;
- uma única fonte de verdade (o processo) para todos os motores; cada número final é recalculado de forma independente
  (engines.urbanismo_pt.auto.coerencia) e o processo só é dado como pronto se tudo bater certo.
"""
