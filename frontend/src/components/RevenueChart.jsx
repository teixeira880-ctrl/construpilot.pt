import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from "recharts";
import { TrendingUp } from "lucide-react";
import { api } from "@/lib/api";

const eur0 = (n) =>
  (n || 0).toLocaleString("pt-PT", { maximumFractionDigits: 0 }) + " €";

export const RevenueChart = ({ compact = false }) => {
  const [data, setData] = useState(null);

  useEffect(() => {
    api
      .get("/quotes/revenue/monthly")
      .then(({ data }) => setData(data))
      .catch(() => setData({ months: [], total: 0, signed_count: 0 }));
  }, []);

  if (!data) {
    return (
      <div className="surface p-6 text-sm text-muted-foreground animate-pulse"
           data-testid="revenue-chart-loading">
        Carregamento do volume de negócios…
      </div>
    );
  }

  const months = data.months || [];
  const hasData = (data.total || 0) > 0;

  return (
    <div className="surface p-5" data-testid="revenue-chart">
      <div className="flex items-center justify-between mb-4 gap-3">
        <div>
          <p className="overline flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-primary" /> Volume de negócios assinado
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            {data.signed_count || 0} orçamentos assinados · últimos 12 meses
          </p>
        </div>
        <p className="num font-display text-2xl font-extrabold text-primary"
           data-testid="revenue-chart-total">
          {eur0(data.total)}
        </p>
      </div>

      {!hasData ? (
        <div className="h-[210px] grid place-items-center text-center text-sm text-muted-foreground"
             data-testid="revenue-chart-empty">
          <span>
            Nenhum orçamento assinado por agora.<br />
            O seu volume de negócios mensal será apresentado aqui após a primeira assinatura.
          </span>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={compact ? 200 : 260}>
          <BarChart data={months} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                   axisLine={false} tickLine={false} />
            <YAxis tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : v)}
                   tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false}
                   tickLine={false} width={44} />
            <Tooltip cursor={{ fill: "hsl(var(--primary))", fillOpacity: 0.08 }}
                     formatter={(v) => [eur0(v), "Receita assinada"]}
                     contentStyle={{ background: "hsl(var(--background))",
                                     border: "1px solid hsl(var(--primary))",
                                     borderRadius: 6, fontSize: 12 }}
                     labelStyle={{ color: "hsl(var(--foreground))" }} />
            <Bar dataKey="revenue" radius={[4, 4, 0, 0]} maxBarSize={46} fill="hsl(var(--primary))">
              {months.map((m, i) => (
                <Cell key={i} fillOpacity={i === months.length - 1 ? 1 : 0.5} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
};

export default RevenueChart;
