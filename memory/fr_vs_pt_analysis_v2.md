# FR vs PT · Análise comparativa — V2 (zip corrigido)

**Data**: 2026-02-04
**Fonte FR v2**: `/tmp/construpilot_fr_v2/construpilot.fr_1-main/` (snapshot **2026-10-04 21:12**, 198 MB)
**Fonte PT**: `/app/` (actual, Opus 5.5 + Perplexity + Aurora removido)

> **Nota importante**: este relatório **substitui** a conclusão da V1. A V1 analisava o zip errado (snapshot de 2026-08-26, 29 MB). O zip V2 (198 MB, snapshot de hoje) revela um FR **genuinamente mais avançado** em várias áreas. A estratégia recomendada é agora diferente.

---

## 🎯 Sumário executivo (TL;DR)

### Respostas directas às 5 perguntas

1. **Quão mais desenvolvido é o FR agora?**
   - **Significativamente mais, mas NÃO em todas as áreas.**
   - Backend: 121 679 linhas FR vs 41 207 PT (**×3**)
   - Frontend: 65 383 linhas FR vs 42 760 PT (**×1.5**)
   - 152 engines FR vs 59 PT (+ 5 pastas de domínio dedicadas: `btp_ai`, `btp_solver`, `perplexity_plus`, `plans_pro`, `stair_engine`, `growth`)
   - 88 routes FR vs 57 PT
   - 98 pages FR vs 70 PT (30 páginas únicas FR vs 1 única PT)
   - 168 tests FR vs 4 PT
   - **MAS**: FR não tem o nosso router Claude Opus 5.5, não tem o Apology Banner, não tem o `ai_health`, não tem a Biblioteca PT 2026, usa `emergentintegrations` (abandonado por nós).

2. **Top 10 features valiosas no FR que PT NÃO tem**:
   1. **`btp_solver/`** — resolve problemas BTP com cascade IA (Perplexity Sonar → Claude Sonnet 4.6 → GPT-5.6 Terra fallback). Retorna diagnóstico+soluções chiffradas+normativas+gráficos+urgência. Routes `/api/btp-solver/solve|history|{id}`.
   2. **`plans_pro/`** — análise plantas DWG/RVT/IFC/PDF/PNG via Autodesk Platform Services + vision cascade (Claude Sonnet 4.6 Vision + GPT-4o + Gemini 2.0 Flash, fusão por voto). Job assíncrono com polling. Routes `/api/plans-pro/upload|job/{id}`.
   3. **`perplexity_plus/`** — 4 endpoints: chat SSE streaming, regulamentação (Legifrance/AFNOR/CSTB), redacção devis estruturado JSON, artigo CCTP. **Chama atenção**: já existe infra Perplexity em PT, mas estes 4 endpoints novos valem a pena portar.
   4. **`stair_engine/`** — calculador escadas completo (Blondel, 1⁄4 virada, 1⁄2 virada, helicoidal, concreto+ábacos, forced-solver, optimizer, PDF dossier, alertas, normas FR→adaptar PT).
   5. **`growth/`** — módulo de growth automático: ads connectors (Google), autofix SEO, autopilot campanhas, brands, content, crawler. Página `GrowthPage.jsx` + 10 panels.
   6. **Autodesk Platform Services pipeline** — upload OSS, tradução Model Derivative, extracção properties com cache por hash. 25 ficheiros a referenciar. Essencial para DWG profissional.
   7. **Assistant workspace** — `Assistant.jsx` + `assistant_*` engines (14 ficheiros): workspace completo com files, jobs, media, quote pricing, quote schema, quote service, state, trace, web, sources. Alternativa modular ao Coach IA.
   8. **DocIntel / Doc Reconcile / Doc Embeddings / Doc Compare** — pipeline documentos inteligente (embeddings, reconciliação, comparação).
   9. **Structuro** — reconhecimento estrutural + modelo + notas + sheets + AI (`structuro_*.py` 5 engines). Página dedicada.
   10. **Portal / Portal Chat / Chantiers / RadarChantiers / Today / Journey / Preferences / Help** — módulos operacionais do pro (gestão de obras ativas, radar de chantiers via Sitadel, timeline do dia, jornada do utilizador, preferências, help center integrado).

   **Bónus**:
   - `i18n/pt_auto.json` — já tem **5 408 linhas** de traduções FR→PT (auto-geradas). **Ganho enorme de tempo**.
   - `AUDIT.md` — relatório de segurança completo com roadmap priorizado.
   - 168 tests backend (vs 4 em PT) — massa crítica de regression testing.

3. **Conflitos com trabalho recente PT**:
   | Área PT | FR tem? | Conflito |
   |---|---|---|
   | Claude Opus 5.5 | ❌ (usa `claude-sonnet-4-6` + `emergentintegrations`) | **SIM — manter PT, não regressar** |
   | Router multi-provider (`ai_providers/`) | ❌ (usa cascade ad-hoc em cada módulo) | **SIM — preservar, adaptar FR aos nossos providers** |
   | Perplexity em `coach_ai.py` | ❌ (tem Perplexity só em `btp_ai` e `growth`) | **PARCIAL — nós temos melhor; mas FR tem Perplexity Plus 4 routes avançadas que valem a pena** |
   | ServiceApologyBanner | ❌ | **Preservar PT** |
   | Aurora removal | ❌ (nunca teve) | **Zero conflito** |
   | Biblioteca PT 2026 (322 items) | ❌ | **Preservar PT absolutamente** |
   | AdminSecrets | ❌ | **Preservar PT** |
   | ai_health endpoint | ❌ | **Preservar PT** |
   | Páginas PT: LandingPortugal, LandingParticuliers | ❌ (FR tem só Landing FR) | **Preservar PT** |
   | PRD + rotate_2026_secrets.txt + test_credentials | ❌ | **Preservar PT** |

4. **Estratégia recomendada**: **B+ — Merge selectivo direccionado por valor** (não é "trazer TUDO" — é portar features específicas de alto valor FR, adaptando-as ao stack PT já existente).

5. **Esforço estimado por estratégia**:

   | Estratégia | Horas | Iterações | Risco |
   |---|---|---|---|
   | **A — Replace total `/app` ← FR** | 80-160 h | 15-20+ | **ALTO** (perde-se Opus 5.5, biblioteca PT, banner, i18n PT já feito manual, etc.) |
   | **B — Merge selectivo (recomendado)** | **40-80 h** | **6-10 iter** | **MÉDIO** (controlável fase a fase) |
   | C — Side-by-side | 2 h | 1 | Nulo (só documentar) |
   | D — Keep PT, FR como arquivo | 0 h | 0 | Nulo |

   **Decomposição da estratégia B em 10 sprints** (~ 6-8 h por sprint):
   1. Sprint 1 — infra i18n + port de `pt_auto.json` (5408 strings) · 4 h
   2. Sprint 2 — `btp_solver/` ← adaptar para nossos providers (Opus 5.5 + Perplexity actual) · 6 h
   3. Sprint 3 — `plans_pro/` + Autodesk APS pipeline · 8 h + conta Autodesk
   4. Sprint 4 — `perplexity_plus/` 4 endpoints · 4 h
   5. Sprint 5 — `stair_engine/` + adaptar normas FR→Eurocódigos PT · 8 h
   6. Sprint 6 — `growth/` module · 10 h
   7. Sprint 7 — Assistant workspace (14 engines) · 10 h
   8. Sprint 8 — DocIntel/Structuro · 8 h
   9. Sprint 9 — Páginas Portal/Chantiers/Today/Journey/Preferences/Help · 8 h
   10. Sprint 10 — Adaptações PT obrigatórias (IVA 23%, RGEU, RJUE, DL FR→DL PT, moeda formato, NIF) + 168 tests → selecção de 30-40 relevantes · 10 h

   **Risco crítico**: cada sprint pode trazer regressões se não for isolado por feature flag. Recomendo trabalhar branch por sprint.

---

## Secção 1 — Inventário factual do FR v2

### 1.1 Metadata
| Campo | Valor |
|---|---|
| Snapshot | **2026-10-04 21:12** (timestamp mtime uniforme = export, não git clone) |
| Tamanho zip | 198.3 MB |
| Ficheiros total (excl. node_modules/.git/__pycache__) | 1 767 |
| Tamanho descomprimido | 212 MB |
| `.git` | ausente |
| README | `# ConstruPilot — Bundle Sprint 0 + Perplexity+` (menciona "Sprint 0 sécurité + 4 nouvelles routes IA") |
| Audit docs | `AUDIT.md` (12.9 KB, 17-set-2026) + `SPRINT1-README.md` + `PROMPT-EMERGENT.md` |

### 1.2 Estrutura top-level
```
/tmp/construpilot_fr_v2/construpilot.fr_1-main/
├── .emergent/, .screenshots/, .gitconfig, .gitignore
├── AUDIT.md, SPRINT1-README.md, PROMPT-EMERGENT.md
├── README.md, test_result.md, auth_testing.md, image_testing.md
├── design_guidelines.json (18 KB — mais rico que o nosso de 6 KB)
├── test_metre.pdf, branded.pdf, after.png, before.png
├── backend/
│   ├── assets/              ← novo (fontes/imagens embutidos)
│   ├── btp_ai/              ← novo (métrique + research + report + routes)
│   ├── btp_solver/          ← novo (solver BTP: diagnóstico/soluções)
│   ├── core/                (idem PT)
│   ├── data/                ← novo (symbols_btp.json)
│   ├── engines/             (152 ficheiros, +expenses/ +metre/ subpastas)
│   ├── growth/              ← novo (growth marketing automação)
│   ├── perplexity_plus/     ← novo (4 endpoints Perplexity avançados)
│   ├── plans_pro/           ← novo (Autodesk pipeline + vision cascade)
│   ├── plans_pro ...        (plans análise avançada)
│   ├── routes/              (88 ficheiros)
│   ├── scripts/             (22 ficheiros)
│   ├── stair_engine/        ← novo (calculador escadas completo)
│   ├── tests/               (168 ficheiros, iter2 → iter85 + muitos novos)
│   ├── pytest.ini
│   ├── requirements.txt     (172+ pacotes, muito maior)
│   ├── server.py            (96 include_router — vs 57 em PT)
│   └── video_cache/
├── frontend/
│   └── src/
│       ├── App.css, App.js, index.css, index.js
│       ├── components/      (225 .jsx)
│       ├── constants/, context/, hooks/, lib/
│       ├── growth/          ← novo (10 panels growth)
│       ├── i18n/            ← novo (pt_auto.json 5408 linhas)
│       ├── pages/           (98 .jsx)
│       ├── seo/             ← novo (DefaultSEO.jsx)
│       └── styles/          ← novo (workspace.css)
├── deployer-agent-docs/
├── integration/revision3/, revision4/
├── memory/, scripts/, test_reports/, tests/
```

### 1.3 Linhas de código
| Métrica | FR v2 | PT | Delta |
|---|---|---|---|
| Backend `.py` | **121 679** | 41 207 | **+195 %** |
| Frontend `.jsx` | **65 383** | 42 760 | **+53 %** |
| Backend ficheiros | 450 (`engines/` 152 + `routes/` 88 + `tests/` 168 + outros) | 146 | +208 % |
| Frontend ficheiros | 297 .jsx | 207 .jsx | +43 % |
| Páginas | 98 | 70 | +40 % |
| Componentes | 225 | 132 | +70 % |
| Tests backend | 168 | 4 | +4100 % |

### 1.4 Backend — rotas montadas em `server.py` FR
**96 `include_router(...)` registrados** (PT tem 57). Rotas únicas chave (confirmadas):
`trash, growth, btp_ai, pplx_plus, btp_solver, plans_pro, doc_photos, quote_templates, doc_intel, renovation, structuro, admin_expenses, presentation, brochures, radar, radar_contacts, radar_sync, assistant, agents, marketing_public, blg, newsletter, dpgf_public, profitability, project_quotes, company_page, today, chantiers, onboarding, portal, portal_chat, speech, assistant_files, assistant_jobs, journey, stairs`.

### 1.5 Backend — engines únicos em FR (não existem em PT)
147 engines dos 152 do FR são únicos. Agrupados por domínio:

**AI Assistant (14)**: `assistant_claude, assistant_fallback, assistant_files, assistant_jobs, assistant_media, assistant_quote_pricing, assistant_quote_schema, assistant_quote_service, assistant_report_pdf, assistant_sources, assistant_sources_tools, assistant_state, assistant_trace, assistant_web, assistant_workspace`

**Autodesk Platform Services (7)**: `autodesk_activity, autodesk_client, autodesk_dwg, autodesk_md, autodesk_md_tools, autodesk_storage, autodesk_validation`

**Plan analysis avançada (18)**: `plan_chains, plan_cotes, plan_cotes_pdf, plan_crops, plan_geometry_ai, plan_geometry_prompt, plan_identity, plan_interior_overlay, plan_narrative_pdf, plan_pdf_i18n, plan_principles, plan_refresh, plan_report_pdf, plan_sources, plan_symbols, plan_vector_pdf, plan_walls, interior_prompt`

**Doc intelligence (5)**: `doc_compare, doc_embeddings, doc_intel, doc_reconcile, office_text`

**Structuro (5)**: `structuro_ai, structuro_model, structuro_note, structuro_recognition, structuro_sheets`

**Studies PDF (3)**: `studies_pdf, studies_prompt, openai_studies`

**Postal / Merci Facteur (6)**: `mercifacteur, postal_billing, postal_delivery, postal_diagnostics, postal_offer, postal_sender, postal_tracking` — **adaptar para CTT em PT**

**Sitadel (bases de licenças FR) (4)**: `sitadel_client, sitadel_permits, sitadel_sync, sitadel_text` — **adaptar para base PT (Portal.pt / IHRU)**

**Comparatif / Presentation (6)**: `comparatif_pdf, compare_pdf, estimate_pdf, presentation_assets, presentation_pdf, presentation_pptx`

**Radar chantiers (2)**: `radar_filters, radar_zones`

**Finance (5)**: `chantier_costs, deadline_reminders, deposit_credit, profitability` ...

**Outros**: `ademe_dpe` (DPE FR → adaptar REH PT), `aides_reno` (ajudas FR → adaptar IFRRU PT), `cad_geometry, company_registry, corps_etat, dpgf_engine, eval_harness, gemini_ocr, journey, llm_keys, native_chains, object_storage, pdf_internal, pool, pv_pdf, quote_check, section_schema, speech, trash_jobs, upsell`.

### 1.6 Backend — pastas de domínio dedicadas (6 — todas únicas no FR)
- `btp_ai/` — métrique + research + report_pdf + routes
- `btp_solver/` — solver + schema + photos + report_pdf + routes
- `perplexity_plus/` — client + routes (4 endpoints: chat SSE, reglementation, devis, cctp)
- `plans_pro/` — autodesk_pipeline + vision_cascade + routes
- `stair_engine/` — blondel + concrete + concrete_abaques + forced_solver + half_turn + helicoidal + models + norms_fr + optimizer + pdf_dossier + quarter_turn + assistant + alerts
- `growth/` — ads_connectors + autofix + autopilot + brands + campaigns + content + crawler + google + jobs + marketing + providers + research + routes

### 1.7 Frontend — 30 páginas únicas em FR
`AppPrivacy, Assistant, BtpSolver, ChantierDetail, Chantiers, CompanyPage, CompanyPublic, CotesControl, DeleteAccountPage, DocIntelPage, DpgfPage, Help, Landing, LandingMetre, LandingPro, PlanAnalysis, PlansPro, Portal, PostalPaymentReturn, Preferences, ProOffer, Profitability, ProspectionLanding, RadarChantiers, Renovation, RfqPublic, SharedEstimate, StairCalculator, Structuro, Trash`

### 1.8 Frontend — i18n já existente
- `src/i18n/pt_auto.json` — **5 408 linhas de traduções FR→PT**, gerado automaticamente mas revisável. Amostra:
  ```
  "Impression et expédition par Merci Facteur…" → "Impressão e envio por Merci Facteur…"
  "Tarif du courrier" → "Preço da carta"
  "Calcul en cours…" → "A calcular…"
  ```
- `scripts/i18n_pt_auto.py` — gerador deste JSON (reutilizável).

### 1.9 AI stack FR
| Métrica | Hits |
|---|---|
| `emergentintegrations` | **22 ficheiros** (ainda muito usado) |
| `openai` | 38 ficheiros |
| `claude` / `anthropic` | 13 / 14 ficheiros |
| `perplexity` | 13 ficheiros |
| `gemini` (3.1 Pro / 3-flash / 2.5-flash-image) | 12 ficheiros |
| `autodesk` | 25 ficheiros |
| `sitadel` | 8 ficheiros |

**Modelos LLM referenciados** no código FR:
`claude-haiku-4-5-20251001, claude-opus-4-8, claude-sonnet-4-5-20250929, claude-sonnet-4-6, gemini-2.5-flash-image, gemini-3-flash-preview, gemini-3.1-pro, gemini-3.1-pro-preview, gemini-3.5-flash, gemini-3.6-flash, gpt-4o-transcribe, gpt-5.4, gpt-5.4-mini, gpt-5.5, gpt-5.6-terra, gpt-6-astra`.

**Observação**: FR tem **menu de modelos admin configuráveis** (`engines/ai.py` `AI_TEXT_MODELS` dict). O PT ainda não — pode ser portado.

### 1.10 Aurora no FR v2?
**Zero referências**. FR nunca teve Aurora (coerente com a V1).

### 1.11 Segurança no FR v2
| Verificação | Resultado |
|---|---|
| `.token.txt` / `.adm_token.txt` / `.pro_token.txt` no root | **AUSENTES ✅** (já foram higienizados) |
| `grep -rE "sk-ant-[a-zA-Z0-9]{30,}"` | 0 matches ✅ |
| `grep -rE "sk-proj-[a-zA-Z0-9]{30,}"` | 0 matches ✅ |
| `grep -rE "pplx-[a-zA-Z0-9]{30,}"` | 0 matches ✅ |
| `grep -rE "AKIA[0-9A-Z]{16}"` (AWS) | 0 matches ✅ |
| `.env` / `.env.example` | **ausentes** no zip |
| `scripts/revoke_leaked_tokens.py` | **presente** — já tiveram incidente, resolvido |

**AUDIT.md** confirma que foi conduzido audit em 17-set-2026 e identificou 4 problemas críticos (Sprint 0): tokens no root (já corrigido), JWT em localStorage, rate limiting, …

### 1.12 Tests
168 ficheiros backend tests. Suite muito mais rica que a V1 (66). Nomes relevantes:
`test_btp_solver, test_plans_pro, test_stair_engine, test_assistant_*, test_perplexity_plus, test_doc_intel, test_structuro, test_growth, test_journey, test_portal, test_chantiers, test_radar`.

---

## Secção 2 — Estado actual `/app` (PT)

Idêntico ao relatório V1. Resumo:
- 59 engines · 57 routes · 70 pages · 132 components
- 41 207 linhas backend / 42 760 linhas frontend
- **Core preservável**: `ai_providers/` (Claude Opus 5.5 + OpenAI + Perplexity + fallback), `coach_ai.py`, `ai_health.py`, `ServiceApologyBanner.jsx`, Aurora master spec, Biblioteca PT 2026 (322 items), `AdminSecrets.jsx`, i18n PT via `landingI18n.js`, 23 páginas PT únicas (`LandingPortugal, Welcome, Comparatif, …`), 4 tests a passar (26 passed).

---

## Secção 3 — Matriz comparativa (actualizada)

| Área | FR v2 | PT | Recomendação |
|---|---|---|---|
| Auth | login, Google, reset, 2FA, KYC | **idem + verify-email mais robusto** | **IDENTICAL / KEEP_PT** |
| Projects | CRUD, expenses, budget, PDF, timeline | idem | IDENTICAL |
| Estimates | Smart Project + Describe + Analyse | idem | IDENTICAL |
| **BTP Solver** | ✅ cascade IA Perplexity→Claude→GPT-5.6 | ❌ | **TAKE_FR + adaptar (Opus 5.5 + Perplexity actual)** |
| **Plans Pro + Autodesk APS** | ✅ DWG/RVT/IFC + vision cascade | ❌ (temos `plan_ai.py` básico) | **TAKE_FR** (feature core) |
| **Perplexity Plus (4 endpoints)** | ✅ chat SSE, reglementation, devis, cctp | ❌ (temos Perplexity mas via router) | **TAKE_FR + adaptar prompts PT** |
| **Stair Engine** | ✅ Blondel+concreto+ábacos+PDF | ❌ | **TAKE_FR + adaptar normas (Eurocódigo 2 + REH)** |
| **Growth module** | ✅ ads+autofix+autopilot+brands+content | ❌ | **TAKE_FR** (valor comercial) |
| **Assistant workspace (14 engines)** | ✅ files, jobs, media, pricing, schema, service, state, trace, web | ❌ (temos `coach_ai`) | **MERGE — manter `coach_ai`, trazer workspace features** |
| **DocIntel / DocCompare / DocReconcile** | ✅ embeddings + reconciliação | ❌ | **TAKE_FR** |
| **Structuro** | ✅ reconhecimento estrutural (5 engines) | ❌ | **TAKE_FR** |
| **DPGF engine** | ✅ engine dedicado | parcial (temos `dpgf.py` route) | **MERGE** |
| **Portal / Portal Chat** | ✅ portal pro completo | parcial | **TAKE_FR** |
| **Chantiers + RadarChantiers** | ✅ via Sitadel FR | ❌ | **TAKE_FR + adaptar fonte (Sitadel FR→Portal.pt/IHRU)** |
| **Postal (Merci Facteur)** | ✅ envio+tracking+billing | ❌ | **TAKE_FR + adaptar (CTT PT)** |
| **DPE / Aides Reno FR** | ✅ (ademe_dpe, aides_reno) | ❌ | **TAKE_FR + adaptar (REH + IFRRU 2020 PT)** |
| **Today / Journey / Preferences / Help** | ✅ pages dedicadas | ❌ | **TAKE_FR** |
| **Comparatif / Presentation PDF** | ✅ PDF + PPTX | parcial | **TAKE_FR** |
| **i18n infra** | ✅ `pt_auto.json` 5408 linhas + script gerador | ❌ (só `landingI18n.js`) | **TAKE_FR + revisar PT-PT (não PT-BR)** |
| **AI model selector admin** | ✅ `AI_TEXT_MODELS` dict | ❌ | **TAKE_FR + usar nossos providers** |
| **AUDIT.md security roadmap** | ✅ | ❌ | **TAKE_FR** (adaptar) |
| **168 backend tests** | ✅ | 4 | **MERGE selectivo** (portar 30-40 relevantes) |
| **AI providers router (Opus 5.5)** | ❌ | ✅ | **KEEP_PT** (base para integrar features FR) |
| **ServiceApologyBanner** | ❌ | ✅ | **KEEP_PT** |
| **Aurora master spec PDF + routes/docs** | ❌ | ✅ | **KEEP_PT** |
| **Biblioteca PT 2026 (322 items)** | ❌ | ✅ | **KEEP_PT absolutamente** |
| **AdminSecrets** | ❌ | ✅ | **KEEP_PT** |
| **ai_health endpoint** | ❌ | ✅ | **KEEP_PT** |
| **LandingPortugal / LandingParticuliers / Welcome / Comparatif / Investors** | ❌ | ✅ | **KEEP_PT** |

### Resumo
- **TAKE_FR**: 14 áreas (features de alto valor que PT não tem)
- **MERGE**: 3 áreas (Assistant, DPGF, Tests)
- **KEEP_PT**: 9 áreas (preservar o nosso trabalho recente)
- **IDENTICAL**: 3 áreas

---

## Secção 4 — Adaptações obrigatórias FR→PT

Para cada feature portada do FR, as seguintes substituições são **obrigatórias**:

| Área | FR | PT |
|---|---|---|
| Idioma UI | Francês | **100 % PT-PT** |
| Moeda formato | `1 234,56 €` ou `1.234,56€` | `1 234,56 €` (idêntico) |
| IVA | TVA 20 % | **IVA 23 % (continental) / 22 % (Madeira) / 16 % (Açores)** |
| Datas | `dd/mm/yyyy` | `dd/mm/yyyy` (igual) |
| ID fiscal | SIRET 14 dígitos | **NIF 9 dígitos** |
| Código postal | `75001` (5 dígitos) | **`nnnn-nnn`** |
| Normas construção | RE2020 (térmica) | **REH + RECS + RSECE** |
| Normas edificado | DTU + CSTB | **E-LNEC + Decreto-Lei 95/2019** |
| Normas estruturais | Eurocodes + NF | **Eurocódigos + anexos nacionais PT** |
| Regulamento edificações | RNU + PLU | **RGEU + PDM** |
| Permissions construção | PC (Permis de Construire) | **Licença urbanística / Autorização / Comunicação prévia** (RJUE) |
| Segurança obra | CSPS | **CSS (Coordenador Segurança Saúde em Obra)** |
| Base dados licenças | Sitadel | **IHRU + geoportal municipal** (não há BD nacional unificada) |
| Correio profissional | Merci Facteur (FR) | **CTT ClickSign ou CTT Correio Normal** |
| Energia / DPE | DPE (classe A-G, calc ADEME) | **Certificado Energético (ADENE)** |
| Ajudas renovação | MaPrimeRénov, CEE, Éco-PTZ | **IFRRU 2020, Programa de Apoio ao Ambiente, IRS Jovem** |
| Base fornecedores | fournisseurs FR | **CAE 41/42/43 + Portal da Construção** |

---

## Secção 5 — Classificação idioma FR

### 5.1 Strings a traduzir
Total estimado após deduplicação: ~**8 000-12 000 strings únicas**. 
- **5 408 já estão em `pt_auto.json`** (traduções automáticas prontas, qualidade variável — necessita revisão PT-PT).
- Restantes: prompts de sistema BTP (~ 50 blocos), email templates (~ 40), docstrings (centenas, baixa prioridade).

### 5.2 Qualidade `pt_auto.json`
Amostra revelou traduções **em português (BR ou PT misto)**. Precisa:
- Script de revisão PT-PT (ex: trocar "ônus" por "ónus", "ação" por "ação" OK, "vocês" por "vós", "você" por "o/a utilizador(a)", "legal" por "jurídico/legal", etc.)
- Ou nova geração via Claude Opus 5.5 com prompt "traduzir estrictamente para PT-PT, nunca PT-BR".

---

## Secção 6 — Estratégia recomendada (actualizada)

### Opção B+ — Merge selectivo direccionado por valor ⭐ RECOMENDADO

**Plano de 10 sprints** (~ 60-80 h total, 6 semanas trabalho controlado):

| Sprint | Duração | Entrega | Risco |
|---|---|---|---|
| **S1** · i18n infra + pt_auto revision | 4 h | `i18n/pt-PT.json` revisto + wiring React | Baixo |
| **S2** · BTP Solver (`btp_solver/`) | 6 h | `/api/btp-solver/*` + página `BtpSolver.jsx` em PT, usando nossos `ai_providers` | Médio |
| **S3** · Plans Pro + Autodesk APS | 8 h | Pipeline DWG/RVT/IFC → vision cascade. **Pré-requisito**: conta Autodesk Platform Services + credenciais | Alto |
| **S4** · Perplexity Plus (4 endpoints) | 4 h | SSE chat + reglementação PT (Legifrance→DRE) + devis + CCE (equivalente PT ao CCTP) | Baixo |
| **S5** · Stair Engine | 8 h | Calculador escadas · adaptar normas FR→Eurocódigo 2 + REH | Médio |
| **S6** · Growth module | 10 h | ads/autofix/autopilot/campaigns · Google Ads auth | Médio |
| **S7** · Assistant workspace | 10 h | 14 engines + Assistant.jsx · integrar com nosso `coach_ai` | Alto |
| **S8** · DocIntel + Structuro | 8 h | embeddings + reconcile + comparar + structuro | Médio |
| **S9** · Portal/Chantiers/Today/Journey | 8 h | páginas operacionais + adaptar Sitadel→Portal.pt | Médio |
| **S10** · Validação PT | 10 h | IVA 23 %, NIF, códigos postais, normas, 30-40 tests portados, pytest verde | Baixo |

**Total**: 76 h · ~ 2 semanas full-time ou 6 semanas part-time.

### Preservar sempre (não negociável)
- `ai_providers/` + Claude Opus 5.5 + Perplexity + OpenAI fallback
- `coach_ai.py` como implementação de referência do Coach
- `ServiceApologyBanner.jsx`
- `docs/aurora_master_spec.{md,pdf}` + `routes/docs.py`
- Biblioteca PT 2026 (322 items)
- `AdminSecrets.jsx`
- `ai_health.py`
- `LandingPortugal.jsx`, `LandingParticuliers.jsx`, `Welcome.jsx`, páginas PT únicas
- Pytest actual verde (26/27)

### Nunca copiar directamente
- Strings FR não traduzidas
- Prompts de sistema com normas FR (adaptar para PT)
- Rotas em URL francês (`/calculateurs, /devis, /factures, /rh, /pointage, /parrainage, /bibliotheque`) — manter rotas PT ou criar aliasing
- Modelos LLM pre-Opus 5.5 (manter o nosso stack)
- `emergentintegrations` (nós abandonámos — usar SDKs nativos)
- Sitadel/Merci Facteur sem substituto PT equivalente

---

## Confirmações finais

- `/tmp/construpilot_fr_v2/` mantido ✅
- `/tmp/construpilot_fr/` apagado + zip antigo removido ✅ (libertou ~ 60 MB)
- `/app` **100 % intocado** ✅ (`git status` só mostra 2 untracked yarn.lock pré-existentes + o relatório novo em `memory/`)
- Único ficheiro novo: `/app/memory/fr_vs_pt_analysis_v2.md` (este relatório)
