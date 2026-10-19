# Pitch Deck v2 — relatório de preview

**Estado**: ✅ **PPTX + PDF gerados, previews prontos — aguarda validação do fundador antes de qualquer uso externo**.

## Entregáveis

| Ficheiro | Caminho | Tamanho | SHA-256 |
|--|--|--|--|
| PPTX | `/app/backend/assets/investors/v2/ConstruPilot_PitchDeck_v2.pptx` | 47.5 KB | `99c90038c509fd55e609ea0bbf2ac7a41f71d33b01ba232bfd5b798385115c83` |
| PDF | `/app/backend/assets/investors/v2/ConstruPilot_PitchDeck_v2.pdf` | 57.4 KB | `101773b95488ef9135ec8aeadd4b2ef3ae3827cd15b52ff8833716eba947edf0` |
| Manifest | `/app/backend/assets/investors/v2/manifest_v2.json` | 4.4 KB | — |
| 14 PNG previews | `/app/memory/pitch_deck_v2/previews/slide-01…14.png` | 435 KB total | — |

## 14 slides

1. **ConstruPilot — Estimar. Comparar. Construir.** · Capa
2. **O problema** · 🟡 placeholder: estatística tempo/abandono (fonte INE/BTP)
3. **A solução** · SaaS BTP all-in-one
4. **Demo em 60 segundos** · Demo pro Moradia Martins → 3 entregáveis <5s
5. **4 ofertas, 1 plataforma** · Preços directos do deck v1 (zero inventado)
6. **Diferenciador 1 — IA de leitura de plantas** · Cascata Claude→OpenAI→Gemini
7. **Diferenciador 2 — Radar de obras** · Alvarás oficiais PT/FR
8. **Diferenciador 3 — Processo BET completo** · PDF+DXF+XLSX "PRÊT POUR VISA BET"
9. **Mercado** · 🟡 placeholder: TAM/SAM/SOM + digitalização BTP (fonte INE/Insee)
10. **Tracção** · 🟡 placeholder: utilizadores, MRR, ARR (fonte Stripe/interno)
11. **Modelo de negócio** · Recorrente + one-shot + comissão Radar
12. **Equipa** · 🟡 placeholder: nomes, backgrounds, LinkedIn
13. **O que estamos a construir** · Roadmap curto
14. **Juntem-se a nós** · 🟡 placeholder: ronda, stand Web Summit

**5 placeholders** `[a confirmar com fundador — <hint>]` destacados em caixa amarelo `#FEF3C7` com borda laranja `#F97316`, texto bold slate `#0F172A`. Impossível passar despercebido numa apresentação.

## Design

- Formato: 16:9 widescreen (13.333" × 7.5").
- Fonte: declarada "Inter" no PPTX (fallback automático pelo PowerPoint/LibreOffice); DejaVu usada no PDF ReportLab (fallback universal, equivalente visual neutro).
- Cores: `#F97316` (laranja marca) + `#0F172A` (slate) sobre fundo claro `#FAFAF9`.
- Elementos: barra lateral laranja esquerda · nº slide canto superior direito · rodapé "pré-rascunho v2, confidencial, não distribuir · construpilot.pt".
- Zero logo (deck v1 tem logo embutido; aqui mantemos minimalista para rascunho).

## Fontes de dados (zero inventado)

| Slide | Dados | Fonte |
|--|--|--|
| 5 | Preços €50/€19/€149/€249 | Deck v1 `ConstruPilot_PitchDeck.pptx` — extraídos directamente |
| 11 | Mix recorrente + one-shot | Estrutura comercial actual |
| 13 | Roadmap | Estado actual do repositório `construpilot.pt` |

Qualquer outro número → ainda não existe no deck v1 nem no repositório → fica como placeholder destacado.

## Previews visuais

14 PNG em `/app/memory/pitch_deck_v2/previews/`. Exemplo slide 2 (com placeholder destacado) renderizado correctamente — caixa amarela com borda laranja visível. Design limpo e profissional.

## Verificações

- **Idempotência**: re-correr `build_pitch_deck_v2.py` + `build_pitch_deck_v2_pdf.py` com mesmo input gera **mesmo SHA-256** (ordem de slides e conteúdo fixos; apenas timestamp no manifest varia).
- **14 páginas**: confirmado via `pypdfium2` leitura `len(PdfDocument(...))` = 14.
- **Zero rota pública**: `routes/investors.py` continua a servir só o deck v1. **Zero `/api/investors/pitch-deck/v2` adicionado**.

## Próximo passo

**Fundador abre o PDF em `/app/backend/assets/investors/v2/ConstruPilot_PitchDeck_v2.pdf`** (ou os PNG em `/app/memory/pitch_deck_v2/previews/`) e valida:

1. Estrutura 14 slides OK?
2. Textos PT-PT correctos?
3. Preços no slide 5 correctos (vêm do deck v1)?
4. Preenche os 5 placeholders com fontes citadas OU confirma que ficam destacados até ao Web Summit?
5. Autoriza substituir deck v1 em `routes/investors.py` por este v2 em deploy futuro OU deixa coexistir ambos?

**Zero acção adicional da minha parte até feedback.** Zero rota pública ligada. Zero deploy.
