import { useEffect, useState } from "react";
import { LineChart, Line, CartesianGrid, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart, Legend } from "recharts";
import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { api, eur2 } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

export const PriceHistoryChart = ({ query, days = 90 }) => {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!query) return;
    api.get(`/prices/history/chart?query=${encodeURIComponent(query)}&days=${days}`)
       .then(({ data }) => setData(data))
       .catch(() => setData({ series: [] }));
  }, [query, days]);

  if (!data) return <div className="surface p-6 h-40 animate-pulse" />;
  const series = data.series || [];
  if (series.length < 2) {
    return (
      <div className="surface p-6 text-center" data-testid="price-history-empty">
        <p className="text-sm text-muted-foreground">
          Historique insuffisant pour tracer la courbe. Créez une alerte prix pour commencer le suivi quotidien.
        </p>
      </div>
    );
  }
  const first = series[0].min_price;
  const last = series[series.length - 1].min_price;
  const diff = last - first;
  const pct = first ? (diff / first) * 100 : 0;
  const Icon = diff < -0.5 ? TrendingDown : diff > 0.5 ? TrendingUp : Minus;
  const color = diff < 0 ? "text-emerald-500" : diff > 0 ? "text-red-500" : "text-muted-foreground";

  return (
    <div className="surface p-6 grid gap-4" data-testid="price-history-chart">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <p className="overline">Historique des prix · {query}</p>
          <p className="text-xs text-muted-foreground mt-1">Meilleur prix quotidien sur {days} derniers jours ({series.length} points)</p>
        </div>
        <div className={`flex items-center gap-2 ${color}`}>
          <Icon className="h-5 w-5" />
          <span className="num font-display font-bold text-lg">
            {diff >= 0 ? "+" : ""}{eur2(diff)} ({pct >= 0 ? "+" : ""}{pct.toFixed(1)} %)
          </span>
        </div>
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="hsl(var(--primary))" stopOpacity={0.4} />
                <stop offset="100%" stopColor="hsl(var(--primary))" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="day" stroke="hsl(var(--muted-foreground))" fontSize={11}
                   tickFormatter={(d) => d.slice(5)} />
            <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11}
                   tickFormatter={(v) => `${v}€`} />
            <Tooltip
              contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 2, fontSize: 12 }}
              formatter={(v) => eur2(v)} labelFormatter={(l) => `Le ${l}`}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            <Area type="monotone" dataKey="min_price" name="Meilleur prix"
                  stroke="hsl(var(--primary))" strokeWidth={2}
                  fill="url(#priceGrad)" />
            <Line type="monotone" dataKey="avg_price" name="Prix moyen"
                  stroke="hsl(var(--muted-foreground))" strokeWidth={1}
                  strokeDasharray="4 4" dot={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        <Badge variant="outline" className="rounded-sm num">Min : {eur2(Math.min(...series.map((d) => d.min_price)))}</Badge>
        <Badge variant="outline" className="rounded-sm num">Max : {eur2(Math.max(...series.map((d) => d.max_price)))}</Badge>
        <Badge variant="outline" className="rounded-sm num">Actuel : {eur2(last)}</Badge>
      </div>
    </div>
  );
};
