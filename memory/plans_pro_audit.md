# Auditoria do Motor Plans Pro — Fase 0

**Data**: 07 Out 2026 · **Scope**: diagnóstico factual. Sem alterações de código.
**Perímetro**: `/app/backend/engines/plans_pro/` + `/app/backend/routes/plans_pro.py`.

---

## 1. Arquitectura actual

```
                    ┌───────────────────────┐
   POST /upload ───►│ routes/plans_pro.py   │
                    │ upload (func)         │
                    └──────────┬────────────┘
                               │ async upload (OSS)
                               ▼
                    ┌───────────────────────┐
                    │ autodesk_client.py    │ ← OAuth v2 token cache
                    │ upload_object(…)      │ ← S3 signeds3upload (single-part)
                    │ translate(urn, svf2)  │ ← Model Derivative Job
                    └──────────┬────────────┘
                               │ background task
                               ▼
                    _translate_and_poll(plan_id,urn)   # routes:62
                      ├─ manifest() em loop 5s × 180
                      └─ persiste translation_status

   POST /{plan_id}/analyze ──► routes:184 analyze(…)
                               ├─ autodesk_client.metadata(urn)
                               ├─ aggregate_quantities(categories_views)   ← plan_metadata.py
                               ├─ autodesk_client.thumbnail(urn)           ← 400×400 PNG
                               └─ plan_vision.full_analysis(…)             ← cascade IA
                                     1) _vision_openai(thumb) → gpt-4o json
                                     2) _synthesis_claude(meta+vision) → Opus 5.5 json
                                     3) _norms_perplexity(ouvrages) → PPLX cita

   GET /{plan_id}/export-excel  → excel_export.build_workbook(doc, iva, branding)
```

**Ficheiros envolvidos** (totais LoC):
| Ficheiro | LoC | Papel |
|----------|----:|-------|
| `routes/plans_pro.py` | 334 | 6 endpoints (`/upload`, `/{id}/status`, `/{id}/viewer-token`, `/{id}/analyze`, `/{id}/analysis`, `/{id}/export-excel`) + background poll |
| `engines/plans_pro/autodesk_client.py` | 279 | OAuth v2 · OSS buckets · signed S3 · Model Derivative (translate/manifest/thumbnail/metadata/properties) |
| `engines/plans_pro/plan_metadata.py` | 105 | `aggregate_quantities(views)` + `_LAYER_RULES` (16 buckets PT/FR/EN) |
| `engines/plans_pro/plan_vision.py` | 225 | Cascade IA: `_vision_openai`, `_synthesis_claude`, `_norms_perplexity`, `full_analysis` + `_extract_json` tolerante |
| `engines/plans_pro/excel_export.py` | 377 | Geração .xlsx (openpyxl) com IVA PT 23/22/16/6/0 e branding utilizador |

---

## 2. Pontos de falha identificados

### 2.1 LLM — formato de resposta

**Observação** (`plan_vision.py:24-56`): os `system prompts` pedem JSON estrito, mas:

- **`_vision_openai`** usa `json_mode=True` só se o provedor OpenAI o suportar (confirmado em `openai_provider.py:104` → `response_format={"type":"json_object"}`). **Boa prática aplicada.**
- **`_synthesis_claude`** (`plan_vision.py:138-142`) **NÃO** usa `json_mode` nem equivalente anthropic — Claude pode envolver em markdown ```json ```. É só mitigado pelo stripper regex em `_extract_json` (linhas 62-63).
- **`_extract_json`** (`plan_vision.py:59-91`) tenta 3 estratégias: parse directo, substring entre `{…}`, patching tolerante (fechar chaves/brackets abertos para lidar com truncagem por `max_tokens`). **O patching tolerante é um perigo**: pode devolver um dict incompleto como se fosse válido, sem sinalizar.
- Não existe validação Pydantic da resposta (nem `vision`, nem `synthesis`): o chamador acede com `.get("ouvrages", [])` e aceita qualquer coisa.

### 2.2 Tratamento de dados em falta

**Observação** (`plan_vision.py:111-146`, `routes/plans_pro.py:196-199`):

- Vision falha → `out["vision"] = None` + warning silencioso (`"Leitura visual indisponível."`). Pipeline continua sem informar o utilizador final.
- Síntese Claude falha → `out["synthesis"] = None` + warning. **O endpoint devolve `status: "failed"` mas sem causa clara ao front** (`plan_vision.py:223`).
- `metadata()` falha (`routes/plans_pro.py:196-198`) → **engolido silenciosamente** com `meta = {}` → `quantities` acaba a `{}` sem bandeira. **Grave**: utilizador não sabe que não há dados Autodesk.
- `thumbnail()` HTTP != 200 → `return None` (`autodesk_client.py:252`) sem distinguir 404 (ainda a traduzir) de erro de permissão.

### 2.3 OCR e reconhecimento de materiais

- **Não há OCR nenhum**. O prompt pede ao LLM que leia texto da thumbnail (`plan_vision.py:35` → `"text_detected": string`), mas o sistema não corre OCR dedicado (Tesseract, Textract, etc.).
- Thumbnail Autodesk é 400×400 (`autodesk_client.py:243`) — **demasiado pequeno** para OCR fiável de rótulos de cotas, legendas, mapas de material.
- Dicionário de abreviaturas PT (`A1`, `B500A`, `C25/30`, `PRÉ-E`, `BA`) → **inexistente**. O LLM pode confundir "A1" (laje) com "A1" (anotação).
- Reconhecimento por regex de dimensões (`"2,50m"`, `"H=2.80"`, `"∅12"`) → **inexistente**. Delegado totalmente ao LLM.

### 2.4 Escala e cotas

- `plan_vision.py:29` o prompt pede `"scale": string|null` ao LLM mas:
  - não há verificação cruzada com a escala real da planta (que estaria em metadata Revit/IFC: `view.getScale()`).
  - para DWG, não há leitura das variáveis `$MEASUREMENT`/`$INSUNITS` do DXF (ezdxf está nos requirements mas **não é usado** por este motor; só nos testes de outros módulos).
- `plan_vision.py:32` pede `dimensions: [{label, value_m, raw}]` mas sem conversão de unidades — se o DWG estiver em mm e o LLM devolver "2500", é logo valor errado.

### 2.5 Cross-check camadas/OCR

**Nenhum**. A pipeline funciona em dois canais isolados:
1. **Metadata APS** → `aggregate_quantities()` (regra determinística de layer → categoria).
2. **Visão LLM** → `_vision_openai()` (percepção visual).

Depois `_synthesis_claude()` recebe os dois dumps como string JSON concatenada no prompt (`plan_vision.py:131-137`). Não há código que:
- diga "o layer `MUR_INTERIOR` tem 42 ocorrências ⇔ a visão vê 42 paredes".
- detecte conflitos (ex: metadata diz 15 janelas mas vision diz 3).
- devolva confidence score.

### 2.6 Confidence scoring

**Inexistente**. Nenhum campo `confidence`, `score`, `uncertainty` na resposta:
```python
out = {
    "vision": …,            # dict ou None
    "synthesis": …,         # dict ou None
    "norms": …,
    "providers_used": […],
    "status": "done"|"failed",
    "warnings": […],        # strings livres
    "model_used": "claude-opus-5-5"
}
```
O frontend não tem como diferenciar "análise fiável" de "palpite do LLM com metadata vazia".

---

## 3. Casos problemáticos nos logs / código

### 3.1 Patching tolerante pode devolver JSON inventado
`plan_vision.py:76-91` — ao fechar brackets abertos num JSON truncado, pode criar objetos vazios ou arrays artificiais que depois são tratados como dados reais pelo chamador.

### 3.2 `int(item[1])` sem try/except
`plan_metadata.py:59, 61, 78, 80` — se Autodesk devolver `null`/`"42"`/`{}` como `item[1]`, levanta `TypeError`/`ValueError` → o `view` inteiro é ignorado silenciosamente (via `except: continue` noutro ponto, mas aqui a excepção **propaga**).

### 3.3 `except Exception` com `logger.warning` em 11 pontos
- `plan_vision.py:111, 144, 167`
- `autodesk_client.py:97` (ocult o erro de parse de token)
- `routes/plans_pro.py:77, 88, 114, 166, 196, 216, 304`

Todos engolem erros com `type(e).__name__` no log, perdendo a mensagem original (`str(e)`) → debugging em produção é opaco.

### 3.4 Thumbnail opcional sem retry
`routes/plans_pro.py:214-217` — thumbnail falha → `thumb = None` → vision não corre → síntese fica cega. Sem retry, sem `retry_after`.

### 3.5 Polling de 15 min bloqueia background workers
`routes/plans_pro.py:72-84` — 180 iterações × 5s = 15 min por plano. Com N uploads concorrentes, satura o pool asyncio sem backpressure.

### 3.6 Falta de validação do schema SVF2/manifest
`plan_metadata.py:46-98` — aceita qualquer dict `view` sem verificar se é Revit (tem `categories`) ou DWG (tem `layers`). Mistura cross-formato está hard-coded com `if not any(v["count"] for v in result.values())`.

### 3.7 Zero TODOs/FIXMEs no código
Grep retornou **0 ocorrências** de `TODO`, `FIXME`, `XXX`, `HACK`, `BUG` nos ficheiros do motor. **Isso não é um elogio** — significa que as fragilidades acima nunca foram oficialmente reconhecidas como dívida.

---

## 4. Testes actuais

Executados agora (`pytest tests/test_plans_pro* -q`): **19 passed · 0 skip · 0 fail · 0.5 s**.

| Ficheiro | Classes / casos | O que testa | Lacunas evidentes |
|----------|-----------------|-------------|-------------------|
| `test_plans_pro.py` | `TestAggregateQuantities` | Agregação de categorias Revit + agregação de layers DWG. | Não testa conflito entre `categories` e `layers` numa mesma view. Não testa `int()` com `null`. |
|  | `TestAutodeskClient` | Cache do token, geração de bucket name, config check. | Não mocka chamadas reais a OSS/MD. Sem test de retry. |
|  | `TestLayerCategory` | `_layer_category("MUR_INT_001")` → `"Paredes"`, etc. | Não testa layers ambíguas (ex: `A1_WALL` que casa com dois buckets). |
| `test_plans_pro_excel.py` | `TestExcelExport` | Workbook correto com branding + IVA PT; cabeçalhos; totais. | Não valida merge com `ai_analysis.synthesis`; não testa `ouvrages=[]`. |

**Lacunas no suite** (não cobertas por **nenhum** teste):
- `_extract_json` tolerante (3 ramos de recuperação)
- `full_analysis` com vision/synthesis a `None`
- `_norms_perplexity` sem Perplexity configurado
- Pipeline end-to-end mockando Autodesk + OpenAI + Claude
- Validação Pydantic da resposta IA (não existe de todo)
- Confidence scoring (campo não existe)

---

## 5. Top 10 falhas prioritárias a corrigir na Fase 1

| # | Fragilidade | Ficheiro / Linha | Impacto |
|--:|-------------|------------------|---------|
| 1 | **Sem validação Pydantic da resposta LLM** — qualquer forma inválida passa | `plan_vision.py:143,210` | Devolve dados fantoche ao Excel export |
| 2 | **Patching tolerante do JSON** pode inventar estrutura vazia | `plan_vision.py:76-91` | Alucinação silenciosa |
| 3 | **`metadata()` falha engolida** com `meta = {}` sem bandeira | `routes/plans_pro.py:196-199` | Utilizador não sabe que não há dados APS |
| 4 | **Sem OCR nem regex de dimensões/materiais PT** (A1, C25/30, BA, ∅12) | `plan_vision.py` (ausente) | Reconhecimento depende 100 % do LLM |
| 5 | **Sem cross-check metadata ↔ vision** (ex: 15 janelas APS vs 3 LLM) | `full_analysis` (ausente) | Zero detecção de contradição |
| 6 | **Sem confidence score** na resposta | `full_analysis:182-225` | Frontend trata palpite = facto |
| 7 | **Thumbnail 400×400** — demasiado pequeno para legendas | `autodesk_client.py:243` | OCR impossível, LLM "adivinha" |
| 8 | **Escala não extraída** do DXF (`$INSUNITS`) nem da view Revit | `plan_metadata.py` (ausente) | Dimensões em mm vs m confundidas |
| 9 | **Polling 15 min dentro do asyncio** sem backpressure | `routes/plans_pro.py:72-84` | Satura workers com N uploads concorrentes |
| 10 | **`except Exception` nus** com `type(e).__name__` perdem stacktrace | 11 pontos (ver 3.3) | Debugging opaco em produção |

---

## 6. Recomendações para Fases 1-4 (não implementar nesta fase)

### Fase 1 — Robustez semântica (bloco crítico)
- Definir `ouvrage_schema.py` com Pydantic (`VisionResult`, `SynthesisResult`, `AnalysisEnvelope`).
- Rejeitar respostas LLM que não validem o schema (sem patching tolerante). Retentar 1× com prompt mais estrito.
- Adicionar `confidence: 0..1` por campo (`ouvrages[].confidence`, `vision.confidence`).
- Converter todos os `except Exception` em `except (httpx.HTTPError, AutodeskError, …)` explícitos.
- Grid de testes de regressão com fixtures de resposta Autodesk real (sanitizada).

### Fase 2 — OCR + léxico PT
- Pipeline OCR dedicado (Tesseract PT + preprocessing) na thumbnail (**pedir thumb 1600×1600** à API Autodesk).
- Dicionário `lexico_pt_btp.py` com abreviaturas, classes de betão, aço, materiais isolantes, famílias Eurocódigo.
- Regex de dimensões PT (`\d+[,.]?\d*\s*(m|cm|mm)`), áreas (`m²`, `m2`), diâmetros (`∅|Ø\s*\d+`).
- Alimentar o `synthesis` com `ocr_text` separado da `vision`.

### Fase 3 — Cross-check e scoring
- `cross_check(metadata_counts, vision_counts) → list[Conflict]` com severidade.
- Confidence scoring por fonte: `metadata_confidence`, `vision_confidence`, `ocr_confidence`.
- Agregador que escolhe fonte dominante por tipo de ouvrage.
- Flagging `requires_human_review: bool` quando divergência > N %.

### Fase 4 — UX + observabilidade
- Endpoint `/plans-pro/{id}/trace` com breakdown por provedor + tempos.
- Frontend: mostrar bandeiras ao utilizador (`"Autodesk metadata vazia"`, `"OCR falhou"`, `"3 conflitos"`).
- Métricas (Prometheus-style) por etapa: duração, tokens, taxa de retry.

---

## Resumo em 3 frases

1. O motor **funciona em dois canais paralelos** (metadata APS + vision LLM) **sem cross-check nem confidence**, e o merge final depende de um único prompt Claude Opus 5.5 cuja resposta JSON é parseada com um **recuperador tolerante que pode inventar estruturas**.
2. O **OCR dedicado é inexistente** apesar de a thumbnail Autodesk ter 400×400 (não é suficiente) e **nenhum léxico PT-BTP** (classes de betão, aço, Eurocódigo, famílias de materiais) está codificado.
3. **Testes passam (19/19) mas cobrem só a agregação de layers e o Excel** — nenhum testa a cascade IA, nem o `_extract_json` tolerante, nem o caminho feliz end-to-end com Autodesk+OpenAI+Claude.
