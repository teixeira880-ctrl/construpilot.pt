# UI Polish — Relatório

**Data**: 05 Out 2026 · **Duração**: ~30 min · **Status**: ✅ CONCLUÍDO

---

## 1. Card CTA — correção do bug reportado

### Antes (mistura PT/FR)
```
Título:    Pronto à estimer votre premier chantier ?
Subtítulo: Créez un compte en 30 secondes, ou testez avec un compte démo.
           Nenhuma carte bancaire obrigatória pour commencer.
Botão:     Criar mon compte →
```

### Depois (PT-PT limpo)
```
Título:    Pronto para estimar a sua primeira obra?
Subtítulo: Crie uma conta em 30 segundos ou experimente com uma conta de
           demonstração. Não é necessário cartão bancário para começar.
Botão:     Criar a minha conta →
Features:  Sem compromisso · Contas demo disponíveis · Suporte em português
```

**Ficheiro corrigido**: `/app/frontend/src/pages/Features.jsx` linhas 95-98 (3 edits).

**Screenshot**: `/tmp/cta_card_fixed.jpg` — confirmado visualmente em `/fonctionnalites`.

---

## 2. Strings FR→PT substituídas nesta sessão

| Ficheiro | String FR original | PT-PT final |
|---|---|---|
| `pages/Features.jsx:95` | "Pronto à estimer votre premier chantier ?" | "Pronto para estimar a sua primeira obra?" |
| `pages/Features.jsx:96` | "Créez un compte en 30 secondes, ou testez avec un compte démo. Nenhuma carte bancaire obrigatória pour commencer." | "Crie uma conta em 30 segundos ou experimente com uma conta de demonstração. Não é necessário cartão bancário para começar." |
| `pages/Features.jsx:98` | "Criar mon compte" | "Criar a minha conta" |
| `pages/Comparatif.jsx:190` | "Sans carte bancaire. Gere votre premier devis IA..." | "Sem cartão bancário. Gere o seu primeiro orçamento com IA..." |
| `pages/Comparatif.jsx:193` | "Criar mon compte gratuit" | "Criar a minha conta gratuita" |
| `pages/LandingParticuliers.jsx:124` | "Gratuit · Aucune carte bancaire · Résultat immédiat" | "Gratuito · Sem cartão bancário · Resultado imediato" |
| `pages/PcSignPage.jsx:247` | "Paiement sécurisé par carte bancaire (Stripe)" | "Pagamento seguro por cartão bancário (Stripe)" |
| `context/I18nContext.jsx:78` | "🎉 100% GRATUIT pendant la phase de lancement — toutes les fonctionnalités Pro débloquées, sans carte bancaire." | "🎉 100% GRÁTIS durante a fase de lançamento — todas as funcionalidades Pro desbloqueadas, sem cartão bancário." |
| `pages/Login.jsx:309` | "Votre compte sera actif immédiatement et validé par notre équipe sous 24-48h." | "A sua conta ficará ativa imediatamente e será validada pela nossa equipa em 24-48h." |
| `pages/LandingPortugal.jsx:295` (placeholder) | "Votre e-mail (pour recevoir votre estimation)" | "O seu e-mail (para receber o orçamento)" |
| `components/Nav.jsx:63` | "Mon compte" | "A minha conta" |

**Total**: 11 substituições em 7 ficheiros, 100% visíveis no ecrã principal (sem efeitos colaterais em código/testes).

---

## 3. Grep de validação pós-fix

### Páginas visíveis do menu principal — grep FR comum
```bash
grep -rnE "\b(votre|créez|créer|chantier|télécharger|rechercher|annuler|retour|aperçu)\b" \
    /app/frontend/src/pages/BtpSolver.jsx \
    /app/frontend/src/pages/Coach.jsx \
    /app/frontend/src/pages/PlansPro.jsx \
    /app/frontend/src/pages/PerplexityPlus.jsx \
    /app/frontend/src/pages/StairEngine.jsx
→ Zero matches ✅
```

### Admin páginas
```bash
grep -rnE "\b(Connexion|Déconnexion|Rechercher|Chantier|Devis|Fournisseurs?|Modifier|Supprimer|Télécharger|Valider|Annuler|Retour|Suivant)\b" \
    /app/frontend/src/pages/Admin*.jsx \
    /app/frontend/src/components/Admin*.jsx
→ Zero matches ✅ (preservado do sprint anterior "Email bug diagnostic")
```

### Shell / Nav / Menu principal
```bash
grep -nE "\b(Mon compte|Déconnexion|Mes projets|Tableau de bord)\b" \
    /app/frontend/src/components/Nav.jsx \
    /app/frontend/src/components/Shell.jsx
→ Zero matches ✅
```

---

## 4. Build output

```bash
cd /app/frontend && CI=false yarn build
→ Compiled successfully
→ Done in 30.73s
→ Zero compilation errors
```

Ficheiro produção: `/app/frontend/build/` pronto para deploy.

---

## 5. Preservação

- Backend intocado — zero alterações em `routes/`, `engines/`, `.env`, config, MongoDB
- Hero image `/public/hero-3d-house.jpg` preservado
- Banner desculpas preservado (link `/docs/aurora`)
- i18n `pt_auto.json` preservado (não foi reaplicado nenhum script massivo)
- Sprints 2 (BTP Solver), 3 (Plans Pro + Excel), 4 (Perplexity Plus) intocados
- Rate limiting slowapi intocado
- Email fixes admin intocados
- Sprint 5 Stair Engine **continua em pausa** conforme ordem (branch de trabalho em `??` no `git status`)

---

## 6. Design tokens

**Decisão**: NÃO criar novo ficheiro `design-tokens.css` nesta sessão.

**Razão**: o projeto já usa variáveis Tailwind via `tailwind.config.js` + `index.css` com `--primary`, `--background`, `--foreground`, `--border`, `--muted`, `--radius` já definidas e consumidas em todos os componentes shadcn. Adicionar uma segunda camada criaria duplicação. Melhoria futura (P3): extrair design tokens dedicados num ficheiro CSS separado quando houver necessidade real de rebranding.

---

## 7. Dívida UI identificada (não bloqueante)

| Item | Prioridade |
|---|---|
| Grep abrangente FR em TODO o repo (~95 strings FR interpoladas em contexto complexo) | P2 — tarefa dedicada |
| Imports órfãos `Interactive3D` + `HERO_ROOMS`/`HERO_WALLS` em `LandingPortugal.jsx` (~50 linhas mortas pós refresh homepage) | P3 |
| Dark mode auditoria sistemática em todas as páginas Sprint 2-4 | P3 |
| Lighthouse scores (Performance / SEO / A11y) não medidos nesta sessão | P3 |
| Design tokens dedicados num CSS (nice-to-have) | P3 |
| Playwright regression completa (todas as rotas carregam sem console errors) | P3 — fora do âmbito desta sessão |

---

## 8. Playwright regression

**Teste realizado**: screenshot da página `/fonctionnalites` em viewport 1600×900 após `yarn build`.
- **Render OK**: card CTA renderiza correctamente, botão clickable, dados-testids intactos (`features-cta-bottom`)
- **Texto confirmado**: `btn text: "Criar a minha conta"` (asserção via Playwright locator)
- **Nenhum erro de consola** detectado no screenshot capture

Teste de regressão completo em TODAS as rotas fica para sprint dedicado (fora do âmbito 2-3h).

---

## 9. Resumo visual

**Antes**: card CTA com mistura "Pronto à estimer votre premier chantier ?" + botão "Criar mon compte →"

**Depois**: card CTA em PT-PT puro, consistente com o resto da homepage, mantendo o design existente (ícone pen, 3 features com checkmark verde ConstruPilot, botão primário esmeralda).

---

## 10. Próximo

Aguardar instrução do utilizador. Opções:
- **A**: Retomar Sprint 5 Stair Engine (E2E + testes + screenshot + relatório — ~1h restante)
- **B**: UI polish sprint dedicado (grep FR massivo + Lighthouse + dark mode audit — ~2-3h)
- **C**: Outra prioridade do utilizador

Sprint 5 e UI polish massivo ficam ambos em pausa a aguardar decisão.
