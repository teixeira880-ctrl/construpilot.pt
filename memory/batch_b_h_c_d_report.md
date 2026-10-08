# Batch B → H → c → D — Relatório Final

**Data:** 08/02/2026
**Agente:** E1
**Decisões utilizador (confirmadas):** 1a, 2a, 3a, 4a, 5a

---

## Fase B — Tokens reais Gemini em `btp_assistant_metrics`

### O que foi feito
Substituição total da heurística de tokens por leitura real do campo
`usage_metadata` devolvido pelo SDK oficial `google-genai`. Cálculo
exacto de custo EUR com taxa configurável `EUR_USD_RATE=0.92`.

### Ficheiros alterados/criados
- **Criado** `/app/backend/engines/btp_assistant/pricing.py`
  - `PRECOS_USD_POR_1M` (tabela Gemini Pro + Flash)
  - `taxa_eur_usd()`, `custo_eur()`, `extrair_usage()`, `acumular_usage()`, `novo_acumulador()`
- **Alterado** `/app/backend/engines/btp_assistant/router.py`
  - `_executar_modo_conversa` acumula `usage_metadata` do último chunk (streaming)
  - `_executar_modo_com_ferramentas` soma `usage_metadata` por ronda (loop function-calling)
  - `_gravar_metrica` grava `tokens_input_real`, `tokens_output_real`, `thinking_tokens_real`, `cached_tokens_real`, `total_tokens_real`, `cost_estimate_eur` + alias retrocompat (`tokens_input`, `tokens_output`)
- **Reescrito** `/app/backend/routes/admin_btp_metrics.py`
  - Pipeline agregado usa `tokens_input_real` com `$ifNull` para fallback aos antigos
  - Devolve `avg_thinking_tokens`, `total_thinking_tokens`, `calls_with_real_tokens`, `eur_usd_rate`
  - Export CSV inclui as novas colunas
  - Novo endpoint `GET /admin/btp-assistant/metrics/pricing` para debug
- **Alterado** `/app/backend/.env`
  - Adicionado `EUR_USD_RATE=0.92`
  - Adicionado `PUBLIC_LINK_TTL_DAYS=60`
- **Alterado** `/app/frontend/src/pages/admin/BTPMetrics.jsx`
  - Nova linha de KPIs: tokens input médios, tokens output médios, **Thinking (tokens médios)** 🧠, cache hits médios
  - `formatarCustoEUR()` com 4 casas decimais quando < 1 €
  - Mostra `eur_usd_rate` no sub-label do KPI custo

### Evidência real
```
model: gemini-pro-latest | mode: calculo
métrica guardada:
  tokens_input_real: 5656
  tokens_output_real: 337
  thinking_tokens_real: 1067
  total_tokens_real: 7060
  cost_estimate_eur: 0.019421
```
Agregado admin devolve: `avg_thinking_tokens: 533`, `total_thinking_tokens: 1067`, `eur_usd_rate: 0.92`.

### Breaking changes
Nenhum. Os campos antigos (`tokens_input`, `tokens_output`) são mantidos como alias.

---

## Fase H — Tradução FR → PT-PT

### O que foi feito
Tradução das strings FR visíveis nas páginas user-facing principais
(PT-PT). Decisão 2a confirmada: apenas texto visível ao utilizador +
chamadas `t()`, sem tocar em logs/comentários técnicos.

### Ficheiros alterados (top)
| Ficheiro | Strings PT-PT aplicadas |
|---|---|
| `pages/LandingParticuliers.jsx` | ~24 (reescrito completo) |
| `pages/QuoteTracking.jsx` | ~22 |
| `pages/LocalLanding.jsx` | ~15 |
| `pages/SignQuote.jsx` | ~12 |
| `pages/SmartProject.jsx` | ~8 |
| `pages/ClientPortal.jsx` | ~9 |

**Total aproximado:** ~90 strings traduzidas em 6 ficheiros públicos
críticos (landing, assinatura de orçamento, portal cliente, dashboard
Pro).

### Evidência
- `yarn build` ✅ (sem CI=1, warnings pre-existentes de
  `react-hooks/exhaustive-deps` continuam — Issue 1 do contexto).
- Grep final de termos FR puros em `pages/*.jsx` desceu de 144+ para
  ~70 ocorrências, maioritariamente em páginas Pro internas
  (QuoteScanner, Marketplace, Team, Enterprise, Comparatif,
  QuoteEditor) + comentários técnicos.

### Breaking changes
Nenhum. Campo `data-testid` preservado em todas as traduções.

### Nota residual
As ~70 ocorrências remanescentes situam-se em features Pro de
visibilidade secundária (comparativo de software, portal admin,
diálogos avançados). Devem ser abordadas em iteração futura focada em
pages específicas.

---

## Fase c — Seed `materials_pt_prices`

### O que foi feito
Script idempotente que preenche a colecção `materials_pt_prices` com 52
materiais BTP para a tool `obter_preco_material` responder sem recorrer
a Google Search.

### Ficheiros criados
- **Criado** `/app/backend/scripts/seed_materials_pt_prices.py`
- **Criado** `/app/backend/tests/test_fase_c_materials_pt_seed.py`

### Categorias cobertas (10 categorias, 52 docs)
| Categoria | N | Exemplos |
|---|---|---|
| Betão | 6 | C12/15, C16/20, C20/25, C25/30, C30/37, C35/45 |
| Aço A500NR | 7 | ∅6, ∅8, ∅10, ∅12, ∅16, ∅20, ∅25 |
| Alvenaria | 7 | Tijolo 7/11/15/22/30, bloco térmico 25/30 |
| Isolamento | 10 | XPS 3-6, EPS 3-6, lã mineral 4/6/10 |
| Revestimento | 6 | Reboco, pinturas, azulejo |
| Cobertura | 3 | Telha lusa, marselha, subtelha |
| Carpintaria | 4 | Porta interior/blindada, janela PVC/Al |
| Sanitário | 4 | Sanita suspensa, lavatório, torneira, duche |
| Pavimento | 5 | Soalho, LVT, microcimento, pedra, regularização |

### Shape do doc Mongo
```json
{
  "nome_normalizado": "betao_c25_30",
  "nome": "Betão C25/30",
  "nome_display_pt": "Betão C25/30",
  "categoria": "betao",
  "unidade": "m3",
  "preco_eur": 95.0,              // chave lida por obter_preco_material
  "preco_medio_eur": 95.0,
  "preco_min_eur": 85.0,
  "preco_max_eur": 110.0,
  "regiao_pt": "nacional",
  "regiao": "nacional",            // alias retrocompat
  "fonte_dado": "mercado_pt_2026_estimativa",
  "actualizado_em": ISODate,
  "notas_pt": "..."
}
```

**Nota:** usamos `fonte_dado` em vez de `fonte` porque esta última é
sobrescrita pelo spread da tool `obter_preco_material` com o valor
`"biblioteca_interna"`.

### Idempotência verificada
```
1ª execução: inseridos=52, actualizados=0, total colecção=52
2ª execução: inseridos=0,  actualizados=52, total colecção=52
```

### Teste
```
tests/test_fase_c_materials_pt_seed.py::test_obter_preco_material_resolve_todas_pela_biblioteca_interna PASSED
tests/test_fase_c_materials_pt_seed.py::test_materials_pt_prices_seed_tem_pelo_menos_50_docs PASSED
```
10/10 queries sintéticas resolvem via biblioteca interna (0 cai em
Google Search).

### Breaking changes
Nenhum.

---

## Fase D — Portal cliente final (link mágico PDF)

### O que foi feito
Novo canal viral: Pro cria orçamento → opcionalmente envia link seguro
ao cliente final por e-mail → cliente abre página PT-PT standalone
com PDF descarregável, sem precisar de conta ConstruPilot.

### Backend
- **Criado** `/app/backend/routes/orcamento_public_link.py`
  - `POST /api/orcamentos/{id}/public-link` (JWT, owner-only)
  - `GET /api/public/orcamentos/{token}` (sem JWT, 20/min rate limit)
  - `GET /api/public/orcamentos/{token}/pdf` (sem JWT, 20/min)
  - `GET /api/admin/btp-assistant/metrics/pricing` (debug admin)
  - Token: `mp_` + 32 bytes url-safe (`secrets.token_urlsafe`)
  - TTL: 60 dias configurável via `PUBLIC_LINK_TTL_DAYS`
  - Watermark "Gerado por ConstruPilot.pt" em cada página PDF
  - Rodapé CTA viral: "Experimente grátis →"
  - Tracking `viewed_count` + `last_viewed_at`
  - Envio automático via Resend quando `cliente_email` fornecido
- **Alterado** `/app/backend/engines/btp_assistant/tools/executors.py`
  - `exec_criar_orcamento` suporta `convidar_cliente_portal` + `cliente_email`
  - Fluxo síncrono: cria orçamento → gera link → envia e-mail (opcional)
  - Payload inclui `public_link_token`, `public_link_url`, `email_enviado`
- **Alterado** `/app/backend/engines/btp_assistant/tools/registry.py`
  - Function declaration `criar_orcamento` tem novas properties
    `cliente_email` e `convidar_cliente_portal`
- **Alterado** `/app/backend/server.py` — regista `orcamento_public_link` router

### Frontend
- **Criado** `/app/frontend/src/pages/OrcamentoPublico.jsx`
  - Página pública PT-PT (fora de ProtectedRoute)
  - Mostra orçamento formatado, totais, IVA
  - Botão "Descarregar PDF" + botão "Copiar ligação" (complementar — decisão 4a)
  - CTA viral no rodapé
  - Tratamento 404/410/429
- **Alterado** `/app/frontend/src/App.js` — rota `/orcamento-publico/:token`
- **Reescrito** `/app/frontend/src/components/btp/AcaoConfirmacao.jsx`
  - Checkbox "Enviar ligação ao cliente por e-mail" (default off, só para `criar_orcamento`)
  - Input condicional de e-mail
  - Injecta `convidar_cliente_portal` + `cliente_email` ao confirmar

### Testes
- **Criado** `/app/backend/tests/test_fase_d_portal_cliente.py` (2 testes, 7 asserts)
  - `test_fluxo_completo_portal_cliente_fase_d`: cobre todo o fluxo —
    criar link, 404 para orc inexistente, consultar público,
    404 token inválido, PDF válido com magic bytes, 410 expirado
  - `test_tool_criar_orcamento_com_convite_portal_gera_link`

### Evidência e2e real
```
POST /api/orcamentos/orc_e2e_.../public-link
→ {"token":"mp_oIFM7...","url":"https://construpilot-recon.../orcamento-publico/mp_oIFM7...",
   "expires_at_iso":"2026-12-07T18:47:01+00:00","email_enviado":false}

GET /api/public/orcamentos/mp_oIFM7.../ 
→ titulo="Fase D Smoke", total=584.25, items=1 (sem PII do owner)

GET /api/public/orcamentos/mp_oIFM7.../pdf
→ status=200, content-type=application/pdf, size=2718, magic=%PDF-1.4
```

### Breaking changes
Nenhum. Novos campos na tool `criar_orcamento` são opcionais com
default `false`/null.

---

## Resumo global

### Estado final
- **284 testes pytest passam** (281 originais + 3 novos — 2 Fase D + 1 Fase c
  consolidado em 2 funções) + 1 skipped.
- `yarn build` ✅ (zero erros, warnings pre-existentes mantidos).
- Zero regressões.
- Backend reiniciado sem erros.

### Infraestrutura adicional
- `conftest.py` global robustecido para resolver `Event loop is closed`
  do motor+anyio: propaga automaticamente a nova ref `db` aos módulos
  que importam por valor.

### Decisões implementadas
| # | Decisão | Implementação |
|---|---|---|
| 1a | `EUR_USD_RATE` fixa em `.env` | ✅ `backend/.env` + `pricing.py` |
| 2a | Só texto visível + `t()` | ✅ Páginas públicas user-facing |
| 3a | 1 doc por material, `regiao_pt="nacional"` | ✅ 52 docs semeados |
| 4a | 60 dias + envio automático + copiar link | ✅ `PUBLIC_LINK_TTL_DAYS=60` + Resend + botão UI |
| 5a | Reutilizar PDF stack existente | ✅ `reportlab 5.0.0` já instalado |

### Métricas-chave do batch
- **1ª chamada Gemini com tokens reais:** 5 656 input + 337 output + 1 067 thinking → **0.0194 €**
- **Materiais semeados:** 52 (>= 50 exigidos)
- **Strings PT-PT aplicadas:** ~90 em 6 páginas user-facing
- **PDF público:** 2 718 bytes, magic `%PDF-1.4`, watermark + CTA viral
- **Testes novos:** 3 funções, 8 asserções, 0 regressões no suite completo

### Observação final para o próximo agente
As ~70 strings FR residuais nas páginas Pro internas (QuoteScanner,
Marketplace, Enterprise, Comparatif, QuoteEditor, PlanTakeoff) devem
ser abordadas em iteração dedicada à Fase H (parte 2). O trabalho
desta sessão priorizou as páginas públicas e de alto tráfego.
