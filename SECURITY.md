# Política de Segurança — ConstruPilot

Versão: 2026-10-15 · Mantida sincronizada com os testes de regressão em
`backend/tests/test_security_policy.py`.

---

## 1. Detecção de ambiente

- **Fonte única**: `backend/core/environment.py`.
- **Valores aceites como relaxado**: `development`, `preview`.
- **Qualquer outro valor** (incluindo vazio, mal formatado ou corrompido) é
  tratado como **produção** (comportamento *fail-closed*). O boot emite
  `WARNING` no log quando o valor é inválido.
- **Nenhum outro ficheiro** do backend lê `ENV` directamente. Importar
  `is_production()`, `is_relaxed()`, etc. deste módulo.
- Teste automático: `test_env_read_only_in_core_environment`.

## 2. Segredos e credenciais

- Todas as credenciais (Stripe, Resend, OpenAI, Anthropic, Gemini, Mongo,
  JWT, admin passwords, chaves SMTP) **apenas** em variáveis de ambiente
  carregadas de `backend/.env`.
- Nunca em código, logs persistidos, ou commits versionados.
- `.env` está em `.gitignore`. Documentação pública em `backend/.env.example`
  (sem valores).
- Scripts operacionais (`backend/scripts/*`) exigem a password via env e
  abortam com erro se não definida — nenhum fallback literal.
- Teste automático: `test_no_hardcoded_secrets`.

## 3. Documentação pública da API

- `openapi.json`, `/api/docs` (Swagger), `/api/redoc` fechados em produção.
- Guard: `openapi_url = None if is_production() else "/api/openapi.json"`
  (idem `docs_url`, `redoc_url`).
- Fonte única: `backend/core/environment.py`.

## 4. CORS

- **Produção**: *allowlist* vinda de `CORS_ORIGINS_PROD`
  (default `https://construpilot.pt, https://www.construpilot.pt`).
  `allow_methods` restrito a `GET/POST/PUT/PATCH/DELETE/OPTIONS`.
  Nenhum regex (preview URLs não aceites em prod).
- **Dev/preview**: lista do `CORS_ORIGINS` + `allow_origin_regex` para subdomínios
  Emergent (`emergent.host`, `preview.emergentagent.com`).
- `allow_credentials=True`; `allow_origins` nunca contém `*` quando
  `allow_credentials=True`.

## 5. Seed de demonstração

- **Desligado por defeito**.
- Activar explicitamente: `SEED_DEMO_DATA=true` no `.env`.
- Quando desligado, `provisioned_accounts.py` **não cria** contas E2E com
  passwords em claro.

## 6. Admin secundário

- *Fail-closed*: sem `SECOND_ADMIN_PASSWORD` definida (vazia ou ausente),
  a conta `info@construpilot.pt` **não é criada**. Nenhum fallback literal.
- `must_change_password: True` ao primeiro login (forçado).

## 7. Uploads

- Todos os endpoints `UploadFile` passam por `core.uploads.validate_upload`.
- Validação obrigatória:
  - *Whitelist* de `content_type` (ex.: `ALLOWED_IMAGE`, `ALLOWED_DOCUMENT`,
    `ALLOWED_CAD`, `ALLOWED_AUDIO`, `ALLOWED_IMPORT`, `ALLOWED_OFFICE`).
  - `max_mb` por endpoint (default global `MAX_UPLOAD_MB=20`, limites
    específicos preservados — ex.: 10 MB em KYC, 15 MB em learning, 25 MB
    em CAD).
  - `sanitize_filename` contra *path traversal* / caracteres perigosos.
- CAD com `application/octet-stream`: validação adicional por *magic-bytes*
  (DWG `AC10xx-AC10xx`, DXF ASCII/binário, IFC/STEP `ISO-10303-`).
- Teste automático: `test_all_upload_endpoints_use_validate_upload`
  (inclui lista de pendentes conhecidos — ver FOLLOW-UP Y.2).

## 8. Cabeçalhos de segurança

Middleware `SecurityHeadersMiddleware` aplicado a todas as respostas HTTP:

- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  **apenas** em produção (via `is_production()`).

Desactivável em dev via `SECURITY_HEADERS=off`.

## 9. Autenticação

- Hash de passwords: **bcrypt** com `gensalt()`.
- Sessão via cookie **HTTPOnly + Secure + SameSite=lax**, `max_age=7 dias`.
- JWT emitido via `make_jwt` em `routes/auth.py`.
- Rate-limit no login: `@limiter.limit("5/minute")` por IP (slowapi).
- Password reset: tokens one-shot com TTL via índice Mongo.
- 2FA: códigos com TTL via índice Mongo.
- Admin secundário *fail-closed* (ver §6).

## 10. Testes de regressão

`backend/tests/test_security_policy.py` corre em cada CI.
O build **falha** se:

1. password/chave hardcoded detectada em código (fora de `tests/`,
   `.env.example`, `memory/` com justificação, e `provisioned_accounts.py`
   gated por `SEED_DEMO_DATA`),
2. endpoint `UploadFile` sem `validate_upload` detectado fora da lista
   explícita `UPLOADFILE_MIGRATION_PENDING` (follow-up documentado),
3. leitura directa de `ENV` fora de `core/environment.py` ou `tests/`,
4. módulo `environment` não falha para produção com `ENV=""` ou valor
   corrompido (patterns reais testados: vazio + copy-paste bug
   `"SENDER_PT_FROM = ..."`).

## 11. Produção vs preview

- Preview: `https://construpilot-recon.preview.emergentagent.com`
  (ambiente de desenvolvimento, dados de teste, `ENV=development`).
- Produção: `https://construpilot.pt`
  (ambiente *live*, `ENV=production`).
- Nenhum teste automatizado contra produção. Debug em produção **só**
  mediante autorização explícita.

---

**Follow-ups humanos pendentes** (ver `memory/lote_v_regression_report.md`,
`memory/lote_w_security_audit_report.md`, `memory/lote_x_hardening_report.md`):

1. 🔴 Rotar passwords das 3 contas E2E em produção.
2. 🟠 Definir `SECOND_ADMIN_PASSWORD` no `.env` prod se admin secundário for
   necessário em produção.
3. 🟡 Migrar os 17 endpoints `UploadFile` restantes
   (`UPLOADFILE_MIGRATION_PENDING` em `tests/test_security_policy.py`).
4. 🟡 Pipeline CI com `pip-audit` + `safety check` + upgrades de patch.

---

## 12. Zero segredos em claro em `/app` — regra permanente

**Regra absoluta** (aplicada 2026-10-17 em diante): nenhum valor em claro de
password, chave de API, token, cookie de sessão ou qualquer segredo pode
existir em `/app` fora de `/app/backend/.env`. Aplica-se a:

- Código fonte (`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, etc.).
- Scripts operacionais (seed, demo recorders, auditorias, migrações).
- Testes automatizados (incluindo Playwright e pytest).
- Documentação (`.md`, `.txt`, `.log`), relatórios e CHANGELOGs.
- Commits, PRs e mensagens associadas.
- `print()`, logs, comentários.

Mesmo para descrever o que foi substituído, usar sempre o **tipo** do segredo
("password da conta admin", "token Stripe", "chave Resend") — nunca o valor
nem os primeiros caracteres.

### 12.1 Como ler credenciais em código

- **Python**: `os.environ.get("<KEY>")` com fail-closed se vazio/`<redacted>`.
- **Node/Playwright**: `process.env.<KEY>` com `process.exit(2)` se ausente.
- **curl/shell**: resolver via `$VAR` do shell (nunca interpolar literais).
- Fonte canónica das credenciais operacionais: `/app/backend/.env` (não
  commitado, nunca copiado para relatórios). Nomes das variáveis documentados
  em `/app/memory/test_credentials.md` e `/app/memory/auth_testing.md`.

### 12.2 Tolerância legada — test fixtures sintéticas

Os ficheiros `/app/backend/tests/test_iter*.py` (padrão de 127 ficheiros
históricos) ainda contêm strings de passwords sintéticas usadas como
**fixtures de pytest** — valores arbitrários passados pelo próprio teste
para criar utilizadores fictícios na BD de teste local e logo os validar.

Caracterização:

- **Não são segredos.** Não dão acesso a nenhuma conta de produção.
- `SEED_DEMO_DATA=false` por omissão em prod → as contas correspondentes
  nunca existem no ambiente *live*.
- Em dev/CI, as mesmas strings podem coincidir com seeds locais; o risco é
  nulo (ambiente isolado).

**Decisão explícita (2026-10-17)**: estes 127 ficheiros são **tolerância
legada**, não precedente. Mantidos como estão por pragmatismo (purga
automática arriscava partir fixtures com scopes diferentes).

### 12.3 Nova regra permanente para testes

Qualquer teste **novo** (criado após 2026-10-17) **deve** ler credenciais do
ambiente. Zero valores em claro no código, mesmo em fixtures sintéticas:

```python
# Python / pytest
import os
import pytest

PWD = os.environ.get("TEST_PRO_PASSWORD")
if not PWD or PWD == "<redacted>":
    pytest.skip("TEST_PRO_PASSWORD ausente — fixture pulada", allow_module_level=True)
```

```js
// Node / Playwright
const PASSWORD = process.env.TEST_PRO_PASSWORD;
if (!PASSWORD) {
  console.error("TEST_PRO_PASSWORD ausente. Abort.");
  process.exit(2);
}
```

A fonte central para credenciais de teste em Python é
`/app/backend/tests/creds.py` (reescrita em 2026-10-17 sem fallbacks
hardcoded). Novos testes devem importar daí ou ler directamente do ambiente.

Code review deve rejeitar qualquer PR que introduza nova string literal com
aparência de credencial em qualquer `.py`/`.js`/`.jsx`/`.ts`/`.tsx` novo.
