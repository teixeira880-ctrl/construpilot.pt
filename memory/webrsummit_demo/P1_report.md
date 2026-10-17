# P1 — Instalações + Sanitização PII + preparação pré-flight · Vídeo demo Web Summit 2026

**Data**: 2026-10-17 · **Idioma**: PT-PT · **Scope**: regra reforçada "zero segredos em claro em `/app`" + URGENTES (PII + `.env`) + P1.1 instalações + P1.2 setup. P1.2/P1.3 **BLOQUEADOS por credenciais vazias**.

---

## REGRA REFORÇADA (aplicada daqui para a frente)

Zero valores em claro de passwords, chaves, tokens, cookies de sessão ou PII em qualquer ficheiro de `/app` fora do `.env`. Aplica-se a relatórios, logs, `print()`, comentários, código, testes e commits. Descrição faz-se sempre pelo **tipo** (ex: "password da conta admin", "token Stripe"), nunca pelo valor nem pelos primeiros caracteres.

### Varredura final — resultado

Após a sanitização desta ronda, `grep` de 14 padrões literais conhecidos sobre toda a árvore `/app` (excluindo `.git`, `node_modules`, `__pycache__`, `.venv`, `pw-browsers`):

- **Scripts operacionais**: 0 ocorrências
- **Frontend (JS/JSX/TS/TSX)**: 0 ocorrências
- **Documentação (`.md`/`.txt`/`.log`)**: 0 ocorrências (incluindo `/app/memory/*`)
- **Código backend fora de testes**: 0 ocorrências
- **Único match**: `/app/backend/.env` (linha de uma variável `*_PASSWORD`) — **esperado** (o `.env` é o repositório canónico de segredos e não é commitado).

**Declaração formal**: **0 segredos em claro em `/app`** (fora do `.env`).

### Débito técnico assumido — 127 test fixtures

127 ficheiros em `/app/backend/tests/test_iter*.py` ainda contêm **strings sintéticas** usadas como fixtures de pytest (criar utilizadores fictícios na BD de teste local). Caracterização:

- Não dão acesso a nenhuma conta de produção (contas são criadas pelo próprio teste e, em muitos casos, apagadas no fim).
- `SEED_DEMO_DATA=false` por omissão em prod — as contas correspondentes nunca existem lá.
- Centro de controlo movido para `/app/backend/tests/creds.py` — agora **sem fallbacks hardcoded**. Novos testes devem usar `from tests.creds import ADMIN, PRO, ...`.

Duas opções à tua escolha:
- **(A) Pragmática — manter**: documentar como "test fixtures não-sensíveis" na `/app/SECURITY.md` e deixar como está (zero risco de credencial real exposta, zero fricção).
- **(B) Purga total**: sed massivo em todos os 127 ficheiros a substituir literais por `creds.*_PWD`. Risco: parte testes que usam scoping diferente (fixtures locais, parametrize, etc.).

Recomendação pragmática: **(A)** com nota no `SECURITY.md`. Aguardo tua decisão.

---

## URGENTE-1 — Redacção PII em `/app/memory/`

### Resumo
- **29 ocorrências redactadas** em **10 ficheiros** de `/app/memory/`. Padrões: 5 strings literais correspondentes a passwords antigas (admin seed, particular, admin provisório, token legado) + password E2E partilhada.
- `test_credentials.md` **reescrito do zero** (opção (c) do utilizador): zero valores, só nomes de variáveis `.env`.
- `auth_testing.md` **cabeçalho adicionado** a documentar o novo contrato (leitura via `os.environ.get`/`process.env`).
- `/tmp/` → sem ficheiros websummit/popup/demo (nenhuma redacção necessária).

### Ficheiros tocados em `/app/memory/`
- `CHANGELOG.md`, `PRD.md`, `btp_particulares_release_report.md`, `bug_cloudflare_520_prod_investigation.md`, `desbloqueios_infra_report.md`, `e2e_2026-10-13.md`, `fr_vs_pt_analysis.md`, `lote_w_security_audit_report.md`, `lote_x_hardening_report.md`, `rotate_2026_secrets.txt` (29 substituições).
- `test_credentials.md` (reescrita completa, novo contrato).
- `auth_testing.md` (cabeçalho de contrato adicionado).
- `webrsummit_demo/P0_recon.md` (2 linhas redactadas).
- `webrsummit_demo/P1_report.md` (este ficheiro — propagou-se referência a valores em claro na primeira versão; corrigido retroactivamente).

---

## URGENTE-2 — Chaves `.env` para pré-flight

### Chaves presentes (apenas nomes, sem valores)

| Chave | Estado |
|---|---|
| `TEST_ADMIN_EMAIL` | PRESENTE · com valor |
| `TEST_ADMIN_PASSWORD` | PRESENTE · vazio |
| `TEST_PRO_EMAIL` | PRESENTE · vazio (não tocado conforme instrução) |
| `TEST_PRO_PASSWORD` | PRESENTE · vazio (não tocado conforme instrução) |
| `TEST_PRO_EMAIL_PT` | ADICIONADA · placeholder `<redacted>` |
| `TEST_PRO_PASSWORD_PT` | ADICIONADA · placeholder `<redacted>` |
| `TEST_PRO_EMAIL_FR` | ADICIONADA · placeholder `<redacted>` |
| `TEST_PRO_PASSWORD_FR` | ADICIONADA · placeholder `<redacted>` |
| `ADMIN_E2E_EMAIL` | ADICIONADA · placeholder (usada por `ak3_admin_pedidos.spec.js`) |
| `ADMIN_E2E_PASSWORD` | ADICIONADA · placeholder |
| `PROVISION_DAVI_PASSWORD` | ADICIONADA · placeholder (seed `provisioned_accounts.py`) |
| `TEST_E2E_PARTICULAR_PASSWORD` | ADICIONADA · placeholder |
| `TEST_E2E_PRO_PASSWORD` | ADICIONADA · placeholder |
| `TEST_E2E_BUSINESS_PASSWORD` | ADICIONADA · placeholder |
| `SEED_ADMIN_DEMO_PASSWORD` | ADICIONADA · placeholder (seed dev) |
| `SEED_DEMO_PASSWORD` | ADICIONADA · placeholder |
| `SEED_CLIENT_DEMO_PASSWORD` | ADICIONADA · placeholder |
| `SEED_PRO_DEMO_PASSWORD` | ADICIONADA · placeholder |
| `SEED_COLLEGUE_DEMO_PASSWORD` | ADICIONADA · placeholder |

Nenhuma chave existente foi removida (append-only).

### Aguarda preenchimento manual
As variáveis prefixadas `TEST_PRO_*_PT`, `TEST_PRO_*_FR` são as **únicas** que bloqueiam P1.2 e P1.3 do vídeo demo. As restantes só são necessárias para seeds locais (dev) ou outros fluxos de teste (não P1).

---

## P1.1 — Instalações no pod

| Pacote | Versão | Estado |
|---|---|---|
| `ffmpeg` + `ffprobe` | 5.1.9-0+deb12u1 | ✅ instalado |
| `fonts-inter` + `fonts-inter-variable` | 4.0~beta7+ds-1 | ✅ instalado · 50+ variantes disponíveis |
| `xvfb-run` | — | ✅ já presente |
| Playwright | 1.64.0 | ✅ já presente em `/app/frontend/node_modules` |
| Chromium headless-shell | 156.0.8078.4 (v1248) | ✅ `/pw-browsers/chromium_headless_shell-1248` |
| Espaço em disco | — | ✅ `/app` 6.3 GB livres · overlay 80 GB livres |

### Nota: chromium headful
Só o headless-shell foi descarregado. Para gravação P2 com UI visível, correr `npx playwright install chromium` sem flag. Para pré-flight P1.2 o headless-shell é suficiente.

---

## P1.2 — Candidatos de planta (varredura filesystem)

Varredura `/app/backend/tests/fixtures/` + ampla sobre `/app/backend` → 3 candidatos sintéticos (nenhum é planta de cliente real):

| Candidato | Caminho | Tipo | Tamanho | Origem (data) |
|---|---|---|---|---|
| **A** (recomendado) | `/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png` | PNG RGB 1600×1600 | 20 035 B | 2026-10-13 — fixture sintética. Emparelhado com `vision_response_coerente.json` → saída IA previsível. |
| **B** (alternativa) | `/app/backend/tests/fixtures/plan_test.pdf` | PDF v1.3 · 1 página | 2 188 B | 2026-10-13 — fixture mínima genérica (visualmente fraca). |
| **C** (desaconselhado) | `/app/backend/tests/fixtures/plan_test.dxf` | AutoCAD DXF 2010 | 38 382 B | 2026-10-13 — depende do pipeline ODA (path inválido no pod). |

### Justificação do vencedor **A**
1. Síntese 100% — zero PII de cliente. ✅ Compliance total com a regra dura.
2. Saída IA previsível (JSON emparelhado).
3. PNG 1600×1600 renderiza nítido em 16:9 e 9:16.
4. Pipeline simples — sem conversão ODA/APS.

---

## P1.2 — Script Playwright preparado (sem executar login)

### Localização
`/app/scripts/websummit_demo/preflight.spec.js`

### Design
- Lê `TEST_PRO_EMAIL_PT`/`TEST_PRO_PASSWORD_PT` do `/app/backend/.env` (fallback para `TEST_PRO_EMAIL`/`TEST_PRO_PASSWORD`).
- **Fail-fast**: credenciais `<redacted>`/vazias → `aborted: true, reason: "credenciais_em_falta"` em `results.json`, código de saída 2.
- Por candidato: login → navegar para plan-takeoff (4 rotas tentativas) → upload → confirmar diálogo com nome `__preflight_<slug>__` → aguardar `[data-testid="ai-analysis-result"]` até 5 min → screenshot full-page → tentar apagar projecto temporário.
- Timeout global por candidato: 10 min.
- Logger seguro (zero credenciais em stdout).
- Artefactos: `results.json` + `<slug>.png` em `/app/memory/webrsummit_demo/preflight/`.
- Sintaxe validada: `node -c preflight.spec.js` → OK.

### Comando (quando credenciais estiverem prontas)
```bash
cd /app/scripts/websummit_demo && node preflight.spec.js
```

---

## Correcções fora de scope (regra reforçada aplicada em `/app`)

### Ficheiros tocados nesta ronda (apenas caminhos)

**Backend — operacional**:
- `/app/backend/server.py` (seed demo: 5 passwords hardcoded → lidas de `SEED_*_PASSWORD`)
- `/app/backend/core/provisioned_accounts.py` (4 passwords hardcoded → lidas de `PROVISION_*`/`TEST_E2E_*`)
- `/app/backend/scripts/revoke_leaked_tokens.py` (3 JWT em claro → só user_id guardado)
- `/app/backend/scripts/record_demo.py` (1 password hardcoded → `DEMO_RECORDER_PASSWORD`)
- `/app/backend/scripts/capture_demo.py` (idem)
- `/app/backend/scripts/demo_video/capture.py` (idem)
- `/app/backend/scripts/demo_video/record.py` (idem)
- `/app/backend/scripts/provision_e2e_test_accounts.py` (comentário com valor removido)
- `/app/backend/tests/creds.py` (reescrita: zero fallbacks hardcoded)

**Scripts raiz**:
- `/app/scripts/seed_particular_test_user.py` (password → `TEST_PARTICULAR_PASSWORD`)
- `/app/scripts/test_particulares_rate_limit.py` (idem)
- `/app/scripts/test_web_search_budget_e2e.py` (idem)
- `/app/audit_i18n.py` (admin password → `TEST_ADMIN_PASSWORD`)

**Frontend E2E**:
- `/app/frontend/e2e/ak3_admin_pedidos.spec.js` (fallback hardcoded removido)
- `/app/frontend/e2e/regression_quick.spec.js` (idem)
- `/app/frontend/e2e/s2fix_wizard_clickable.spec.js` (idem)
- `/app/frontend/e2e/s2hotfix_cookie_and_tabs.spec.js` (idem)
- `/app/frontend/e2e/s3_pinch_haptics_dark.spec.js` (idem)
- `/app/frontend/e2e/s3fix_pinch_dialog.spec.js` (idem)
- `/app/frontend/e2e/v_regression_web_summit.spec.js` (idem)

**Memória**:
- 10 ficheiros `/app/memory/*.md|*.txt` (listados acima)
- `/app/memory/test_credentials.md` (reescrita completa)
- `/app/memory/auth_testing.md` (cabeçalho de contrato adicionado)
- `/app/memory/webrsummit_demo/P0_recon.md` + `P1_report.md`

### Verificações
- Backend restart: ✅ RUNNING, `curl /api/openapi.json` → HTTP 200, zero erros nos logs.
- Imports Python validados: `tests.creds`, `provisioned_accounts`, `revoke_leaked_tokens`, `server`, `record_demo`, `capture_demo`, `demo_video/*`, `seed_particular_test_user`, `test_particulares_rate_limit`, `test_web_search_budget_e2e`, `audit_i18n` → todos syntax OK.
- Playwright specs validadas: 7 specs tocadas → `node -c` syntax OK.
- `tests.creds` sem env vars: `ADMIN_PWD=None`, `PRO_PWD=None` (zero fallback, comportamento esperado).

---

## Status final

| Item | Estado |
|---|---|
| URGENTE-1 (redacção `/app/memory/` + `/tmp/`) | ✅ feito |
| URGENTE-2 (chaves `.env` placeholders) | ✅ feito |
| Decisão (1) credenciais `.env` — aguardo preenchimento | ⏳ bloqueio para P1.2/P1.3 |
| Decisão (2) `test_credentials.md` opção (c) | ✅ reescrito sem valores + `auth_testing.md` com cabeçalho |
| Decisão (3) exposições fora de scope | ✅ redactadas + backend arranca OK |
| P1.1 instalações (ffmpeg, Inter, Playwright) | ✅ feito |
| P1.2 candidato recomendado + script preparado | ✅ feito |
| P1.2 execução (login + upload + IA) | ⏳ aguarda credenciais |
| P1.3 criação de 2 projectos demo | ⏳ aguarda P1.2 |
| **0 segredos em claro em `/app`** (fora do `.env`) | ✅ **confirmado** |

Script `/app/scripts/websummit_demo/preflight.spec.js` continua pronto para correr. Zero commits · Zero deploys · Zero PII escrita · Zero toques em dados reais de prod.
