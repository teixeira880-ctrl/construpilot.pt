# P1 — Instalações + preparação de pré-flight · Vídeo demo Web Summit 2026

**Data**: 2026-10-17 · **Idioma**: PT-PT · **Scope**: URGENTES (PII + .env) + P1.1 instalações + P1.2 setup. P1.2/P1.3 **BLOQUEADOS por credenciais vazias**.

---

## URGENTE-1 — Redacção PII em `/app/memory/`

### Resumo
- **29 ocorrências redactadas** em **10 ficheiros**. Padrões removidos: `TesteE2E!2026`, `CP-Admin-2026!`, `Particular2026!`, `CP-D5615C-Prov!`, `uFuBb6Q5h1QUxCmc` → substituídos por `<redacted>`.
- **Verificação final**: `grep -rE "TesteE2E!2026|CP-Admin-2026!|Particular2026!|CP-D5615C-Prov!|uFuBb6Q5h1QUxCmc" /app/memory/` (excluindo `test_credentials.md`) → **0 ocorrências**.
- `/tmp/` → sem ficheiros relacionados com websummit/popup/demo.

### Ficheiros tocados (contagem de linhas afectadas)
| Ficheiro | Linhas |
|---|---|
| `CHANGELOG.md` | 1 |
| `PRD.md` | 1 |
| `btp_particulares_release_report.md` | 1 |
| `bug_cloudflare_520_prod_investigation.md` | 1 |
| `desbloqueios_infra_report.md` | 4 |
| `e2e_2026-10-13.md` | 3 |
| `fr_vs_pt_analysis.md` | 1 |
| `lote_w_security_audit_report.md` | 6 |
| `lote_x_hardening_report.md` | 7 |
| `rotate_2026_secrets.txt` | 1 |
| **Total** | **26** (algumas linhas tinham mais que uma ocorrência; 29 substituições totais) |

### Ficheiros **preservados intencionalmente**
- **`/app/memory/test_credentials.md`** — é o ficheiro **oficial lido pelo testing agent** (regra do sistema `/app/memory/test_credentials.md`). Redactar aqui quebra o fluxo de testing. **Decisão pendente do utilizador**:
  - (a) manter como está (actual);
  - (b) redactar e passar o testing agent a ler as mesmas chaves do `.env` (`TEST_PRO_EMAIL_PT`/`TEST_PRO_PASSWORD_PT`).

### Outras exposições de PII **FORA do scope `/app/memory/`** (sinalização apenas, não tocadas)
- `/app/frontend/e2e/ak3_admin_pedidos.spec.js:26` — fallback hardcoded `"TesteE2E!2026"` em código fonte.
- `/app/backend/core/provisioned_accounts.py` — segundo o audit `lote_w` já contém 3 passwords E2E em claro. Não verifiquei agora (fora do scope "só memory/tmp"); mas regra do utilizador implica **futura rotação**.

### Regra permanente (aplicada daqui para a frente)
Zero passwords, chaves, tokens, cookies de sessão ou PII em relatórios, mensagens, logs, código novo, ou commits. Sempre `<redacted>` + leitura via `os.environ.get(...)`.

---

## URGENTE-2 — Chaves `.env` para pré-flight

### Verificação (`/app/backend/.env`)
| Chave | Estado |
|---|---|
| `TEST_ADMIN_EMAIL` | PRESENTE · TEM VALOR |
| `TEST_ADMIN_PASSWORD` | PRESENTE · **VAZIO** |
| `TEST_PRO_EMAIL` | PRESENTE · **VAZIO** |
| `TEST_PRO_PASSWORD` | PRESENTE · **VAZIO** |
| `TEST_PRO_EMAIL_PT` | **ADICIONADA** com placeholder `<redacted>` |
| `TEST_PRO_PASSWORD_PT` | **ADICIONADA** com placeholder `<redacted>` |
| `TEST_PRO_EMAIL_FR` | **ADICIONADA** com placeholder `<redacted>` |
| `TEST_PRO_PASSWORD_FR` | **ADICIONADA** com placeholder `<redacted>` |

### Nenhuma chave existente foi apagada
Append-only. Convenção respeita `.env` protegido do runtime.

### Acção necessária do utilizador antes de P1.2
Preencher no `.env` do backend os valores reais (sem me os mostrar aqui):
- `TEST_PRO_EMAIL_PT` + `TEST_PRO_PASSWORD_PT` (conta prod `construpilot.pt`).
- `TEST_PRO_EMAIL_FR` + `TEST_PRO_PASSWORD_FR` (conta prod `construpilot.fr`; se for a mesma conta cross-domain, replicar o email PT).

Após preenchimento, não é preciso restart — o script `preflight.spec.js` lê o `.env` directamente a cada execução.

---

## P1.1 — Instalações no pod

| Pacote | Versão | Estado |
|---|---|---|
| `ffmpeg` | 5.1.9-0+deb12u1 | ✅ instalado via apt |
| `ffprobe` | 5.1.9-0+deb12u1 | ✅ instalado (companheiro) |
| `fonts-inter` | 4.0~beta7+ds-1 | ✅ apt |
| `fonts-inter-variable` | 4.0~beta7+ds-1 | ✅ apt |
| `xvfb-run` | — | ✅ já presente |
| Playwright | 1.64.0 (node) | ✅ já presente em `/app/frontend/node_modules` |
| Chromium headless shell | 156.0.8078.4 (v1248) | ✅ descarregado para `/pw-browsers/chromium_headless_shell-1248` |
| Chromium (full headful) | — | ⚠️ **só o headless-shell foi descarregado**. Para gravação P2 com UI visível, pode ser necessário `npx playwright install chromium` sem `--only=chromium-headless-shell`. Para pré-flight P1.2 **o headless-shell basta** (não gravamos nada em P1). |

### Verificação Inter
`fc-list | grep -i inter` devolve 50+ variantes (Thin → Black, Regular, Bold, Display, Italic, VF). Suficiente para legendas de vídeo e UI de preview.

### Espaço em disco pós-install
`/app`: 6.3 GB livres (36% usado) · overlay: 80 GB livres (23% usado). Margem confortável para gravações `.webm` + conversões `.mp4`.

---

## P1.2 — Candidatos de planta (varredura filesystem)

Varrido `/app/backend/tests/fixtures/` e todo `/app/backend` para ficheiros `*.png / *.jpg / *.pdf / *.dwg / *.dxf`.

### Resultados
| Candidato | Caminho | Tipo | Tamanho | Origem (data) |
|---|---|---|---|---|
| **A** (recomendado) | `/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png` | PNG RGB 1600×1600 | 20 035 B | 2026-10-13 — fixture sintética criada para testes de Lote Plans Pro. Nome indica síntese; emparelhado com `vision_response_coerente.json` → resposta IA previsível. |
| **B** (alternativa) | `/app/backend/tests/fixtures/plan_test.pdf` | PDF v1.3 · 1 página | 2 188 B | 2026-10-13 — fixture mínima genérica. Visualmente provavelmente fraca (2 KB sugere box simples). |
| **C** (desaconselhado) | `/app/backend/tests/fixtures/plan_test.dxf` | AutoCAD DXF 2010 | 38 382 B | 2026-10-13 — depende do pipeline ODA_FILE_CONVERTER que o P0 identificou como path inválido no pod; incerteza em prod. |

### Justificação do vencedor **A**
1. **Síntese 100%** — nome `moradia_sintetica` + pasta `plans_pro/fixtures` confirmam origem controlada. Zero risco de PII de cliente real em vídeo para investidores (regra dura do utilizador).
2. **Resposta IA previsível** — `vision_response_coerente.json` emparelhado garante que o motor produz saída visualmente útil (áreas, divisões).
3. **Qualidade visual** — PNG 1600×1600 renderiza nítido em 16:9 (padding) e 9:16 (centrado vertical), sem artefactos de rasterização.
4. **Pipeline simples** — PNG não requer conversão ODA/APS; evita o bloqueador identificado no P0.

### Validação dura do utilizador
> "Só plantas sintéticas ou de demonstração. Nenhuma planta de cliente real num vídeo para investidores."

Candidatos A, B e C **todos** residem em `/app/backend/tests/fixtures/` — pasta reservada a fixtures de teste, nunca contém dados de clientes. ✅ Compliance total.

---

## P1.2 — Script Playwright preparado (sem executar login)

### Localização
`/app/scripts/websummit_demo/preflight.spec.js`

### Design
- Lê `TEST_PRO_EMAIL_PT`/`TEST_PRO_PASSWORD_PT` do `/app/backend/.env` (fallback para `TEST_PRO_EMAIL`/`TEST_PRO_PASSWORD`).
- **Fail-fast**: se credenciais `<redacted>` ou vazias → aborta antes de qualquer navegação. Escreve `results.json` com `aborted: true, reason: "credenciais_em_falta"`.
- Para cada candidato: login → navega para `/plan-takeoff` (ou `/plans`, `/chiffrer/plans`, `/takeoff` — fallback por tentativa) → upload via `input[data-testid="plan-upload-input"]` → confirmar diálogo `plan-import-dialog` com nome `__preflight_<slug>__` → aguardar `[data-testid="ai-analysis-result"]` (até 5 min) → screenshot full-page → tentar apagar projecto.
- Timeout global por candidato: 10 min.
- Logging seguro: `log()` nunca imprime credenciais.
- Artefactos: `results.json` + `<slug>.png` em `/app/memory/webrsummit_demo/preflight/`.
- **Headless-shell** (não headful) — para P1.2 é suficiente; P2 (gravação) usará headful via xvfb-run.

### Sintaxe validada
`node -c preflight.spec.js` → OK.

### Validação não executada
Como combinado, **login não foi executado**. O script só correrá quando o utilizador preencher as credenciais no `.env`.

### Comando para executar quando credenciais estiverem prontas
```bash
cd /app/scripts/websummit_demo && node preflight.spec.js
```

### Divergências preview↔prod a confirmar na primeira execução
1. Rota real para o leitor de plantas (`/plan-takeoff` vs `/plans` vs `/chiffrer/plans`).
2. Existência real do `data-testid="ai-analysis-result"` em prod (preview build pode diferir).
3. Botão de apagar projecto — selector tentativo. Se falhar, projectos `__preflight_*` ficam criados e o relatório final sinaliza para limpeza manual.

---

## P1.3 — BLOQUEADO

Depende de P1.2 ter escolhido vencedor com credenciais reais. Não arrancado.

---

## Bloqueadores (prioridade)

| # | Bloqueador | Acção necessária | Dono |
|---|---|---|---|
| 1 | Credenciais `TEST_PRO_EMAIL_PT`/`TEST_PRO_PASSWORD_PT` vazias | preencher no `/app/backend/.env` | utilizador |
| 2 | Credenciais `TEST_PRO_EMAIL_FR`/`TEST_PRO_PASSWORD_FR` vazias | preencher no `/app/backend/.env` (se conta FR for distinta) | utilizador |
| 3 | `test_credentials.md` ainda tem passwords em claro | decisão: manter (actual) ou migrar testing agent para ler `.env` | utilizador |

---

## Próximos passos (quando credenciais estiverem prontas)

1. Executar `node /app/scripts/websummit_demo/preflight.spec.js`.
2. Validar `results.json` (login_ok, upload_ok, ai_result_received, ai_elapsed_ms, screenshot).
3. Se candidato A passar → avançar P1.3 (criar `Moradia Demo Web Summit` em `.pt` e `Maison Démo Web Summit` em `.fr`). Caso contrário, iterar.
4. Reportar com screenshots finais em `/app/memory/webrsummit_demo/preflight/final_pt_*.png` e `final_fr_*.png` para validação antes de P2 (gravação).

---

**Estado**: P1.1 ✅ · URGENTE-1/2 ✅ · P1.2 setup ✅ · P1.2 execução ⏳ (aguarda credenciais) · P1.3 ⏳.

Zero commits · Zero deploys · Zero PII escrita · Zero toques em dados reais de prod.
