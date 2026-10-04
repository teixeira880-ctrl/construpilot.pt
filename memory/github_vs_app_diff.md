# Diff `/tmp/inspect_repo` vs `/app` — ConstruPilot

**Data**: 2026-02-04
**Operador**: E1

---

## Sumário executivo

1. **Impossível comparar**: o repo remoto `https://github.com/teixeira880-ctrl/construpilot.pt` devolveu **HTTP 404** em todas as tentativas de acesso público (ver `github_recon_report.md`). Nenhum ficheiro foi obtido do GitHub.
2. **Risco de perder trabalho**: **nulo nesta fase** — nenhum merge foi feito. Qualquer merge futuro vindo de um repo mais antigo poderá sobrepor o trabalho recente em `/app` (migração AI providers, Coach IA, Aurora master spec), por isso **recomenda-se merge só por cherry-pick manual**, nunca `git pull` cego.
3. **Código útil só no remoto**: **desconhecido** — não foi possível inspecionar o remoto. Só confirmável após o utilizador fornecer PAT ou URL correto.

---

## 1. Comparação formal

Impossível executar `diff -r --brief /tmp/inspect_repo /app` porque `/tmp/inspect_repo` está vazio.

| Métrica | Valor |
|---|---|
| Ficheiros só no remoto | **?** (0 obtidos) |
| Ficheiros só em `/app` | ver secção 2 |
| Ficheiros com conteúdo diferente | **?** |
| Linhas alteradas | **?** |

---

## 2. Estado atual de `/app` (contexto para merge futuro)

Trabalho **acumulado em `/app`** desde o último sync com qualquer repo externo (ordem cronológica inversa, por commits locais):

| Commit | Descrição | Impacto |
|---|---|---|
| `effdbc1` | Aurora Master Spec v1.0 entregue | `/app/docs/aurora_master_spec.{md,pdf}` + endpoint PDF |
| `42dbec1` | Coach IA · migração Aurora exclusivo (18/18 testes verdes) | `routes/coach.py`, `engines/coach_aurora.py` |
| `62a45e3` | Fase A + B concluídas (11/11 testes verdes) | fixes Aurora backend |
| `d84a592` | Fix crítico Aurora `/ask` parsing (10/10 testes) | `engines/aurora_client.py` |
| `f3aca77` | Estado debug Aurora `/ask` | documentação |

### Ficheiros **novos (untracked)** gerados nesta sessão (não commitados)
```
backend/engines/ai_providers/           # pacote completo (Claude/OpenAI/Perplexity router)
backend/engines/coach_ai.py             # Coach IA via router multi-provider
backend/routes/ai_health.py             # GET /api/admin/ai-health
backend/scripts/test_ai_providers_e2e.py
backend/scripts/test_coach_fallback.py
frontend/src/components/ServiceApologyBanner.jsx
```

### Ficheiros **modificados** (não commitados)
```
backend/requirements.txt                # +anthropic, +openai, +weasyprint, +markdown
backend/routes/admin.py                 # endpoint ai-health injetado
backend/routes/coach.py                 # redirecionamento Aurora→router
backend/routes/projects.py              # Phase 2 plan analyzer refactor
backend/server.py                       # mount dos novos routers
frontend/src/pages/LandingPortugal.jsx  # injeção do ServiceApologyBanner
```

**Nenhum destes ficheiros existe (presumivelmente) no repo remoto** — foram criados após qualquer snapshot que o utilizador tenha feito ao GitHub.

---

## 3. Recomendações por divergência

Dado que não há remoto para comparar, as recomendações são **preventivas** para o momento em que o repo for acessível:

| Área | Recomendação | Justificação |
|---|---|---|
| Pacote `backend/engines/ai_providers/*` | `KEEP_APP` | Criado nesta sessão por pedido explícito do utilizador (pivot Aurora→Claude/OpenAI/Perplexity). Não existe no remoto. |
| `backend/engines/coach_ai.py` | `KEEP_APP` | Idem. |
| `backend/routes/ai_health.py` | `KEEP_APP` | Idem. |
| `backend/scripts/test_ai_providers_e2e.py`, `test_coach_fallback.py` | `KEEP_APP` | Scripts internos de validação. |
| `frontend/src/components/ServiceApologyBanner.jsx` | `KEEP_APP` | Decisão UX recente. |
| `backend/engines/aurora_*.py` (legacy) | `MERGE_MANUAL` | Dormante (`AURORA_ENABLED=false`). Se o remoto trouxer versão nova, decidir caso a caso — não restaurar o path Aurora como primário. |
| `backend/.env` e `.env.example` | `KEEP_APP` + revisar | Nunca sobrepor `.env` real. `.env.example` pode receber chaves novas do remoto se forem relevantes. |
| `backend/requirements.txt` | `MERGE_MANUAL` | Union manual: manter `anthropic`, `openai`, `weasyprint`, `markdown` + trazer o que o remoto adicionou. |
| `frontend/package.json` | `MERGE_MANUAL` | Idem para deps novas. |
| Rotas FastAPI já existentes em `/app` | `KEEP_APP` | Representam estado estável atual. |
| Rotas FastAPI **novas** só no remoto | `MERGE_MANUAL` após inspeção | Avaliar se se aplicam à arquitetura actual. |

### Regra geral de merge
- **Nunca** executar `git pull --rebase origin main` nem `git merge origin/main` cegos.
- Clonar o remoto para `/tmp/inspect_repo` → `diff -r --brief` → aplicar **cherry-pick manual** apenas para o que trouxer valor.

---

## 4. O que falta para completar este relatório

1. Acesso ao repo remoto (PAT ou URL correto).
2. Clone efectivo para `/tmp/inspect_repo`.
3. Execução de:
   ```bash
   diff -rq /tmp/inspect_repo /app > /tmp/diff_brief.txt 2>&1
   diff -r  /tmp/inspect_repo /app | diffstat -p1 > /tmp/diff_stat.txt 2>&1
   ```
4. Preencher as secções em branco deste documento e do `github_recon_report.md`.

---

## 5. Confirmações finais

- **`/app` não foi alterado** por esta operação (os ficheiros `?? ... M ...` no `git status` são todos **anteriores** aos créditos acabarem — do trabalho da migração AI).
- **`/tmp/inspect_repo`** permanece vazio.
- **`.env`** confirmado com todas as chaves + `AURORA_ENABLED` resolvido como `false` (sem leak de valores).
