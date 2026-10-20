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
      title: "Estime as suas obras",
      desc: "Descreva um projeto e obtenha uma estimativa detalhada em 30 s.",
      to: "/estimation",
      cta: "Estimar",
    },
    {
      done: planDone,
      title: "Meça uma planta",
      desc: "Importe uma planta e deixe a IA calcular as áreas.",
      to: "/plan",
      cta: "Medir",
    },
    {
      done: quoteDone,
      title: "Crie um orçamento",
      desc: "Transforme a sua estimativa num orçamento pronto a enviar.",
      to: "/devis-editeur",
      cta: "Criar",
    },
  ] : [
    {
      done: projectDone,
      title: "Estime as suas obras",
      desc: "Descreva o seu projeto e obtenha uma estimativa detalhada em 30 s.",
      to: "/estimation",
      cta: "Estimar",
    },
    {
      done: false,
      title: "Compare os preços dos materiais",
      desc: "Consulte os preços de mercado para orçamentar as suas obras.",
      to: "/prix",
      cta: "Ver preços",
    },
    {
      done: false,
      title: "Use as calculadoras",
      desc: "Áreas, volumes e quantidades em poucos segundos.",
      to: "/calculateurs",
      cta: "Calcular",
    },
  ];

  const doneCount = items.filter((i) => i.done).length;
  const allDone = doneCount === items.length;

  // Masquée si tout est fait, ou si l'utilisateur l'a fermée
  if (allDone || dismissed) return null;

  const close = () => {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  };

  return (
    <div className="cp-glass rounded-3xl p-5 sm:p-6 border-2 border-primary/30" data-testid="starter-checklist">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
            <Rocket className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h3 className="font-bold">Primeiros passos — {doneCount}/{items.length}</h3>
            <p className="text-xs text-muted-foreground">Alguns passos para tirar o máximo partido do ConstruPilot.</p>
          </div>
        </div>
        <button onClick={close} data-testid="checklist-dismiss"
                className="text-muted-foreground hover:text-foreground" title="Ocultar" aria-label="Ocultar">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* barre de progression */}
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
