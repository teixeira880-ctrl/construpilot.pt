# Bug Cloudflare 520 em `construpilot.pt/plan` — Relatório de investigação

**Data**: 2026-02
**Sintoma**: Toast de erro Cloudflare 520/521 no canto superior direito ao abrir `https://construpilot.pt/plan`. Página renderiza.
**Reprodução em preview**: ❌ **NÃO REPRODUZ**. Todos os endpoints respondem 200 OK em <10ms.

---

## 1. Endpoints chamados ao carregar `/plan`

Da inspecção estática de `/app/frontend/src/pages/PlanTakeoff.jsx`:

| On-mount useEffect | Endpoint | Condição |
|---|---|---|
| L270-298 | `GET /api/takeoffs` (via `loadAllPlans()`) | Sempre (quando sem plan activo) |
| L1193-1223 | `GET /api/takeoffs/settings/beton-defaults` | Sempre |
| L1193-1223 | `GET /api/takeoffs/settings/beton-presets` | Sempre |
| L345-354 | `GET /api/takeoffs/{pid}` | Só se URL tem `?open=` |
| L270 (quando plan) | `GET /api/takeoffs/{plan_id}/page/{pageIndex}` | Quando plano activo |
| L777-783 | `GET /api/emails/templates` | Só quando abre dialog "enviar ecarts" |

Outros `useEffect` posteriores só disparam após interacção (upload, análise, etc).

---

## 2. Testes locais (preview, backend @ `localhost:8001`)

Com token do admin `info@construpilot.pt`:

```
GET /api/takeoffs                           → HTTP 200 · 5ms · 12 bytes · {"plans":[]}
GET /api/takeoffs/settings/beton-defaults   → HTTP 200 · 5ms · 306 bytes · JSON válido
GET /api/takeoffs/settings/beton-presets    → HTTP 200 · 5ms · 489 bytes · JSON válido
GET /api/emails/templates                   → HTTP 200 · 6ms · 16 bytes · {"templates":[]}
GET /api/openapi.json                       → HTTP 200 · 473 KB
```

Content-Type: `application/json` em todos. Headers OK. Sem truncagens.

## 3. Logs backend preview

```
INFO: 127.0.0.1 - "GET /api/takeoffs HTTP/1.1" 200 OK
INFO: 127.0.0.1 - "GET /api/takeoffs/settings/beton-defaults HTTP/1.1" 200 OK
INFO: 127.0.0.1 - "GET /api/takeoffs/settings/beton-presets HTTP/1.1" 200 OK
INFO: 127.0.0.1 - "GET /api/emails/templates HTTP/1.1" 200 OK
```

**Zero exceptions, zero 500/502, zero stacktraces** nos últimos 300 logs filtrados.

## 4. Supervisor

```
backend                          RUNNING   pid 7847, uptime 1:26:06
frontend                         RUNNING   pid 124
mongodb                          RUNNING   pid 126
```

Backend saudável. Sem crash-loop. Sem reinícios anormais.

---

## 5. Diagnóstico — root cause provável (produção-específico)

Como **o bug NÃO reproduz em preview**, não é possível identificar o endpoint culpado com certeza sem acesso a produção. Causas prováveis, por ordem de probabilidade:

### 🔴 Hipótese A — Timeout upstream (mais provável)
Cloudflare 520 aparece tipicamente quando o origin não responde dentro de ~100 s. Em produção, um dos endpoints iniciais do `/plan` pode estar lento com dados reais:

- **`GET /api/takeoffs`** não paginado — se o utilizador tem N planos pesados e a query devolve `plan_data` completo (plans podem conter PDFs base64, imagens, estruturas), a serialização pode exceder 100 s em produção. Em preview com 0 planos, instantâneo.
- **`GET /api/takeoffs/{plan_id}/page/{pageIndex}`** com PDF grande.

**Mitigação**: paginação + projection Mongo que exclua campos pesados em `GET /api/takeoffs` (listar só metadata).

### 🟠 Hipótese B — Exception a meio do streaming
Se um endpoint começa a devolver bytes e crasha a meio (ex: `datetime` não serializável, `ObjectId` leaking, Pydantic validation error após primeiro flush), o Cloudflare recebe body truncado e devolve 520.

**Mitigação**: `try/except` global com `logger.exception()` nos endpoints `/takeoffs/*`.

### 🟡 Hipótese C — Env var em falta em produção
Logs preview mostram:
```
engines.monetization - WARNING - STRIPE_SECRET_KEY manquant — Stripe désactivé
```
Isto é um warning benigno. Mas se em produção falta `AUTODESK_CLIENT_ID`, `GEMINI_API_KEY` ou `TAVILY_API_KEY`, algum endpoint pode fazer uma chamada externa e timeout.

**Mitigação**: validar na página `/admin` ou `/health` que todas as env vars críticas estão presentes.

### 🟢 Hipótese D — Diferença de versão produção vs preview
Deploy mais antigo em produção pode conter bug já fixado em preview.

**Mitigação**: redeploy do preview actual.

### 🟢 Hipótese E — Mongo sem index em produção
Query `{"user_id": "..."}` sem index numa collection `takeoffs` grande → full scan → timeout. Em preview a collection está (quase) vazia.

**Mitigação**: `db.takeoffs.create_index("user_id")`.

---

## 6. Fix NÃO aplicado — motivo

**Não é possível identificar o endpoint culpado sem acesso aos logs de produção.** Aplicar um fix cego a `GET /api/takeoffs` (ex: paginação) é possível mas pode não corrigir se o problema estiver noutro sítio (hipótese C ou E).

---

## 7. Próximos passos recomendados ao utilizador

Para avançar, precisamos de **UM** dos seguintes:

1. **Logs produção**: aceder ao painel de deploy (Emergent) e extrair os logs do backend `construpilot.pt` ao momento em que o toast aparece. Procurar por:
   - HTTP status != 200 (ex: 500, 502, 504)
   - Exception / Traceback
   - Linhas com `takeoffs` ou `beton-`
   - Tempo de resposta anormalmente alto (>10s)

2. **DevTools do browser em produção**:
   - Abrir `https://construpilot.pt/plan` logado
   - F12 → Network tab → Preserve log
   - Reproduzir o erro
   - Identificar qual request devolve 520 (status vermelho) e colar o pathname + response headers aqui.

3. **Redeploy do preview actual**: se a hipótese D for a correcta, basta redeploy. Preview actual tem 296 pytests a passar e `yarn build` OK.

### Fix defensivo pré-emptivo (opcional, baixo risco)
Enquanto esperamos info, posso aplicar o seguinte (não aplicado ainda):

a. **Paginação em `GET /api/takeoffs`** com projection a excluir `plan_data`, `pdf_data`, `pages` → só devolver `plan_id`, `title`, `created_at`, `page_count`.
b. **`try/except logger.exception` wrapper** nos top-N endpoints de `/takeoffs/*`.
c. **Timeout explícito de 15s** nas chamadas externas (Autodesk, Gemini, Tavily) com fallback.
d. **`ensure_indexes()`** no startup para garantir `("user_id", 1)` em `takeoffs`.

---

## 8. Estado actual

- Preview estável, 100% operacional.
- 296 pytests a passar.
- `yarn build` OK.
- Scope restrito a este bug: nenhuma alteração ainda aplicada.
