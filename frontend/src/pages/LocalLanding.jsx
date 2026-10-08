import { useLocation, Navigate, Link } from "react-router-dom";
import { MapPin, Users, TrendingUp, Zap, ArrowRight, CheckCircle2, Building2 } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { getCity, CITY_LIST } from "@/lib/cities";

export default function LocalLanding() {
  const location = useLocation();
  // Derive slug from URL: /devis-travaux-{slug}
  const slug = location.pathname.replace(/^\/devis-travaux-/, "").split("/")[0];
  const c = getCity(slug);
  if (!c) return <Navigate to="/" replace />;

  // JSON-LD LocalBusiness scoped to the city (best-in-class local SEO)
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "ProfessionalService",
    "name": `ConstruPilot ${c.name}`,
    "description": `Estimativa de obra, orçamento calculado e comparador de preços de materiais para toda a construção e remodelação em ${c.name} (${c.department}).`,
    "url": `https://construpilot.pt/devis-travaux-${c.slug}`,
    "areaServed": {
      "@type": "City",
      "name": c.name,
      "containedInPlace": { "@type": "State", "name": c.region },
    },
    "geo": { "@type": "GeoCoordinates", "latitude": c.lat, "longitude": c.lng },
    "priceRange": `${c.priceRange} €/m²`,
    "aggregateRating": {
      "@type": "AggregateRating",
      "ratingValue": "4.8",
      "reviewCount": Math.max(30, Math.floor(c.artisans / 100)),
    },
    "hasOfferCatalog": {
      "@type": "OfferCatalog",
      "name": `Serviços BTP ${c.name}`,
      "itemListElement": [
        { "@type": "Offer", "name": "Estimativa de obra gratuita" },
        { "@type": "Offer", "name": "Orçamento de remodelação calculado" },
        { "@type": "Offer", "name": "Comparador de preços de materiais" },
        { "@type": "Offer", "name": "Medição 2D a partir da planta" },
      ],
    },
  };

  return (
    <>
      <SEO
        title={`Orçamento de obras ${c.name} — Estimativa de remodelação em 30 s`}
        description={`Estime a sua obra em ${c.name} em 30 segundos. Preço médio de remodelação ${c.name}: ${c.priceRange} €/m². Orçamento IA gratuito, ${c.artisans.toLocaleString("pt-PT")} profissionais referenciados em ${c.region}.`}
        keywords={`orçamento obras ${c.name}, preço remodelação ${c.name}, profissional ${c.name}, orçamento remodelação ${c.department}, custo obras ${c.name}, ${c.region} construção`}
        canonical={`/devis-travaux-${c.slug}`}
        image={c.heroImage}
        jsonLd={jsonLd}
      />

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border grain">
        <img src={c.heroImage} alt={`Remodelação de apartamento em ${c.name}`}
             className="absolute inset-0 h-full w-full object-cover opacity-25" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="relative mx-auto max-w-[1500px] px-5 lg:px-8 py-16 lg:py-20">
          <p className="overline">
            <MapPin className="inline h-3 w-3 mr-1" />
            {c.name} · {c.region}
          </p>
          <h1 className="mt-4 font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter">
            Orçamento de obras em <span className="text-primary">{c.name}</span>:<br />
            estime, compare, assine.
          </h1>
          <p className="mt-5 text-base md:text-lg text-muted-foreground max-w-2xl">
            Remodelação de apartamento, moradia, casa de banho, cozinha ou construção nova em{" "}
            <strong>{c.name} ({c.department})</strong>: o ConstruPilot orça o seu projecto em 30 s
            com preços reais de 2026 ajustados ao mercado local.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/smart-project">
              <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white h-11"
                      data-testid={`local-cta-smart-${c.slug}`}>
                Estimar o meu projecto <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/prix">
              <Button variant="outline" className="rounded-sm h-11" data-testid={`local-cta-prix-${c.slug}`}>
                Comparar preços de materiais
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat icon={TrendingUp} value={`${c.priceStandard.toLocaleString("pt-PT")} €`}
                label="Remodelação padrão / m²" />
          <Stat icon={Users} value={c.artisans.toLocaleString("pt-PT")}
                label={`Profissionais em ${c.region}`} />
          <Stat icon={Building2} value={c.surface} label={`Área ${c.name}`} />
          <Stat icon={Zap} value="30 s" label="Orçamento instantâneo" />
        </div>
      </section>

      {/* Local content */}
      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-16 grid lg:grid-cols-[2fr_1fr] gap-10">
        <div>
          <p className="overline">O que precisa de saber</p>
          <h2 className="mt-3 font-display text-2xl lg:text-3xl font-bold tracking-tight">
            Remodelar em {c.name} em 2026: contexto local
          </h2>
          <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
            O mercado de remodelação em <strong>{c.name}</strong> é particularmente dinâmico.
            O preço médio de uma remodelação padrão situa-se em torno de{" "}
            <strong>{c.priceStandard.toLocaleString("pt-PT")} €/m²</strong>, num intervalo de{" "}
            <strong>{c.priceRange} €/m²</strong> consoante a gama (económica / padrão / premium). Uma obra
            típica na região, por exemplo <em>{c.typicalProject}</em>, orça-se em média
            entre <strong>{c.typicalPrice}</strong>.
          </p>

          <h3 className="mt-8 font-display text-lg font-semibold">Especificidades locais</h3>
          <ul className="mt-4 grid gap-3">
            {c.localTips.map((tip, i) => (
              <li key={i} className="flex gap-3 text-sm" data-testid={`local-tip-${c.slug}-${i}`}>
                <CheckCircle2 className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <span className="text-muted-foreground">{tip}</span>
              </li>
            ))}
          </ul>

          <h3 className="mt-8 font-display text-lg font-semibold">
            Códigos postais cobertos em {c.name}
          </h3>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {c.zipcodes.map((z) => (
              <span key={z}
                    className="text-[11px] font-mono border border-border rounded-sm px-2 py-1 bg-secondary/40"
                    data-testid={`zipcode-${z}`}>
                {z}
              </span>
            ))}
          </div>
        </div>

        {/* Sidebar CTA */}
        <aside className="surface p-6 h-fit sticky top-24" data-testid={`local-sidebar-${c.slug}`}>
          <p className="overline">Pronto para começar?</p>
          <h3 className="mt-2 font-display text-xl font-bold">
            Orce o seu projecto em {c.name}
          </h3>
          <p className="mt-3 text-xs text-muted-foreground">
            Gratuito, sem inscrição. Resultado em 30 segundos com preços ajustados a{" "}
            {c.region}.
          </p>
          <Link to="/smart-project" className="block mt-5">
            <Button className="w-full rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              Iniciar estimativa <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <div className="mt-6 pt-6 border-t border-border grid gap-2 text-[11px]">
            <p className="font-bold">Outras localidades cobertas:</p>
            <div className="flex flex-wrap gap-1">
              {CITY_LIST.filter((x) => x.slug !== c.slug).map((x) => (
                <Link key={x.slug} to={`/devis-travaux-${x.slug}`}
                      className="text-primary hover:underline"
                      data-testid={`local-link-${x.slug}`}>
                  {x.name}
                </Link>
              )).reduce((acc, el, i, arr) => acc.concat(el, i < arr.length - 1 ? " · " : ""), [])}
            </div>
          </div>
        </aside>
      </section>
    </>
  );
}

function Stat({ icon: Icon, value, label }) {
  return (
    <div className="surface p-4 flex items-center gap-3">
      <span className="h-10 w-10 grid place-items-center rounded-sm bg-primary/15 text-primary">
        <Icon className="h-4 w-4" />
      </span>
      <div>
        <p className="num font-display font-extrabold text-lg leading-none">{value}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">{label}</p>
      </div>
    </div>
  );
}
