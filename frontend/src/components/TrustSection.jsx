import { useEffect, useState } from "react";
import { Star, TrendingUp } from "lucide-react";

const TESTIMONIALS = [];

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
        {/* Counter row */}
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

        {/* Testimonials — emplacement conservé, avis à venir */}
        <div className="grid md:grid-cols-3 gap-4" data-testid="testimonials">
          {TESTIMONIALS.length === 0 ? (
            <div className="md:col-span-3 surface p-8 grid place-items-center text-center gap-2" data-testid="testimonials-empty">
              <div className="flex gap-0.5 text-primary/40">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Star key={i} className="h-4 w-4 fill-current" />
                ))}
              </div>
              <p className="text-sm text-muted-foreground max-w-md">
                Les avis de nos utilisateurs apparaîtront ici prochainement.
              </p>
            </div>
          ) : TESTIMONIALS.map((t) => (
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
