# Bug upstream Aurora — `gpt-5.6-luna` reasoning devolve texto vazio

**Data**: 2026-02 (última observação)
**Status**: Aberto, do lado Aurora — não fixável pela ConstruPilot
**Impacto**: Análises Aurora `/ask` em `mode=reasoning` falham silenciosamente (retornam HTTP 200 mas `text: ""`), forçando o nosso pipeline a devolver 503 gracioso após 3 retries.

## Sintomas

Chamada `POST /api/gateway/v1/aurora-core/company/ask` com body válido devolve:

```json
{
  "schema": "aurora.company-answer.v1",
  "text": "",
  "model": "gpt-5.6-luna",
  "route": "openai/gpt-5.6-luna",
  "mode": "reasoning",
  "external_ai_used": true,
  "deterministic": false
}
```

Observado consistentemente em:
- `POST /api/admin/aurora/phase3` (query fixa "Resume o estado desta obra…")
- `POST /api/aurora/projects/{id}/plans/analyze` (query dinâmica com dados DXF/PDF)

`external_ai_used: true` sugere que o provider OpenAI foi contactado, mas a resposta terminou vazia. Retries (3× com backoff exponencial 1s/2s/4s) não resolvem — todas as tentativas devolvem `text: ""`.

## O que o nosso lado faz corretamente

1. Contract parser (`engines/aurora_contract.py`) valida `schema` e força `text` como string.
2. `ask_with_retry` (`engines/aurora_client.py`) retenta 3× com backoff.
3. Endpoints públicos (`/api/aurora/*`) devolvem **HTTP 503 gracioso** com `aurora_meta.error = "empty_text_after_retries"`.
4. Endpoints de debug (`/api/admin/aurora/phase3`) marcam `ok: false` + `warning: "aurora_returned_empty_text"` + expõem `text_length: 0`.

## O que pedir à equipa Aurora

- Investigar porque `gpt-5.6-luna` em modo `reasoning` devolve `text: ""` sistematicamente.
- Confirmar se é config da conta / plano, budget do provider, ou bug de routing na Aurora Gateway.
- Sugestões:
  - Fallback automático para `mode=fast` quando `reasoning` devolve vazio.
  - Retornar erro estruturado (`error.code: reasoning_empty`) em vez de HTTP 200 com body vazio.
  - Expor um endpoint `/health/routing?model=gpt-5.6-luna` para diagnóstico.

## Evidência (curl reproduzível)

```bash
BASE=<REACT_APP_BACKEND_URL>
TOKEN=<admin_bearer>
curl -X POST "$BASE/api/admin/aurora/phase3" -H "Authorization: Bearer $TOKEN"
# → {"ok":false,"phase":3,"status":200,"schema":"aurora.company-answer.v1",
#     "model":"gpt-5.6-luna","route":"openai/gpt-5.6-luna","mode":"reasoning",
#     "external_ai_used":true,"text_length":0,"text_snippet":"",
#     "warning":"aurora_returned_empty_text"}
```

## Testes que ficam verdes independentemente

`tests/test_aurora_parsing.py` — 10 testes unit do contrato (passam).
`tests/test_plan_analyzer_pipeline.py` — pipeline com Aurora mockado (passa).
Os smoke tests contra Aurora ao vivo devolvem 503 gracioso e são o comportamento esperado enquanto o bug upstream não for resolvido.

---

Assim que Aurora corrigir o bug (ou tivermos routing para outro modelo com `text` não-vazio), o pipeline deve começar a devolver HTTP 200 automaticamente sem alterações do nosso lado.
