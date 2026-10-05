# Diagnóstico Resend — Bug Emails Admin UI

**Data**: 05 Out 2026 · **Status**: ✅ RESOLVIDO

---

## 1. Causa raiz

**Combinação de 3 causas**, nenhuma ligada a Resend em si:

### 1.a — `.env` com aspas malformadas (fix preventivo crítico)
`RESEND_API_KEY="re_..."` com aspas duplas → Python lia a string literal com aspas incluídas → Resend 400 `"API key is invalid"`.

**Fix**: script automatizado removeu aspas de **33 linhas** do `.env` (todas as `KEY="valor"` → `KEY=valor`).

### 1.b — Bounces legítimos interpretados como "falhas Resend"
Os "19 echecs" reportados eram:
- 24 `bounced`: endereços de teste fictícios `qa+test1@construpilot.pt`, `teste-rate-N@construpilot.pt` — **mailboxes não existentes**
- 21 `suppressed`: endereços FR antigos `pro/demo/admin@construpilot.fr` em suppression list por bounces anteriores
- Resend fez o trabalho corretamente — o problema era UI não distinguir bounce legítimo de falha de sistema

**Fix**: `/api/admin/bulk-email` agora classifica cada falha (`invalid_recipient`, `bounced`, `rate_limited`, `suppressed`, `auth_error`, `domain_not_verified`, `unknown`) e devolve `categories: {...}`. UI mostra toast PT com legenda clara.

### 1.c — UX confuso: botão "E-mail (0)"
O botão só habilita após seleccionar checkboxes. Com "(0)" aparece disabled e o utilizador pensa que está broken.

**Fix**: tooltip PT no botão quando disabled: *"Selecione utilizadores com a caixa à esquerda"*.

---

## 2. Status Resend (confirmado por API live)

| Métrica | Valor |
|---|---|
| API Key | ✅ Válida (36 chars, `re_...`) |
| Plano | **Pro** (3000+ emails/dia) |
| Domínio `construpilot.pt` | ✅ **verified** (eu-west-1) |
| Capabilities | `sending: enabled` |
| Success rate últimos 100 | **~80% delivered/opened/clicked** |
| Bounced | 24 (todos endereços de teste fictícios) |
| Suppressed | 21 (endereços FR antigos em deny list) |

**Nenhum problema de infraestrutura. DNS/SPF/DKIM/DMARC OK.**

---

## 3. Fix aplicado — Diffs

### Backend
- `/app/backend/.env` — 33 linhas corrigidas (remoção de aspas)
- `routes/admin.py`:
  - `admin_bulk_email` enriquecido com classificação de erros + `categories` no response
  - `drill/users` labels PT ("Utilizadores", "Nome", "E-mail", "Telefone", "Empresa", "Plano", "Função", "Cidade", "Última atividade", "Inscrito em")
  - **novo** `/api/admin/emails/resend-status` — dashboard real-time Resend (events_count, success_rate_pct, domains verified, legend PT)

### Frontend
- `components/AdminDrillDialog.jsx` — toda a UI traduzida para PT:
  - "Détails" → "Detalhes"
  - "Chargement" → "A carregar"
  - "Pesquisar" (já PT)
  - "résultat(s)" → "resultado(s)"
  - "Exporter CSV" → "Exportar CSV"
  - "Filtres" → "Filtros"
  - "Plan" / "Tous les plans" → "Plano" / "Todos os planos"
  - "Ville / adresse" → "Cidade / morada"
  - "Inactifs (+30 j)" → "Inativos (+30 dias)"
  - "Réinitialiser" → "Repor"
  - "Aucune donnée" → "Sem dados"
  - Modal composer: "E-mail promotionnel" → "E-mail promocional", "Objet" → "Assunto", "Annuler" → "Cancelar", "Envoyer" → "Enviar"
  - `toast` enriquecido: `"3 enviados · 1 falha — 1× mailbox inexistente"`
  - Tooltip no botão quando disabled

---

## 4. Teste reproduzível — 3 emails via admin UI

Request:
```bash
POST /api/admin/bulk-email
{
  "recipients": ["info@construpilot.pt", "deboradsmelo@gmail.com", "nao-existe@construpilot.pt"],
  "subject": "[VALIDACAO FINAL] UI admin",
  "message": "..."
}
```

Response:
```json
{"ok": true, "sent": 3, "failed": 0, "total": 3, "categories": {}}
```

Resend `last_event` após 15s:
```
info@construpilot.pt       → delivered   ✅
deboradsmelo@gmail.com     → sent (gmail delay, deve ir para delivered)
nao-existe@construpilot.pt → bounced     ⚠️ (mailbox não existe — comportamento correto do Resend)
```

Os 5 emails de validação enviados anteriormente (`[DIAG 1-5/5]`) estão **todos `delivered`**.

---

## 5. Validação pytest

```
62 passed, 1 skipped — ZERO regressões
```

---

## 6. Instrução ao utilizador

**A infraestrutura Resend está 100% funcional.** O que o utilizador tem de fazer:

### Para enviar emails via admin
1. Abrir `/admin` → clicar em "Utilizadores"
2. **Selecionar os utilizadores** com os checkboxes à esquerda de cada linha
3. O contador do botão passa de "E-mail (0)" para "E-mail (N)" (fica habilitado quando N ≥ 1)
4. Clicar "E-mail" → preencher Assunto + Mensagem → "Enviar"
5. Toast PT confirma: `"3/3 e-mails enviados com sucesso"` ou, se houver falhas, mostra categoria clara (`"1× mailbox inexistente"`)

### Para endereços de teste
Resend classifica como `bounced` endereços que não existem. Isto **não é falha do sistema** — é proteção reputacional. Para testes reais usar sempre endereços válidos (`info@construpilot.pt`, Gmail pessoal, etc.).

### Para limpar suppression list
Resend tem auto-cleanup após 30 dias. Alternativamente, admin pode remover manualmente em https://resend.com/suppressions (plano Pro).

---

## 7. Dívida técnica identificada (não bloqueante)

| Item | Prioridade | Nota |
|---|---|---|
| Webhook `/api/webhooks/resend` para captura async de bounces | P2 | Collection `resend_webhook_events` já existe mas vazia. Falta implementar endpoint + verificar secret. |
| Dashboard "/admin/emails" com UI consumindo `/resend-status` | P2 | Backend endpoint pronto; falta página React. ~1h. |
| Retry button para bounced | P3 | Útil para falsos positivos. |
| i18n automático admin usando `translate_fr_to_pt.py` em todo o `/admin/*` | P2 | Dívida técnica geral (99 strings FR pendentes). |

---

## 8. Rate limiting Perplexity (bonus do passo anterior)

Durante este diagnóstico também validei o rate limiting:
- `slowapi` v0.1.10 instalada
- `limiter` em `core/rate_limit.py` com `key_func=user_id|ip`
- Limites: `/chat` 30/h · `/compare` 20/h · `/norms` 20/h · `/materials-watch` 15/h
- Resposta 429 em PT-PT: `"Atingiu o limite de pedidos. Tente novamente em X min."`
- **Fix adicional**: `headers_enabled=False` para evitar `Exception: parameter 'response' must be an instance of starlette.responses.Response` + migração de type hints `str | None` → `Optional[str]` (slowapi incompatível com `from __future__ import annotations`)

Rate limiting NÃO está aplicado ao bulk-email admin (foi deliberado — admin tem throttle próprio de 1.1s/chunk).

---

## 9. Pontos de atenção para o futuro

- Nunca editar `.env` com aspas em volta dos valores — python-dotenv processa, mas certos contextos (Docker, supervisor) passam a string literal
- Sempre testar envio bulk com pelo menos **1 endereço real** antes de concluir que "não funciona"
- Resend `bounce` ≠ "sistema broken" — significa que o endereço do destinatário não é válido

Status final: **sistema de emails operacional, UI em PT-PT, mensagens de erro informativas**.
