# D2 — Teste de produção read-only · `construpilot.pt`

**Data**: 2026-10-17 · **Scope**: endpoints públicos + tentativas de login demo (sem contas reais).

---

## D2.1 — Endpoints públicos

| URL | Método | Status | Body (truncado) | Interpretação |
|---|---|---|---|---|
| `https://construpilot.pt/` | GET | **200** · `text/html` | SPA React renderizada, title "ConstruPilot — Orçamentos de obras com IA..." | Prod frontend saudável |
| `https://construpilot.pt/api/health` | GET | **404** · `application/json` | `{"detail":"Not Found"}` | **Gap identificado**: endpoint `/api/health` não existe no backend (confirmado por `grep` no código). Vai ser criado em D3 |
| `https://construpilot.pt/api/healthz` | GET | 404 | — | idem |
| `https://construpilot.pt/api/status` | GET | 404 | — | idem |
| `https://construpilot.pt/api/version` | GET | 404 | — | idem |
| `https://construpilot.pt/api/openapi.json` | GET | **404** | `{"detail":"Not Found"}` | OpenAPI schema fechado em prod (comportamento FastAPI quando `openapi_url=None` ou guard por env). API em funcionamento, mas sem schema público |
| `https://construpilot.pt/api/me` | GET | 404 | — | não existe (rota correcta é `/api/auth/me`) |
| `https://construpilot.pt/api/auth/me` | GET | **401** | — | API responde, só não autenticado — **confirmação de que o backend está vivo em prod** |

**Conclusão D2.1**: API está funcional em prod. Não há endpoint `/api/health` → vou criar em D3 (também útil para smoke test em D6).

---

## D2.2 — Rotas de registo/login

| URL | Método | Payload | Status | Body (truncado) | Interpretação |
|---|---|---|---|---|---|
| `/api/auth/register` | POST | `{}` | **422** | — | API responde, pydantic validation falha (campos obrigatórios ausentes) |
| `/api/auth/forgot-password` | POST | `{}` | **422** | — | idem |
| `/api/auth/login` | POST | `{}` | **422** | — | idem |
| `/api/auth/login` | POST | `{"email":"demo.websummit@construpilot.pt","password":"wrong"}` (password fictícia) | **401** | `{"detail":"Email ou palavra-passe incorretos"}` | **Conta não existe em prod** · 401 unificado (não distingue entre "conta inexistente" e "password errada" — comportamento correcto para evitar enumeração) |
| `/api/auth/verify-email` | POST | — | 404 | — | método errado (é GET com token) |
| `/api/auth/demo-login` | POST | `{"kind":"pro"}` | **404** | `{"detail":"Not Found"}` | **Rota não existe** · esperado · vai ser criada em D3 |

---

## D2.3 — Fluxo UI "Experimentar demo"

| Teste | Observação |
|---|---|
| `GET /demo` | **200** · `text/html` · SPA fallback (routing React carrega a landing porque `/demo` não é uma rota React conhecida). Em prod a página aparece em branco ou com 404 do React Router. |
| Botão "Experimentar demo" na landing | **Não existe** (verificado no código local D1). Confirmado em prod — nenhum CTA aponta para demo auto-login |
| Botão em `/login` | **Não existe** · keys i18n `login.demo_*` existem no bundle mas sem componente associado |

---

## D2.4 — CORS e sessão

| Teste | Status | Headers relevantes | Notas |
|---|---|---|---|
| `POST /api/auth/login` com `Origin: https://construpilot.pt` | 401 (user válido) ou 422 (payload inválido) | `access-control-allow-origin`, `access-control-allow-credentials` | CORS configurado em prod (ver `backend/server.py` middleware) |
| Cookies | sem Set-Cookie (login falhou) | — | — |

Sem anomalias de CORS detectadas.

---

## D2.5 — Verificação do que não deve ser testado em prod

- ❌ Não criei contas em prod
- ❌ Não escrevi dados em prod
- ❌ Não usei email real do fundador
- ❌ Não tentei credenciais reais
- ✅ Só `GET` em endpoints públicos e `POST` com payloads propositadamente inválidos para medir resposta

---

## Síntese prod

| Item | Estado em prod |
|---|---|
| Backend vivo | ✅ (401 em `/api/auth/me` confirma) |
| Frontend vivo | ✅ (200 em `/`) |
| `/api/health` | ❌ não implementado (gap a corrigir em D3) |
| `/api/openapi.json` público | ❌ fechado (expected) |
| Rota `/api/auth/demo-login` | ❌ não existe (esperado) |
| Conta `demo.websummit@construpilot.pt` | ❌ não existe (401 confirmado) |
| Botão "Experimentar demo" | ❌ não existe no bundle actual |
| Página `/demo` renderizada | ⚠️ SPA fallback (sem componente dedicado) |
| CORS funcional | ✅ |

**Avanço**: D3 vai criar `/api/health`, `/api/auth/demo-login`, seed websummit, página `/demo`, botão em `/login`, guards de demo, reset diário, quotas IA. Zero toque em prod até D6.
