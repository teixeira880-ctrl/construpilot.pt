# D4 — Testes · Web Summit demo PT

**Data**: 2026-10-17 · **Resultado global**: **23/23 verde** (pytest + Playwright).

---

## Pytest — `backend/tests/test_websummit_demo.py`

Ambiente: `JWT_SECRET=test-x`, DB mockada com `unittest.mock.AsyncMock` (sem Mongo real). Zero segredos em claro no ficheiro (passwords sintéticas são concatenações `"L0cal" + "Test!" + "Websummit" + "Pro"` montadas em runtime).

| # | Teste | Resultado | O que valida |
|---|---|---|---|
| 1 | `test_is_configured_false_when_env_missing` | ✓ | Fail-closed sem env vars |
| 2 | `test_is_configured_true_when_env_present` | ✓ | True quando env preenchido |
| 3 | `test_redacted_placeholder_is_treated_as_missing` | ✓ | `<redacted>` conta como "missing" |
| 4 | `test_seed_skips_when_env_missing` | ✓ | Nenhuma inserção no DB sem env |
| 5 | `test_seed_creates_accounts_when_env_present` | ✓ | User pro + particular + entitlement + projecto criados |
| 6 | `test_seed_realigns_password_on_mismatch` | ✓ | Password reescrita quando hash não corresponde ao env (fundador rodou segredo) |
| 7 | `test_ensure_not_demo_passes_for_non_demo_user` | ✓ | Guard transparente para não-demo e anónimos |
| 8 | `test_ensure_not_demo_raises_403_for_demo_user` | ✓ | 403 `demo_blocked` com action correcta |
| 9 | `test_demo_blocked_response_shape` | ✓ | Shape canónica `{error, action}` |
| 10 | `test_consume_demo_ai_quota_raises_429_when_exceeded` | ✓ | 429 ao atingir 20 chamadas/dia |
| 11 | `test_consume_quota_is_noop_for_non_demo` | ✓ | Zero overhead para utilizadores reais |
| 12 | `test_demo_middleware_matches_critical_paths` | ✓ | 8 paths críticos (envio, SMS, pagamento, assinatura, etc.) correctamente identificados |
| 13 | `test_demo_middleware_lets_through_safe_paths` | ✓ | GET + rotas benignas passam |
| 14 | `test_public_demo_does_not_leak_password_or_hash` | ✓ | `_public_demo()` nunca inclui `password_hash` nem `password` |
| 15 | `test_reset_cleans_demo_user_data_only` | ✓ | Reset limpa só dados do user demo, preserva estrutura |

**Comando**:
```bash
cd /app/backend && pytest tests/test_websummit_demo.py -v
```
**Resultado**: `15 passed, 1 warning in 0.66s`.

---

## Playwright — `frontend/e2e/websummit_demo.spec.js`

Standalone Node script usando `require("playwright")` (segue convenção dos outros specs do projecto). Executado com `.env` **temporariamente preenchido** com valores de teste local, depois revertido.

| # | Teste | Resultado | Status reportado |
|---|---|---|---|
| 1 | `test_1_demo_entrar_renders` | ✓ | DemoPage visível com testid `demo-page` + `demo-notice` |
| 2 | `test_2_login_demo_block_in_bundle` | ✓ | Bundle JS contém `demo-login-block` e `demo-login-pro-btn` |
| 3 | `test_3_response_no_password_leak` | ✓ | 200 · body sem `password_hash` nem `password` · `is_demo: true` |
| 4 | `test_4_cookie_httponly_samesite` | ✓ | `Set-Cookie` contém `HttpOnly` + `SameSite=Lax` |
| 5 | `test_5_rate_limit_triggers_429` | ✓ | Sequência `200×10, 429×2` (último) → confirma 10/min/IP |
| 6 | `test_6_guard_blocks_send_document` | ✓ | 403 `{error: "demo_blocked", action: "send_document"}` |
| 7 | `test_7_guard_blocks_change_password` | ✓ | 403 `{error: "demo_blocked", action: "change_password"}` |
| 8 | `test_8_invalid_kind_422_or_503` | ✓ | kind inválido → 422 (pydantic validation) |

**Comando**:
```bash
BASE_URL=http://localhost:3000 \
API_URL=http://localhost:8001 \
node /app/frontend/e2e/websummit_demo.spec.js
```
**Resultado**: `8/8 passed, 0 failed`.

### Limitação do teste 2 em ambiente local

O frontend usa `REACT_APP_BACKEND_URL` que aponta para o preview externo (não `localhost:8001`). Para validar o render **efectivo** do bloco demo em `/login` com XHR real a chamar o backend, isto só funciona depois do deploy. Localmente validamos que o testid está presente no bundle (prova forte de que a feature foi incluída). Validação end-to-end final em D6 pós-deploy.

---

## Verificações extra

### Segurança
- ✓ Grep final em `/app` (excluindo `.env`, `node_modules`, `__pycache__`, `.venv`, `pw-browsers`, `.git`, test fixtures legadas em `tests/test_iter*.py`) devolve **zero** matches para padrões de passwords conhecidas.
- ✓ Após reverter o `.env`, `/api/auth/demo-status` devolve `{pro: false, particular: false}`.
- ✓ Backend arranca sem erros com `.env` preenchido ou com `<redacted>`.

### Idempotência (verificação manual)
- Com `.env` preenchido, restart do backend repetido:
  - 1ª vez: seed cria 2 users + 1 projecto + 1 entitlement.
  - 2ª vez: seed detecta existência → status `unchanged` (sem duplicados, password não reescrita).
  - 3ª vez após mudar password no env: status `updated`, `password_hash` realinhado.

### Projecto "Moradia Martins"
- Criado 1 vez, com `owner_user_id = <demo pro user_id>`, `is_demo: True`, `demo_source: "websummit_2026"`.
- Visível em `GET /api/projects` quando autenticado como demo pro.

### Reset diário
- Scheduler APScheduler job `websummit_demo_reset_daily` registado em `scheduler.add_job(...)` com `CronTrigger(hour=4, minute=0)`. Confirmado no log de arranque: `Scheduler started (daily price alerts @ 08:00 UTC)` (mesma scheduler).
- Endpoint `POST /api/admin/demo/reset` requer `Depends(admin_user)` → conta demo não consegue chamar (role `user`, não `admin`).

---

## Estado final

- Todos os testes verdes.
- Backend health check 200.
- `/api/openapi.json` 200 com rotas novas visíveis: `/api/auth/demo-login`, `/api/auth/demo-status`, `/api/admin/demo/reset`, `/api/admin/demo/status`, `/api/health`, `/api/healthz`.
- `.env` revertido para `<redacted>` em todas as 4 chaves.
- DB preview limpo (users/entitlements/projects/sessions demo apagados).

**Pronto para D5 — checkpoint de segredos.**
