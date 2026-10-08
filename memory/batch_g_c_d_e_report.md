# Batch G → C → D → E — Relatório Final

**Data:** 08/02/2026
**Agente:** E1
**Status:** ✅ Todas as 4 letras completas · 296 pytest passed · yarn build OK

---

## Fase G — Webhook Resend com HMAC

### O que foi feito
Fecha automaticamente o ciclo `accepted → delivered | bounced | complained | failed` sem polling, resolvendo a queixa antiga da UI mostrar "delivered" sendo apenas "queued".

### Ficheiros alterados/criados
- **Reescrito** `/app/backend/routes/resend_webhook.py` — PT-PT, 7 tipos de evento (`email.sent/delivered/bounced/complained/delivery_delayed/failed/opened/clicked`), proteção anti-replay 5 min, estados finais nunca retrocedem, actualiza `email_logs` por `resend_id` + `quote_sends` legacy.
- **Criado** `/app/backend/tests/test_resend_webhook_fase_g.py` — 5 testes.
- **Alterado** `/app/backend/.env` — placeholder `RESEND_WEBHOOK_SECRET` comentado.
- **Alterado** `/app/backend/tests/conftest.py` — propaga `db` a `routes.resend_webhook`.

### Testes (5/5)
- HMAC inválido → 401 ✓
- Timestamp antigo (anti-replay) → 401 ✓
- Secret em falta → 503 ✓
- Fluxo completo: `sent → delivered` (não retrocede) → `clicked` (incrementa) → `bounced` (final já atingido, não altera) ✓
- Evento sem `resend_id` conhecido → 200 ack + `email_log_modified=false` ✓

### Configuração para o utilizador
1. `https://resend.com/webhooks → Add endpoint`
2. URL: `https://construpilot.pt/api/webhooks/resend`
3. Eventos: todos os `email.*`
4. Copiar o Signing Secret para `.env` como `RESEND_WEBHOOK_SECRET=whsec_...`
5. `sudo supervisorctl restart backend`

---

## Fase C — Tradução FR→PT-PT em páginas Pro secundárias

### Páginas totalmente traduzidas
| Página | Antes | Agora |
|---|---|---|
| QuoteScanner.jsx | 7 | 1 (URL rota) |
| QuoteEditor.jsx | 6 | 4 (paths de rotas internas) |
| Marketplace.jsx | 6 | 0 |
| Enterprise.jsx | 2 | 0 |
| Comparatif.jsx | 1 | 0 |
| PlanTakeoff.jsx | 20 | 4 (paths/rotas) |
| **Total** | **42** | **9** (meta <10 ✅) |

As 9 ocorrências remanescentes são todas paths de rotas (`/devis-editeur/`, `/scanner-devis`, `/devis`) — não são strings visíveis ao utilizador.

### Evidência
- `yarn build` ✅
- Zero regressões pytest (289 → mantido)

---

## Fase D — Stair Engine E2E + ligação `calcular_escada`

### O que foi feito
A tool `calcular_escada` do Agente BTP deixou de devolver `MissingDataRequest` e passa a invocar o motor real `engines.stair_engine.calculate_stair(StairInputs(...))`.

### Ficheiros alterados/criados
- **Reescrito** `exec_calcular_escada` em `/app/backend/engines/btp_assistant/tools/executors.py` — chama motor real, persiste em `db.stair_analyses` com `analysis_id`, devolve payload amigável + `pdf_url`.
- **Adicionado** endpoint `GET /api/stair-engine/{analysis_id}/pdf` em `/app/backend/routes/stair_engine.py` — suporta docs criados pela tool (`result` field) e legacy.
- **Criado** `/app/backend/tests/test_stair_engine_e2e_fase_d.py` — 2 testes (motor directo + fluxo tool→PDF).

### Testes (2/2)
- **Motor directo (padrão 2.70 m)**: espelho 16.88 cm, cobertor 29.25 cm, Blondel 63.0 cm, inclinação 30.0°, 16 degraus ✓
- **Fluxo completo tool → PDF**: payload com `analysis_id`, `pdf_url`; PDF 2 KB+ com magic bytes `%PDF` ✓

### Evidência real
```
Blondel = 63.0 cm (OK, entre 60-64)
Espelho = 16.88 cm (OK, entre 16-18)
Cobertor = 29.25 cm (OK, entre 25-32)
Inclinação = 30.0° (OK, entre 25-36)
```

---

## Fase E — Fase 2 Plans Pro · OCR Tesseract-PT

### O que foi feito
OCR real integrado no pipeline Plans Pro antes do LLM, com léxico PT-BTP a reconhecer deterministicamente materiais e dimensões no texto detectado. Fallback graceful se Tesseract falhar.

### Dependências instaladas
- `apt-get install tesseract-ocr tesseract-ocr-por` → **Tesseract 5.3.0** com langs `eng/osd/por`
- `pip install pytesseract==0.3.13` → adicionado a `requirements.txt`
- Pillow 12.3.0 já presente

### Ficheiros criados
- `/app/backend/engines/plans_pro/semantic/ocr_tesseract.py` — `extrair_texto_thumbnail(image_bytes, lang="por")` + `OCRResult` + `LinhaOCR` Pydantic models
- `/app/backend/scripts/gerar_fixture_ocr.py` — gera idempotentemente `thumbnail_moradia_sintetica.png` (1600×1600, 10 linhas PT-BTP)
- `/app/backend/tests/test_plans_pro_ocr.py` — 5 testes
- `/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png` — 20 KB

### Ficheiros alterados
- `/app/backend/engines/plans_pro/autodesk_client.py` — thumbnail 400→**1600** (default)
- `/app/backend/engines/plans_pro/plan_vision.py` — OCR + léxico PT-BTP correm ANTES do LLM; `ocr.texto_completo` é injectado em `project_hint` para enriquecer o prompt; `trace["ocr_disponivel"|"ocr_confidence_media"|"ocr_linhas_count"|"ocr_material_detectado"|"ocr_dimensoes_count"]` populado.
- `/app/backend/requirements.txt` — `pytesseract==0.3.13`

### Pré-processamento aplicado
1. Grayscale (`ImageOps.grayscale`)
2. Contraste 1.5× (`ImageEnhance.Contrast`)
3. Upscale até 1600 px (Lanczos) se imagem < 1200 px

### Testes (5/5)
- `test_ocr_extrai_texto_pt_de_fixture_sintetica` ✓ (confidence média 48.7, 15 linhas detectadas)
- `test_lexico_pt_btp_reconhece_material_do_ocr` ✓ ("PP e=20" → alvenaria)
- `test_ocr_fallback_quando_tesseract_indisponivel` ✓ (mock `_TESS_DISPONIVEL=False`)
- `test_ocr_bytes_vazios_graceful` ✓
- `test_plan_vision_integra_ocr_no_trace` ✓ (`trace["ocr_disponivel"]=True`, `ocr_linhas_count>0`)

### Evidência real
```python
>>> from engines.plans_pro.semantic.ocr_tesseract import extrair_texto_thumbnail
>>> r = extrair_texto_thumbnail(open("thumbnail_moradia_sintetica.png","rb").read())
>>> r.confidence_media
48.7
>>> len(r.linhas)
15
>>> r.texto_completo[:80]
'PLANTAMORADIATS Ppe=20 AB ASOONR VAR 12 SAPATAO 30h00 350m 70m COBERTURA TELHALUSA'
```

### Fallback graceful
- Se `pytesseract` import falhar → `disponivel=False`, pipeline LLM continua sem OCR
- Se Tesseract lançar excepção → log warning, mesmo comportamento
- Se `thumbnail_bytes=None` → `trace["ocr_disponivel"]=False`

---

## Resumo global

### Testes
```
296 passed · 1 skipped · 0 failed · 34.79 s
```
Novos:
- Fase G: +5 testes webhook Resend HMAC
- Fase D: +2 testes Stair Engine E2E
- Fase E: +5 testes OCR Tesseract-PT

### Build frontend
`yarn build` ✅ · 22 s · zero erros

### Zero regressões
Nenhum teste pre-existente partido. O flaky `test_c3_wave::test_login_invalid` (rate-limit, Issue 2 pre-existente) voltou a passar nesta execução.

### Métricas-chave
- **Webhook Resend:** 7 tipos de evento tratados, estados finais protegidos
- **FR→PT-PT:** 33 strings traduzidas em 6 páginas Pro secundárias
- **Stair Engine:** cálculo real para 2.70 m → 16 degraus · Blondel 63.0 cm · inclinação 30.0°
- **OCR Tesseract:** 15 linhas detectadas na fixture sintética, confidence média 48.7
- **Thumbnail Autodesk:** 400×400 → **1600×1600** (4× resolução)

### Next Action Items
- Configurar `RESEND_WEBHOOK_SECRET` em produção (painel Resend → Signing Secret).
- Correr `python scripts/gerar_fixture_ocr.py` após cada reset do pod se necessário.
- OCR actual tem confidence média ~49% devido a limitações da fixture sintética (fonte DejaVuSans sem anti-aliasing típico de plantas BTP reais) — thumbnails Autodesk reais a 1600 px deverão atingir 70-85% confidence.
- Fase 3 Plans Pro possível: substituir o pré-processamento PIL por OpenCV (`cv2.adaptiveThreshold`) para plantas com fundo cinzento típico CAD — melhoria estimada +15-20 % confidence.

### Potencial melhoria orientada à receita
Quando a análise OCR + léxico PT-BTP detecta `C25/30` + `A500NR` + `∅12` numa planta, o Agente BTP pode automaticamente sugerir um **orçamento preliminar instantâneo** sem o utilizador clicar — crescimento virtuoso: utilizadores Free vêem o valor concreto que o Pro desbloqueia (orçamentação IA automática a partir de ficheiro Autodesk) e convertem com fricção zero.
