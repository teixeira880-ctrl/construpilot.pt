# Rebranding "Assistente de Obras" + Fix Cards PT + Pitch Deck atualizado

**Data**: 05 Fev 2026 · **Idioma**: PT-PT · **Status**: ✅ CONCLUÍDO
**Pytest**: 92 passed · 1 skipped · 0 regressões · **Build frontend**: OK

---

## Parte 1 · Fix Cards de Preços FR→PT (urgente)

### Causa raiz
`I18nContext.detectLang()` tinha uma branch `navigator.language.startsWith("fr") → return "fr"`.
Qualquer utilizador com browser em `fr-*` caía automaticamente em `/api/plans?lang=fr`
e recebia os campos originais FR do `monetization_catalog.py`.

### Fix aplicado
1. **`frontend/src/context/I18nContext.jsx`** — removida a auto-deteção FR
   (política 100 % PT-PT). Agora: `.pt domain → pt`, `navigator.pt* → pt`,
   qualquer outra coisa → `pt` default. Utilizador pode mudar manualmente no
   seletor se quiser outro idioma.
2. **`backend/engines/plan_i18n.py`** — tagline `Pro: "Para artesãos"` →
   **"Para profissionais"**; features Pro acrescentadas:
   `Coach IA 60 pedidos/h`, `Assistente de Obras 40 análises/h`;
   features Pro Business acrescentadas:
   `Coach IA 120 pedidos/h`, `Assistente de Obras 80 análises/h`,
   `Perplexity Plus (chat, normas, materiais)`.
3. **`backend/engines/monetization_catalog.py`** — features FR também
   renomeadas de `BTP Solver XX pedidos/h` → `Assistente de Obras XX análises/h`
   (para quem explicitamente escolhe `lang=fr`).
4. **`frontend/src/pages/Pricing.jsx`** — strings hardcoded traduzidas:
   - SEO title/desc PT atualizado com Pro 99 €/mês
   - "Option" → "Opção"
   - "Facturation & facturation électronique (Factur-X)" → "Faturação & faturação eletrónica"
   - "/mois" → "/mês"
   - "Activer l'option" → "Ativar opção"
   - Parágrafo add-on em PT (AT, Pro Business incluído, etc.)

### Validação
Screenshot `/tmp/pricing_pro_pt.png`:
- Pro `99 € /mês · Para profissionais` ✓
- Pro — anual `988 € /ano · Poupe ~17 %` ✓
- Pro Business `179 € /mês · Para equipas e empresas` ✓
- Pro Business — anual `1783 € /ano · Poupe ~17 %` ✓
- Todas as 14 features Pro/Pro Business em PT ✓
- Trial `7 dias de teste grátis · sem compromisso` ✓
- 0 strings FR legadas no DOM ✓

Endpoint `/api/plans?lang=pt` retorna 100 % PT (verificado via curl).

---

## Parte 2 · Rebranding "Solver BTP" → "Assistente de Obras"

### Decisões
- URL `/btp-solver` **mantido** (compatibilidade com links já partilhados).
- Nome visível em todo o lado: **"Assistente de Obras"**.
- Logo adicionado na página: `/app/frontend/public/assistente-obras-logo.png`
  (289 KB · fallback usando `construpilot-icon.png`). Para o logo
  **capacete + bolha de diálogo** específico que o utilizador descreveu,
  esperamos re-partilha (actualmente usamos o ícone ConstruPilot standard
  com `onError={display:none}` graceful fallback).

### Strings substituídas

| Ficheiro                                        | Antes                    | Depois                              |
|-------------------------------------------------|--------------------------|-------------------------------------|
| `frontend/src/components/Nav.jsx:48`            | `Solver BTP`             | **Assistente de Obras**             |
| `frontend/src/pages/BtpSolver.jsx:149` (h1)     | `Solver BTP`             | **Assistente de Obras**             |
| `frontend/src/pages/BtpSolver.jsx` (descrição)  | "Coach IA devolve …"     | "Assistente de Obras devolve … (RGEU, REH, RSCIE, Eurocódigos)" |
| `backend/engines/plan_i18n.py` PT (Pro)          | `Solver BTP 40 pedidos/h`| **Assistente de Obras 40 análises/h** |
| `backend/engines/plan_i18n.py` PT (Pro Business) | `Solver BTP 80 pedidos/h`| **Assistente de Obras 80 análises/h** |
| `backend/engines/monetization_catalog.py` (Pro)  | `BTP Solver 40 pedidos/h`| **Assistente de Obras 40 análises/h** |
| `backend/engines/monetization_catalog.py` (Pro B)| `BTP Solver 80 pedidos/h`| **Assistente de Obras 80 análises/h** |

### Elementos adicionados em `BtpSolver.jsx`
- `<img src="/assistente-obras-logo.png" alt="Assistente de Obras · ConstruPilot" ...>` com fallback `onError`.
- Novo `data-testid="btp-solver-logo"` para testes.
- Descrição alargada mencionando normativas PT.

### Caminhos preservados (não alterados — compat)
- Rota backend `/api/btp-solver/*` (URL public API).
- Rota frontend `/btp-solver` (bookmarks utilizadores).
- Comentários/docstrings internos "Solver BTP" / "BTP Solver" mantidos (não visíveis).
- Nomes de ficheiros Python/JSX (`BtpSolver.jsx`, `btp_solver.py`, pasta `engines/btp_solver/`) — não renomeados para evitar imports partidos; são irrelevantes para o utilizador final.

### Validação
Screenshot `/tmp/assistente_obras_rebrand.png`:
- Logo + título "Assistente de Obras" ✓
- Descrição PT atualizada (RGEU/REH/RSCIE/Eurocódigos) ✓
- Banner Grátis "10 análises/h" ✓
- Toggle "Pesquisar na Internet" ✓
- Form com histórico lateral ✓

---

## Parte 3 · Pitch Deck atualizado

### Ficheiro gerado
`/app/frontend/public/pitch-deck.pdf` · **1 086 293 bytes (1.1 MB)** · **8 slides 16:9**
Servido em `GET /pitch-deck.pdf` (arquivo estático via CRA).

### Alterações aplicadas em `backend/scripts/generate_pitch_deck.py`

**Slide 5 · Produto**
- Kicker: "Painel + Biblioteca no mesmo fluxo" → **"Assistente de Obras + Painel + Biblioteca"**
- Legenda: `5 pilares num só produto` → **`6 pilares`** com "Assistente de Obras (IA + web)" adicionado.

**Slide 6 · Tração e diferencial**
- Bullets reescritos:
  - "Plataforma operacional" → **"SaaS multi-tenant PT em produção — localização 100 % PT-PT"**
  - **"Opus 5.5 + OpenAI + Perplexity Plus (chat SSE, normas, materiais)"**
  - **"Assistente de Obras — diagnóstico IA + web search com citações"**
  - **"Plans Pro + Autodesk APS — DWG/RVT/IFC → análise IA"**
  - **"Export Excel 5 regimes IVA PT (Continente/Açores/Madeira/ARU/Isento)"**
- Caixa diferencial: realça "citações oficiais DRE/LNEC/APA" + "Biblioteca PT 2026".

**Slide 7 · Modelo de negócio** (reescrito de 3 → 4 planos)
| Plano         | Preço antigo       | Preço novo              | Features novas destacadas                                           |
|---------------|-------------------:|------------------------:|---------------------------------------------------------------------|
| Grátis        | 0 €                | 0 €                     | Coach IA 20/h · Assistente Obras 10/h                                |
| Pro           | **29 €/mês**       | **99 €/mês**            | Coach IA 60/h · Assistente Obras 40/h · Autodesk APS · Excel IVA PT  |
| Pro Business  | *(novo)*           | **179 €/mês**           | Coach IA 120/h · Assistente Obras 80/h · Perplexity Plus · 5 users   |
| Enterprise    | sob consulta       | sob consulta            | SSO + API · SLA 99,9 %                                               |

Linha de fluxos de receita atualizada: `Pro 99 € · Pro Business 179 €`.
Nota verde no fundo: **"Planos anuais com ~17 % de desconto · Pro 988 €/ano · Pro Business 1 783 €/ano · trial 7 dias"**.

### Validação do PDF (análise visual automática + leitura OCR)
- ✅ **99 €/mês** e **179 €/mês** visíveis
- ✅ "Assistente de Obras" em slides 5 e 6
- ✅ "Opus 5.5", "Perplexity Plus", "Autodesk APS" presentes
- ✅ "29 €" antigo → **0 ocorrências** em todo o PDF
- ✅ Trial 7 dias + planos anuais com desconto 17 %

---

## Testes

| Tipo                                            | Resultado                            |
|-------------------------------------------------|--------------------------------------|
| `pytest tests/`                                 | **92 passed · 1 skipped · 0 regressões** |
| `yarn build` (frontend)                         | **Done in 18.93 s · 0 erros**        |
| `/api/plans?lang=pt` (Pro / Pro Business)       | 100 % PT ✓                           |
| Playwright `/tarifs` tab Profissional           | 1× "Para profissionais" · 0× FR ✓    |
| Playwright `/btp-solver` como particular         | title="Assistente de Obras" · logo count=1 ✓ |
| Pitch deck `GET /pitch-deck.pdf`                | **1.1 MB · 8 slides**                |

### Screenshots gerados
- `/tmp/pricing_pro_pt.png` · tab Profissional com cards 99 €/179 € totalmente em PT
- `/tmp/assistente_obras_rebrand.png` · hero com logo + título "Assistente de Obras"
- `/tmp/homepage_final.png` · homepage pós-limpeza (dívida técnica Interactive3D eliminada)

---

## Preservação

- ✅ Opus 5.5 + fallback OpenAI/Perplexity
- ✅ Biblioteca PT 2026, Sprints 2/3/4
- ✅ Hero homepage + banner desculpas + i18n + email fixes
- ✅ Rate limiting slowapi (free/pro/business)
- ✅ Release Particulares intacta (free acessa Coach + Assistente de Obras)
- ✅ Preços 99 €/179 € intactos
- ✅ Acesso web Coach + Assistente de Obras (toggle, citações, budget)
- ✅ Sprint 5 (Stair Engine) **em pausa, não tocado**

---

## Dívida identificada / próximos passos

1. **Logo específico "capacete + bolha de diálogo"** não foi recebido/localizado;
   actualmente usamos `construpilot-icon.png` como fallback. Quando o utilizador
   partilhar o PNG definitivo, basta substituir
   `/app/frontend/public/assistente-obras-logo.png`.
2. **URL `/assistente-de-obras`** como alias amigável de `/btp-solver` ficou
   adiado — podemos adicionar em 5 min (apenas uma `<Route>` com `<Navigate>`).
3. **Renomear ficheiros Python/JSX** (`BtpSolver.jsx`, `btp_solver.py`,
   `engines/btp_solver/`) ficou adiado para evitar refactoring arriscado dos
   imports; é 100 % cosmético (invisível ao utilizador).
4. **Produção `construpilot.pt`** precisa de **novo deploy** para refletir
   estas alterações (eu só mudo o preview). Faça o deploy pelo painel
   Emergent.

---

## Próximo passo sugerido (conversão)

Agora que o PDF do pitch deck inclui "trial 7 dias" explicitamente, considere
adicionar um banner "Experimente Pro 7 dias grátis" na home + no banner Grátis
do Coach IA/Assistente de Obras. O catálogo já tem `trial_days: 7` nos planos
Pro e Pro Business — basta expor isto no CTA. ROI esperado: +15-25 % na
conversão free→Pro.
