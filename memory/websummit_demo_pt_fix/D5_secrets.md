# D5 — Segredos a adicionar nos Production Secrets (`construpilot.pt`)

**Data**: 2026-10-17 · **Entregável**: lista de nomes de segredos para o fundador adicionar ao dashboard do Emergent antes do deploy. **Zero valores, zero sugestões**.

---

## Para o fundador

Adicionar as 4 variáveis seguintes nos **Production Secrets** do deploy `construpilot.pt` (dashboard Emergent → ambiente de produção → secrets). **Nunca** partilhar os valores comigo, nem colar em `.env` do preview.

### 1. Nomes das variáveis (obrigatório adicionar as 4)

```
WEBSUMMIT_DEMO_EMAIL_PT
WEBSUMMIT_DEMO_PASSWORD_PT
WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT
WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT
```

### 2. Semântica de cada variável

| Variável | Significado | Default se não definida |
|---|---|---|
| `WEBSUMMIT_DEMO_EMAIL_PT` | Email da conta demo profissional. Será visível no stand (mostrado no header do dashboard quando logado). | **Nenhum.** Se ausente ou vazio → conta pro não é criada no startup. Login demo pro devolve 503 `demo_unavailable`. |
| `WEBSUMMIT_DEMO_PASSWORD_PT` | Password da conta demo profissional. Nunca sai do backend. | **Nenhum.** Fail-closed idêntico ao email. |
| `WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT` | Email da conta demo particular (plano free). | **Nenhum.** Fail-closed. |
| `WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT` | Password da conta demo particular. | **Nenhum.** Fail-closed. |

### 3. Política de passwords recomendada

- **Comprimento mínimo**: 16 caracteres.
- **Mistura**: letras maiúsculas + minúsculas + dígitos + 1 símbolo (ex: `!@#$`).
- **Zero reutilização**: nunca reutilizar passwords de preview, dev ou outros ambientes. Zero overlap com `TEST_PRO_PASSWORD_PT` da ronda anterior.
- **Rotação**: podem ser rodadas a qualquer momento. O seed detecta mismatch e realinha o `password_hash` automaticamente no próximo startup (`test_seed_realigns_password_on_mismatch` cobre isto).
- **Gerador sugerido**: `python3 -c "import secrets, string; print(''.join(secrets.choice(string.ascii_letters+string.digits+'!@#$%&*') for _ in range(20)))"` executado offline pelo fundador.

### 4. Convenção de emails recomendada

- Emails devem incluir "demo" ou "websummit" no local-part para serem identificáveis à vista (ex: `demo.websummit@construpilot.pt`, `demo.visitante@construpilot.pt`).
- **Não** usar emails pessoais do fundador nem `contact@cmrenov.com` nem `teixeira880@gmail.com`.
- **Não** usar emails de clientes reais ou prospects.
- Caixa de correio real **não é necessária** — a conta demo não envia nem recebe emails (bloqueado pelo middleware). O email é só identificador.

### 5. Validação pós-adição (sem me partilhar valores)

Depois de adicionar os 4 segredos no dashboard e antes de passar a D6:

1. Fazer deploy (ou aguardar o redeploy automático que o Emergent despoleta).
2. Verificar via `curl` **a partir do dashboard** ou browser:
   ```
   curl https://construpilot.pt/api/auth/demo-status
   ```
   Deve devolver `{"pro":true,"particular":true}`. Se devolver `{"pro":false,"particular":false}` → segredos não foram picked up pelo backend.
3. Verificar `curl https://construpilot.pt/api/health` → `{"status":"ok","mongo":true}`.

Se os 2 checks passarem, confirmar comigo com uma mensagem **sem valores** (ex: *"segredos adicionados, demo-status reporta ambos true"*) e eu avanço para D6 (smoke test completo).

---

## O que NÃO deves fazer

- ❌ **Não** adicionar os valores no `/app/backend/.env` do preview (o preview pode continuar com `<redacted>`; teste a mesma config desligada é parte da validação).
- ❌ **Não** colar os valores em nenhum relatório, mensagem, email, Slack, GitHub issue.
- ❌ **Não** usar passwords já conhecidas (`TesteE2E!2026`, `Construpilot2026!`, ou qualquer das já rodadas).
- ❌ **Não** partilhar os valores comigo (agente) nem com o testing agent — nunca precisamos.

---

## O que o deploy em D6 vai fazer automaticamente

Depois dos segredos adicionados em prod e do deploy executado:

1. **Startup do backend** chama `seed_websummit_demo_pt(db, hash_password, verify_password, new_user_id)`:
   - Se segredos presentes → cria 2 users com `is_demo=True, demo_source="websummit_2026"`.
   - Cria entitlement `pro_business_monthly` para o pro.
   - Cria projecto "Moradia Martins" ligado ao pro.
   - Log: `websummit demo seed summary: {'pro': 'created', 'particular': 'created', 'project': 'created'}`.
2. **Scheduler APScheduler** regista job `websummit_demo_reset_daily` a correr às 04:00 UTC.
3. **Rotas públicas activas**:
   - `GET  /api/auth/demo-status` (público, sem rate limit)
   - `POST /api/auth/demo-login` (rate limit 10/min/IP)
   - `GET  /api/health` + `GET /api/healthz`
   - `POST /api/admin/demo/reset` (admin real only)
   - `GET  /api/admin/demo/status` (admin real only)
4. **Frontend** mostra:
   - Botão "Experimentar demo" em `/login` (Pro + Particular).
   - Página `/demo/entrar` (QR code do stand).
5. **Protecção runtime** via `DemoActionsMiddleware`:
   - 25+ padrões de rotas sensíveis bloqueadas com 403 `demo_blocked`.
   - Password + email imutáveis para contas demo.

---

## Estado actual

- ✓ Código completo, testado localmente (23/23 verde).
- ✓ `/app/backend/.env` tem as 4 chaves com valor `<redacted>` (placeholders — fail-closed activo no preview).
- ✓ Zero segredos em claro em `/app` fora do `.env`.
- ✓ 20 commits locais pendentes intactos.
- ✓ Zero deploys executados.

**Em espera**: confirmação do fundador de que os 4 segredos foram adicionados nos Production Secrets. Depois executo D6 (deploy + smoke tests).
