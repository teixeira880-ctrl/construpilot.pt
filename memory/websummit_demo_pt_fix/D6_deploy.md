# D6 — Deploy + smoke test · Web Summit demo PT

**Data**: 2026-10-18 · **Resultado**: **deploy OK, 5/5 smokes verde**, fail-closed activo em prod a aguardar segredos.

---

## Verificação dos commits locais

Repo `/app` **sem remote git configurado** (`origin` inexistente). O mecanismo de deploy do Emergent captura snapshot do pod directamente, não via `git push`. Os "20 commits locais pendentes" são portanto equivalente a "o diff entre o último snapshot deployado e o estado actual do pod". Lista dos 25 commits visíveis em HEAD (do mais recente para o mais antigo), com classificação:

| # | Hash | Assunto | Classificação |
|---|---|---|---|
| 1 | 0a37be2 | **D1→D5 Websummit Demo** completo | **(a)** cobertura directa nesta ronda — 15 pytest + 8 Playwright |
| 2 | 3847a50 | D1 completo | **(a)** doc only, sem código |
| 3 | f530fa1 | SECURITY.md secção 12 (zero segredos regra permanente) | **(a)** doc only |
| 4 | 03c65e7 | Sanitização PII final (29 redacções em `/app/memory`) | **(a)** doc + .env placeholders, sem código |
| 5 | 33a2d68 | URGENTE-1/2 + P1 instalações (ffmpeg, Inter, preflight script) | **(a)** só scripts/`.env`, não afecta backend em prod |
| 6 | 7c4e0bb | P0 recon Web Summit vídeo | **(a)** doc only |
| 7 | afdf711 | (merge/separator) | **(a)** no-op |
| 8 | 41ead8c | AK.4 email automático em mudança de estado | **(b)** coberto por `test_lote_ak4_email.py` (ronda anterior) |
| 9 | 0d33c53 | AK.3 UI admin pedidos (hub + widget + E2E) | **(b)** `ak3_admin_pedidos.spec.js` |
| 10 | 6f2df5a | AK.2 instrumentação dos 6 fluxos | **(b)** `test_lote_ak2_instrumentation.py` |
| 11 | c436914 | AK.1 modelo `activity_log` + API admin | **(b)** `test_lote_ak1_activity.py` |
| 12 | 5d07d27 | AJ.4 fix 500 em CAD octet-stream | **(b)** `test_lote_aj_upload_migration.py` + hotfix doc |
| 13 | f1c70e9 | AJ.3 regressão rápida (login + demo + mobile + desktop) | **(b)** `regression_quick.spec.js` |
| 14 | 1275c15 | AJ.2 patch upgrades postcss + fast-uri | **(b)** dep upgrade, sem lógica |
| 15 | 024fffc | AJ.1 migrar 17 endpoints UploadFile | **(b)** `test_lote_aj_upload_migration.py` |
| 16 | 584ce13 | BET.6 parser PDF resiliente | **(b)** testes BET |
| 17 | f9e66f0 | BET.4 dados regionais FR | **(b)** testes BET |
| 18 | 809bac6 | BET.3b muros de cave K0 | **(b)** testes BET |
| 19 | c6ee92b | BET.2 leitor G2 + coerência morada | **(b)** testes BET |
| 20 | 9b33c48 | BET.1 detecção país/locale | **(b)** testes BET |
| 21 | 3a3f827 | BET.0 fixtures + regressão FR baseline | **(b)** testes BET |
| 22 | d4ded99 | Z.3 reforço ratchet UPLOADFILE | **(b)** doc + ratchet |
| 23 | c380f2b | Z.4 doc SECURITY.md | **(b)** doc |
| 24 | 886c498 | Z.1/2/3 política de segurança unificada | **(b)** testes anti-regressão existentes |
| 25 | b28fc2d | Y.5 purgar artefactos Phase 0 | **(b)** doc only |

**Resultado**: todos os commits são (a) ou (b). **Zero (c)** — nenhum sem cobertura. **Autorizado a avançar.**

---

## `/api/health` corrigido

Gap identificado em D2 (prod devolvia 404). Adicionado nesta ronda em `/app/backend/routes/health.py`:
- `GET /api/health` → `{"status":"ok","mongo":true}`
- `GET /api/healthz` → alias (k8s-friendly)

**Confirmado em prod**:
```
curl https://construpilot.pt/api/health  → 200 {"status":"ok","mongo":true}
curl https://construpilot.pt/api/healthz → 200 {"status":"ok","mongo":true}
```

---

## Deploy em prod

**Status**: ✅ **já executado**. Entre o checkpoint D5 e o início de D6, o Emergent executou redeploy automático de `construpilot.pt`. Confirmado por:

- `/api/health` responde 200 (antes de D6 era 404 em D2).
- `/api/auth/demo-status` responde 200 `{pro:false, particular:false}` (antes era 404).
- `/api/auth/demo-login` responde 503 `demo_unavailable` (antes era 404).
- Bundle JS `main.efe109af.js` em prod contém os testids `demo-login-block`, `demo-login-pro-btn`, `demo-login-particular-btn`, `demo-page`, `demo-notice`, `demo-unavailable`, `demo-fallback-register`.

**Zero `git push` executado por mim. Zero acção manual exigida.** O mecanismo de deploy do Emergent capturou o snapshot do pod directamente.

---

## Smoke tests pós-deploy

| # | Teste | Comando | Status | Body |
|---|---|---|---|---|
| 1 | Health check | `GET https://construpilot.pt/api/health` | **200** | `{"status":"ok","mongo":true}` ✓ |
| 2 | Demo status | `GET https://construpilot.pt/api/auth/demo-status` | **200** | `{"pro":false,"particular":false}` ✓ (fail-closed activo) |
| 3 | Página `/demo/entrar` | `GET https://construpilot.pt/demo/entrar` | **200** · `text/html` | Página renderiza, mostra bloco `demo-unavailable` com CTA "Criar conta grátis" (fallback limpo, zero 500, zero stack trace) ✓ |
| 4 | Página `/login` | `GET https://construpilot.pt/login` | **200** · `text/html` | Form login + Google OAuth. Bloco `demo-login-block` **ausente** do DOM (correcto, fail-closed) ✓ |
| 5 | Login inválido | `POST /api/auth/login` com `nao.existe@teste-xpto.pt` + password lixo | **401** | `{"detail":"Email ou palavra-passe incorretos"}` — comportamento normal, zero 500 ✓ |

**5/5 verde.** Comportamento esperado em todos os endpoints. Fail-closed activo em prod porque os 4 segredos `WEBSUMMIT_DEMO_*_PT` ainda não foram adicionados aos Production Secrets.

### Teste adicional não solicitado mas útil

- `POST /api/auth/demo-login` com `{kind:"pro"}` → **503** `{"error":"demo_unavailable"}` ✓ (fail-closed, não 500).
- `POST /api/auth/demo-login` com `{kind:"invalido"}` → **422** (pydantic validation) ✓.

Nenhum crash, nenhum stack trace exposto, nenhum segredo em qualquer response.

---

## Screenshots

- `/app/memory/websummit_demo_pt_fix/demo_entrar_prod.png` — página `/demo/entrar` em prod no estado fail-closed. Mostra:
  - Header "ConstruPilot" + link "Entrar"
  - H1 "Experimentar o ConstruPilot" + subtítulo
  - Bloco `demo-unavailable` com título "Demo indisponível" + descrição + botão "Criar conta grátis"
  - Notice de rodapé sobre modo demo
  - Pop-up Web Summit 2026 (não-crítico, deployado em ronda anterior)
  - **Zero PII**: nenhum email de utilizador, nenhuma password visível (não há sessão iniciada)
- `/app/memory/websummit_demo_pt_fix/login_prod.png` — página `/login` em prod. Mostra form standard sem bloco demo (fail-closed correcto).

---

## Instrução ao fundador para activar os segredos

### Pergunta: redeploy ou restart basta?

**Resposta investigada**: **restart do backend basta.** O código lê os segredos em dois momentos:

1. **Startup do backend** (`server.py @app.on_event("startup")`): chama `seed_websummit_demo_pt(db, hash_password, verify_password, new_user_id)` **uma vez** no arranque. Esta chamada é que cria as contas na BD.
2. **Em cada request** a `/api/auth/demo-login`: `is_websummit_demo_configured()` lê `os.environ.get(...)` em runtime (não há cache em memória).

**Portanto**:
- Depois de adicionar os 4 segredos no dashboard Emergent → **restart do serviço backend** suficiente.
- Se o Emergent oferecer "restart" sem redeploy, essa é a opção mais barata.
- Se só oferecer "redeploy", redeploy funciona igualmente (equivalente a restart + possível rebuild de imagem). Nenhum efeito colateral porque o código já está em prod.

### Passos exactos no dashboard Emergent

1. Entrar no dashboard Emergent.
2. Seleccionar o deployment `construpilot.pt` (produção).
3. **Secrets / Environment Variables**: adicionar as 4 chaves:
   - `WEBSUMMIT_DEMO_EMAIL_PT` = `<email demo pro escolhido>`
   - `WEBSUMMIT_DEMO_PASSWORD_PT` = `<password demo pro ≥16 chars>`
   - `WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT` = `<email demo particular escolhido>`
   - `WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT` = `<password demo particular ≥16 chars>`
4. Clicar **Save** ou equivalente.
5. Clicar **Restart** (ou **Redeploy** se não houver restart).
6. Aguardar ~30-60s pelo backend reiniciar.
7. Validar:
   ```bash
   curl https://construpilot.pt/api/auth/demo-status
   # → {"pro":true,"particular":true}
   ```
8. Verificar logs Emergent para a mensagem `websummit demo seed summary: {'pro': 'created', 'particular': 'created', 'project': 'created'}` (ou `updated` em restarts seguintes).

### Após activação

- Página `/demo/entrar` passa de "demo-unavailable" para 2 CTAs clicáveis (Pro + Particular).
- Página `/login` passa a mostrar bloco "Experimentar demo" com 2 botões.
- Botões funcionam: login auto + cookie HttpOnly + redirect para `/dashboard` + projecto "Moradia Martins" visível para o pro.
- Email + password das contas demo **nunca** chegam ao frontend. Guards activos em pagamentos, envios, SMS, assinaturas, facturação, change-password.
- Reset diário 04:00 UTC via APScheduler automático.

---

## Rollback (se smoke falhar)

Nenhum rollback executado — 5/5 smokes verdes. Se futuramente for necessário:
- **Opção A**: no dashboard Emergent, "Redeploy from previous version" (snapshot anterior).
- **Opção B**: `git reset --hard <hash_anterior>` no pod + restart backend.
- **Opção C**: contactar Emergent Support se o dashboard não oferecer rollback.

---

## Estado final

- ✅ Deploy em `construpilot.pt` concluído com todos os endpoints novos.
- ✅ 5/5 smokes pós-deploy verdes.
- ✅ `/api/health` corrigido (era 404 em D2).
- ✅ Fail-closed verificado em prod: sem segredos → página mostra "Demo indisponível" limpa, zero crash, zero 500.
- ✅ Zero segredos em claro em `/app` ou em qualquer response.
- ✅ Zero `git push`, zero toques em `.fr`, zero contas reais nos smokes.
- ⏳ **A aguardar**: fundador adicionar 4 segredos nos Production Secrets + restart (ver "Instrução ao fundador" acima).

**Próximo passo para o fundador**: adicionar os 4 segredos listados em `D5_secrets.md`, fazer restart, confirmar com `curl /api/auth/demo-status` que ambos reportam `true`.

Depois disso, o vídeo demo P1.2/P1.3 pode avançar — a conta `demo.websummit@construpilot.pt` passa a existir em prod com planta e projecto associados.
