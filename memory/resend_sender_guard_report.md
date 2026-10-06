# Fix Resend P0 — Guard anti-`.local` + Tracking fiel + Endpoint admin

**Data**: 05 Fev 2026 · **Idioma**: PT-PT
**Status**: ✅ **CONCLUÍDO** · pytest **105/105 + 13 novos** · envio real `delivered` com `info@construpilot.pt`

---

## 1. Diagnóstico

Grep em `/app/backend/` e `/app/frontend/`:
- Nenhum ficheiro de código tem `construpilot.local` hardcoded.
- `backend/.env` tem `SENDER_EMAIL=no-reply@construpilot.pt` (correto).
- `backend/engines/emailer.py` lia apenas `SENDER_EMAIL` sem validação.
- Resend API respondia 200 OK → código marcava "delivered" na UI de forma falsa.

**Conclusão**: o `.local` em produção vem muito provavelmente de uma `SENDER_EMAIL`
mal configurada no painel Emergent, ou de um override por campanha. Para que
nunca mais aconteça foi introduzido um **guard de produção**.

---

## 2. Ficheiros alterados / criados

### Backend
1. **`backend/engines/mail_sender_config.py`** *(novo · 155 LoC)*
   - `Market` enum (PT/FR/OTHER)
   - `FORBIDDEN_DOMAIN_SUFFIXES = (".local", ".localhost", "localhost", ".example.com", "example.com", ".test", ".invalid")`
   - `get_sender(market, override)` — valida e devolve `{name, from, reply_to}`
   - `assert_valid_sender(address)` — **levanta `ForbiddenSenderError` em `ENV=production`**; log warning em dev
   - `format_from_header({name, from})` → `"ConstruPilot <info@construpilot.pt>"`
   - `is_production()` — lê `ENV|APP_ENV` (prod/production ⇒ True)

2. **`backend/engines/emailer.py`** *(reescrito)*
   - `send_email` e `send_email_with_pdf` chamam `get_sender(Market.PT, override)` → guard dispara **ANTES** de qualquer chamada Resend.
   - Nova helper `_log_email_event()` grava em MongoDB `email_logs`:
     - 200 OK com `id` → `status="accepted"` (**NUNCA `delivered`**)
     - 200 OK sem `id` → `status="queued"`
     - Exceção Resend → `status="failed"` + `errors[]`
     - Guard `.local` → levanta antes do log; o chamador decide se grava.
   - Mantido 100% backwards-compat: assinaturas antigas (`from_name`, `reply_to`) continuam a funcionar.

3. **`backend/routes/admin.py`**
   - Novo endpoint **`GET /api/admin/resend-status`** (alias curto como pedido):
     - Lê `email_logs` locais (últimos 50 por default, máx 200)
     - Devolve `items`, `total`, `buckets` por estado, `config` (sender atual, env, lista proibida), `legend` PT-PT
     - Protegido por `admin_user` (JWT admin)
   - Endpoint existente `GET /api/admin/emails/resend-status` **preservado** (consulta directa à Resend API).

### Configuração
4. **`backend/.env`** — acrescentado (sem segredos):
   ```
   SENDER_PT_NAME=ConstruPilot
   SENDER_PT_FROM=info@construpilot.pt
   SENDER_PT_REPLY=info@construpilot.pt
   ENV=development
   ```
   `SENDER_EMAIL=no-reply@construpilot.pt` preservado para compat.

### Testes
5. **`backend/tests/test_emailer_sender_guard.py`** *(novo · 13 testes)*
   - a) ENV=production + `.local` → `ForbiddenSenderError` ✓
   - a2) ENV=production + `localhost` → bloqueado ✓
   - a3) ENV=production + `example.com` → bloqueado ✓
   - b) Default sender = `info@construpilot.pt` ✓
   - b2) `SENDER_PT_FROM` env override ✓
   - c) Resend lança exceção → log com `status="failed"` ✓
   - d) Resend devolve `{id}` → log com `status="accepted"` (**nunca `delivered`**) ✓
   - e) ENV=production + `.local` → **API Resend NÃO é chamada** (prova via spy) ✓
   - f) ENV dev → warning em log mas não bloqueia ✓
   - g) `is_production()` flags corretas ✓

6. **`backend/scripts/test_sender_pt.py`** *(novo)*
   - Teste manual E2E: valida guard em prod + envio real em dev
   - Executado: **guard bloqueou `.local` em prod + envio real entregue (`delivered`) em 25 s**

---

## 3. Variáveis `.env` necessárias (ambiente)

| Variável                 | Valor exemplo              | Obrigatório |
|--------------------------|----------------------------|-------------|
| `RESEND_API_KEY`         | `re_…`                     | Sim         |
| `RESEND_WEBHOOK_SECRET`  | *(se usar webhook)*        | Recomendado |
| `SENDER_PT_NAME`         | `ConstruPilot`             | Default OK  |
| `SENDER_PT_FROM`         | `info@construpilot.pt`     | Default OK  |
| `SENDER_PT_REPLY`        | `info@construpilot.pt`     | Default OK  |
| `ENV`                    | `production` em prod       | **Sim em prod** |
| `SENDER_EMAIL`           | *(preservado p/ compat)*   | Opcional    |

---

## 4. Testes · output

### Guard (ENV=production + `.local`)
```
[1/2] Guard em ENV=production com remetente .local
[PROD BLOCK] Remetente bloqueado — domínio proibido: 'construpilot.local' (addr='no-reply@construpilot.local')
    ✅ OK — bloqueado: Remetente inválido para produção (domínio proibido: 'construpilot.local').
```

### Envio real (ENV=development)
```
RESEND_API_KEY present: True   SENDER_PT_FROM: info@construpilot.pt   ENV: development
resp: {'ok': True, 'id': '01a11071-4814-752d-9aa7-53eb1507b609', 'status': 'accepted'}
after 25s · last_event: delivered · from: ConstruPilot <info@construpilot.pt>
```

### Endpoint `/api/admin/resend-status`
```
total: 2
buckets: {'accepted': 2}
config: { sender_from: 'info@construpilot.pt', sender_name: 'ConstruPilot',
          sender_ok: True, env_is_production: False,
          forbidden_domains: ['.local', '.localhost', 'localhost', '.example.com', 'example.com', '.test', '.invalid'] }
último item: to=info@construpilot.pt  from=info@construpilot.pt  status=accepted  resend_id=01a11071-4814-752d-9aa7-53eb1507b609
```

### Pytest
```
105 passed, 1 skipped, 2 warnings in 4.84s
```
(+13 novos vs 92 anteriores · 0 regressões)

### OpenAPI
`GET /api/openapi.json` → HTTP 200 ✓ (inclui `/admin/resend-status` novo).

---

## 5. Ação necessária para produção (`construpilot.pt`)

Para que o fix fique **ativo em produção** o utilizador tem de:

1. **Painel Emergent → Variáveis de ambiente do backend**:
   - Definir **`ENV=production`** (crítico — ativa o guard)
   - Garantir **`SENDER_PT_FROM=info@construpilot.pt`** (ou remover todas as variantes `.local` que lá estejam)
   - Opcional: `SENDER_PT_NAME=ConstruPilot` · `SENDER_PT_REPLY=info@construpilot.pt`
   - Preservar `RESEND_API_KEY` existente

2. **Redeploy** da aplicação pelo painel (Preview → Produção)

3. Após redeploy, abrir `https://construpilot.pt/api/admin/resend-status` (como admin) e confirmar:
   - `config.env_is_production: true`
   - `config.sender_from: "info@construpilot.pt"`
   - `config.sender_ok: true`

4. Fila atual — **não é retrocessada automaticamente**:
   - Os emails já em `queued` com `from: .local` na Resend vão continuar queued e eventualmente timeout do Resend.
   - Para investigar basta ir à `/api/admin/emails/resend-status` (que consulta Resend API em directo) ou ao dashboard Resend.
   - Não há lógica automática de reenvio — se quiser reenviar algo depois de corrigir, abra uma nova campanha.

5. **Webhook Resend** (opcional, para fechar o ciclo `accepted → delivered`):
   - URL: `https://construpilot.pt/api/webhooks/resend`
   - Secret: definir `RESEND_WEBHOOK_SECRET` no painel + no Resend
   - *(Endpoint do webhook não foi criado nesta tarefa; está fora de scope mas é a próxima evolução natural para que `email_logs.status` passe de `accepted` → `delivered`/`bounced` automaticamente.)*

---

## 6. Preservado

- Opus 5.5, Biblioteca PT, Sprints 2/3/4
- Hero homepage, i18n 100% PT-PT, rate limiting
- Release Particulares + preços 99/179
- Rebranding Assistente de Obras + logo
- Acesso web Coach + Assistente de Obras
- Sprint 5 em pausa (não tocado)
- Config FR intacta (`SENDER_FR_*` continuam opcionais)
- Overrides de clientes continuam a funcionar — mas agora validados contra `.local`

---

## 7. Critérios de aceitação

- [x] Nenhum email sai com `.local` em produção (bloqueado por guard — provado em teste e)
- [x] Default sender = `info@construpilot.pt`
- [x] Estado real do Resend é persistido (não fake "delivered" — provado em teste d)
- [x] Endpoint `/api/admin/resend-status` devolve lista fiel + config
- [x] Pytest passa — **105 ok, 13 novos, 0 regressões**
- [x] Ficheiros alterados + output do pytest reportados acima
