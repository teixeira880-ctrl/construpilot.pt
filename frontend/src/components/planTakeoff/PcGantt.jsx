import { useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const isWE = (d) => d.getDay() === 0 || d.getDay() === 6;
const skipWE = (d) => { const x = new Date(d); while (isWE(x)) x.setDate(x.getDate() + 1); return x; };
const fmt = (d) => d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
const fmtLong = (d) => d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const COLORS = ["#f59e0b", "#f97316", "#0ea5e9", "#10b981", "#8b5cf6"];

export const computeSchedule = (planning, start) => {
  let cursor = skipWE(new Date(start + "T00:00:00"));
  return (planning?.phases || []).map((ph) => {
    const workStart = skipWE(cursor);
    const d = new Date(workStart);
    let remaining = ph.work_days - 1;
    while (remaining > 0) { d.setDate(d.getDate() + 1); if (!isWE(d)) remaining--; }
    const workEnd = new Date(d);
    const cureEnd = new Date(workEnd);
    cureEnd.setDate(cureEnd.getDate() + ph.cure_days);
    cursor = new Date(cureEnd);
    cursor.setDate(cursor.getDate() + 1);
    return { ...ph, workStart, workEnd, cureEnd };
  });
};

export default function PcGantt({ planning, start, onStartChange }) {

  const rows = useMemo(() => computeSchedule(planning, start), [planning, start]);

  if (!rows.length) return null;
  const t0 = rows[0].workStart.getTime();
  const span = rows[rows.length - 1].cureEnd.getTime() + 86400000 - t0;
  const pct = (t) => Math.max(0, Math.min(100, ((t - t0) / span) * 100));

  return (
    <div className="space-y-2" data-testid="pc-gantt">
      <div className="flex items-center gap-2">
        <Label htmlFor="pc-gantt-start" className="text-xs shrink-0">Início obra:</Label>
        <Input id="pc-gantt-start" type="date" value={start}
               onChange={(e) => e.target.value && onStartChange(e.target.value)}
               data-testid="pc-gantt-start-input"
               className="rounded-sm h-8 w-40 text-xs num" />
      </div>
      <div className="border border-border rounded-sm p-3 space-y-2 bg-muted/20">
        {rows.map((r, i) => {
          const left = pct(r.workStart.getTime());
          const workW = Math.max(1.5, pct(r.workEnd.getTime() + 86400000) - left);
          const cureW = Math.max(0, pct(r.cureEnd.getTime() + 86400000) - left - workW);
          return (
            <div key={i} className="grid grid-cols-[minmax(140px,220px)_1fr] gap-2 items-center"
                 data-testid={`pc-gantt-row-${i}`}>
              <div className="min-w-0">
                <p className="text-[11px] font-medium truncate" title={r.name}>{r.name}</p>
                <p className="text-[10px] text-muted-foreground num">
                  {fmt(r.workStart)} → {fmt(r.workEnd)}
                  {r.cure_days > 0 && `· secagem →${fmt(r.cureEnd)}`}
                </p>
              </div>
              <div className="relative h-5 rounded-sm bg-background border border-border/60 overflow-hidden">
                <div className="absolute top-0 h-full rounded-sm"
                     style={{ left: `${left}%`, width: `${workW}%`, backgroundColor: COLORS[i % COLORS.length] }}
                     title={`${r.work_days}dias úteis`} />
                {cureW > 0 && (
                  <div className="absolute top-0 h-full opacity-50"
                       style={{
                         left: `${left + workW}%`, width: `${cureW}%`,
                         backgroundImage: `repeating-linear-gradient(45deg, ${COLORS[i % COLORS.length]} 0 4px, transparent 4px 8px)`,
                       }}
                       title={`Secagem do betão${r.cure_days} j`} />
                )}
              </div>
            </div>
          );
        })}
        <p className="text-[11px] text-muted-foreground pt-1" data-testid="pc-gantt-end-date">
          Cheio = trabalho (dias úteis, fins de semana saltados) · tracejado = secagem do betão. Fim de obra estimado: <b className="text-foreground">{fmtLong(rows[rows.length - 1].cureEnd)}</b>
        </p>
      </div>
    </div>
  );
}
