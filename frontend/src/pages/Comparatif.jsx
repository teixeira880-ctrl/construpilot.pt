import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, X, Minus, Cuboid, Sparkles, Globe2, Megaphone, ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SEO } from "@/components/SEO";
import { SectionTitle } from "@/components/Bits";

const COLS = ["ConstruPilot", "Costructor", "Obat", "Tolteck", "Graneet", "Batigest", "OptimBTP", "ProGBat"];

const ROWS = [
  { label: "Preço de entrada", values: ["Gratuit → 39€", "Gratuit → 12,50€", "32€/mois", "25€/mois", "Sur devis", "Sur devis", "Sur devis", "29€/mois"] },
  { label: "Versão gratuita ilimitada", values: [true, true, false, false, false, false, false, false] },
  { label: "IA (extraction matériaux, coaching)", values: [true, "~", false, false, false, false, false, false] },
  { label: "Render 3D desde un plan 2D", values: [true, false, false, false, false, false, false, false] },
  { label: "Estimativa por foto", values: [true, false, false, false, false, false, false, false] },
  { label: "Multi-langue (7 langues)", values: [true, false, false, false, false, false, false, false] },
  { label: "Calculateurs métier (placo, carrelage…)", values: [true, "~", "~", false, false, false, false, "~"] },
  { label: "Comparador de preços fornecedores", values: [true, true, false, false, false, false, false, "~"] },
  { label: "Suivi de chantier (réserves, CR, photos)", values: [true, "~", true, false, true, true, true, true] },
  { label: "Module RH / pointage GPS", values: [true, false, true, false, false, false, true, true] },
  { label: "Orçamento & facturation", values: [true, true, true, true, true, true, true, true] },
  { label: "Assinatura electrónica de orçamentos", values: [true, "~", true, "~", true, true, "~", true] },
  { label: "Fatura électronique Factur-X (2026)", values: ["~", true, "~", "~", true, true, "~", true] },
  { label: "Facturação por autos de medição", values: [false, false, true, false, true, true, true, true] },
  { label: "Marketing & captation de leads intégrés", values: [true, false, false, false, false, false, false, false] },
];

const REASONS = [
  { icon: Cuboid, title: "Render 3D unique", text: "Gere une visualisation 3D desde un simple plan 2D. Nenhum autre logiciel BTP grand public ne le propose." },
  { icon: Sparkles, title: "IA nativa de ponta a ponta", text: "Extracção de materiais, coaching de obra e análise de orçamentos por IA — muito além de um simples gerador." },
  { icon: Globe2, title: "Multi-idioma (7 línguas)", text: "A única ferramenta pensada para internacional: Portugal, Espanha, Brasil e mais, quando os outros ficam restritos ao seu mercado." },
  { icon: Megaphone, title: "Aquisição integrada", text: "Landing dupla Profissional/Particular, captação de leads e painel Ads. Os seus concorrentes param no negócio, você não." },
];

const Cell = ({ v, highlight }) => {
  if (v === true)
    return <Check className={`h-5 w-5 mx-auto ${highlight ? "text-primary" : "text-emerald-500"}`} strokeWidth={2.5} />;
  if (v === false)
    return <X className="h-4 w-4 mx-auto text-muted-foreground/40" />;
  if (v === "~")
    return <Minus className="h-4 w-4 mx-auto text-amber-500" title="Partiel / via partenaire" />;
  return <span className={`num text-sm font-semibold ${highlight ? "text-primary" : ""}`}>{v}</span>;
};

const container = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.08 } } };
const item = { hidden: { opacity: 0, y: 18 }, visible: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } } };

export default function Comparatif() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Quelle est la différence entre ConstruPilot et Costructor, Obat ou Tolteck ?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "ConstruPilot combine l'IA (extraction de matériaux, coaching), le rendu 3D desde un plan 2D, une interface multi-langue et une brique marketing intégrée — des atouts uniques face à Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP et ProGBat, tout en restant gratuit pour démarrer.",
        },
      },
      {
        "@type": "Question",
        name: "ConstruPilot est-il conforme à la facture électronique 2026 ?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "ConstruPilot génère des factures au format Factur-X. La transmission via plateforme agréée (PDP) est en cours de finalisation pour la réforme 2026.",
        },
      },
    ],
  };

  return (
    <>
      <SEO
        title="ConstruPilot vs Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP & ProGBat"
        description="Comparatif complet des logiciels BTP 2026. ConstruPilot combine IA, rendu 3D, multi-langue et marketing intégré, gratuit pour démarrer. Découvrez pourquoi il se démarque."
        canonical="/comparatif"
        keywords="logiciel BTP, comparatif, devis, facturation, Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP, ProGBat, ConstruPilot"
        jsonLd={jsonLd}
      />

      <section className="text-center max-w-3xl mx-auto" data-testid="comparatif-hero">
        <p className="overline">Comparatif 2026</p>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
          ConstruPilot face aux <span className="text-primary">logiciels BTP</span> du marché
        </h1>
        <p className="mt-4 text-base text-muted-foreground">
          Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP, ProGBat… Voici, en toute transparence,
          ce que chacun sait faire — et pourquoi ConstruPilot va plus loin.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button asChild className="rounded-sm gap-2" data-testid="comparatif-cta-signup">
            <Link to="/inscription">Essayer gratuitement <ArrowRight className="h-4 w-4" /></Link>
          </Button>
          <Button asChild variant="outline" className="rounded-sm" data-testid="comparatif-cta-pricing">
            <Link to="/tarifs">Ver les tarifs</Link>
          </Button>
        </div>
      </section>

      <div className="mt-14 surface rounded-md overflow-hidden" data-testid="comparatif-table-wrap">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm min-w-[820px]" data-testid="comparatif-table">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left font-display font-semibold p-4 sticky left-0 bg-card z-10 min-w-[220px]">
                  Fonctionnalité
                </th>
                {COLS.map((c, i) => (
                  <th
                    key={c}
                    className={`p-4 text-center font-display font-bold whitespace-nowrap ${
                      i === 0 ? "bg-primary/10 text-primary rounded-t-md" : "text-foreground"
                    }`}
                    data-testid={`comparatif-col-${i}`}
                  >
                    {c}
                    {i === 0 && <span className="block text-[10px] font-normal text-primary/70 mt-0.5">Notre solution</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row, ri) => (
                <tr key={row.label} className="border-b border-border/60 hover:bg-muted/30 transition-colors" data-testid={`comparatif-row-${ri}`}>
                  <td className="p-4 text-left font-medium sticky left-0 bg-card z-10">{row.label}</td>
                  {row.values.map((v, ci) => (
                    <td
                      key={ci}
                      className={`p-4 text-center ${ci === 0 ? "bg-primary/5" : ""}`}
                    >
                      <Cell v={v} highlight={ci === 0} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-4 px-4 py-3 text-xs text-muted-foreground border-t border-border">
          <span className="flex items-center gap-1"><Check className="h-3.5 w-3.5 text-emerald-500" /> Inclus</span>
          <span className="flex items-center gap-1"><Minus className="h-3.5 w-3.5 text-amber-500" /> Partiel / via partenaire</span>
          <span className="flex items-center gap-1"><X className="h-3.5 w-3.5 text-muted-foreground/40" /> Non proposé</span>
        </div>
      </div>

      <div className="mt-16">
        <SectionTitle over="Porquê escolher-nos" title="4 razões que fazem a diferença">
          Là où les autres logiciels s'arrêtent au devis et à la facture, ConstruPilot ajoute l'innovation
          et l'acquisition — sans sacrifier les fondamentaux métier.
        </SectionTitle>
        <motion.div
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          variants={container}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.2 }}
          data-testid="comparatif-reasons"
        >
          {REASONS.map((r) => (
            <motion.div key={r.title} variants={item} className="surface p-6 rounded-md">
              <div className="h-11 w-11 rounded-xl bg-primary/10 grid place-items-center mb-4">
                <r.icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="font-display font-semibold">{r.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{r.text}</p>
            </motion.div>
          ))}
        </motion.div>
      </div>

      <div className="mt-14 surface rounded-md p-6 flex gap-4 items-start" data-testid="comparatif-honest">
        <ShieldCheck className="h-6 w-6 text-primary shrink-0 mt-0.5" />
        <div>
          <h3 className="font-display font-semibold">Notre engagement de transparence</h3>
          <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
            Graneet et Batigest restent des références pour le pilotage financier avancé et l'écosystème
            comptable des grosses PME. ConstruPilot finalise la facturation à l'avancement et la transmission
            Factur-X via plateforme agréée (réforme 2026). Notre parti pris : rester le logiciel BTP le plus
            innovant et le plus accessible, gratuit pour démarrer.
          </p>
        </div>
      </div>

      <div className="mt-14 text-center rounded-md bg-primary/10 border border-primary/20 p-10" data-testid="comparatif-final-cta">
        <h2 className="font-display text-2xl lg:text-3xl font-bold tracking-tight">
          Testez ConstruPilot gratuitement en 30 secondes
        </h2>
        <p className="mt-3 text-muted-foreground max-w-xl mx-auto">
          Sans carte bancaire. Gere votre premier devis IA, un rendu 3D ou une estimation par photo dès maintenant.
        </p>
        <Button asChild className="rounded-sm mt-6 gap-2" size="lg" data-testid="comparatif-final-cta-btn">
          <Link to="/inscription">Criar mon compte gratuit <ArrowRight className="h-4 w-4" /></Link>
        </Button>
      </div>
    </>
  );
}
