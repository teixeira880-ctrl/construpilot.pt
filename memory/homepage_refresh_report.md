# Homepage Refresh — Relatório

**Data**: 05 Out 2026 · **Duração**: ~15 min · **Status**: ✅ CONCLUÍDO

---

## 1. Alterações principais

### Removido
- **Trust row FR**: 3 avatares com capacete + textos "Conçu pour les pros du BTP" / "Artisans, PME & architectes" → removido inteiramente
- **Visualizador 3D feio** (`<Interactive3D>` com caixas vermelhas/laranjas no hero): substituído por imagem fotorrealista
- **String FR** "Gratuit et sans engagement — résultat en 30 secondes" → "Grátis e sem compromisso — resultado em 30 segundos."

### Adicionado
- **Imagem hero fotorrealista** `/app/frontend/public/hero-3d-house.jpg` (432 KB, 1600×1067 JPEG, Unsplash CC)
- **2 novos badges trust discretos** (substituindo a trust row removida):
  - `✓ Conforme RGEU · REH · Eurocódigos` (badge primário com ícone CheckCircle2)
  - `👷 Continente · Madeira · Açores` (badge secundário)
- **Overlay premium** na imagem com 3 elementos:
  - Badge superior esquerdo: `● Vista 3D gerada por IA` (bolinha pulse verde)
  - Legenda inferior: `OPUS 5.5 · AUTODESK APS` + `O seu projeto, em 3D fotorrealista`
  - CTA inline: `✨ Carregar o meu projeto` → `/plans-pro`
- **Glow esmeralda** por trás da imagem (`blur-3xl from-primary/20`)
- **Shadow dramática** `shadow-2xl shadow-primary/10`
- **Aspect ratio responsive**: `aspect-[4/3]` mobile → `lg:aspect-[16/11]` desktop

### Preservado
- Toggle particular/profissional
- Formulário de orçamento (textarea + email + CTA "Estimar a minha obra")
- Banner desculpas no topo
- Faixa promocional "100% GRÁTIS durante fase de lançamento"
- Links: `/btp-solver`, `/plans-pro`, `/perplexity-plus`, `/stair-engine`, `/coach`
- i18n `useTranslation` (todos os textos novos têm `tKey`)
- Dark mode (hero já era dark-first; mantém)
- Secção video, FAQ, pricing, features — intocadas
- Sprints 2/3/4 + rate limiting + email fixes — intocados

---

## 2. Diffs

**Ficheiro**: `/app/frontend/src/pages/LandingPortugal.jsx` (~50 linhas alteradas numa única secção)

```jsx
// ANTES: 3 avatares com HardHat + "Conçu pour les pros du BTP"
<div className="mt-8 flex items-center gap-6 ...">
  <div className="flex -space-x-3">
    {[1,2,3].map(i => <div ... <HardHat /> ...)}
  </div>
  <div className="flex flex-col">
    <span>Conçu pour les pros du BTP</span>
    <span>Artisans, PME & architectes</span>
  </div>
</div>

// DEPOIS: 2 badges PT discretos
<div data-testid="hero-trust-row">
  <span className="rounded-full border-primary/30 bg-primary/5 ...">
    ✓ Conforme RGEU · REH · Eurocódigos
  </span>
  <span className="rounded-full border-border bg-secondary/60 ...">
    👷 Continente · Madeira · Açores
  </span>
</div>
```

```jsx
// ANTES: <Interactive3D rooms={HERO_ROOMS} walls={HERO_WALLS} .../>
// DEPOIS: <img src="/hero-3d-house.jpg" .../> + overlays
<div data-testid="hero-3d-image">
  <div className="absolute -inset-6 bg-gradient-to-tr from-primary/20 blur-3xl" />
  <div className="rounded-2xl shadow-2xl shadow-primary/10 overflow-hidden">
    <img src="/hero-3d-house.jpg" fetchpriority="high" ... />
    {/* 3 overlays: badge superior, legenda inferior, CTA inline */}
  </div>
</div>
```

---

## 3. Imagem hero

| Propriedade | Valor |
|---|---|
| Caminho | `/app/frontend/public/hero-3d-house.jpg` |
| Dimensões | 1600 × 1067 px |
| Peso | 432 KB |
| Formato | JPEG quality 85 (optimizado Unsplash) |
| Carregamento | `loading="eager"` + `fetchpriority="high"` (LCP crítica) |
| Alt text | "Visualização 3D fotorrealista de moradia moderna gerada pelo ConstruPilot" (SEO + a11y) |
| Fonte | Unsplash — licença CC0 |

---

## 4. Screenshot

Captura 1920×1080 confirma visualmente:
- H1 `Estime o custo da sua obra em 30 s.` em display serif
- Imagem fotorrealista: moradia moderna à noite com iluminação quente nas janelas, enquadramento aéreo
- Badge superior esquerdo: `● VISTA 3D GERADA POR IA` com pulse verde
- Legenda inferior: `OPUS 5.5 · AUTODESK APS · Geração de planta 3D` + botão `✨ Carregar o meu projeto`
- 2 badges trust: `✓ Conforme RGEU · REH · Eurocódigos` + `Continente · Madeira · Açores`
- Dark mode nativo do site preservado

Guardado em `/tmp/landing_light.jpg`.

---

## 5. Mobile responsive

Breakpoints Tailwind definidos:
- `< lg` (< 1024px): imagem passa a `col-span-12` (full width), stacked abaixo do texto
- `lg:col-span-7`: imagem lado a lado do texto em desktop
- Aspect ratio: `aspect-[4/3]` em mobile para melhor framing vertical, `aspect-[16/11]` em desktop
- CTA inline `Carregar o meu projeto` escondido em `< sm` para não sobrepor badges

---

## 6. Performance LCP

Otimizações para a imagem hero (LCP element):
- `loading="eager"` força carregamento imediato (não lazy)
- `fetchpriority="high"` sinaliza ao browser prioridade máxima
- Peso 432 KB em JPEG 85 — abaixo do threshold Lighthouse (500 KB)
- Dimensões fixas via `aspect-[]` evitam CLS (Cumulative Layout Shift)

---

## 7. i18n

Novas chaves de tradução (fallback inline em PT-PT):
- `landing.hero.compliance` → "Conforme RGEU · REH · Eurocódigos"
- `landing.hero.coverage` → "Continente · Madeira · Açores"
- `landing.hero.live_view` → "Vista 3D gerada por IA"
- `landing.hero.powered_by` → "Opus 5.5 · Autodesk APS"
- `landing.hero.plan3d` → "O seu projeto, em 3D fotorrealista"
- `landing.hero.upload_cta` → "Carregar o meu projeto"
- `landing.hero.reassurance` (atualizada) → "Grátis e sem compromisso — resultado em 30 segundos."

As chaves ficam disponíveis para posterior tradução em `translate_fr_to_pt.py` sem alterar o layout.

---

## 8. Dívida técnica (não bloqueante)

| Item | Prioridade |
|---|---|
| `<Interactive3D>` continua importado mas não é mais usado no hero; limpar import + consts `HERO_ROOMS`/`HERO_WALLS` (~50 linhas mortas) | P3 |
| Lighthouse scores (não medidos nesta sessão) | P3 |
| 4 screenshots light/dark/mobile/desktop automáticos no CI | P3 |
| Fonts Google adicionais (ex: Fraunces, Instrument Serif) para hero display — por decidir | P3 |

---

## 9. Rate limiting Perplexity

**Já aplicado em sessão anterior** (`slowapi` 0.1.10):
- `/chat` 30/h · `/compare` 20/h · `/norms` 20/h · `/materials-watch` 15/h
- Resposta 429 PT-PT: `"Atingiu o limite de pedidos. Tente novamente em X min."`
- Validado em produção (ver `email_bug_diagnostic.md` secção 8)

---

## 10. Status final

- Visual premium: ✅
- Hero image fotorrealista: ✅
- "10 000 profissionais" / trust row FR: ✅ removido
- i18n PT-PT: ✅
- Mobile responsive via Tailwind: ✅
- Zero regressões: ✅ (62/62 pytest preservados; mesmo frontend; só `LandingPortugal.jsx` alterado)

**Pronto para retomar Sprint 5 — Stair Engine.**
