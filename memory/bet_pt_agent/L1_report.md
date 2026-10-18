# L1 — BET-PT Agent (relatório parcial sub-passos L1.0 → L1.5 + L1.7 cost)

**Data abertura**: 2026-02-16 · **Estado**: ⏳ **L1.0 – L1.2 – L1.4 – L1.5 – L1.7 (cost) ENTREGUES.** L1.3 (Reader LLM) + L1.6 (Fixture PDF sintética) + L1.8 (UI admin) + L1.9 (Playwright) + L1.10 (deploy preview) por fazer.

Nenhum deploy. Nenhum toque em `.fr` nem nos lotes BET anteriores.
Feature flag `BET_AGENT_ENABLED=false` por omissão — pipeline inactivo até L1 estar completo.

---

## 1. Entregas desta ronda

### L1.0 — Setup do módulo
- Pacote criado em `/app/backend/engines/bet_agent/`:
  ```
  bet_agent/
  ├── __init__.py              (feature flag is_enabled())
  ├── brief.py                 (parse + hypotheses_used)
  ├── reader.py                (stub L1.3)
  ├── summary.py               (build_summary + global_status)
  ├── cost.py                  (DossierMeter + preços PT)
  ├── testing.py               (helpers mk_* para testes — fora de tests/)
  ├── models/
  │   ├── __init__.py          (re-exports)
  │   ├── building.py          (BuildingModel + Floor/Wall/Opening/Stair/...)
  │   ├── brief.py             (UserBrief + enums materiais)
  │   └── summary.py           (Summary + Anomaly + GlobalStatus)
  ├── checks/
  │   ├── __init__.py
  │   ├── geometric.py         (GEO-001..GEO-006)
  │   └── semantic.py          (SEM-001..SEM-005)
  ├── agent/
  │   ├── __init__.py
  │   ├── loop.py              (stub L1.3)
  │   ├── tools.py             (stub L1.3)
  │   └── prompts.py           (READER_SYSTEM_PT + VERIFIER_SYSTEM_PT)
  └── registry/
      ├── __init__.py
      └── deliverables_pt.py   (DeliverableKind + CRITICAL + OUT_OF_SCOPE)
  ```
- Feature flag `BET_AGENT_ENABLED` lida via `os.environ`. Default `false`.
- Zero modificação em lotes BET existentes.

### L1.1 — Modelos Pydantic
- `BuildingModel` com secções: floors / walls / structural_elements / openings
  / stairs / slab_openings / roof / rooms / networks / site / electrical.
- Cada elemento tem `source: {page, bbox, extraction_method}` + `confidence ∈ [0,1]` + `user_imposed: bool`.
- `UserBrief` com materiais (slab_type, masonry, concrete, steel, roof),
  nível freático, sísmicas (zona + solo + município/CP), room_uses,
  `requested_deliverables`.
- `Summary` com `requested_deliverables` vs `produced_deliverables`,
  `hypotheses_used`, `anomalies`, `global_status`, `cost`, `footer` imposto.
- `Anomaly` com `severity ∈ {bloqueante, grave, aviso}`, `code`, `message_pt`,
  `source: {page, bbox}`, `remediation`.
- `ElectricalBrief` com flags RTIEBT / DR 23/95 presentes mas vazios
  (decisão 5 do fundador — cálculo real em L2/L3).

### L1.2 — Brief
- `parse_user_brief()` valida JSON, levanta `BriefError` em caso de erro.
- `hypotheses_used()` devolve lista de `HypothesisUsed` com flag
  `user_imposed`/`default_used` para transparência total.
- Defaults documentados em `DEFAULT_HYPOTHESES` (betão C25/30, aço A500 NR,
  tijolo cerâmico furado 15, laje aligeirada vigotas+abobadilhas, cobertura
  inclinada telha cerâmica).
- **Resolução de zona sísmica** a partir de município/CP ainda não implementada
  (sub-passo L1.2b pendente — exige dados DGT NP EN 1998-1 NA PT).

### L1.4 — Checks determinísticos
#### `checks/geometric.py`
- **GEO-001** — Nenhum elemento com largura ≤ 0. ✅
- **GEO-002** — Vãos duplicados (mesmo kind, bbox sobreposta, centros próximos). ✅
- **GEO-003** — Pé-direito plausível (CAVE 2.20–3.00 / RC 2.40–3.20 / SOTAO 1.80–3.20). ✅
- **GEO-004** — Escada cabe na abertura: Lei da escada 2a+b ≈ 58–68 cm +
  comprimento necessário ≤ opening_length. ✅
- **GEO-006** — Parede inteiramente dentro de abertura de laje. ✅
- **GEO-005** (áreas por compartimento ±5 %) e **GEO-007** (cotas parciais
  somam totais ±2 cm) — placeholders pendentes para L1.4b (precisam do reader
  para extrair texto vectorial).

#### `checks/semantic.py`
- **SEM-001** — Hipótese `slab_type` do utilizador vs leitura real. ✅
- **SEM-002** — Classificação de sótão habitável coerente (altura + janelas + escada). ✅
- **SEM-003** — Nenhum piso lido só por vision com confidence < 0.70. ✅
- **SEM-004** — SEM "verde" se existir bloqueante/grave (lógica em `summary.py`). ✅
- **SEM-005** — Nota do utilizador referencia item fora de âmbito (termica_reh,
  acustica, gas, scie) → anomalia AVISO. ✅

### L1.5 — Resumo honesto
- `build_summary(building, brief, anomalies, cost, produced_deliverables) → Summary`.
- Regra `global_status`:
  - **vermelho** se ≥1 bloqueante OU ≥4 graves OU entregável crítico em falta.
  - **verde** se 0 anomalias bloqueantes/graves + todos pedidos produzidos + custo dentro do limite.
  - **amarelo** restantes casos com produced_ratio ≥ 50 %.
- `missing_deliverables()` e `missing_critical()` métodos auxiliares para UI.
- Rodapé imposto: *"pré-dimensionamento, a verificar e assinar pelo técnico responsável"*.

### L1.7 (parcial) — Cost metering
- `DossierMeter(project_id)` acumula input/output/cache_read tokens por chamada.
- Preços PT em `_PRICING_EUR_PER_M` (opus-5-5, sonnet-5-5, haiku-5-5),
  conservador se modelo desconhecido.
- Limite €10/dossier (override via `BET_AGENT_COST_LIMIT_EUR`).
- `CostBreakdown.exceeded_limit` degrada o `global_status` para não-verde.

### L1.7 — Testes
Ficheiros em `/app/backend/tests/engines/bet_agent/`:
- `test_brief.py` — 7 testes · hipóteses user vs default.
- `test_building_model.py` — 6 testes · validações Pydantic.
- `test_checks_geometric.py` — 8 testes · cada regra apanha o seu defeito.
- `test_checks_semantic.py` — 7 testes · SEM-001..005.
- `test_summary.py` — 9 testes · global_status + delta.
- `test_cost.py` — 6 testes · metering + exceeded_limit.

**Resultado**: `43 passed in 0.42s` (com config `-n 2 --dist loadscope` do
`pytest.ini`, zero chamadas LLM, zero rede).

---

## 2. Decisões de implementação (notas para L1.3 em diante)

- **Colisão de namespace pytest** — `tests/engines/__init__.py` sobrepunha-se
  ao pacote `engines/`. Resolvi movendo os helpers `mk_*` para
  `engines/bet_agent/testing.py` (padrão Django) e removendo os `__init__.py`
  de `tests/engines/*`. Esta decisão fica documentada aqui para evitar
  regressão.
- **Pricing table EUR/1M tokens** — valores indicativos convertidos USD→EUR
  (0.92 factor Jan 2026). Serve apenas para o alerta >€10, não para
  facturação. Preços oficiais vêm da conta Anthropic.
- **Hipóteses do utilizador** — nunca sobrescrevem `UserBrief` com defaults.
  Os defaults só aparecem em `hypotheses_used()` com flag `default_used=True`
  para transparência.
- **BuildingModel aceita `extra="forbid"`** em todos os sub-modelos — rejeita
  campos inesperados vindos do reader LLM.
- **Flags RTIEBT / DR 23/95** presentes no `BuildingModel.electrical` mas
  marcadas `needs_future_computation=True`. L1 só reserva o espaço, L2/L3
  implementam o cálculo.

---

## 3. O que falta em L1 (próximos sub-passos)

| Sub-passo | Descrição | Dependências |
|-----------|-----------|--------------|
| **L1.2b** | `registry/zonas_sismicas_pt.py` com tabela DGT NP EN 1998-1 NA PT | dados oficiais DGT — pode exigir web_search |
| **L1.3** | Reader Claude Opus 5.5 + tool-use + loop ReAct | **chama `integration_playbook_expert_v2`** antes de escrever código (tool-use + metering tokens Opus) |
| **L1.4b** | GEO-005 (áreas) + GEO-007 (cotas parciais) | depende do L1.3 ter texto vectorial |
| **L1.6** | Fixture PDF sintética `moradia_pt_reticular_r2_cave_sotao/` com 5 defeitos intencionais | reportlab + ezdxf |
| **L1.7b** | Teste de não-regressão end-to-end sobre fixture (mock Claude) | L1.3 + L1.6 |
| **L1.8** | UI admin `/admin/bet-agent` + rotas `POST /api/admin/bet-agent/run` e `GET /api/admin/bet-agent/costs` | admin role já existe |
| **L1.9** | Playwright E2E: admin corre pipeline, demo não vê rota, custo real visível | L1.8 |
| **L1.10** | Smoke local verde → deploy preview Emergent + screenshots → `L1_report.md` | tudo acima |

---

## 4. Checkpoint para o fundador

- **Nada ainda em produção.** Nem o preview foi tocado além do pod corrente.
- **Playbook Claude** necessário antes de L1.3 — vou chamar
  `integration_playbook_expert_v2` para confirmar o padrão de tool-use com
  Opus 5.5 e metering de tokens (nunca chamei este modelo com tool-use neste
  codebase; o `anthropic_native` existente só expõe `complete()` sem tool-use
  e sem captura de usage).
- **Dados DGT NP EN 1998-1** — qualquer tabela que use terá fonte citada no
  próprio ficheiro `zonas_sismicas_pt.py`. Posso usar web_search para
  confirmar oficial. Confirma se queres que o faça ou se tens uma fonte
  preferida (ex: DGT PDF)?
- Nenhum teste live chamando Claude vai correr sem aprovação explícita (regra
  dura do briefing).

Qualquer luz vermelha, pára-se.

---

## 5. Estado deste documento

**Estado**: ⏳ L1.0 → L1.5 + cost(L1.7) **verdes**. Próxima acção: arrancar
L1.6 (fixture sintética) em paralelo com chamada ao
`integration_playbook_expert_v2` para L1.3 (Reader).
