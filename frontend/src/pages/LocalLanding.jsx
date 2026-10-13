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
    "description": `Estimation travaux, devis chiffré et comparateur prix matériaux pour tous les chantiers de rénovation et construction à ${c.name} (${c.department}).`,
    "url": `https://construpilot.fr/devis-travaux-${c.slug}`,
    "areaServed": {
      "@type": "City",
      "name": c.name,
      "containedInPlace": { "@type": "State", "name": c.region },
    },
    "geo": { "@type": "GeoCoordinates", "latitude": c.lat, "longitude": c.lng },
    "priceRange": `${c.priceRange} €/m²`,
    "hasOfferCatalog": {
      "@type": "OfferCatalog",
      "name": `Services BTP ${c.name}`,
      "itemListElement": [
        { "@type": "Offer", "name": "Estimation travaux gratuite" },
        { "@type": "Offer", "name": "Devis rénovation chiffré" },
        { "@type": "Offer", "name": "Comparateur prix matériaux" },
        { "@type": "Offer", "name": "Métré 2D depuis plan" },
      ],
    },
  };

  return (
    <>
      <SEO
        title={`Devis travaux ${c.name} — Estimation rénovation`}
        description={`Estimez vos travaux à ${c.name} avec ConstruPilot. Ordre de grandeur rénovation ${c.name} : ${c.priceRange} €/m² selon la gamme. Estimation détaillée, prix matériaux et devis PDF.`}
        keywords={`devis travaux ${c.name}, prix rénovation ${c.name}, artisan ${c.name}, devis rénovation ${c.department}, coût travaux ${c.name}, ${c.region} BTP`}
        canonical={`/devis-travaux-${c.slug}`}
        image={c.heroImage}
        jsonLd={jsonLd}
      />

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-border grain">
        <img src={c.heroImage} alt={`Rénovation appartement ${c.name}`}
             className="absolute inset-0 h-full w-full object-cover opacity-25" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="relative mx-auto max-w-[1500px] px-5 lg:px-8 py-16 lg:py-20">
          <p className="overline">
            <MapPin className="inline h-3 w-3 mr-1" />
            {c.name} · {c.region}
          </p>
          <h1 className="mt-4 font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter">
            Devis travaux à <span className="text-primary">{c.name}</span> :<br />
            estimez, comparez, signez.
          </h1>
          <p className="mt-5 text-base md:text-lg text-muted-foreground max-w-2xl">
            Rénovation appartement, maison, salle de bain, cuisine ou construction neuve à{" "}
            <strong>{c.name} ({c.department})</strong> : ConstruPilot chiffre votre projet
            avec les prix réels France 2026 ajustés au marché local.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link to="/smart-project">
              <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white h-11"
                      data-testid={`local-cta-smart-${c.slug}`}>
                Estimer mon projet <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link to="/prix">
              <Button variant="outline" className="rounded-sm h-11" data-testid={`local-cta-prix-${c.slug}`}>
                Comparer les prix matériaux
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 grid grid-cols-2 md:grid-cols-4 gap-4">
          <Stat icon={TrendingUp} value={`${c.priceStandard.toLocaleString("fr-FR")} €`}
                label="Rénovation standard / m²" />
          <Stat icon={Users} value={`~${c.artisans.toLocaleString("fr-FR")}`}
                label={`Artisans du bâtiment en ${c.region} (estimation)`} />
          <Stat icon={Building2} value={c.surface} label={`Surface ${c.name}`} />
          <Stat icon={Zap} value="PDF" label="Devis chiffré téléchargeable" />
        </div>
      </section>

      {/* Local content */}
      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-16 grid lg:grid-cols-[2fr_1fr] gap-10">
        <div>
          <p className="overline">Ce qu'il faut savoir</p>
          <h2 className="mt-3 font-display text-2xl lg:text-3xl font-bold tracking-tight">
            Rénover à {c.name} en 2026 : contexte local
          </h2>
          <p className="mt-4 text-sm text-muted-foreground leading-relaxed">
            Le marché de la rénovation à <strong>{c.name}</strong> est particulièrement dynamique.
            Le prix moyen d'une rénovation standard s'établit autour de{" "}
            <strong>{c.priceStandard.toLocaleString("fr-FR")} €/m²</strong>, dans une fourchette de{" "}
            <strong>{c.priceRange} €/m²</strong> selon la gamme (éco / standard / premium). Un chantier
            type dans la région, par exemple <em>{c.typicalProject}</em>, se chiffre en moyenne
            entre <strong>{c.typicalPrice}</strong>.
          </p>

          <h3 className="mt-8 font-display text-lg font-semibold">Spécificités locales</h3>
          <ul className="mt-4 grid gap-3">
            {c.localTips.map((tip, i) => (
              <li key={i} className="flex gap-3 text-sm" data-testid={`local-tip-${c.slug}-${i}`}>
                <CheckCircle2 className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                <span className="text-muted-foreground">{tip}</span>
              </li>
            ))}
          </ul>

          <h3 className="mt-8 font-display text-lg font-semibold">
            Codes postaux couverts à {c.name}
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
          <p className="overline">Prêt à démarrer ?</p>
          <h3 className="mt-2 font-display text-xl font-bold">
            Chiffrez votre projet {c.name}
          </h3>
          <p className="mt-3 text-xs text-muted-foreground">
            Gratuit pour démarrer. Estimation détaillée avec des prix ajustés à{" "}
            {c.region}.
          </p>
          <Link to="/smart-project" className="block mt-5">
            <Button className="w-full rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              Lancer l'estimation <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <div className="mt-6 pt-6 border-t border-border grid gap-2 text-[11px]">
            <p className="font-bold">Autres villes couvertes :</p>
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
