"""Decks PowerPoint ConstruPilot : version client et version investisseur, FR / EN / PT.

- `build_client_pptx(lang)` : deck commercial avec captures d'écran réelles du produit.
- `build_investor_pptx(lang, metrics, docs_count)` : deck investisseur ; les KPI viennent des
  mesures réelles (`engines.journey.journey_metrics`). Une valeur non mesurable s'affiche
  « non mesurable », jamais 0.

Les captures sont celles de `backend/assets/screens/` (script `scripts/capture_screens.py`).
"""
from __future__ import annotations

import io
import os
import base64
from datetime import date

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

SHOTS = "/app/backend/assets/screens/"
DEEP = RGBColor(0x0B, 0x3B, 0x25)
GREEN = RGBColor(0x15, 0x80, 0x3D)
GREY = RGBColor(0x5B, 0x64, 0x72)
DARK = RGBColor(0x11, 0x18, 0x27)
LIGHT = RGBColor(0xF1, 0xF6, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

SITE = "construpilot.fr"
CONTACT = "info@construpilot.pt"
PATENT = "FR2611044"

# ════════════════════════════════════  Deck client  ════════════════════════════════════

CLIENT = {
    "fr": {
        "cover": ("ConstruPilot",
                  "Do mapa de quantidades do arquiteto à conta final",
                  f'Orçamentação · medição · orçamentos · obra · faturação por autos de medição — uma única ferramenta para os profissionais e as PME da construção · {SITE}'),
        "slides": [
            ("O que faz o ConstruPilot", [
                "Uma única base: a informação introduzida uma vez serve da primeira chamada do cliente até ao saldo final.",
                "Orçamentação de mapas de quantidades, medições sobre planta, orçamentos, acompanhamento de obra, autos de medição, conta final.",
                "Dois espaços: PARTICULAR (projeto pessoal) e PROFISSIONAL (artesão, PME, empresa geral).",
                "Web e aplicações móveis dedicadas para Android e iOS.",
                f'Brevet n° {PATENT} · alojamento na União Europeia.',
            ], "dashboard.png"),
            ("1. Orçamentar o mapa do arquiteto", [
                "DPGF / BPU / DQE: vários mapas Excel e vários cadernos de encargos num mesmo estudo.",
                "Lotes detetados, preços da SUA biblioteca e depois IA para as linhas desconhecidas.",
                "Instruções em linguagem natural: «não orçamentes a cerâmica nem o parquet, margem 12 %».",
                "Leitura do caderno de encargos: prescrições ligadas às linhas e alerta sobre trabalhos esquecidos.",
                "Margem por lote, alerta de margem baixa, comparação de propostas de subempreiteiros, passagem a orçamento num clique.",
            ], "dpgf.png"),
            ("2. Medições e orçamentos assinados", [
                "Medições sobre planta: importação PDF / DWG, escala, comprimentos, áreas, quantidades exportáveis.",
                "Orçamentos: 3 apresentações, o seu logótipo e cores, descritivos detalhados, IVA 5,5 / 10 / 20 %.",
                "Assinatura: código QR, assinatura online ou no local, reativação automática aos 7 dias.",
                "Biblioteca de preços que cresce em cada orçamentação validada.",
                "Ditado por voz: orçamentos, reservas e mensagens ditados na obra.",
            ], "devis.png"),
            ("3. Acompanhar a obra e o cliente", [
                "Processo de obra: planeamento, tarefas, fotografias antes/depois, reservas, relatórios.",
                "Espaço do cliente seguro: progresso, mensagens, documentos, comunicação de problemas.",
                "Subempreiteiros e fornecedores: fichas, consultas por lote, respostas online sem conta.",
                "Aprovisionamentos e registo de horas das equipas.",
                "O cliente vê apenas a sua obra: isolamento estrito dos dados.",
            ], "chantiers.png"),
            ("4. Faturar sem perder nada", [
                "Fatura de adiantamento gerada automaticamente logo após a assinatura do orçamento.",
                "Autos de medição: progresso linha a linha, retenção de garantia, conta em PDF, certificado de pagamento.",
                "O adiantamento efetivamente recebido é deduzido automaticamente (proporcional, total ou valor escolhido).",
                "Conta final num clique: saldo, adiantamento restante, libertação da retenção.",
                "Acompanhamento de pagamentos, avisos, notas de crédito, exportações contabilísticas.",
            ], "situations.png"),
            ("Assistente de IA e ditado", [
                "Respostas técnicas: normas DTU, métodos de execução, dosagens, com os seus documentos em contexto.",
                "Redação assistida: cartas, relatórios, descritivos de orçamento.",
                "A IA propõe, você decide: qualquer preço é editável e a sua origem fica registada.",
                "Três fornecedores de IA intercambiáveis: sem dependência de um único ator.",
                "Estimativas indicativas: ajudam a decidir, o autor do orçamento continua a ser você.",
            ], "assistant.png"),
            ("Aplicações Android e iOS", [
                "Aplicações móveis dedicadas, não um site adaptado ao telefone.",
                "Três utilizações: Obra (empresa), Colaborador (equipa), Particulares (cliente final).",
                "No terreno: fotografias, reservas, ditado, progresso, assinatura no local.",
                "Notificações: orçamento assinado, fatura em atraso, proposta de subempreiteiro recebida.",
                "Eliminação autónoma da conta e dos dados, conforme as regras das lojas de aplicações.",
            ], None),
            ("Preços e início", [
                "Profissional: 149 € / mês por empresa · Particular: 19 € / mês.",
                "API e integrações: 99 € / mês · opções e módulos a partir de 5 € / mês.",
                "Teste de 7 dias, fase de lançamento gratuita em curso, pagamentos por Stripe.",
                f'Os preços apresentados na aplicação prevalecem ({SITE}/tarifs) : ce document est indicatif.',
                "Para começar: crie a conta, importe a sua biblioteca de preços, carregue o primeiro mapa de quantidades.",
            ], None),
        ],
        "end": ("Falemos da sua próxima obra",
                f"{CONTACT} · {SITE} · Brevet n° {PATENT}"),
        "note": "Captura de ecrã real da plataforma.",
    },
    "en": {
        "cover": ("ConstruPilot",
                  "From the architect's bill of quantities to the final account",
                  "Pricing · take-off · quotes · site monitoring · progress invoicing — one tool for "
                  f"trade contractors and construction SMEs · {SITE}"),
        "slides": [
            ("What ConstruPilot does", [
                "One database: information entered once is reused from the first client call to the final payment.",
                "Pricing architects' schedules, on-plan take-off, quotes, site monitoring, progress accounts, final account.",
                "Two workspaces: INDIVIDUAL (personal project) and PROFESSIONAL (trade contractor, SME, main contractor).",
                "Web plus dedicated Android and iOS mobile apps.",
                f"Patent no. {PATENT} · hosted in the European Union.",
            ], "dashboard.png"),
            ("1. Price the architect's schedule", [
                "Bills of quantities (DPGF / BPU / DQE): several Excel schedules and several specifications in one study.",
                "Lots detected, prices taken from YOUR library first, then AI for unknown items.",
                "Plain-language instructions: \"don't price the tiling or the parquet, 12% markup\".",
                "Specification reading: requirements attached to lines and alerts on omitted items.",
                "Margin per lot, low-margin alert, subcontractor offer comparison, one click to a quote.",
            ], "dpgf.png"),
            ("2. Take-off and signed quotes", [
                "On-plan take-off: PDF / DWG import, scaling, lengths, areas, exportable quantities.",
                "Quotes: 3 layouts, your logo and colours, detailed descriptions, French VAT rates.",
                "Signature: QR code, online or on-site signing, automatic 7-day follow-up.",
                "A price library that grows with every validated pricing job.",
                "Voice dictation: quotes, snags and messages dictated from the site.",
            ], "devis.png"),
            ("3. Run the site and the client relationship", [
                "Site file: schedule, tasks, before/after photos, snags, reports.",
                "Secure client portal: progress, messaging, documents, issue reporting.",
                "Subcontractors and suppliers: records, lot-level enquiries, online answers without an account.",
                "Deliveries and team time tracking.",
                "Your client only sees their own project: strict data isolation.",
            ], "chantiers.png"),
            ("4. Invoice without losing money", [
                "Deposit invoice created automatically as soon as the quote is signed.",
                "Progress accounts: line-by-line progress, retention, PDF statement, payment certificate.",
                "The deposit actually received is offset automatically (pro rata, in full or a chosen amount).",
                "Final account in one click: balance, remaining deposit, release of retention.",
                "Payment tracking, reminders, credit notes, accounting exports.",
            ], "situations.png"),
            ("AI assistant and dictation", [
                "Technical answers: French DTU standards, methods, mixes, with your own documents as context.",
                "Writing help: letters, reports, quote descriptions.",
                "AI proposes, you decide: every price stays editable and its origin is traced.",
                "Three interchangeable AI vendors: no dependency on a single provider.",
                "Estimates are indicative: they help you decide, you remain the author of the quote.",
            ], "assistant.png"),
            ("Dedicated Android and iOS apps", [
                "Dedicated mobile apps, not a website squeezed onto a phone.",
                "Three uses: Site (company), Team member, Individuals (end client).",
                "In the field: photos, snags, dictation, progress, on-site signature.",
                "Notifications: quote signed, invoice overdue, subcontractor offer received.",
                "Self-service account and data deletion, in line with app store rules.",
            ], None),
            ("Pricing and getting started", [
                "Professional: €149 / month per company · Individual: €19 / month.",
                "API and integrations: €99 / month · add-ons from €5 / month.",
                "7-day trial, free launch phase in progress, Stripe payments.",
                f"Prices shown in the application prevail ({SITE}/tarifs): this document is indicative.",
                "Getting started: create your account, import your price library, upload your first schedule.",
            ], None),
        ],
        "end": ("Let's talk about your next project",
                f"{CONTACT} · {SITE} · Patent no. {PATENT}"),
        "note": "Real screenshot of the platform.",
    },
    "pt": {
        "cover": ("ConstruPilot",
                  "Do mapa de quantidades do arquiteto à conta final",
                  "Orçamentação · medições · orçamentos · obra · faturação por autos de medição — uma "
                  f"única ferramenta para artesãos e PME da construção · {SITE}"),
        "slides": [
            ("O que faz o ConstruPilot", [
                "Uma única base: a informação introduzida uma vez serve da primeira chamada do cliente até ao saldo final.",
                "Orçamentação de mapas de quantidades, medições sobre planta, orçamentos, acompanhamento de obra, autos de medição, conta final.",
                "Dois espaços: PARTICULAR (projeto pessoal) e PROFISSIONAL (artesão, PME, empresa geral).",
                "Web e aplicações móveis dedicadas para Android e iOS.",
                f"Patente n.º {PATENT} · alojamento na União Europeia.",
            ], "dashboard.png"),
            ("1. Orçamentar o mapa do arquiteto", [
                "DPGF / BPU / DQE: vários mapas Excel e vários cadernos de encargos num mesmo estudo.",
                "Lotes detetados, preços da SUA biblioteca e depois IA para as linhas desconhecidas.",
                "Instruções em linguagem natural: « não orçamentes a cerâmica nem o parquet, margem 12 % ».",
                "Leitura do caderno de encargos: prescrições ligadas às linhas e alerta sobre trabalhos esquecidos.",
                "Margem por lote, alerta de margem baixa, comparação de propostas de subempreiteiros, passagem a orçamento num clique.",
            ], "dpgf.png"),
            ("2. Medições e orçamentos assinados", [
                "Medições sobre planta: importação PDF / DWG, escala, comprimentos, áreas, quantidades exportáveis.",
                "Orçamentos: 3 apresentações, o seu logótipo e cores, descritivos detalhados, IVA 5,5 / 10 / 20 %.",
                "Assinatura: código QR, assinatura online ou no local, reativação automática aos 7 dias.",
                "Biblioteca de preços que cresce em cada orçamentação validada.",
                "Ditado por voz: orçamentos, reservas e mensagens ditados na obra.",
            ], "devis.png"),
            ("3. Acompanhar a obra e o cliente", [
                "Processo de obra: planeamento, tarefas, fotografias antes/depois, reservas, relatórios.",
                "Espaço do cliente seguro: progresso, mensagens, documentos, comunicação de problemas.",
                "Subempreiteiros e fornecedores: fichas, consultas por lote, respostas online sem conta.",
                "Aprovisionamentos e registo de horas das equipas.",
                "O cliente vê apenas a sua obra: isolamento estrito dos dados.",
            ], "chantiers.png"),
            ("4. Faturar sem perder nada", [
                "Fatura de adiantamento gerada automaticamente logo após a assinatura do orçamento.",
                "Autos de medição: progresso linha a linha, retenção de garantia, conta em PDF, certificado de pagamento.",
                "O adiantamento efetivamente recebido é deduzido automaticamente (proporcional, total ou valor escolhido).",
                "Conta final num clique: saldo, adiantamento restante, libertação da retenção.",
                "Acompanhamento de pagamentos, avisos, notas de crédito, exportações contabilísticas.",
            ], "situations.png"),
            ("Assistente de IA e ditado", [
                "Respostas técnicas: normas NP EN, especificações LNEC, métodos de execução, dosagens, com os seus documentos em contexto.",
                "Redação assistida: cartas, relatórios, descritivos de orçamento.",
                "A IA propõe, você decide: qualquer preço é editável e a sua origem fica registada.",
                "Três fornecedores de IA intercambiáveis: sem dependência de um único ator.",
                "Estimativas indicativas: ajudam a decidir, o autor do orçamento continua a ser você.",
            ], "assistant.png"),
            ("Aplicações Android e iOS", [
                "Aplicações móveis dedicadas, não um site adaptado ao telefone.",
                "Três utilizações: Obra (empresa), Colaborador (equipa), Particulares (cliente final).",
                "No terreno: fotografias, reservas, ditado, progresso, assinatura no local.",
                "Notificações: orçamento assinado, fatura em atraso, proposta de subempreiteiro recebida.",
                "Eliminação autónoma da conta e dos dados, conforme as regras das lojas de aplicações.",
            ], None),
            ("Preços e início", [
                "Profissional: 149 € / mês por empresa · Particular: 19 € / mês.",
                "API e integrações: 99 € / mês · opções e módulos a partir de 5 € / mês.",
                "Teste de 7 dias, fase de lançamento gratuita em curso, pagamentos por Stripe.",
                f"Os preços apresentados na aplicação prevalecem ({SITE}/tarifs): este documento é indicativo.",
                "Para começar: crie a conta, importe a sua biblioteca de preços, carregue o primeiro mapa de quantidades.",
            ], None),
        ],
        "end": ("Falemos da sua próxima obra",
                f"{CONTACT} · {SITE} · Patente n.º {PATENT}"),
        "note": "Captura de ecrã real da plataforma.",
    },
}

# ══════════════════════════════════  Deck investisseur  ══════════════════════════════════

FUNDS = {
    "fr": [["Aplicação dos fundos", "Detalhe", "Montante", "Parte"],
           ["Produto & tecnologia", "Desenvolvimento, apps Android/iOS, fiabilidade, testes", "150 000 €", "30 %"],
           ["Aquisição & vendas", "Comerciais no terreno, demonstrações, feiras, CRM", "160 000 €", "32 %"],
           ["Conteúdo & marketing", "SEO, conteúdos do setor, folhetos com código QR", "60 000 €", "12 %"],
           ["Infraestrutura & IA", "Alojamento, APIs de IA, armazenamento, segurança", "50 000 €", "10 %"],
           ["Suporte & sucesso do cliente", "Acompanhamento, formação, migração de preços", "40 000 €", "8 %"],
           ["Conformidade & jurídico", "RGPD, contratos, patente, contabilidade", "20 000 €", "4 %"],
           ["Reserva", "Imprevistos e oportunidades não orçamentadas", "20 000 €", "4 %"],
           ["Total", "24 meses · ~20 800 € / mês", "500 000 €", "100 %"]],
    "en": [["Use of funds", "Detail", "Amount", "Share"],
           ["Product & engineering", "Development, Android/iOS apps, reliability, testing", "€150,000", "30%"],
           ["Acquisition & sales", "Field sales, demos, trade shows, CRM", "€160,000", "32%"],
           ["Content & marketing", "SEO, trade content, QR-code leaflets", "€60,000", "12%"],
           ["Infrastructure & AI", "Hosting, AI APIs, storage, security", "€50,000", "10%"],
           ["Support & customer success", "Onboarding, training, price migration", "€40,000", "8%"],
           ["Compliance & legal", "GDPR, contracts, patent, accounting", "€20,000", "4%"],
           ["Reserve", "Contingencies and unbudgeted opportunities", "€20,000", "4%"],
           ["Total", "24 months · ~€20,800 / month", "€500,000", "100%"]],
    "pt": [["Aplicação dos fundos", "Detalhe", "Montante", "Parte"],
           ["Produto & tecnologia", "Desenvolvimento, apps Android/iOS, fiabilidade, testes", "150 000 €", "30 %"],
           ["Aquisição & vendas", "Comerciais no terreno, demonstrações, feiras, CRM", "160 000 €", "32 %"],
           ["Conteúdo & marketing", "SEO, conteúdos do setor, folhetos com código QR", "60 000 €", "12 %"],
           ["Infraestrutura & IA", "Alojamento, APIs de IA, armazenamento, segurança", "50 000 €", "10 %"],
           ["Suporte & sucesso do cliente", "Acompanhamento, formação, migração de preços", "40 000 €", "8 %"],
           ["Conformidade & jurídico", "RGPD, contratos, patente, contabilidade", "20 000 €", "4 %"],
           ["Reserva", "Imprevistos e oportunidades não orçamentadas", "20 000 €", "4 %"],
           ["Total", "24 meses · ~20 800 € / mês", "500 000 €", "100 %"]],
}

INV = {
    "fr": {
        "cover": ("ConstruPilot — apresentação a investidores",
                  "Software vertical para a construção francesa: orçamentação do mapa de quantidades do arquiteto, medições sobre planta e faturação por autos na mesma base",
                  "Documento de trabalho · confidencial · plano de exploração de 500 000 € em 24 meses"),
        "kpi_title": "Números medidos na base de dados",
        "kpi_cols": ["Indicador", "Valor"],
        "kpi_note": "Medido em {d} · janela de {w} dias · uma métrica não mensurável é apresentada como «não mensurável»: nunca 0, nunca um número reconstituído.",
        "nomeasure": "não mensurável",
        "labels": ["Contas existentes (sem testes)", "Ativos em 30 dias", "Subscrições pagas ativas",
                   "Registos medidos (30 d)", "Taxa de ativação (30 d)",
                   "Empresas identificadas (SIRET)", "Orçamentos e faturas criados"],
        "funds_title": "Plano de exploração — 500 000 € em 24 meses",
        "slides_before": [
            ("1. O problema", [
                "As pequenas e médias empresas de construção continuam a trabalhar em folhas de cálculo: mapas do arquiteto orçamentados à mão, medições repetidas, orçamentos sem biblioteca de preços fiável.",
                "A margem perde-se nos esquecimentos administrativos: trabalhos exigidos no caderno de encargos nunca orçamentados, adiantamentos não deduzidos, autos mal calculados, retenções nunca reclamadas.",
                "As ferramentas existentes cobrem a gestão, ou a orçamentação, ou o acompanhamento de obra: a ligação entre as três continua a ser humana e, por isso, caro.",
                "Resultado: horas de escritório não faturáveis e margem que desaparece no fim da obra.",
            ], None),
            ("2. O produto: a cadeia completa", [
                "Um único registo do mapa do arquiteto até à conta final.",
                "Estimativa, medições sobre planta, orçamentação DPGF, orçamentos, obra, autos de medição, conta final, espaço do cliente.",
                "Web e aplicações nativas Android e iOS para utilização no terreno.",
                "Gestão interna integrada: origem dos registos, ativação, despesas por envelope.",
            ], "dashboard.png"),
            ("3. O núcleo técnico: orçamentação DPGF", [
                "Leitura multi-folha de vários mapas Excel e vários cadernos de encargos num mesmo estudo.",
                "Preços da biblioteca da empresa e depois IA para as linhas desconhecidas, com a origem de cada preço registada.",
                "Instruções em linguagem natural, margem por lote, alerta de margem baixa, deteção de trabalhos exigidos no caderno de encargos mas ausentes do mapa.",
                "Consultas a subempreiteiros por lote, resposta online sem conta, comparação de propostas.",
                "A tarefa mais longa da profissão passa de várias horas a alguns minutos: é a porta de entrada do produto.",
            ], "dpgf.png"),
            ("4. Onde a margem se recupera: a faturação", [
                "Adiantamento automático na assinatura, autos de medição, retenção de garantia, certificado de pagamento.",
                "O adiantamento efetivamente recebido é deduzido automaticamente — a fonte de erro mais frequente do setor.",
                "Conta final num clique: saldo, adiantamento restante, libertação da retenção.",
                "Um benefício que o próprio utilizador consegue quantificar: tesouraria recebida mais cedo, margem preservada.",
            ], "situations.png"),
            ("5. O mercado francês", [
                "450 000 empresas de construção com volume de negócios positivo, excluindo micro-empresas puras (FFB, 2025).",
                "Cerca de 95 % são estruturas artesanais: aproximadamente metade da atividade e dos efetivos assalariados.",
                "193 mil milhões de euros de volume de negócios da construção em 2025 (FFB).",
                "1 731 000 ativos, dos quais 1 234 000 assalariados e 407 000 artesãos independentes (FFB).",
                "19 959 criações de empresas na construção no 3.º trimestre de 2025, +4,6 % num ano (INSEE).",
                "Fontes: ffbatiment.fr/le-batiment-en-chiffres · nota de conjuntura CAPEB T4 2025 · INSEE.",
            ], None),
            ("6. Posicionamento concorrencial", [
                "Ferramentas de gestão (orçamentos/faturas): não orçamentam um DPGF nem tratam autos completos ou conta final.",
                "Software de medições: poderoso, mas desligado da faturação e do acompanhamento de obra.",
                "ERP de construção: caro e pesado, fora do alcance de estruturas de 1 a 20 pessoas.",
                "ConstruPilot: a cadeia completa para o artesão e a PME, com IA onde é verificável.",
                "Barreira à saída: a biblioteca de preços da empresa enriquece em cada obra.",
            ], None),
            ("7. Modelo de negócio", [
                "Profissional: 149 € / mês por empresa — núcleo da receita recorrente.",
                "Particular: 19 € / mês · API e integrações: 99 € / mês · opções a partir de 5 € / mês.",
                "Teste de 7 dias, fase de lançamento gratuita em curso, pagamentos por Stripe.",
                "Receita recorrente por empresa com custo marginal controlado: a IA só é chamada nas linhas desconhecidas.",
                "Extensões naturais: integrações contabilísticas, distribuição pelos armazenistas, API para editores.",
            ], None),
        ],
        "slides_after": [
            ("Marcos do plano", [
                "Meses 1-6: publicação das aplicações Android e iOS, primeiros clientes pagantes, industrialização da orçamentação DPGF.",
                "Meses 7-12: aquisição controlada (SEO, terreno, parcerias com armazenistas), integrações contabilísticas.",
                "Meses 13-18: equipa comercial, implantação regional, módulos de subcontratação.",
                "Meses 19-24: abertura da API, parcerias de distribuição, preparação da internacionalização.",
                "São objetivos de trabalho: o progresso é publicado tal como é medido, sem números reconstituídos.",
            ], None),
            ("Riscos e respostas", [
                "Qualidade dos preços propostos pela IA → prioridade absoluta à biblioteca da empresa, preços sempre editáveis e arquivados.",
                "Dependência de um fornecedor de IA → três fornecedores intercambiáveis atrás de uma mesma interface interna.",
                "Heterogeneidade dos mapas → leitura tolerante (multi-folha, cabeçalhos variáveis) e correção linha a linha.",
                "Desvio de custos → aplicações seguidas por envelope no back-office, reconciliação mensal com os canais de aquisição.",
                "Conformidade (RGPD, lojas) → páginas legais, eliminação autónoma da conta, registo de acessos.",
            ], None),
            ("O que procuramos", [
                "Acesso ao mercado: apresentações a federações, agrupamentos de artesãos, armazenistas e gabinetes de projeto.",
                "Capacidade comercial: financiar um ciclo de venda no terreno e as contratações associadas ao longo dos 24 meses do plano.",
                "Parcerias de integração: software de contabilidade, distribuidores de materiais, plataformas de plantas.",
                "Governação: reporte trimestral exatamente sobre os indicadores medidos aqui apresentados.",
            ], None),
        ],
        "end": ("Contacto", f"{CONTACT} · {SITE} · Brevet n° {PATENT}"),
        "note": "Captura de ecrã real da plataforma.",
    },
    "en": {
        "cover": ("ConstruPilot — investor presentation",
                  "Vertical software for French construction: pricing an architect's bill of "
                  "quantities, on-plan take-off and progress invoicing in one database",
                  "Working document · confidential · €500,000 operating plan over 24 months"),
        "kpi_title": "Figures measured in the database",
        "kpi_cols": ["Indicator", "Value"],
        "kpi_note": "Measured on {d} · {w}-day window · a metric that cannot be measured is shown as "
                    "\"not measurable\": never 0, never a reconstructed figure.",
        "nomeasure": "not measurable",
        "labels": ["Existing accounts (excl. tests)", "Active over 30 days", "Active paid subscriptions",
                   "Measured sign-ups (30 d)", "Activation rate (30 d)",
                   "Identified companies (SIRET)", "Quotes & invoices created"],
        "funds_title": "Operating plan — €500,000 over 24 months",
        "slides_before": [
            ("1. The problem", [
                "Small and mid-sized construction firms still work in spreadsheets: architects' schedules priced by hand, take-offs redone, quotes without a reliable price library.",
                "Margin is lost in administrative omissions: items required by the specification never priced, deposits never offset, progress accounts miscalculated, retention never claimed.",
                "Existing tools cover admin, or pricing, or site monitoring: joining the three stays a human task, therefore costly.",
                "The result: hours of unbillable office work and margin that evaporates at the end of the job.",
            ], None),
            ("2. The product: the complete chain", [
                "One single record from the architect's schedule to the final account.",
                "Estimating, on-plan take-off, schedule pricing, quotes, site management, progress accounts, final account, client portal.",
                "Web plus native Android and iOS apps for field use.",
                "Built-in steering: sign-up sources, activation, spending by envelope.",
            ], "dashboard.png"),
            ("3. The technical core: schedule pricing", [
                "Multi-sheet reading of several Excel schedules and several specifications in one study.",
                "Prices from the company library first, then AI for unknown lines, with the origin of every price traced.",
                "Plain-language instructions, margin per lot, low-margin alert, detection of items required by the specification but missing from the schedule.",
                "Lot-level subcontractor enquiries, online answers without an account, offer comparison.",
                "The longest task of the trade drops from hours to minutes: this is the product's entry point.",
            ], "dpgf.png"),
            ("4. Where margin is recovered: invoicing", [
                "Automatic deposit on signature, progress accounts, retention, payment certificate.",
                "The deposit actually received is offset automatically — the most frequent source of error in the trade.",
                "Final account in one click: balance, remaining deposit, release of retention.",
                "A benefit the user can quantify themselves: cash collected earlier, margin preserved.",
            ], "situations.png"),
            ("5. The French market", [
                "450,000 construction companies with positive turnover, excluding pure micro-businesses (FFB, 2025).",
                "Close to 95% are craft-sized firms: about half of the activity and of salaried headcount.",
                "€193 billion of construction turnover (excl. VAT) in 2025 (FFB).",
                "1,731,000 people at work including 1,234,000 employees and 407,000 self-employed craftsmen (FFB).",
                "19,959 new construction companies in Q3 2025, +4.6% year on year (INSEE).",
                "Sources: ffbatiment.fr/le-batiment-en-chiffres · CAPEB Q4 2025 outlook · INSEE.",
            ], None),
            ("6. Competitive positioning", [
                "Admin tools (quotes/invoices): they do not price a bill of quantities, nor handle full progress accounts or final accounts.",
                "Take-off software: powerful but disconnected from invoicing and site monitoring.",
                "Construction ERPs: expensive and heavy, out of reach for firms of 1 to 20 people.",
                "ConstruPilot: the complete chain for trade contractors and SMEs, with AI where it is verifiable.",
                "Switching cost: the company's price library grows richer with every job.",
            ], None),
            ("7. Business model", [
                "Professional: €149 / month per company — the core of recurring revenue.",
                "Individual: €19 / month · API and integrations: €99 / month · add-ons from €5 / month.",
                "7-day trial, free launch phase in progress, Stripe payments.",
                "Recurring revenue per company with controlled marginal cost: AI is only called on unknown lines.",
                "Natural extensions: accounting integrations, distribution through material merchants, vendor API.",
            ], None),
        ],
        "slides_after": [
            ("Plan milestones", [
                "Months 1-6: Android and iOS apps published, first paying customers, industrialised schedule pricing.",
                "Months 7-12: controlled acquisition (SEO, field sales, merchant partnerships), accounting integrations.",
                "Months 13-18: sales team, regional roll-out, subcontracting modules.",
                "Months 19-24: API opening, distribution partnerships, preparation for international markets.",
                "These are working objectives: progress is published exactly as measured, with no reconstructed figures.",
            ], None),
            ("Risks and answers", [
                "Quality of AI-proposed prices → absolute priority to the company library, prices always editable and archived.",
                "Dependency on one AI vendor → three interchangeable vendors behind a single internal interface.",
                "Heterogeneous schedules → tolerant parsing (multi-sheet, variable headers) and line-by-line correction.",
                "Cost drift → uses of funds tracked by envelope in the back office, monthly reconciliation with acquisition channels.",
                "Compliance (GDPR, app stores) → legal pages, self-service account deletion, access logging.",
            ], None),
            ("What we are looking for", [
                "Market access: introductions to trade federations, contractor groups, material merchants and architecture practices.",
                "Commercial capacity: funding a field sales cycle and the related hires over the 24 months of the plan.",
                "Integration partnerships: accounting software, material distributors, plan platforms.",
                "Governance: quarterly reporting on exactly the measured indicators presented here.",
            ], None),
        ],
        "end": ("Contacto", f"{CONTACT} · {SITE} · Patent no. {PATENT}"),
        "note": "Real screenshot of the platform.",
    },
    "pt": {
        "cover": ("ConstruPilot — apresentação a investidores",
                  "Software vertical para a construção francesa: orçamentação do mapa de quantidades "
                  "do arquiteto, medições sobre planta e faturação por autos na mesma base",
                  "Documento de trabalho · confidencial · plano de exploração de 500 000 € em 24 meses"),
        "kpi_title": "Números medidos na base de dados",
        "kpi_cols": ["Indicador", "Valor"],
        "kpi_note": "Medido em {d} · janela de {w} dias · uma métrica não mensurável é apresentada como "
                    "« não mensurável »: nunca 0, nunca um número reconstituído.",
        "nomeasure": "não mensurável",
        "labels": ["Contas existentes (sem testes)", "Ativos em 30 dias", "Subscrições pagas ativas",
                   "Registos medidos (30 d)", "Taxa de ativação (30 d)",
                   "Empresas identificadas (SIRET)", "Orçamentos e faturas criados"],
        "funds_title": "Plano de exploração — 500 000 € em 24 meses",
        "slides_before": [
            ("1. O problema", [
                "As pequenas e médias empresas de construção continuam a trabalhar em folhas de cálculo: mapas do arquiteto orçamentados à mão, medições repetidas, orçamentos sem biblioteca de preços fiável.",
                "A margem perde-se nos esquecimentos administrativos: trabalhos exigidos no caderno de encargos nunca orçamentados, adiantamentos não deduzidos, autos mal calculados, retenções nunca reclamadas.",
                "As ferramentas existentes cobrem a gestão, ou a orçamentação, ou o acompanhamento de obra: a ligação entre as três continua a ser humana e, por isso, caro.",
                "Resultado: horas de escritório não faturáveis e margem que desaparece no fim da obra.",
            ], None),
            ("2. O produto: a cadeia completa", [
                "Um único registo do mapa do arquiteto até à conta final.",
                "Estimativa, medições sobre planta, orçamentação DPGF, orçamentos, obra, autos de medição, conta final, espaço do cliente.",
                "Web e aplicações nativas Android e iOS para utilização no terreno.",
                "Gestão interna integrada: origem dos registos, ativação, despesas por envelope.",
            ], "dashboard.png"),
            ("3. O núcleo técnico: orçamentação DPGF", [
                "Leitura multi-folha de vários mapas Excel e vários cadernos de encargos num mesmo estudo.",
                "Preços da biblioteca da empresa e depois IA para as linhas desconhecidas, com a origem de cada preço registada.",
                "Instruções em linguagem natural, margem por lote, alerta de margem baixa, deteção de trabalhos exigidos no caderno de encargos mas ausentes do mapa.",
                "Consultas a subempreiteiros por lote, resposta online sem conta, comparação de propostas.",
                "A tarefa mais longa da profissão passa de várias horas a alguns minutos: é a porta de entrada do produto.",
            ], "dpgf.png"),
            ("4. Onde a margem se recupera: a faturação", [
                "Adiantamento automático na assinatura, autos de medição, retenção de garantia, certificado de pagamento.",
                "O adiantamento efetivamente recebido é deduzido automaticamente — a fonte de erro mais frequente do setor.",
                "Conta final num clique: saldo, adiantamento restante, libertação da retenção.",
                "Um benefício que o próprio utilizador consegue quantificar: tesouraria recebida mais cedo, margem preservada.",
            ], "situations.png"),
            ("5. O mercado francês", [
                "450 000 empresas de construção com volume de negócios positivo, excluindo micro-empresas puras (FFB, 2025).",
                "Cerca de 95 % são estruturas artesanais: aproximadamente metade da atividade e dos efetivos assalariados.",
                "193 mil milhões de euros de volume de negócios da construção em 2025 (FFB).",
                "1 731 000 ativos, dos quais 1 234 000 assalariados e 407 000 artesãos independentes (FFB).",
                "19 959 criações de empresas na construção no 3.º trimestre de 2025, +4,6 % num ano (INSEE).",
                "Fontes: ffbatiment.fr/le-batiment-en-chiffres · nota de conjuntura CAPEB T4 2025 · INSEE.",
            ], None),
            ("6. Posicionamento concorrencial", [
                "Ferramentas de gestão (orçamentos/faturas): não orçamentam um DPGF nem tratam autos completos ou conta final.",
                "Software de medições: poderoso, mas desligado da faturação e do acompanhamento de obra.",
                "ERP de construção: caro e pesado, fora do alcance de estruturas de 1 a 20 pessoas.",
                "ConstruPilot: a cadeia completa para o artesão e a PME, com IA onde é verificável.",
                "Barreira à saída: a biblioteca de preços da empresa enriquece em cada obra.",
            ], None),
            ("7. Modelo de negócio", [
                "Profissional: 149 € / mês por empresa — núcleo da receita recorrente.",
                "Particular: 19 € / mês · API e integrações: 99 € / mês · opções a partir de 5 € / mês.",
                "Teste de 7 dias, fase de lançamento gratuita em curso, pagamentos por Stripe.",
                "Receita recorrente por empresa com custo marginal controlado: a IA só é chamada nas linhas desconhecidas.",
                "Extensões naturais: integrações contabilísticas, distribuição pelos armazenistas, API para editores.",
            ], None),
        ],
        "slides_after": [
            ("Marcos do plano", [
                "Meses 1-6: publicação das aplicações Android e iOS, primeiros clientes pagantes, industrialização da orçamentação DPGF.",
                "Meses 7-12: aquisição controlada (SEO, terreno, parcerias com armazenistas), integrações contabilísticas.",
                "Meses 13-18: equipa comercial, implantação regional, módulos de subcontratação.",
                "Meses 19-24: abertura da API, parcerias de distribuição, preparação da internacionalização.",
                "São objetivos de trabalho: o progresso é publicado tal como é medido, sem números reconstituídos.",
            ], None),
            ("Riscos e respostas", [
                "Qualidade dos preços propostos pela IA → prioridade absoluta à biblioteca da empresa, preços sempre editáveis e arquivados.",
                "Dependência de um fornecedor de IA → três fornecedores intercambiáveis atrás de uma mesma interface interna.",
                "Heterogeneidade dos mapas → leitura tolerante (multi-folha, cabeçalhos variáveis) e correção linha a linha.",
                "Desvio de custos → aplicações seguidas por envelope no back-office, reconciliação mensal com os canais de aquisição.",
                "Conformidade (RGPD, lojas) → páginas legais, eliminação autónoma da conta, registo de acessos.",
            ], None),
            ("O que procuramos", [
                "Acesso ao mercado: apresentações a federações, agrupamentos de artesãos, armazenistas e gabinetes de projeto.",
                "Capacidade comercial: financiar um ciclo de venda no terreno e as contratações associadas ao longo dos 24 meses do plano.",
                "Parcerias de integração: software de contabilidade, distribuidores de materiais, plataformas de plantas.",
                "Governação: reporte trimestral exatamente sobre os indicadores medidos aqui apresentados.",
            ], None),
        ],
        "end": ("Contacto", f"{CONTACT} · {SITE} · Patente n.º {PATENT}"),
        "note": "Captura de ecrã real da plataforma.",
    },
}


def _new():
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    return prs


def _blank(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.14))
    bar.fill.solid()
    bar.fill.fore_color.rgb = GREEN
    bar.line.fill.background()
    bar.shadow.inherit = False
    return s


def _para(box, text, size, color, bold=False, space=6):
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0] if (not tf.paragraphs[0].runs and not tf.paragraphs[0].text) \
        else tf.add_paragraph()
    run = p.add_run()
    run.text = text
    p.space_after = Pt(space)
    p.alignment = PP_ALIGN.LEFT
    f = run.font
    f.size, f.bold, f.color.rgb, f.name = Pt(size), bold, color, "Arial"
    return p


def _cover(prs, title, subtitle, footer):
    s = _blank(prs)
    box = s.shapes.add_textbox(Inches(0.9), Inches(2.2), Inches(11.5), Inches(3.2))
    box.text_frame.word_wrap = True
    _para(box, title, 46, DEEP, True, 14)
    _para(box, subtitle, 20, GREEN, True, 16)
    _para(box, footer, 13, GREY)
    return s


PREPARED = {"fr": "Preparado para", "en": "Prepared for", "pt": "Preparado para"}


def _logo_stream(branding: dict | None):
    raw = (branding or {}).get("logo_b64") or (branding or {}).get("photo_b64")
    if not raw:
        return None
    try:
        return io.BytesIO(base64.b64decode(raw.split(",", 1)[-1]))
    except Exception:  # noqa: BLE001 — un logo illisible ne bloque pas le deck
        return None


def _branded_cover(prs, lang, cover, branding, prospect):
    """Page de garde personnalisée : logo et coordonnées de l'entreprise, nom du prospect, date."""
    s = _cover(prs, *cover)
    logo = _logo_stream(branding)
    if logo:
        s.shapes.add_picture(logo, Inches(10.4), Inches(0.6), height=Inches(1.0))
    name = (branding or {}).get("company_name")
    infos = " · ".join(filter(None, [
        (branding or {}).get("contact_line"),
        " ".join(filter(None, [(branding or {}).get("postal"), (branding or {}).get("city")])),
        (branding or {}).get("company_email")]))
    if name or infos:
        hb = s.shapes.add_textbox(Inches(0.9), Inches(0.65), Inches(9.2), Inches(1.0))
        hb.text_frame.word_wrap = True
        if name:
            _para(hb, name, 18, DEEP, True, 4)
        if infos:
            _para(hb, infos, 11, GREY)
    today = date.today().strftime("%d/%m/%Y") if lang != "en" else date.today().isoformat()
    line = f"{PREPARED[lang]} {prospect} · {today}" if prospect else today
    pb = s.shapes.add_textbox(Inches(0.9), Inches(5.6), Inches(11.5), Inches(0.6))
    _para(pb, line, 16, DEEP, True)
    return s


def _content(prs, title, bullets, shot, note):
    s = _blank(prs)
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.42), Inches(12.1), Inches(0.9))
    tb.text_frame.word_wrap = True
    _para(tb, title, 27, DEEP, True)
    has_img = bool(shot) and os.path.exists(SHOTS + shot)
    width = Inches(6.1) if has_img else Inches(11.9)
    bb = s.shapes.add_textbox(Inches(0.7), Inches(1.5), width, Inches(5.2))
    bb.text_frame.word_wrap = True
    for b in bullets:
        _para(bb, "•  " + b, 13 if has_img else 15, DARK, False, 11)
    if has_img:
        s.shapes.add_picture(SHOTS + shot, Inches(7.1), Inches(1.6), width=Inches(5.6))
        nb = s.shapes.add_textbox(Inches(7.1), Inches(5.35), Inches(5.6), Inches(0.4))
        _para(nb, note, 10, GREY)
    return s


def _table(prs, title, rows, widths, note=None):
    s = _blank(prs)
    tb = s.shapes.add_textbox(Inches(0.6), Inches(0.42), Inches(12.1), Inches(0.9))
    _para(tb, title, 27, DEEP, True)
    shape = s.shapes.add_table(len(rows), len(rows[0]), Inches(0.7), Inches(1.5),
                               Inches(11.9), Inches(0.42) * len(rows))
    table = shape.table
    for i, w in enumerate(widths):
        table.columns[i].width = Inches(w)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = table.cell(r, c)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = DEEP if r == 0 else (WHITE if r % 2 else LIGHT)
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.RIGHT if c >= 2 and r > 0 else PP_ALIGN.LEFT
            f = p.runs[0].font if p.runs else p.font
            f.size = Pt(12)
            f.name = "Arial"
            f.bold = r == 0 or r == len(rows) - 1
            f.color.rgb = WHITE if r == 0 else DARK
    if note:
        nb = s.shapes.add_textbox(Inches(0.7), Inches(6.7), Inches(11.9), Inches(0.6))
        nb.text_frame.word_wrap = True
        _para(nb, note, 10.5, GREY)
    return s


def _save(prs) -> bytes:
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_client_pptx(lang: str = "pt", branding: dict | None = None,
                      prospect: str | None = None) -> bytes:
    t = CLIENT.get(lang) or CLIENT["fr"]
    lang = lang if lang in CLIENT else "pt"
    prs = _new()
    if branding or prospect:
        _branded_cover(prs, lang, t["cover"], branding, prospect)
    else:
        _cover(prs, *t["cover"])
    for title, bullets, shot in t["slides"]:
        _content(prs, title, bullets, shot, t["note"])
    _cover(prs, t["end"][0], t["end"][1], "")
    return _save(prs)


def _fmt(value, nomeasure: str, suffix: str = "") -> str:
    if value is None:
        return nomeasure
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value:,}".replace(",", " ") + suffix


def build_investor_pptx(lang: str = "pt", metrics: dict | None = None,
                        docs_count: int | None = None) -> bytes:
    t = INV.get(lang) or INV["fr"]
    prs = _new()
    _cover(prs, *t["cover"])
    for title, bullets, shot in t["slides_before"]:
        _content(prs, title, bullets, shot, t["note"])

    nm = t["nomeasure"]
    acc = (metrics or {}).get("accounts") or {}
    act = (metrics or {}).get("activity") or {}
    jou = (metrics or {}).get("journey") or {}
    values = [_fmt(acc.get("existing_excluding_tests"), nm),
              _fmt(act.get("active_users_window"), nm),
              _fmt(act.get("paying_customers"), nm),
              _fmt(jou.get("signups_window"), nm),
              _fmt(jou.get("activation_rate_pct"), nm, " %"),
              _fmt(acc.get("companies_with_siret"), nm),
              _fmt(docs_count, nm)]
    generated = ((metrics or {}).get("generated_at") or "")[:10] or date.today().isoformat()
    rows = [t["kpi_cols"]] + [[lab, val] for lab, val in zip(t["labels"], values)]
    _table(prs, t["kpi_title"], rows, [8.4, 3.5],
           t["kpi_note"].format(d=generated, w=(metrics or {}).get("window_days", 30)))

    _table(prs, t["funds_title"], FUNDS.get(lang) or FUNDS["fr"], [3.1, 5.3, 1.9, 1.6])
    for title, bullets, shot in t["slides_after"]:
        _content(prs, title, bullets, shot, t["note"])
    _cover(prs, t["end"][0], t["end"][1], "")
    return _save(prs)
