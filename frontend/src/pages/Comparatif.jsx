import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Check, X, Minus, Cuboid, Sparkles, Globe2, Megaphone, ArrowRight, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SEO } from "@/components/SEO";
import { SectionTitle } from "@/components/Bits";

const COLS = ["ConstruPilot", "Costructor", "Obat", "Tolteck", "Graneet", "Batigest", "OptimBTP", "ProGBat"];

const ROWS = [
  { label: "Preço de entrada", values: ["Gratuito → 39€", "Gratuito → 12,50€", "32€/mês", "25€/mês", "Sob orçamento", "Sob orçamento", "Sob orçamento", "29€/mês"] },
  { label: "Versão gratuita ilimitada", values: [true, true, false, false, false, false, false, false] },
  { label: "IA (extração de materiais, coaching)", values: [true, "~", false, false, false, false, false, false] },
  { label: "Render 3D a partir de uma planta 2D", values: [true, false, false, false, false, false, false, false] },
  { label: "Estimativa por foto", values: [true, false, false, false, false, false, false, false] },
  { label: "Multi-idioma (7 línguas)", values: [true, false, false, false, false, false, false, false] },
  { label: "Calculadoras profissionais (pladur, cerâmicos…)", values: [true, "~", "~", false, false, false, false, "~"] },
  { label: "Comparador de preços de fornecedores", values: [true, true, false, false, false, false, false, "~"] },
  { label: "Acompanhamento de obra (reservas, RC, fotos)", values: [true, "~", true, false, true, true, true, true] },
  { label: "Módulo RH / picagem GPS", values: [true, false, true, false, false, false, true, true] },
  { label: "Orçamentos e faturação", values: [true, true, true, true, true, true, true, true] },
  { label: "Assinatura eletrónica de orçamentos", values: [true, "~", true, "~", true, true, "~", true] },
  { label: "Fatura eletrónica Factur-X (2026)", values: ["~", true, "~", "~", true, true, "~", true] },
  { label: "Faturação por autos de medição", values: [false, false, true, false, true, true, true, true] },
  { label: "Marketing e captação de leads integrados", values: [true, false, false, false, false, false, false, false] },
];

const REASONS = [
  { icon: Cuboid, title: "Render 3D único", text: "Gera uma visualização 3D a partir de uma simples planta 2D. Nenhum outro software de construção para o grande público oferece esta funcionalidade." },
  { icon: Sparkles, title: "IA nativa de ponta a ponta", text: "Extração de materiais, coaching de obra e análise de orçamentos por IA — muito além de um simples gerador." },
  { icon: Globe2, title: "Multi-idioma (7 línguas)", text: "A única ferramenta pensada para internacional: Portugal, Espanha, Brasil e mais, quando os outros ficam restritos ao seu mercado." },
  { icon: Megaphone, title: "Aquisição integrada", text: "Landing dupla Profissional/Particular, captação de leads e painel Ads. Os seus concorrentes param no negócio, você não." },
];

const Cell = ({ v, highlight }) => {
  if (v === true)
    return <Check className={`h-5 w-5 mx-auto ${highlight ? "text-primary" : "text-emerald-500"}`} strokeWidth={2.5} />;
  if (v === false)
    return <X className="h-4 w-4 mx-auto text-muted-foreground/40" />;
  if (v === "~")
    return <Minus className="h-4 w-4 mx-auto text-amber-500" title="Parcial / via parceiro" />;
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
        name: "Qual é a diferença entre o ConstruPilot e o Costructor, Obat ou Tolteck?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "O ConstruPilot combina IA (extração de materiais, coaching), render 3D a partir de uma planta 2D, interface multi-idioma e uma componente de marketing integrada — vantagens únicas face a Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP e ProGBat, mantendo-se gratuito para começar.",
        },
      },
      {
        "@type": "Question",
        name: "O ConstruPilot está conforme à fatura eletrónica 2026?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "O ConstruPilot gera faturas no formato Factur-X. A transmissão via plataforma certificada (PDP) está em fase de finalização para a reforma de 2026.",
        },
      },
    ],
  };

  return (
    <>
      <SEO
        title="ConstruPilot vs Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP e ProGBat"
        description="Comparativo completo de softwares de construção 2026. O ConstruPilot combina IA, render 3D, multi-idioma e marketing integrado, gratuito para começar. Descubra porque se destaca."
        canonical="/comparatif"
        keywords="software BTP, comparativo, orçamento, facturação, Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP, ProGBat, ConstruPilot"
        jsonLd={jsonLd}
      />

      <section className="text-center max-w-3xl mx-auto" data-testid="comparatif-hero">
        <p className="overline">Comparativo 2026</p>
        <h1 className="mt-2 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
          ConstruPilot face aos <span className="text-primary">softwares de construção</span> do mercado
        </h1>
        <p className="mt-4 text-base text-muted-foreground">
          Costructor, Obat, Tolteck, Graneet, Batigest, OptimBTP, ProGBat… Eis, com toda a transparência,
          o que cada um sabe fazer — e porque é que o ConstruPilot vai mais longe.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button asChild className="rounded-sm gap-2" data-testid="comparatif-cta-signup">
            <Link to="/inscription">Experimentar gratuitamente <ArrowRight className="h-4 w-4" /></Link>
          </Button>
          <Button asChild variant="outline" className="rounded-sm" data-testid="comparatif-cta-pricing">
            <Link to="/planos">Ver os planos</Link>
          </Button>
        </div>
      </section>

      <div className="mt-14 surface rounded-md overflow-hidden" data-testid="comparatif-table-wrap">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm min-w-[820px]" data-testid="comparatif-table">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left font-display font-semibold p-4 sticky left-0 bg-card z-10 min-w-[220px]">
                  Funcionalidade
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
                    {i === 0 && <span className="block text-[10px] font-normal text-primary/70 mt-0.5">A nossa solução</span>}
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
          <span className="flex items-center gap-1"><Check className="h-3.5 w-3.5 text-emerald-500" /> Incluído</span>
          <span className="flex items-center gap-1"><Minus className="h-3.5 w-3.5 text-amber-500" /> Parcial / via parceiro</span>
          <span className="flex items-center gap-1"><X className="h-3.5 w-3.5 text-muted-foreground/40" /> Não proposto</span>
        </div>
      </div>

      <div className="mt-16">
        <SectionTitle over="Porquê escolher-nos" title="4 razões que fazem a diferença">
          Onde os outros softwares se limitam ao orçamento e à fatura, o ConstruPilot acrescenta a inovação
          e a aquisição — sem sacrificar os fundamentos do negócio.
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
          <h3 className="font-display font-semibold">O nosso compromisso de transparência</h3>
          <p className="mt-2 text-sm text-muted-foreground leading-relaxed">
            O Graneet e o Batigest continuam a ser referências para a gestão financeira avançada e para o
            ecossistema contabilístico das grandes PME. O ConstruPilot está a finalizar a faturação por autos
            de medição e a transmissão Factur-X via plataforma certificada (reforma de 2026). O nosso compromisso:
            manter-nos como o software de construção mais inovador e mais acessível, gratuito para começar.
          </p>
        </div>
      </div>

      <div className="mt-14 text-center rounded-md bg-primary/10 border border-primary/20 p-10" data-testid="comparatif-final-cta">
        <h2 className="font-display text-2xl lg:text-3xl font-bold tracking-tight">
          Experimente o ConstruPilot gratuitamente em 30 segundos
        </h2>
        <p className="mt-3 text-muted-foreground max-w-xl mx-auto">
          Sem cartão bancário. Gere o seu primeiro orçamento com IA, uma renderização 3D ou uma estimativa por foto já de seguida.
        </p>
        <Button asChild className="rounded-sm mt-6 gap-2" size="lg" data-testid="comparatif-final-cta-btn">
          <Link to="/inscription">Criar a minha conta gratuita <ArrowRight className="h-4 w-4" /></Link>
        </Button>
      </div>
    </>
  );
}
