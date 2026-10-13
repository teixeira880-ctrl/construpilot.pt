import { Plus, Trash2, ArrowUp, ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const fr = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "—");

export function TaskTable({ tasks, computed, trades = [], selected, onSelect, onChange, onProgress, onFollowTimesheets }) {
  const byId = Object.fromEntries((computed || []).map((t) => [t.id, t]));
  const update = (idx, patch) => onChange(tasks.map((t, i) => (i === idx ? { ...t, ...patch, duration_source: patch.duration != null ? "saisie" : t.duration_source } : t)));
  const move = (idx, dir) => {
    const j = idx + dir;
    if (j < 0 || j >= tasks.length) return;
    const next = [...tasks];
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange(next);
  };
  const remove = (idx) => {
    const id = tasks[idx].id;
    onChange(tasks.filter((_, i) => i !== idx).map((t) => ({ ...t, predecessors: (t.predecessors || []).filter((p) => p.id !== id) })));
  };
  const add = () => {
    let n = tasks.length + 1;
    while (tasks.some((t) => t.id === `t${n}`)) n += 1;
    const last = tasks[tasks.length - 1];
    onChange([...tasks, { id: `t${n}`, name: "Nova tarefa", resource: last?.resource || "Equipa", duration: 5, duration_source: "saisie",
      predecessors: last ? [{ id: last.id, lag: 0 }] : [], progress: 0, auto_link: false }]);
  };
  const togglePred = (idx, pid) => {
    const t = tasks[idx];
    const has = (t.predecessors || []).some((p) => p.id === pid);
    update(idx, { predecessors: has ? t.predecessors.filter((p) => p.id !== pid) : [...(t.predecessors || []), { id: pid, lag: 0 }], auto_link: false });
  };
  const setLag = (idx, pid, lag) => update(idx, { predecessors: tasks[idx].predecessors.map((p) => (p.id === pid ? { ...p, lag: Number(lag) || 0 } : p)) });

  return (
    <div className="overflow-x-auto" data-testid="task-table">
      <table className="w-full text-xs min-w-[900px]">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-border">
            <th className="py-2 ps-2 w-8">#</th><th>Tarefa</th><th>Equipa / capítulo</th><th className="w-20">Duração (d)</th><th className="w-20">H. previstas</th>
            <th>Depois de (antecessoras)</th><th className="w-24">Não antes de</th><th className="w-24">Início → fim</th><th className="w-16">Marge</th><th className="w-28">Avancement</th><th className="w-24" />
          </tr>
        </thead>
        <tbody>
          {tasks.map((t, idx) => {
            const c = byId[t.id];
            return (
              <tr key={t.id} data-testid={`task-row-${t.id}`} onClick={() => onSelect?.(t.id)}
                  className={`border-b border-border/60 align-top ${selected === t.id ? "bg-muted/60" : "hover:bg-muted/30"}`}>
                <td className="py-1.5 ps-2 font-mono text-muted-foreground">{t.id}</td>
                <td className="py-1.5 pe-2 min-w-[180px]">
                  <Input value={t.name} onChange={(e) => update(idx, { name: e.target.value })} className="h-8 text-xs" data-testid={`task-name-${t.id}`} />
                  {t.duration_source === "defaut" && <span className="text-[10px] text-amber-600">duração por omissão — a confirmar</span>}
                </td>
                <td className="py-1.5 pe-2 min-w-[150px]">
                  <Input list="planning-trades" value={t.resource} onChange={(e) => update(idx, { resource: e.target.value })} className="h-8 text-xs" data-testid={`task-resource-${t.id}`} />
                </td>
                <td className="py-1.5 pe-2">
                  <Input type="number" min={1} max={365} value={t.duration} onChange={(e) => update(idx, { duration: Math.max(1, Number(e.target.value) || 1) })}
                         className="h-8 text-xs w-16" data-testid={`task-duration-${t.id}`} />
                </td>
                <td className="py-1.5 pe-2">
                  <Input type="number" min={0} step={1} value={t.planned_hours ?? ""} placeholder="—" title="Horas de mão de obra previstas: o avanço segue então as horas registadas validadas (módulo RH, mesmo capítulo)"
                         onChange={(e) => update(idx, { planned_hours: e.target.value === "" ? null : Math.max(0, Number(e.target.value) || 0) })} className="h-8 text-xs w-16" data-testid={`task-hours-${t.id}`} />
                  {c?.hours_logged > 0 && <div className="text-[10px] text-emerald-700 whitespace-nowrap" data-testid={`task-hours-logged-${t.id}`}>{c.hours_logged} h registadas</div>}
                </td>
                <td className="py-1.5 pe-2 min-w-[200px]">
                  <div className="flex flex-wrap gap-1">
                    {tasks.filter((o) => o.id !== t.id).map((o) => {
                      const p = (t.predecessors || []).find((x) => x.id === o.id);
                      return (
                        <span key={o.id} className="inline-flex items-center">
                          <button type="button" onClick={(e) => { e.stopPropagation(); togglePred(idx, o.id); }} title={o.name}
                                  data-testid={`task-pred-${t.id}-${o.id}`}
                                  className={`px-1.5 h-6 rounded-s-sm border text-[10px] font-mono ${p ? "bg-primary text-white border-primary" : "border-border text-muted-foreground hover:border-primary"} ${!p ? "rounded-e-sm" : ""}`}>
                            {o.id}
                          </button>
                          {p && <input type="number" value={p.lag} title="Desfasamento (dias úteis, negativo = sobreposição)" onClick={(e) => e.stopPropagation()}
                                       onChange={(e) => setLag(idx, o.id, e.target.value)} className="h-6 w-10 text-[10px] border border-s-0 border-primary rounded-e-sm px-1 bg-background" />}
                        </span>
                      );
                    })}
                  </div>
                </td>
                <td className="py-1.5 pe-2">
                  <Input type="date" value={t.not_before || ""} onChange={(e) => update(idx, { not_before: e.target.value || null })} className="h-8 text-xs" data-testid={`task-notbefore-${t.id}`} />
                </td>
                <td className="py-1.5 pe-2 whitespace-nowrap" data-testid={`task-dates-${t.id}`}>
                  {c ? <>{fr(c.start_date)}<br />{fr(c.end_date)}</> : <span className="text-muted-foreground">a recalcular</span>}
                </td>
                <td className="py-1.5 pe-2">
                  {c && (c.critical ? <span className="text-primary font-semibold">critique</span> : <span>{c.slack} j</span>)}
                  {c?.late && <div className="text-red-600 text-[10px]">en retard</div>}
                </td>
                <td className="py-1.5 pe-2">
                  <div className="flex items-center gap-1">
                    <input type="range" min={0} max={100} step={10} value={t.progress || 0} onClick={(e) => e.stopPropagation()}
                           onChange={(e) => onProgress(t.id, Number(e.target.value))} className="w-16 accent-emerald-600" data-testid={`task-progress-${t.id}`} />
                    <span className="w-8 text-right">{t.progress || 0}%</span>
                  </div>
                  {t.actual_end && <div className="text-[10px] text-emerald-700">concluída em {fr(t.actual_end)}</div>}
                  {c?.progress_source === "pointage" && <div className="text-[10px] text-emerald-700" data-testid={`task-progress-source-${t.id}`}>auto · pointage RH</div>}
                  {c?.progress_source === "manuel" && t.planned_hours > 0 && t.progress < 100 && <button type="button" className="text-[10px] underline text-muted-foreground" onClick={(e) => { e.stopPropagation(); onFollowTimesheets?.(t.id); }} data-testid={`task-follow-timesheets-${t.id}`}>voltar a seguir o registo de horas</button>}
                </td>
                <td className="py-1.5 pe-1">
                  <div className="flex gap-0.5">
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); move(idx, -1); }} title="Monter"><ArrowUp className="h-3 w-3" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); move(idx, 1); }} title="Descendre"><ArrowDown className="h-3 w-3" /></Button>
                    <Button size="icon" variant="ghost" className="h-7 w-7 text-red-600" onClick={(e) => { e.stopPropagation(); remove(idx); }} title="Eliminar" data-testid={`task-delete-${t.id}`}><Trash2 className="h-3 w-3" /></Button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <datalist id="planning-trades">{trades.map((n) => <option key={n} value={n} />)}</datalist>
      <Button variant="outline" size="sm" className="mt-3 gap-1 rounded-sm" onClick={add} data-testid="task-add-btn"><Plus className="h-3.5 w-3.5" /> Adicionar uma tarefa</Button>
    </div>
  );
}
