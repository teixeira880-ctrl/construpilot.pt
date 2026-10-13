import { useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Circle, X, Rocket, ArrowRight } from "lucide-react";

const DISMISS_KEY = "construpilot_checklist_dismissed";

/** Étapes calculées sur les vraies données du compte (`GET /api/onboarding/status`). */
export function StarterChecklist({ status, isPro = true }) {
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(DISMISS_KEY) === "1");
  if (!status) return null;
  const s = status;

  const items = isPro ? [
    { done: s.client, title: "Adicione um cliente", desc: "Uma ficha de cliente reutilizada em todos os seus orçamentos, faturas e obras.", to: "/clients", cta: "Adicionar" },
    { done: s.chantier, title: "Crie um processo de obra", desc: "Cliente, plantas, orçamentos e fotografias reunidos — acabou-se a reintrodução de uma ferramenta para outra.", to: "/chantiers", cta: "Criar" },
    { done: s.plan, title: "Meça uma planta", desc: "Importe um PDF, DXF ou DWG e deixe a IA calcular as áreas.", to: "/plan", cta: "Medir" },
    { done: s.quote, title: "Crie um orçamento", desc: "O seu primeiro orçamento pronto a enviar, com o IVA do seu país.", to: "/devis-editeur", cta: "Criar" },
    { done: s.page_published, title: "Publique a página da sua empresa", desc: "Uma página pública com as suas obras realizadas e um formulário de pedido de orçamento.", to: "/ma-page", cta: "Publicar" },
  ] : [
    { done: s.project, title: "Estime os seus trabalhos", desc: "Descreva o seu projeto e obtenha uma estimativa detalhada em 30 s.", to: "/estimation", cta: "Estimar" },
    { done: false, title: "Compare os preços materiais", desc: "Consulte os preços de mercado para orçamentar os seus trabalhos.", to: "/precos", cta: "Ver os preços" },
    { done: false, title: "Utilize as calculadoras", desc: "Superfícies, volumes e quantidades em poucos segundos.", to: "/calculadoras", cta: "Calcular" },
  ];

  const doneCount = items.filter((i) => i.done).length;
  if (doneCount === items.length || dismissed) return null;
  const close = () => { localStorage.setItem(DISMISS_KEY, "1"); setDismissed(true); };

  return (
    <div className="surface p-6 border-2 border-primary/30" data-testid="starter-checklist">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center shrink-0"><Rocket className="h-5 w-5 text-primary" /></div>
          <div>
            <h3 className="font-bold" data-testid="starter-checklist-progress">Primeiros passos — {doneCount}/{items.length}</h3>
            <p className="text-xs text-muted-foreground">Etapas reais, marcadas automaticamente assim que são feitas.</p>
          </div>
        </div>
        <button onClick={close} data-testid="checklist-dismiss" className="text-muted-foreground hover:text-foreground" title="Ocultar"><X className="h-4 w-4" /></button>
      </div>
      <div className="mt-4 h-1.5 w-full rounded-full bg-border overflow-hidden">
        <div className="h-full bg-primary transition-all duration-500" style={{ width: `${(doneCount / items.length) * 100}%` }} />
      </div>
      <div className="mt-5 grid gap-2">
        {items.map((it) => (
          <div key={it.to} className={`flex items-center gap-3 rounded-sm border border-border p-3 ${it.done ? "opacity-60" : ""}`} data-testid={`checklist-item-${it.to.slice(1)}`} data-done={it.done ? "1" : "0"}>
            {it.done ? <CheckCircle2 className="h-5 w-5 text-primary shrink-0" /> : <Circle className="h-5 w-5 text-muted-foreground shrink-0" />}
            <div className="min-w-0 flex-1">
              <p className={`text-sm font-semibold ${it.done ? "line-through" : ""}`}>{it.title}</p>
              {!it.done && <p className="text-xs text-muted-foreground">{it.desc}</p>}
            </div>
            {!it.done && <Link to={it.to} data-testid={`checklist-cta-${it.to.slice(1)}`} className="text-primary text-xs font-semibold inline-flex items-center gap-1 hover:underline shrink-0">{it.cta} <ArrowRight className="h-3 w-3" /></Link>}
          </div>
        ))}
      </div>
    </div>
  );
}
