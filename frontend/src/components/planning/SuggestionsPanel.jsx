import { Lightbulb, AlertTriangle, CheckCircle2, Info, Users } from "lucide-react";
import { Button } from "@/components/ui/button";

const STYLE = {
  critical: { cls: "border-red-300 bg-red-50 text-red-900", Icon: AlertTriangle },
  high: { cls: "border-orange-300 bg-orange-50 text-orange-900", Icon: AlertTriangle },
  medium: { cls: "border-amber-300 bg-amber-50 text-amber-900", Icon: Users },
  info: { cls: "border-blue-200 bg-blue-50 text-blue-900", Icon: Info },
  success: { cls: "border-emerald-300 bg-emerald-50 text-emerald-900", Icon: CheckCircle2 },
};

export function SuggestionsPanel({ suggestions = [], onApplyCapacity, onHighlight }) {
  return (
    <section className="surface" data-testid="planning-suggestions">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Lightbulb className="h-4 w-4 text-primary" />
        <p className="font-display font-bold text-sm">Propositions de réorganisation</p>
        <span className="text-[11px] text-muted-foreground">gains mesurés en rejouant le planning — aucune estimation IA</span>
      </div>
      <div className="p-3 grid gap-2">
        {suggestions.length === 0 && <p className="text-sm text-muted-foreground px-1">Rien à signaler : planning cohérent.</p>}
        {suggestions.map((s, i) => {
          const { cls, Icon } = STYLE[s.severity] || STYLE.info;
          return (
            <div key={i} className={`border rounded-sm p-3 text-xs flex gap-2 ${cls}`} data-testid={`suggestion-${s.kind}-${i}`}>
              <Icon className="h-4 w-4 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="font-semibold">{s.title}</p>
                <p className="opacity-90 mt-0.5">{s.detail}</p>
                <div className="flex flex-wrap gap-2 mt-2">
                  {s.task_ids?.length > 0 && (
                    <button type="button" className="underline opacity-80 hover:opacity-100" onClick={() => onHighlight?.(s.task_ids[0])}>
                      Voir la tâche {s.task_ids.join(", ")}
                    </button>
                  )}
                  {s.action?.type === "capacity" && (
                    <Button size="sm" variant="outline" className="h-6 rounded-sm text-[11px] bg-white" onClick={() => onApplyCapacity(s.action.resource, s.action.value)}
                            data-testid={`suggestion-apply-${i}`}>
                      Passer à {s.action.value} équipes « {s.action.resource} »
                    </Button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
