# Pitch Deck v2 — proposta de slides (PT-PT · Web Summit 2026)

**Fase**: proposta de lista. **Zero slide gerado**. Pausa aqui até validação do fundador.

**Base**: deck v1 `backend/assets/investors/ConstruPilot_PitchDeck.pptx` (19 slides, 100 % FR). Dados numéricos extraídos **apenas** do deck v1; qualquer número não presente lá fica como `[a confirmar com fundador]`.

**Objectivo da v2**: investor deck PT-PT para Web Summit 2026, 12-14 slides (vs 19 na v1), história mais clara, menos redundância "detalhe por oferta".

---

## Estrutura proposta (14 slides)

| # | Título proposto (PT-PT) | 1 linha de conteúdo |
|---|-------------------------|--------------------|
| 1 | **ConstruPilot — Estimar. Comparar. Construir.** | Capa com logótipo + tagline PT-PT · `construpilot.pt` em destaque |
| 2 | **O problema** | Orçamentar obra em Portugal/França é lento, opaco e exige excel + telefone a 15 fornecedores — `[a confirmar: estatística de tempo médio ou % de orçamentos abandonados, fonte INE/BTP]` |
| 3 | **A solução** | SaaS BTP all-in-one: IA de leitura de plantas + metragem + orçamento + comparação + acompanhamento |
| 4 | **Demo em 60s** | Screenshot/animação da conta demo pro: Moradia Martins → "faz o estudo BET completo" → 3 entregáveis (PDF processo + ZIP DXF + XLSX orçamento) em <5s |
| 5 | **4 ofertas, 1 plataforma** | Grelha compacta: Particulares Grátis · Project Pass 50 € · Premium 19 €/mês · Pro 149 € HT/mês · Pro Business 249 € HT/mês (preços directos do deck v1) |
| 6 | **Diferenciador 1 — IA de leitura de plantas** | Cascata Claude Opus → OpenAI → Gemini; leitura de PDF/DWG até 50 MB em segundos; cálculo determinístico 100% pós-leitura (zero alucinação em números) |
| 7 | **Diferenciador 2 — Radar de obras & prospecção** | Alvarás oficiais PT (Sitadel) + FR em tempo real → leads qualificados para artesãos/PME |
| 8 | **Diferenciador 3 — Processo BET completo** | Único player a entregar PDF processo + DXF + XLSX com `PRÊT POUR VISA BET` em 1 clique |
| 9 | **Mercado** | PT + FR = `[a confirmar: tamanho TAM/SAM/SOM; fonte INE para PT, Insee para FR]` · taxa de digitalização BTP ainda `[a confirmar]` |
| 10 | **Tracção** | `[a confirmar: utilizadores registados, MRR, ARR, nº projectos processados — fonte dashboard interno/Stripe]` |
| 11 | **Modelo de negócio** | Receita recorrente (Premium + Pro + Pro Business) + one-shot (Project Pass) + comissão Radar (futuro) |
| 12 | **Equipa** | `[a confirmar: fundadores, backgrounds, LinkedIn — fonte LinkedIn pessoal/empresa]` |
| 13 | **O que estamos a construir** | Roadmap curto: factura electrónica CIUS-PT/UBL, melhorias ao CAD, cascata IA (feito), Web Summit demo (feito) |
| 14 | **Call to action** | `[a confirmar: valor da ronda, uso dos fundos, timeline]` · "venha ao stand XX" + QR code `construpilot.pt` + emails fundador |

---

## Números/dados que o fundador tem de validar

- **Slide 2**: estatística do problema (tempo médio para orçamento tradicional / taxa de abandono).
- **Slide 9**: tamanho de mercado PT + FR (TAM/SAM/SOM) + taxa de digitalização.
- **Slide 10**: utilizadores, MRR, ARR, projectos processados (fonte dashboard Stripe ou interno).
- **Slide 12**: equipa (nomes, fotos, bios curtas).
- **Slide 14**: montante da ronda, use of funds, timeline.
- **Slide 14**: stand Web Summit (número).

Qualquer número inserido tem de ter **fonte citada no rodapé do slide**.

---

## Design (zero slide gerado ainda)

- Fonte: Inter (já instalada em `backend/assets/fonts/`).
- Cores marca: `#F97316` (laranja) + `#0F172A` (slate) sobre fundo claro `#FAFAF9`.
- Logótipo oficial em cada slide (já no deck v1).
- Rodapé: `construpilot.pt` + nº slide + fonte dos dados.
- Legendas de screenshots em PT-PT.

## Diferenças vs deck v1

- Língua: 100% PT-PT (v1 = 100% FR).
- Compactação: 2 slides por oferta → 1 slide "4 ofertas, 1 plataforma" (slide 5).
- Novo: slide "demo em 60s" (slide 4) — hooks visuais directos para o pitch oral.
- Novo: slide "diferenciadores" explícito (slides 6-8), em vez de módulos transversais.
- Novo: slide "o que estamos a construir" (slide 13) — mostra momentum.
- Novo: slide "call to action" com QR code para Web Summit (slide 14).
- Suprimido: redundância "detalhe por oferta" (v1 slides 4, 6, 8, 10, 12 duplicavam a oferta anterior).

---

## Próximo passo

**Fundador valida esta lista** →
- Confirma estrutura 14 slides vs manter os 19 de v1.
- Confirma os números a inserir (fontes).
- Confirma stand Web Summit, ronda, equipa.

Só então gero `/app/backend/assets/investors/v2/ConstruPilot_PitchDeck_PT_v2.pptx` + PDF em paralelo.

**Zero geração até confirmação.**
