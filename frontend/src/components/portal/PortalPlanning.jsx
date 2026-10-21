import { useEffect, useState } from "react";
import { CalendarRange, CheckCircle2, Clock, Circle, AlertTriangle } from "lucide-react";

const fr = (d) => (d ? `${d.slice(8, 10)}/${d.slice(5, 7)}/${d.slice(0, 4)}` : "—");
const ST = {
  termine: ["Terminado", CheckCircle2, "text-emerald-600"], en_cours: ["Em curso", Clock, "text-sky-600"],
  a_venir: ["Brevemente", Circle, "text-slate-400"], en_retard: ["A confirmar", AlertTriangle, "text-amber-600"],
};

/** Planning (lecture seule) de l'Espace Client : Gantt simplifié + prochaines étapes. */
export function PortalPlanning({ portalApi, chantierRef, accent }) {
  const [data, setData] = useState(undefined);
  useEffect(() => { portalApi.get(`/${chantierRef}/planning`).then(({ data }) => setData(data.planning)).catch(() => setData(null)); }, [portalApi, chantierRef]);
  if (data === undefined) return null;
  if (!data) return null;
  const { project, tasks, current, upcoming } = data;
  const first = Math.min(...tasks.map((t) => t.start_idx));
  const total = Math.max(1, Math.max(...tasks.map((t) => t.end_idx)) - first);
  const todayIdx = tasks.find((t) => t.start_date <= project.as_of && t.end_date >= project.as_of);
  return (
    <section className="rounded-2xl border bg-white p-5" data-testid="portal-planning">
      <div className="flex flex-wrap items-center gap-2">
        <CalendarRange className="h-5 w-5" style={{ color: accent }} />
        <h2 className="font-semibold">Planeamento das obras</h2>
        <span className="text-xs text-slate-500">du {fr(project.start_date)} au <b data-testid="portal-planning-end">{fr(project.end_date)}</b> · {project.duration_workdays} dias úteis · situação em {fr(project.as_of)}</span>
      </div>

      {(current.length > 0 || upcoming.length > 0) && (
        <div className="mt-4 grid sm:grid-cols-2 gap-3" data-testid="portal-planning-next">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Neste momento</p>
            {current.length === 0 ? <p className="text-sm text-slate-500 mt-1">Nenhuma intervenção em curso.</p> : current.map((t) => (
              <p key={t.id} className="text-sm mt-1"><b>{t.name}</b> <span className="text-slate-500">· {t.lot} · até {fr(t.end_date)} · {t.progress}%</span></p>))}
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-[11px] uppercase tracking-wide text-slate-500">Próximas etapas</p>
            {upcoming.length === 0 ? <p className="text-sm text-slate-500 mt-1">Todas as etapas estão iniciadas.</p> : upcoming.map((t) => (
              <p key={t.id} className="text-sm mt-1"><b>{t.name}</b> <span className="text-slate-500">· a partir de {fr(t.start_date)}</span></p>))}
          </div>
        </div>
      )}

      <ol className="mt-4 grid gap-1.5" data-testid="portal-gantt">
        {tasks.map((t) => {
          const [label, I, cls] = ST[t.status] || ST.a_venir;
          const left = ((t.start_idx - first) / total) * 100;
          const width = Math.max(((t.end_idx - t.start_idx) / total) * 100, 1);
          return (
            <li key={t.id} className="grid grid-cols-[minmax(0,180px)_1fr] sm:grid-cols-[minmax(0,240px)_1fr] items-center gap-2 text-xs" data-testid={`portal-gantt-${t.id}`}>
              <div className="flex items-center gap-1.5 min-w-0"><I className={`h-3.5 w-3.5 shrink-0 ${cls}`} /><span className="truncate" title={`${t.name} · ${t.lot}`}>{t.name}</span></div>
              <div className="relative h-5 rounded bg-slate-100 overflow-hidden">
                <div className="absolute top-0.5 bottom-0.5 rounded-sm" style={{ left: `${left}%`, width: `${width}%`, background: t.status === "termine" ? "#16a34a" : t.status === "a_venir" ? "#cbd5e1" : accent, opacity: t.status === "a_venir" ? 1 : 0.9 }}>
                  {t.progress > 0 && t.progress < 100 && <div className="h-full bg-emerald-500/70 rounded-sm" style={{ width: `${t.progress}%` }} />}
                </div>
                <span className={`absolute inset-y-0 flex items-center text-[10px] text-slate-500 ${left + width > 60 ? "left-1" : "right-1"}`}>{fr(t.start_date)} → {fr(t.end_date)} · {label}</span>
              </div>
            </li>
          );
        })}
      </ol>
      {todayIdx && <p className="text-[11px] text-slate-500 mt-2">As datas são previsionais e recalculadas pela empresa ao longo do avanço.</p>}
    </section>
  );
}
