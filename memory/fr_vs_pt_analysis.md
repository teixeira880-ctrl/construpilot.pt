# FR vs PT · Análise comparativa

**Data**: 2026-02-04
**Fonte FR**: `/tmp/construpilot_fr/construpilot.fr-main/` (snapshot 2026-08-26, extraído do zip de 29.3 MB enviado pelo utilizador)
**Fonte PT**: `/app/` (actual, após migração AI Claude Opus 5.5 e remoção Aurora)

---

## 🎯 Sumário executivo (TL;DR)

1. **O FR é SIGNIFICATIVAMENTE MENOS desenvolvido que o `/app`** nesta cópia. É um **snapshot de 2026-08-26** (há 5+ meses), de onde o PT partiu e evoluiu muito.
   - FR: 137 .py backend + 147 .jsx frontend · 35 219 + 28 259 linhas · 494 ficheiros total · 33 MB
   - PT: 146 .py backend + 207 .jsx frontend · **41 207 + 42 760 linhas** · ~ 2× mais ficheiros em componentes · 24 páginas únicas · 25 routes únicas · 26 engines únicos

2. **Features MAIS valiosas que o FR tem e o PT NÃO tem**: **zero** (nenhum engine, nenhuma rota, nenhuma página significativa). Única "ausência" formal em PT: `Landing.jsx` (versão francesa — PT já tem `LandingPortugal.jsx` + `LandingParticuliers.jsx` em seu lugar).

3. **Conflitos com trabalho recente**:
   - FR usa `emergentintegrations` (abandonado por nós) + modelo `claude-sonnet-4-6` (mais antigo que `claude-opus-5-5`).
   - FR **não tem**: `ai_providers/` (router Claude/OpenAI/Perplexity), `coach_ai.py`, `ai_health.py`, `ServiceApologyBanner.jsx`, biblioteca PT 2026 (322 items), master spec Aurora, Opus 5.5, documentação limpa pós-Aurora.
   - Trazer código FR **destruiria** todo esse trabalho recente.

4. **Estratégia recomendada**: **D — Manter PT, usar FR só como arquivo de referência**. Não há merge inverso que faça sentido. Se o utilizador quer paridade "FR = PT em features", **o alvo já está ultrapassado**: o PT ultrapassou o FR em ~5 meses de desenvolvimento.

5. **Esforço estimado**: 
   - **Para trazer código do FR → 0 h recomendado** (regressão garantida).
   - **Para traduzir strings FR remanescentes em `/app`** (se o utilizador quiser higienizar FR→PT em docstrings/comentários): ~ 2-4 h · 1 iteração.
   - Alternativa: continuar o desenvolvimento normal do PT. O FR serve como histórico.

6. **⚠ Risco de segurança no zip FR**: três ficheiros `.adm_token.txt`, `.pro_token.txt`, `.token.txt` (141 bytes cada) no root do FR — contêm tokens de sessão em texto plano. **Não devem ser copiados para `/app`**. Devem ser apagados do zip de arquivo.

---

## Secção 1 — Inventário factual do FR

### 1.1 Metadata
| Métrica | Valor |
|---|---|
| Fonte | zip 29.3 MB (`2u0oooxi_construpilot.fr-main.zip`) |
| Snapshot date | **2026-08-26 12:37** (mtime uniforme = export do zip, não repo git) |
| `.git` metadata | **ausente** (não é um clone, é um export) |
| Nº ficheiros | 494 |
| Tamanho total | 33 MB |
| `README.md` | 1 linha: `# Here are your Instructions` (vazio) |
| Backend lang | Python / FastAPI (uvicorn) |
| Frontend | React 19 (CRA 5), Tailwind, Radix UI |

### 1.2 Estrutura top-level
```
/tmp/construpilot_fr/construpilot.fr-main/
├── backend/
│   ├── core/           # db.py, security.py
│   ├── engines/        # 34 ficheiros
│   ├── routes/         # 33 ficheiros
│   ├── tests/          # 66 ficheiros (iter2 → iter85)
│   ├── video_cache/    # cache binário
│   ├── server.py
│   ├── requirements.txt  (148 linhas)
│   └── pytest.ini
├── frontend/
│   ├── src/
│   │   ├── pages/      # 48 páginas
│   │   ├── components/ # 95 componentes
│   │   ├── context/, hooks/, lib/, constants/
│   │   ├── App.js, App.css, index.js, index.css
│   │   └── plugins/health-check/
│   └── package.json    (59 deps + 15 devDeps)
├── memory/             # (vazio ou mínimo)
├── test_reports/pytest/
├── tests/              # (vazio ou mínimo)
├── .emergent/
├── design_guidelines.json
├── SECURITY.md
├── before.png, after.png, branded.pdf, test_metre.pdf
├── auth_testing.md
├── test_result.md
├── .adm_token.txt, .pro_token.txt, .token.txt    ⚠ TOKENS EM TEXTO PLANO
└── .gitignore, .gitconfig
```

### 1.3 Dependências — backend
Top 20 do FR `requirements.txt` (148 linhas; PT tem 163):
`aiohttp 3.14.3`, `anyio 4.14.2`, `APScheduler 3.11.3`, `bcrypt 4.1.3`, `boto3 1.43.67`, `cryptography 50.0.0`, `email-validator 2.3.0`, **`emergentintegrations 0.2.0`**, `ezdxf 1.4.4`, `fastapi 0.110.1`, `fastuuid 0.14.0`, `google-genai 2.17.0`, `fonttools 4.63.0`, `botocore 1.43.68`, `cffi 2.1.1`, …

**Diferenças chave vs PT**:
- FR **tem** `emergentintegrations==0.2.0` → PT **removeu** (migrou para SDKs nativos `anthropic` + `openai`).
- PT **tem** `anthropic` e `openai` (SDKs oficiais) · `weasyprint` · `markdown` → FR **não tem**.
- Resto da base é idêntica.

### 1.4 Dependências — frontend
FR tem **59 deps** no `package.json`. **PT tem exactamente as mesmas** (confirmado por `diff` sem output). Scripts idênticos: `start`, `build`, `test`. Toda a árvore Radix UI (`@radix-ui/react-*`), `react-hook-form`, `@hookform/resolvers`, `@phosphor-icons/react`, Tailwind. Zero divergência.

### 1.5 Backend — rotas FR
`server.py` monta **27 routers**: `auth, estimation_routes, tools, prices, projects, ai_routes, leads, admin, photos, billing, revenue, phase4-7, share, admin_revenue, plans, tool_presets, referrals, clients, library, documents, reviews, errors, emails, hr, ads`.

Páginas totais na API: ~340 endpoints (estimado por grep `@router`).

Todas estas rotas **já existem em PT**. Adicionalmente, PT tem **25 rotas únicas**:
`ai_health, appro, autoseo, branding_public, coach, company, company_library, docs, dpgf, einvoicing, evolution, help, investors, notifications, param_library, resend_webhook, roofing, runway_render, shared_library, site, situations, steel, suppliers, vrd, waterproofing`.

### 1.6 Backend — engines FR
34 engines. **Todos presentes em PT**. PT tem adicionalmente **26 engines únicos** (ver secção 2).

### 1.7 Backend — `.env` / `.env.example`
**FR não contém** nenhum ficheiro `.env` ou `.env.example` no zip. (Snapshot limpo.)

### 1.8 Frontend — rotas (React Router)
52 rotas em `App.js` do FR, todas em **francês URL**:
`/smart-project, /estimation, /calculateurs, /prix, /diy, /coach, /photo, /tarifs, /blog, /devis-travaux-:city, /parrainage, /inviter, /equipe, /devis, /factures, /rh, /pointage, /mes-avis, /clients, /bibliotheque, /devis-editeur, /scanner-devis, /etudes-pc, /compte, /pc, /plan, /plan/compare, /marketplace, /pro, /developpeurs, /docs, /enterprise, /fournisseur, /dashboard, /projet/:id, /admin`, mais rotas públicas de assinatura/partilha.

Todas as rotas estão **traduzidas para PT em `/app`** (ou pelo menos aliasadas; `App.js` do PT tem mais rotas).

### 1.9 Integrações 3rd party FR (grep hits em backend)
| Serviço | Ocorrências |
|---|---|
| `anthropic` | 1 (via emergentintegrations) |
| `claude` | 1 (string em `ai.py`) |
| `openai` | 2 |
| `perplexity` | **0** (FR não usa Perplexity) |
| `aurora` | **0** (FR nunca teve Aurora) |
| `stripe` | 13 |
| `resend` | 14 |
| `cloudconvert` | 2 |
| `twilio` | 9 |
| `tavily` | 1 |
| `emergentintegrations` | 4 |

**Nota crítica**: FR usa `emergentintegrations` como wrapper único para LLM. Define apenas: `claude-sonnet-4-6` (texto) + `gpt-5.5` (visão) + `claude-opus-4-8` opcional. **FR não tem Perplexity nem fallback multi-provider.**

### 1.10 Tests FR
66 ficheiros `test_iterN_*.py` (de iter2 a iter85) + `backend_test.py` + `_iter63_setup.py` + `creds.py`. Suite legacy pre-refactor — provavelmente desactualizada vs schema actual.

PT tem **4 ficheiros**: `__init__.py`, `conftest.py`, `test_c2_wave.py`, `test_c3_wave.py` (26 passed + 1 skipped após o fix de password).

### 1.11 ⚠ Riscos de segurança detectados no FR
- `.adm_token.txt` · 141 bytes · token admin em texto plano
- `.pro_token.txt` · 141 bytes · token pro em texto plano
- `.token.txt` · 141 bytes · token genérico em texto plano
- `.gitconfig` versionado · 61 bytes

**Nenhum destes ficheiros deve ser copiado para `/app`.** O utilizador deve apagá-los do arquivo zip ou invalidar os tokens.

---

## Secção 2 — Inventário factual do `/app` (actual)

### 2.1 Features críticas de preservar (confirmadas)
- `backend/engines/ai_providers/` (Claude Opus 5.5 + OpenAI gpt-4o + Perplexity sonar) — **router multi-provider com fallback automático**
- `backend/engines/coach_ai.py` — Coach IA actual
- `backend/routes/ai_health.py` — `GET /api/admin/ai-health`
- `backend/routes/docs.py` — serve `/api/docs/aurora-master-spec.{md,pdf}`
- `backend/scripts/build_aurora_pdf.py` — gerador do PDF (52 páginas)
- `docs/aurora_master_spec.{md,pdf}` — documentação técnica histórica (manter como referência)
- `frontend/src/components/ServiceApologyBanner.jsx` — banner com dismiss persistente
- `memory/aurora_upstream_bug.md` — histórico documental
- Biblioteca PT 2026: 322 items (`scripts/import_biblioteca_pt_2026.py`)

### 2.2 Engines únicos em PT (não existem em FR)
26 engines:
`activity, ai_providers/*, coach_ai, dwg_convert, dxf_extractor, dxf_takeoff, evolution, facturx_converter, facturx_validator, library_import, mailbox_smtp, order_pdf, param_import, pdf_pitch, plan_annot_pdf, plan_structure, price_library, pricing, pro_receipt, quote_receipt, rebar, roofing, situation_pdf, sms_provider, vrd, waterproofing`.

### 2.3 Routes únicas em PT (25)
`ai_health, appro, autoseo, branding_public, coach, company, company_library, docs, dpgf, einvoicing, evolution, help, investors, notifications, param_library, resend_webhook, roofing, runway_render, shared_library, site, situations, steel, suppliers, vrd, waterproofing`.

### 2.4 Páginas únicas em PT (23 vs 1 FR)
`AdminSecrets, Comparatif, EInvoicing, Entreprise, Features, Investors, LandingParticuliers, LandingPortugal, LegalPages, MyLeads, NotFound, PhotoMeasure, PriceCatalog, ProUpsell, ProVerified, RenderShare, RenderStudio, SiteTracking, Situations, TechAnalysis, VerifyEmail, Welcome, _Landing.fr.jsx.bak`.

### 2.5 Collections MongoDB críticas
`coach_messages, coach_failures, plan_analyses, shared_library_items, projects, users, auth_sessions, library_items, prices_catalog, prices_history, …`.

### 2.6 Bugfixes aplicados nesta sessão
- `test_c2_wave.py` password `Ruquinha2020.` → `uFuBb6Q5h1QUxCmc`
- `claude_provider.py` suporte Opus 5.5 (`output_config.effort`, auto-retry temperature deprecated)
- Remoção Aurora: 11 ficheiros, 283 linhas em `admin.py`, hooks em `projects.py`+`server.py`
- Env limpo (`AURORA_*` removidas) + whitelist actualizada

---

## Secção 3 — Matriz comparativa por área funcional

| Área | FR tem | PT tem | Recomendação |
|---|---|---|---|
| **Auth** | login, Google, reset, 2FA | **idem + KYC pro, verify-email, change-password, device mgmt, logout-others** | KEEP_PT |
| **Projects** | CRUD, expenses, budget, PDF, timeline | **idem + Aurora sync removido, hooks limpos** | KEEP_PT |
| **Estimates** | compute, catalog, analyse (Smart Project), PDF, PDF email, materials | idem (idêntico em features) | IDENTICAL (talvez pequenas melhorias UI do FR a avaliar) |
| **Invoices** | tracking básico (199 linhas) | **tracking + E-Invoicing + Facturx + tracking em 366 linhas** | KEEP_PT |
| **Coach IA** | `emergentintegrations` + Claude Sonnet 4.6 (sem fallback) | **Claude Opus 5.5 + OpenAI fallback + Perplexity web search + email alerts** | **KEEP_PT** (temos Opus 5.5) |
| **Plan analysis** | `plan_ai.py` (OpenAI vision via emergent) | **plan_ai.py + plan_structure + plan_annot_pdf + dwg_convert + CloudConvert** | KEEP_PT |
| **Pricing/Catalogue** | search, suppliers, catalog upload | **idem + biblioteca PT 2026 (322 items) + price_library + param_library + price_catalog** | **KEEP_PT** (biblioteca única) |
| **PC (Permis de Construire)** | `pc_study, pc_weather, pc_export` | idem + `situations.py` + `situation_pdf.py` extras | KEEP_PT |
| **HR** | `/rh` module | idem · 365 linhas lado a lado | IDENTICAL |
| **DIY** | `/diy` básico | idem | IDENTICAL |
| **Marketing pages** | 1 Landing | **LandingPortugal + LandingParticuliers + Entreprise + Features + Comparatif + Investors + Welcome** | KEEP_PT |
| **Materials library** | `library` básico | **library + company_library + shared_library + param_library + price_library + 322 items PT** | **KEEP_PT** (biblioteca única) |
| **Admin** | 1188 linhas | **1465 linhas** (ai-health, secrets protegidos, ai-usage, ai-budget) | KEEP_PT |
| **Dashboard** | 259 linhas | **371 linhas** | KEEP_PT |
| **PlanTakeoff** | 3341 linhas | **4900 linhas** | KEEP_PT |
| **QuoteEditor** | 350 linhas | **1240 linhas** | KEEP_PT |
| **i18n** | `landingI18n.js` (FR único) | `landingI18n.js` (idêntico + traduções PT) | IDENTICAL |
| **AI Health endpoint** | — | **`GET /api/admin/ai-health`** | KEEP_PT |
| **Documentação Aurora** | — | Master spec 52 páginas + PDF endpoint | KEEP_PT |
| **Apology Banner** | — | `ServiceApologyBanner.jsx` com dismiss persistente | KEEP_PT |
| **Multi-provider AI router** | — | `ai_providers/` com Claude/OpenAI/Perplexity | KEEP_PT |
| **Steel / VRD / Roofing / Waterproofing** | — | engines + routes dedicados | KEEP_PT |
| **Verified pro / Pro upsell / Pro portal** | ProPortal 1 | ProPortal + ProUpsell + ProVerified + MyLeads | KEEP_PT |
| **Tests** | 66 ficheiros (iter legacy) | 4 ficheiros (actual) | MERGE opcional (reativar os relevantes do FR seria tarefa dedicada) |

**Nenhuma linha é TAKE_FR ou MERGE a nosso favor.** O FR só tem valor como arquivo histórico de testes.

---

## Secção 4 — Classificação do idioma do FR

### 4.1 Idioma do UI
**100 % francês.** Amostra de strings extraídas de `Landing.jsx` do FR:
```
"Je décris mon projet"
"Le moteur calcule"
"Je trouve les meilleurs prix"
"Calculateurs pros"
"Comparateur de prix"
"Estimation par photo"
"Scanner de devis"
"Particuliers / Architectes"
"Pour les particuliers"
"Estimer mes travaux"
"Chiffrez et éditez"
"Je suis un particulier / Je suis un pro"
```

Rotas URL em francês: `/calculateurs, /prix, /devis, /factures, /rh, /pointage, /bibliotheque, /scanner-devis, /parrainage, /inviter, /equipe, /tarifs, /compte, /developpeurs, /fournisseur, /projet/:id`.

### 4.2 Volume estimado de strings
Se o utilizador quisesse adoptar o FR como base:
- ~ 48 páginas × ~ 60 strings UI/página = **~ 2 880 strings de UI** a traduzir
- ~ 95 componentes × ~ 20 strings = **~ 1 900 strings componentes**
- Prompts de sistema BTP em `engines/ai.py, pc_study.py, plan_ai.py` = **~ 50 blocos longos de prompt**
- Email templates (`email_i18n.py`) = **~ 30 templates**
- Mensagens de erro = **~ 200 strings**

**Total: ~ 5 000 strings a traduzir FR → PT**. Mas isto é **irrelevante** porque o `/app` já está em PT (como se vê pelas páginas únicas `LandingPortugal.jsx`, `LandingParticuliers.jsx`, `Welcome.jsx`, etc.).

### 4.3 Strings FR residuais em `/app`
Verificação rápida (fora do âmbito desta análise, mas sinalização): há comentários em docstrings de `routes/auth.py`, `admin.py` e alguns engines ainda em francês ou mistos ("Envoie un lien", "Dépôt des documents pro"). **Esta é a única área onde "traduzir FR→PT" faria sentido** — mas apenas comentários/docstrings, não UI.

---

## Secção 5 — Conflitos directos com trabalho recente

| Alteração recente em `/app` | Conflito se trouxermos FR? |
|---|---|
| Opus 5.5 (`claude-opus-5-5`) + `output_config.effort` | **SIM** — FR usa `claude-sonnet-4-6` via `emergentintegrations` |
| Router multi-provider com Perplexity | **SIM** — FR não tem Perplexity nem fallback |
| Remoção Aurora (11 ficheiros, 283 linhas) | **NÃO** — FR nunca teve Aurora |
| `ServiceApologyBanner` | **SIM** se o utilizador trouxer `LandingPortugal.jsx` do zip — não existe |
| Biblioteca PT 2026 (322 items) | **SIM** — FR não tem |
| Master spec Aurora PDF | **NÃO** — já é só histórico |
| Tests actualizados (`test_c2_wave`, `test_c3_wave`) | **SIM** — FR tem suite legacy que falharia |
| Páginas únicas PT (23) | **SIM** — perda garantida |
| Routes únicas PT (25) | **SIM** — perda garantida |

**Conclusão**: trazer código do FR causa regressão em pelo menos **7 áreas** críticas. Não há caminho de merge seguro.

---

## Secção 6 — Estratégia recomendada

### Opção A — Replace total `/app` ← FR
**NÃO RECOMENDADO.** Perde-se:
- Router AI Claude Opus 5.5 + OpenAI + Perplexity
- 23 páginas únicas, 25 routes únicas, 26 engines únicos
- Biblioteca PT 2026 (322 items), Aurora master spec, Apology Banner
- Fixes de testes, environment limpo, documentação

### Opção B — Merge "FR como fonte"
**NÃO RECOMENDADO.** Qualquer feature "nova" trazida do FR já existe no PT em versão mais recente/completa.

### Opção C — Side-by-side (manter FR como repo separado)
**OK se o utilizador quiser preservar o histórico FR.** Zero valor funcional actual, mas é um arquivo útil se quiser:
- Rever decisões antigas de design
- Reactivar suite legacy de testes (iter2-85) um a um
- Comparar implementações históricas de features agora refactoradas

### Opção D — Manter PT, usar FR só como arquivo de referência ⭐
**RECOMENDADO.**
- `/app` continua o path actual (Opus 5.5, Perplexity, bibliotecas PT)
- Mantém-se `/tmp/construpilot_fr/` disponível para consultas pontuais
- Qualquer "quero isto como o FR" vira uma tarefa dirigida: copiar **um** ficheiro específico ou **uma** feature específica, nunca merge global

### Esforço estimado
| Caminho | Horas | Iterações |
|---|---|---|
| A — Replace total | 40-80 h + regressões | 10+ |
| B — Merge inteligente | 20-40 h (sem valor adicional claro) | 5-8 |
| C — Side-by-side | 1 h (só documentar) | 1 |
| **D — Keep PT, FR como arquivo** | **0 h** (já é o estado actual) | **0** |

### Micro-tarefas opcionais (independentes da estratégia)
1. **Higienização de comentários FR→PT em `/app`** (apenas docstrings e comentários; sem alterar lógica): 2-4 h · 1 iteração.
2. **Portar 2-3 testes legacy FR seleccionados** (ex: `test_iter75_photo_reset_device`, `test_iter76_2fa_devices_csv`) para a suite PT actual: 2-6 h.
3. **Apagar tokens do zip FR** antes de arquivar: 2 min.

---

## Confirmações finais

- `/tmp/construpilot_fr/` mantido para próxima fase ✅
- `/app` **100 % intocado** por esta análise (`git status` só mostra 2 untracked `yarn.lock` pré-existentes) ✅
- Único ficheiro novo criado: `/app/memory/fr_vs_pt_analysis.md` (este relatório)
