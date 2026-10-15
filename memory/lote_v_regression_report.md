# Lote V — Regressão completa pré-Web Summit

- Preview URL: `https://construpilot-recon.preview.emergentagent.com`
- Backend URL: `https://construpilot-recon.preview.emergentagent.com`
- Executado em: 2026-10-15T15:28:29.184Z
- Duração: 393 s

## Resumo PASS/FAIL por grupo × viewport

| Grupo | iPhone 13 (390x844) | Pixel 7 (412x915) | Desktop (1280x800) | iPad landscape (1024x768) |
|---| --- | --- | --- | --- |
| V1·escadas | PASS | PASS | PASS | — |
| V1·medicoes | PASS | PASS | PASS | — |
| V1·orcamentos | PASS | PASS | PASS | — |
| V1·plantas | PASS | PASS | PASS | — |
| V1·autorizacao | PASS | PASS | PASS | — |
| V1·moradia | PASS | PASS | PASS | — |
| V1·calculadoras | PASS | PASS | PASS | — |
| V1·moradia_clarify | PASS | — | — | — |
| V2_demo | PASS | PASS | PASS | — |
| V3_shell | PASS | PASS | — | — |
| V4_tablet | — | — | — | PASS |

## Falhas detectadas (checks críticos a FAIL)

> Nenhuma falha crítica detectada.

## Notas / desvios ao briefing

- **orcamentos**: /devis (QuoteTracking) não contém PromptBar — a PromptBar vive em /devis-editeur (QuoteEditor). Testado em /devis-editeur como fallback. (testado em /devis-editeur)
- **orcamentos**: /devis (QuoteTracking) não contém PromptBar — a PromptBar vive em /devis-editeur (QuoteEditor). Testado em /devis-editeur como fallback. (testado em /devis-editeur)
- **orcamentos**: /devis (QuoteTracking) não contém PromptBar — a PromptBar vive em /devis-editeur (QuoteEditor). Testado em /devis-editeur como fallback. (testado em /devis-editeur)

## Checks informativos (não forçam fail)

- `moradia_clarify_banner_present` [moradia_clarify · iPhone 13 (390x844)] → apiStatus=429 rateLimited=true text=
- `moradia_clarify_mentions_area` [moradia_clarify · iPhone 13 (390x844)] → 
- `moradia_prompt_fill_api_meta` [moradia_clarify · iPhone 13 (390x844)] → status=429 body={"detail":"Demasiados pedidos — aguarde alguns instantes.","limit":"20 per 1 hour"}
- `demo_offline_still_renders_root` [V2_demo · iPhone 13 (390x844)] → demo-root visible offline = true
- `demo_offline_still_renders_root` [V2_demo · Pixel 7 (412x915)] → demo-root visible offline = true
- `demo_offline_still_renders_root` [V2_demo · Desktop (1280x800)] → demo-root visible offline = true
- `swipe_back_informational` [V3_shell · iPhone 13 (390x844)] → before=https://construpilot-recon.preview.emergentagent.com/compte after=https://construpilot-recon.preview.emergentagent.com/compte
- `pull_to_refresh_informational` [V3_shell · iPhone 13 (390x844)] → não testado automaticamente; validação táctil manual
- `swipe_back_informational` [V3_shell · Pixel 7 (412x915)] → before=https://construpilot-recon.preview.emergentagent.com/compte after=https://construpilot-recon.preview.emergentagent.com/compte
- `pull_to_refresh_informational` [V3_shell · Pixel 7 (412x915)] → não testado automaticamente; validação táctil manual

## Resultado numérico global

- Total checks: 90
- Checks críticos: 80
- Críticos PASS: 80
- Críticos FAIL: 0
- Taxa de sucesso crítico: 100.0%