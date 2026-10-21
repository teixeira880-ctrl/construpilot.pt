// Rendu des graphiques renvoyés par le solveur BTP.
// Utilise recharts si disponible dans le projet ; sinon fallback SVG maison.
import { useMemo } from "react";

function BarComparison({ chart }) {
  const { x_labels, series, unit } = chart;
  const max = useMemo(
    () => Math.max(...series.flatMap((s) => s.data), 1),
    [series]
  );
  const colors = ["#10b981", "#f59e0b", "#3b82f6", "#ef4444"];
  return (
    <div className="space-y-3">
      <h3 className="font-semibold text-base">{chart.title}</h3>
      <div className="space-y-3">
        {x_labels.map((label, i) => (
          <div key={i} className="space-y-1">
            <div className="text-sm text-slate-600 dark:text-slate-300">{label}</div>
            <div className="flex gap-1 h-7">
              {series.map((s, j) => {
                const v = s.data[i] || 0;
                const w = (v / max) * 100;
                return (
                  <div key={j} className="flex-1 relative bg-slate-100 dark:bg-slate-800 rounded">
                    <div className="absolute inset-y-0 left-0 rounded transition-all"
                         style={{ width: `${w}%`, backgroundColor: colors[j % colors.length] }} />
                    <div className="absolute inset-0 flex items-center justify-center text-xs font-medium">
                      {Math.round(v).toLocaleString("pt-PT")} {unit || ""}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-3 text-xs">
        {series.map((s, j) => (
          <span key={j} className="flex items-center gap-1">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: colors[j % colors.length] }} />
            {s.name}
          </span>
        ))}
      </div>
      {chart.caption && <p className="text-xs text-slate-500 italic">{chart.caption}</p>}
    </div>
  );
}

function RadarChart({ chart }) {
  const { x_labels, series } = chart;
  const size = 220;
  const cx = size / 2, cy = size / 2, r = size / 2 - 20;
  const axes = x_labels.length;
  const angle = (i) => (Math.PI * 2 * i) / axes - Math.PI / 2;
  const maxByAxis = x_labels.map((_, i) =>
    Math.max(...series.map((s) => Math.abs(s.data[i] || 0)), 1)
  );
  const colors = ["#10b981", "#f59e0b", "#3b82f6", "#ef4444"];
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-base">{chart.title}</h3>
      <div className="flex flex-col md:flex-row items-center gap-4">
        <svg width={size} height={size} className="shrink-0">
          {[0.25, 0.5, 0.75, 1].map((r2, i) => (
            <polygon key={i}
              points={x_labels.map((_, j) => {
                const a = angle(j);
                return `${cx + Math.cos(a) * r * r2},${cy + Math.sin(a) * r * r2}`;
              }).join(" ")}
              fill="none" stroke="currentColor" strokeOpacity="0.15" />
          ))}
          {x_labels.map((label, i) => {
            const a = angle(i);
            return (
              <g key={i}>
                <line x1={cx} y1={cy} x2={cx + Math.cos(a) * r} y2={cy + Math.sin(a) * r}
                      stroke="currentColor" strokeOpacity="0.15" />
                <text x={cx + Math.cos(a) * (r + 12)} y={cy + Math.sin(a) * (r + 12)}
                      textAnchor="middle" fontSize="9" fill="currentColor" opacity="0.65">
                  {label.length > 14 ? label.slice(0, 14) + "…" : label}
                </text>
              </g>
            );
          })}
          {series.map((s, si) => (
            <polygon key={si}
              points={x_labels.map((_, j) => {
                const a = angle(j);
                const norm = (s.data[j] || 0) / maxByAxis[j];
                return `${cx + Math.cos(a) * r * norm},${cy + Math.sin(a) * r * norm}`;
              }).join(" ")}
              fill={colors[si % colors.length]} fillOpacity="0.2"
              stroke={colors[si % colors.length]} strokeWidth="1.5" />
          ))}
        </svg>
        <div className="flex flex-col gap-1 text-xs">
          {series.map((s, j) => (
            <span key={j} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: colors[j % colors.length] }} />
              {s.name}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function PieChart({ chart }) {
  const { x_labels, series } = chart;
  const data = series[0]?.data || [];
  const total = data.reduce((a, b) => a + b, 0) || 1;
  const size = 200;
  const cx = size / 2, cy = size / 2, r = 80;
  const colors = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];
  let acc = 0;
  const slices = data.map((v, i) => {
    const start = (acc / total) * Math.PI * 2 - Math.PI / 2;
    acc += v;
    const end = (acc / total) * Math.PI * 2 - Math.PI / 2;
    const large = end - start > Math.PI ? 1 : 0;
    const x1 = cx + Math.cos(start) * r, y1 = cy + Math.sin(start) * r;
    const x2 = cx + Math.cos(end) * r, y2 = cy + Math.sin(end) * r;
    return {
      d: `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`,
      color: colors[i % colors.length],
      pct: ((v / total) * 100).toFixed(1),
      label: x_labels[i],
    };
  });
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-base">{chart.title}</h3>
      <div className="flex flex-col md:flex-row items-center gap-4">
        <svg width={size} height={size}>
          {slices.map((s, i) => <path key={i} d={s.d} fill={s.color} />)}
        </svg>
        <ul className="text-xs space-y-1">
          {slices.map((s, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: s.color }} />
              <span className="font-medium">{s.pct} %</span>
              <span className="text-slate-500">{s.label}</span>
            </li>
          ))}
        </ul>
      </div>
      {chart.caption && <p className="text-xs text-slate-500 italic">{chart.caption}</p>}
    </div>
  );
}

export function SolverCharts({ charts }) {
  if (!charts?.length) return null;
  return (
    <div className="grid md:grid-cols-2 gap-6">
      {charts.map((c) => {
        const wrapper = "rounded-xl border border-slate-200 dark:border-slate-800 p-4 bg-white dark:bg-slate-900/40";
        if (c.type === "bar" || c.type === "comparison") {
          return <div key={c.id} className={wrapper}><BarComparison chart={c} /></div>;
        }
        if (c.type === "radar") {
          return <div key={c.id} className={wrapper}><RadarChart chart={c} /></div>;
        }
        if (c.type === "pie") {
          return <div key={c.id} className={wrapper}><PieChart chart={c} /></div>;
        }
        return (
          <div key={c.id} className={wrapper}>
            <BarComparison chart={c} />
          </div>
        );
      })}
    </div>
  );
}
