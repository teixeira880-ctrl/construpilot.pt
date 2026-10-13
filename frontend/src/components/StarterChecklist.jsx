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
    { done: s.client, title: "Ajoutez un client", desc: "Une fiche client réutilisée dans tous vos devis, factures et chantiers.", to: "/clients", cta: "Ajouter" },
    { done: s.chantier, title: "Créez un dossier chantier", desc: "Client, plans, devis et photos réunis — plus de ressaisie d'un outil à l'autre.", to: "/chantiers", cta: "Créer" },
    { done: s.plan, title: "Mesurez un plan", desc: "Importez un PDF, DXF ou DWG et laissez l'IA calculer les surfaces.", to: "/plan", cta: "Mesurer" },
    { done: s.quote, title: "Créez un devis", desc: "Votre premier devis prêt à envoyer, avec la TVA de votre pays.", to: "/devis-editeur", cta: "Créer" },
    { done: s.page_published, title: "Publiez votre page entreprise", desc: "Une page publique avec vos réalisations et un formulaire de demande de devis.", to: "/ma-page", cta: "Publier" },
  ] : [
    { done: s.project, title: "Estimez vos travaux", desc: "Décrivez votre projet et obtenez une estimation détaillée en 30 s.", to: "/estimation", cta: "Estimer" },
    { done: false, title: "Comparez les prix matériaux", desc: "Consultez les prix du marché pour budgéter vos travaux.", to: "/prix", cta: "Voir les prix" },
    { done: false, title: "Utilisez les calculateurs", desc: "Surfaces, volumes et quantités en quelques secondes.", to: "/calculateurs", cta: "Calculer" },
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
            <h3 className="font-bold" data-testid="starter-checklist-progress">Prise en main — {doneCount}/{items.length}</h3>
            <p className="text-xs text-muted-foreground">Des étapes réelles, cochées automatiquement dès qu'elles sont faites.</p>
          </div>
        </div>
        <button onClick={close} data-testid="checklist-dismiss" className="text-muted-foreground hover:text-foreground" title="Masquer"><X className="h-4 w-4" /></button>
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
