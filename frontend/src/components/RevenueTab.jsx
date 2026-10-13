import { useEffect, useState } from "react";
import {
  TrendingUp, Users, Zap, Wallet, RefreshCw, Info,
  UserPlus, Clock, CreditCard,
} from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, eur, num } from "@/lib/api";
import { Stat } from "@/components/Bits";

const KPICard = ({ label, value, sub, testId, accent, icon: Icon }) => (
  <div className={`surface p-6 ${accent ? "border-primary" : ""}`} data-testid={testId}>
    <div className="flex items-center gap-2">
      {Icon && <Icon className={`h-4 w-4 ${accent ? "text-primary" : "text-muted-foreground"}`} />}
      <p className="overline">{label}</p>
    </div>
    <p className={`num mt-3 text-2xl font-bold ${accent ? "text-primary" : ""}`}>{value}</p>
    {sub && <p className="num mt-1 text-xs text-muted-foreground">{sub}</p>}
  </div>
);

export default function RevenueTab() {
  const [kpis, setKpis] = useState(null);
  const [series, setSeries] = useState([]);
  const [days, setDays] = useState(90);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const [{ data: k }, { data: t }] = await Promise.all([
        api.get("/admin/revenue/kpis"),
        api.get(`/admin/revenue/timeseries?days=${days}`),
      ]);
      setKpis(k);
      setSeries(t.series || []);
    } finally { setBusy(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [days]);

  if (!kpis) return (
    <div className="h-40 grid place-items-center" data-testid="revenue-loading">
      <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const funnel = kpis.funnel_30d || {};

  return (
    <div className="grid gap-8" data-testid="revenue-tab">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="overline">Revenue Cockpit</p>
          <h2 className="font-display text-2xl font-bold tracking-tight">Crescimento & rentabilidade</h2>
          <p className="text-xs text-muted-foreground mt-1">
            Gerado a {new Date(kpis.generated_at).toLocaleString("fr-FR")}
          </p>
        </div>
        <div className="flex gap-2">
          {[30, 90, 180, 365].map((d) => (
            <Button
              key={d} size="sm" variant={d === days ? "default" : "outline"}
              onClick={() => setDays(d)} data-testid={`revenue-range-${d}`}
              className="rounded-sm num"
            >
              {d} j
            </Button>
          ))}
          <Button size="sm" variant="ghost" onClick={load} disabled={busy} data-testid="revenue-refresh" className="rounded-sm">
            <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {/* KPIs monétaires */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <KPICard label="MRR" value={eur(kpis.mrr_eur)} testId="kpi-mrr"
                 sub={`${kpis.paying_subs} subscr. paga${kpis.paying_subs > 1 ? "s" : ""}`}
                 accent icon={Zap} />
        <KPICard label="ARR" value={eur(kpis.arr_eur)} testId="kpi-arr" icon={TrendingUp} />
        <KPICard label="ARPU" value={eur(kpis.arpu_eur)} testId="kpi-arpu"
                 sub="Receita média por utilizador" icon={Users} />
        <KPICard label="LTV" value={eur(kpis.ltv_eur)} testId="kpi-ltv"
                 sub={`churn assumido ${num((kpis.assumed_monthly_churn || 0) * 100, 1)} %/mês`}
                 icon={Wallet} />
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <KPICard label="CAC" value={kpis.cac_eur ? eur(kpis.cac_eur) : "— a introduzir"}
                 sub="Indique as suas despesas de aquisição no .env"
                 testId="kpi-cac" icon={CreditCard} />
        <KPICard label="Trials em curso" value={num(kpis.trialing_subs)} testId="kpi-trialing" icon={Clock} />
        <KPICard label="Receita este mês" value={eur(kpis.revenue_this_month_eur)}
                 sub={`${kpis.new_paying_this_month} novos pagantes`}
                 testId="kpi-revenue-month" icon={Wallet} />
        <KPICard label="LTV / CAC"
                 value={kpis.cac_eur ? num(kpis.ltv_eur / kpis.cac_eur, 1) + "×" : "—"}
                 sub={kpis.cac_eur && (kpis.ltv_eur / kpis.cac_eur >= 3 ? "Saudável ✅" : "A vigiar")}
                 testId="kpi-ltv-cac" icon={TrendingUp} />
      </div>

      {/* Time series */}
      <div className="surface p-6">
        <div className="flex items-center justify-between mb-6">
          <p className="overline">Receita diária</p>
          <Badge variant="outline" className="rounded-sm num">{days} últimos dias</Badge>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={series} margin={{ top: 8, right: 24, bottom: 8, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" strokeOpacity={0.15} />
            <XAxis dataKey="day" tick={{ fontSize: 10 }} interval={Math.max(1, Math.floor(series.length / 10))} />
            <YAxis tick={{ fontSize: 10 }} />
            <Tooltip
              contentStyle={{ background: "hsl(var(--background))", border: "1px solid hsl(var(--border))", borderRadius: 0, fontSize: 12 }}
              labelStyle={{ color: "hsl(var(--muted-foreground))" }}
              formatter={(v, k) => k === "revenue_eur" ? [eur(v), "Receita"] : [v, "Pagamentos"]}
            />
            <Line type="monotone" dataKey="revenue_eur" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Per-plan MRR breakdown */}
      <div className="surface p-6" data-testid="mrr-per-plan">
        <p className="overline mb-4">MRR por plano</p>
        {kpis.per_plan?.length ? (
          <div className="grid gap-2">
            {kpis.per_plan.map((p) => (
              <div key={p.plan_id} className="flex items-center justify-between border-b border-border pb-2">
                <div>
                  <p className="font-medium text-sm">{p.name || p.plan_id}</p>
                  <p className="num text-xs text-muted-foreground">{p.count} subscr. · {p.plan_id}</p>
                </div>
                <p className="num font-bold text-primary">{eur(p.mrr)}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Nenhuma subscrição paga por agora.</p>
        )}
      </div>

      {/* Funnel 30 jours */}
      <div className="surface p-6" data-testid="funnel-30d">
        <div className="flex items-center gap-2 mb-4">
          <p className="overline">Funil últimos 30 dias</p>
          <Info className="h-3 w-3 text-muted-foreground" />
        </div>
        <div className="grid sm:grid-cols-4 gap-4">
          <Stat label="Registos" value={num(funnel.signups)} testId="funnel-signups" />
          <Stat label="Trials iniciados" value={num(funnel.trials_started)}
                sub={`${funnel.signup_to_trial_pct} % conv.`} testId="funnel-trials" />
          <Stat label="Pagamentos confirmados" value={num(funnel.paid_transactions)}
                sub={`${funnel.trial_to_paid_pct} % conv.`} accent testId="funnel-paid" />
          <Stat label="Leads ConstruPilot" value={num(funnel.leads)} testId="funnel-leads" />
        </div>
      </div>
    </div>
  );
}
