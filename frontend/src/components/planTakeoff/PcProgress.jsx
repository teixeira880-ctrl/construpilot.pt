import { useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Hammer } from "lucide-react";
import { api } from "@/lib/api";

export const PcProgress = ({ planId, planning, progress }) => {
  const phases = planning?.phases || [];
  const [done, setDone] = useState(new Set(progress?.done || []));
  if (!phases.length) return null;
  const pct = Math.round((100 * done.size) / phases.length);

  const toggle = async (i) => {
    const next = new Set(done);
    if (next.has(i)) next.delete(i); else next.add(i);
    setDone(next);
    try {
      await api.post(`/takeoffs/${planId}/pc-study/progress`, { done: [...next] });
      toast.success("Progresso atualizado — visível pelo seu cliente");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
      setDone(done);
    }
  };

  return (
    <div className="rounded-sm border border-border p-2.5 space-y-2 mt-2"
         data-testid="pc-progress-section">
      <p className="text-xs font-semibold flex items-center gap-1.5">
        <Hammer className="h-3.5 w-3.5 text-primary" />
        Progresso da obra — {pct} % (visível pelo cliente na sua página)
      </p>
      <div className="h-1.5 bg-muted rounded-full overflow-hidden">
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1">
        {phases.map((ph, i) => (
          <label key={i} className="flex items-center gap-2 text-xs cursor-pointer py-0.5"
                 data-testid={`pc-progress-phase-${i}`}>
            <input type="checkbox" checked={done.has(i)} onChange={() => toggle(i)}
                   className="accent-primary shrink-0"
                   data-testid={`pc-progress-check-${i}`} />
            <span className={done.has(i) ? "line-through text-muted-foreground" : ""}>
              {ph.name}
            </span>
            {done.has(i) && <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />}
          </label>
        ))}
      </div>
    </div>
  );
};
