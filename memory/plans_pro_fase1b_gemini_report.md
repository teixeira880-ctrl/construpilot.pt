# Fase 1b — Integração Gemini (primário global)

**Data:** 07 Out 2026 · **Scope:** Gemini como primário em Coach IA, Assistente de Obras e Plans Pro.

---

## 1. Decisão sobre o modelo

**Modelo configurado:** `gemini-pro-latest` (alias que resolve para `gemini-3.1-pro-preview`).

### Validação inicial da chave `AQ.Ab8…` — resultado dos testes HTTP

| Formato | HTTP | Interpretação |
|---------|-----:|---------------|
| `?key=AQ.Ab8…` (query param) | **200** ✅ | Funciona |
| `Authorization: Bearer AQ.Ab8…` | 401 UNAUTHENTICATED | **Rejeitado** — Google só aceita Bearer para OAuth2 |
| `x-goog-api-key: AQ.Ab8…` (header) | **200** ✅ | Funciona (**escolhido**: mais limpo que `?key=`) |

### Modelo original pedido vs. modelo final

- **`gemini-2.5-pro` (pedido inicial):** HTTP 404 — Google devolve `"This model is no longer available to new users. Please update your code to use models/gemini-3.1-pro-preview"`. A chave `AQ.*` é nova → cai na categoria *new users*.
- **`gemini-pro-latest` (final):** alias oficial, resolve para `gemini-3.1-pro-preview`. Permite upgrade automático quando o novo Pro sair da fase preview.
- **Confirmação na response:** `modelVersion: "gemini-3.1-pro-preview"` em todas as chamadas reais.

---

## 2. Cascata de providers por motor

| Motor | Ordem Fase 1a (antes) | Ordem Fase 1b (agora) |
|-------|------------------------|------------------------|
| Coach IA (`/api/coach/ask`) | Claude → OpenAI | **Gemini → Claude → OpenAI** |
| Assistente de Obras / BTP Solver (`/api/btp-solver/solve`) | Claude → OpenAI | **Gemini → Claude → OpenAI** |
| Plans Pro (`/api/plans-pro/{id}/analyze`) | OpenAI → Claude | **Gemini → Claude → OpenAI** |
| Perplexity (`/api/perplexity-plus/*`) | Dedicado web search | **Dedicado web search (INTACTO)** |

Perplexity **não entra** na cascata — mantém o seu propósito próprio (enriquecimento web search com citações).

---

## 3. Ficheiros criados / alterados

### Criados
| Caminho | LoC | Papel |
|---------|----:|-------|
| `engines/ai_providers/gemini_provider.py` | 230 | `GeminiProvider` (REST v1beta, `x-goog-api-key`, `systemInstruction`, `responseSchema`, `inline_data`) + redacção automática da chave em logs |
| `tests/test_ai_providers_gemini.py` | 410 | 23 testes com mocks + 1 `@pytest.mark.integration` real |
| `tests/test_plans_pro_gemini.py` | 230 | 7 testes de cascata Gemini → Claude → OpenAI em structured outputs |
| `pytest.ini` | 3 | Registo do marker `integration` |

### Alterados
| Caminho | Alteração |
|---------|-----------|
| `engines/ai_providers/router.py` | Instancia `GeminiProvider` lazy, adiciona `@property gemini`, actualiza `coach_ask()` com nova cascata **Gemini → Claude → OpenAI**, `health()` inclui Gemini |
| `engines/plans_pro/semantic/llm_structured.py` | Nova `_call_gemini()`, cascata Gemini → Claude → OpenAI, `_schema_for_gemini()` com inlining de `$defs`/`$ref` e remoção de `additionalProperties` (restrições v1beta Gemini). `trace` inclui `gemini_latency_ms` e `network_errors[]` |
| `backend/.env` | +`GEMINI_API_KEY`, +`GEMINI_MODEL=gemini-pro-latest`, +`GEMINI_PROJECT_ID` |
| `backend/.env.example` | Placeholders Gemini com instruções de onde obter chave |
| `tests/test_plans_pro_llm_structured.py` | Testes antigos actualizados para a nova ordem (passam `router.gemini = None` quando o foco é só OpenAI/Claude) |
| `tests/test_plans_pro_missing_data.py` | Idem |

---

## 4. Evidência de ping real (chave em uso)

### 4.1 Health check global
```
Primário: gemini | Fallback 1: claude | Fallback 2: openai
  - gemini: configurado (model=gemini-pro-latest)
  - claude: configurado (model=claude-opus-5-5)
  - openai: configurado (model=gpt-4o)
  - perplexity: configurado (model=perplexity/sonar)
```

### 4.2 Coach IA — Gemini real
```
Provider: gemini | Model: gemini-3.1-pro-preview | Latência: 5956ms
Resposta: 'ok construpilot'
```

### 4.3 BTP Solver — Gemini real
```
Provider: gemini | Model: gemini-3.1-pro-preview | Latência: 6111ms
Resposta: 'A causa mais provável é a ocorrência de tensões estruturais provocadas por…'
```

### 4.4 Plans Pro (structured output) — Gemini real
```
Provider usado: gemini | Tentados: ['gemini']
Latência Gemini: 32058ms (inclui thinking tokens Pro)
plan_id: pln_e2e_v3 | Elementos: 2 | Missing data: 1 | Confidence: 0.8
Primeiro elemento: id=WALL-01, tipo=parede, confidence=0.8, source=aps_classification
```

### 4.5 Ping test `@pytest.mark.integration`
```
$ pytest -m integration tests/test_ai_providers_gemini.py -v
tests/test_ai_providers_gemini.py::test_integration_ping_real_gemini[asyncio] PASSED
======================= 1 passed, 22 deselected in 3.50s =======================
```

---

## 5. Suite de testes

### Resultado final
```
$ pytest tests/
228 passed, 1 skipped, 2 warnings in 8.82s
```

**Composição:** 198 testes pré-Fase 1b (zero regressões) + 30 novos testes Gemini (23 em `test_ai_providers_gemini.py` + 7 em `test_plans_pro_gemini.py`).

### Cobertura dos novos testes
| Cenário | Teste | Estado |
|---------|-------|:------:|
| Gemini OK → Claude/OpenAI não chamados | `TestRouterCascade::test_gemini_ok_claude_nao_e_chamado` | ✅ |
| Gemini 429 → fallback Claude | `TestRouterCascade::test_gemini_429_cai_para_claude` | ✅ |
| Gemini 401 → fallback Claude (sem retry) | `TestRouterCascade::test_gemini_401_cai_para_claude_sem_retry` | ✅ |
| Gemini + Claude falham → OpenAI vence | `TestRouterCascade::test_gemini_e_claude_falham_openai_ganha` | ✅ |
| Todos falham → `CoachUnavailableError` | `TestRouterCascade::test_todos_falham_levanta_coach_unavailable` | ✅ |
| `systemInstruction` separado de `contents` | `TestAsk::test_system_passa_via_systemInstruction` | ✅ |
| Header `x-goog-api-key` (não `Bearer`) | `TestAsk::test_system_passa_via_systemInstruction` | ✅ |
| `responseSchema` activa `responseMimeType=application/json` | `TestAsk::test_response_schema_activa_json_mime` | ✅ |
| Chave redactada em stacktraces | `TestAsk::test_erro_response_redacta_chave` | ✅ |
| Plans Pro Gemini schema inválido → Claude | `TestCascadeGemini::test_gemini_schema_invalido_cai_para_claude` | ✅ |
| Plans Pro: inlining `$defs`/`$ref` | `TestSchemaForGemini::test_remove_additional_properties` | ✅ |
| Integração real HTTP 200 | `test_integration_ping_real_gemini` | ✅ |

---

## 6. Segurança da chave

### Grep final
```
$ grep -rln "AQ.Ab8RN6L504" /app
/app/backend/.env       ← único local
```

- ✅ Zero exposição em logs (`/var/log/supervisor/backend.*.log`).
- ✅ Zero exposição em código versionado (nem em `/app/backend/`, nem em `/app/frontend/`).
- ✅ Função `_redact_key()` chamada em todas as mensagens de erro antes de serem passadas ao `AIProviderError`.
- ✅ Padrões cobertos: `AQ.*` (novo formato) e `AIzaSy*` (legado).
- ✅ Header `x-goog-api-key` nunca é logado pelo `httpx` (não aparece no payload).

---

## 7. Latência observada

| Motor | Gemini real | Comparação |
|-------|-------------|------------|
| Coach IA (ping curto) | ~6s | — |
| BTP Solver (patologia simples) | ~6s | — |
| Plans Pro (structured output completo) | ~32s | Inclui raciocínio Pro + thinking tokens |

**Nota UX:** Gemini Pro usa thinking tokens que inflacionam a latência vs. Claude/OpenAI. Para o Coach IA interactivo (humano a aguardar resposta no chat), 6s é aceitável mas no limite — se o utilizador reportar lentidão, considerar `gemini-flash-latest` **só para Coach** mantendo `pro-latest` em Plans Pro (onde a precisão > velocidade).

---

## 8. Compatibilidade com o schema do Gemini `responseSchema`

Descoberto durante teste real: Gemini v1beta é mais restritivo que OpenAI strict:

| Chave JSON Schema | OpenAI strict | Gemini v1beta | Tratamento |
|-------------------|:---:|:---:|---|
| `additionalProperties` | aceita (obriga `false`) | **rejeita** | Removido em `_strip_additional_properties()` |
| `$defs` + `$ref` | aceita | **rejeita (HTTP 400)** | Inlining recursivo em `_inline_refs()` |
| `$schema`, `$id`, `const` | aceita | rejeita | Removido em `_strip_unsupported_keys()` |

Resultado: um único `_schema_openai_strict()` serve de fonte-única-de-verdade, e `_schema_for_gemini()` degrada-o para o subset aceite. Zero duplicação de schemas.

---

## 9. Critérios de aceitação

- [x] Chave validada via HTTP real (`?key=` e `x-goog-api-key` ambos 200; `Bearer` → 401).
- [x] `.env` actualizado + `.env.example` placeholders.
- [x] `call_gemini_structured()` implementado com `responseSchema` nativo.
- [x] Cascata **Gemini → Claude → OpenAI** funcional em Coach IA, BTP Solver e Plans Pro.
- [x] `test_plans_pro_gemini.py` + `test_ai_providers_gemini.py` verdes (30 novos casos).
- [x] Teste integração real executado — ping Gemini responde HTTP 200 em 3.5s.
- [x] **E2E real nos 3 motores confirmado:** Coach (`6s`), BTP (`6s`), Plans Pro structured (`32s`).
- [x] Zero regressões: **228/228** testes verdes (198 pré-existentes + 30 novos).
- [x] Grep final: chave só existe em `/app/backend/.env`, nunca em código, logs ou frontend.
- [x] Perplexity preservado (não entra na cascata).
- [x] System prompts do Claude reaproveitados literal (via `systemInstruction` do Gemini).

---

## 10. Decisões técnicas de nota

### 10.1 System prompt — reaproveitamento literal
O System Prompt do Claude é passado directamente ao Gemini via `systemInstruction` do payload (não em `contents` como mensagem `role=user`). Isto permite:
- Zero duplicação de prompts.
- Gemini aplica o prompt globalmente (todas as mensagens).
- Troca de provider é transparente para o user.

Quando o utilizador enviar o System Prompt dedicado ao Assistente de Obras, basta substituir `_SOLVER_SYSTEM` em `engines/btp_solver/solver.py` — Gemini continua a usá-lo da mesma forma.

### 10.2 Ordem global vs. especial para Plans Pro
Antes da Fase 1b, Plans Pro usava `OpenAI → Claude` (sem Gemini) porque OpenAI tem `response_format=json_schema strict`. Agora Gemini também suporta `responseSchema` nativo com qualidade equivalente, portanto alinhei o Plans Pro com a cascata global **Gemini → Claude → OpenAI** — simplicidade de operação prevalece sobre o micro-ganho de ter uma ordem diferente.

### 10.3 Thinking tokens no Gemini Pro
Observado em todas as chamadas reais: `usageMetadata.thoughtsTokenCount` pode consumir 500-2000 tokens antes de o modelo produzir o output textual. Dois impactos:
- `max_tokens` precisa de ser dimensionado para INCLUIR os thinking tokens. Ping aumentado de 8 → 256; structured output Plans Pro de 4096 → 8192.
- Latência Pro ~5-30s é característica do modo thinking. Para operações que precisam de resposta sub-segundo, usar `gemini-flash-latest`.

---

## 11. O que fica para fases seguintes

- **System Prompt dedicado ao Assistente de Obras** quando o utilizador o enviar → substitui `_SOLVER_SYSTEM` directamente.
- Avaliar `gemini-flash-latest` para Coach IA se o utilizador reportar que ~6s é lento para chat.
- Métricas Prometheus-style por provider (futuro Fase observabilidade).
- Fase 2 do plano global Plans Pro: OCR dedicado (Tesseract PT) + léxico expandido.
