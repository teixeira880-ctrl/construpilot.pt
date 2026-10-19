# Orchestration summary — frentes paralelas

**Última actualização**: 2026-10-18.

Mantém-se vivo. Cada frente actualizada à medida que avança.

---

## F0 · Deploy consolidado (BLOQUEADOR)

- **Estado**: 🟡 **aguarda "deploy on" do fundador**.
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

## F3 · Pitch deck v2 (lista de slides)

- **Estado**: ✅ **lista proposta pronta — aguarda validação do fundador**.
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
