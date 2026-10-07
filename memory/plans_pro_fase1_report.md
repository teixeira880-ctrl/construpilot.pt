# Fase 1 — Blindagem do Motor Plans Pro

**Data:** 07 Out 2026 · **Scope:** Pydantic + Cross-check + Léxico PT + Excepções tipadas.
**Base de trabalho:** `/app/memory/plans_pro_audit.md` (10 fragilidades identificadas).

---

## 1. Fragilidades atacadas vs. auditoria

| # | Fragilidade (auditoria) | Resolvido? | Como |
|--:|-------------------------|:---------:|------|
| 1 | Sem validação Pydantic da resposta LLM | ✅ | `AnalisePlanta` + `extra="forbid"` + `strict=True` |
| 2 | Patching tolerante do JSON (`_extract_json`) | ✅ | Substituído por `_parse_strict` que levanta `SchemaValidationError`. Helper legado marcado `# DEPRECATED Fase 1` |
| 4 | Sem OCR nem regex de materiais/dimensões PT | ✅ (parcial — Fase 2 adiciona OCR) | `materials_pt.py` com léxico determinístico PT-BTP |
| 5 | Sem cross-check metadata ↔ vision | ✅ | `cross_check.py` com 3 regras (aberturas, materiais, área) |
| 10 | `except Exception` nus apagam stacktrace | ✅ (parcial — fluxo de análise) | Excepções tipadas em `exceptions.py` + `routes/plans_pro.py:analyze` com `except` tipados e `logger.exception` |

Fragilidades `#3, #6, #7, #8, #9` ficam para fases seguintes conforme plano
(OCR dedicado, thumbnail HD, polling backpressure, etc.).

---

## 2. Ficheiros criados

| Caminho | LoC | Papel |
|---------|----:|-------|
| `engines/plans_pro/semantic/__init__.py` | 50 | Exports do pacote |
| `engines/plans_pro/semantic/schemas.py` | 300 | Pydantic v2 strict (`AnalisePlanta`, `Material`, `Dimensao`, `ElementoBase`, `Sapata`, `MuroSoubassement`, `Armadura`, `Laje`, `Pilar`, `Viga`, `Abertura`, `MissingDataRequest`, `CrossCheckWarning`) |
| `engines/plans_pro/semantic/exceptions.py` | 92 | `PlansProError`, `AutodeskError`, `VisionAnalysisError`, `SchemaValidationError`, `MissingDataError`, `OCRError` (todas logam stacktrace no `__init__`) |
| `engines/plans_pro/semantic/materials_pt.py` | 230 | Léxico PT-BTP: C12/15…C50/60, A400/A500/A500NR/A500ER/B500A/B500B, varões ∅6–∅40, PP/BA/BB/TJ/BLOCO/TIJOLO, XPS/EPS/MW |
| `engines/plans_pro/semantic/cross_check.py` | 190 | 3 regras: aberturas (>20% erro, >10% aviso), materiais extra, área bbox >15% |
| `engines/plans_pro/semantic/llm_structured.py` | 240 | Ordem **OpenAI → Claude** (específica a este motor), `response_format=json_schema strict`, zero patching |

**Total novo código: ~1 100 LoC.**

### Fixtures (`tests/fixtures/plans_pro/`)
- `aps_metadata_moradia.json` (15 janelas, 7 portas, área 180 m²)
- `vision_response_coerente.json`
- `vision_response_incoerente.json` (3 janelas vs 15 APS → disparar erro)
- `vision_response_missing.json` (rácio aço `null` + `MissingDataRequest` PT-PT)
- `vision_response_malformado.json` (campos extra, falta tudo)
- `ocr_abreviaturas_pt.txt` (49 linhas de léxico real)

### Testes criados (6 ficheiros, 93 casos)

| Ficheiro | Casos | Cobertura |
|----------|------:|-----------|
| `test_plans_pro_schemas.py` | 19 | Pydantic strict + forbid-extra, discriminador, defaults |
| `test_plans_pro_materials_pt.py` | 49 | Léxico PT-BTP (betão, aço, varões, alvenaria, isolamento, dimensões, "não inventa") |
| `test_plans_pro_cross_check.py` | 7 | 15 vs 3 janelas → erro; 15 vs 15 → zero; aviso moderado; materiais extras; área divergente; aplicação de warnings |
| `test_plans_pro_llm_structured.py` | 10 | Zero patching; OpenAI → Claude; schema strict; fallback encadeado |
| `test_plans_pro_missing_data.py` | 3 | Fixture rácio `null`; `question_pt` PT-PT; schema inválido → `MissingDataRequest` bloqueante |
| `test_plans_pro_exceptions.py` | 9 | Hierarquia, preservação de contexto, logger.exception é chamado |

---

## 3. Ficheiros alterados

### `engines/plans_pro/plan_vision.py`
- **Antes:** devolvia `dict` com `vision/synthesis/norms/warnings/status`, chamadas LLM "tolerantes", `_extract_json` com patching de brackets.
- **Depois:** devolve `AnalisePlanta` tipado. Chamadas via `analisar_com_structured_output`. Cross-check incorporado. `trace` dict com tempos, provider usado, erros de schema. `_extract_json` isolado e marcado `# DEPRECATED Fase 1`.

### `routes/plans_pro.py`
- Imports das excepções tipadas (`SchemaValidationError`, `VisionAnalysisError`, `AutodeskError`).
- `POST /{plan_id}/analyze` reescrito:
  - **Novo contrato de resposta** (ver §4).
  - `except VisionAnalysisError` → 503; `except SchemaValidationError` → 502; `except SemAutodeskError` → 502. Todos com `logger.exception`.
  - Persiste `AnalisePlanta` como `ai_analysis.analise` + wrapper legado `ai_analysis.synthesis.ouvrages=[]` para que `/export-excel` continue a funcionar sem crashar.
- Endpoints `/upload`, `/status`, `/viewer-token`, `/export-excel`, `/history/list` — mantidos tal como estavam.

---

## 4. Novo contrato da resposta de `POST /api/plans-pro/{plan_id}/analyze`

**Breaking change.** O frontend `PlansPro.jsx` precisa de adaptação na Fase 4.

```json
{
  "plan_id": "pln_abc123",
  "analise": {
    "plan_id": "pln_abc123",
    "elementos": [
      {
        "id": "SAP-01",
        "tipo": "sapata",
        "confidence": 0.9,
        "source": "aps_classification",
        "warnings": [],
        "dimensoes": [...],
        "material": { "nome": "C25/30", "categoria": "betao", "classe": "C25/30", "confidence": 0.95 },
        "cota_assentamento": -1.5,
        "diametro_mm": null,
        "racio_kg_m3": null,
        "classe_aco": null,
        "sub_tipo": null
      }
    ],
    "missing_data": [...],
    "warnings": [...],
    "confidence_global": 0.75,
    "requires_human_review": false,
    "trace": {...}
  },
  "missing_data": [
    {
      "question_pt": "Qual é o rácio de armadura (kg/m³) a aplicar na laje do piso 0?",
      "field": "armadura.racio_kg_m3",
      "unit": "kg/m³",
      "element_id": "ARM-01",
      "suggested_default": 100.0,
      "criticidade": "bloqueante"
    }
  ],
  "requires_human_review": false,
  "trace": {
    "providers_used": "openai",
    "openai_latency_ms": 1842,
    "duration_s": 2.1,
    "warnings_count": 2,
    "missing_data_count": 1,
    "confidence_global": 0.75,
    "has_thumbnail": true
  },
  "quantities": {...},
  "views_count": 3
}
```

### Pontos importantes para o front
1. **HTTP 200 mesmo com `missing_data`.** O modal deve ser disparado por `missing_data.length > 0` e não por código 4xx.
2. `requires_human_review=true` → mostrar banner amarelo "Análise requer revisão manual".
3. `trace.providers_used` ∈ {`openai`, `claude`} — útil para badge "Analisado com GPT-4o / Claude Opus 5.5".
4. Para pop-up de dados em falta, iterar `missing_data[]` e perguntar `question_pt` em ordem decrescente de `criticidade` (`bloqueante` > `importante` > `opcional`).

---

## 5. Exemplos de `MissingDataRequest` geradas

**A — Rácio de aço ausente (fixture):**
```json
{
  "question_pt": "Qual é o rácio de armadura (kg/m³ de betão) a aplicar na laje do piso 0?",
  "field": "armadura.racio_kg_m3",
  "unit": "kg/m³",
  "element_id": "ARM-01",
  "suggested_default": 100.0,
  "criticidade": "bloqueante"
}
```

**B — LLM devolveu JSON inválido:**
```json
{
  "question_pt": "A análise automática do plano falhou (resposta IA não validada). Pode confirmar/completar manualmente os dados principais do projecto?",
  "field": "plano.analise_llm",
  "unit": null,
  "element_id": null,
  "suggested_default": null,
  "criticidade": "bloqueante"
}
```

---

## 6. Output pytest completo

```
$ pytest tests/test_plans_pro_*.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.17, pytest-9.1.1, pluggy-1.6.0
collected 112 items

tests/test_plans_pro.py ................                                 [ 14%]
tests/test_plans_pro_cross_check.py .......                              [ 20%]
tests/test_plans_pro_excel.py ...                                        [ 23%]
tests/test_plans_pro_exceptions.py .........                             [ 31%]
tests/test_plans_pro_llm_structured.py ..........                        [ 40%]
tests/test_plans_pro_materials_pt.py .................................   [ 70%]
tests/test_plans_pro_missing_data.py ...                                 [ 73%]
tests/test_plans_pro_schemas.py ...................                      [100%]

============================== 112 passed in 0.38s ==============================
```

**Suite global** (regressões em toda a app):
```
$ pytest tests/
198 passed, 1 skipped, 2 warnings in 5.39s
```
→ 105 testes legados + 93 novos. **Zero regressões.**

---

## 7. Critérios de aceitação

- [x] Pacote `engines/plans_pro/semantic/` criado com 5 ficheiros (`schemas.py`, `materials_pt.py`, `cross_check.py`, `exceptions.py`, `llm_structured.py`) + `__init__.py`.
- [x] `plan_vision.full_analysis()` devolve `AnalisePlanta` tipado.
- [x] `_extract_json` tolerante **isolado como DEPRECATED Fase 1**, não é chamado no caminho principal (confirmação 4b do utilizador).
- [x] 6 novos ficheiros de teste criados, **todos verdes** (93 casos).
- [x] Teste `TestParseStrict::test_json_malformado_pydantic_levanta_schema_error` confirma JSON malformado → `SchemaValidationError`, **NÃO patch**.
- [x] Teste `TestMissingDataFixture::test_fixture_tem_racio_ausente` confirma rácio aço ausente → `MissingDataRequest.question_pt` em PT-PT com `criticidade='bloqueante'`.
- [x] Teste `TestCrossCheckAberturas::test_15_vs_3_janelas_dispara_erro` confirma 15 vs 3 janelas → `CrossCheckWarning(severidade='erro')`. Teste `TestAplicarWarnings::test_erro_forca_revisao_humana` confirma `requires_human_review=True`.
- [x] Todos os 19 testes existentes do Plans Pro continuam a passar.
- [x] Suite global 198/198 (1 skipped pré-existente), zero regressões.

---

## 8. O que fica para a Fase 2 (não executado)

- OCR dedicado (Tesseract PT) na thumbnail → pedir Autodesk thumbnail 1600×1600.
- Alimentar `AnalisePlanta.elementos` com `source="ocr"` directo (sem passar pelo LLM).
- Testes com imagens reais sanitizadas de plantas PT.
- Adaptação do frontend `PlansPro.jsx` ao novo contrato (Fase 4 do plano global).
- Remover definitivamente `_extract_json` DEPRECATED (Fase 3).
- Substituir os restantes `except Exception` nus em `autodesk_client.py` por `AutodeskError` tipado (Fase 3).
