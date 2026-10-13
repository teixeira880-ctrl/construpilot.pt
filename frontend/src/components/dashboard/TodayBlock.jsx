import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { useExperienceCopy } from "@/components/workspace/experienceCopy";
import { ArrowRight, AlertTriangle, Clock, FileText, Receipt, Ruler, CalendarClock, CheckCircle2, ChevronDown } from "lucide-react";

const ICONS = { invoice_overdue: Receipt, quote_followup: FileText, plan_review: Ruler, deadline: CalendarClock, vat_to_confirm: AlertTriangle, setup: ArrowRight, clear: CheckCircle2 };
export const TodayBlock = () => {
  const nav = useNavigate();
  const { lang } = useI18n();
  const copy = useExperienceCopy();
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { let active = true; api.get("/dashboard/today").then(({ data }) => { if (active) setData(data); }).catch(() => { if (active) setFailed(true); }); return () => { active = false; }; }, []);
  if (failed) return null;
  if (!data) return <div className="surface p-5 animate-pulse h-28" data-testid="today-loading" aria-busy="true" />;
  if (!data.next_action) return null;
  const items = data.items || [];
  const Icon = ICONS[data.next_action.kind] || ArrowRight;
  const locale = { pt: "pt-PT", en: "en-GB" }[lang] || "fr-FR";
  const money = n => Number(n || 0).toLocaleString(locale, { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
  return <section className="dashboard-today" data-testid="today-block">
    <div className="dashboard-today-heading"><h2><span className="dashboard-status-dot" />{copy("today")}</h2>
      {data.running_analyses > 0 && <span data-testid="today-running"><Clock size={14} />{data.running_analyses} {copy("running")}</span>}
    </div>
    <button type="button" onClick={() => nav(data.next_action.url)} data-testid="today-next-action" className="dashboard-next-action">
      <span className="dashboard-action-icon"><Icon size={21} /></span><span><small>{copy("next")}</small><strong>{data.next_action.label}</strong></span><ArrowRight size={18} />
    </button>
    {items.length > 1 && <details className="dashboard-today-more"><summary data-testid="today-more"><span>{copy("otherActions")} <b>{items.length - 1}</b></span><ChevronDown size={16} /></summary>
      <ul data-testid="today-items">{items.slice(1).map((item, i) => { const I = ICONS[item.kind] || ArrowRight; return <li key={i}><button type="button" onClick={() => nav(item.url)} data-testid={`today-item-${item.kind}`}><I size={16} /><span>{item.label}</span>{item.amount != null && <strong>{money(item.amount)}</strong>}<ArrowRight size={15} /></button></li>; })}</ul>
    </details>}
    {items.length === 0 && data.next_action.kind === "clear" && <p className="text-xs text-muted-foreground" data-testid="today-clear">{copy("clear")}</p>}
  </section>;
};
