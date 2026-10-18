# D1 — Diagnóstico read-only · Contas demo em produção `.pt`

**Data**: 2026-10-17 · **Scope**: código local apenas (D1). Prod em D2.

---

## Conclusão executiva — assunções do briefing a validar

A tarefa assume que existe um padrão `_seed_websummit_demo` em `.fr` para replicar em `.pt`. **Esse padrão não existe no repositório.** O código `.pt` e `.fr` partilham o **mesmo codebase** (sem pastas separadas `/app/construpilot.fr` / `.pt`), portanto não há nada específico de `.fr` para copiar.

Resumo do que **efectivamente existe**:

| Mecanismo | Localização | Alvo | Guard | Estado em prod |
|---|---|---|---|---|
| Seed demo clássico (5 contas `@construpilot.fr`) | `backend/server.py:426-456` | `admin@/demo@/client@/pro@/collegue@construpilot.fr` | `SEED_DEMO_DATA=true` + 5 vars `SEED_*_DEMO_PASSWORD` | **Desactivado** (`SEED_DEMO_DATA` não é `"true"` em prod) |
| Provisioning contas E2E `.pt` | `backend/core/provisioned_accounts.py` + chamada em `server.py` | 4 contas (Davi + 3 E2E `@construpilot.pt`) | Variáveis `PROVISION_DAVI_PASSWORD` + `TEST_E2E_*_PASSWORD` individualmente | Depende das vars em prod |
| Chaves i18n `login.demo_*` | `frontend/src/context/I18nContext.jsx:706-1101` (7 idiomas) | — | — | **Nunca referenciadas em componentes JSX** (artefacto de botão removido/nunca implementado) |
| Botão "Experimentar demo" | — | — | — | **Não existe** no `Login.jsx` (verificado 334 linhas, só botões Google OAuth, login tradicional e register) |
| Conta `demo.websummit@construpilot.pt` | — | — | — | **Não existe no código**. Zero ocorrências em todo `/app` |
| Projecto "Moradia Martins" | — | — | — | **Não existe no código**. Zero ocorrências em todo `/app` |

**Implicação**: o pedido não é "replicar `.fr` em `.pt`" — é **criar de raiz** um fluxo demo websummit em código partilhado, com guards fail-closed, para que **existia** em `.pt` depois do próximo deploy.

Antes de arrancar D2/D3, preciso de confirmação do utilizador em três pontos (ver secção "Perguntas ao fundador" no fim).

---

## D1.1 — Mapa das entradas demo em código local

### Frontend — pontos de entrada e CTAs

| Caminho | Linha | Elemento | Comportamento | Site |
|---|---|---|---|---|
| `src/pages/Landing.jsx` | 419 | CTA `"Experimentar gratuitamente"` | `<Link>` para fluxo normal (sem demo auto-login) | ambos |
| `src/pages/LandingPro.jsx` | 51 | CTA `"Experimentar o ConstruPilot"` (data-testid `pro-hero-primary-cta`) | `<Link to="/inscription">` registo normal | ambos |
| `src/pages/LandingPro.jsx` | 51 | CTA `"Ver a demonstração"` (data-testid `pro-hero-secondary-cta`) | Abre dialog de vídeo, não loga | ambos |
| `src/pages/BlogPost.jsx` | 115 | CTA `"Experimentar agora"` | `<Link>` registo normal | ambos |
| `src/pages/Features.jsx` | 119 | Texto: *"Crie uma conta em 30 segundos, ou teste com uma conta demo. Nenhum cartão bancário necessário."* | Só copy — nenhum botão demo correspondente | ambos |
| `src/pages/Login.jsx` | 1-334 | Login + registo tradicional + Google OAuth | **Zero botão demo**. Keys `login.demo_*` não são referenciadas | ambos |
| `src/components/landing/LandingLayout.jsx` | 36, 63 | CTA `"Experimentar"` / `"Experimentar durante 7 dias"` | `<Link to="/inscription">` | ambos |
| `src/components/SoftPaywall.jsx` | 78 | Botão `"Experimentar Premium"` | Trial Stripe, não demo | ambos |
| `src/context/I18nContext.jsx` | 706-1101 | Chaves `login.demo_hint`, `login.demo_over`, `login.demo_desc`, `login.demo_fail` (7 idiomas) | Keys existem mas **ninguém as usa**. Candidato forte: funcionalidade removida ou nunca completada | — |

### Backend — rotas de demo (não é o que se procura)

| Rota | Handler | Função real | Relevante para websummit? |
|---|---|---|---|
| `POST /api/structuro/studies/demo` | `routes/structuro.py:124` | Cria estudo técnico sintético (não login nem user) | ❌ |
| `POST /api/admin/demo-unlock` | `routes/admin.py:1132` | Concede entitlement Pro Business "démo 10 anos" ao admin que chama | ❌ (apenas admin) |
| `POST /api/admin/demo-lock` | `routes/admin.py:1155` | Reverte o unlock | ❌ |

**Zero rotas de "demo login"** no backend. Nenhuma `/api/auth/demo-login` ou equivalente.

### Backend — seeds de startup

**(A) `_seed_demo_org` + bloco `SEED_DEMO_DATA`** · `server.py:360-471`
- Guard: `os.environ.get("SEED_DEMO_DATA") == "true"` → **off em prod**.
- Cria 5 utilizadores com emails `@construpilot.fr` (admin, demo, client, pro, collegue). Password cada um lida de `SEED_*_DEMO_PASSWORD` (sem fallback hardcoded desde a sanitização de 2026-10-17).
- Cria organização "BTP Demo SAS" (`DEMO-2026`) com pro@ como owner e collegue@ como member.
- Dá entitlement `pro_business_monthly` a demo@ e pro@.
- **Impacto em prod**: inexistente (flag off).

**(B) Admin seed definitivo** · `server.py:472-502`
- `ADMIN_SEED_EMAIL` + `ADMIN_SEED_PASSWORD` do `.env` → cria conta admin.
- Idempotente, não reescreve password existente.
- Executado em cada startup. **Activo em prod se as vars estiverem definidas.**

**(C) Admin secundário / terciário / CM Rénov** · `server.py:504-...`
- 3 blocos adicionais, cada um lendo o seu próprio env var dedicado.
- Fail-closed se var ausente.

**(D) `provisioned_accounts.py`** · chamado em `server.py:410`
- 4 contas: `construtoradavi15@gmail.com` + 3 contas E2E `@construpilot.pt` (particular, pro, business).
- Cada conta requer a sua password em var dedicada (`PROVISION_DAVI_PASSWORD`, `TEST_E2E_PARTICULAR_PASSWORD`, `TEST_E2E_PRO_PASSWORD`, `TEST_E2E_BUSINESS_PASSWORD`).
- Fail-closed: se var em falta → `logger.warning` + skip (não cria conta).
- Executado em cada startup. **Activo em prod se as vars estiverem definidas.**

### Backend — rate limiting disponível

- `core/rate_limit.py` com `slowapi.Limiter` já integrado no `app` (ver `server.py:67-82`).
- Decorador `@limiter.limit("20/minute")` ou `@limiter.limit("10/hour")` usado em várias rotas.
- Pronto a aplicar à nova rota demo-login quando a implementarmos.

### Flag `is_demo` nos documentos

- Já existe em `permits` (radar) — mas é para marcar permits sintéticos de demonstração, não users.
- **Nenhuma flag equivalente em `users`**. Vamos ter de introduzir uma (ex: `demo_account: true` + `demo_source: "websummit_2026"`).

---

## D1.2 — Tabela por entrada demo

| Entrada | Caminho | Email alvo | Criação | Guard | Site | Hipótese prod `.pt` |
|---|---|---|---|---|---|---|
| Seed demo clássico | `server.py:426-456` | `demo pro .fr` (5 contas) | Startup | `SEED_DEMO_DATA=true` + passwords | Partilhado | ❌ off |
| Admin seed | `server.py:472-502` | admin owner | Startup | `ADMIN_SEED_EMAIL` + `_PASSWORD` | Partilhado | ✅ se vars em prod |
| Provisioning Davi | `provisioned_accounts.py:34` | `construtoradavi15@gmail.com` | Startup | `PROVISION_DAVI_PASSWORD` | Partilhado | ✅ se var em prod |
| Provisioning E2E particular | `provisioned_accounts.py:40` | `teste.particular+e2e@construpilot.pt` | Startup | `TEST_E2E_PARTICULAR_PASSWORD` | Partilhado | ✅ se var em prod |
| Provisioning E2E pro | `provisioned_accounts.py:45` | `teste.pro+e2e@construpilot.pt` | Startup | `TEST_E2E_PRO_PASSWORD` | Partilhado | ✅ se var em prod |
| Provisioning E2E business | `provisioned_accounts.py:49` | `teste.business+e2e@construpilot.pt` | Startup | `TEST_E2E_BUSINESS_PASSWORD` | Partilhado | ✅ se var em prod |
| Websummit demo pro | — | `demo.websummit@construpilot.pt` | — | — | — | ❌ **inexistente** |
| Websummit demo particular | — | `demo.particular.websummit@construpilot.pt` | — | — | — | ❌ **inexistente** |

Validação concreta no DB prod em D2.

---

## D1.3 — Delta `.fr` vs `.pt`

**Não aplicável.** `.pt` e `.fr` partilham o mesmo codebase e as mesmas seeds. Tudo o que existe em `.fr` existe também em `.pt` e vice-versa. A única diferença operacional entre os dois domínios é:

1. Domínio HTTP (`construpilot.pt` vs `construpilot.fr`).
2. `.env` eventualmente distinto por deployment (ex: `SENDER_PT_FROM` vs `SENDER_FR_FROM` em `/app/backend/.env`, com guards por `ENV`).
3. Locale default (i18n `pt` vs `fr`) determinado pelo header `Accept-Language` ou user profile.

**Delta real**: para o websummit demo em `.pt` precisamos de **criar** o padrão, não replicar. Vai ficar num ficheiro novo (ex: `backend/core/websummit_seed.py`) chamado após o `provisioned_accounts.py` no startup.

---

## Resumo "o que precisamos de construir"

1. **Novo módulo** `backend/core/websummit_seed.py` que, no startup, cria idempotentemente:
   - Utilizador `WEBSUMMIT_DEMO_EMAIL_PT` com plano Pro, flag `demo_account: true`, `demo_source: "websummit_2026"`.
   - Utilizador `WEBSUMMIT_DEMO_EMAIL_PARTICULAR_PT` com plano free, flags iguais.
   - Entitlement Pro para o primeiro.
   - Projecto associado `"Moradia Martins"` com planta sintética (reusa `tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png`).
   - Guard fail-closed: skip cada conta se a sua password não estiver em env; nunca criar com password em claro.

2. **Nova rota** `POST /api/auth/demo-login` que:
   - Recebe um identificador de perfil (`pro` ou `particular`) sem receber credenciais.
   - Valida que o perfil pedido corresponde a uma conta `demo_account: true, demo_source: "websummit_2026"`.
   - Lê a password do env, faz autenticação interna, devolve cookie de sessão.
   - Rate limit `@limiter.limit("10/hour")` por IP.
   - Fail-closed: 503 se vars ausentes; 404 se conta não existe.

3. **Botão UI** em `Login.jsx` (ou landing dedicada `/demo`):
   - Reusa as keys já existentes `login.demo_hint/over/desc/fail`.
   - Chama `POST /api/auth/demo-login` com `profile: "pro"` ou `"particular"`.
   - Redirect para dashboard em caso de sucesso.

4. **Isolamento das contas demo**:
   - Flag `demo_account: true` + filtragem nos endpoints admin (listas de clientes, exportações, bulk emails).
   - Nunca receber emails marketing (CRM Lite já tem opt-out — reaproveitar).
   - Nunca podem ser promovidas a admin (guard em `/admin/promote` ou equivalente).

5. **Documentação**:
   - `SECURITY.md` secção nova com nomes de env vars.
   - `auth_testing.md` com instruções para `e1_tester`.

---

## Perguntas ao fundador — bloqueio antes de D2

Preciso de confirmar 3 pontos antes de arrancar D2 (teste prod) e D3 (fix):

1. **Padrão `.fr` existe mesmo?** O briefing diz "em `.fr` já existe um seed/padrão `_seed_websummit_demo`". **Não encontrei nenhum.** Pode ser que:
   - (a) o briefing se refira a uma funcionalidade **planeada** que ainda não foi implementada; vou **criar de raiz** com o nome `websummit_seed_pt`.
   - (b) existe num branch git separado que não está no `main` actual; se é o caso, dá-me o nome do branch e eu inspecciono.
   - (c) existe num repo externo (`construpilot.fr_1` que mencionaste); se é o caso, dá-me acesso de leitura ao URL e eu replico.
   
   **Default se não responderes**: assumo (a) e crio de raiz.

2. **Nomes das variáveis finais** — confirma estes nomes (sem valores):
   - `WEBSUMMIT_DEMO_EMAIL_PT` + `WEBSUMMIT_DEMO_PASSWORD_PT` (conta pro)
   - `WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT` + `WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT` (conta particular free)
   - Business websummit: incluir ou omitir? O briefing diz "(opcional) `BUSINESS_DEMO_EMAIL_PT` + `BUSINESS_DEMO_PASSWORD_PT` se o padrão `.fr` tiver business — senão omite". Como não há padrão `.fr`, decido **omitir** (menos superfície de ataque, menos segredos a gerir). Confirma ou pede para incluir.

3. **Botão de demo-login nativo ou landing dedicada?**
   - (A) Adicionar botão em `Login.jsx` ao lado do form tradicional (reaproveita keys i18n já existentes).
   - (B) Página dedicada `/demo` com 2 CTAs (Pro / Particular) e UI explicativa.
   - (C) Ambos.
   
   **Default se não responderes**: (A), mais simples e reutiliza i18n.

---

## Follow-ups menores detectados (não bloqueiam D2)

- `/app/frontend/src/context/I18nContext.jsx` tem 7 traduções de `login.demo_*` órfãs. Se decidirmos manter o botão demo, aproveitamos; se não, candidato a limpeza futura.
- `engines/ai.py:487` HELP_KB menciona "Experiência com contas de demonstração disponíveis na página de início de sessão" — texto desalinhado da realidade actual. Será corrigido naturalmente quando o botão demo voltar.

---

**Estado**: D1 completo. Aguarda resposta às 3 perguntas antes de arrancar D2.
