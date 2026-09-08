import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, X, Rocket, ArrowRight } from "lucide-react";
import { useI18n } from "@/context/I18nContext";

const DISMISS_KEY = "construpilot_checklist_dismissed";

export function StarterChecklist({ projectDone, planDone, quoteDone, isPro = true }) {
  const { t } = useI18n();
  const [dismissed, setDismissed] = useState(
    () => localStorage.getItem(DISMISS_KEY) === "1"
  );

  const items = isPro ? [
    {
      done: projectDone,
      title: t("dash.checklist.estimate.title"),
      desc: t("dash.checklist.estimate.desc_pro"),
      to: "/estimation",
      cta: t("dash.checklist.estimate.cta"),
    },
    {
      done: planDone,
      title: t("dash.checklist.plan.title"),
      desc: t("dash.checklist.plan.desc"),
      to: "/plan",
      cta: t("dash.checklist.plan.cta"),
    },
    {
      done: quoteDone,
      title: t("dash.checklist.quote.title"),
      desc: t("dash.checklist.quote.desc"),
      to: "/devis-editeur",
      cta: t("dash.checklist.quote.cta"),
    },
  ] : [
    {
      done: projectDone,
      title: t("dash.checklist.estimate.title"),
      desc: t("dash.checklist.estimate.desc_free"),
      to: "/estimation",
      cta: t("dash.checklist.estimate.cta"),
    },
    {
      done: false,
      title: t("dash.checklist.prices.title"),
      desc: t("dash.checklist.prices.desc"),
      to: "/prix",
      cta: t("dash.checklist.prices.cta"),
    },
    {
      done: false,
      title: t("dash.checklist.calc.title"),
      desc: t("dash.checklist.calc.desc"),
      to: "/calculateurs",
      cta: t("dash.checklist.calc.cta"),
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
            <h3 className="font-bold">{t("dash.checklist.title")} — {doneCount}/{items.length}</h3>
            <p className="text-xs text-muted-foreground">{t("dash.checklist.subtitle")}</p>
          </div>
        </div>
        <button onClick={close} data-testid="checklist-dismiss"
                className="text-muted-foreground hover:text-foreground" title={t("dash.checklist.hide")}>
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
