import { Link } from "react-router-dom";
import {
  Footprints, Ruler, Receipt, FileCheck2, HardHat, Calculator, Hammer,
} from "lucide-react";

const APPS = [
  {
    to: "/escaliers",
    icon: Footprints,
    title: "Escadas",
    desc: "Calcular escada em betão armado — RGEU, Blondel.",
    testId: "apps-escadas",
  },
  {
    to: "/plan",
    icon: Ruler,
    title: "Medições",
    desc: "Medir divisões, áreas e perímetros a partir de plantas.",
    testId: "apps-medicoes",
  },
  {
    to: "/devis",
    icon: Receipt,
    title: "Orçamentos",
    desc: "Preparar orçamentos profissionais com IVA PT.",
    testId: "apps-orcamentos",
  },
  {
    to: "/particulares/autorizacao-obras",
    icon: FileCheck2,
    title: "Autorização de Obras",
    desc: "Diagnóstico e dossier RJUE para a Câmara Municipal.",
    testId: "apps-autorizacao",
  },
  {
    to: "/estudo-moradia",
    icon: HardHat,
    title: "Estudo de Moradia",
    desc: "Análise estrutural, fundações e escadas.",
    testId: "apps-estudo-moradia",
  },
  {
    to: "/calculadoras",
    icon: Calculator,
    title: "Calculadoras",
    desc: "Cálculos rápidos de construção (betão, armaduras, cargas).",
    testId: "apps-calculadoras",
  },
];

export default function AppsHub() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8" data-testid="apps-hub">
      <header className="mb-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Apps</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Todas as ferramentas ConstruPilot num só sítio.
        </p>
      </header>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {APPS.map(({ to, icon: Icon, title, desc, testId }) => (
          <Link
            key={to}
            to={to}
            data-testid={testId}
            className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/30 transition-all touch-target"
          >
            <div className="h-11 w-11 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
            </div>
            <div className="min-w-0">
              <h2 className="font-semibold text-foreground group-hover:text-primary transition-colors">
                {title}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                {desc}
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
