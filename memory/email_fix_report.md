# Fix email — Relatório de diagnóstico

**Data**: 2026-02-04
**Reporter**: utilizador ("os emails não funcionam")
**Ambiente testado**: PREVIEW (`https://construpilot-recon.preview.emergentagent.com`)

---

## 🎯 Diagnóstico resumido

**O envio técnico via Resend está 100 % operacional no preview.** Todos os fluxos de email testados responderam HTTP 200 e geraram IDs de envio Resend válidos.

A **percepção** de "não funcionam" tinha 3 causas combinadas:
1. **Silent fail** em `routes/auth.py` — 4 `except Exception: pass` engoliam qualquer erro de envio sem registar log, dando a aparência de "nada acontece".
2. **Nenhum log INFO de sucesso** em `engines/emailer.py` — mesmo quando o email saía com sucesso, não havia feedback em `/var/log/supervisor/backend.*.log`.
3. **Email de registo em francês** — mesmo chegando, o utilizador pode ter achado que estava partido.

---

## 1. Configuração verificada

| Vari | Estado |
|---|---|
| `RESEND_API_KEY` | ✅ presente (prefix `re_***`) |
| `RESEND_WEBHOOK_SECRET` | ✅ presente |
| `SENDER_EMAIL` | ✅ presente · domínio `@construpilot.pt` |
| `FRONTEND_URL` | ✅ presente (`https://construpilot-recon.preview.emergentagent.com`) |
| `ADMIN_ALERT_EMAIL` | ❌ ausente · fallback para `info@construpilot.pt` em `coach_ai.py` (hardcoded default) |
| `resend` lib em `requirements.txt` | ✅ 2.35.0 |
| `aiosmtplib` em `requirements.txt` | ✅ 5.1.2 |

---

## 2. Teste directo Resend (contorna todo o nosso código)

```python
await emailer.send_email(
  to="info@construpilot.pt",
  subject="ConstruPilot — Teste email (diagnóstico Sprint 1)",
  html="<p>...</p>",
  from_name="ConstruPilot Teste",
)
# → {'ok': True, 'id': '01a108e4-6abd-7dc0-bedb-195ed98e5833'}
```

Resend aceitou. **Zero problema de API/key/domínio.**

---

## 3. Fluxos testados end-to-end via REST

| Endpoint | HTTP | Email saiu? | ID Resend |
|---|---|---|---|
| `POST /api/auth/register` | 200 | ✅ (após fix tradução) `"Confirme o seu e-mail — ConstruPilot"` | `01a108e8-40d5-72de-95ed-c94c4d23e7b8` |
| `POST /api/auth/forgot-password` | 200 | ✅ `"Redefina a sua palavra-passe ConstruPilot"` (já em PT) | `01a108e7-53a7-7825-9ac4-9bdb052ae2ba` |
| Coach IA failure → admin alert | — | ✅ `"[ConstruPilot] Coach IA falhou — user_id=…"` | `01a108e8-bd1f-790d-a6ed-84663640f5c3` |
| `POST /api/users/me/mailbox/test` | 400 | ⚠ "Aucune boîte e-mail connectée/vérifiée" — não é bug: requer caixa SMTP configurada |
| `GET /api/emails/templates` | 200 | — (listagem, não envio) |

---

## 4. Fixes aplicados

### 4.1 `engines/emailer.py`
Adicionado log INFO de sucesso em `send_email()` para visibilidade:
```python
logger.info("Email sent to=%s subject=%r id=%s", to, subject[:60], resp.get("id"))
```

### 4.2 `routes/auth.py` — 4 pontos de silent-fail eliminados
Substituído `except Exception: pass` por `logger.exception(...)` em:
- `register` (linha ~174) · logger `auth.register`
- `resend_verification` (linha ~217) · logger `auth.resend_verification`
- KYC status change (linha ~547) · logger `auth.kyc`
- 2FA code send (linha ~720) · logger `auth.2fa`

### 4.3 Tradução FR → PT-PT dos emails de verificação
- `register` welcome email: FR → PT-PT completo ("Olá", "Bem-vindo(a)", "Confirme o seu e-mail", "Particular/Profissional", "A equipa ConstruPilot")
- `resend-verification`: FR → PT-PT ("Confirme o seu e-mail")
- URL `/verifier-email/{token}` **mantida** porque é a rota real em `App.js` (linha 220: `path="/verifier-email/:token"`). Não alterar sem migrar a rota frontend.

### 4.4 Ficheiros alterados
```
M backend/engines/emailer.py       (+3 linhas log INFO)
M backend/routes/auth.py           (+import logging · 4 pass→exception · 2 blocos FR→PT)
```

---

## 5. Logs reais capturados após fix

```
2026-10-04 21:52:20,181 - engines.emailer - INFO - Email sent to=test-mail-trace-...@construpilot.pt subject='Confirmez votre e-mail — ConstruPilot' id=01a108e7-527d-7481-bf10-89c8b39ce0c9
2026-10-04 21:52:20,455 - engines.emailer - INFO - Email sent to=info@construpilot.pt subject='Redefina a sua palavra-passe ConstruPilot' id=01a108e7-53a7-7825-9ac4-9bdb052ae2ba
2026-10-04 21:53:21,164 - engines.emailer - INFO - Email sent to=test-final-...@construpilot.pt subject='Confirme o seu e-mail — ConstruPilot' id=01a108e8-40d5-72de-95ed-c94c4d23e7b8
```

---

## 6. Segurança

```
grep -riE "sk-ant-|sk-proj-|pplx-|re_[a-zA-Z0-9]{20,}" /var/log/supervisor/ → 0 matches
```
Zero keys em logs. `.env` continua fora do git (`git check-ignore` OK).

---

## 7. Riscos ainda abertos

1. **Rate limit Resend 10 req/s** — logs antigos (set/2026) mostram 2 ocorrências. Não observado agora, mas se o utilizador fizer bulk-email massivo pode voltar a bater. Mitigação: `engines/emailer.py` deveria ter retry com backoff. **FORA do âmbito** deste bugfix (feature para Sprint 10).
2. **`SENDER_EMAIL` em `@construpilot.pt`** — se o domínio não tiver SPF/DKIM/DMARC configurados correctamente no DNS, os emails chegam mas vão para SPAM. **Verificar via Resend dashboard `Domains`** se o estado está "Verified ✓".
3. **`ADMIN_ALERT_EMAIL`** não está no `.env` — depende do fallback hardcoded `info@construpilot.pt`. Se o utilizador quiser outro destinatário, precisa adicionar no admin secrets.
4. **Emails ainda em francês noutros fluxos**: `KYC validation` (routes/auth.py linha ~534), `admin bulk email` (routes/admin.py), `invoices/estimates` (routes/plans_export.py), etc. **FORA do âmbito** deste bugfix urgent — fica para Sprint 1 (i18n) e sprints subsequentes.

---

## 8. Dúvida a resolver com o utilizador

**O preview funciona.** Mas há **produção live** em `https://construpilot.pt` que foi deployada recentemente. É possível que:
- A `RESEND_API_KEY` em produção seja diferente/inválida.
- `SENDER_EMAIL` em produção use outro domínio sem SPF/DKIM.
- `FRONTEND_URL` em produção aponte para o local errado → links do email vão para 404.

**Preciso que o utilizador confirme**:
- Está a observar a falha em **preview** ou em **produção**?
- Fluxo específico que falha (registo? reset password? envio de orçamento? alerta admin? outro?)
- Email destinatário usado no teste.
- Já verificou pasta spam/junk?
