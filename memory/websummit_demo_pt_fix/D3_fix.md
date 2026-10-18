# D3 — Correcção local · Web Summit demo PT

**Data**: 2026-10-17 · **Deploy**: zero · **Testes locais**: 23/23 verde (ver `D4_tests.md`).

---

## Ficheiros criados / modificados

### Backend (novo)
- `/app/backend/core/websummit_seed_pt.py` — seed idempotente das 2 contas + projecto "Moradia Martins" + helpers de login.
- `/app/backend/core/demo_guards.py` — `ensure_not_demo`, `consume_demo_ai_quota` (20/dia), `demo_blocked_response`.
- `/app/backend/core/demo_middleware.py` — intercept global para 403 `demo_blocked` em paths sensíveis (pagamentos, envios, SMS, facturação, assinatura, edit profile, change-password).
- `/app/backend/routes/auth_demo.py` — `POST /api/auth/demo-login` (rate limit 10/min/IP) + `GET /api/auth/demo-status` (público).
- `/app/backend/routes/health.py` — `GET /api/health` e `/api/healthz` (ping Mongo, para smoke tests pós-deploy).
- `/app/backend/routes/admin_demo.py` — `POST /api/admin/demo/reset` + `GET /api/admin/demo/status` (admin real only).

### Backend (modificado)
- `/app/backend/server.py` — includes dos 4 novos routers, chamada ao `seed_websummit_demo_pt` no startup (sempre, fail-closed), scheduler APScheduler job diário 04:00 UTC para reset dos dados sintéticos, `DemoActionsMiddleware` adicionado antes do SlowAPIMiddleware, import de `verify_password`.
- `/app/backend/.env` — 4 chaves adicionadas (append-only) com valor `<redacted>`: `WEBSUMMIT_DEMO_EMAIL_PT`, `WEBSUMMIT_DEMO_PASSWORD_PT`, `WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT`, `WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT`. Nenhuma chave existente removida.

### Frontend
- `/app/frontend/src/pages/DemoPage.jsx` — novo, página dedicada acessível em `/demo/entrar` e `/demo-entrar`. 2 CTAs (Pro / Particular). Sem credenciais no bundle; chama `POST /api/auth/demo-login` e deixa o backend definir cookie HttpOnly.
- `/app/frontend/src/pages/Login.jsx` — adicionado bloco opcional "Experimentar demo" (data-testid `demo-login-block`) com 2 botões (Pro `demo-login-pro-btn` + Particular `demo-login-particular-btn`), só renderizado se `/api/auth/demo-status` devolver `pro:true` ou `particular:true`.
- `/app/frontend/src/context/AuthContext.jsx` — novo helper `demoLogin(kind)` que chama o endpoint sem passar credenciais.
- `/app/frontend/src/context/I18nContext.jsx` — adicionadas 17 chaves novas: `login.demo_pro`, `login.demo_particular`, `demo_page.*`, `demo.blocked_toast`. PT + EN implementadas; outros idiomas caem no fallback do JSX.
- `/app/frontend/src/App.js` — rotas `/demo/entrar` e `/demo-entrar` apontando para `DemoPage`. `/demo` original (showcase interactivo) preservado intacto.

### Testes
- `/app/backend/tests/test_websummit_demo.py` — 15 testes pytest (seed, guards, middleware, quota, reset).
- `/app/frontend/e2e/websummit_demo.spec.js` — 8 testes Playwright standalone (render, bundle, cookie HttpOnly, rate limit, guards, 503 fail-closed).

### Documentação
- `/app/SECURITY.md` — nova secção 13 "Modo demo Web Summit".
- `/app/memory/auth_testing.md` — bloco novo sobre como testar demo login.

---

## Decisões arquitecturais tomadas

### D3.1 — Guards: middleware global vs decoradores por rota
**Escolhido**: middleware global (`DemoActionsMiddleware`) com regex de paths sensíveis.
**Porquê**: há 25+ rotas de envio/pagamento espalhadas por 15 ficheiros. Instrumentar uma a uma era frágil e custoso. Centralizar num middleware garante que novas rotas de envio ficam **automaticamente** bloqueadas desde que sigam a convenção de nome (`/send`, `/pay`, `/sms`, etc.).
**Trade-off**: regex pode falhar em casos exóticos. Mitigação: lista explícita + testes unitários em `test_demo_middleware_matches_critical_paths`. Rotas que não casem com regex podem complementar com `Depends(ensure_not_demo)` no handler.

### D3.2 — Password nunca ao frontend
**Mecanismo**: `POST /auth/demo-login` recebe só `{kind: "pro"|"particular"}`. Backend lê password do env, faz `verify_password` interno, cria `user_sessions` com `is_demo=True`, define `Set-Cookie` HttpOnly `samesite=lax` `secure=true`. Response body **omite** `password_hash`, `password`, `token_version`. Validado em pytest (`test_public_demo_does_not_leak_password_or_hash`) e Playwright (`test_3_response_no_password_leak`).

### D3.3 — Rate limit
**Escolhido**: 10 pedidos/minuto/IP via slowapi existente. Equilibra protecção contra brute-force com UX normal (QR code → clique → login).
**Validado**: `test_5_rate_limit_triggers_429` confirma 429 ao 11º/12º pedido.

### D3.4 — Flag `is_demo` em 3 níveis
1. **User**: `users.is_demo = True`, `users.demo_source = "websummit_2026"` → impede promoção a admin futura.
2. **Session**: `user_sessions.is_demo = True` → middleware verifica em cada request.
3. **Response pública**: `_public_demo` inclui `is_demo` para frontend sinalizar "Modo demo" no header/footer.

### D3.5 — Quota IA 20/dia
Hard-coded em `demo_guards.DEMO_AI_QUOTA_DAILY = 20`. Reset diário via APScheduler cron 04:00 UTC + fail-safe inline (compara `demo_quota_date` com hoje).
**Porquê 20**: baseado em custo médio por chamada IA (~0.01 €) × 20 = 0.20 €/dia × 2 contas = 0.40 €/dia. Suficiente para demonstrações no stand sem queimar créditos. Ajustável facilmente.

### D3.6 — Reset diário
Dois mecanismos complementares:
1. **APScheduler cron** 04:00 UTC — limpa quotes, takeoffs, photos, project_documents, assistant_messages, coach_messages, activity_log, notifications, email_logs, stripe_customer_actions criados pela conta demo. **Preserva**: user doc, projecto "Moradia Martins", entitlements.
2. **Endpoint manual** `POST /api/admin/demo/reset` — admin real pode disparar reset on-demand (p.ex. a meio do dia no stand).

### D3.7 — Alinhamento com `TEST_PRO_*_PT` da ronda anterior
As chaves `TEST_PRO_EMAIL_PT` + `TEST_PRO_PASSWORD_PT` criadas na ronda do vídeo (ainda com placeholders `<redacted>`) são **mantidas como estão**. Têm propósito diferente:
- `TEST_PRO_*_PT`: credenciais de uma **conta real pro** (criada pelo fundador manualmente) para scripts de teste automatizados e vídeo demo.
- `WEBSUMMIT_DEMO_*_PT`: credenciais de uma **conta sintética demo** criada e gerida pelo seed, com `is_demo=True` e guards activos.

Não consolidei para evitar colisão semântica. Documentei em `/app/memory/test_credentials.md`.

### D3.8 — Rota `/demo` existente
Preservada. Já era usada para o showcase interactivo com `scenarios.json`. Nova rota `/demo/entrar` (alias `/demo-entrar`) é dedicada ao login auto do Web Summit. QR code do stand deve apontar para `/demo/entrar`.

---

## Fluxo end-to-end validado (local)

```
                                                        
Browser → GET /demo/entrar                              
  → React renderiza DemoPage.jsx                        
  → Fetch /api/auth/demo-status                         
    → {pro: true, particular: true}                     
  → User clica "Entrar como profissional"               
                                                        
Browser → POST /api/auth/demo-login {kind: "pro"}       
  → Backend lê WEBSUMMIT_DEMO_PASSWORD_PT do env        
  → verify_password OK                                  
  → user_sessions.insert({is_demo: True, ...})          
  → Set-Cookie: session_token=... HttpOnly SameSite=lax 
  → Response body: {user: {is_demo: true}, token: "..."}
    (zero password / password_hash)                     
                                                        
Browser → GET /dashboard (navega automaticamente)       
  → Cookie enviado, backend reconhece sessão demo       
  → UI mostra projecto "Moradia Martins"                
                                                        
Browser → POST /api/documents/.../send                  
  → DemoActionsMiddleware detecta cookie demo           
  → Devolve 403 {error: "demo_blocked", action: ...}    
  → Frontend mostra toast "Modo demo — crie conta..."   
                                                        
Cron 04:00 UTC                                          
  → reset_websummit_demo_data_pt()                      
  → Limpa dados sintéticos acumulados                   
  → Preserva user, projecto base, entitlements          
                                                        
```

---

## Smoke test local

Verificações passadas antes de reverter o `.env` para `<redacted>`:
- Seed criou user pro + user particular + entitlement Pro + projecto "Moradia Martins".
- `/api/auth/demo-login` com kind=pro devolveu 200, cookie HttpOnly definido.
- Middleware bloqueou `/api/documents/.../send` → 403 `demo_blocked` com action correcta.
- Middleware bloqueou `/api/auth/change-password` → 403.
- `/api/health` → 200 com `mongo: true`.
- `/api/openapi.json` → 200 com todas as rotas novas visíveis.

Após reverter `.env`:
- `/api/auth/demo-status` → `{pro: false, particular: false}` (correcto, fail-closed).
- Backend arranca sem erros.
- Zero segredos em `/app` fora de `.env`.
