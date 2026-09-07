import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, X, Rocket, ArrowRight } from "lucide-react";

const DISMISS_KEY = "construpilot_checklist_dismissed";

export function StarterChecklist({ projectDone, planDone, quoteDone, isPro = true }) {
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === "1"
  );

  const items = isPro ? [
    {
      done: projectDone,
      title: "Estime a tua obra",
      desc: "Descreve um projeto e obtém uma estimativa detalhada em 30 s.",
      to: "/estimation",
      cta: "Estimar",
    },
    {
      done: planDone,
      title: "Mede uma planta",
      desc: "Importa uma planta e deixa a IA calcular as áreas.",
      to: "/plan",
      cta: "Medir",
    },
    {
      done: quoteDone,
      title: "Cria um orçamento",
      desc: "Transforma a tua estimativa num orçamento pronto a enviar.",
      to: "/devis-editeur",
      cta: "Criar",
    },
  ] : [
    {
      done: projectDone,
      title: "Estime a tua obra",
      desc: "Descreve o teu projeto e obtém uma estimativa detalhada em 30 s.",
      to: "/estimation",
      cta: "Estimar",
    },
    {
      done: false,
      title: "Compara os preços dos materiais",
      desc: "Consulta os preços de mercado para orçamentar a tua obra.",
      to: "/prix",
      cta: "Ver os preços",
    },
    {
      done: false,
      title: "Usa as calculadoras",
      desc: "Áreas, volumes e quantidades em segundos.",
      to: "/calculateurs",
      cta: "Calcular",
    },
  ];

  const doneCount = items.filter((i) => i.done).length;
  const allDone = doneCount === items.length;

  // Escondida se tudo estiver feito, ou se o utilizador a fechou
  if (allDone || dismissed) return null;

  const close = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  };

  return (
    <div className="surface p-6 border-2 border-primary/30" data-testid="starter-checklist">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <Rocket className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h3 className="font-bold">Começar — {doneCount}/{items.length}</h3>
            <p className="text-xs text-muted-foreground">Alguns passos para tirar o melhor partido do ConstruPilot.</p>
          </div>
        </div>
        <button onClick={close} data-testid="checklist-dismiss"
                className="text-muted-foreground hover:text-foreground" title="Ocultar">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* barra de progresso */}
      <div className="mt-4 h-1.5 w-full rounded-full bg-border overflow-hidden">
        <div className="h-full bg-primary transition-all duration-500"
             style={{ width: `${(doneCount / items.length) * 100}%` }} />
      </div>

      <div className="mt-5 grid gap-2">
        {items.map((it) => (
          <div key={it.to}
               className={`flex items-center gap-3 rounded-sm border p-3 ${it.done ? "border-border opacity-60" : "border-border"}`}
               data-testid={`checklist-item-${it.to.slice(1)}`}>
            {it.done
              ? <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
              : <Circle className="h-5 w-5 text-muted-foreground shrink-0" />}
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-semibold ${it.done ? "line-through" : ""}`}>{it.title}</p>
              {!it.done && <p className="text-xs text-muted-foreground">{it.desc}</p>}
            </div>
            {!it.done && (
              <Link to={it.to} data-testid={`checklist-cta-${it.to.slice(1)}`}
                    className="text-primary text-xs font-semibold inline-flex items-center gap-1 hover:underline shrink-0">
                {it.cta} <ArrowRight className="h-3 w-3" />
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
