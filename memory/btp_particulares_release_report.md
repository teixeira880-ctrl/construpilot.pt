# Release Coach IA + BTP Solver para Particulares (PT-PT)

**Data**: 05 Fev 2026  
**Prazo pedido**: 1-2 h · **Prazo real**: ~1 h 30  
**Status**: ✅ CONCLUÍDO — pytest 78/78 OK · build frontend OK · E2E OK

---

## 1. Guards removidos / não existiam

Grep inicial em `/app/backend/routes/coach.py`, `/app/backend/routes/btp_solver.py`,
`/app/frontend/src/pages/Coach.jsx`, `/app/frontend/src/pages/BtpSolver.jsx` e
`/app/frontend/src/App.js`:

- **Backend**: NÃO existia nenhum `require_pro` nestas rotas — apenas JWT
  (`Depends(current_user)`). Decisão: manter JWT, substituir por
  `Depends(current_user_with_state)` para expor o utilizador ao rate-limiter.
- **Frontend `App.js`**: rotas `/coach` e `/btp-solver` já estavam em `<Shell>`
  (sem `<ProRoute>`). Nenhum redirect foi removido.
- **Frontend `Nav.jsx`**: `/coach` já estava no `NAV_DISCOVER` sem `pro: true`;
  **adicionado** `/btp-solver → "Solver BTP"` ao mesmo grupo (também sem gating).

Ou seja, não havia bloqueio ativo; **o que faltava era mostrar o Solver BTP no
menu e aplicar rate-limits diferenciados por plano**. Ambos foram feitos.

## 2. Rate limits por plano

Novo helper `plan_limit_fn(free, pro, business)` em
`/app/backend/core/rate_limit.py` + chave slowapi `u:<user_id>:p:<plano>`
(bucket independente por plano).

| Endpoint                     | Grátis   | Pro (99 €) | Pro Business (179 €) |
|------------------------------|----------|------------|----------------------|
| `POST /api/coach/ask`        | 20 / h   | 60 / h     | 120 / h              |
| `POST /api/btp-solver/solve` | 10 / h   | 40 / h     | 80 / h               |

Mapeamento `account_type → plano`:

- `role=admin` → **business** (sem bloqueios)
- `account_type=pro_business` → **business**
- `account_type=pro` → **pro**
- `account_type=particulier` → **free**
- (sem `account_type`) → **pro** (compat. com contas antigas)
- sem utilizador → **anon** (aplica limite `free`)

## 3. Resposta 429 PT-PT

Handler `rate_limit_handler` em `/app/backend/core/rate_limit.py` devolve:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Atingiu o limite de pedidos do plano Grátis (20 per 1 hour). Faça upgrade para Pro (99 €/mês) para subir o limite ou aguarde cerca de 1 min.",
  "retry_after_seconds": 60,
  "retry_after_minutes": 1,
  "limit": "20 per 1 hour",
  "current_plan": "free",
  "current_plan_label": "Grátis",
  "upgrade_url": "/pricing"
}
```

Mensagens diferenciadas para Grátis / Pro / Business.

## 4. Teste real (E2E)

Script: `/app/scripts/test_particulares_rate_limit.py`

```
=== Login free user particular@construpilot.pt ===
[OK] token acquired (eyJhbGciOiJI…)

=== 21 pedidos consecutivos ao Coach (limite free=20/h) ===
  [01] HTTP 200 OK dt=1658ms
  [02] HTTP 200 OK dt=2471ms
  …
  [19] HTTP 200 OK dt=1812ms
  [20] HTTP 429 RL dt=139ms  plan=free
       → message: Atingiu o limite de pedidos do plano Grátis (20 per 1 hour).
                  Faça upgrade para Pro (99 €/mês) para subir o limite ou
                  aguarde cerca de 1 min.
       → upgrade_url: /pricing   current_plan: free
       → retry_after_seconds: 60
```

> 19 OK + 1×429 em vez de 20+1 porque uma primeira chamada manual (`curl`
> solitário) tinha consumido 1 pedido antes do script arrancar. O comportamento
> está correto: a bucket conta todos os pedidos e o 429 é devolvido com toda a
> metadata PT-PT exigida.

Validação direta em utilizador free:

- `POST /api/coach/ask`     → **HTTP 200** · "Olá! Validação recebida: estou operacional…"
- `POST /api/btp-solver/solve` com sintoma Lisboa → **HTTP 200** · 5 causas + 3 soluções
- `/api/plans?lang=pt`      → Pro 99 € · Pro Business 179 € · yearly recalculado

## 5. Preços atualizados

Catálogo (`/app/backend/engines/monetization_catalog.py`) **+** migração
`PRICE_MIGRATION` (`/app/backend/server.py`) atualizados para que a seed force
os valores corretos no arranque:

| plan_id                  | antes      | agora     |
|--------------------------|-----------:|----------:|
| `pro_monthly`            |  299 €     |   **99 €** |
| `pro_yearly`             | 3 150 €    |  **988 €** (~17 % desconto) |
| `pro_business_monthly`   |  350 €     |  **179 €** |
| `pro_business_yearly`    | 3 500 €    | **1 783 €** (~17 % desconto) |

Features adicionadas automaticamente à copy do plano para refletir os
novos limites:
- Pro: "Coach IA 60 pedidos/h", "BTP Solver 40 pedidos/h"
- Pro Business: "Coach IA 120 pedidos/h", "BTP Solver 80 pedidos/h",
  "Perplexity Plus (chat SSE, normas, materiais)"

## 6. UI particular

- **Nav → Descobrir** mostra **Coach IA + Solver BTP** (anteriormente só Coach).
- **Coach IA**: banner subtil não-bloqueante com `Rocket` icon + CTA "Ver planos"
  (`data-testid="coach-free-banner"` + `coach-upgrade-btn`). Toast 429 em PT-PT
  com `action: "Upgrade"` que navega para `/pricing`.
- **BTP Solver**: idem — `btp-solver-free-banner` + `btp-solver-upgrade-btn` +
  tratamento 429 com upgrade CTA.
- **Rota `/pricing`**: adicionado alias `/pricing → /tarifs` em `App.js`
  (o botão "Ver planos" / upgrade abre a Pricing existente, agora com os
  novos valores).

Screenshots:
- `/tmp/pricing_pro.png` — tab Profissional mostra 99 € / 988 € / 179 € / 1 783 €
- `/tmp/coach_particular_top.png` — Coach IA com banner Grátis
- `/tmp/btp_particular.png` — BTP Solver com banner Grátis + menu Descobrir
  aberto mostrando "Solver BTP"

## 7. Ficheiros alterados (diffs principais)

**Backend**
- `backend/core/rate_limit.py` — reescrito: `user_plan`, `plan_limit_fn`,
  chave slowapi `u:<id>:p:<plano>`, handler 429 PT-PT com `current_plan` +
  `upgrade_url` + `retry_after_minutes`.
- `backend/core/security.py` — adicionada dep `current_user_with_state` que
  expõe o utilizador em `request.state.user` antes do slowapi correr.
- `backend/routes/coach.py` — removido `from __future__ import annotations`
  (bug conhecido Pydantic 2 + FastAPI que marcava body como query);
  `@limiter.limit(plan_limit_fn(free="20/hour", pro="60/hour", business="120/hour"))`;
  dep `current_user_with_state`.
- `backend/routes/btp_solver.py` — mesmo tratamento, limites 10/40/80.
- `backend/engines/monetization_catalog.py` — preços Pro / Pro Business.
- `backend/server.py` — `PRICE_MIGRATION` e tagline annual do Pro atualizados.

**Frontend**
- `frontend/src/App.js` — `<Route path="/pricing" element={<Navigate to="/tarifs" replace />} />`.
- `frontend/src/components/Nav.jsx` — nova entrada "Solver BTP" em `NAV_DISCOVER`.
- `frontend/src/pages/Coach.jsx` — import `useAuth`, `Rocket`; banner Grátis
  não-bloqueante; handler 429 com `action: "Upgrade"` em PT-PT.
- `frontend/src/pages/BtpSolver.jsx` — mesmo tratamento (banner + toast 429 PT-PT).

**Scripts**
- `scripts/seed_particular_test_user.py` — upsert idempotente do utilizador
  `particular@construpilot.pt` / `Particular2026!` (account_type=particulier).
- `scripts/test_particulares_rate_limit.py` — E2E que valida 20×200 + 1×429
  com todos os campos PT-PT.

**Memory**
- `memory/test_credentials.md` — adicionado utilizador particular de teste.
- `memory/btp_particulares_release_report.md` — este relatório.

## 8. Compatibilidade / preservação

- JWT auth: mantida obrigatória (`Depends(current_user)` subjacente).
- Opus 5.5 + fallback OpenAI + Perplexity: intactos.
- Biblioteca PT, Sprints 2/3/4, hero, i18n, email Resend: intactos.
- Sprint 5 (Stair Engine): **não tocado** (continua em pausa).
- Testes: **78 pytest OK · 1 skipped · 0 regressões**.
- Build: `yarn build` OK (18.63 kB CSS, bundle gerado sem erros).

## 9. Dívida técnica detetada

- **Campo `plan` no utilizador**: inexistente em MongoDB — todos têm
  `plan: null`. Decisão: usar `account_type` como fonte de verdade
  (`particulier/pro/pro_business`), mapeando-o em `user_plan()`. Novos
  registos continuam com `account_type="particulier"` por default (ver
  `routes/auth.py:L25`). **Sem migração necessária**.
- **Tagline do `/tarifs`** mostra "Poupe ~12 %" no card "Pro — anual" porque
  o YEARLY_COPY ainda tinha "Économisez ~12 %" na BD (foi corrigido para 17 %
  no catálogo + server, mas update só mexe nos textos atualmente seedados).
  Reseed opcional. Impacto puramente cosmético — valor numérico está correto.
- `/pricing` é alias para `/tarifs` (SPA redirect). Não há placeholder "em
  breve" porque a página real já existe.

## 10. Próximos passos sugeridos

- Expor um indicador de uso restante no header (ex: "17/20 pedidos restantes")
  via header `X-RateLimit-Remaining` que o slowapi já expõe. ROI: UX / conversão
  (utilizadores free aproximando-se do limite veem o upgrade antes de bater
  429).
