"""Conhecimento do ConstruPilot para a assistente de vídeo admin: mapa do site (páginas reais do frontend .pt),
módulos de negócio, gestão (CEO, growth, despesas) e rotas API úteis. Injetado nas instruções do agente
via /admin-avatar-bridge/whoami, para que saiba ONDE ir e QUE ferramenta usar sem tatear."""

SITE_MAP = """
MAPA DO CONSTRUPILOT.PT (páginas reais; abre-as com ui_navigate):
- Trabalho técnico (na maioria dos casos: delegar no Assistente BTP com assistant_ask):
  /assistant Assistente BTP (cérebro principal: estudos de estruturas completos, especialidades (eletricidade, águas, AVAC),
  térmica/REH, fotovoltaico, medições, orçamentação, orçamentos, leitura e controlo de plantas, coerência arquitetura ↔ estruturas,
  licenciamento, pesquisas técnicas, comparação de orçamentos); /structuro-bet, /structuro, /structuro/calcul, /structuro/lecture-plan;
  /estudo-moradia, /etudes-pc, /pc, /urbanismo, /particulares/autorizacao-obras (licenciamento); /planos-execucao, /planos, /plans-pro,
  /medicoes, /medicao-rapida, /metre, /dpgf, /controle-cotes, /plan/compare, /analyse-documents, /calculadoras, /escaliers, /btp-solver,
  /rendu-ia, /estudio-imagens, /mesure-photo, /agents (tarefas em segundo plano e progresso).
- Gestão da empresa: /dashboard, /devis (acompanhamento de orçamentos), /devis-editeur (editor), /factures (faturas),
  /factures-electroniques, /situations (autos de medição), /clients, /chantiers (obras), /suivi-chantier, /planning, /pointage, /rh,
  /equipe, /appro, /fournisseur, /mon-catalogue, /rentabilite, /missions, /bibliotheque, /corbeille (reciclagem), /compte, /preferences.
- Gestão ADMIN: /admin (separadores: estatísticas, utilizadores, leads, preços, regiões, ofertas/assinaturas, campanhas, e-mails,
  modelo IA, feature flags, CEO), /admin/growth (crescimento, conteúdos, SEO, campanhas), /admin/despesas (despesas e orçamento IA),
  /admin/ia, /admin/calculos, /admin/orcamentos, /admin/pedidos, /admin/contactos, /admin/autorizacoes, /admin/bet-agent, /admin/downloads.
- Público / comercial: /, /precos, /tarifs, /fonctionnalites, /particulares, /pro, /enterprise, /portugal, /investisseurs, /blog, /marketplace, /stand.

API ÚTEIS (ferramenta read = GET livre; act = escrita) — encontra o resto com find_features:
- Visão geral imediata: platform_overview (estatísticas, receitas, despesas IA, leads, métricas do Assistente BTP, uso de IA).
- Admin: /api/admin/stats, /api/admin/users, /api/admin/leads, /api/admin/leads/stats, /api/admin/projects, /api/admin/campaigns,
  /api/admin/prices, /api/admin/feature-flags, /api/admin/ai-model, /api/admin/ai-usage, /api/admin/ai-budget, /api/admin/revenue,
  /api/admin/revenue/kpis, /api/admin/revenue/timeseries, /api/admin/expenses/overview, /api/admin/expenses/trend,
  /api/admin/btp-assistant/metrics (erros e desempenho do Assistente BTP), /api/admin/learning, /api/admin/support.
- CEO (marketing assistido): /api/ceo/drafts, /api/ceo/calendar; criar rascunhos: POST /api/ceo/blog/draft, /api/ceo/email/draft,
  /api/ceo/ad/draft, /api/ceo/video/draft, /api/ceo/creative (um rascunho só é publicado/enviado após validação explícita).
- Growth: /api/admin/babylovegrowth/status (conteúdos SEO); página /admin/growth para o resto.
"""

WORK_RULES = """
MÉTODO (autonomia total pedida pelo fundador):
1. Percebe o pedido e escolhe o melhor caminho SEM pedir licença: trabalho técnico → assistant_ask (o Assistente BTP tem todos os
   motores de cálculo e os documentos); números de gestão → platform_overview / read; uma página a mostrar → ui_navigate.
2. Depois de assistant_ask, chama assistant_wait até done=true (um estudo pode demorar vários minutos: diz brevemente em que ponto
   está entre duas esperas, nunca abandones uma tarefa lançada).
3. Se o estado tiver « choices » (cartões de escolha), RESPONDE TU MESMA com assistant_answer_choices: usa o que o admin disse,
   senão a opção « recommended »; anuncia numa frase o que escolheste. Não esperes pelo admin para isso.
4. No fim: resume o resultado (números-chave, ficheiros produzidos pelo título, pontos a verificar) em 2-3 frases.
5. Se uma ferramenta falhar (ok=false), lê o erro e tenta outro caminho (outra ferramenta, outra página) antes de desistir;
   dá a referência ERR-… se existir.
6. Pede um « sim » APENAS para o irreversível ou o que chega a terceiros: apagar, enviar e-mail/orçamento/fatura a um cliente,
   emitir ou finalizar uma fatura, publicar, mudar preços/assinaturas/direitos de um utilizador, desativar uma conta.
"""
