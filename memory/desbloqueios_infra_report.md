# Desbloqueios Infraestruturais — 07 Out 2026

Problemas reportados pelo `e1_tester` que impediam validação end-to-end das Fases B+C do Assistente BTP.

---

## #1 — Preview URL servia Webflow em vez da app

### Root cause
O `e1_tester` tentou abrir `https://b7f56e69-a4cc-41b2-a9ca-73526f6eaf4c.preview.emergentagent.com/`. Este subdomínio **não pertence a este pod** — é um subdomínio genérico (ou de outra sessão/pod) que o CDN Cloudflare da emergent.sh resolve para a landing institucional Webflow da própria emergent (`cf-ray: *-ATL`, `x-wf-domain: emergent.sh`, body com `data-wf-site="6a0edf12ef1a8562ed56d806"` → página "Not Found" do site institucional).

### URL correcto deste pod
```
https://construpilot-recon.preview.emergentagent.com
```
Está em `/app/frontend/.env` como `REACT_APP_BACKEND_URL`. Verificado:
- `curl -I <URL>/` → HTTP 200
- `<title>ConstruPilot — Orçamentos de Obras com IA | Portugal</title>`
- `<URL>/api/openapi.json` → HTTP 200, 460 KB

### Fix aplicado
Nenhum fix de código — era confusão de URL do tester. Documentei explicitamente em `test_credentials.md` qual é o URL correcto + como verificar deploy (ver #3).

---

## #2 — `/api/openapi.json` → HTTP 500 ❗

### Root cause
```
PydanticUserError: `TypeAdapter[typing.Annotated[ForwardRef('ChatIn'), ...]]`
is not fully defined
```

Em `/app/backend/routes/btp_assistant.py` havia `from __future__ import annotations` combinado com o decorador `@limiter.limit(...)` do `slowapi`. Com future annotations, Pydantic recebe `'ChatIn'` como string/`ForwardRef` em vez da classe real; o decorador do `limiter` reempacota a assinatura e o `TypeAdapter` do FastAPI nunca consegue chamar `model_rebuild()` para resolver o `ForwardRef`. Resultado: erro na geração do OpenAPI em arranque.

Isto afectava **todas as chamadas a `/api/openapi.json`** (usado por ferramentas de validação automática + Swagger UI quando activo).

### Fix aplicado em `/app/backend/routes/btp_assistant.py`
1. **Removido** `from __future__ import annotations`.
2. Substituídos tipos `str | None` → `Optional[str]`, `list[AttachmentIn]` → `List[AttachmentIn]`, `dict[str, Any]` → `dict`.
3. Explicitado `body: ChatIn = Body(...)` e `body: ConfirmIn = Body(...)` (defesa em profundidade contra interpretações como `Query`).
4. Reordenado `(request: Request, body: ChatIn = Body(...), user=Depends(current_user))` — `request` em primeiro lugar é requisito do `slowapi`.

### Verificação
```
$ curl -sS -o /tmp/f.json -w "HTTP %{http_code} bytes=%{size_download}\n" \
    https://construpilot-recon.preview.emergentagent.com/api/openapi.json
HTTP 200 bytes=460060

$ python3 -c "import json; d=json.load(open('/tmp/f.json')); print(d['openapi'], len(d['paths']))"
3.1.0 530
```

As novas rotas aparecem no schema:
- `/api/btp-assistant/chat`
- `/api/btp-assistant/confirm`
- `/api/btp-assistant/conversations/{conv_id}`
- `/api/btp-assistant/orcamentos/{orc_id}/excel`
- `/api/admin/btp-assistant/metrics`
- `/api/admin/btp-assistant/metrics/recent`
- `/api/admin/btp-assistant/metrics/export.csv`

---

## #3 — `test_credentials.md` ambíguo

### Root cause
O ficheiro listava `teixeira880@gmail.com` sem password numa secção isolada "Admin owner (contactável)". O tester interpretou-o erradamente como credencial principal.

As credenciais funcionais estavam lá (`info@construpilot.pt` para admin + `particular@construpilot.pt` para user) mas misturadas com notas de rotação de secrets e sem destaque do URL preview correcto.

### Fix aplicado em `/app/memory/test_credentials.md`
Reescrita completa com estrutura clara:
1. **Topo:** URL preview correcto + aviso explícito de que outros subdomínios `preview.emergentagent.com` NÃO servem este pod.
2. **Formato de autenticação:** exemplo HTTP concreto com request/response JWT.
3. **Admin:** `info@construpilot.pt` / `<redacted>` em tabela destacada.
4. **Particular:** `particular@construpilot.pt` / `<redacted>` com rate limits aplicáveis.
5. **Secção segurança:** `teixeira880@gmail.com` claramente marcado como email de contacto do owner, **não** credencial de teste.

### Verificação
```
$ curl -X POST .../api/auth/login -d '{"email":"info@construpilot.pt","password":"<redacted>"}'
HTTP 200  → {"user":{"role":"admin","plan":"premium",...}, "token":"eyJ..."}

$ curl -X POST .../api/auth/login -d '{"email":"particular@construpilot.pt","password":"<redacted>"}'
HTTP 200  → {"user":{"role":"user","account_type":"particulier",...}, "token":"eyJ..."}
```

---

## Validação final — critérios de aceitação

```
✓ [1] Preview URL serve ConstruPilot?
  title: <title>ConstruPilot — Orçamentos de Obras com IA | Portugal</title>

✓ [2] /api/openapi.json responde 200 com schema válido?
  HTTP 200 · bytes 460060 · openapi 3.1.0 · paths count: 530
  ✓ Rotas Fase A + Fase C registadas (/btp-assistant/*, /admin/btp-assistant/*)

✓ [3] Credenciais funcionam?
  admin login → HTTP 200
  particular login → HTTP 200

✓ [4] Suite backend verde?
  280 passed, 1 skipped, 6 warnings in 27.95s
```

---

## Impacto

- **Validação do e1_tester desbloqueada** — pode agora atacar `/btp-assistente` e `/admin/btp-metrics` com credenciais válidas + URL correcto + OpenAPI schema disponível para descoberta automática de rotas.
- **Zero mudanças funcionais** — só desbloqueios de infraestrutura/documentação.
- **Zero regressões**: `280/280` pytest verdes (igual à Fase C).
- **Scope preservado**: Stair Engine continua pausado, Resend intocado, Fase 1 Plans Pro intocada, i18n PT-PT mantido.
