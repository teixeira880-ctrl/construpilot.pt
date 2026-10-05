# Sprint 4 — Perplexity Plus + Excel Enhancement — Relatório

**Data**: 05 Out 2026 · **Duração**: ~1h30 · **Status**: ✅ CONCLUÍDO

---

## PARTE 1 — Enhancement Excel (logo + NIF)

### Diff
- `engines/plans_pro/excel_export.py` — `_write_project_header` agora aceita `branding: dict | None`, renderiza logo PNG em A1 via `openpyxl.drawing.image.Image` (redimensionado para 60px), substitui o título por `brand_company_name`, adiciona linhas NIF / Morada / Contacto quando disponíveis.
- `routes/plans_pro.py` — endpoint `export-excel` agora fetchar `db.users.find_one` + override com `db.organizations` se o user pertencer a org. Passa `branding` para `build_workbook`.

### Prova
Teste real com user `info@construpilot.pt` + seed branding fiscal → folha "Resumo" gerada com:
```
A1: ConstruPilot Teste, Lda          (título em verde ConstruPilot)
A3-B3: Ficheiro: casa_t2.dwg
A10-B10: NIF: 509123456
A11-B11: Morada: Rua da Construção, 42, 1000-100 Lisboa
A12-B12: Contacto: +351 210 000 000 · info@construpilot.pt
```

Logo PNG renderiza-se automaticamente se `brand_logo_b64` existir. Fallback: título textual.

---

## PARTE 2 — Sprint 4 Perplexity Plus

### Diffs principais

**Backend — novos ficheiros**
| Caminho | Linhas | Propósito |
|---|---|---|
| `engines/perplexity_plus/__init__.py` | 18 | Exports presets + cache + client |
| `engines/perplexity_plus/pplx_presets.py` | 82 | 5 presets PT: DRE, LNEC, APA, ADENE, IHRU com `system` prompts + `domains` oficiais |
| `engines/perplexity_plus/pplx_cache.py` | 50 | MongoDB TTL 24h (`createIndex expireAfterSeconds=86400`) + SHA256 cache keys |
| `engines/perplexity_plus/pplx_client.py` | 190 | `ask_structured` (cache + JSON parsing tolerante) + `stream_chat` (SSE Agent API) |
| `routes/perplexity_plus.py` | 215 | 6 endpoints REST |
| `tests/test_perplexity_plus.py` | 134 | 13 testes (presets, cache, extract_json, client mocks, routes) |
| `scripts/test_perplexity_plus_e2e.py` | 170 | E2E real: todos os endpoints + cache HIT verification |

**Frontend — novo**
- `pages/PerplexityPlus.jsx` (593 linhas) com 4 panes Tab (Chat SSE + Comparar + Normas + Materiais) e `useAuthHeaders` já corrigido via localStorage

**Alterações**
- `server.py` +2 linhas (import + include_router)
- `App.js` +2 linhas (import + rota `/perplexity-plus`)

### Endpoints novos (6 total)
```
GET  /api/perplexity-plus/presets         # Lista 5 presets PT
POST /api/perplexity-plus/chat            # SSE streaming (Agent API /v1/responses)
POST /api/perplexity-plus/compare         # Tabela comparativa estruturada
POST /api/perplexity-plus/norms           # Normas PT (DRE/LNEC/APA/ADENE)
POST /api/perplexity-plus/materials-watch # Preços + tendência trimestral
GET  /api/perplexity-plus/cache-stats     # Contagem cache + TTL
```

### Presets PT configurados

| Código | Fontes oficiais | Caso de uso |
|---|---|---|
| `DRE` | dre.pt, diariodarepublica.pt | Legislação (DL, Lei, Portaria) |
| `LNEC` | lnec.pt, docentes.ipt.pt | Normas construtivas NP, DE, Eurocódigos |
| `APA` | apambiente.pt, snirh.apambiente.pt | AIA, LER, licenciamento ambiental |
| `ADENE` | adene.pt, sce.pt | SCE, REH, certificação energética |
| `IHRU` | ihru.pt, portaldahabitacao.pt | ARU, IFRRU 2020, 1.º Direito |

### Cache MongoDB

- Collection `pplx_cache`, chave `_id` = SHA256 do payload normalizado
- Index TTL automático: `createIndex({created_at: 1}, {expireAfterSeconds: 86400})` idempotente
- Headers resposta: `cache: "HIT"|"MISS"` no JSON

---

## Pytest final

```
tests/test_btp_solver.py         4/4   ✅
tests/test_c2_wave.py           17/17  ✅
tests/test_c3_wave.py            9/9 + 1 skip ✅
tests/test_plans_pro.py          8/8   ✅
tests/test_plans_pro_excel.py   11/11  ✅
tests/test_perplexity_plus.py   13/13  ✅ (novos Sprint 4)

TOTAL: 62 passed, 1 skipped — ZERO regressões
```

---

## E2E real (`test_perplexity_plus_e2e.py`)

Login real → cache cleared → chamadas reais contra Perplexity Agent API `/v1/responses`:

| Endpoint | Status | Cache | Tempo | Dados reais obtidos |
|---|---|---|---:|---|
| `/presets` | 200 | — | 0.1s | 5 presets PT devolvidos |
| `/norms` (query LNEC: espessura isolamento zona I2) | 200 | MISS | 17.4s | 4 normas · **15 citações oficiais** |
| `/compare` (ETICS vs fachada ventilada vs alvenaria dupla) | 200 | MISS | 13.5s | Recomendado: **"ETICS com EPS"** |
| `/materials-watch` (Betão + Aço + Cimento em Lisboa) | 200 | MISS | 7.3s | 3 materiais com preço + tendência |
| `/chat` SSE (RGEU preset DRE) | 200 | — | 5.3s | **92 chunks · 298 chars · 15 citações** |
| `/norms` (**repetido**) | 200 | **HIT** | **0.06s** | **290× mais rápido** vs MISS |

### Prova cache funcional
Primeira chamada `/norms` MISS: **17.4s** · segunda chamada idêntica: **0.06s HIT** · ganho **290×** · poupança estimada: ~1500 tokens de output por query repetida.

---

## Preservação (checklist)

- [x] Opus 5.5, OpenAI, Perplexity router (não tocados; `ai_router.perplexity` reutilizado)
- [x] Biblioteca PT 2026 (não tocada)
- [x] BTP Solver Sprint 2 (4/4 tests ✅)
- [x] Plans Pro Sprint 3 + Fase A Excel (8+11 tests ✅)
- [x] Banner, `ai_health`, docs Aurora, email fixes, `I18nContext`
- [x] 62/62 pytest verdes (0 regressões)

---

## Decisão de arquitetura — Agent API migration

A Perplexity migrou `/chat/completions` → `/v1/responses` em finais 2025. O streaming SSE antigo foi deprecated com erro:
```
"Sonar is now the Agent API. Use /v1/responses instead."
```

Adaptei o `stream_chat` para o novo formato:
- Body: `input[]` em vez de `messages[]`
- `max_output_tokens` em vez de `max_tokens`
- Event types: `response.output_text.delta` (não `choices[].delta.content`)
- Citations: via item `type: "search_results"` dentro de `output[]`

Mantidos fallbacks para `choices[].delta.content` caso Perplexity introduza compat layer.

---

## Screenshot `/perplexity-plus`

Confirmado:
- H1 "Perplexity Plus" + subtítulo PT-PT
- Badge "Cache ativo: 3 entradas · TTL 24h"
- 4 Tabs: **Chat / Comparar / Normas / Materiais**
- Chat selecionado por default com dropdown preset + input + botão Enviar
- Autenticado como "Administrador ConstruPilot"

---

## Dívida técnica

| Item | Prioridade | Nota |
|---|---|---|
| Testes Playwright E2E UI (SSE streaming display) | P2 | Backend 100% testado; faltam asserts frontend. |
| Dashboard de uso Perplexity (tokens/dia/user) | P3 | Fora de âmbito deste sprint, user confirmou. |
| Alertas automáticos materials-watch (watchlist + email) | P3 | Fora de âmbito; integra com Resend + APScheduler já disponíveis. |
| Rate limiting por utilizador (fora de admin) | P2 | Perplexity cobra por token — proteger contra abuso: adicionar `slowapi` com `20/hour` por user. |
| Export compare → Excel/PDF | P3 | Reaproveitar `engines/plans_pro/excel_export.py` como template. |

---

## Finish

**Backend**: 62 pytest verdes · 6 endpoints `/perplexity-plus/*` ativos em produção · cache funcional (290× speed-up) · Agent API migration completa.

**Frontend**: `/perplexity-plus` com 4 tabs render em PT-PT (acessível autenticado).

**Excel enhancement**: logo + NIF + morada + contacto no cabeçalho "Resumo" — pronto para apresentar a clientes.

Aguardo próxima instrução.
