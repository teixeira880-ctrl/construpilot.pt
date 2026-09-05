import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useInView } from "framer-motion";
import {
  ScanLine, FileText, Cuboid, Bot, ArrowRight, CheckCircle2, Video, Layers, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/context/I18nContext";
import { SHOWCASE_I18N, SHOWCASE_STATS } from "@/lib/showcaseI18n";

const IMGS = [
  "https://images.unsplash.com/photo-1721244654392-9c912a6eb236?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
  "https://images.pexels.com/photos/8961008/pexels-photo-8961008.jpeg?auto=compress&cs=tinysrgb&dpr=2&w=1200",
  "https://images.unsplash.com/photo-1531834685032-c34bf0d84c77?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200",
  null,
];
const ICONS = [ScanLine, FileText, Cuboid, Bot];
const LINKS = ["/plan", "/devis-editeur", "/plan", "/plan"];

function Row({ item, index, cta }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const Icon = ICONS[index];
  const reverse = index % 2 === 1;
  const img = IMGS[index];
  return (
    <div ref={ref} data-testid={`showcase-row-${index}`}
         className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
      <motion.div
        className={`relative ${reverse ? "lg:order-2" : ""}`}
        initial={{ opacity: 0, x: reverse ? 40 : -40 }}
        animate={inView ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="absolute -inset-2 bg-primary/15 blur-3xl rounded-3xl pointer-events-none" aria-hidden="true" />
        <div className="group relative aspect-[4/3] rounded-3xl overflow-hidden border border-white/15 shadow-2xl bg-card">
          {img ? (
            <img src={img} alt={item.title} loading="lazy"
                 className="absolute inset-0 h-full w-full object-cover transition-transform duration-[900ms] group-hover:scale-110" />
          ) : (
            <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-primary/25 via-background to-secondary">
              <Layers className="h-24 w-24 text-primary/70" aria-hidden="true" />
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
          <motion.div
            className="absolute bottom-5 left-5 rounded-2xl bg-background/85 backdrop-blur-md border border-white/20 px-5 py-3 shadow-lg"
            initial={{ opacity: 0, y: 16 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.35 }}
          >
            <p className="num text-3xl font-extrabold text-primary leading-none">{SHOWCASE_STATS[index]}</p>
            <p className="text-[11px] text-muted-foreground mt-1">{item.statLabel}</p>
          </motion.div>
          {index === 1 && (
            <div className="absolute top-5 right-5 h-11 w-11 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-lg animate-pulse">
              <Video className="h-5 w-5" />
            </div>
          )}
        </div>
      </motion.div>

      <motion.div
        className={reverse ? "lg:order-1" : ""}
        initial={{ opacity: 0, y: 30 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.7, delay: 0.15, ease: "easeOut" }}
      >
        <div className="inline-flex items-center gap-2 mb-4">
          <span className="h-10 w-10 rounded-xl bg-primary/10 border border-primary/20 grid place-items-center">
            <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
          </span>
          <span className="overline">{item.overline}</span>
        </div>
        <h3 className="font-display text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight text-foreground">
          {item.title}
        </h3>
        <p className="mt-4 text-base text-muted-foreground leading-relaxed max-w-xl">{item.text}</p>
        <ul className="mt-6 space-y-2.5">
          {item.bullets.map((b) => (
            <li key={b} className="flex items-start gap-2.5 text-sm text-foreground">
              <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" aria-hidden="true" />
              <span>{b}</span>
            </li>
          ))}
        </ul>
        <Button asChild className="mt-8 rounded-full gap-2 group" data-testid={`showcase-cta-${index}`}>
          <Link to={LINKS[index]}>
            {cta}
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </Link>
        </Button>
      </motion.div>
    </div>
  );
}

export function FeatureShowcase() {
  const { lang } = useI18n();
  const L = SHOWCASE_I18N[lang] || SHOWCASE_I18N.fr;
  const ctaRef = useRef(null);
  const ctaInView = useInView(ctaRef, { once: true, margin: "-60px" });
  return (
    <section className="border-y border-border bg-secondary/20 relative overflow-hidden" data-testid="feature-showcase">
      <div className="absolute inset-0 grain opacity-30 pointer-events-none" />
      <div className="mx-auto max-w-[1400px] px-6 lg:px-10 py-24 lg:py-32 relative z-10">
        <div className="max-w-2xl mb-16 lg:mb-24">
          <p className="overline">{L.over}</p>
          <h2 className="mt-4 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">{L.title}</h2>
          <p className="mt-5 text-base sm:text-lg text-muted-foreground leading-relaxed">{L.sub}</p>
        </div>
        <div className="space-y-24 lg:space-y-36">
          {L.items.map((item, i) => <Row key={i} item={item} index={i} cta={L.cta} />)}
        </div>

        {/* CTA final — Essai gratuit */}
        <motion.div
          ref={ctaRef} data-testid="showcase-try-cta"
          className="mt-24 lg:mt-36 rounded-3xl border border-primary/25 bg-gradient-to-br from-primary/15 via-card to-secondary p-10 lg:p-16 text-center relative overflow-hidden"
          initial={{ opacity: 0, y: 30 }}
          animate={ctaInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.7, ease: "easeOut" }}
        >
          <div className="absolute -top-16 left-1/2 -translate-x-1/2 h-40 w-[60%] bg-primary/25 blur-3xl rounded-full pointer-events-none" aria-hidden="true" />
          <h3 className="relative font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">{L.tryTitle}</h3>
          <p className="relative mt-4 text-base sm:text-lg text-muted-foreground max-w-xl mx-auto">{L.trySub}</p>
          <Button asChild size="lg" className="relative mt-8 rounded-full h-14 px-10 text-base gap-2 group shadow-xl" data-testid="showcase-try-btn">
            <Link to="/inscription">
              <Sparkles className="h-5 w-5" />
              {L.tryCta}
              <ArrowRight className="h-5 w-5 transition-transform group-hover:translate-x-1" />
            </Link>
          </Button>
          <p className="relative mt-4 text-xs text-muted-foreground">{L.tryNote}</p>
        </motion.div>
      </div>
    </section>
  );
}

export default FeatureShowcase;
