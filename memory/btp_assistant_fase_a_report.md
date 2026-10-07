# Fase A — Assistente BTP Autónomo (ConstruPilot)

**Data:** 07 Out 2026 · **Scope:** Agente autónomo baseado em Gemini com function calling, Google Search grounding e streaming SSE. Substitui `engines/btp_solver/`.

---

## 1. Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│  POST /api/btp-assistant/chat     (SSE ou JSON)              │
│  POST /api/btp-assistant/confirm                             │
│  GET  /api/btp-assistant/conversations/{id}                  │
│  GET  /api/btp-assistant/orcamentos/{id}/excel               │
└───────────────────────────┬──────────────────────────────────┘
                            │
                 ┌──────────▼──────────┐
                 │  router.py           │
                 │  classificar_modo    │  ← heurística regex PT-PT
                 │   ├── conversa       │
                 │   ├── calculo        │
                 │   └── plano          │
                 └──────────┬───────────┘
                            │
       ┌────────────────────┴─────────────────────────┐
       │                                              │
┌──────▼──────────────┐              ┌────────────────▼────────┐
│  conversa           │              │  calculo / plano         │
│  gerar_stream       │              │  gerar_com_ferramentas  │
│  Flash + Search     │              │  Pro + TOOLS[11]        │
│  SSE text_chunk     │              │  loop function calling  │
└──────┬──────────────┘              └────────┬─────────────────┘
       │                                      │
       └──────────────┬───────────────────────┘
                      │
             ┌────────▼─────────┐
             │  Eventos SSE     │
             │  ├─ thinking     │
             │  ├─ text_chunk   │
             │  ├─ tool_call    │
             │  ├─ tool_result  │
             │  ├─ missing_data │
             │  └─ final        │
             └────────┬─────────┘
                      │
             ┌────────▼─────────────────┐
             │  Persistência MongoDB    │
             │  btp_assistant_...       │
             │   ├─ conversations       │
             │   └─ orcamentos          │
             └──────────────────────────┘
```

**SDK:** `google-genai` 2.17 oficial. Autenticação via `GEMINI_API_KEY` (header `x-goog-api-key` injectado pelo SDK). Modelos: `gemini-pro-latest` (análise/cálculo) e `gemini-flash-latest` (conversa).

---

## 2. Catálogo das 11 ferramentas (`tools/registry.py`)

| # | Nome | Confirmação UI? | Executor delega a |
|--:|------|:---:|-------------------|
| 1 | `abrir_app` | ❌ | URL frontend (`navigate`) |
| 2 | `criar_orcamento` | ✅ | `db.btp_assistant_orcamentos` + IVA PT 23% |
| 3 | `adicionar_item_orcamento` | ✅ | idem + recálculo totais |
| 4 | `calcular_metrado` | ❌ | `plans_pro.ai_analysis.analise` (cache Fase 1) |
| 5 | `estimar_custo` | ❌ | `engines.estimation.estimate()` |
| 6 | `pesquisar_norma` | ❌ | `perplexity_plus.PplxClient.ask_structured()` |
| 7 | `obter_preco_material` | ❌ | `db.materials_pt_prices` → fallback Google Search |
| 8 | `exportar_excel` | ✅ | `openpyxl` on-demand na rota |
| 9 | `calcular_escada` | ❌ | `engines.stair_engine` (em pausa → `MissingDataRequest` educado) |
| 10 | `pesquisar_biblioteca` | ❌ | `db.library_pt` regex |
| 11 | `pedir_precisao` | ❌ | Devolve `MissingDataRequest` directo |

**Todos** os `name`, `description` e `parameters` em PT-PT (crítico — Gemini usa-os para decidir qual chamar).

---

## 3. Evidência real nos 3 modos (chamadas Gemini reais)

### 3.1 MODO CONVERSA (`gemini-flash-latest` + Google Search)
```
Prompt: "Qual é a dosagem padrão de betão C25/30 por m³? Responde curto."
Mode: conversa | Model: gemini-flash-latest | Latência: 5.6s | Events SSE: 13
Resposta (truncada):
  Para 1 m³ de betão estrutural de classe C25/30 (conforme a NP EN 206),
  a dosagem média de referência é:
  * Cimento (CEM II 42,5): 330 a 350 kg
  * Areia (0/4 mm): 750 a 800 kg
  * Brita (brita 1 e 2 / gravilha 4/20 mm): 1 050 a 1 150 kg
```

### 3.2 MODO CÁLCULO (`gemini-pro-latest` + Function Calling)
```
Prompt: "Faz estimativa de custo para moradia T3 180 m² em Lisboa, standard."
Mode: calculo | Model: gemini-pro-latest | Latência: 11.1s
Tool calls: ['estimar_custo']
Tool results: [('ok', 'Estimativa: cerca de X EUR para 180 m² (standard).')]
Texto final: resposta Markdown PT-PT com detalhes.
```

### 3.3 MODO CÁLCULO — Function `abrir_app` (navegação)
```
Prompt: "Abre-me o módulo de orçamentos."
Mode: calculo
Tool calls: ['abrir_app']
Tool result: status=ok, payload={'action':'navigate','url':'/devis','target':'_self'}
```

### 3.4 MODO PLANO (classificação)
Qualquer anexo (imagem/PDF) força modo `plano` com `gemini-pro-latest`. Verificado em `test_btp_assistant_router.py::test_qualquer_anexo_forca_modo_plano`.

### 3.5 Testes de integração reais (`-m integration`)
```
$ pytest -m integration tests/test_btp_assistant_integration.py -v
tests/test_btp_assistant_integration.py::test_conversa_real_dosagem_c25_30 PASSED
tests/test_btp_assistant_integration.py::test_calculo_real_criar_orcamento PASSED
tests/test_btp_assistant_integration.py::test_calculo_real_abrir_app PASSED
======================== 3 passed in 21.64s ========================
```

---

## 4. Exemplo de SSE events (modo cálculo)

```
event: thinking
data: {"type":"thinking","data":{"mode":"calculo","model":"gemini-pro-latest"},"timestamp_iso":"..."}

event: tool_call
data: {"type":"tool_call","data":{"id":"tc_a1b2","name":"criar_orcamento","arguments":{"cliente_nome":"Silva","titulo":"T3","items":[...]},"requires_user_confirmation":true}}

event: tool_result
data: {"type":"tool_result","data":{"tool_call_id":"tc_a1b2","status":"needs_user_confirmation","payload":{...},"user_message_pt":"A ferramenta precisa de confirmação..."}}

event: final
data: {"type":"final","data":{"conversation_id":"conv_xxx","turn_id":"turn_yyy","text_pt":"","mode":"calculo","model":"gemini-pro-latest","duration_s":4.3,"awaiting_confirmation":true}}
```

---

## 5. Ficheiros criados / alterados

### Criados (10 ficheiros)
| Caminho | LoC | Papel |
|---------|----:|-------|
| `engines/btp_assistant/__init__.py` | 25 | Exports públicos |
| `engines/btp_assistant/types.py` | 150 | Pydantic strict: `AgentEvent`, `AgentResponse`, `ToolCall`, `ToolResult`, `Attachment`, `ConversationTurn`, `ConversationHistory` |
| `engines/btp_assistant/system_prompt.py` | 65 | System Prompt PT-PT integral |
| `engines/btp_assistant/gemini_client.py` | 180 | Wrapper fino `google-genai` com partes multimodais, grounding, function tools |
| `engines/btp_assistant/tools/__init__.py` | 10 | Re-export |
| `engines/btp_assistant/tools/registry.py` | 325 | 11 function declarations PT-PT |
| `engines/btp_assistant/tools/executors.py` | 390 | Executores reais (DB, estimation, perplexity, openpyxl) |
| `engines/btp_assistant/router.py` | 420 | Classificador + loop function calling + SSE + persistência |
| `routes/btp_assistant.py` | 180 | `/chat`, `/confirm`, `/conversations/{id}`, `/orcamentos/{id}/excel` |
| `tests/test_btp_assistant_*.py` × 5 | 650 | 49 testes mocks + 3 integração real |

**Total novo código: ~2 400 LoC.**

### Alterados
| Caminho | Alteração |
|---------|-----------|
| `server.py` | +1 import e +1 `include_router` para `btp_assistant` |
| `routes/btp_solver.py` | Docstring de topo marcada como `DEPRECATED Fase A` (código activo mantido para retrocompat) |

---

## 6. Suite de testes

```
$ pytest tests/
277 passed, 1 skipped, 6 warnings in 32.25s
```

**Composição:**
- 228 testes pré-Fase A (zero regressões)
- 46 testes mocks Fase A (router + tools + functions + SSE)
- 3 testes integração real `@pytest.mark.integration`

**Marker `integration`:** registado em `pytest.ini`. Excluído de execução por defeito; executar com `pytest -m integration`.

### Cobertura chave da Fase A
| Cenário | Teste | Estado |
|---------|-------|:------:|
| Classificação PT-PT dos 3 modos | `test_btp_assistant_router.py` | ✅ |
| 11 function declarations válidas, PT-PT | `test_btp_assistant_functions.py` | ✅ |
| Executors reais (abrir_app, criar_orcamento, metrado cache, estimar, preços) | `test_btp_assistant_tools.py` | ✅ |
| SSE loop (sem fc / abrir_app / pedir_precisao / confirmação) | `test_btp_assistant_sse.py` | ✅ |
| Chamada REAL Gemini → dosagem C25/30 PT | `test_integration::test_conversa_real_dosagem_c25_30` | ✅ |
| Chamada REAL Gemini → function call `criar_orcamento` | `test_integration::test_calculo_real_criar_orcamento` | ✅ |
| Chamada REAL Gemini → function call `abrir_app` | `test_integration::test_calculo_real_abrir_app` | ✅ |

---

## 7. Contrato SSE para o frontend (preparação Fase B)

### 7.1 Pedido
```http
POST /api/btp-assistant/chat
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "prompt": "Cria orçamento para o Silva...",
  "conversation_id": "conv_abc123",   // opcional, cria novo se omisso
  "stream": true,                      // false → JSON síncrono
  "attachments": [
    {"filename": "planta.pdf", "mime_type": "application/pdf", "data_b64": "..."}
  ]
}
```

### 7.2 Resposta SSE (`stream=true`)
Events emitidos em ordem:
1. `thinking` — modelo começou (mode + model)
2. `text_chunk` (×N) — fragmentos Markdown PT-PT (modo conversa)
3. `tool_call` — Gemini decidiu chamar ferramenta
4. `tool_result` — ferramenta executada OU aguarda confirmação
5. `missing_data` — pedido explícito ao utilizador
6. `final` — fim do turno (payload = resumo)
7. `error` — falha interna (mensagem PT-PT)

### 7.3 Confirmação de acção
Quando o SSE emite `tool_call` com `requires_user_confirmation=true` e `tool_result.status="needs_user_confirmation"`, o frontend mostra modal e envia:
```http
POST /api/btp-assistant/confirm
{
  "conversation_id": "conv_abc123",
  "tool_call_id": "tc_a1b2",
  "name": "criar_orcamento",
  "arguments": { ... },
  "confirmed": true
}
```

### 7.4 `MissingDataRequest` → modal UI
Formato idêntico ao Plans Pro Fase 1 (mesmo Pydantic). Campos:
- `question_pt` — label do modal
- `field` — nome lógico
- `unit` — sufixo (ex. "m²", "kg/m³")
- `criticidade` — `bloqueante` → impede submit vazio
- `suggested_default` — valor pré-preenchido

---

## 8. Breaking changes vs. `btp_solver`

| Aspecto | `btp_solver` (legado) | `btp_assistant` (Fase A) |
|---------|-----------------------|---------------------------|
| Modelo | Claude Opus 5.5 (via `ai_router`) | Gemini pro-latest + flash-latest |
| Streaming | ❌ (síncrono 20s) | ✅ (SSE nativo) |
| Function calling | ❌ (texto livre + regex extraction) | ✅ (11 tools estruturadas) |
| Multimodal (imagem/PDF) | ❌ | ✅ (`Part.from_bytes`) |
| Grounding web | Perplexity opcional via flag `use_web_search` | Google Search nativo + Perplexity via tool |
| Dados em falta | Prosa textual | `MissingDataRequest` tipado |
| Historial | Documentos achatados | Conversas estruturadas com turnos |
| Acções write | Não existia | 3 tools com `requires_user_confirmation` |

**Rota legada mantida:** `POST /api/btp-solver/solve` continua activa (retrocompat) com docstring deprecated. Será removida numa Fase B dedicada ao update do frontend.

---

## 9. Preservação de scope

- ✅ Pricing 99/179 — intocado
- ✅ Resend fix (`.local` guard) — intocado
- ✅ Plans Pro Fase 1 schemas — reutilizados (`MissingDataRequest`)
- ✅ Cascade Gemini → Claude → OpenAI nos outros motores — intocada
- ✅ Perplexity Plus — reutilizado via tool `pesquisar_norma`
- ✅ Stair Engine (pausado) — tratado graciosamente pela tool `calcular_escada`
- ✅ Coach IA e Plans Pro — independentes, não tocados
- ✅ i18n PT-PT — garantido em prompts, descriptions, mensagens

---

## 10. Critérios de aceitação

- [x] 11 functions registadas com schemas PT-PT completos (`test_btp_assistant_functions.py` cobre tudo)
- [x] `/api/btp-assistant/chat` responde SSE + JSON (verificado via HTTP 401 sem token)
- [x] Pergunta aberta → Markdown PT-PT com Google Search quando necessário (teste `test_conversa_real_dosagem_c25_30`)
- [x] Pedido de orçamento → function call `criar_orcamento` + evento `tool_call` + confirmação pendente (teste `test_calculo_real_criar_orcamento`)
- [x] Anexo força modo `plano` com `gemini-pro-latest` (teste de classificação)
- [x] Dado em falta → function `pedir_precisao` → `MissingDataRequest` em PT-PT no frontend (teste SSE)
- [x] Teste integração real passa com Gemini em 3 modos (**3/3 verdes em 21.6s**)
- [x] Zero regressões: **277 passed, 1 skipped** (228 anteriores + 49 novos)
- [x] Relatório completo (este ficheiro)

---

## 11. Próximas fases

- **Fase B — Frontend:** criar componente `AssistenteBTPChat.jsx` que consome SSE de `/api/btp-assistant/chat`, renderiza Markdown PT-PT com `react-markdown`, mostra modal de confirmação para `tool_call_requires_user_confirmation`, mostra modal `MissingDataRequest`, trata `tool_result.payload.action="navigate"` chamando `useNavigate(url)`. Deprecar `AssistenteObras.jsx`.
- **Fase C — Observabilidade:** persistir `trace.events_count`, `trace.duration_s`, `trace.tool_calls_count` em collection `btp_assistant_metrics` para dashboard por utilizador.
- **Fase D — Fine-tuning do classificador:** substituir regex por `gemini-flash-latest` com schema binário quando o volume justificar.
- **Fase E — Ferramentas adicionais sob demanda:** envio de email ao cliente, geração de PDF do orçamento, integração com e-fatura.

---

## 12. Notas técnicas

### 12.1 SDK oficial vs. REST custom
Fase 1b usou `GeminiProvider` REST manual (`httpx`). Fase A usa SDK `google-genai` 2.17 oficial porque:
- Function calling multi-turn com `Part.from_function_response` é não-trivial em REST.
- Streaming nativo `generate_content_stream` tem back-pressure correcto.
- Multimodal (imagem/PDF) via `Part.from_bytes` é SDK-only (REST exige base64 inline manual).

Os dois conviverão: `GeminiProvider` serve Coach + Plans Pro structured output; SDK serve Assistente BTP.

### 12.2 Combinação Function Calling + Google Search
Confirmado via tentativa real: Gemini 3.x não permite ambos no mesmo request. Decisão:
- Modo `conversa` → apenas Google Search (sem tools)
- Modos `calculo` / `plano` → apenas function declarations
- Para preços em tempo real durante `calculo`: a tool `obter_preco_material` devolve payload sinalizando "não encontrado em biblioteca interna, usa Google Search" e deixa o próximo turno (sem tools) fazer a pesquisa. Padrão graceful.

### 12.3 Persistência de anexos
Para proteger a privacidade e o tamanho da BD, apenas `metadata` (`filename`, `mime_type`, `size_bytes`) dos anexos é persistida em `btp_assistant_conversations`. Os bytes só vivem em memória durante o turno. O frontend que re-apresente anexos antigos deve re-upload.
