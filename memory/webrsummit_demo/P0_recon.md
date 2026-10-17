# P0 — Reconhecimento (read-only) · Vídeo demo Web Summit 2026

**Data**: 2026-10-17 · **Idioma**: PT-PT · **Scope**: só sondagens; zero escritas em prod, zero logins, zero instalações.

---

## 1. Tooling no pod

| Ferramenta | Estado | Nota |
|---|---|---|
| `ffmpeg` | ❌ **AUSENTE** (`command not found`) | **BLOQUEADOR P2/P3**. Precisa de `apt install ffmpeg` em pod runtime antes da gravação final. |
| `chromium` | ✅ `/root/bin/chromium` | — |
| `google-chrome` | ✅ `/usr/bin/google-chrome` | — |
| `chromium-browser` | ❌ ausente | fallback irrelevante dado os 2 acima. |
| `node` | ✅ `v24.19.0` | — |
| `yarn` | ✅ `1.22.22` | — |
| Playwright | ✅ `1.64.0` (em `/app/frontend/node_modules`) | Browsers Chromium 1248 já cacheados em `/pw-browsers/` (verificado em AJ.3). |
| `pymupdf` | ✅ `1.28.2` | — |
| `pillow` | ✅ `12.3.0` | — |
| `xvfb-run` | ✅ `/usr/bin/xvfb-run` | — |
| Fontes | ⚠️ **Inter / Roboto / DejaVu / Noto Sans AUSENTES**. Disponíveis: Liberation Sans, FreeSans, Bitstream Charter, Noto Color Emoji. | Para legendas e UI em vídeo, uso **Liberation Sans** (suporta acentos PT/FR Latin-1 Supplement). Alternativa: `apt install fonts-noto-core fonts-inter` em P1. |
| Disco | `/app` 6.8 GB livres (31% usado); overlay 74 GB livres | Suficiente para `.webm`/`.mp4` + 19 slides webp. |

**Resumo**: tudo pronto excepto **ffmpeg** (crítico) e opcionalmente fontes modernas (cosmético).

---

## 2. Fixtures de plantas candidatas

Busca exaustiva em `/app/backend/tests/fixtures/` + varredura ampla `/app/**/*.pdf` com "plan|planta|maison|moradia|floor|hab".

| # | Ficheiro | Tipo | Tamanho | Dim | Preview gerado |
|---|---|---|---|---|---|
| A | `/app/backend/tests/fixtures/plan_test.pdf` | PDF 1 página v1.3 | 2 188 B | 1241×1754 (A4) | `/tmp/plan_preview_plan_test.png` (112 KB) |
| B | `/app/backend/tests/fixtures/plan_test.dxf` | AutoCAD DXF v2010 | 38 382 B | — | ❌ não gerado (requer ODA/ezdxf) |
| C | `/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png` | PNG RGB 8-bit | 20 035 B | 1600×1600 | `/tmp/plan_preview_thumbnail_moradia_sintetica.png` (cópia directa) |

**Contexto adicional** (encontrado ao lado do candidato C):
- `plans_pro/aps_metadata_moradia.json` — metadados APS para processamento.
- `plans_pro/vision_response_coerente.json` — resposta IA **já coerente** pré-produzida (planta deliberadamente desenhada para ser legível pelo motor IA).
- `plans_pro/ocr_abreviaturas_pt.txt` — abreviaturas PT para OCR.
- Nome "moradia_sintetica" sinaliza fixture controlada para testes positivos.

### Recomendação: **Candidato C — `thumbnail_moradia_sintetica.png`**

**Justificação em 2 critérios do briefing**:

1. **Legibilidade da IA**: já tem `vision_response_coerente.json` emparelhado — garantia de que o motor IA produz resposta útil e visualmente convincente (áreas delineadas, divisões identificadas). O `plan_test.pdf` é PDF sintético genérico sem metadados — risco de IA produzir resposta pobre ou ambígua. O DXF (B) requer pipeline de conversão que pode falhar em prod e introduz segmento de carregamento mais longo.

2. **Visual convincente**: PNG 1600×1600 renderiza nitidamente a qualquer resolução sem artefactos de rasterização. Dimensão quadrada enquadra bem num segmento 16:9 (centrado com padding) e num 9:16 (centrado vertical). Confirmo visualmente antes de P1 abrindo `/tmp/plan_preview_thumbnail_moradia_sintetica.png`.

**Alternativa segunda prioridade**: `plan_test.pdf` só se o motor IA de prod rejeitar PNG não-metadados (improvável — Vision aceita imagens genéricas).

**Avisos**:
- A planta é "sintética" — se o Martinho quiser realismo máximo (planta real de arquitecto), o pod não tem fixture adequada. Nessa hipótese, Martinho envia PDF/PNG como asset externo em P1.

---

## 3. Acesso de rede a prod

### `construpilot.pt`
```
HTTP/2 200
date: Sat, 17 Oct 2026 12:30:10 GMT
content-type: text/html; charset=utf-8
access-control-allow-origin: *
cache-control: no-cache, no-store, must-revalidate
etag: "4a4efc0eb508f7a3215840cd502c6143"
set-cookie: __emg_vid=...; __emg_sid=...; Secure; SameSite=Lax
```

### `construpilot.fr`
```
HTTP/2 200
date: Sat, 17 Oct 2026 12:30:11 GMT
content-type: text/html; charset=utf-8
access-control-allow-origin: *
set-cookie: __emg_vid=...; __emg_sid=...; Secure; SameSite=Lax
```

**Observações**:
- ✅ Ambos acessíveis via HTTPS directo.
- ✅ Zero header `cf-ray` / `cf-cache-status` / `server: cloudflare` → não detecto Cloudflare na frente. Infra parece ser directa Emergent (cookies `__emg_vid`/`__emg_sid`).
- ⚠️ Cookies de sessão são emitidos no primeiro GET — Playwright herda-os ao navegar. Zero bloqueio anti-bot visível neste HEAD, mas rate limiting pode activar sob carga de login/API em P1.
- ⚠️ Lingua detection do pop-up Web Summit funciona por hostname (`.pt`/`.fr`) → ambos os domínios já respondem com conteúdo próprio. Para capturar vídeo PT uso `construpilot.pt`; para FR uso `construpilot.fr`; para EN uso o toggle de língua da aplicação após login (confirmar em P1 que existe).

---

## 4. Estado actual dos projectos-demo (verificação diferida para P1)

Nesta fase P0 recon **não efectuei login nem queries à API** conforme instrução. Documento para P1:

- **Credenciais a usar** (ambiente de prod, autorizadas por escrito pelo utilizador para gravação): `teste.pro+e2e@construpilot.pt` / `TesteE2E!2026` (do `/app/memory/test_credentials.md`).
- **Pergunta pendente para P1 (a responder via `GET /api/projects` logadado)**:
  > "Existe já na conta `teste.pro+e2e` um projecto com nome `Moradia Demo Web Summit` ou `Maison Démo Web Summit`?"
  Se **sim** → reutilizar e verificar que estado está limpo. Se **não** → criar em P1 numa única sessão, usando a planta recomendada em (2).
- Resposta ficará explicitamente em P1_setup.md.

---

## 5. Estratégia técnica de gravação (proposta, não executada)

### Opção A — Playwright nativo `video: on`
```js
const ctx = await browser.newContext({
  viewport: { width: 1920, height: 1080 },
  recordVideo: { dir: "/app/memory/webrsummit_demo/raw/", size: { width: 1920, height: 1080 } },
});
```
Gera `.webm` (VP8/VP9) por page.

**Prós**:
- Zero dependências externas em runtime (xvfb/x11grab não necessários).
- Mesma linha temporal que os `page.waitFor…` — fluidez previsível.
- Resolução exacta (sem riscos de capturar partes do desktop virtual).
- Reproduzível em qualquer pod.

**Contras**:
- Framerate é fixo (~25fps em `.webm`) e **cursor NÃO é renderizado** no vídeo nativo Playwright (bug conhecido). Para carimbo de rato visível seria necessário overlay CSS artificial.
- `.webm` tem que ser convertido para `.mp4` H.264 com ffmpeg para compatibilidade universal (Instagram/LinkedIn/Keynote aceitam `.mp4`).

### Opção B — `xvfb-run` + `ffmpeg x11grab` + Playwright headful
```bash
xvfb-run -s "-screen 0 1920x1080x24" node record.js &
ffmpeg -f x11grab -video_size 1920x1080 -r 30 -i :99 out.mp4
```

**Prós**:
- Cursor visível nativamente (ponteiro renderizado pelo xvfb).
- Framerate configurável (30/60fps).
- Output `.mp4` H.264 directo, sem passo de conversão.

**Contras**:
- **Depende de `ffmpeg`** — actualmente ausente no pod.
- Mais frágil: sincronização entre Playwright script e processo ffmpeg paralelo pode produzir inícios/fins recortados.
- Riscos de capturar artefactos do desktop virtual se a janela não ocupa 100%.
- Mais latência (3 processos a correr).

### Recomendação: **Opção A — Playwright `video: on` + conversão `ffmpeg` em pós-processamento**

Razões:
1. Instalação de `ffmpeg` já é necessária para pós-produção (concat segmentos, legendas, exports 9:16, aplicação de música silenciosa se houver). Reutilizar.
2. Cursor pode ser simulado com overlay artificial (`div` com `transform: translate(x,y)` sincronizado via Playwright `page.evaluate`) — carimbo visualmente "clean" e previsível, melhor que ponteiro nativo que pode saltitar.
3. Reprodutibilidade >> fidelidade pixel-perfeita do ponteiro para um vídeo de demo publicitário.

### Pipeline proposto
```
Playwright (A opção)  →  /tmp/raw_<seg>.webm  (×N segmentos)
         ↓
ffmpeg (concat + overlay cursor + legendas via drawtext/subtitles)
         ↓
/app/memory/webrsummit_demo/final/
    demo_pt_16x9.mp4   demo_pt_9x16.mp4
    demo_fr_16x9.mp4   demo_fr_9x16.mp4
    demo_en_16x9.mp4   demo_en_9x16.mp4
```

**Dependência bloqueadora**: `ffmpeg` tem de ser instalado em P1 (via `apt install ffmpeg` — operação standard em pod runtime).

---

## 6. Estratégia de export 9:16 a partir de 16:9

### (a) Crop centrado 607×1080
Pega no centro horizontal da fonte 1920×1080. **Perde laterais** (~68% da largura). Se o conteúdo IA fica no header ou se divisões da planta estão nos cantos, cortadas.

**Veredicto**: ❌ demasiado destrutivo para uma aplicação com UI densa.

### (b) Padding fundo `#0F172A` + conteúdo reescalado
Fonte 1920×1080 é redimensionada para largura 1080 (altura ≈ 607), posicionada ao centro vertical de um canvas 1080×1920 com fundo `#0F172A` (azul-escuro ConstruPilot, matching popup Web Summit).

Espaço restante acima/abaixo (≈ 656 px total) usado para:
- Topo: logótipo ConstruPilot grande (~130 px alto).
- Baixo: legenda principal grande (~160 px alto) + CTA/badge (~80 px).

**Veredicto**: ✅ **Recomendada**. Legibilidade de legendas garantida em telemóvel (160px altura equivale a ~48pt — leitura confortável em 6"), zero cortes do conteúdo original, branding reforçado nas bandas.

### (c) Crop dinâmico que segue área activa
Script heurístico que detecta área de foco (ex. onde está o cursor sintético ou o modal aberto) e desloca o crop em cada frame.

**Veredicto**: ❌ alta complexidade (requer análise frame-a-frame ou timeline manual), riscos de panoramas enjoativos, pouco ganho vs (b).

### Recomendação: **(b) Padding + branding bands**

Comando ffmpeg indicativo (a validar em P3):
```
ffmpeg -i demo_pt_16x9.mp4 -filter_complex \
  "[0:v]scale=1080:-2[main]; \
   color=c=0x0F172A:size=1080x1920:duration=90[bg]; \
   [bg][main]overlay=0:(H-h)/2[composed]; \
   [composed]drawtext=fontfile=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf: \
     text='Plataforma IA para a construção':fontcolor=white:fontsize=48:x=(w-tw)/2:y=1760" \
  demo_pt_9x16.mp4
```

Legendas e drawtext calibrados em P3 por segmento.

---

## 7. Riscos identificados

| # | Risco | Prob | Impacto | Mitigação proposta |
|---|-------|------|---------|-------------------|
| R1 | **`ffmpeg` ausente no pod** | Certo | Alto | Instalar em P1 (`apt install ffmpeg`). Único blocker técnico identificado. |
| R2 | Rate limiting prod em sequência rápida de API calls (upload planta → start reading → poll status) | Médio | Médio | Pausas 1-2s entre acções no script Playwright + `page.waitForLoadState('networkidle')`. Se bater em 429, backoff exponencial. Se persistir, split em 2 sessões separadas. |
| R3 | **Loader IA imprevisível** (leitura de planta pode demorar 15-60s em vez de 5-10s expectável) | Alto | Médio | Script Playwright usa `page.waitForSelector('[data-testid*="result"]')` com `timeout: 120000`. **Nunca gravar waits em tempo real** — gravar em dois takes (upload+click) + (resultado) e cortar/comprimir o loader em pós-produção com cut ou speed-up 4-8× com texto overlay "A IA está a trabalhar…". Melhor UX de demo e evita vídeo cheio de "a carregar". |
| R4 | **PII acidental em prod** (menu utilizador aberto, email no header, histórico de outros projectos, tooltips com ficheiros de outros clientes) | Médio | Alto (GDPR + imagem) | **Regra estrita antes de cada take**: 1) menu utilizador deve estar fechado; 2) header NÃO deve mostrar email (verificar se há flag "demo mode" ou mascarar via `page.addStyleTag({content: '[data-testid*="user-email"] { display:none }'})`); 3) nenhum tooltip com nome de ficheiro de outro projecto; 4) listar projectos antes de gravar para confirmar que só existe o `Moradia Demo Web Summit`; 5) revisão visual frame-a-frame do primeiro take antes de replicar nos outros idiomas. |
| R5 | Fontes modernas ausentes → legendas renderizadas em Liberation Sans podem parecer "datadas" visualmente | Baixo | Baixo | Opcional em P1: `apt install fonts-inter fonts-noto-core`. Se bloqueado, Liberation Sans Bold a 48pt renderiza decentemente. |
| R6 | **Cookies prod persistem** entre sessões Playwright se não isolar context — risco de "contaminação" visual (pop-up Web Summit do sessionStorage marcado, estado de login residual) | Médio | Médio | Cada take num `browser.newContext()` fresco. SessionStorage e localStorage limpos. Se o pop-up Web Summit (do deployment anterior) aparecer durante a gravação, decidir se fica (vantagem publicitária: cita o Web Summit) ou se é fechado programaticamente antes do take. |
| R7 | **Playwright `video: on` não captura o cursor nativo** → clicks parecem "mágicos" | Médio | Baixo | Overlay cursor artificial via CSS/JS injectado no Playwright context, posicionado em `mousemove`/`click` sintetizados. Alternativa: anotar visualmente com um "halo" radial pulsado no local do click, mais vistoso para demo publicitária. |

### Estimativa de tempo total (P0+P1+P2+P3)

| Fase | Scope | Tempo |
|------|-------|-------|
| **P0** | Recon (esta fase) | ✅ ~15 min (concluída) |
| **P1** | Setup: instalar ffmpeg + preparar projecto demo em prod + validar planta + afinar fontes se necessário | **~30-45 min** (depende de velocidade de upload+leitura IA real; multiplicar por 2 se R3 activar) |
| **P2** | Gravação: 3 línguas × ~6 segmentos cada = 18 takes brutos em 1920×1080 | **~45-60 min** (sem reprises); contingência +30 min se R2/R3 surgirem |
| **P3** | Pós-produção: concat, legendas, overlay cursor, exports 16:9 + 9:16 × 3 línguas = 6 outputs finais | **~45-60 min** (ffmpeg encode ×6 outputs 60-90s @ 1080p é ~5-8 min cada em CPU) |
| **Total** | Com buffers de segurança | **≈ 2h30 – 4h00** em sessão corrida ideal |

---

## Resumo (10 linhas)

1. **Pod pronto excepto `ffmpeg`** — único blocker; instalar em P1 (`apt install ffmpeg`). Chromium, Playwright 1.64, Node 24, pymupdf, xvfb — todos presentes.
2. **Fontes modernas ausentes** (Inter/Roboto/Noto Sans) — Liberation Sans Bold cobre acentos PT/FR; opcional reforço em P1.
3. **Planta recomendada**: `/app/backend/tests/fixtures/plans_pro/thumbnail_moradia_sintetica.png` (1600×1600 PNG) — fixture controlada com `vision_response_coerente.json` emparelhado, garante leitura IA convincente.
4. **Prod acessível** em `.pt` + `.fr` via HTTPS directo (HTTP/2 200, cookies `__emg_vid`/`__emg_sid`, sem Cloudflare detectável).
5. **Credenciais** `teste.pro+e2e@construpilot.pt` / `TesteE2E!2026` (uso em P1).
6. **Estratégia gravação recomendada**: Playwright nativo `video: on` + conversão ffmpeg. Simples, reproduzível, cursor simulado por overlay para melhor controlo visual.
7. **Export 9:16 recomendado**: padding com fundo `#0F172A` + redimensionamento central + bandas superiores/inferiores para logótipo e legenda grande. Zero cortes do conteúdo.
8. **Riscos principais**: `ffmpeg` ausente (certo), loader IA imprevisível em prod (alto), PII acidental em header/menus (médio mas alto impacto GDPR).
9. **Regra PII estabelecida**: nunca mostrar menu utilizador aberto, header sem email, zero tooltips com nomes de outros projectos. Revisão visual obrigatória antes de replicar takes.
10. **Estimativa total P0+P1+P2+P3**: **~2h30 a 4h00** em sessão corrida. Zero toques em prod nesta fase P0. Lotes AK + 20 commits + pop-up em pausa — todos intactos. Pedido admin `es643515@gmail.com` continua em pausa.
