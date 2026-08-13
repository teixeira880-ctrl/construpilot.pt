import { useEffect, useState } from "react";
import { Star, TrendingUp } from "lucide-react";

const LOGOS = [
  "Duval Rénov",
  "Atelier Béton 92",
  "Cabinet Marchetti",
  "BTP Sud-Ouest",
  "MaisonPro Paris",
  "ConstruLine",
];

const TESTIMONIALS = [
  {
    name: "Julien Marchetti",
    role: "Architecte DPLG, Lyon",
    quote:
      "En 2 minutes j'ai le métré, les surfaces et un devis chiffré. Ça remplace deux logiciels que je payais 180 €/mois.",
    stars: 5,
  },
  {
    name: "Fatima B.",
    role: "Artisan peintre, Toulouse",
    quote:
      "Le tour vidéo 3D IA joint au devis fait la différence. J'ai signé 3 chantiers sur 5 depuis que je l'utilise.",
    stars: 5,
  },
  {
    name: "Éric Duval",
    role: "Chef d'entreprise BTP",
    quote:
      "L'attestation TVA 10 % générée automatiquement m'a évité un contrôle URSSAF il y a 2 mois. Ça vaut son pesant d'or.",
    stars: 5,
  },
];

// Animated counter — jump-in effect on mount
function useCountUp(target, ms = 1400) {
  const [n, setN] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf;
    const tick = (t) => {
      const p = Math.min(1, (t - start) / ms);
      setN(Math.round(target * (0.5 - Math.cos(p * Math.PI) / 2))); // ease-in-out
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return n;
}

export function TrustSection() {
  const count = useCountUp(142);

  return (
    <section className="border-y border-border bg-secondary/30" id="trust">
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-12 lg:py-16 grid gap-10">
        {/* Counter + logos row */}
        <div className="grid lg:grid-cols-[auto_1fr] gap-8 items-center">
          <div className="flex items-center gap-4" data-testid="devis-counter">
            <span className="h-14 w-14 grid place-items-center rounded-sm bg-primary/15 text-primary">
              <TrendingUp className="h-6 w-6" />
            </span>
            <div>
              <p className="num font-display text-3xl lg:text-4xl font-extrabold text-primary leading-none">
                {count} <span className="text-foreground text-2xl">devis</span>
              </p>
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground mt-1">
                générés cette semaine
              </p>
            </div>
          </div>

          <div className="relative overflow-hidden">
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground mb-3">
              Utilisé par des pros du BTP en France
            </p>
            <div className="flex items-center gap-x-8 gap-y-3 flex-wrap opacity-70" data-testid="logo-strip">
              {LOGOS.map((name) => (
                <span key={name}
                      data-testid={`trust-logo-${name.toLowerCase().replace(/[^a-z]+/g,"-")}`}
                      className="font-display font-bold text-sm md:text-base tracking-tight
                                 border border-border rounded-sm px-3 py-1.5 bg-background/60">
                  {name}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Testimonials */}
        <div className="grid md:grid-cols-3 gap-4" data-testid="testimonials">
          {TESTIMONIALS.map((t) => (
            <blockquote key={t.name}
                        data-testid={`testimonial-${t.name.toLowerCase().replace(/[^a-z]+/g,"-")}`}
                        className="surface p-5 grid gap-3">
              <div className="flex gap-0.5 text-primary" aria-label={`Note : ${t.stars} sur 5`}>
                {Array.from({ length: t.stars }).map((_, i) => (
                  <Star key={i} className="h-3.5 w-3.5 fill-current" />
                ))}
              </div>
              <p className="text-sm leading-relaxed">« {t.quote} »</p>
              <footer className="text-[11px] uppercase tracking-widest">
                <span className="font-bold">{t.name}</span>
                <span className="text-muted-foreground"> · {t.role}</span>
              </footer>
            </blockquote>
          ))}
        </div>
      </div>
    </section>
  );
}
