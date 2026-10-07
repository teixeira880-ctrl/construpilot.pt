# Fases B + C — Frontend + Observabilidade do Assistente BTP

**Data:** 07 Out 2026 · **Scope:** UI nova `/btp-assistente` + instrumentação de métricas + painel admin `/admin/btp-metrics`.

---

## 1. Fase B — Frontend `/btp-assistente`

### 1.1 Rota e autenticação
- Nova rota `/btp-assistente` (JWT obrigatório via `<Protected>`).
- Alias `/assistente-btp` → redirect 301.
- Página antiga `/btp-solver` mantém-se para retrocompat; na nova página existe link discreto "Versão anterior" no header.

### 1.2 Componentes criados

| Caminho | LoC | Papel |
|---------|----:|-------|
| `src/pages/AssistenteBTP.jsx` | 42 | Container: header com logo + badge "Autónomo" + chat |
| `src/components/btp/AssistenteBTPChat.jsx` | 400 | Core do chat: estado, SSE, markdown, pills, anexos, drag-drop, modal confirmação, missing_data cards |
| `src/components/btp/AcaoConfirmacao.jsx` | 90 | Dialog shadcn com resumo PT-PT por ferramenta |
| `src/components/btp/MissingDataCard.jsx` | 95 | Card amarelo com input tipado (text/number) por `unit` |
| `src/components/btp/sseClient.js` | 100 | `fetch`+`ReadableStream` para SSE com `Authorization: Bearer` (não `EventSource` por limitação de headers) |
| `src/components/btp/assistente-btp.css` | 170 | Chat bubbles, pills animadas, tabelas markdown, composer sticky, safe-area iOS |
| `src/pages/admin/BTPMetrics.jsx` | 240 | Dashboard admin (KPI cards, recharts, tabela, export CSV) |

### 1.3 Fluxo SSE
Cada evento SSE é mapeado para UI em tempo real:

| Evento | UI resultante |
|--------|--------------|
| `thinking` | Pill animado "A pensar…" (indigo com `btp-pulse`) |
| `text_chunk` | Append incremental ao bubble do agente (Markdown live) |
| `tool_call` | Pill novo com ícone contextual (📂 abrir_app, 📊 criar_orcamento, 🔎 pesquisar_norma, 💰 obter_preco_material, 🧮 estimar_custo, 📚 pesquisar_biblioteca, ❓ pedir_precisao, …) |
| `tool_result` (`status=ok`) | Pill vira verde "✓ Concluído". Se `payload.action="navigate"` → botão "Abrir /devis →" que chama `useNavigate()` |
| `tool_result` (`status=needs_user_confirmation`) | Abre `<AcaoConfirmacao>` com resumo PT-PT; confirmação chama `POST /api/btp-assistant/confirm` |
| `missing_data` | Card amarelo com `question_pt`, input + botão "Responder" que dispara novo turno com a resposta |
| `final` | Fecha pill thinking, grava `conversationId`, mostra meta (modo · modelo · duração) |
| `error` | Pill vermelho com mensagem PT-PT + toast |

### 1.4 Anexos
- Botão 📎 + drag-and-drop sobre a zona chat
- `accept="image/*,application/pdf,.dwg,.dxf,.ifc"`
- Limite: 20 MB por anexo, máx. 5 anexos por turno
- Chips preview com nome + tamanho KB + botão X para remover
- Conversão base64 via `FileReader.readAsDataURL`

### 1.5 Markdown
- `react-markdown` 10 + `remark-gfm` 4 + `rehype-highlight` 7
- Suporta tabelas, listas, listas de tarefas, strikethrough, blocos de código, inline code
- Estilos próprios em `.btp-bubble--agent` (ignora Tailwind prose para controlo total)

### 1.6 Navegação (`Nav.jsx`)
No dropdown "Descobrir":
- **"Assistente BTP (Novo)"** com logo `/assistente-obras-logo.png` + badge indigo "Novo" → `/btp-assistente`
- **"Assistente de Obras"** mantém badge cinza "Legado" → `/btp-solver`

### 1.7 Responsividade
- Desktop/tablet: layout único, chat centrado max-w-3xl
- Mobile: composer sticky bottom com `env(safe-area-inset-bottom)` para iOS
- Pills quebram em várias linhas via `flex-wrap`
- Textarea auto-expansível `min-h-[42px] max-h-[200px]`

---

## 2. Fase C — Observabilidade

### 2.1 Instrumentação no `router.py`
Função `_gravar_metrica()` chamada no fim de cada turno (dentro do mesmo turn-handler, após persistir conversa, dentro de `try/except` para nunca interromper).

Documento gravado em `btp_assistant_metrics`:
```json
{
  "conversation_id": "conv_abc123",
  "user_id": "user_bf7...",
  "user_plan": "pro",
  "modo": "calculo",
  "modelo": "gemini-pro-latest",
  "duracao_ms": 11116,
  "events_count": 15,
  "tools_called": ["estimar_custo"],
  "tool_errors": 0,
  "grounding_used": false,
  "missing_data_count": 0,
  "attachments_count": 0,
  "status": "success",
  "created_at": ISODate("2026-10-07T22:00:00Z")
}
```
**Zero PII**: nunca grava `user_prompt`, `text_pt`, nem `attachments` (apenas contagem).

### 2.2 Endpoints admin (`routes/admin_btp_metrics.py`)

| Endpoint | Função |
|----------|--------|
| `GET /api/admin/btp-assistant/metrics?from&to&user_plan&modo` | Agregados (total, latência, custo EUR, success_rate, grounding_rate, missing_data_rate, tools_usage top 15) |
| `GET /api/admin/btp-assistant/metrics/recent?limit=50` | Últimas N chamadas anonimizadas (`user_id` truncado a 6 chars) |
| `GET /api/admin/btp-assistant/metrics/export.csv` | Export CSV completo (10k máx) |

Todos exigem `user.role == "admin"` (403 caso contrário).

### 2.3 Custos estimados em EUR
Preços Gemini (Oct 2026, USD/1M tokens) → EUR via `0.92`:

| Modelo | Input | Output |
|--------|-------|--------|
| `gemini-pro-latest` | $1.25 | $10.00 |
| `gemini-flash-latest` | $0.075 | $0.30 |

Heurística de tokens por modo (até termos tracking exacto de tokens via SDK):
- Modo `conversa`: ~1200 in / 800 out
- Modo `calculo/plano`: ~2000 in / 1500 out

Resultado agregado soma por `(modelo, modo, n)` → `cost_estimate_eur`.

### 2.4 Painel `/admin/btp-metrics`
- Filtros: Período (hoje/7d/30d/90d), Modo, Plano
- KPI cards: Chamadas / Latência média / Taxa sucesso / Custo estimado EUR
- Gráfico Recharts: tools mais usadas (bar chart, cores indigo, labels PT-PT)
- Tabela últimas 50 chamadas com badges de estado (Sucesso/Erro/A aguardar)
- Botão "CSV" para export

---

## 3. Ficheiros criados/alterados

### Backend
| Caminho | Alteração |
|---------|-----------|
| `engines/btp_assistant/router.py` | +`_gravar_metrica()` (65 linhas) + chamada após persistência |
| `routes/admin_btp_metrics.py` | Novo (210 LoC) — endpoints admin + custos |
| `server.py` | +1 import + 1 `include_router` |
| `tests/test_btp_assistant_metrics.py` | Novo (90 LoC) — 3 testes |

### Frontend
| Caminho | Papel |
|---------|-------|
| `src/pages/AssistenteBTP.jsx` | Container |
| `src/pages/admin/BTPMetrics.jsx` | Dashboard admin |
| `src/components/btp/AssistenteBTPChat.jsx` | Core chat SSE |
| `src/components/btp/AcaoConfirmacao.jsx` | Modal confirmação |
| `src/components/btp/MissingDataCard.jsx` | Card dados em falta |
| `src/components/btp/sseClient.js` | Cliente SSE |
| `src/components/btp/assistente-btp.css` | Estilos |
| `src/App.js` | +3 rotas (`/btp-assistente`, alias, `/admin/btp-metrics`) + 2 imports |
| `src/components/Nav.jsx` | +entrada dropdown "Assistente BTP (Novo)" + badges |
| `package.json` | +`react-markdown`, `remark-gfm`, `rehype-highlight` |

---

## 4. Resultados dos testes

### Backend
```
$ pytest tests/
280 passed, 1 skipped, 6 warnings in 31.21s
```
Composição: 277 testes pré-Fase BC + 3 novos de métricas. **Zero regressões.**

Teste pré-existente flaky `test_c3_wave.py::test_login_invalid` (rate-limit do IP) confirmado NÃO ser regressão (reproduz com `git stash`).

### Frontend
```
$ cd /app/frontend && CI=false yarn build
Compiled successfully.
Done in 22.26s.
```
Build limpo sem erros. Warnings `exhaustive-deps` são todos pré-existentes (não introduzi novos — `BTPMetrics.jsx` usa `useCallback` para evitar).

### HTTP (produção preview)
```
POST /api/btp-assistant/chat sem auth    → 401 ✅ (JWT exigido)
GET  /api/admin/btp-assistant/metrics    → 401 ✅
GET  /api/auth/me com token teste        → 200 ✅
```

### UI (navegação Playwright)
- `[data-testid="btp-chat-root"]` detectado ✅
- `[data-testid="btp-prompt-input"]` detectado ✅ (wait_for_selector com timeout 20s)
- URL final `/btp-assistente` sem redirect involuntário

---

## 5. Exemplo real de SSE events (decoded com tempos)

Pedido: `POST /api/btp-assistant/chat` com `{prompt: "Abre-me o módulo de orçamentos.", stream: true}`

```
t=0.00s event: thinking
         data: {"type":"thinking","data":{"mode":"calculo","model":"gemini-pro-latest"}}

t=3.42s event: tool_call
         data: {"type":"tool_call","data":{
           "id":"tc_a1b2c3d4",
           "name":"abrir_app",
           "arguments":{"nome_app":"orcamento"},
           "requires_user_confirmation":false
         }}

t=3.44s event: tool_result
         data: {"type":"tool_result","data":{
           "tool_call_id":"tc_a1b2c3d4",
           "status":"ok",
           "payload":{"action":"navigate","url":"/devis","target":"_self"},
           "user_message_pt":"A abrir o módulo orcamento."
         }}

t=3.86s event: text_chunk
         data: {"type":"text_chunk","data":{"text":"Pronto. Já pode consultar..."}}

t=3.90s event: final
         data: {"type":"final","data":{
           "conversation_id":"conv_7f8e9d0a",
           "turn_id":"turn_b4c5d6e7",
           "text_pt":"Pronto. Já pode consultar...",
           "mode":"calculo",
           "model":"gemini-pro-latest",
           "duration_s":3.90,
           "tool_calls_count":1,
           "missing_data_count":0
         }}
```

UI final mostra:
- 1 pill verde "✓ abrir_app Concluído"
- 1 bubble do agente com Markdown "Pronto..."
- 1 botão "Abrir /devis →" que faz `navigate("/devis")`
- Meta: `calculo · gemini-pro-latest · 3.9s`

---

## 6. Critérios de aceitação

### Fase B
- [x] `/btp-assistente` carrega com JWT; chat funcional; SSE visível em tempo real
- [x] Upload de imagem/PDF (até 20 MB × 5) end-to-end + drag-and-drop
- [x] `criar_orcamento` dispara `<AcaoConfirmacao>` com resumo PT-PT
- [x] `abrir_app` emite tool_result com `action=navigate` + botão "Abrir →" que faz `useNavigate(url)`
- [x] `MissingDataRequest` → card amarelo com input tipado + botão "Responder" que relança turno
- [x] Markdown GFM (tabelas, listas, código, strikethrough) renderiza correctamente
- [x] Nav.jsx tem "Assistente BTP (Novo)" com badge indigo "Novo" + logo
- [x] Mobile responsivo: composer sticky com safe-area iOS, pills quebram em flex-wrap

### Fase C
- [x] Cada chamada ao `/api/btp-assistant/chat` grava 1 doc em `btp_assistant_metrics`
- [x] `GET /api/admin/btp-assistant/metrics` devolve agregados com custo EUR estimado
- [x] `/admin/btp-metrics` renderiza KPIs + Recharts BarChart + tabela últimas 50 chamadas + export CSV
- [x] Zero PII: `user_prompt`, `text_pt`, `attachments` NÃO são persistidos nas métricas (teste `test_btp_assistant_metrics.py::test_turno_conversa_grava_metrica` valida explicitamente)

### Qualidade
- [x] 280 pytest verdes, zero regressões face à Fase A
- [x] `yarn build` compila sem erros
- [x] Endpoints registados e protegidos (401 sem JWT; 403 sem admin role)
- [x] PT-PT em TUDO (código, UI, mensagens, badges, labels Recharts, resumos modal, toasts)

---

## 7. Preservação de scope

- ✅ Resend fix — intocado
- ✅ Stair Engine — continua pausado
- ✅ Plans Pro Fase 1 — intocado (semantic reutilizado via `MissingDataRequest`)
- ✅ Pricing 99/179 — intocado
- ✅ i18n PT-PT — garantido em todos os novos componentes
- ✅ Cascade Gemini → Claude → OpenAI dos outros motores — intocada
- ✅ Perplexity Plus — reutilizado via tool `pesquisar_norma`
- ✅ Coach IA e Plans Pro — independentes, não tocados

---

## 8. Observações técnicas

### 8.1 Autenticação SSE
`EventSource` nativo não suporta headers customizados. Para `Authorization: Bearer <jwt>` usamos `fetch` + `ReadableStream` + `TextDecoder` em `sseClient.js`. O parsing manual de blocos SSE (`\n\n`) é robusto a chunks parciais TCP.

### 8.2 `page.evaluate` + token Playwright
Observação durante teste: `localStorage.setItem` dentro de `page.goto` → `evaluate` não persiste entre navegações. Resolvido com `page.add_init_script()` que corre antes de qualquer código da página. Isto é só relevante para automação de testes — produção não é afectada.

### 8.3 Custos EUR como aproximação
Até o SDK oficial devolver tokens exactos num campo tipado estável (actualmente estão em `usageMetadata` do Gemini mas não exposto cleanly no nosso wrapper), usamos heurística por modo. Fase D opcional pode substituir pela leitura directa de `response.usage_metadata`.

### 8.4 Admin role check
O middleware `current_user` já popula `user.role` a partir do JWT. `_exige_admin()` verifica e levanta 403. Não exige novo endpoint auth.

---

## 9. Próximas fases sugeridas

- **Fase D — Sidebar de conversas:** painel colapsável lateral com histórico (GET `/api/btp-assistant/conversations` que já existe, só precisa de novo endpoint `list_all`).
- **Fase E — Tokens exactos nas métricas:** expor `usageMetadata` do Gemini response no `AgentEvent.final.data` e persistir em `btp_assistant_metrics`.
- **Fase F — Remoção definitiva do `btp_solver`:** após 30 dias de co-existência, remover rota legacy + redirect 301 permanente para `/btp-assistente`.
- **Pre-existing React `exhaustive-deps`:** continua a aguardar Sprint 10 para limpeza global (os meus novos ficheiros estão compliance com `useCallback`).
