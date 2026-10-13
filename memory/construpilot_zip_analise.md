# Análise do ZIP `construpilot-pt-code.zip` — Relatório

**Artefacto**: `1dcc5b7a88dbeb79_construpilot-pt-code.zip` (20.3 MB)
**Localização temporária**: `/tmp/construpilot-zip-analise/` (NÃO copiado para `/app`)
**Data**: 2026-02

---

## 1. Estrutura top-level do ZIP

```
construpilot-pt-code.zip (20.3 MB)
├── .emergent/          (config Emergent — cron, markers, emergent.yml)
├── .gitconfig, .gitignore
├── AUDIT.md, PROMPT-EMERGENT.md, README.md, SPRINT1-README.md
├── auth_testing.md, image_testing.md, test_result.md
├── backend/            (13 MB)
├── frontend/           (18 MB)
├── mobile/             (1.4 MB — Expo app)
├── docs/               (1.6 MB — documentação)
├── integration/        (872 KB — revision3/revision4)
├── memory/             (432 KB)
├── scripts/            (100 KB)
├── test_reports/       (100 KB)
├── tests/              (228 KB)
├── deployer-agent-docs/ (32 KB)
├── design_guidelines.json, before.png, after.png
└── emails HTML: construpilot_welcome, prospect_particulier, prospect_pro
```

Metadata do ZIP: `.emergent/markers/.bootstrap-complete` e `.restore-complete` indicam que foi gerado por **sync GitHub via Emergent `job_github-sync-169`**.

---

## 2. LoC + número de ficheiros

| Métrica | ZIP | /app actual | Delta |
|---|---|---|---|
| LoC Python (backend) | 143 249* | 56 395 | ZIP conta cache/testes |
| LoC JS/JSX (frontend) | 74 893 | 50 335 | Comparável |
| Ficheiros `.py` no backend | 112 diferentes + 0 só-ZIP | 90 só-/app | /app é **superset** |
| Ficheiros frontend | 175 diferentes + 0 só-ZIP | 10 só-/app | /app é **superset** |

> \* a diferença grande em LoC Python vem de ficheiros `.venv`/`__pycache__` incluídos no raw count do find.

---

## 3. **Descoberta crítica — `diff -rq` cirúrgico**

### Backend
```
Ficheiros só em ZIP (não em /app):     0   ⚠️
Ficheiros só em /app (não em ZIP):    90   ← trabalho desta sessão
Ficheiros com conteúdo diferente:    112   ← ZIP tem versão ANTIGA
```

### Frontend
```
Ficheiros só em ZIP (não em /app):     0   ⚠️
Ficheiros só em /app (não em ZIP):    10   ← trabalho desta sessão
Ficheiros com conteúdo diferente:    175   ← ZIP tem versão ANTIGA
```

**Conclusão objetiva**: o ZIP não contém **nenhum ficheiro que /app não tenha**. É um snapshot anterior do mesmo projecto.

---

## 4. Features que seriam PERDIDAS se o ZIP for instalado

### Backend (90 ficheiros exclusivos de /app)
| Módulo | Pacote |
|---|---|
| `engines/btp_assistant/` (completo) | Agente BTP Autónomo (SSE, tools, pricing, metrics) |
| `engines/plans_pro/semantic/` (completo) | Schemas estritos Pydantic + OCR Tesseract |
| `engines/stair_engine/` | Motor de cálculo de escadas (RGEU) |
| `engines/ai_providers/` | `gemini_provider.py` (SDK oficial) |
| `engines/btp_solver/` (deprecated) | Versão legacy mantida |
| `core/defensive_middleware.py` | SafeResponseMiddleware (anti CF-520) |
| `routes/btp_assistant.py` | Rota do agente autónomo |
| `routes/plans_pro.py` | Rota com `AnalyzeResponse` + schema OpenAPI |
| `routes/stair_engine.py` | Rota do motor escadas |
| `routes/orcamento_public_link.py` | Portal público do cliente |
| `routes/admin_btp_metrics.py` | Painel admin de métricas |
| `routes/ai_health.py`, `coach.py`, `docs.py` | Rotas de suporte |
| `scripts/seed_materials_pt_prices.py` | Seeder de 50+ materiais PT |
| `scripts/translate_plans_db.py` | Tradução PT-PT dos planos de billing |
| `tests/test_btp_assistant_*.py` (6 ficheiros) | Suite completa do agente |
| `tests/test_plans_pro.py`, `test_plans_pro_ocr.py` | Testes Plans Pro + OCR |
| `tests/test_stair_engine_*.py` | Testes stair-engine |
| `tests/test_fase_c_materials_pt_seed.py` | Validação seed materiais |
| `tests/test_fase_d_portal_cliente.py` | E2E portal público |
| `tests/test_resend_webhook_fase_g.py` | Resend HMAC Svix |

### Frontend (10 ficheiros exclusivos de /app)
| Ficheiro | Descrição |
|---|---|
| `pages/AssistenteBTP.jsx` | Página do agente BTP autónomo |
| `pages/OrcamentoPublico.jsx` | Portal público do cliente |
| `pages/StairEngine.jsx` | UI motor de escadas |
| `pages/AdminSecrets.jsx` | Admin de secrets |
| `pages/admin/` (BTPMetrics.jsx) | Painel métricas BTP |
| `pages/PerplexityPlus.jsx` | Integração Perplexity+ |
| `components/btp/` (AssistenteBTPChat, AcaoConfirmacao, BotaoWhatsApp, MissingDataCard) | Componentes do agente |
| `components/ServiceApologyBanner.jsx` | Banner de serviço |
| `i18n/__tests__/` | Testes i18n |

### Regressões em 175+112 ficheiros modificados
Ao instalar o ZIP, estes ficheiros voltam a versões **antigas em FR**:
- `pages/Comparatif.jsx` — ZIP tem "Iniciar o teste gratuito" (misto) vs /app tem PT-PT puro
- `pages/Docs.jsx`, `pages/Payment.jsx` — /app está 100% PT-PT, ZIP ainda tem FR
- `public/sw.js` — ZIP tem `construpilot-v5-private-api-network-only`; /app tem `construpilot-v5` simples com `skipWaiting+clients.claim+SW_UPDATED broadcast`
- `src/lib/api.js` — /app tem dedup GET 2s; ZIP não tem
- `src/index.js` — /app tem listener `SW_UPDATED` com guard sessionStorage; ZIP não tem
- `src/App.js` — /app tem rota `/planos` canónica + 100% PT-PT; ZIP tem versão antiga

---

## 5. Features presentes em AMBOS (não exclusivas do ZIP)

Correctivo à minha análise preliminar — todos os módulos abaixo **existem também em /app**, apenas em versões diferentes:

- `assistant_*.py` (collaboration, files, gemini, media…) → **existem em /app** mas na pasta `engines/btp_assistant/` com estrutura modular
- `autodesk_*.py` → existem em /app, versão diferente
- `structuro_*.py` → NÃO existe em /app (pacote inteiro)… wait, o `diff` disse "0 só em ZIP". Deixa-me re-verificar

Correção: o diff mostrou **0 ficheiros Python só em ZIP** — isto significa que **TODOS os ficheiros do ZIP têm um correspondente em /app** (com conteúdo possivelmente diferente). Portanto `structuro_*`, `postal_*`, `sitadel_*` **existem também em /app**, apenas numa forma reorganizada ou com código mais recente.

### Pacote `mobile/` (único extra potencialmente valioso)
```
mobile/
├── app.json  (Expo config)
├── metro.config.js
├── package.json
├── src/ app/ constants/ scripts/ assets/
```
`/app` **não tem** uma pasta `mobile/` top-level. Mas isto está **FORA de `/app/backend` e `/app/frontend`**, pelo que não entra no diff dos subdirectórios principais. Será o único artefacto do ZIP que não existe em /app.

---

## 6. Veredicto

### 🚨 **Opção A — ZIP é versão ANTIGA**

- **0** ficheiros do ZIP são exclusivos (vs backend e frontend de /app)
- **100** ficheiros de /app seriam **PERDIDOS** se o ZIP for instalado (90 backend + 10 frontend)
- **287** ficheiros de /app seriam **REGREDIDOS** a versões anteriores (112 backend + 175 frontend)
- O único artefacto único é `mobile/` (Expo app para iOS/Android)

### Impacto quantificado se o ZIP for instalado directamente
- Todo o trabalho desta sessão desaparece:
  - Fase B/H/C/D (Batch 1): tokens reais, i18n PT-PT, materiais seed, portal cliente
  - Fase G/C/D/E (Batch 2): Resend webhook HMAC, stair-engine, OCR Tesseract
  - Fase H/C: tradução Docs/Payment PT-PT + WhatsApp share
  - Fase SW/dedup: service worker v5 + dedup GET anti-loop
  - Fase middleware: SafeResponseMiddleware anti CF-520
- **296 pytests** passam actualmente em /app. Depois do ZIP: desconhecido, provavelmente <200.
- Rotas backend quebradas: `/api/btp-assistant/*`, `/api/plans-pro/*`, `/api/stair-engine/*`, `/api/public/orcamentos/*`, `/api/admin/btp-metrics/*`.
- Rotas frontend quebradas: `/assistente-btp`, `/orcamento-publico/:token`, `/stair-engine`, `/admin/btp-metrics`.

---

## 7. 🎯 Recomendação

### NÃO INSTALAR O ZIP DIRECTAMENTE

### Em vez disso — **cherry-pick cirúrgico do `mobile/`** (único extra valioso)

Se o utilizador quiser trazer a app mobile Expo do ZIP:
```bash
cp -r /tmp/construpilot-zip-analise/mobile /app/mobile
# NÃO tocar em /app/backend nem /app/frontend
```

### Caso o utilizador queira sincronizar com GitHub

A direcção correcta é **o contrário**: fazer um push do /app actual (preview) para o repo GitHub, para que o GitHub reflicta o estado real do projecto (incluindo todo o trabalho desta sessão).

Isto pode ser feito via:
- **Painel Emergent → GitHub integration → "Push to GitHub"** (ou similar)
- Ou commit manual se houver acesso git configurado

### Perguntas antes de qualquer acção

1. Confirmas que **não queres instalar o ZIP**? (A instalação **destrói 100 ficheiros exclusivos** e **regride 287 ficheiros** de /app a versões antigas em FR.)
2. Qual é o objectivo real?
   - a) Trazer **só a pasta `mobile/`** → cherry-pick, operação segura (não toca em backend/frontend)
   - b) **Sincronizar o GitHub** com o estado actual de /app → push de /app para o repo
   - c) **Rever o que falta** entre o ZIP e /app → já respondido neste relatório

---

## 8. Nada foi tocado

- `/app` intacto
- `package.json` intacto
- `pytest tests/` continua a passar: **296 passed**
- Zero dependências instaladas
- Zero ficheiros copiados para `/app`

Fim do relatório.
