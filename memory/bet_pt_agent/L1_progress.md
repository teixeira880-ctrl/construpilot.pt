# L1 — Progresso BET-PT Agent (checkpoint de encerramento)

**Última actualização**: 2026-10-18 (encerrado por instrução do fundador —
pivot para o Claude escrever ele próprio o núcleo dos motores primeiro no `.fr`).

**Modo actual**: ⏸ **PASSIVO**. Nenhum novo trabalho em `/app/backend/engines/bet_agent/`
sem instrução explícita futura. Mantém-se apenas o monitor reactivo ao
`demo-status` em prod para o checkpoint D7.

---

## 1. Estado por sub-passo

| Sub-passo | Estado | Ficheiros entregues |
|---|---|---|
| **L1.0** Setup do módulo | ✅ concluído | `engines/bet_agent/__init__.py` (feature flag `is_enabled()`) + estrutura de pastas isolada. |
| **L1.1** Modelos Pydantic | ✅ concluído | `engines/bet_agent/models/{building.py,brief.py,summary.py,__init__.py}` + `registry/deliverables_pt.py` (enum + CRITICAL + OUT_OF_SCOPE). |
| **L1.2** Brief parser | ✅ concluído | `engines/bet_agent/brief.py` (parse + `hypotheses_used` + defaults documentados). |
| **L1.2b** Zonas sísmicas PT | ✅ concluído | `engines/bet_agent/registry/zonas_sismicas_pt.py` (agR 1.1–1.6 + 2.1–2.5, classes solo A–E, mapeamento concelho→zona inicial com Lisboa CONFIRMADO e resto PENDENTE). Fontes citadas inline. |
| **L1.3** Reader (Anthropic SDK + tool-use + caching) | ✅ concluído | `engines/bet_agent/registry/pricing_claude.py` (preços docs.claude.com, 2026-10-18), `engines/bet_agent/agent/{client.py,tools.py,loop.py,verifier.py,prompts.py,__init__.py}`, `engines/bet_agent/reader.py` (entrypoint com pymupdf 300 DPI), `engines/bet_agent/pipeline.py` (orquestrador brief→reader→checks→verificador→summary). Fail-closed se flag off ou chave ausente. |
| **L1.4** Checks geo+sem base | ✅ concluído | `engines/bet_agent/checks/{geometric.py,semantic.py}` (GEO-001..006 + SEM-001/002/003/005; SEM-004 em `summary.py`). |
| **L1.4b** Checks GEO-005 + GEO-007 | ✅ concluído | funções `check_room_areas_vs_table` e `check_dimension_chain` em `engines/bet_agent/checks/geometric.py`. |
| **L1.5** Resumo honesto | ✅ concluído | `engines/bet_agent/summary.py` (`global_status`: vermelho/amarelo/verde; `missing_critical`; rodapé imposto) + integração verificador via `pipeline.py`. |
| **L1.6** Fixture sintética PT | ✅ concluído | `tests/fixtures/bet_agent/generate_moradia_pt.py` + saída em `moradia_pt_reticular_r2_cave_sotao/{arquitectura.pdf, geotecnico.pdf, brief.json, fixture_defects.md}` com 5 defeitos intencionais. |
| **L1.7** Testes unitários + integração | ✅ concluído | 15 ficheiros em `tests/engines/bet_agent/` (ver secção 2). Mocks em CI (`engines/bet_agent/testing_llm.py` + `engines/bet_agent/testing.py`). |
| **L1.8** UI admin (back + front) | ✅ concluído | Backend: `routes/admin_bet_agent.py` com 5 endpoints (`status`, `run`, `costs`, `runs`, `runs/{id}`) + registo em `server.py`. Frontend: `pages/AdminBetAgent.jsx` + rota `/admin/bet-agent` em `App.js` (Protected admin). |
| **L1.9** Playwright E2E | 🟡 escrito mas inacessível localhost | `frontend/e2e/bet_agent_admin.spec.js` (spec desktop + iPhone 13, suprime pop-up WebSummit e banner cookies via initScript). Falhou a correr em pod local porque o browser Playwright não consegue resolver o `REACT_APP_BACKEND_URL` externo preview a partir de `localhost:3000`. Ficheiro deixado em estado válido e documentado com nota de ambiente no topo. |
| **L1.10** Preview deploy + screenshots | ❌ não iniciado | nada feito (pivot do fundador antes de arrancar). |

**Teste `@pytest.mark.live`**: ❌ não criado. O plano era um teste manual (skip por omissão) que corre reader+verificador contra fixture com Claude real. Deferred — não foi arrancado.

---

## 2. Resultado do último pytest `tests/engines/bet_agent/`

```
cd /app/backend && PYTHONPATH=. python -m pytest tests/engines/bet_agent/ -q
...
99 passed, 6 warnings in 8.17s
```

Config `pytest.ini` padrão (`-n 2 --dist loadscope`). Zero chamadas Claude live.
Zero rede externa.

Distribuição por ficheiro:

| Ficheiro | Testes |
|---|---|
| `test_admin_routes.py` | 7 |
| `test_agent_loop.py` | 6 |
| `test_agent_tools.py` | 8 |
| `test_brief.py` | 7 |
| `test_building_model.py` | 6 |
| `test_checks_geometric.py` | 8 |
| `test_checks_geometric_l1_4b.py` | 11 |
| `test_checks_semantic.py` | 7 |
| `test_cost.py` | 6 |
| `test_fixture_moradia_pt.py` | 3 |
| `test_pipeline_e2e.py` | 2 |
| `test_reader_integration.py` | 2 |
| `test_registries.py` | 13 |
| `test_summary.py` | 9 |
| `test_verifier.py` | 3 |
| **Total** | **99 passed** |

---

## 3. Decisões já integradas (conforme instrução do fundador)

- **Modelos Claude** (via env var com default documentado):
  - Reader = `claude-opus-5-5`.
  - Verificador = `claude-opus-5-5` (sessão nova, cliente separado).
  - Sonnet 5.5 = `claude-sonnet-5-5` para brief/resumo/tarefas simples (prompt
    pronto em `agent/prompts.py` como `BRIEF_SYSTEM_PT`; chamada ainda não cablada
    porque L1 só exigia Opus + mocks).
- **Prompt caching** `ephemeral` aplicado nos blocos `system` + último `tool`
  no loop ReAct (`agent/loop.py`).
- **Preços** NÃO hardcoded no código — tabela em
  `engines/bet_agent/registry/pricing_claude.py` com:
  - Fonte canónica: `https://docs.claude.com/pricing`
  - `LAST_UPDATED = date(2026, 10, 18)`
  - TODO comentado para refrescar manualmente.
  - Função `estimate_cost_eur(model, usage, usd_eur_rate=0.93, cache_write_ttl)`
    pura + testada.
- **Teto de custo €10/dossier** (`BET_AGENT_COST_LIMIT_EUR`) com flag
  `CostBreakdown.exceeded_limit` que degrada o `global_status` para não-verde.
- **Interactividade híbrida**:
  - Bloqueante — tool `ask_user(question_pt, page, bbox, severity)` com crop
    (bbox) + loop interrompe (`stop_on_user_question=True` default).
  - Leve — ficam agregadas no `Summary` (campo `pending_questions` em
    `PipelineRun`).
- **Entregáveis obrigatórios** completos em `registry/deliverables_pt.py`
  (DeliverableKind enum + CRITICAL_DELIVERABLES + OUT_OF_SCOPE).
- **Fora de âmbito** (térmica REH, acústica, gás, SCIE) sempre marcados em
  `Summary.out_of_scope` + detectados por SEM-005 quando referenciados nas notas.
- **RTIEBT / DR 23/95**: campos presentes em `BuildingModel.electrical` com
  flags `rtiebt_scope_present`, `dr_23_95_scope_present`,
  `needs_future_computation=True`. Cálculo real diferido para L2/L3.
- **Verificador isolado**: `agent/verifier.py` com `VERIFIER_SYSTEM_PT`
  (sessão nova, zero histórico, chamada API separada via `AnthropicClient()`
  instanciado em separado no `pipeline.py`).
- **Rodapé obrigatório** `"pré-dimensionamento, a verificar e assinar pelo
  técnico responsável"` em `Summary.footer` (constante, não overridable).
- **Feature flag `BET_AGENT_ENABLED=false`** em todos os ambientes
  (preview + prod). Reader faz raise `ReaderDisabled` quando chamado com
  `enforce_flag=True` e flag off — zero crash.
- **ANTHROPIC_API_KEY** esperado como env var:
  - **Preview**: presente no `.env` do pod (confirmado por verificação sem
    expor valor — prefixo `sk-ant-`, 108 chars).
  - **Prod**: fundador confirmou injecção em `construpilot.pt`; validação
    pós-deploy ficará por fazer com chamada API mínima quando feature flag
    for ligada.
- **Mocks obrigatórios em CI** — `engines/bet_agent/testing_llm.py` com
  `MockLLMClient` + `ScriptedResponse`. Nenhum teste em CI chama Claude real.
- **Hipóteses do utilizador têm prioridade absoluta** sobre defaults —
  `DEFAULT_HYPOTHESES` em `models/brief.py` só são aplicados em
  `hypotheses_used()` quando o utilizador omite o campo, nunca sobrescrevem
  o `UserBrief`.

---

## 4. Ponto exacto onde parei

- **Último sub-passo activo**: L1.9 (Playwright E2E).
- **Última acção**: tentativa de correr `frontend/e2e/bet_agent_admin.spec.js`
  localmente. Falhou porque o browser Playwright a correr no pod localhost
  não conseguiu resolver o `REACT_APP_BACKEND_URL` externo preview — o fetch
  do login devolve `net::ERR_FAILED`.
- **Último ficheiro tocado**: `/app/frontend/e2e/bet_agent_admin.spec.js`
  (adicionada nota de ambiente no topo, inicialização de `sessionStorage`
  para suprimir pop-up WebSummit + `localStorage` para aceitar cookies).
- **Último teste a correr com sucesso**: `tests/engines/bet_agent/` → 99 passed.
- **Decisões pendentes do fundador antes de arrancar L1.10**: nenhuma —
  pivot imposto antes.

---

## 5. O que ficaria por fazer se o trabalho fosse retomado

(Documentado para memória — não é recomendação de continuação.)

1. **L1.9 Playwright E2E** — correr o spec `bet_agent_admin.spec.js` com
   `MOBILE_BASE_URL=<URL preview>` (ex: `https://construpilot-recon.preview.emergentagent.com`)
   em vez de `localhost:3000`. O spec já tem toda a lógica para suprimir
   overlays e fazer login admin.
2. **L1.10 Preview deploy + screenshots**:
   - Confirmar que preview rebuild carrega as 15 ficheiros bet_agent.
   - Capturar screenshots: `/admin/bet-agent` (status card), run detail dialog
     com anomalias + rodapé, costs panel.
   - Escrever `/app/memory/bet_pt_agent/L1_deploy.md` com evidências.
   - Zero deploy prod (feature flag OFF em prod).
3. **Teste `@pytest.mark.live`** — 1 teste manual que corre reader+verificador
   contra fixture PT com Claude real (ANTHROPIC_API_KEY), skip por omissão,
   activável via `pytest -m live`. Serve para validação pontual sem gastar
   créditos em cada CI.
4. **Mapeamento concelho→zonas sísmicas** — expandir
   `registry/zonas_sismicas_pt.py` com todos os concelhos de Portugal
   Continental + Açores + Madeira. Actualmente só Lisboa é `CONFIRMADO`;
   restantes são placeholders `PENDENTE`.
5. **Preços Haiku 5.5** — confirmar em `docs.claude.com` e remover TODO.
6. **Resolver divergência inter-fontes agR da zona 1.5** (0.5 vs 0.6 m/s²).
7. **Camada de produção de entregáveis** (L2/L3) — pensar como gerar os
   PDFs/DWGs da planta de fundações, cortes, etc.

Nenhum destes é bloqueio; o pacote L1 é estável e funcional como está.

---

## 6. Risco de regressão zero — confirmação

**Ficheiros tocados nesta sessão** (adições isoladas):

Backend novos:
```
engines/bet_agent/__init__.py
engines/bet_agent/brief.py
engines/bet_agent/reader.py
engines/bet_agent/summary.py
engines/bet_agent/cost.py
engines/bet_agent/pipeline.py
engines/bet_agent/testing.py
engines/bet_agent/testing_llm.py
engines/bet_agent/models/__init__.py
engines/bet_agent/models/brief.py
engines/bet_agent/models/building.py
engines/bet_agent/models/summary.py
engines/bet_agent/checks/__init__.py
engines/bet_agent/checks/geometric.py
engines/bet_agent/checks/semantic.py
engines/bet_agent/agent/__init__.py
engines/bet_agent/agent/client.py
engines/bet_agent/agent/loop.py
engines/bet_agent/agent/prompts.py
engines/bet_agent/agent/tools.py
engines/bet_agent/agent/verifier.py
engines/bet_agent/registry/__init__.py
engines/bet_agent/registry/deliverables_pt.py
engines/bet_agent/registry/pricing_claude.py
engines/bet_agent/registry/zonas_sismicas_pt.py
routes/admin_bet_agent.py
tests/engines/bet_agent/test_admin_routes.py
tests/engines/bet_agent/test_agent_loop.py
tests/engines/bet_agent/test_agent_tools.py
tests/engines/bet_agent/test_brief.py
tests/engines/bet_agent/test_building_model.py
tests/engines/bet_agent/test_checks_geometric.py
tests/engines/bet_agent/test_checks_geometric_l1_4b.py
tests/engines/bet_agent/test_checks_semantic.py
tests/engines/bet_agent/test_cost.py
tests/engines/bet_agent/test_fixture_moradia_pt.py
tests/engines/bet_agent/test_pipeline_e2e.py
tests/engines/bet_agent/test_reader_integration.py
tests/engines/bet_agent/test_registries.py
tests/engines/bet_agent/test_summary.py
tests/engines/bet_agent/test_verifier.py
tests/fixtures/bet_agent/generate_moradia_pt.py
```

Frontend novos:
```
frontend/src/pages/AdminBetAgent.jsx
frontend/e2e/bet_agent_admin.spec.js
```

**Edições pontuais** (único toque fora do bet_agent):
- `backend/server.py`: inseridas 2 linhas após o `include_router(admin_demo_routes.router)`
  para registar o novo router isolado. Zero remoção, zero modificação de
  comportamento existente.
- `frontend/src/App.js`: adicionado 1 `import AdminBetAgent` + 1 `<Route>`
  nova para `/admin/bet-agent`. Zero remoção, zero modificação de rotas
  existentes.

**Verificações pós-encerramento**:
- `supervisorctl status` → `backend / frontend / mongodb / mobile = RUNNING`.
- `curl http://localhost:8001/api/health` → `200 {"status":"ok","mongo":true}`.
- `pytest tests/engines/bet_agent/` → `99 passed`.
- Nenhum ficheiro em `.fr` tocado.
- Nenhum ficheiro em lotes BET anteriores (BET.0 → BET.6) tocado.

Risco de regressão: **zero**.

---

## 7. Estado do checkpoint D7 WebSummit (paralelo)

- `GET https://construpilot.pt/api/auth/demo-status` → `{"pro":false,"particular":false}` HTTP 200.
- Restart em prod ainda **não** ocorreu desde a adição dos segredos.
- `D7_activation.md` continua à espera da acção manual do fundador.
- Nenhuma intervenção P1-P6 disparada nesta sessão.

**Modo monitor**: se `demo-status` passar a `{"pro":true,"particular":true}`,
executar P1-P6 autónomos, capturar screenshot sem PII, fechar
`D7_activation.md` e parar novamente.
