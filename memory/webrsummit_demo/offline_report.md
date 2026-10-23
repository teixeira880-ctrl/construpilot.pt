# WebSummit — demo 100% offline (LOTE 2 consolidado)

## Resultado

Demo da **Moradia Martins** funciona sem internet no stand WebSummit (Lisboa, 10-13 Nov 2026): autenticação, projecto, estimativa, dossier BET, desenhos, orçamento, nota sísmica e assistente — tudo offline. Contas normais **não são afectadas** (interceptor passa adapter original quando `localStorage.is_demo !== "true"`).

HEAD após 2a→2d: ver `git log --oneline -1 /app`. Zero `git push`.

## Correcção estimativa Moradia Martins (pré-LOTE 2)

- **Problema**: 13 lotes escritos à mão em `_demo_moradia_martins_estimation()` violavam a regra "zero números inventados".
- **Fix**: `_demo_moradia_martins_estimation()` chama agora `engines.estimation.estimate_from_request(PricingRequest(**DEMO_MORADIA_MARTINS_PRICING))` → 20 lotes, `total_avg €188 962,19` HT, assinatura `source: engines.estimation.…`.
- **Teste**: `test_moradia_martins_estimation_matches_engine` compara campo a campo (totais, breakdown, coefficients, lots). Falha ao primeiro drift.
- Commits: `884e89e`, `93cae03`.

## Sub-lote 2a — PWA Workbox

- `/public/sw.js` v6 (`construpilot-v6-pwa-demo-ready`): app shell strict + pré-cache best-effort das 7 rotas demo (`/`, `/demo/entrar`, `/dashboard`, `/assistant`, `/smart`, `/chantiers`, `/devis`) + 6 assets `/demo-assets/*`.
- Estratégias: HTML network-first com fallback cache SPA (`/`), assets cache-first, `/api/*` sempre `no-store`.
- Registo em `src/index.js`: gate `process.env.NODE_ENV === "production"` ou flag opt-in `localStorage.cp_force_pwa === "true"` (reservada para o spec 2d).
- Em dev sem flag: desregista SW órfãos de sessões anteriores (anti-HMR-ghost).
- Commit: `c78f1c6`.

## Sub-lote 2b — Interceptor axios + fixtures via motores

- `backend/scripts/websummit/export_demo_fixtures.py` gera `src/fixtures/demo/{users,projects,demo_branding,assistant_docs,plans,quotes,_manifest}.json` a partir de `estimate_from_request` + `samples.demo_branding`. Zero números à mão.
- `src/lib/demoInterceptor.js` substitui `api.defaults.adapter`: quando `localStorage.is_demo === "true"`, resolve routing table local (auth, projects, branding, growth, assistant_docs, leads, estimation/materials) — senão delega ao adapter original (XHR real).
- Mutações persistidas em IndexedDB `construpilot_demo_v1`.
- `DemoPage.jsx` ganha bloco "Modo offline — stand WebSummit" com CTAs `data-testid="demo-offline-{pro|particular}-btn"` + botão `demo-offline-reset-btn` (reset IndexedDB).
- Testes backend: 4 novos em `test_demo_fixtures_export.py`. Commit: `94fc5eb`.

## Sub-lote 2c — Assets estáticos + Assistente offline

- `backend/scripts/websummit/generate_demo_assets.py` chama `bet_core.samples.build_all` + `bet_core.pipeline.run` → 6 ficheiros em `/public/demo-assets/`:
  - Projeto arquitectura (109 KB), Estudo geotécnico (41 KB), Dossier BET (289 KB), Desenhos DXF ZIP (160 KB), Orçamento XLSX (17 KB), Nota sísmica (3 KB) — total ~620 KB.
- Assistente offline: 13 cenários em `src/fixtures/demo/assistant_responses.json` cobrindo o guião (BET, custo, paredes, sísmico, betão, aço, IVA, prazo, arquitectura, geotécnico, energia, licenciamento, exportar). Matching por keywords normalizadas (NFD), fallback com 4 sugestões clicáveis. Zero LLM.
- Interceptor ganha rotas `POST /assistant/{chat,ask,message}` + `GET /assistant/{threads,history}` → resolução local com `source: "demo_offline:fixtures/..."`.
- Testes backend: 4 novos em `test_demo_assets_export.py` (magic bytes PDF/ZIP/XLSX). Commit: `f5ba6d9`.

## Sub-lote 2d — Playwright offline

- `e2e/demo_offline.spec.js` — standalone node (chromium headless). Resultado local: **8/8 verdes**.
  - **Teste 1** (online → offline mid-session): `/demo/entrar` → click "Offline — Profissional" → `context.setOffline(true)` → nav `/dashboard` → verifica "Moradia Martins" no DOM → 0 chamadas `/api/*` à rede → sem crash.
  - **Teste 2** (SW offline boot): registo SW (flag `cp_force_pwa`) → pré-aquecer `/demo/entrar` → `setOffline(true)` → `reload()` serve HTML + chunks da cache SW → shell `data-testid="demo-page"` renderiza sem crash.
- Flag preview `DEMO_E2E_ENABLED`: **não necessária** — o interceptor resolve tudo client-side, zero dependência do backend demo.

## Smoke LOTE 1 (reactivo)

- `scripts/websummit/smoke_lote1_prod.sh` 3 pontos: `/api/health` + login demo pro Moradia Martins (verifica `source` começa por `engines.estimation.`) + login demo particular.
- Prod `/api/health` 200 OK, `/api/auth/demo-status` → `{pro:true, particular:true}`.
- **Credenciais prod indisponíveis no pod** (`WEBSUMMIT_DEMO_PASSWORD_PT` placeholder `<redacted>`). Smoke prod aguarda credenciais reais em env ou execução manual pelo fundador. HTTP 200 em `/api/health` sugere backend saudável.

## Deploy final LOTE 1 + LOTE 2 — clique manual

Zero tool de deploy. Fundador: **Dashboard Emergent → `construpilot.pt` → "Deploy to production"** com HEAD actual + checkpoint.

HEAD a deployar cobre:
- F3 pitch deck v2, F5 promote admin + audit log
- LOTE 1 fix crash `ProjectDetail` + estimativa Moradia Martins via motor real
- LOTE 2 completo (PWA v6, interceptor demo, 6 assets, 13 cenários Assistente, Playwright 8/8).

## Procedimento stand WebSummit

1. **Antes do dia 9 Nov** (preparação):
   - Abrir https://construpilot.pt uma vez com dados móveis/WiFi para registar SW em cache.
   - "Adicionar ao ecrã principal" (Chrome Android / Safari iOS) → ícone ConstruPilot.
   - Ir a `/demo/entrar` e clicar **"Offline — Profissional"** → confirma o download das fixtures.
   - Activar **modo avião** no telemóvel → re-abrir ConstruPilot → confirmar que o fluxo completo funciona (login, Moradia Martins, dossier BET, Assistente responde a "quanto custa").
2. **Durante o stand**:
   - Modo avião ligado (ou simplesmente sem WiFi) → zero dependência do stand WiFi do WebSummit.
   - Visitante escolhe modo demo (Pro ou Particular) → percorre o guião.
   - Após cada visitante: botão **"Reiniciar demo"** apaga IndexedDB → próxima demo arranca limpa.

## Regras duras honoradas

Zero `git push` · Zero `.fr` · Zero `engines/bet_agent/` · Zero segredos em claro · Zero dados reais · Zero números inventados (tudo via `engines.estimation` + `bet_core`) · Zero alteração a contas normais · Zero toque na enhancement "source estimativa" (adiada).

## Testes finais

- Backend: **65/65 verdes** (bet_core 46 + showcase 5 + admin audit 6 + fixtures export 4 + assets export 4). `tests/backend_test.py` skip condicional quando `REACT_APP_BACKEND_URL` ausente.
- Frontend compila (`webpack compiled successfully`).
- Playwright `demo_offline.spec.js`: **8/8 verdes**.
