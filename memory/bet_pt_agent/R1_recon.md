# R1 — Reconnaissance read-only · BET-PT agente Claude + motores determinísticos

**Data**: 2026-10-18 · **Scope**: código local apenas. Zero modificações, zero código, zero deploys. Zero toques em `.fr`.

---

## Síntese executiva

O codebase já tem **42 módulos `structuro_*`** + 5 módulos novos em `engines/bet/` dos Lotes BET.0→BET.6. A matemática determinística do EC2/EC3/EC5/EC7 **já existe** (`structuro_ec2.py`, `structuro_crack.py`, `structuro_anchorage.py`, `structuro_continuous.py`, `structuro_slab2way.py`, etc.). O que **falha** é a camada superior: a leitura é feita por **Gemini vision** (não Claude), as hipóteses do utilizador são tratadas como "faits déclarés" sem recálculo de impacto, não há verificador em contexto novo, e não há `BuildingModel` tipado com `confidence+source` por elemento.

A arquitectura proposta mantém **100% dos motores determinísticos existentes**, **substitui** o leitor Gemini por Claude vision com tool-use (via `anthropic_native` já presente), **introduz** `BuildingModel` Pydantic tipado, **adiciona** verificador Claude em sessão nova e **adiciona** `summary.py` honesto (comparar entregáveis pedidos vs produzidos). Zero rewrite do que funciona.

---

## R1.1 — Inventário BET actual

### Pasta nova `engines/bet/` (5 ficheiros, Lotes BET.0→BET.6)
| Ficheiro | Linhas | Função | Testes |
|---|---|---|---|
| `locale.py` | 49 | Detecção país/locale/normas a partir da morada | `test_bet_france_regression.py` |
| `g2_coherence.py` | 111 | Coerência morada PC ↔ relatório G2 | idem |
| `pdf_import.py` | 150 | Import resiliente de PDF do Pedido de Construção | idem |
| `regional_data.py` | 97 | Dados regionais FR (neve, sismo EC8-AN FR) | idem |
| `cave_walls.py` | 80 | Muros de cave K0 por camada + sobrecarga confinantes | idem |

> **Nota PT**: `regional_data.py` ainda é FR-only. Falta equivalente `regional_data_pt.py` com zonas sísmicas AN PT, zonas neve, zonas vento.

### Módulos estruturais `engines/structuro_*.py` (42 ficheiros)

**Motores determinísticos (reais)**:
- `structuro_calc.py` (467 L) — mecânica gravítica auditável, vigas isostáticas, descente de cargas.
- `structuro_continuous.py` (278 L) — vigas contínuas Clapeyron + alternância de cargas.
- `structuro_slab2way.py` — lajes two-way (presumo tabelas Czerny ou similares).
- `structuro_ec2.py` + `structuro_ec3.py` + `structuro_ec5.py` + `structuro_ec7.py` — motores EC betão/aço/madeira/geotécnico.
- `structuro_anchorage.py` (113 L) — EN 1992-1-1 §8.4/8.7 ancoragens e emendas.
- `structuro_crack.py` (98 L) — EN 1992-1-1 §7.3 fendilhação ELS qp.
- `structuro_sls.py` — flechas e vibrações.
- `structuro_rebar.py` + `_rebar_scheme.py` + `_linked_rebar.py` + `_rebar_exports.py` — armaduras.
- `structuro_lintel.py` + `_lintel_draw.py` + `_lintel_export.py` — padieiras.
- `structuro_coffrage.py` (856 L) — dossier execução cofragem + armaduras A3 vectorial.
- `structuro_profiles.py` — catálogo perfis aço.
- `structuro_eurocode.py` — combinações EN 1990.
- `structuro_check.py` — relatório utilização Ed/Rd indicativo.

**IA (probabilistic, actual)**:
- `structuro_ai.py` (79 L) — Claude leitura/redacção APENAS, nunca produz resistências. Model: `claude-sonnet-4-6` via `MeteredChat`.
- `structuro_bet_ai.py` (224 L) — Claude lê plantas/notas, extrai factos escritos, compara versões.
- `structuro_bet_pdf.py` (200 L) — PDF controlo BET (leitura apenas).
- `structuro_autopilot.py` (**1100 L**) — pont IA→determinístico. **Problema**: usa `Gemini vision` (não Claude) para extracção geom + solo via `_GEOM_PROMPT` + `_SOIL_PROMPT`. Esta é a parte que falhou no `.fr`.
- `structuro_recognition.py` — reconhecimento de elementos em planta.
- `structuro_architecture.py` (111 L) — constraints PC (sem reconhecimento, sem código mínimo auto).

**Modelo de dados existente**:
- `structuro_model.py` (282 L) — `SOURCES`, `VERIFICATIONS`, `VERIF_STATUS`, mas **sem** `BuildingModel`/`Floor`/`Wall`/`Opening` Pydantic. É mais um registo de verificações.
- `structuro_house_extract.py` — presumo extrai dados tipo "casa".

**Desenho/exports**:
- `structuro_drawings.py` + `_drawing_exports.py` + `_drawing_example.py` (316 L) — vectorial A3.
- `structuro_sheets.py` — folhas.
- `structuro_ec_exports.py` — PDF já com cabeçalhos **NP EN 1990/1992/1993/1995/1997** correctos (secção 2bis fendilhação, 2ter amarrações, flechas, sismos aviso).

**Rotas**:
- `routes/structuro.py` (20 KB) — CRUD estudos.
- `routes/structuro_bet.py` (20 KB) — import LECTURE BET.
- `routes/structuro_calc.py` (37 KB) — cálculos.
- `routes/structuro_plan.py` (5 KB) — leitura plantas.
- `routes/structuro_house.py` (1.5 KB) — stub.

### Testes existentes (BET)
- `test_bet_fase1_pt.py` — valida `norms_pt.py` (sobrecargas, γc=1.5, γs=1.15, αcc=0.85, ψ factores, recobrimentos, aviso sismo).
- `test_bet_france_regression.py` — regressão FR (cave_walls, g2_coherence, locale, pdf_import, regional_data).
- `test_bet_securite.py` — segurança do pipeline (sem valores inventados).
- `test_iter229_bet_offline.py` — modo offline.
- `test_iter230_gating_bet_autodesk.py` — gating Autodesk.
- `test_iter232_structuro_plan_reader.py` — plan reader.
- `test_slab2way_bet_reference.py` — slab2way EC2.
- `test_structuro.py` — baseline.
- `test_iter92_beton_refs.py` + `test_iter93_plan_beton_acier.py` — referências betão/aço.

### Confirmação dos lotes marcados DONE
- ✅ BET.0 — fixtures + regressão FR baseline (`test_bet_france_regression.py`).
- ✅ BET.1 — detecção país/locale (`engines/bet/locale.py`).
- ✅ BET.2 — leitor G2 + coerência morada (`engines/bet/g2_coherence.py`).
- ✅ BET.3b — muros de cave K0 (`engines/bet/cave_walls.py`).
- ✅ BET.4 — dados regionais FR (`engines/bet/regional_data.py`). **PT ausente.**
- ✅ BET.6 — parser PDF PC (`engines/bet/pdf_import.py`).
- ⚠️ BET.3 (geral) e BET.5 — pausados em rondas anteriores.

### Normas PT já implementadas (`engines/norms_pt.py`, 240+ L)
- NP EN 1991-1-1 sobrecargas (Quadros 6.2): habitação 2.0, bureau 3.0, comércio 4.0, parking 2.5, industrial 7.5, erp 4.0, cobertura 0.4 kN/m².
- NP EN 1990 ψ₀/ψ₁/ψ₂ por categoria A..H.
- Neve: zonas Z1/Z2/Z3 + critério altitude 200 m.
- Vento: zonas A/B + `vb,0`.
- NP EN 1992: γc=1.5, γs=1.15, αcc=0.85, betão default C25/30, aço A500 NR, recobrimentos XC1..XS3 + 50 mm fundações.
- NP EN 1998-1: **só aviso**, não calcula sismo. `SEISMIC_WARNING_TEXT` + `SEISMIC_INPUT_SCHEMA` listam campos a preencher.
- Todos marcados "AN PT — a confirmar pelo projetista".

Todos os valores assinalados "AN PT a confirmar pelo projetista" nos comments.

---

## R1.2 — Router Claude existente

### Dois caminhos LLM coexistem

**(A) Via `emergentintegrations` + `MeteredChat`** (usado maioritariamente)
- `engines/expenses/metering.py` encapsula `LlmChat` com telemetria de tokens.
- Suporta `.with_model(provider, model)` + `.with_params(max_tokens=...)`.
- Suporta `ImageContent(image_base64=...)` → **vision** OK.
- Suporta `send_message_with_tools(UserMessage(text=...))` → **tool-use** OK (exemplo em `stair_engine/assistant.py:291`).
- Modelos Claude actualmente usados: `claude-sonnet-4-5-20250929` (stair_engine), `claude-sonnet-4-6` (structuro_ai).

**(B) Via `engines/anthropic_native.py`** (Claude directo via SDK oficial)
- Model slugs via env: `ANTHROPIC_MODEL_SONNET=claude-sonnet-5-5`, `ANTHROPIC_MODEL_OPUS=claude-opus-5-5`, `ANTHROPIC_MODEL_HAIKU=claude-haiku-5-5`.
- Função `complete(system, text, images, model, max_tokens)` — vision OK (base64 PNG/JPEG).
- **Não vi** `complete_with_tools()` — tool-use via SDK oficial ainda não exposto.
- Guard: só activo se `ANTHROPIC_API_KEY` presente, senão degrada para `_chat()` emergent.
- Usado em `engines/ai.py:347,545` para fallback de qualidade superior.

### Pipeline cascade `engines/ai.py`
- `_chain(images: bool)` devolve lista `[(provider, model), ...]` por ordem.
- Vision chain começa em `VISION_PROVIDER / VISION_MODEL` + failover.
- Call point: `_call_provider(provider, model, system, text, images, feature)` → se `anthropic_native.native_available()` → caminho directo.

### Suporta tool-use + vision + contexto isolado?

| Capacidade | emergent `MeteredChat` | `anthropic_native` |
|---|---|---|
| Vision alta resolução | ✅ `ImageContent(image_base64)` | ✅ base64 PNG/JPEG |
| Tool-use (function calling) | ✅ `send_message_with_tools` | ❌ só `complete` texto |
| Contexto isolado (sem histórico) | ✅ cada `LlmChat(session_id=...)` é novo | ✅ cada chamada stateless |
| Rate-limits | não visíveis no wrapper | gerido pelo SDK anthropic |
| Streaming | ✅ `stream_message` | não visto |

**Conclusão**: para o agente novo, usar **`MeteredChat` com `.with_model("anthropic", "claude-sonnet-5-5")` + tool-use** é a via natural. Para o verificador em contexto novo, idêntico mas `session_id=f"verifier-{uuid}"`. Fallback possível para `anthropic_native` se latência / qualidade exigir, mas tool-use fica no `MeteredChat`.

### Segredos lidos
- `EMERGENT_LLM_KEY` (universal via emergentintegrations).
- `ANTHROPIC_API_KEY` (directo, opcional).
- `BET_GEMINI_MODEL` + `GEMINI_FALLBACK_MODEL` (usados em `structuro_autopilot.py` — a desactivar/substituir no novo pipeline).

---

## R1.3 — Fixtures existentes

### `/app/backend/tests/fixtures/`
```
plan_test.pdf           (2 KB — PDF minimal)
plan_test.dxf           (38 KB — DXF 2010 simples)
bet_france_coherent_g2.py        — fixture Python PC+G2 FR coerente
bet_france_mismatched_g2.py      — fixture PC+G2 com morada divergente
plans_pro/
  thumbnail_moradia_sintetica.png  (20 KB · PNG 1600×1600)
  aps_metadata_moradia.json
  ocr_abreviaturas_pt.txt
  vision_response_coerente.json
  vision_response_incoerente.json
  vision_response_malformado.json
  vision_response_missing.json
```

### Falta — a criar em L1
- **Moradia PT típica** com cave + R/C + 1.º andar + sótão habitável. Não existe nos fixtures.
- Estudo geotécnico PT (G2 equivalente) — só existe modelo FR.
- Dossier arquitectura PT realista (plantas, cortes, alçados, plantas de cobertura, redes, electricidade).

### `fixtures/bet_france_coherent_g2.py` — modelo útil
Estrutura clara: `PC_DATA` com `project_address`, `building_type` (R+2+cave), `levels`, `parking`, `neighbors`; `G2_DATA` com `soil_layers`, `water_level_m`, `foundation_level_m`, `q_ELS_MPa`, `q_ELU_MPa`, `settlement_mm`, `preferred_footing_type`, `sismicidade_zona`. **Reusar o schema** adaptado a PT (ex: `foundation_level_mNGF` → `foundation_level_m` relativa, zonas sísmicas 1.1..1.6 + 2.1..2.5).

---

## R1.4 — Normas PT já referenciadas

### Betão/aço (NP EN 1990/1992/1993/1995/1997)
- `norms_pt.py` cobre coeficientes, materiais default, recobrimentos, ψ.
- `structuro_ec_exports.py` já exporta PDF com cabeçalhos corretos NP EN 1990, 1992 (§7.3 fendilhação, §8.4/8.7 amarrações), 1993, 1995, 1997 + nota "A VERIFICAR PELO ENGENHEIRO".

### Sismo (NP EN 1998-1 + AN PT)
- `SEISMIC_WARNING_TEXT` + `SEISMIC_INPUT_SCHEMA` em `norms_pt.py` **avisam** mas **não calculam**.
- Zonas sísmicas PT (tipo 1 afastada + tipo 2 interplaca) e classes de solo A..E **não** estão tabeladas no código. **Gap para L1**.
- Dependência regional por município/freguesia **ausente**.

### RTIEBT / ITED / DR 23/95
- **Zero referências** em código activo. Único hit relevante: `stair_engine/pdf_dossier.py` menciona "RGEU — Regulamento Geral das Edificações Urbanas (escadas)" e "DL 163/2006 — Acessibilidades".
- **Gaps para L1 (redes/electricidade/águas)**: nenhum motor existente conhece RTIEBT (electricidade), ITED (telecomunicações), DR 23/95 (águas e esgotos), REH + REEH (térmico), SCIE (incêndio).

---

## R1.5 — Análise forense das falhas `.fr`

Dado o que o fundador reportou (dossier `.fr` inaceitável), eis a regra determinística que apanha cada falha + sinal do verificador Claude.

| # | Falha `.fr` | Regra determinística | Sinal Claude verificador |
|---|---|---|---|
| 1 | Utilizador pediu laje aligeirada, saiu maciça | `UserBrief.floor_type` persistido em `BuildingModel.floor_type_user_choice`; `checks/semantic.verify_user_choices()` compara com `BuildingModel.floors[*].type_as_calculated` → **FAIL** se diferente | "Hipótese do utilizador IGNORADA: pediste laje aligeirada mas o motor calculou maciça. Divergência não justificada." |
| 2 | Portão de garagem contado em duplicado | `checks/geometric.detect_duplicate_openings()` → para cada `Opening`, verifica se há outro com `|dx|<30cm ∧ |dy|<30cm ∧ same_wall_id`. Flag UNIQUE_OPENING | "Abertura detectada 2× na parede X: {opening1.id} e {opening2.id} a <30cm" |
| 3 | Nível/piso inventado | `BuildingModel.floors[i].source` deve ser `document` (lido da planta) ou `declaration` (declarado pelo utilizador). Se `source==ia_proposition` **sem** declaração explícita → FAIL | "Piso {n} marcado como existente mas sem fonte documental nem declaração do utilizador" |
| 4 | Sótão habitável tratado como não habitável | `UserBrief.attic_type` ∈ {habitable, non_habitable, technical}; se habitable → `imposed_load_kN_m2 = norms_pt.IMPOSED_LOADS["habitation"]["q"]`, carga variável 2.0 kN/m². Verifica `floor_attic.imposed_load_applied == 2.0` | "Sótão declarado habitável, mas sobrecarga aplicada = 0.4 kN/m² (cobertura não acessível). Incorreto." |
| 5 | Escada que não cabe | `checks/geometric.verify_stair_fits()` lê `Stair.length_mm × Stair.width_mm × Stair.rise_mm` + `opening_in_slab_above = {length, width}` → `assert length >= stair.length ∧ width >= stair.width` | "Escada {id} com desenvolvimento {L}mm não cabe na abertura da laje superior ({opening.L}mm). Falta {L - opening.L}mm." |
| 6 | Falta planta de cobertura | `summary.required_deliverables` lista: foundation_plan, framework_plan_rc, framework_plan_floors, roof_plan, electrical_plan, water_sewer_plan. Comparar com `summary.produced_deliverables`. Diff → **FAIL** | "Entregáveis em falta: planta de cobertura, planta de electricidade (RTIEBT), planta de águas/esgotos (DR 23/95)" |
| 7 | "OK verde" apesar de alertas | `summary.global_status = "OK"` só se `all(check.status != "FAIL" for check in all_checks)`. Qualquer FAIL → `global_status = "VERMELHO"` + lista obrigatória | "Dossier marcado OK mas 4 verificações falharam: ... Status corrigido para VERMELHO." |

Cada regra determinística corresponde a um teste pytest obrigatório em L1.

---

## R1.6 — Proposta de arquitectura

### Estrutura de módulos — `engines/bet_agent/`

```
engines/bet_agent/
├── __init__.py
├── brief.py                   # Schema UserBrief: hipóteses do utilizador (fonte de verdade)
├── reader.py                  # Orquestração Claude vision + pymupdf → BuildingModel
├── models/
│   ├── __init__.py
│   ├── building.py            # Pydantic BuildingModel + Floor + Wall + Opening + Stair + Roof + Room
│   ├── source.py              # Source(page, coordinates, confidence, raw_quote)
│   └── versioning.py          # BuildingModel schema version + migrations
├── checks/
│   ├── __init__.py
│   ├── geometric.py           # Cotas, nembos, duplicação de aberturas, escada cabe, pés-direitos, áreas
│   ├── semantic.py            # UserBrief choices foram respeitadas?
│   └── structural.py          # Coerência estrutural de alto nível (não substitui structuro_calc)
├── agent/
│   ├── __init__.py
│   ├── loop.py                # Ciclo verificação: re-leitura 3x → pergunta ao utilizador
│   ├── tools.py               # Tool-use schema: read_region, measure_dimension, ask_user, flag_anomaly
│   └── prompts.py             # System prompts para leitor e verificador (em contexto novo)
├── geotech/
│   ├── __init__.py
│   └── parser.py              # Parse G2 → tensões, cota fundação, freático, contenções, vizinhos
├── calc/
│   ├── __init__.py
│   ├── eurocode_pt/           # Wrapper para structuro_ec2/3/5/7 com normalização AN PT
│   │   ├── __init__.py
│   │   ├── loads.py           # Combinações NP EN 1990 PT
│   │   ├── concrete.py        # Wrapper structuro_ec2
│   │   ├── steel.py           # Wrapper structuro_ec3
│   │   ├── timber.py          # Wrapper structuro_ec5
│   │   ├── geotech.py         # Wrapper structuro_ec7
│   │   └── seismic.py         # NP EN 1998-1 AN PT (NOVO, L2)
│   └── regional_data_pt.py    # Zonas sísmicas PT 1.x/2.x + classes solo + vento + neve
├── drawings/
│   ├── __init__.py
│   ├── pdf.py                 # Wrapper structuro_coffrage + exports
│   ├── dxf.py                 # Export DXF via ezdxf (já instalado 1.4.4)
│   └── required_sheets.py     # Lista obrigatória: fund, estrut, cobertura, electricidade, águas
├── verifier/
│   ├── __init__.py
│   ├── review.py              # Claude em sessão nova com BuildingModel + saídas → emite diff
│   └── report.py              # Report revisor estruturado
└── summary.py                 # Resumo honesto: entregáveis pedidos vs produzidos + anomalias + status global
```

### Modelo central `BuildingModel`

```python
class Source(BaseModel):
    page: int                    # página do PDF original
    coordinates: list[float]     # bounding box [x1, y1, x2, y2] em pt do PDF
    confidence: float            # 0.0..1.0, do Claude vision
    raw_quote: str | None        # cota ou texto literal lido (ex: "+3.10")
    kind: Literal["measurement", "declaration", "inferred", "user_brief"]

class Opening(BaseModel):
    id: str
    wall_id: str
    type: Literal["door", "window", "garage_door", "passage", "service"]
    width_mm: float
    height_mm: float
    sill_mm: float
    position_in_wall_mm: float
    source: Source

class Wall(BaseModel):
    id: str
    floor_id: str
    type: Literal["load_bearing", "partition", "facade"]
    material: Literal["concrete", "masonry_block", "masonry_brick", "lsf", "wood"]
    thickness_mm: float
    length_mm: float
    height_mm: float
    polyline: list[tuple[float, float]]
    openings: list[str]           # ids
    source: Source

class Stair(BaseModel):
    id: str
    from_floor: str
    to_floor: str
    length_mm: float
    width_mm: float
    rise_mm: float
    tread_mm: float
    steps: int
    opening_above: dict | None    # abertura da laje por cima: {length_mm, width_mm}
    source: Source

class Floor(BaseModel):
    id: str
    level: int                    # -1=cave, 0=rc, 1=p1, ..., 99=cobertura
    name: str                     # "Cave", "R/C", "1.º andar", "Sótão"
    habitable: bool
    floor_z_m: float              # cota em m relativa ao ±0.00
    ceiling_height_mm: float      # pé-direito livre
    slab_type: Literal["solid", "lightweight", "ribbed", "pre_tensioned", "wood"]
    slab_thickness_mm: float
    rooms: list["Room"]
    walls: list[str]              # wall ids
    stairs_to_above: list[str]    # stair ids
    imposed_load_kN_m2: float     # calculado via norms_pt + habitable
    source: Source

class Roof(BaseModel):
    type: Literal["flat", "double_slope", "hip", "mansard"]
    pitch_deg: float | None
    covering: Literal["ceramic_tile", "fiber_cement", "metal", "membrane"]
    insulation_mm: float | None
    source: Source

class BuildingModel(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str
    address: str
    locale: Literal["pt", "fr"]
    floors: list[Floor]
    walls: list[Wall]
    openings: list[Opening]
    stairs: list[Stair]
    roof: Roof | None
    user_brief: "UserBrief"
    reader_metadata: dict         # tempo, tokens Claude, nº iterações re-leitura
```

### Interfaces entre módulos

```
┌────────────────────────────┐
│  frontend (/bet/pt/new)    │
└──────────┬─────────────────┘
           │ POST /api/bet/pt/project  { user_brief, pdf_arch, pdf_g2 }
           ▼
┌────────────────────────────┐
│  routes/bet_pt.py          │
└──────────┬─────────────────┘
           │
           ▼
┌────────────────────────────┐  tool-use: read_region, measure, ask_user
│  agent/loop.py             │◄───┐
│  (Claude Sonnet 5.5)       │    │ re-reads até 3x
└──────────┬─────────────────┘    │
           │                      │
           ▼                      │
┌────────────────────────────┐    │
│  reader.py                 │────┘
│  (Claude vision + pymupdf) │
└──────────┬─────────────────┘
           │ produz BuildingModel + G2Report
           ▼
┌────────────────────────────┐
│  checks/{geometric,        │  — determinístico
│   semantic, structural}.py │
└──────────┬─────────────────┘
           │ CheckReport
           ▼
┌────────────────────────────┐
│  calc/eurocode_pt/*        │  — determinístico, 100% motores existentes
│  (envolve structuro_*)     │
└──────────┬─────────────────┘
           │ CalcReport
           ▼
┌────────────────────────────┐
│  drawings/{pdf,dxf}        │  — determinístico (wrapper structuro_coffrage)
│  + required_sheets.py      │
└──────────┬─────────────────┘
           │ DrawingSet
           ▼
┌────────────────────────────┐
│  verifier/review.py        │  — Claude em sessão NOVA, zero histórico
│  (BuildingModel+saídas)    │
└──────────┬─────────────────┘
           │ VerifierDiff (lista de anomalias detectadas pelo revisor)
           ▼
┌────────────────────────────┐
│  summary.py                │  compara entregáveis pedidos vs produzidos
│                            │  + global_status (VERDE | AMARELO | VERMELHO)
└──────────┬─────────────────┘
           │
           ▼
     Dossier final zip (PDFs + DXF + summary.md + verifier_diff.json)
```

### Pontos de fail-stop (dossier VERMELHO)

1. **UserBrief incompleto**: campos obrigatórios ausentes → nem arranca.
2. **BuildingModel incoerente**: `checks/geometric` detecta cotas negativas, área < 0, paredes sem fecho poligonal → **STOP**.
3. **Decisão do utilizador ignorada**: `checks/semantic.verify_user_choices()` FAIL → **STOP** com UserBrief.diff.
4. **Verificador Claude** emite anomalia de categoria `blocking` → **STOP**.
5. **Entregáveis em falta** (comparando `required_deliverables` vs `produced_deliverables`) → sempre output VERMELHO.

### Pontos de interacção com o utilizador

- Após `reader.py` → se `confidence < 0.7` para algum campo crítico → `agent.loop` envia pergunta precisa ao utilizador antes de prosseguir.
- Após `verifier/review.py` → se o Claude verificador propõe correcção → apresenta ao utilizador antes de regenerar.
- Qualquer `global_status == VERMELHO` → UI mostra lista de FAILs com propostas de correcção.

### Formato `BuildingModel` JSON + versionamento

- `schema_version: "1.0"` em todo o doc. Migrations futuras em `models/versioning.py`.
- Serialização via `.model_dump_json(indent=2)`. Guardado em Mongo colecção `bet_building_models` com `project_id`, `revision`, `created_at`.
- Imutável após criação; mudanças criam nova revisão.

---

## R1.7 — Riscos, custos e perguntas abertas

### O que **não** dá para fazer determinístico (reconhecer honestamente)

| Área | Porque não | Mitigação |
|---|---|---|
| Desenho de cobertura (traçado 3D de águas, rufos, caleiras) | Não há norma única; é convenção + boa prática | Claude propõe traçado, humano valida; motor valida só pendentes, caimentos e sobreposição |
| Classificação sótão habitável vs técnico | Depende de pé-direito legal (RGEU 2.40m) + uso declarado | Determinístico: `habitable = ceiling_height_mm >= 2400 AND user_brief.attic_use == habitable` |
| Reconhecimento de materiais de alvenaria | Vision tem incerteza (bloco térmico vs tijolo furado) | Pedir sempre no UserBrief; vision apenas sugere com `confidence` |
| Zona sísmica exacta por morada | Depende de freguesia (zonação AN PT) | Tabela estática `regional_data_pt.py` por município, com fallback "verificar com projetista" |

### Custos estimados Claude vision por projecto (moradia R+2+cave+sótão)

- PDF arquitectura típico: 8-15 páginas A3 (plantas, cortes, alçados, cobertura, redes).
- PDF G2 típico: 20-40 páginas.
- Imagens @150 DPI PNG: ≈ 1-3 MB cada após compressão base64.
- Chamadas estimadas:
  - 1 chamada de leitura geral (vision + text) ≈ 15 imagens × 1500 tokens output ≈ **~40k input tokens + 20k output**.
  - 2-3 re-leituras de regiões específicas ≈ **~10k input + 5k output cada**.
  - 1 chamada verificador (texto + 3 imagens contexto) ≈ **~15k input + 10k output**.
- Total aproximado: **~85k input + ~50k output** = **~€0.85 input + €1.00 output = ~€1.85 por projecto** (claude-sonnet-5-5 @ $3/$15 per 1M).
- **Nota**: valor estimado — a validar com instrumentação real em L1.

### Limites de confiança

- `confidence >= 0.9` → aceita silenciosamente.
- `0.7 <= confidence < 0.9` → regista no `BuildingModel` mas sinaliza em `summary.anomalies`.
- `confidence < 0.7` → **re-leitura dirigida** (até 3 tentativas) + se continuar baixo, **pergunta ao utilizador**.

### Dependências

**Já instaladas** (verificado em `requirements.txt`):
- `anthropic==1.12.1` · `ezdxf==1.4.4` · `opencv-python-headless==5.0.0.93` · `pillow==12.3.0` · `pymupdf==1.28.2` · `reportlab==5.0.0` · `shapely==2.1.2`.

**A instalar (L1)**: nenhuma. O stack já cobre tudo.

### Perguntas abertas ao fundador antes de L1

1. **Model Claude**: usar `claude-sonnet-5-5` (default do pod) ou `claude-opus-5-5` para o verificador em contexto novo? Opus custa 5× mais mas tem melhor raciocínio em revisões densas. Recomendação: Sonnet 5.5 para leitura + Opus 5.5 só para verificador final.
2. **Fluxo de aprovação do utilizador**: queres interactividade em cada confidence baixa (muitas perguntas) ou agregada no fim (uma lista única "preciso de clarificação em X pontos")? Recomendação: agregada, menos fricção.
3. **Reset de projecto**: se o utilizador rectifica uma declaração a meio, recalculamos tudo ou só o que depende dessa declaração? Recomendação: recalcular tudo (deterministic, custa pouco).
4. **Entregáveis obrigatórios para L1**: foundation_plan + framework_plans (por piso) + roof_plan + electrical_plan + water_sewer_plan + seismic_summary + full_calc_pdf + dxf_bundle. Confirma a lista ou acrescenta?
5. **DR 23/95 (águas/esgotos)** e **RTIEBT (electricidade)**: queres entregáveis conformes às tabelas mínimas (traçados simplificados com dimensionamento básico) ou só folhas vazias com "a ser preenchido por projetista especializado"? Recomendação para L1: traçados simplificados com dimensionamento tabelado + nota "assinatura do projetista especializado obrigatória".
6. **Fixtures PT**: queres que eu crie um dossier sintético de moradia R+2+cave+sótão para testes de L1 (desenho via DXF→PDF), ou tens um dossier real anónimo que posso usar?
7. **Modelo "contexto novo"**: para o verificador Claude, criamos nova `session_id` (sem histórico) ou nova `LlmChat` instance (presumo o mesmo efeito mas confirma)? Recomendação: nova instance + session_id novo + system prompt completamente diferente (perspectiva de revisor crítico, não de leitor).

---

## Estado final

- ✅ Codebase explorado: 42 módulos `structuro_*` + 5 em `engines/bet/` + 10 testes BET.
- ✅ Motores determinísticos EC existentes identificados — reutilizáveis sem reescrever.
- ✅ `norms_pt.py` tem AN PT para EC1-1-1, EC1-1-3, EC1-1-4, EC2 (parcial), EC1990. Sismo EC8 apenas aviso. Gap: zonas sísmicas PT, redes PT.
- ✅ Router Claude disponível: `MeteredChat` com tool-use + vision + sessions isoladas. Fallback `anthropic_native` para completações directas.
- ✅ Fixtures FR OK; **fixtures PT a criar em L1**.
- ✅ 7 falhas `.fr` com regra determinística + sinal Claude mapeados.
- ✅ Arquitectura modular proposta em `engines/bet_agent/` com `BuildingModel` tipado.
- ✅ 7 perguntas abertas ao fundador listadas.

**Zero código escrito. Zero modificações. Zero deploys. Zero toques em `.fr`.**

Pronto para apresentação ao fundador e aprovação para arranque de L1.
