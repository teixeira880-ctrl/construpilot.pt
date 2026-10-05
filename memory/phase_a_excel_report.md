# Fase A — Export Excel Plans Pro — Relatório

**Data**: 05 Out 2026  
**Duração**: ~45 min  
**Status**: ✅ CONCLUÍDO

---

## 1. Diffs principais

### Backend — novo
| Caminho | Linhas | Propósito |
|---|---|---|
| `engines/plans_pro/excel_export.py` | 263 | Workbook openpyxl 3 folhas (Resumo + Orçamento + Quantidades) com fórmulas Excel, IVA PT configurável (23/22/16/6/0), estilo ConstruPilot |
| `tests/test_plans_pro_excel.py` | 128 | 11 testes unitários (IVA rates, totais matemáticos, estrutura, headers PT, fórmulas) |
| `scripts/test_excel_export_e2e.py` | 115 | E2E: login real → seed plano fake → chama endpoint em 3 regimes IVA → valida xlsx |

### Backend — alterações
- `routes/plans_pro.py`: `+45` linhas (endpoint `GET /{plan_id}/export-excel?iva_rate=…` + imports)

### Frontend — alteração
- `pages/PlansPro.jsx`: `+65` linhas
  - Import `Select` do shadcn
  - State `exporting` + `ivaRate` (default 23)
  - Função `handleExportExcel()` com blob download + filename do `Content-Disposition`
  - UI: dropdown IVA (5 opções PT) + botão "Exportar para Excel" (variant outline) ao lado do "Analisar com IA"
  - **Fix bug**: `useAuthHeaders()` lia `useAuth().token` (inexistente); passa a ler `localStorage.getItem('construpilot_token')` diretamente

---

## 2. Endpoint novo

```
GET /api/plans-pro/{plan_id}/export-excel?iva_rate=23
```

Response headers úteis:
```
Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="orcamento_<stem>_ORC-YYYYMMDD-HHMM-<id6>.xlsx"
X-Orc-Numero: ORC-20261005-1252-abc123
X-Orc-Total-HT: 9500.0
X-Orc-Total-TTC: 11685.0
Cache-Control: private, no-store
```

**Total openapi.json endpoints `/plans-pro/*`**: **8** (config, upload, status, viewer-token, analyze, analysis, export-excel, history/list).

---

## 3. Estrutura do Excel gerado

3 folhas:

### Folha "Resumo"
Cabeçalho projeto (nome ficheiro, formato, nº orçamento auto, data UTC, regime IVA, modelo IA, URN truncado) + Totais HT/IVA/TTC em destaque + contagens + resumo técnico IA + lista de normas aplicáveis.

### Folha "Orçamento" (fórmulas reais Excel)
| Col | Cabeçalho PT |
|---|---|
| A | Designação |
| B | Un |
| C | Quantidade |
| D | Preço Unit. (€) |
| E | Total s/ IVA = `=IFERROR(C*D,0)` |
| F | IVA (xx%) = `=E*rate` |
| G | Total c/ IVA = `=E+F` |
| H | Ref. Biblioteca PT |
| I | Observações |

Linha TOTAL com `=SUM(E2:En)`, `=SUM(F2:Fn)`, `=SUM(G2:Gn)`, highlight amarelo + legenda IVA.

Formato numérico: `#,##0.00" €"` (locale do Excel converte vírgula/ponto conforme sistema do utilizador).

### Folha "Quantidades"
Ouvrage · N.º entidades · Fonte (categorias/layers) · Layers principais.

---

## 4. Taxas IVA PT suportadas

| Código | Taxa | Label |
|---|---|---|
| `23` | 23% | Continente (regime geral) — default |
| `22` | 22% | Açores (regime geral) |
| `16` | 16% | Madeira (regime geral) |
| `6`  | 6%  | Reabilitação urbana (ARU) / reforma pensionistas |
| `0`  | 0%  | Isento (ex.: exportação) |

Base legal: DL n.º 102/2008 + Lei do OE. Validação server-side em `IVA_RATES_PT` — 400 Bad Request se inválido.

---

## 5. Linhas Excel reais (exemplo IVA 23% com 3 ouvrages)

```
Folha "Orçamento":
  A1: Designação                       | B1: Un          | C1: Quantidade
  D1: Preço Unit. (€)                  | E1: Total s/ IVA | F1: IVA (23%)
  G1: Total c/ IVA                     | H1: Ref. Biblioteca PT | I1: Observações
  A2: Fundações C25/30                 | B2: m³          | C2: 15
  D2: 180                              | E2: =IFERROR(C2*D2,0) → 2700
  F2: =E2*0.23 → 621                   | G2: =E2+F2 → 3321
  A3: Laje térrea massame armado       | B3: m²          | C3: 80, D3: 45
  A4: Alvenaria tijolo 15cm            | B4: m²          | C4: 100, D4: 32
  D6: TOTAL | E6: =SUM(E2:E4) → 9500   | F6: =SUM(F2:F4) → 2185 | G6: =SUM(G2:G4) → 11685
  A8: IVA 23% — Continente (regime geral)

Folha "Resumo":
  A1: ConstruPilot — Orçamento preliminar
  B3: e2e_casa.dwg
  B4: DWG
  B6: ORC-20261005-1252-_excel
  B7: 05/10/2026 12:49 UTC
  B8: IVA 23% — Continente (regime geral)
```

---

## 6. Pytest

```
tests/test_btp_solver.py         4/4   ✅
tests/test_c2_wave.py           17/17  ✅
tests/test_c3_wave.py            9/9 (+1 skip pré-existente) ✅
tests/test_plans_pro.py          8/8   ✅
tests/test_plans_pro_excel.py   11/11  ✅ (novos Fase A)

TOTAL: 49 passed, 1 skipped — ZERO regressões
```

---

## 7. E2E real (`test_excel_export_e2e.py`)

Login real → seed MongoDB → chamada endpoint em 3 regimes IVA → validação xlsx:

| IVA | Size (B) | Total HT (€) | Total c/ IVA (€) | Nº orçamento |
|---|---:|---:|---:|---|
| 23% Continente | 7 872 | 9 500,00 | 11 685,00 | ORC-20261005-1249-_excel |
| 6% ARU / Reabilitação | 7 901 | 9 500,00 | 10 070,00 | — |
| 22% Açores | 7 868 | 9 500,00 | 11 590,00 | — |

Matemática verificada: 9500 × 1,23 = 11 685 ✅ · 9500 × 1,06 = 10 070 ✅ · 9500 × 1,22 = 11 590 ✅

Download real via browser (Playwright `expect_download`): ficheiro `orcamento_e2e_casa_ORC-20261005-1252-_excel.xlsx` (7 870 bytes) + toast "Excel exportado (IVA 23%)" visível.

---

## 8. Preservação (checklist)

- [x] Opus 5.5, OpenAI, Perplexity (não tocados)
- [x] Biblioteca PT 2026 referenciada no cabeçalho Excel
- [x] i18n `pt_auto.json` + `I18nContext` intactos
- [x] Banner, `ai_health`, `/docs/aurora` sem alterações
- [x] Sprints 2 + 3 (BTP Solver + Autodesk APS) intactos
- [x] `emailer.py`, `auth.py`, admin secrets whitelist preservados
- [x] 49/49 pytest verdes

---

## 9. Dívida técnica / melhorias futuras

| Item | Prioridade | Nota |
|---|---|---|
| Branding: incluir logo ConstruPilot (PNG) no cabeçalho A1 Resumo | P2 | openpyxl suporta `openpyxl.drawing.image.Image`. Logo em `/app/frontend/public/`. ~15 min. |
| Ref. Biblioteca PT por ouvrage | P2 | Hoje coluna vazia. Depende do `synthesis.ouvrages[].ref_biblioteca` (ainda não emitido pelo prompt Claude). Melhorar prompt para incluir `ref` + cross-match com `/api/library`. |
| Dados cliente/empresa (NIF, morada) no cabeçalho | P2 | Buscar de `db.companies` do user. Já há endpoint `/api/company/me`. ~20 min. |
| PDF export complementar | P3 | Reusar o mesmo pipeline via `openpyxl → PDF` ou gerar via `reportlab`. |
| CSV lite para integração ERP (Primavera, PHC) | P3 | Formato simples: `designacao;unidade;quantidade;pu;total_ht` com `;` separador PT. |
| Testes Playwright E2E download real | P2 | Já validado manualmente nesta sessão; falta automatizar no CI. |

---

## 10. Como o utilizador usa a feature

1. Entrar em `/plans-pro` com conta autenticada
2. Fazer upload DWG/RVT/IFC → aguardar `success`
3. Clicar em **"Analisar com IA"** → Claude Opus 5.5 produz ouvrages PT
4. Escolher o regime IVA no dropdown (Continente 23% / Açores 22% / Madeira 16% / ARU 6%)
5. Clicar em **"Exportar para Excel"** → download automático
6. Abrir `.xlsx` no Excel/LibreOffice/Google Sheets: todas as fórmulas são **reais** (não valores fixos), empreiteiro pode ajustar preços e totais recalculam-se automaticamente

---

## 11. Próximo

Aguardar confirmação do utilizador para arrancar **Fase B — Sprint 4 Perplexity Plus** (4 endpoints com presets PT: DRE, LNEC, APA, materials-watch).
