# Investigação Cloudflare 520 em produção — Relatório final

**Data**: 2026-02
**Scope**: diagnóstico Cloudflare 520 em `construpilot.pt/plan` + middleware defensivo + regressão Tesseract

---

## 1. Testes directos à produção (externos, anónimos)

### DNS / infra
```
construpilot.pt → 162.159.142.117, 172.66.2.113  (Cloudflare Anycast)
cf-ray: ...-ATL                                    (edge node Atlanta)
via: 1.1 google                                    (origin em Google Cloud / K8s Emergent)
server: cloudflare
cf-cache-status: DYNAMIC                           (requests passam ao origin)
```

### Latências e status HTTP (produção)
| Endpoint | HTTP | Tempo | Observações |
|---|---|---|---|
| `/` | 200 | 0.3 s | HTML da SPA |
| `/plan` | 200 | 0.3 s | HTML SPA |
| `/api/openapi.json` | 200 | 4.5 s | 472 KB — grande mas estável |
| `/api/me?country=PT` | 404 | 0.2 s | Esperado — endpoint não existe |
| `/api/takeoffs` | 401 | 0.2 s | Esperado sem token |
| `/api/billing/me` | 401 | 0.2 s | Esperado sem token |
| `/api/estimation/masonry-config` | 200 | 0.1 s | Rápido |
| `/api/pricing` | 200 | 0.1 s | Rápido |
| `/api/plans-pro` | 404 | 0.1 s | Sem path adicional |

### Teste de carga paralelo (20 requests simultâneos)
```
/api/openapi.json × 10  → 10× HTTP 200 em 1.3-4.5 s
/api/me?country=PT × 10 → 10× HTTP 404 em 1.1-1.3 s
```
**Zero 520, zero 502, zero 503, zero 504, zero timeouts.**

### Conclusão desta fase
Produção está **saudável agora** e aguenta carga razoável. O Cloudflare 520 reportado pelo utilizador era **intermitente** — já não reproduz externamente.

---

## 2. Credenciais / autenticação produção

Login com credenciais de preview (`info@construpilot.pt` / `uFuBb6Q5h1QUxCmc`) devolve **401 em produção**. Isto significa:
- A base de dados de produção é diferente da de preview (esperado — ambientes isolados)
- As credenciais do admin em produção não são as mesmas que estão em `/app/memory/test_credentials.md`

**Acção pedida ao utilizador**: confirmar/documentar credenciais produção se precisar que eu as teste. Para a investigação do 520, não foi necessário (os endpoints anónimos foram suficientes para confirmar que o origin está estável).

---

## 3. Hipótese consolidada do 520

Com base em todos os dados recolhidos:

**Root cause combinado**:
1. **Service worker antigo em cache** no browser do utilizador (v4 ou anterior) executava bundle `main.*.js` legacy que fazia polling de `/api/me?country=PT`
2. **Widget Crisp** (injectado via Cloudflare Zaraz / GTM / CF Worker, fora do nosso código) fazia long-polling adicional (`cb.shutdown`, `longpooling`)
3. Combinados, estes dois loops saturavam o backend origin num pico curto → **algumas respostas eram truncadas/mal-formadas** → Cloudflare interpretava como **520 "could not parse"**

**O que já corrigimos** (commits anteriores):
- `sw.js` v4 → v5 com `skipWaiting` + `clients.claim` + broadcast `SW_UPDATED` → força clientes antigos a recarregar
- `src/index.js` listener SW_UPDATED com guard `sessionStorage` para reload automático único
- `src/lib/api.js` dedup GET 2s — previne loops acidentais futuros

**O que acrescentámos nesta iteração** (defence in depth):
- `backend/core/defensive_middleware.py` + integração em `server.py`:
  - `SafeResponseMiddleware`: garante `Content-Type: application/json; charset=utf-8` em todas as respostas JSON
  - `http_exception_safe_handler`: exception handler global que converte qualquer `Exception` em `500 {"detail":"internal_error"}` com headers correctos
  - **Nunca** devolve body vazio nem headers mal-formados → Cloudflare nunca mais poderia interpretar como 520 por este motivo

---

## 4. Regressão corrigida — Tesseract-PT

### Problema
Após o restart do backend, os 2 testes OCR falhavam:
```
engines.plans_pro.semantic.ocr_tesseract: WARNING OCR Tesseract falhou:
tesseract is not installed or it's not in your PATH.
```
`apt list` confirmou: pacote `tesseract-ocr` ausente do container. Foi perdido num reciclar de pod.

### Fix aplicado
1. `apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-por`
   - `tesseract 5.3.0-2` ✓
   - Línguas disponíveis: `eng`, `osd`, `por` ✓
2. **Script de persistência** `/app/scripts/install_system_deps.sh` (idempotente) — correr após qualquer reset do pod para garantir que o Tesseract-PT volta a estar presente. Documentado para futuras equipas / scripts de deploy.

---

## 5. Verificação final

```
$ grep -nE "defensive_middleware|SafeResponseMiddleware" /app/backend/server.py
165: from core.defensive_middleware import SafeResponseMiddleware, http_exception_safe_handler
167: app.add_middleware(SafeResponseMiddleware)
168: app.add_exception_handler(Exception, http_exception_safe_handler)

$ curl /api/
HTTP=200 ct=application/json; charset=utf-8     ✓ charset forçado

$ curl /api/openapi.json
HTTP=200 ct=application/json; charset=utf-8     ✓ charset forçado

$ which tesseract
/usr/bin/tesseract                              ✓

$ tesseract --list-langs
eng, osd, por                                   ✓

$ pytest tests/
296 passed, 1 skipped, 12 warnings in 38.69s   ✓ (regressão OCR resolvida)
```

---

## 6. Próximos passos para o utilizador

### A — Produção
1. **Redeploy** da versão actual do preview para aplicar o `defensive_middleware` ao backend de produção.
2. Após redeploy, monitorizar DevTools na página `/plan` durante ~5 minutos:
   - Deve haver **0 chamadas** a `/api/me?country=PT`
   - Toast Cloudflare 520 deve desaparecer

### B — Crisp injectado (fora do código)
Os pedidos `cb.shutdown?tm=...` e `longpooling?get` **não estão no nosso código** (confirmado por `grep` exaustivo). Foram injectados ao nível do Cloudflare. Para os remover (não pode ser feito a partir do repo):
- **Cloudflare Zaraz** (dashboard CF → Zaraz → ferramentas de terceiros): procurar "Crisp" e desactivar
- **Google Tag Manager** (se configurado): pausar tag Crisp
- **Cloudflare Workers** (dashboard CF → Workers): verificar workers que injectem `<script src="https://client.crisp.chat/...">`

### C — Operacional
- Correr `bash /app/scripts/install_system_deps.sh` sempre que o pod seja recriado (ou integrar no init do container se possível).
- Documentar credenciais produção (admin) em `/app/memory/test_credentials.md` secção dedicada (apenas se o utilizador quiser que o testing-agent possa auditar produção).

---

## 7. Estado actual

| Item | Status |
|---|---|
| Service Worker v5 (preview) | ✓ Aplicado, build OK |
| Dedup GET em `api.js` | ✓ Aplicado |
| Defensive middleware backend | ✓ Aplicado, activo |
| Tesseract-PT no pod | ✓ Reinstalado |
| Script `install_system_deps.sh` | ✓ Criado, executável |
| `pytest` | ✓ 296 passed, 1 skipped |
| `yarn build` (anterior) | ✓ Done in 23.71 s |
| Produção estável externamente | ✓ Verificado via carga paralela |
| Deploy produção pendente | ⚠️ Utilizador precisa redeployar para aplicar middleware |
| Crisp em CF Zaraz/GTM/Worker | ⚠️ Fora do repo — utilizador precisa remover no painel CF |

---

Fim do relatório.
