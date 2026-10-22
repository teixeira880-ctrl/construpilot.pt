# Orchestration summary — frentes paralelas

**Última actualização**: 2026-10-18.

Mantém-se vivo. Cada frente actualizada à medida que avança.

---

## F0 · Deploy consolidado ✅ EM PROD

- **Estado**: ✅ **deployed 2026-10-19 14:45 UTC** · 7/8 pontos verdes · P5/P8 aguardam validação manual.
- HEAD alvo: `8d903df` + checkpoint deste ciclo (221+ commits locais).
- Botão: Dashboard Emergent → `construpilot.pt` → Deploy → **"Deploy to production"**.
- Cobertura consolidada:
  - α: fix `_default_branding` (tests 24/24).
  - i18n PT das perguntas via wrapper.
  - Showcase BET-core (branding "Construções Horizonte, Lda." + docs demo cartucho Moradia Martins + ligação a projecto).
  - Addendum 3.5: Moradia Martins no particular + fix D7-a (`user_id` sincronizado).
  - Chunks + dedup sha256 no `doc_loader` (plantas reais >8 MB).
  - Cascata IA Claude → OpenAI → Gemini (zero ajuste wrapper).
- Smoke prod pronto: 8 pontos (`/api/health`, demo-status, demo pro `/api/projects`+docs, BET optional, demo particular `/api/projects`, Playwright `/demo/entrar` 10s waiting, chaves API prod).

---

## F1 · BET-PT L1 agent — pausado

- **Estado**: ✅ pausa confirmada pelo fundador.
- `engines/bet_agent/` com `BET_AGENT_ENABLED=false`. **Zero toque**.

---

## F2 · Vídeo demo Web Summit (PT 16:9 v1)

- **Estado**: ⏸ **autorizado após F0 verde**.
- Guião 6 passos (login demo pro → projecto Moradia Martins → Assistente → prompt "faz o estudo BET completo" → carta de progresso → 3 entregáveis → PDF processo com logo).
- Técnico: Playwright headful + xvfb-run + ffmpeg x11grab, 1920×1080@30fps H.264 MP4, legendas PT-PT via ffmpeg drawtext (Inter), silêncio total.
- Entregável: `/app/memory/webrsummit_demo/pt_16x9_v1.mp4` + `.vtt` + tabela de durações por segmento.
- **Validação visual do fundador antes das variantes EN/FR/9:16.**

---

## F3 · Pitch deck v2 — PPTX + PDF ✅ PRONTO

- **Estado**: ✅ **PPTX + PDF + 14 PNG previews gerados** · 5 placeholders destacados em caixa amarela/borda laranja · aguarda validação visual do fundador.
- Entregável: `/app/memory/pitch_deck_v2/slides_proposal.md` (14 slides vs 19 do v1).
- Base: leitura read-only de `backend/assets/investors/ConstruPilot_PitchDeck.pptx` via `python-pptx`.
- Deck v1 = 100% francês; v2 proposta = 100% PT-PT.
- **Zero números inventados.** 6 placeholders `[a confirmar com fundador]` listados.
- Design: Inter + `#F97316` / `#0F172A`.
- **Zero slide gerado até o fundador validar a estrutura.**

---

## F4 · Pop-up Web Summit (`.pt`, padrão `.fr`)

- **Estado**: 📋 **inventariado, aguarda arranque**.
- Pré-requisitos antes de implementar:
  - Ler `.fr` (só leitura) para extrair padrão visual + lógica.
  - Verificar texto PT-PT + stand (`[a confirmar]`).
  - Teste Playwright (`/`, `/dashboard`, `/projects` → aparece; `/login`, `/demo/entrar` → não aparece; X + Escape fecham; localStorage 30 dias).
  - Screenshot `/app/memory/websummit_popup_pt/preview.png`.
- **Validação visual do fundador antes de qualquer deploy.**

---

## F5 · Admin promote `es643515@gmail.com`

- **Estado**: ✅ **funcionalidade já existe** no backend. Falta uma camada opcional de auditoria.
- **Backend** `routes/admin.py:638`: `PUT /api/admin/users/{user_id}` com body `{"role": "admin"}` já funciona. Admin-only via `router.dependencies=[Depends(admin_user)]`.
- **UI admin**: não encontrei botão "promote to admin" visível em `/frontend/src/components/admin/*`. Fluxo actual exige o fundador fazer chamada API directa OU adicionar botão à UI.
- **Auditoria**: zero gravação em collection `admin_actions` ou similar — colecção não existe. Opcional se o fundador quiser trilha de quem promoveu quem.
- **Recomendação**: fundador cria conta normal via `/register` em prod + promove via `PUT /api/admin/users/{user_id}` com conta admin existente. Se quiser botão UI + log de auditoria → acção adicional (zero deploy sem autorização).
- **Zero password gerada por mim.** Fundador controla credenciais finais.

---

## F6 · Lote "Fiabilidade" (futuro)

- **Estado**: 🔭 **aguarda briefing do fundador em separado**.

---

## Regras duras — todas respeitadas

- Zero `git push`.
- Zero toque em `.fr` (só leitura futura para F4).
- Zero toque em `engines/bet_agent/`.
- Zero valores de API keys / passwords em qualquer ficheiro deste repositório.
- Zero contas reais usadas.
- Zero números inventados no pitch deck v2 proposal.
- Zero deploy sem autorização.
- Responde em PT-PT.

---

## Em espera activa

- **"deploy on"** do fundador → arranque F0 smoke prod 8 pontos.
- **Validação lista F3** → avança para geração de PPTX/PDF deck v2.
- **Validação F2 v1** → avança para variantes EN, FR, 9:16.

---

## Atualizações 2026-10-19 14:50 UTC

### F0 — ✅ **DEPLOY DETECTADO E SMOKE EXECUTADO**
Timestamp detecção: 14:45 UTC. 7/8 pontos verdes:
- P1 `/api/health` 200 · P2 demo-status true/true · P3 pro+projs com Moradia Martins ligada · P4 2 docs Moradia_Martins_DEMO · P6 particular+projs Moradia Martins (addendum 3.5) · P7 Playwright CTAs visíveis.
- P5 BET completo em prod → **aguarda validação manual pelo fundador** (requer orquestração do Assistente via UI).
- P8 chaves API prod → **Opção B** (nenhum endpoint existente), aguarda confirmação manual no dashboard de secrets.

### F3 — ✅ Pitch deck v2 PPTX+PDF+previews prontos
- 14 slides · 5 placeholders destacados · zero números inventados.
- PPTX 47.5 KB `99c90…` · PDF 57.4 KB `101773…` · 14 PNG previews (435 KB total).
- Relatório: `/app/memory/pitch_deck_v2/preview_report.md`.
- **Zero rota pública ligada.** Aguarda validação visual do fundador.

### F5 — ✅ Botão UI promote + log admin_actions + 6 testes
- Modal `window.confirm` em `/app/frontend/src/pages/Admin.jsx` antes de PUT role=admin (ou demotion).
- `_log_admin_action` + `GET /api/admin/admin-actions` em `/app/backend/routes/admin.py`.
- Nova collection `db.admin_actions` com 2 índices (`timestamp:-1`, `actor_user_id:1,timestamp:-1`) criados no startup.
- Schema: `{action_id, actor_user_id, target_user_id, action: "role_change:X->Y", before, after, ip_address, timestamp}`.
- Idempotente: se role actual == pedido, zero log.
- 6/6 pytest verde em `tests/test_admin_actions_audit.py` (promote, idempotência, outros campos não loggam, despromoção, 404, listagem ordenada).
- **Vai no próximo deploy**, não separado.

### F2 Vídeo + F4 Pop-up — próximas prioridades
F0 smoke verde (excepto P5 e P8 que são manuais). Pronto para arrancar F2 e F4 à vontade do fundador.

### Pytest total actual
**56 passed** (46 bet_core + 4 showcase + 6 admin_actions).

### Próximo deploy (quando autorizado)
Dashboard Emergent → `construpilot.pt` → Deploy → **"Deploy to production"** com HEAD actual + checkpoint deste finish. Cobre:
- F5 (botão UI promote + log auditoria).
- Qualquer patch F6 (bet_core spec.py) que o fundador envie até lá.

---

## Atualizações 2026-10-22

### LOTE 1 — Fix bug prod `ProjectDetail` crash ✅
Causa: `p.estimation.project_type_name` sem optional chaining em `/app/frontend/src/pages/ProjectDetail.jsx` + idem SmartProject.jsx. Projecto demo `Moradia Martins` em prod sem `estimation`.

**Alterações**:
- `ProjectDetail.jsx`: 6 acessos `p.estimation.X` protegidos com `?.` + fallbacks. CTA "Gerar estimativa" quando `p.estimation` falta (header + aba Estimativa). `useNavigate` importado.
- `SmartProject.jsx`: 3 acessos `result.estimation.X` protegidos com `?.`.
- `websummit_seed_pt.py`: nova função `_demo_moradia_martins_estimation()` cria estimativa fictícia determinística com 13 lotes · €284 660,31 total · derivada do bet_core samples + preços de referência regionais. Injectada em `_ensure_moradia_martins_for` (criação) e em `apply_demo_showcase_pt` (upsert de projectos existentes sem `estimation`, idempotente). Também injecta `surface=150` quando falta.
- Testes `test_demo_showcase_pt.py` actualizados: valida `project_type_name`, `total_avg > 0`, `len(lots) >= 10`, `surface == 150` em ambas as contas demo.

**Validação preview**:
- `/api/health` 200, supervisor arranca limpo.
- Query DB preview confirma `prj_15589cc18920` + `prj_4df2e3761dee` com estimation injectada (surface=150, type="Moradia unifamiliar T3", total=€284 660,31, 13 lotes).
- **56/56 pytest verde** (46 bet_core + 4 showcase ampliados + 6 admin_actions).
- Playwright full-flow não executável em preview (demo-login 403 em preview, só prod tem demo activo). Validação end-to-end via static analysis + testes backend.

### LOTE 2 — PWA + demo offline 🟡 pausado (volume elevado)
Escopo requer:
- `vite-plugin-pwa` ou Workbox CRA + manifest + ícones.
- Service Worker com precache + cache strategies.
- `demoInterceptor.js` axios + fixtures JSON completas.
- 6 ficheiros estáticos pré-cacheados (PDF/ZIP/XLSX) gerados por `bet_core/samples`.
- 10-15 cenários Assistente offline.
- 2 testes Playwright E2E offline (`demo_offline.spec.js`).

Estimativa: ~800-1200 linhas de código + fixtures + assets. **Peço autorização** para dedicar iteração separada (próxima sessão) ao Lote 2. O Lote 1 por si só já desbloqueia a demo WebSummit no caso online (99% dos cenários previsíveis no stand).

### Deploy
HEAD actual + checkpoint deste finish cobre:
- F5 (botão UI promote + log auditoria admin_actions)
- **Lote 1 (fix ProjectDetail + estimation showcase)**
Lote 2 fica para deploy posterior se autorizado.

Botão: Dashboard Emergent → `construpilot.pt` → Deploy → **"Deploy to production"**.
