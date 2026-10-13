import { useState } from "react";
import { ExpenseSelect } from "./Fields";
import { useExpenseCopy } from "./copy";

export const ExpenseBreakdown = ({ data }) => {
  const [group, setGroup] = useState("provider");
  const { text, money } = useExpenseCopy();
  const groups = { provider: "provider", feature: "feature", company_id: "company", user_id: "user", month: "month" };
  const label = key => key === "unattributed" ? text(key) : group === "provider" ? data.overview.providers.find(p => p.provider === key)?.name || key : group === "company_id" ? data.options.companies.find(c => c.org_id === key)?.name || key : group === "user_id" ? data.options.users.find(u => u.user_id === key)?.name || key : key;
  const rows = group === "month" ? data.trend.map(r => ({ ...r, key: r.month })) : data.overview.breakdowns[group];
  return <section className="grid gap-5 min-w-0" data-testid="expense-breakdown-section">
    <div className="max-w-xs"><ExpenseSelect name="expense-breakdown-group" label={text("breakdown")} value={group} onChange={setGroup} options={Object.entries(groups).map(([value, name]) => ({ value, label: text(name) }))} /></div>
    <p className="text-xs text-muted-foreground" data-testid="expense-breakdown-note">{text("totalsNote")}</p>
    {!rows.length && <p data-testid="expense-breakdown-empty">{text("empty")}</p>}
    {rows.map(r => <div key={r.key} className="grid gap-3 sm:grid-cols-4 border-t pt-4 text-sm" data-testid={`expense-breakdown-${group}-${r.key}`}><strong className="break-all">{label(r.key)}</strong>{["confirmed", "estimated"].map(kind => <div key={kind}><p className="text-xs text-muted-foreground">{text(kind)}</p><p className="num mt-1">{money(r[`${kind}_eur`])}</p>{Object.entries(r[`${kind}_native`]).filter(([c]) => c !== "EUR").map(([c, v]) => <p key={c} className="num text-xs">{money(v, c)}</p>)}</div>)}<p className="num text-xs">{r.operations} {text("operations")}<br />{r.unavailable} {text("unavailable")}</p></div>)}
  </section>;
};