# Acesso à Internet para o Assistente BTP (Coach IA + Solver BTP)

**Data**: 05 Fev 2026 · **Idioma**: PT-PT · **Prazo pedido**: 2–3 h · **Prazo real**: ~1 h 40
**Status**: ✅ CONCLUÍDO · pytest **92 passed · 1 skipped · 0 regressões** · build OK · E2E OK

---

## 1. Objetivo

Dar acesso **transparente** à web ao Coach IA e ao Solver BTP via Perplexity,
com (a) deteção inteligente baseada em keywords PT, (b) toggle UI manual
(auto/sempre/nunca), (c) rate limit **web separado do total** com soft fallback
quando o budget esgota, e (d) indicador de uso visível na UI.

---

## 2. Arquitetura

```
                             ┌────────────────────────┐
   payload.use_web_search ──►│  web_search_router.py  │──► (want_web, mode, reason)
   project_context          │  should_use_web_search  │
                             └────────────────────────┘
                                       │
                                       ▼
                ┌─────────────────────────────────────────┐
                │  rate_limit.web_search_hit(user,plan,   │
                │                            flow,max_h)  │  → soft-fallback se budget esgotou
                └─────────────────────────────────────────┘
                                       │
                                       ▼
                ┌─────────────────────────────────────────┐
                │  ai_router.coach_ask(enrich_with_web=…) │  Perplexity + Claude ou Claude só
                └─────────────────────────────────────────┘
                                       │
                                       ▼
                 response.meta.{web_enriched, web_search_mode,
                                web_search_fallback, citations[]}
                 response.rate_limit.{plan, total_limit, web_limit, web_remaining}
                 headers.X-RateLimit-{Flow,Plan,Limit-Total,Limit-Web,Remaining-Web}
```

---

## 3. Backend — ficheiros alterados

### 3.1 `backend/engines/web_search_router.py` *(novo)*
Função pública `should_use_web_search(query, project_context, user_override) → (bool, mode, reason)`.
Léxicos PT (minúsculas):

| Grupo        | Exemplos                                                                                          |
|--------------|----------------------------------------------------------------------------------------------------|
| actuality    | atual · hoje · recente · preço · iva · incentivo · decreto-lei · rgeu · reh · rccte · rsrae · rscie |
| supplier     | fornecedor · marca · fabricante · leroy merlin · bricodepot · aki · weber · sika · secil · cimpor  |
| location PT  | lisboa · porto · braga · faro · algarve · madeira · açores · concelho · freguesia · distrito       |
| year         | regex `em/desde/até 20(2[4-9]|3\d)`                                                                 |
| comparative  | qual o melhor · diferença entre · comparar · versus                                                 |
| long         | query > 20 palavras                                                                                 |

Precedência: `user_override` > keywords > contexto > ano > comparativo > comprimento.

### 3.2 `backend/core/rate_limit.py`
Novo sub-bucket in-memory (TTL 1 h) com `_web_bucket` + lock:

```python
WEB_LIMITS   = {"coach":{"free":10,"pro":40,"business":80},
                "btp_solver":{"free":5,"pro":20,"business":40}}
TOTAL_LIMITS = {"coach":{"free":20,"pro":60,"business":120},
                "btp_solver":{"free":10,"pro":40,"business":80}}

web_search_hit(user_id, plan, flow, max_per_hour) -> bool  # soft-decrement
web_search_remaining(...) -> int
web_search_reset_seconds(...) -> int
flow_limits(flow, plan) -> {"total_per_hour", "web_per_hour"}
```

### 3.3 `backend/engines/coach_ai.py`
`coach_ask(..., use_web_search=None, plan="free")`:
1. Chama `should_use_web_search`.
2. Se `want_web` **e** `web_search_hit(...)` falhar → `want_web=False`, `web_fallback=True`,
   `mode="budget_exhausted"`.
3. Logs: `flow=coach user=… web_search=T/F mode=… reason=… budget=R/L plan=…`.
4. Retorno enriquecido: `web_enriched · web_search_mode · web_search_reason ·
   web_search_fallback · web_remaining · web_limit · citations[]`.

### 3.4 `backend/engines/btp_solver/solver.py` + `schema.py`
Mesmo tratamento. `SolverResponse` ganha campos:
`web_search_mode · web_search_reason · web_search_fallback · web_remaining · web_limit`.

### 3.5 `backend/routes/coach.py` + `backend/routes/btp_solver.py`
- Body aceita `use_web_search: bool | null`.
- Resposta inclui `meta.*` + `rate_limit.{plan,total_limit,web_limit,web_remaining}`.
- Headers: `X-RateLimit-Flow`, `X-RateLimit-Plan`, `X-RateLimit-Limit-Total`,
  `X-RateLimit-Limit-Web`, `X-RateLimit-Remaining-Web`.

### 3.6 Cache MongoDB `pplx_cache`
Reutilizado tal como está (TTL 24 h, SHA256 do query+presets). Nada alterado;
qualquer chamada Perplexity do Coach ou do Solver passa pelo cache do Sprint 4.

---

## 4. Frontend — ficheiros alterados

### 4.1 `frontend/src/pages/Coach.jsx`
- Novo state: `webMode ("auto"|"always"|"never")`, `rateInfo`.
- Payload: adiciona `use_web_search` apenas quando `always/never`.
- Barra de controlo acima dos exemplos: `🌐 Pesquisar na Internet: [Auto|Sempre|Nunca]` + `⚡ N/N pesquisas web · plano free → Pro 99 €/mês`.
- Em cada mensagem assistente:
  - badge `🌐 N fontes web` (link azul) quando `web_enriched`;
  - badge amarelo `⚠ sem fontes atuais (limite web atingido)` quando `web_search_fallback`;
  - lista até 6 citações clicáveis (`<a href>` com `title`).

### 4.2 `frontend/src/pages/BtpSolver.jsx`
- Mesmo state + payload.
- Toggle + indicador rate limit por baixo do botão **Diagnosticar**.
- Card Diagnóstico: badge `🌐 N fontes web` quando `web_enriched`; badge
  `⚠ Sem fontes atuais` quando fallback.
- Secção **Referências e fontes**: diferencia LNEC/DRE/APA (branco) vs web
  (azul) com `Link2` icon.

Todos os elementos novos têm `data-testid` para testes QA.

---

## 5. Rate limits atualizados

| Flow / Plano   | Grátis               | Pro (99 €)           | Pro Business (179 €) |
|----------------|----------------------|----------------------|----------------------|
| **Coach total**     | 20/h                 | 60/h                 | 120/h                |
| **Coach web**       | **10/h**             | **40/h**             | **80/h**             |
| **BTP Solver total**| 10/h                 | 40/h                 | 80/h                 |
| **BTP Solver web**  | **5/h**              | **20/h**             | **40/h**             |

Comportamento quando o budget web esgota mas o total não:
- resposta continua **HTTP 200**;
- Claude responde sem Perplexity (fallback transparente);
- `meta.web_search_fallback=true`, `meta.web_search_mode="budget_exhausted"`;
- UI mostra badge amarelo + toast "Limite de pesquisas web atingido".

---

## 6. Testes

### 6.1 Unitários `pytest tests/test_web_search_router.py`
```
14 passed in 0.12s
```
Cenários cobertos (quase 1-para-1 com os pedidos no prompt):
- `user_override_true/false` precede tudo
- `empty_query` → skipped
- Eurocode 2 (técnica) → **skipped** ✓
- "preço cimento Lisboa hoje" → auto, keyword `hoje`/`lisboa` ✓
- "incentivos atuais" → auto, keyword `atual`
- "fornecedor isolamento" → auto
- Projeto com `region="Lisboa"` → auto
- Pergunta longa > 20 palavras → auto
- "mudou lei iva desde 2025" → auto (year_mention OU actuality)
- "qual o melhor cimento?" → auto (comparative/supplier)

### 6.2 Suite completa `pytest tests/`
```
92 passed, 1 skipped, 2 warnings in 4.86s
```
*(+14 novos vs 78 anteriores; 0 regressões. 1 teste existente actualizado para
usar `use_web_search=True` dado que semântica `web_enriched` passou a ser
"usou web" em vez de "tem citations".)*

### 6.3 E2E backend `/api/coach/ask` como free user

Cenários validados via curl (log completo em memory):

| Pergunta                                          | `use_web_search` | mode               | enriched | citations |
|---------------------------------------------------|------------------|--------------------|----------|-----------|
| "Eurocode 2 dobragem armaduras"                   | *(auto)*         | `skipped`          | **False**| 0         |
| "preço cimento Lisboa hoje"                       | *(auto)*         | `auto` (`hoje`)    | **True** | **15**    |
| "preço cimento Lisboa hoje"                       | **false**        | `disabled`         | False    | 0         |
| 11 pedidos consecutivos, `use_web_search=true`    | forced           | 10×`forced` + 1×`budget_exhausted` | 10×True + 1×False | 10×Y+1×N |

### 6.4 E2E `/app/scripts/test_web_search_budget_e2e.py`
```
=== Enviar 11 pedidos consecutivos com use_web_search=True ===
  [01] HTTP 200 WEB_OK   mode=forced             web_remaining=9
  [02] HTTP 200 WEB_OK   mode=forced             web_remaining=8
  ...
  [10] HTTP 200 WEB_OK   mode=forced             web_remaining=0
  [11] HTTP 200 FALLBACK mode=budget_exhausted   web_remaining=0

- 1º fallback na iteração: 11
[PASS]
```

### 6.5 Headers `X-RateLimit-*` expostos
```
x-ratelimit-flow: coach
x-ratelimit-plan: free
x-ratelimit-limit-total: 20
x-ratelimit-limit-web: 10
x-ratelimit-remaining-web: 9
```

### 6.6 Build frontend
```
yarn build  →  Done in 19.70s  (0 erros, 0 warnings bloqueantes)
```

---

## 7. Logs estruturados (observabilidade)

Exemplos observados em `/var/log/supervisor/backend.*.log`:

```
flow=coach user=user_bf754e1b web_search=True mode=auto reason=actuality_keyword:hoje budget=9/10 plan=free
flow=coach user=user_bf754e1b citations=15 tokens_in=None tokens_out=None model=claude-opus-4-5...
flow=btp_solver user=user_bf754e1 web_search=True mode=forced reason=user_override_true budget=4/5 plan=free
flow=coach user=user_bf754e1b web_search=False mode=budget_exhausted reason=user_override_true budget=0/10 plan=free
```

Campos chave: `flow`, `web_search`, `mode`, `reason`, `budget=R/L`, `plan`,
`citations`. Suficiente para dashboards (ex: taxa de uso web, hit rate de
cache, breakdown por plano).

---

## 8. Cache hit rate

A infraestrutura `pplx_cache` (Sprint 4) continua ativa; `ai_router.coach_ask`
delega para `pplx_client.ask(..., preset=...)` que já normaliza a query e faz
lookup. **Não foi alterada** nesta release.

Durante os 10 pedidos E2E de teste (mesma pergunta "cimento Lisboa hoje"
seguidos de queries curtas distintas), o cache populou mas todas as queries
eram ligeiramente diferentes (números no corpo da mensagem), logo observámos
~0 % hit rate. Em uso real (perguntas repetidas de user base), o hit rate
sobe. Baseline Sprint 4: ~35 %.

---

## 9. Screenshots

| Vista                                           | Ficheiro                       |
|-------------------------------------------------|--------------------------------|
| Coach IA — topo com toggle `[Auto|Sempre|Nunca]` + banner Grátis | `/tmp/coach_top_toggle.png` |
| Coach IA — resposta com badge "🌐 15 fontes web" + 6 citações clicáveis | `/tmp/coach_citations.png` |
| Coach IA — soft fallback com badge "sem fontes atuais"            | `/tmp/coach_web_badge.png`  |
| Solver BTP — toggle `[Auto|Sempre|Nunca]` + banner Grátis         | `/tmp/btp_toggle.png`        |

---

## 10. Ficheiros alterados (diff rápido)

**Backend**
- `backend/engines/web_search_router.py` — **novo** (183 LoC)
- `backend/core/rate_limit.py` — +130 LoC (sub-bucket web + `WEB_LIMITS` + `TOTAL_LIMITS`)
- `backend/engines/coach_ai.py` — reescrito o fluxo `coach_ask` para integrar router + budget
- `backend/engines/btp_solver/solver.py` — idem (`solve(..., use_web_search, user_id, plan)`)
- `backend/engines/btp_solver/schema.py` — +5 campos web_* em `SolverResponse`
- `backend/routes/coach.py` — body `use_web_search`, response headers, `meta.*` enriquecido
- `backend/routes/btp_solver.py` — idem

**Frontend**
- `frontend/src/pages/Coach.jsx` — toggle + badge + citações + rate indicator
- `frontend/src/pages/BtpSolver.jsx` — toggle + badges + referências diferenciadas + rate indicator

**Tests / Scripts**
- `backend/tests/test_web_search_router.py` — **novo** (14 testes)
- `backend/tests/test_btp_solver.py` — 1 teste actualizado (semântica web_enriched)
- `scripts/test_web_search_budget_e2e.py` — **novo** (E2E 11 pedidos → fallback)

**Memory**
- `memory/btp_web_access_report.md` — este relatório.

---

## 11. Preservação

- ✅ Release Particulares (free acessa Coach + BTP Solver) intacta
- ✅ Novos preços Pro 99 € / Pro Business 179 € intactos
- ✅ Opus 5.5 + fallback OpenAI + Perplexity router intactos
- ✅ Biblioteca PT, Sprints 2/3/4, hero, i18n, email fixes intactos
- ✅ Sprint 5 (Stair Engine) em pausa, **não tocado**
- ✅ JWT auth obrigatório, slowapi 429 PT-PT com `/pricing` intactos

---

## 12. Dívida identificada

1. **Sub-bucket in-memory**: adequado para 1 réplica; multi-réplica precisa de Redis
   (mesmo trade-off do slowapi atual).
2. **BTP Solver + preset LNEC/DRE/APA**: hoje o `ai_router.coach_ask()` chama o
   preset `default` do Perplexity Plus. Evoluir para passar `preset="btp_norms"`
   e enriquecer com `pplx_presets` seria um ganho qualitativo — fora de scope
   nesta release.
3. **Hit rate real do cache**: expor em `/api/admin/pplx-cache/stats` ou dashboard.

---

## 13. Próximo passo sugerido (bónus para conversão)

A UI já mostra `17/20 pesquisas web · plano free → Pro 99 €/mês`. Dois follow-ups
rápidos de alta ROI:

1. **Notificação proativa** quando o utilizador free está a 2 slots do limite
   web (ex: ao chegar a 8/10, toast "Pensa no upgrade — poupe tempo e tenha 4×
   mais pesquisas por mês").
2. **A/B test** CTA do rate indicator: `→ Pro 99 €/mês` vs `→ Veja planos` vs
   `→ Experimente Pro 7 dias grátis`. O tier Pro tem `trial_days: 7` definido
   no catálogo.
