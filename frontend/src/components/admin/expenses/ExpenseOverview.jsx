import { AlertTriangle, Plus, Settings2 } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Button } from "@/components/ui/button";
import { useExpenseCopy } from "./copy";

export const ExpenseOverview = ({ data, trend, onBudget }) => {
  const { text, money, locale } = useExpenseCopy();
  const globalBudget = data.budgets.find(b => b.provider === "all");
  const metrics = [
    ["confirmed-expense-total", "actualTotal", money(data.summary.confirmed_eur), "border-emerald-600"],
    ["estimated-expense-total", "estimateTotal", money(data.summary.estimated_eur), "border-amber-500"],
    ["unknown-expense-total", "unknownTotal", data.summary.unavailable, "border-border"],
    ["budget-total", "budgetGlobal", money(globalBudget?.amount_eur), "border-border"],
  ];
  const rows = trend.map(r => ({ ...r, confirmed_eur: r.confirmed_eur == null ? null : Number(r.confirmed_eur), estimated_eur: r.estimated_eur == null ? null : Number(r.estimated_eur) }));
  return <div className="grid gap-8 min-w-0">
    <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">{metrics.map(([id, label, value, border]) => <div key={id} className={`border-t-2 ${border} pt-4 min-w-0`}><p className="text-xs text-muted-foreground font-semibold">{text(label)}</p><p className="num text-xl font-bold mt-3 break-words" data-testid={`kpi-${id}`}>{value}</p></div>)}</div>
    <p data-testid="expense-nonblocking-notice" className="text-sm border-l-2 border-emerald-600 pl-3">{text("advisory")}</p>
    {(data.summary.unavailable > 0 || data.summary.unconverted > 0) && <p role="status" data-testid="expense-partial-warning" className="text-sm text-amber-700 dark:text-amber-400 flex gap-2"><AlertTriangle size={18} className="shrink-0" />{text("partial")}</p>}
    <section className="min-w-0" data-testid="expense-monthly-trend"><h2 className="text-lg font-bold mb-5">{text("trend")}</h2>
      {rows.some(r => r.confirmed_eur !== null || r.estimated_eur !== null) ? <div className="h-64 w-full min-w-0"><ResponsiveContainer width="100%" height="100%"><BarChart data={rows} margin={{ left: 0, right: 8 }}><CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.2} /><XAxis dataKey="month" tick={{ fontSize: 11 }} /><YAxis width={55} tick={{ fontSize: 11 }} /><Tooltip formatter={v => money(v)} contentStyle={{ background: "hsl(var(--background))", borderColor: "hsl(var(--border))", borderRadius: 4 }} /><Legend /><Bar name={text("confirmed")} dataKey="confirmed_eur" fill="#16805b" maxBarSize={28} /><Bar name={text("estimated")} dataKey="estimated_eur" fill="#d08b17" maxBarSize={28} /></BarChart></ResponsiveContainer></div> : <p className="py-8 text-sm text-muted-foreground" data-testid="expense-trend-empty">{text("empty")}</p>}
    </section>
    <section data-testid="expense-budgets-section"><div className="flex justify-between flex-wrap items-center gap-3"><h2 className="text-lg font-bold">{text("budget")}</h2><Button variant="outline" onClick={() => onBudget(null)} data-testid="expense-add-budget"><Plus size={16} />{text("setBudget")}</Button></div><p className="text-xs text-muted-foreground my-3" data-testid="expense-budget-basis">{text("budgetBasis")}</p>
      {!data.budgets.length && <p className="text-sm text-muted-foreground py-3" data-testid="expense-budgets-empty">{text("empty")}</p>}
      {data.budgets.map(b => <div key={b.budget_id} className="border-t py-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_auto]" data-testid={`expense-budget-${b.budget_id}`}>
        <div className="text-sm"><strong>{b.provider === "all" ? text("all") : data.providers.find(p => p.provider === b.provider)?.name}</strong><p className="num mt-1" data-testid={`expense-budget-amount-${b.budget_id}`}>{money(b.amount_eur)}</p></div>
        <div className="grid gap-3">{[["confirmed", b.percent, b.state], ["estimated", b.estimated_percent, b.estimated_state]].map(([kind, percent, state]) => <div key={kind} data-testid={`expense-budget-${kind}-${b.budget_id}`}><p className="text-xs mb-1 flex justify-between gap-2"><span>{text(kind)} · {text(state === "warning" ? "warningState" : state)}</span><span className="num">{percent == null ? "—" : `${percent.toFixed(1)}%`}</span></p><div className="h-1.5 rounded bg-muted"><div className={`h-full rounded ${state === "exceeded" ? "bg-red-500" : state === "warning" || kind === "estimated" ? "bg-amber-500" : "bg-emerald-600"}`} style={{ width: `${Math.min(100, percent || 0)}%` }} /></div></div>)}{b.incomplete && <span className="text-xs text-muted-foreground" data-testid={`expense-budget-incomplete-${b.budget_id}`}>{text("incomplete")}</span>}</div>
        <Button size="icon" variant="ghost" title={text("setBudget")} aria-label={text("setBudget")} data-testid={`expense-edit-budget-${b.budget_id}`} onClick={() => onBudget(b)}><Settings2 size={16} /></Button>
      </div>)}
    </section>
    <section className="min-w-0" data-testid="expense-providers-section"><h2 className="text-lg font-bold mb-3">{text("provider")} / {text("coverage")}</h2>
      {data.providers.map(p => <div key={p.provider} data-testid={`provider-card-${p.provider}`} className="grid gap-4 border-t py-5 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] text-sm">
        <div className="min-w-0"><h3 className="font-semibold break-words">{p.name}</h3><p className="text-xs text-muted-foreground mt-1" data-testid={`provider-coverage-${p.provider}`}>{text(p.coverage)}</p><p className="text-xs text-muted-foreground mt-1">{p.configured === null ? "—" : text(p.configured ? "configured" : "notConfigured")}</p></div>
        {["confirmed", "estimated"].map(kind => <div key={kind}><p className="text-xs text-muted-foreground">{text(kind)}</p><p className="num font-semibold mt-1" data-testid={`provider-${kind}-${p.provider}`}>{money(p[`${kind}_eur`])}</p>{Object.entries(p[`${kind}_native`]).filter(([c]) => c !== "EUR").map(([currency, value]) => <p key={currency} className="num text-xs mt-1" data-testid={`provider-${kind}-${p.provider}-${currency}`}>{money(value, currency)}</p>)}</div>)}
        <div><p className="text-xs text-muted-foreground">{text("balance")}</p><p className="mt-1" data-testid={`provider-balance-${p.provider}`}>{text("unavailable")}</p><p className="text-xs text-muted-foreground mt-1">{text("balanceNote")}</p></div>
      </div>)}
    </section>
    <footer className="text-xs text-muted-foreground border-t pt-4 grid gap-2"><p data-testid="expense-history-notice">{text("historical")}</p><p data-testid="expense-last-sync">{text("sync")}: {data.sync.last_synced_at ? new Date(data.sync.last_synced_at).toLocaleString(locale) : text("never")}</p>{data.sync.legacy_calls_unallocated > 0 && <p data-testid="expense-legacy-calls">{text("legacy")}: {data.sync.legacy_calls_unallocated}</p>}{data.sync.truncated && <p role="alert" data-testid="expense-import-partial">{text("truncated")}</p>}</footer>
  </div>;
};