# Análise de `editeur-plans.zip` — Relatório

**Artefacto**: `73619d211acd3965_editeur-plans.zip` (183 KB)
**Localização temporária**: `/tmp/editeur-plans-analise/` (NÃO copiado para `/app`)
**Data**: 2026-02

---

## 1. Estrutura do ZIP

```
editeur-plans/
├── pages/
│   └── PlanTakeoff.jsx                  (7 544 linhas)
└── components/
    └── planTakeoff/                     (26 ficheiros)
        ├── CadImportInfo.jsx            🆕 NOVO (5 834 b)
        ├── CotesCheckPanel.jsx          🆕 NOVO (25 054 b)
        ├── GeometryReport.jsx           🆕 NOVO (19 012 b)
        ├── InteriorPanel.jsx            🆕 NOVO (12 210 b)
        ├── ReportIssue.jsx              🆕 NOVO (7 799 b)
        ├── Stair3D.jsx                  🆕 NOVO (6 107 b)
        ├── measureCursor.js             🆕 NOVO (460 b)
        ├── PlanCanvas.jsx               ✏️ MODIFICADO (37→45 kB)
        ├── ObjectPanel.jsx              ✏️ MODIFICADO (21→32 kB)
        ├── RoomEstimateDialog.jsx       ✏️ MODIFICADO (6→11 kB)
        ├── MultiPlanDialog.jsx          ✏️ MODIFICADO (9→11 kB)
        ├── Render3dDialog.jsx           ✏️ MODIFICADO
        ├── MeasureHelpDialog.jsx        ✏️ MODIFICADO
        ├── QuoteDialog.jsx              ✏️ MODIFICADO
        ├── Pc*.jsx (×7)                 ✏️ Pequenas diffs
        ├── EstimateDialog.jsx           ✓ IDÊNTICO
        ├── PcGantt.jsx                  ✓ IDÊNTICO
        └── (outros ...)
```

**Total LoC**: 13 715 linhas (vs ~8 000 actuais → +72%)
**Ficheiros**: 27 (26 componentes + 1 página)
**Deltas**:
- 🆕 **7 novos componentes** (não existem em `/app`)
- ✏️ **18 componentes modificados** (deltas variados, alguns muito pequenos)
- ✓ **2 componentes idênticos** aos actuais

---

## 2. Tecnologia + Deps

### Framework
- **React** com hooks (compatível React 18/19 — não força versão específica)
- **Bundler alvo**: CRA (usa `process.env.REACT_APP_BACKEND_URL` directo)
- **Alias**: `@/*` resolve para `src/*` (igual ao projecto actual)

### Dependências npm externas invocadas
| Pacote | Já em package.json? | Nota |
|---|---|---|
| `react`, `react-router-dom` | ✅ | — |
| `lucide-react` | ✅ 0.516.0 | — |
| `sonner` | ✅ 2.0.3 | — |
| `three` + `OrbitControls` | ✅ 0.170.0 | para `Stair3D.jsx` |
| **`jszip`** | ❌ **FALTA** | usado em `pages/PlanTakeoff.jsx` para empacotar export |

### Dependências internas invocadas — gap vs `/app`
| Import | Existe em `/app`? |
|---|---|
| `@/components/ui/*` (Button, Input, Dialog, Tabs, Select, …) | ✅ shadcn/ui |
| `@/components/BrandingDialog`, `MailboxDialog`, `ConfirmProvider`, `OuvrageComposeDialog`, `Interactive3D` | ✅ |
| `@/context/BillingContext`, `I18nContext` | ✅ |
| `@/lib/api` | ✅ |
| **`@/components/chantiers/ChantierContextBar`** + `useChantierContext` | ❌ **FALTA** (pasta `components/chantiers/` não existe) |
| **`@/lib/cotesJobs`** (`runCotesJob`, `pollCotesJob`) | ❌ **FALTA** |

---

## 3. Papel e features

É **uma versão expandida do módulo `PlanTakeoff` já existente**, não um novo projecto. Trata-se de:

> **Editor de plantas 2D com takeoff automático**, importação CAD (DWG/DXF via Autodesk APS + OCR), medição assistida, geração de orçamentos e integração com Plan de Charge (Chantiers).

### Capacidades principais detectadas (novas vs actual)
1. **CAD import avançado** (`CadImportInfo.jsx`): diagnósticos ricos (XRef não resolvido, blocos ilegíveis, transformações não suportadas), picker de unidade quando ambígua, suporte Autodesk/ODA/CloudConvert — **com i18n FR/PT/EN já traduzido**.
2. **Verificação de cotas** (`CotesCheckPanel.jsx` + `GeometryReport.jsx`): compara cotas lidas vs geometria reconstruída, categoriza anomalias (OK/warn/KO/ignorada/ND) e gera relatório PDF.
3. **Interior/periférico** (`InteriorPanel.jsx`): análise de cadeias de cotas periféricas (haut/bas/gauche/droite), referências `nu int.→nu ext.`, consistência global.
4. **Report de erros do utilizador** (`ReportIssue.jsx`): formulário para o pro assinalar incorrecções na análise → cria issue + arquiva versão (nova workflow de qualidade).
5. **Stair3D** (`Stair3D.jsx`): visualização 3D interactiva de escadas (OrbitControls) a partir do resultado do `calcular_escada` tool — **integração natural com Fase D do stair-engine**.
6. **Measure cursor pixel-perfect** (`measureCursor.js`): cursor independente do zoom.
7. **Novos endpoints backend referenciados** (ver secção Riscos).

### Endpoints `/api/*` referenciados pelo ZIP
```
/takeoffs/corps-etat/{catalog,custom,ouvrages,prefs,estimate,room-preset}
/takeoffs/multilevel/groups
/takeoffs/settings/beton-{defaults,presets}
/takeoffs/metre-multi-pdf
/takeoffs/metre-versions
/takeoffs/bulk-trash
/takeoffs/{plan_id}/cotes/issues
/documents/from-plans
/agents/plan
/agents/runs
/billing/credits-3d
/pc/settings
/estimation/masonry-config
```
→ **Muitos endpoints novos** cujo estado em `/app/backend` não foi verificado nesta análise (lista para auditoria se avançarmos).

---

## 4. Compatibilidade com stack ConstruPilot

| Aspecto | Veredicto |
|---|---|
| React 19 CRA | ✅ Compatível (sem versão hard-coded, sem JSX runtime específico) |
| Tailwind + shadcn/ui | ✅ Usa os mesmos componentes `ui/*` |
| Alias `@/*` | ✅ Igual |
| React Router | ✅ Usa `react-router-dom` |
| Bundler Vite/Next | ✅ Não — fica em CRA |
| i18n | ⚠️ **Parcial**: só `CadImportInfo` usa `useI18n` com PT; **outros ~11 componentes têm FR hardcoded** |
| Deps | ⚠️ Falta `jszip` (único novo) |
| Backend | ❌ **Pedaços grandes de API em falta** no backend actual |

---

## 5. Proposta de integração — 3 opções

### Opção A — Merge total (upgrade do módulo PlanTakeoff)
Substituir completamente `pages/PlanTakeoff.jsx` + 21 componentes + adicionar 7 novos.

**Prós**:
- Alinha com a versão mais recente do módulo (features de qualidade: report issues, geometry check, interior panel, Stair3D)
- Elimina divergência futura entre forks

**Contras / trabalho**:
- 13.7k LoC a importar vs 8k actuais → regressões possíveis em features actualmente em produção
- **11 componentes com FR hardcoded** → tradução PT-PT obrigatória (viola objectivo "100% PT-PT")
- Dependências backend em falta (`/takeoffs/corps-etat/*`, `/takeoffs/multilevel/*`, `/takeoffs/metre-*`, `/takeoffs/{id}/cotes/issues`, `/documents/from-plans`, `/agents/plan`, …) — pode haver 20+ endpoints a implementar
- Falta `@/components/chantiers/` + `@/lib/cotesJobs`
- Falta `jszip` em `package.json`

**Esforço estimado**: 2-3 sprints (incluindo backend + tradução + testes).

### Opção B — Merge selectivo (cherry-pick)
Importar apenas os **novos componentes isolados** sem substituir `PlanTakeoff.jsx` nem `PlanCanvas.jsx`:
- `Stair3D.jsx` → integra directamente no fluxo `stair-engine` (Fase D já completa)
- `measureCursor.js` → utility pura, drop-in
- `CadImportInfo.jsx` → já tem i18n PT, pode ser renderizado se os endpoints APS devolverem o shape esperado

**Prós**:
- Baixo risco, baixo acoplamento
- `Stair3D` é um valor imediato para a Fase D do stair-engine
- Zero necessidade de backend novo (ou mínima)

**Contras**:
- Perde-se o grosso do upgrade (quality check, interior panel, report issue)
- Divergência mantém-se — ciclo repetir-se-á

**Esforço**: 1-2 dias para `Stair3D` + `measureCursor`; +2-3 dias se incluirmos `CadImportInfo` (precisa testar com manifest APS actual).

### Opção C — Fork lateral (`EditorPlantas v2` numa rota paralela)
Criar rota `/plantas-pro-v2` com o módulo completo do ZIP, deixar `/plan` actual intacto. Toggle feature-flag.

**Prós**:
- Zero risco de regressão do módulo em produção
- Permite migrar utilizadores Pro gradualmente

**Contras**:
- Duplicação temporária de 13k LoC
- Backend tem de suportar os dois conjuntos de endpoints até cutover

**Esforço**: Médio (1-2 sprints) mas distribuído.

---

### 🎯 Recomendação

**Opção B** — cherry-pick inicial focado em `Stair3D.jsx` + `measureCursor.js`, com análise follow-up para `CadImportInfo.jsx`.

**Racional**:
1. Objectivo do projecto é **100% PT-PT**. Trazer 11 componentes com FR hardcoded sem traduzir contradiz esta diretiva (viola DoD actual).
2. Os endpoints backend novos exigidos pela Opção A são extensos e não foram validados — risco alto de 404 a toda a hora.
3. `Stair3D.jsx` oferece ROI imediato: a Fase D (stair-engine) já está entregue, falta-lhe só a visualização 3D interactiva — este componente resolve isso em ~6 kB.
4. `measureCursor.js` é um melhoramento UX puro, zero risco.
5. Para o restante (quality check, interior panel, report issue) → fazer **Opção C** depois, numa rota `/plantas-pro-v2` em feature-flag, com tradução PT-PT prévia obrigatória.

**Integração proposta Opção B (DRAFT — pendente aprovação)**:
1. `yarn add jszip` (necessário mesmo para B? — só se usarmos `pages/PlanTakeoff.jsx` do ZIP. Para B puro, **não**).
2. Copiar `Stair3D.jsx` para `/app/frontend/src/components/planTakeoff/`.
3. Copiar `measureCursor.js` para o mesmo sítio.
4. Integrar `<Stair3D result={stairResult} />` em `/app/frontend/src/pages/StairEngine.jsx` sob flag "Pré-visualização 3D".
5. Traduzir comentário FR em `Stair3D.jsx` ("Aperçu 3D interactif…") → PT-PT.
6. Smoke test: `yarn build` + abrir `/stair-engine`, executar cálculo, confirmar que renderer monta sem erros.

**Nenhuma rota `/plantas-pro-v2` nem alteração ao Nav** no âmbito desta Opção B.

---

## 6. Riscos e mitigação

| Risco | Severidade | Mitigação |
|---|---|---|
| FR hardcoded em 11 componentes | 🔴 Alta | Opção B evita; para A/C → tradução PT-PT prévia (estimativa 2-3 dias) |
| Backend com endpoints `/takeoffs/corps-etat/*`, `/takeoffs/multilevel/*`, `/documents/from-plans`, `/agents/plan`, … em falta | 🔴 Alta | Opção A exige auditoria completa + possível implementação. Opção B contorna. |
| Falta `@/components/chantiers/` + `@/lib/cotesJobs` | 🟠 Média | Opção A exige criação. Opção B irrelevante. |
| `jszip` em falta | 🟢 Baixa | `yarn add jszip` (~90 kB gzipped — aceitável para feature de export) |
| Regressão em utilizadores Pro actuais com `/plan` | 🔴 Alta | Opção A substitui código em produção — testing_agent obrigatório antes de merge |
| Impacto no bundle size (`PlanTakeoff.jsx` + `PlanCanvas.jsx` ambos crescem ~30-50%) | 🟠 Média | Code-splitting por rota já aplicado; validar com `yarn build` stats |
| Licença do ZIP | 🟢 Baixa | É mesmo autor/projecto (naming `planTakeoff/Pc*` ← Plan de Charge, consistente com ConstruPilot) |
| Integração com Agente BTP | 🟢 Baixa (oportunidade) | Tool `abrir_app` já suporta `/plan` → upgrade transparente se Opção A/C |
| Integração com Plans Pro (OCR + LLM) | 🟢 Baixa (oportunidade) | Opção A/C expõem `CotesCheckPanel` que consome output do pipeline Plans Pro |

### Scope de teste pós-integração (todas opções)
1. **Smoke**: abrir rota, importar PDF/DWG de teste, confirmar render.
2. **Takeoff**: fazer calibração + medir área, confirmar totais.
3. **Export**: gerar orçamento PDF a partir do canvas.
4. **Opção A/C especifico**: verificar que os endpoints novos devolvem 200 (não 404).
5. **Smoke stair-engine (Opção B)**: executar `calcular_escada`, confirmar que `<Stair3D>` monta sem erros WebGL.
6. `pytest tests/` sem regressões (296 passing baseline).

---

## 🛑 Fim da análise

Nenhum ficheiro foi copiado para `/app`. Nenhuma dependência foi instalada. `package.json` intacto. Aguardo decisão sobre A / B / C antes de qualquer alteração.
