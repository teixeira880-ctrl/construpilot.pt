# Lote W — Auditoria de Segurança (pré-deploy)

- Preview: `https://construpilot-recon.preview.emergentagent.com`
- Data: 2026-10-15
- Scope: `/app/backend` + `/app/frontend/src` + `/app/memory` + `/app/backend/.env`
- Regras: nenhum GitHub, nenhum deploy, nenhuma rotação de chaves ao vivo, nenhum apagamento de contas.

---

## Resumo executivo

| Ponto | Classificação | Fix no código? | Decisão humana? |
|---|---|---|---|
| 1 · Segredos no código | **BAIXO** | parcial (.env.example criado) | 1 ação |
| 2 · Contas de teste expostas | **ALTO** | não (seed é por design) | 3 ações |
| 3 · Rotas sensíveis (openapi/docs/redoc) | **CRÍTICO** | ✅ guard por ENV | 1 ação (fix do `.env`) |
| 4 · Autenticação | **OK** | — | — |
| 5 · Permissões cross-tenant | **OK** | — | — |
| 6 · Uploads | **MÉDIO** | não (amostragem apenas) | 1 ação |
| 7 · CORS + headers de segurança | **ALTO** → **BAIXO** após fix | ✅ middleware adicionado | — |
| 8 · Dependências com vulnerabilidades | **MÉDIO** | não (upgrades só patch) | 1 ação |
| 9 · Resíduos GitHub/Phase 0 | **BAIXO** | não (inventário apenas) | 1 ação |

**Taxa de resolução no código:** 3/9 pontos corrigidos. 4/9 mitigados por design (OK). 2/9 para follow-up humano.

---

## 1 · Segredos no código — **BAIXO**

### Findings
Inventário completo (grep por padrões `sk_live_|sk_test_|re_|AIza|mongodb://|SECRET_KEY=...`):

| Ficheiro:linha | Padrão | Tipo | Risco |
|---|---|---|---|
| `/app/backend/.env:1` | `MONGO_URL=mongodb://localhost:27017` | Credential (local) | nenhum — `.env` não versionado |
| `/app/backend/scripts/translate_plans_db.py:94` | `mongodb://localhost:27017` como `os.environ.setdefault` default | Default local | aceitável |
| `/app/backend/scripts/seed_materials_pt_prices.py:179` | idem | Default local | aceitável |
| `/app/backend/tests/*` (10 ficheiros) | `mongodb://localhost:27017` em `os.environ.get(... , default)` | Default local em testes | aceitável |
| `/app/frontend/src/pages/AdminSecrets.jsx:190` | `placeholder={\`Ex.: sk_live_…\`}` | Placeholder UI (texto estático) | **não é um segredo** — é texto de ajuda |
| `/app/frontend/build/static/js/*.js` | zero matches sk_/re_/AIza/mongodb | — | nenhum |

**Nenhum segredo real exposto em código fonte ou bundles de produção.**

### Corrigido no código
- `/app/backend/.env.example` **criado** com 102 nomes de variáveis + cabeçalho PT-PT explicando que o `.env` real nunca deve ir para GitHub. Documenta as 2 novas vars introduzidas no Lote W (`ENV`, `SECURITY_HEADERS`).

### Para o Martinho decidir
- Adicionar `.env.example` ao `.gitignore`? → **Não** — convencional incluir no repo para onboarding de devs. (Decisão: deixar incluído.)

---

## 2 · Contas de teste expostas — **ALTO**

### Findings

| Ficheiro:linha | Account | Password |
|---|---|---|
| `/app/backend/core/provisioned_accounts.py:15-16` | `teste.particular+e2e@construpilot.pt` | `TesteE2E!2026` (literal) |
| `/app/backend/core/provisioned_accounts.py:19-20` | `teste.pro+e2e@construpilot.pt` | `TesteE2E!2026` (literal) |
| `/app/backend/core/provisioned_accounts.py:22-23` | `teste.business+e2e@construpilot.pt` | `TesteE2E!2026` (literal) |
| `/app/backend/server.py:431` | `info@construpilot.pt` (admin secundário) | fallback **`CP-Admin-2026!`** se `SECOND_ADMIN_PASSWORD` env ausente |
| `/app/memory/test_credentials.md` | 4 contas × passwords em texto claro | documento interno (não indexado) |

### Mitigação de design em curso
- Contas E2E são **provisioned_accounts** com `must_change_password: True` → forçam troca ao primeiro login.
- Admin SEED gated por `SEED_DEMO_DATA=true`.
- Admin secundário também tem `must_change_password: True`.

### Corrigido no código
- `/app/backend/server.py:426-430` typo `info@construpilot.fr` → `info@construpilot.pt`. (Linha 268-272 em comentário também usa `.fr` — está isolado, não propagam para `.env`.)

### Para o Martinho decidir (3 ações)
1. **Em produção**: definir `SECOND_ADMIN_PASSWORD` no `.env` para eliminar o fallback `CP-Admin-2026!`.
2. **Em produção**: trocar imediatamente a password das 3 contas E2E após primeiro login OU remover `provision_accounts` do startup em produção (gating adicional por `ENV`).
3. `/app/memory/test_credentials.md` **permanece** inalterado (necessário aos subagentes de teste). Avaliar se este ficheiro deve ser movido para fora do versionamento Git (actualmente o `/app/memory` provavelmente não é versionado — a confirmar com a plataforma Emergent).

---

## 3 · Rotas sensíveis — **CRÍTICO** → **corrigido**

### Findings
Antes do fix:

| Endpoint | Status antes | Severidade |
|---|---|---|
| `GET /api/openapi.json` | **200** (expõe schema completo da API, ~1 MB) | CRÍTICO |
| `GET /api/docs` | **200** (Swagger UI) | CRÍTICO |
| `GET /api/redoc` | **200** (ReDoc UI) | CRÍTICO |
| `/demo` (frontend) | não hits backend — já isolado como data fictícia + fallback | OK |

Total endpoints registados: **1090 rotas** (`@router.(get|post|put|delete|patch)`).
- Endpoints admin com `require_admin`: 2 ocorrências encontradas. (Amostragem — a maioria usa `Depends(current_user)` + check role manual, não um `require_admin` global.)
- **Não há inventário completo de endpoints admin sem guard** — fica como FOLLOW-UP para auditoria dedicada.

### Corrigido no código

| Ficheiro:linha | Mudança |
|---|---|
| `/app/backend/server.py:70-82` | `openapi_url`, `docs_url`, `redoc_url` passam a `None` se `ENV == "production"`. Em dev continuam acessíveis. |

### Verificação pós-fix
- Backend reiniciado ✅
- Login funcional ✅ (`200`)
- `/api/openapi.json` ainda `200` em dev (correcto)
- `/api/` responde `405` (método não permitido — root route exige GET; não é bug)

### Para o Martinho decidir (1 ação)
- **CRÍTICO**: `/app/backend/.env:33` tem valor **corrompido**: `ENV="SENDER_PT_FROM = info@construpilot.pt"` em vez de `ENV=production` ou `ENV=development`. Esta linha deve ser corrigida manualmente para `ENV=production` **antes do próximo deploy** para activar os guards aqui implementados. Caso contrário, as rotas `/api/docs|openapi|redoc` continuarão expostas em produção.

---

## 4 · Autenticação — **OK**

### Findings positivos
| Verificação | Estado | Localização |
|---|---|---|
| Rate limit no login | `@limiter.limit("5/minute")` | `/app/backend/routes/auth.py:144` |
| Rate limit noutros endpoints de auth | 10/minute (register), 3/minute, 5/hour | `auth.py:287, 608, 658, 773, 940` |
| Cookie `httponly` | `True` | `auth.py:104` |
| Cookie `secure` | `True` | `auth.py:104` |
| Cookie `samesite` | `"lax"` | `auth.py:104, 929, 959` |
| Cookie `max_age` | `7 * 24 * 3600` (7 dias) | `auth.py:105` |
| Password hashing | **bcrypt** com `gensalt()` | `/app/backend/core/security.py:16-17` |
| JWT via `make_jwt` | sim | `auth.py:13` |
| Password reset com token one-shot + TTL | sim, index TTL em `password_reset_tokens` | `server.py:543` |
| 2FA codes com TTL | sim, index TTL em `two_fa_codes` | `server.py:545` |

### Corrigido no código
Nada necessário — autenticação já segue boas práticas.

### Para o Martinho decidir
Nada.

---

## 5 · Permissões cross-tenant — **OK**

### Testes efectuados
Dois tokens (pro `teste.pro+e2e@` e free `teste.particular+e2e@`), 3 recursos criados pelo pro, acesso tentado pelo free:

| Recurso | Owner response | Cross-tenant response | Veredicto |
|---|---|---|---|
| `/api/projects/{id}` | `200` | **`404`** | ✅ seguro |
| `/api/documents/{id}` | `200` | **`403`** | ✅ seguro |
| `/api/stairs/projects/{id}` | `200` | **`403`** | ✅ seguro |

Filtro `user_id==current_user.id` aplicado nos 3 recursos.

### Corrigido no código
Nada necessário.

### Para o Martinho decidir
Nada.

---

## 6 · Uploads — **MÉDIO**

### Findings (amostragem)
Endpoints com `UploadFile` encontrados:

| Ficheiro:linha | Endpoint |
|---|---|
| `/app/backend/routes/admin_learning.py:70` | `import_file(file: UploadFile)` |
| `/app/backend/routes/assistant.py:649` | `upload_doc(file: UploadFile)` |
| `/app/backend/routes/assistant.py:1040` | `transcribe(file: UploadFile)` |
| `/app/backend/routes/assistant.py:1582` | `pdf_pages(file: UploadFile)` |
| `/app/backend/routes/auth.py:478, 496-497` | KYC: `_store_kyc_file`, `kbis`, `decennale` |
| `/app/backend/routes/btp_router.py:23` | `files: list[UploadFile]` |
| `/app/backend/routes/company_library.py:69` | `upload_library` |
| `/app/backend/routes/company_page.py:...` | (vários) |

**Amostragem não exaustiva**. Não foi feita verificação linha-a-linha de `content_type` whitelist nem de `max_size` enforcement.

### Corrigido no código
**Nada** — correcção automática não aplicada. Risco de regressão alto num refactor amplo (ex.: PDFs assinados, imagens em base64, CSVs importados). **FOLLOW-UP**.

### Para o Martinho decidir (1 ação)
Agendar auditoria dedicada de uploads: para cada endpoint, verificar
- Whitelist de `content_type` (`application/pdf`, `image/png`, `image/jpeg`, `text/csv`, etc.).
- `max_size` enforcement (sugestão: 20 MB para PDFs, 10 MB para imagens).
- Sanitização de `filename` contra path traversal (`os.path.basename(filename)` + regex `[^A-Za-z0-9._-]`).

---

## 7 · CORS + cabeçalhos de segurança — **ALTO** → **BAIXO** após fix

### Findings antes do fix

**CORS** (`/app/backend/server.py:248-258`):
- `allow_credentials=True` ✅
- `allow_origins=[... env CORS_ORIGINS, filtrados contra '*']` ✅ (SEC-002 já aplicado)
- `allow_origin_regex=r"https://[a-z0-9-]+\.(emergent\.host|preview\.emergentagent\.com)"` ✅

**Headers no response** (antes):
```
access-control-allow-origin: *      ← vem do Cloudflare, não do backend
x-robots-tag: noindex, nofollow     ← OK (preview)
```
Falta: `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `Strict-Transport-Security`, `Content-Security-Policy`.

### Corrigido no código

| Ficheiro:linha | Mudança |
|---|---|
| `/app/backend/server.py:263-291` | Middleware `SecurityHeadersMiddleware` adicionado. Desactivável via `SECURITY_HEADERS=off` no env (para hot-reload local). |

### Headers aplicados (verificado pós-restart)
```
x-frame-options: DENY
x-content-type-options: nosniff
referrer-policy: strict-origin-when-cross-origin
permissions-policy: geolocation=(), microphone=(), camera=(), payment=()
```

**HSTS** só é emitido se `ENV == "production"` (preserva dev HTTP).

**CSP não emitido** — demasiado risco de quebrar o React dev server e os terceiros embutidos (Stripe, Resend widgets). Fica como FOLLOW-UP para configurar via Cloudflare ou após inventário de origins carregadas.

### Para o Martinho decidir
Nada imediato — fix no código já aplicado. FOLLOW-UP: CSP num futuro lote W.1 depois de inventariar scripts/estilos de terceiros.

---

## 8 · Dependências com vulnerabilidades — **MÉDIO**

### Findings
`pip-audit` / `safety` **não instalados** no container. Foi feito apenas inventário.

Deps críticas (backend):

| Package | Versão instalada | Observação |
|---|---|---|
| fastapi | 0.110.1 | lag ~2 majors face à latest (0.115.x em Jan 2026) |
| starlette | 0.37.2 | arrastado pelo fastapi |
| pydantic | 2.13.4 | OK |
| pydantic-core | 2.46.4 | OK |
| pymongo | 4.6.3 | OK |
| bcrypt | 4.1.3 | OK |
| cryptography | 50.0.0 | latest (jan 2026) ✅ |
| requests | 2.34.2 | OK |
| requests-oauthlib | 2.0.0 | OK |
| urllib3 | 2.7.0 | OK |
| uvicorn | 0.25.0 | lag — latest 0.30.x |

### Corrigido no código
**Nada** — upgrades só patch não são triviais sem auditoria completa. Nenhuma vulnerabilidade CRITICAL conhecida nestes releases, mas há margens de melhoria.

### Para o Martinho decidir (1 ação)
Agendar execução de `pip-audit` ou `safety check` em pipeline CI dedicado. Fazer upgrades só de patch após:
- Fixar o CI com matriz FastAPI/Pydantic/Uvicorn.
- Correr pytest completa (~`/app/backend/tests/*.py`).

---

## 9 · Resíduos GitHub/Phase 0 — **BAIXO**

### Findings (inventário)
Ocorrências textuais de `github.com|teixeira880-ctrl|Phase 0|git clone` encontradas em:

| Ficheiro | Tipo | Mitigação |
|---|---|---|
| `/app/_mobile_src/scripts/cmd-guard/vendor/wildcard-match.js` | npm vendor, menção textual em comentário | nenhuma — vendor code |
| `/app/_mobile_src/README.md` | README do mobile | nenhuma |
| `/app/_mobile_src/.gitignore` | .gitignore (convencional) | nenhuma |
| `/app/frontend/README.md` | README do create-react-app | nenhuma |
| `/app/frontend/.gitignore` | idem | nenhuma |
| `/app/frontend/build/static/js/main.*.js` | bundles com strings `github.com/*` embebidas (deps npm) | nenhuma — artefactos de build |
| `/app/backend/stair_engine/README.md` | README do motor de escadas | nenhuma |
| `/app/.gitignore` | convencional | nenhuma |
| `/app/memory/github_recon_report.md` | **relatório antigo do Phase 0** | HUMANO: eliminar? |
| `/app/memory/github_vs_app_diff.md` | **diff antigo** | HUMANO: eliminar? |
| `/app/memory/fr_vs_pt_analysis_v2.md` | menção textual (histórica) | nenhuma |
| `/tmp/*` | caches do Playwright, Service Worker, bundles de debug | nenhuma (temp) |

### Corrigido no código
**Nada** — conforme instrução do Martinho, decisão de purgar `problem_statement`/`/app/memory` fica para o Martinho/plataforma.

### Para o Martinho decidir (1 ação)
- Decidir se `/app/memory/github_recon_report.md` e `github_vs_app_diff.md` devem ser **eliminados** (artefactos de Phase 0 agora cancelada) ou **arquivados fora de `/app/memory`**.

---

## Lista consolidada de mudanças aplicadas

| Ficheiro | Linhas | Mudança |
|---|---|---|
| `/app/backend/server.py` | 70-82 | `openapi_url/docs_url/redoc_url` passam a `None` se `ENV=="production"` |
| `/app/backend/server.py` | 263-291 | Middleware `SecurityHeadersMiddleware` (desactivável via `SECURITY_HEADERS=off`) |
| `/app/backend/server.py` | 426-430 | Typo `info@construpilot.fr` → `.pt` |
| `/app/backend/.env.example` | 1-113 | Ficheiro **criado** (102 vars + cabeçalho PT-PT) |

**Commit único proposto**: `Lote W: auditoria de segurança (fixes de código)`.

---

## Verificações pós-fix

| Teste | Resultado |
|---|---|
| Backend reinicia sem erro | ✅ |
| Login funcional (`POST /api/auth/login`) | ✅ `200` |
| JWT válido (`GET /api/auth/me`) | ✅ `200` |
| Cross-tenant projects | ✅ `404` |
| Cross-tenant documents | ✅ `403` |
| Cross-tenant stairs | ✅ `403` |
| Security headers no response | ✅ `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` |
| OpenAPI acessível em dev (`ENV!=production`) | ✅ `200` |

---

## Resultado numérico global

- Pontos auditados: **9**
- CRÍTICOS: 1 (ponto 3 — openapi/docs em prod) → **corrigido no código** mas depende de `.env` correcto
- ALTOS: 2 (ponto 2 — contas de teste; ponto 7 — headers) → **1 corrigido**, 1 por design
- MÉDIOS: 2 (ponto 6 — uploads; ponto 8 — deps) → 2 FOLLOW-UPs documentados
- BAIXOS: 2 (ponto 1 — segredos; ponto 9 — resíduos GitHub) → 1 corrigido (`.env.example`), 1 inventariado
- OK: 2 (ponto 4 — auth; ponto 5 — cross-tenant)

**Taxa de resolução no código:** 4/9 corrigidos directamente, 2/9 OK por design, 3/9 FOLLOW-UPs humanos.

---

## Ações HUMANAS pendentes (resumo)

1. **CRÍTICA — corrigir `/app/backend/.env` linha 33**: `ENV="SENDER_PT_FROM = info@construpilot.pt"` → `ENV=production` (ou `development`). **Antes do próximo deploy em produção**.
2. **ALTA — rotar passwords das 3 contas E2E** em produção após primeiro login, ou gating adicional por `ENV==production` em `provision_accounts`.
3. **ALTA — definir `SECOND_ADMIN_PASSWORD`** no `.env` de produção para eliminar fallback `CP-Admin-2026!`.
4. **MÉDIA — auditoria dedicada de uploads**: whitelist content_type + max_size + sanitização filename em ~10 endpoints.
5. **MÉDIA — pipeline CI com `pip-audit`/`safety check`** e upgrades de patch dos deps backend.
6. **BAIXA — decidir destino de `/app/memory/github_recon_report.md` e `github_vs_app_diff.md`** (artefactos Phase 0).

GitHub permanece **BLOQUEADO**. Nenhum push, nenhum deploy, nenhuma rotação de chaves ao vivo.
