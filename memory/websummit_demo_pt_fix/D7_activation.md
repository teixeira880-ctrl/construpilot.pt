# D7 — Activação do seed WebSummit em produção

**Data abertura**: 2026-02-16 · **Estado**: ⏳ **A aguardar restart do backend em produção**

---

## Contexto

O fundador comunicou "segredos ok" — os 4 segredos
`WEBSUMMIT_DEMO_EMAIL_PT`, `WEBSUMMIT_DEMO_PASSWORD_PT`,
`WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT`,
`WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT`
foram adicionados nos Production Secrets de `construpilot.pt`.

Este checkpoint D7 verifica a activação efectiva (seed + guards + screenshot) sem
expor valores de segredos nem usar contas reais.

---

## 1. Verificação baseline (ANTES do restart)

Executado directamente contra `https://construpilot.pt` a partir do pod preview,
sem credenciais, só para capturar o estado inicial.

| # | Request | HTTP | Body (resumo) | Interpretação |
|---|---------|------|---------------|---------------|
| B1 | `GET /api/health` | 200 | `{"status":"ok","mongo":true}` | Backend prod vivo. |
| B2 | `GET /api/auth/demo-status` | 200 | `{"pro":false,"particular":false}` | **Env vars NÃO visíveis no processo backend** — restart ainda não ocorreu desde a adição dos segredos. |
| B3 | `POST /api/auth/demo-login {"kind":"pro"}` | 503 | `{"detail":{"error":"demo_unavailable"}}` | Fail-closed OK — não há contas provisionadas, rejeita. |
| B4 | `POST /api/auth/demo-login {"kind":"particular"}` | 503 | `{"detail":{"error":"demo_unavailable"}}` | Idem particular. |

**Conclusão baseline**: implementação está correctamente fail-closed. Falta
apenas que o processo backend em prod seja reiniciado para que `os.environ`
contenha os 4 segredos. O código em `/app/backend/server.py:434-441` corre o
`seed_websummit_demo_pt(...)` no `@app.on_event("startup")`, e
`core/websummit_seed_pt.py:276-282` lê as env vars em runtime via `_config()`.

Nenhuma acção programática de restart em prod está disponível para o agente
dentro do pod preview — é obrigatória uma acção do fundador no dashboard
Emergent.

---

## 2. Acção manual exigida ao fundador

### 2.1 Passo exacto no dashboard Emergent

1. Abrir **Emergent Dashboard** → menu lateral **Deployments**.
2. Seleccionar o deployment com domínio `construpilot.pt` (produção).
3. Confirmar que as 4 chaves de segredos existem em
   **Secrets / Environment Variables** (sem necessidade de reabrir valores):
   - `WEBSUMMIT_DEMO_EMAIL_PT`
   - `WEBSUMMIT_DEMO_PASSWORD_PT`
   - `WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT`
   - `WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT`
4. Procurar o botão **Restart** no topo (ou canto superior direito) do painel
   do deployment. O botão aparece ao lado de **Redeploy**.
   - **Se o botão `Restart` existir**: clicar `Restart`.
   - **Se não existir `Restart`, apenas `Redeploy`**: clicar `Redeploy`
     (equivalente a restart + possível rebuild de imagem; sem efeito colateral
     porque o código já está em prod).
5. Confirmar o diálogo de confirmação (se aparecer).
6. Aguardar o indicador do dashboard voltar a `Running` / `Healthy`
   (tipicamente 30–90 s).

### 2.2 Validação imediata que o fundador pode fazer

```bash
curl -s https://construpilot.pt/api/auth/demo-status
# esperado: {"pro":true,"particular":true}
```

Se devolver `true/true` → avisar o agente para prosseguir com a verificação
completa. Se continuar `false/false` após 2 minutos → re-tentar restart ou
contactar suporte Emergent (segredos podem não estar a propagar ao container
backend).

---

## 3. Plano de verificação pós-restart (a executar quando fundador confirmar)

Os 6 passos abaixo são disparados após `demo-status` reportar `true/true`.
Nenhum valor de segredo é dumpado em logs/relatório.

### 3.1 Lista dos passos

| # | Teste | Endpoint | Esperado |
|---|-------|----------|----------|
| P1 | Status público | `GET /api/auth/demo-status` | 200, `{"pro":true,"particular":true}` |
| P2 | Logs seed summary | logs Emergent prod | linha `websummit demo seed summary: {'pro': 'created'|'updated', 'particular': 'created'|'updated', 'project': 'created'|'updated'}` — **colada pelo fundador**, agente não tem acesso programático |
| P3 | Login demo Pro | `POST /api/auth/demo-login {"kind":"pro"}` | 200, cookie HttpOnly `session_token`, body sem password/hash/token em claro (campo `token` existe mas é JWT opaco — ok) |
| P4 | Projecto Moradia Martins | `GET /api/projects` (com cookie demo Pro) | 200, lista contém projecto `Moradia Martins`, zero PII externa no body |
| P5a | Envio email bloqueado | `POST /api/plans/00000000-fake/send-quote` (cookie demo Pro) | 403, `{"error":"demo_blocked","action":"send_email"}` |
| P5b | Checkout Stripe bloqueado | `POST /api/billing/checkout` (cookie demo Pro) | 403, `{"error":"demo_blocked","action":"payment"}` |
| P5c | Envio documento bloqueado | `POST /api/documents/00000000-fake/send` (cookie demo Pro) | 403, `{"error":"demo_blocked","action":"send_document"}` |
| P6 | Rate-limit demo-login | 11× `POST /api/auth/demo-login` do mesmo IP | 11º request → 429 (opcional; já validado em D4 em preview — basta citar se repetir em prod der 429) |

### 3.2 Screenshot

- URL: `https://construpilot.pt/demo/entrar`
- Esperado após restart: 2 CTAs clicáveis (**Entrar como PRO**, **Entrar como Particular**) em vez do estado anterior "demo indisponível".
- Destino: `/app/memory/websummit_demo_pt_fix/demo_entrar_prod_post_seed.png`
- Zero PII no screenshot (sem email no header; se houver nome de utilizador,
  redactar visualmente antes de guardar).

### 3.3 Comandos preparados (uso agente, pós-restart)

```bash
# P1
curl -s -w "HTTP %{http_code}\n" https://construpilot.pt/api/auth/demo-status

# P3 (demo Pro login, guarda cookie para passos seguintes)
curl -s -c /tmp/demo_pro_cookies.txt -w "HTTP %{http_code}\n" \
  -X POST https://construpilot.pt/api/auth/demo-login \
  -H "Content-Type: application/json" \
  -d '{"kind":"pro"}' \
  -o /tmp/demo_pro_login.json
# Agente NÃO dumpa o body se contiver campo "token"/"password_hash"/"password".

# P4 (projectos)
curl -s -b /tmp/demo_pro_cookies.txt -w "HTTP %{http_code}\n" \
  https://construpilot.pt/api/projects \
  -o /tmp/demo_pro_projects.json

# P5a (send-quote bloqueado)
curl -s -b /tmp/demo_pro_cookies.txt -w "HTTP %{http_code}\n" \
  -X POST https://construpilot.pt/api/plans/00000000-fake-0000-0000-000000000000/send-quote \
  -H "Content-Type: application/json" -d '{}' \
  -o /tmp/demo_pro_sendquote.json

# P5b (billing checkout bloqueado)
curl -s -b /tmp/demo_pro_cookies.txt -w "HTTP %{http_code}\n" \
  -X POST https://construpilot.pt/api/billing/checkout \
  -H "Content-Type: application/json" -d '{"plan":"premium"}' \
  -o /tmp/demo_pro_checkout.json

# P5c (documents send bloqueado)
curl -s -b /tmp/demo_pro_cookies.txt -w "HTTP %{http_code}\n" \
  -X POST https://construpilot.pt/api/documents/00000000-fake-0000-0000-000000000000/send \
  -H "Content-Type: application/json" -d '{}' \
  -o /tmp/demo_pro_senddoc.json
```

---

## 4. Resultados (preenchidos após restart)

### 4.1 Mecanismo usado
_(a preencher: Restart vs Redeploy, duração aproximada)_

### 4.2 Tabela de resultados P1–P6
_(a preencher)_

### 4.3 Screenshot
_(a preencher: caminho + anotação de redacções visuais, se aplicável)_

### 4.4 Anomalias
_(a preencher)_

### 4.5 Confirmação final
_(a preencher: "seed activo em prod, contas provisionadas, envios bloqueados, zero PII exposta")_

---

## 5. Rollback (se activação falhar)

Caso o fundador faça restart e `demo-status` continue `false/false` após 2
tentativas, ou se o seed falhar com erro nos logs:

1. Verificar nos Secrets que os valores foram efectivamente guardados (às vezes
   paste perde caracteres finais).
2. Verificar que as 4 chaves estão escritas **exactamente** como
   `WEBSUMMIT_DEMO_EMAIL_PT` (case-sensitive, underscore, sem espaço).
3. Se continuar a falhar, remover temporariamente os 4 segredos → restart →
   `demo-status` deve voltar a `false/false` sem crashar o backend
   (fail-closed). O resto da app continua funcional. Depois contactar suporte
   Emergent.

Zero `git push`, zero toques em `.fr`, zero contas reais usadas.

---

## 6. Estado deste documento

**Estado**: ⏳ aguarda **1 acção do fundador** (restart no dashboard Emergent,
secção 2.1 acima). Agente pausa até confirmação.
