import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion, useInView } from "framer-motion";
import {
  ScanLine, FileText, Cuboid, Bot, ArrowRight, CheckCircle2, Video, Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/context/I18nContext";

const IMG_BLUEPRINT = "https://images.unsplash.com/photo-1721244654392-9c912a6eb236?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";
const IMG_TABLET = "https://images.pexels.com/photos/8961008/pexels-photo-8961008.jpeg?auto=compress&cs=tinysrgb&dpr=2&w=1200";
const IMG_REBAR = "https://images.unsplash.com/photo-1531834685032-c34bf0d84c77?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";

const SHOWCASE = [
  {
    id: "analyse-ia", icon: ScanLine, img: IMG_BLUEPRINT, to: "/plan",
    overline: "Analyse IA des plans",
    title: "Un plan → un métré béton complet",
    text: "Détectez automatiquement murs, ouvertures, poteaux, poutres, semelles et planchers. Volumes de béton (m³) et aciers (kg) calculés instantanément, épaisseurs et sections ajustables.",
    bullets: ["Détection murs / poteaux / poutres", "Métré béton + aciers automatiques", "Épaisseurs & sections réglables"],
    stat: "263 m³", statLabel: "béton chiffré en 1 clic",
  },
  {
    id: "devis-express", icon: FileText, img: IMG_TABLET, to: "/devis-editeur", reverse: true,
    overline: "Devis express",
    title: "Générez un devis en un éclair",
    text: "Depuis un plan, une simple description ou même une vidéo filmée sur le chantier : l'IA transcrit, structure et chiffre vos lignes depuis votre bibliothèque de prix.",
    bullets: ["Devis depuis le plan mesuré", "Devis depuis une vidéo (voix + photos)", "Prix auto depuis votre bibliothèque"],
    stat: "30 s", statLabel: "du plan au devis PDF", badge: Video,
  },
  {
    id: "maquette-3d", icon: Cuboid, img: IMG_REBAR, to: "/plan",
    overline: "Maquette 3D",
    title: "Visualisez la structure en 3D",
    text: "Les volumes détectés deviennent une maquette 3D interactive : voiles, planchers, poteaux, poutres et semelles. Exportez une capture PNG à joindre au devis client.",
    bullets: ["Vue 3D des volumes détectés", "Export PNG joint au devis", "Comparaison de réglages par chantier"],
    stat: "3D", statLabel: "générée depuis le métré",
  },
  {
    id: "assistant-ia", icon: Bot, img: null, to: "/plan", reverse: true,
    overline: "Assistant IA & Entreprise",
    title: "Corrigez, chiffrez, pilotez",
    text: "Guidez l'IA en langage naturel pour corriger la détection, chiffrez marge et main d'œuvre, puis pilotez votre entreprise : factures, situations de travaux, suivi de chantier et RH.",
    bullets: ["Assistant IA de correction du plan", "Marge & prix de vente estimés", "Factures, situations & suivi chantier"],
    stat: "100%", statLabel: "de la vente au chantier",
  },
];

function Row({ item, index }) {
  const { t } = useI18n();
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const Icon = item.icon;
  const Badge = item.badge;
  return (
    <div ref={ref} data-testid={`showcase-row-${item.id}`}
         className="grid lg:grid-cols-2 gap-10 lg:gap-16 items-center">
      {/* Visual */}
      <motion.div
        className={`relative ${item.reverse ? "lg:order-2" : ""}`}
        initial={{ opacity: 0, x: item.reverse ? 40 : -40 }}
        animate={inView ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.7, ease: "easeOut" }}
      >
        <div className="absolute -inset-2 bg-primary/15 blur-3xl rounded-3xl pointer-events-none" aria-hidden="true" />
        <div className="group relative aspect-[4/3] rounded-3xl overflow-hidden border border-white/15 shadow-2xl bg-card">
          {item.img ? (
            <img src={item.img} alt={item.title} loading="lazy"
                 className="absolute inset-0 h-full w-full object-cover transition-transform duration-[900ms] group-hover:scale-110" />
          ) : (
            <div className="absolute inset-0 grid place-items-center bg-gradient-to-br from-primary/25 via-background to-secondary">
              <Layers className="h-24 w-24 text-primary/70" aria-hidden="true" />
            </div>
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
          {/* Floating interactive stat */}
          <motion.div
            className="absolute bottom-5 left-5 rounded-2xl bg-background/85 backdrop-blur-md border border-white/20 px-5 py-3 shadow-lg"
            initial={{ opacity: 0, y: 16 }}
            animate={inView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.5, delay: 0.35 }}
          >
            <p className="num text-3xl font-extrabold text-primary leading-none">{item.stat}</p>
            <p className="text-[11px] text-muted-foreground mt-1">{item.statLabel}</p>
          </motion.div>
          {Badge && (
            <div className="absolute top-5 right-5 h-11 w-11 rounded-full bg-primary text-primary-foreground grid place-items-center shadow-lg animate-pulse">
              <Badge className="h-5 w-5" />
            </div>
          )}
        </div>
      </motion.div>

      {/* Text */}
      <motion.div
        className={item.reverse ? "lg:order-1" : ""}
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
        <Button asChild className="mt-8 rounded-full gap-2 group" data-testid={`showcase-cta-${item.id}`}>
          <Link to={item.to}>
            {t("landing.showcase.cta", "Découvrir")}
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
          </Link>
        </Button>
      </motion.div>
    </div>
  );
}

export function FeatureShowcase() {
  const { t } = useI18n();
  return (
    <section className="border-y border-border bg-secondary/20 relative overflow-hidden" data-testid="feature-showcase">
      <div className="absolute inset-0 grain opacity-30 pointer-events-none" />
      <div className="mx-auto max-w-[1400px] px-6 lg:px-10 py-24 lg:py-32 relative z-10">
        <div className="max-w-2xl mb-16 lg:mb-24">
          <p className="overline">{t("landing.showcase.overline", "La démo en images")}</p>
          <h2 className="mt-4 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
            {t("landing.showcase.title", "Tout le chantier, du plan au devis signé")}
          </h2>
          <p className="mt-5 text-base sm:text-lg text-muted-foreground leading-relaxed">
            {t("landing.showcase.sub", "Découvrez comment ConstruPilot transforme un plan en métré, en maquette 3D et en devis chiffré — en quelques secondes.")}
          </p>
        </div>
        <div className="space-y-24 lg:space-y-36">
          {SHOWCASE.map((item, i) => <Row key={item.id} item={item} index={i} />)}
        </div>
      </div>
    </section>
  );
}

export default FeatureShowcase;
