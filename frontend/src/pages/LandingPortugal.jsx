import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import {
  Calculator, ShieldCheck, ReceiptText, Users, FileCheck2, MapPin, ArrowRight, Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SEO } from "@/components/SEO";
import { useI18n } from "@/context/I18nContext";

const DISTRICTS = [
  { name: "Lisboa", low: 750, high: 1400 },
  { name: "Porto", low: 650, high: 1250 },
  { name: "Algarve (Faro)", low: 700, high: 1300 },
  { name: "Setúbal", low: 600, high: 1150 },
  { name: "Braga", low: 500, high: 950 },
  { name: "Aveiro", low: 520, high: 980 },
  { name: "Coimbra", low: 500, high: 950 },
  { name: "Leiria", low: 480, high: 920 },
  { name: "Madeira", low: 650, high: 1200 },
  { name: "Açores", low: 650, high: 1200 },
];

const FEATURES = [
  { icon: Calculator, title: "Estimativa em 5 minutos", text: "Descreva a sua obra e a IA calcula lotes, materiais, mão de obra e orçamento — sem ser especialista." },
  { icon: ShieldCheck, title: "Verifique orçamentos", text: "O scanner deteta preços inflacionados ou lotes em falta nos orçamentos dos seus profissionais." },
  { icon: ReceiptText, title: "IVA de Portugal", text: "23% de taxa normal e 6% (Verba 2.27) na reabilitação de habitação elegível — aplicado automaticamente." },
  { icon: FileCheck2, title: "Faturas com NIF", text: "Orçamentos e faturas com o seu NIF e Alvará, prontos para clientes em Portugal." },
  { icon: Users, title: "Encontre profissionais", text: "Publique o seu pedido de obras e receba propostas de profissionais verificados do seu distrito." },
  { icon: MapPin, title: "Preços por distrito", text: "Coeficientes de mercado 2026 para 16 distritos — de Lisboa aos Açores." },
];

export default function LandingPortugal() {
  const { setLang } = useI18n();
  const heroRef = useRef(null);
  useEffect(() => { setLang("pt"); /* landing sempre em PT-PT */ /* eslint-disable-next-line */ }, []);
  useEffect(() => {
    // React não serializa fiavelmente o atributo `muted` — força via ref para autoplay funcionar
    // em todos os browsers (Chromium/Safari bloqueiam autoplay não-mute).
    const v = heroRef.current;
    if (!v) return;
    v.muted = true;
    v.playsInline = true;
    const p = v.play();
    if (p && typeof p.catch === "function") p.catch(() => {});
  }, []);

  return (
    <div className="grid gap-16 pb-16" data-testid="landing-portugal">
      <SEO
        title="ConstruPilot Portugal — Estimativa de obras grátis"
        description="Estime o custo das suas obras em Portugal em 5 minutos, verifique orçamentos, calcule materiais e IVA (23% ou 6% na reabilitação). Preços €/m² por distrito. Grátis."
        keywords="estimativa obras Portugal, preço renovação casa, orçamento obras, IVA reabilitação 6%, custo remodelação, comparador materiais"
        image="https://static.prod-images.emergentagent.com/jobs/24c1027c-3500-4369-9271-1f0502b94a6a/images/fbaf496274fa11a9c5394225aca188f1a65432f532c0018128117c37f0228ffc.jpeg"
        canonical="/portugal"
      />

      {/* HERO */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-primary/10 via-background to-background p-8 sm:p-12">
        <span className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary bg-primary/10 rounded-full px-3 py-1">
          🇵🇹 Agora em Portugal
        </span>
        <h1 className="mt-4 font-display font-extrabold text-4xl sm:text-5xl lg:text-6xl leading-[1.05] max-w-3xl">
          Estime as suas obras. <span className="text-primary">Sem surpresas.</span>
        </h1>
        <p className="mt-4 text-base sm:text-lg text-muted-foreground max-w-2xl">
          O ConstruPilot ajuda particulares e profissionais em Portugal a estimar o custo de obras,
          verificar orçamentos, calcular materiais e emitir orçamentos e faturas com IVA e NIF — em minutos.
        </p>
        <div className="mt-6 rounded-xl overflow-hidden border border-border bg-black/5 aspect-video">
          <video
            ref={heroRef}
            src="/hero-pt.mp4"
            autoPlay
            muted
            loop
            playsInline
            preload="auto"
            className="w-full h-full object-cover"
            aria-label="Demonstração ConstruPilot"
            data-testid="pt-hero-video"
          />
        </div>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/estimation">
            <Button className="rounded-sm gap-2 h-12 px-6 text-base" data-testid="pt-hero-estimate">
              Estimar a minha obra <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link to="/login">
            <Button variant="outline" className="rounded-sm h-12 px-6 text-base" data-testid="pt-hero-register">
              Criar conta grátis
            </Button>
          </Link>
        </div>
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-primary" /> Grátis para começar</span>
          <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-primary" /> IVA 23% / 6% automático</span>
          <span className="flex items-center gap-1.5"><Check className="h-4 w-4 text-primary" /> 16 distritos cobertos</span>
        </div>
      </section>

      {/* FEATURES */}
      <section className="grid gap-6">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-wider text-primary">Tudo o que precisa</p>
          <h2 className="mt-1 font-display font-bold text-2xl sm:text-3xl">Ferramentas de profissional, ao alcance de todos</h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <div key={i} className="surface p-5 rounded-xl" data-testid={`pt-feature-${i}`}>
              <div className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center mb-3">
                <f.icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="font-semibold text-base">{f.title}</h3>
              <p className="mt-1 text-sm text-muted-foreground leading-relaxed">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* DISTRICT PRICES */}
      <section className="grid gap-5">
        <div className="max-w-2xl">
          <p className="text-xs font-bold uppercase tracking-wider text-primary">Preços 2026 por distrito</p>
          <h2 className="mt-1 font-display font-bold text-2xl sm:text-3xl">Quanto custa renovar em Portugal?</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Valores indicativos de <b>reabilitação</b> (€/m², sem IVA), consoante o distrito e o nível de acabamento.
            Obtenha a sua estimativa exata em segundos.
          </p>
        </div>
        <div className="surface rounded-xl overflow-hidden">
          <table className="w-full text-sm" data-testid="pt-district-table">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="px-4 py-3 font-bold">Distrito</th>
                <th className="px-4 py-3 font-bold text-right">Reabilitação (€/m²)</th>
              </tr>
            </thead>
            <tbody>
              {DISTRICTS.map((d, i) => (
                <tr key={i} className="border-b border-border/40" data-testid={`pt-district-${i}`}>
                  <td className="px-4 py-2.5 flex items-center gap-2"><MapPin className="h-3.5 w-3.5 text-primary" /> {d.name}</td>
                  <td className="px-4 py-2.5 text-right num font-semibold">
                    {d.low.toLocaleString("pt-PT")} – {d.high.toLocaleString("pt-PT")} €
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Estimativas indicativas de mercado 2026. Não substituem um orçamento formal de um profissional.
        </p>
      </section>

      {/* SOCIAL PROOF / TRUST */}
      <section className="grid gap-6" data-testid="pt-social-proof">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
          {[
            { k: "16", v: "distritos cobertos" },
            { k: "6% / 23%", v: "IVA aplicado corretamente" },
            { k: "30 s", v: "para uma estimativa" },
            { k: "100%", v: "grátis para começar" },
          ].map((s, i) => (
            <div key={i} className="surface rounded-xl p-4" data-testid={`pt-stat-${i}`}>
              <div className="font-display font-extrabold text-2xl sm:text-3xl text-primary">{s.k}</div>
              <div className="mt-1 text-xs text-muted-foreground">{s.v}</div>
            </div>
          ))}
        </div>
        <div className="grid md:grid-cols-3 gap-4">
          {[
            { q: "Fiz a estimativa da remodelação do meu T3 em Lisboa em 5 minutos. Ajudou-me a perceber se o orçamento do empreiteiro era justo.", n: "Sofia M.", c: "Lisboa" },
            { q: "Como empreiteiro no Porto, faço os orçamentos com IVA e NIF em minutos. Os clientes adoram receber tudo por e-mail.", n: "Ricardo A.", c: "Porto" },
            { q: "Detetou lotes em falta no orçamento que recebi para a minha moradia no Algarve. Poupou-me uma discussão desagradável.", n: "João P.", c: "Faro" },
          ].map((tst, i) => (
            <figure key={i} className="surface rounded-xl p-5 flex flex-col gap-3" data-testid={`pt-testimonial-${i}`}>
              <div className="text-primary text-lg leading-none">★★★★★</div>
              <blockquote className="text-sm text-foreground/90 leading-relaxed flex-1">“{tst.q}”</blockquote>
              <figcaption className="text-xs text-muted-foreground">
                <span className="font-semibold text-foreground">{tst.n}</span> · {tst.c}
              </figcaption>
            </figure>
          ))}
        </div>
        <p className="text-[11px] text-center text-muted-foreground">
          Testemunhos ilustrativos da fase de lançamento em Portugal.
        </p>
      </section>

      {/* Demonstração vídeo */}
      <section className="max-w-5xl mx-auto py-16 px-6" data-testid="pt-demo-section">
        <p className="overline text-center">Demonstração</p>
        <h2 className="mt-3 font-display text-3xl sm:text-4xl font-bold text-center tracking-tight">
          Ver o ConstruPilot em acção
        </h2>
        <p className="mt-3 text-sm text-muted-foreground text-center max-w-2xl mx-auto">
          Da planta ao orçamento com IVA em poucos minutos. Carregue no vídeo para ver o fluxo completo.
        </p>
        <div className="mt-8 rounded-xl overflow-hidden border border-border shadow-lg bg-black/5">
          <video
            src="/demo-pt.mp4"
            controls
            playsInline
            preload="metadata"
            className="w-full"
            aria-label="Demonstração ConstruPilot Portugal"
            data-testid="pt-demo-video"
          />
        </div>
      </section>

      {/* CTA */}
      <section className="rounded-2xl border border-primary/30 bg-primary/5 p-8 sm:p-10 text-center grid gap-4">
        <h2 className="font-display font-bold text-2xl sm:text-3xl">Pronto para começar a sua obra?</h2>
        <p className="text-sm text-muted-foreground max-w-xl mx-auto">
          Estime, compare e decida com confiança. O essencial é grátis.
        </p>
        <div className="flex flex-wrap gap-3 justify-center">
          <Link to="/estimation">
            <Button className="rounded-sm gap-2 h-12 px-6 text-base" data-testid="pt-cta-estimate">
              Estimar agora <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link to="/tarifs">
            <Button variant="outline" className="rounded-sm h-12 px-6 text-base" data-testid="pt-cta-pricing">
              Ver planos
            </Button>
          </Link>
        </div>
      </section>
    </div>
  );
}
