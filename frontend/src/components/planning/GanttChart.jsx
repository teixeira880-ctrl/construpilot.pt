import { useMemo } from "react";

const fr = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) : "");

export function GanttChart({ tasks = [], project, selected, onSelect }) {
  const total = Math.max(project?.duration_workdays || 0, 1);
  const ticks = useMemo(() => {
    const step = Math.max(1, Math.ceil(total / 14));
    const out = [];
    for (let i = 0; i <= total; i += step) out.push(i);
    return out;
  }, [total]);
  if (!tasks.length) return <p className="text-sm text-muted-foreground p-4">Nenhuma tarefa.</p>;
  return (
    <div className="overflow-x-auto" data-testid="gantt-chart">
      <div className="min-w-[760px]">
        <div className="flex text-[10px] text-muted-foreground border-b border-border pb-1 mb-1">
          <div className="w-56 shrink-0 ps-1">Início {fr(project?.start_date)} → fim {fr(project?.end_date)}</div>
          <div className="flex-1 relative h-4 me-24">
            {ticks.map((i) => (
              <span key={i} className="absolute -translate-x-1/2" style={{ left: `${(i / total) * 100}%` }}>J{i}</span>
            ))}
          </div>
        </div>
        {tasks.map((t) => {
          const left = (t.start_idx / total) * 100;
          const width = Math.max(((t.end_idx - t.start_idx) / total) * 100, 0.8);
          const bar = t.fixed ? "bg-sky-600/80" : t.critical ? "bg-primary" : "bg-slate-300 dark:bg-slate-600";
          return (
            <button type="button" key={t.id} onClick={() => onSelect?.(t.id)}
                    data-testid={`gantt-row-${t.id}`}
                    className={`flex w-full items-center h-8 rounded-sm text-left transition-colors hover:bg-muted/60 ${selected === t.id ? "bg-muted" : ""}`}>
              <div className="w-56 shrink-0 ps-1 pe-2 truncate text-xs flex items-center gap-1">
                {t.late && <span className="h-1.5 w-1.5 rounded-full bg-red-500 shrink-0" title="Em atraso" />}
                <span className="truncate" title={t.name}>{t.name}</span>
              </div>
              <div className="flex-1 relative h-5 me-24">
                {ticks.map((i) => <span key={i} className="absolute top-0 bottom-0 border-s border-dashed border-border/60" style={{ left: `${(i / total) * 100}%` }} />)}
                <div className={`absolute top-0.5 bottom-0.5 rounded-sm ${bar} overflow-hidden`} style={{ left: `${left}%`, width: `${width}%` }}
                     title={`${t.name} · ${fr(t.start_date)} → ${fr(t.end_date)} · ${t.duration} d${t.critical ? " · crítica" : ` · folga ${t.slack} d`}`}>
                  {t.progress > 0 && <div className="h-full bg-emerald-400/70" style={{ width: `${Math.min(100, t.progress)}%` }} />}
                </div>
                <span className="absolute top-0 text-[10px] text-muted-foreground ps-1 whitespace-nowrap" style={{ left: `${Math.min(left + width, 92)}%` }}>
                  {fr(t.start_date)}→{fr(t.end_date)}
                </span>
              </div>
            </button>
          );
        })}
        <div className="flex gap-4 text-[10px] text-muted-foreground mt-2 ps-1">
          <span className="flex items-center gap-1"><i className="h-2 w-4 rounded-sm bg-primary inline-block" /> caminho crítico</span>
          <span className="flex items-center gap-1"><i className="h-2 w-4 rounded-sm bg-slate-300 inline-block" /> com margem</span>
          <span className="flex items-center gap-1"><i className="h-2 w-4 rounded-sm bg-sky-600/80 inline-block" /> real (introduzido)</span>
          <span className="flex items-center gap-1"><i className="h-2 w-4 rounded-sm bg-emerald-400/70 inline-block" /> avancement</span>
        </div>
      </div>
    </div>
  );
}
