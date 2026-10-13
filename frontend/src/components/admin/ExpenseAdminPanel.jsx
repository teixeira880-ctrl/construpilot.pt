import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Download, Plus, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useExpenseCopy } from "./expenses/copy";
import { ExpenseFilters } from "./expenses/ExpenseFilters";
import { ExpenseOverview } from "./expenses/ExpenseOverview";
import { ExpenseLedger } from "./expenses/ExpenseLedger";
import { ExpenseBreakdown } from "./expenses/ExpenseBreakdown";
import { ExpenseRates } from "./expenses/ExpenseRates";
import { ExpenseDialog } from "./expenses/ExpenseDialog";

export const ExpenseAdminPanel = ({ standalone = false }) => {
  const { text } = useExpenseCopy();
  const [filters, setFilters] = useState({ month: new Date().toISOString().slice(0, 7), provider: "", feature: "", company_id: "", user_id: "", include_test: false });
  const [page, setPage] = useState(1), [evidence, setEvidence] = useState(""), [tab, setTab] = useState("overview");
  const [data, setData] = useState(null), [busy, setBusy] = useState(true), [error, setError] = useState(false), [dialog, setDialog] = useState(null);
  const request = useRef(0), alive = useRef(true);
  const params = useCallback(() => Object.fromEntries(Object.entries(filters).filter(([, v]) => v !== "")), [filters]);
  const load = useCallback(async (sync = false) => {
    const id = ++request.current;
    setBusy(true); setError(false);
    try {
      if (sync) await api.post("/admin/expenses/sync-local");
      const base = params();
      const responses = await Promise.all([
        api.get("/admin/expenses/overview", { params: base }), api.get("/admin/expenses/ledger", { params: { ...base, page, evidence: evidence || undefined } }),
        api.get("/admin/expenses/selectors"), api.get("/admin/expenses/trend", { params: base }), api.get("/admin/expenses/rates"),
      ]);
      if (alive.current && id === request.current) setData({ overview: responses[0].data, ledger: responses[1].data, options: responses[2].data, trend: responses[3].data.items, rates: responses[4].data.items });
    } catch { if (alive.current && id === request.current) { setError(true); setData(null); } }
    finally { if (alive.current && id === request.current) setBusy(false); }
  }, [params, page, evidence]);
  useEffect(() => { alive.current = true; return () => { alive.current = false; request.current += 1; }; }, []);
  useEffect(() => { load(); }, [load]);
  const exportCsv = async () => {
    try {
      const response = await api.get("/admin/expenses/export.csv", { params: { ...params(), evidence: evidence || undefined }, responseType: "blob" });
      const url = URL.createObjectURL(response.data), a = document.createElement("a");
      a.href = url; a.download = `api-expenses-${filters.month}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch { toast.error(text("error")); }
  };
  return <section className="min-w-0 grid gap-6" data-testid="admin-despesas-page" aria-busy={busy}>
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>{standalone && <Link to="/admin" data-testid="expense-admin-back" className="inline-flex items-center gap-1 text-sm text-muted-foreground mb-3 hover:text-foreground"><ArrowLeft size={14} />{text("admin")}</Link>}<h1 className="text-3xl sm:text-4xl font-bold" data-testid="expense-title">{text("title")}</h1><p className="text-sm text-muted-foreground mt-2" data-testid="expense-totals-note">{text("totalsNote")}</p></div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => load(true)} disabled={busy} data-testid="expense-sync-all-btn"><RefreshCw className={busy ? "animate-spin" : ""} size={16} />{text("refresh")}</Button>
        <Button variant="outline" onClick={exportCsv} disabled={busy || !data} data-testid="expense-export-csv-btn"><Download size={16} />CSV</Button>
        <Button onClick={() => setDialog({ type: "entry" })} disabled={!data || busy} data-testid="expense-add-entry"><Plus size={16} />{text("add")}</Button>
      </div>
    </div>
    <ExpenseFilters filters={filters} setFilters={v => { setFilters(v); setPage(1); }} providers={data?.overview.providers || []} options={data?.options || { users: [], companies: [], features: [] }} />
    {error && <div role="alert" data-testid="expense-load-error" className="border border-red-500/40 p-4 text-sm">{text("error")}<Button variant="ghost" onClick={() => load()} data-testid="expense-retry">{text("retry")}</Button></div>}
    {busy && <p role="status" data-testid="expense-loading" className="text-sm text-muted-foreground">{text("loading")}</p>}
    {data && !busy && <Tabs value={tab} onValueChange={setTab} className="min-w-0">
      <TabsList className="h-auto flex flex-wrap justify-start w-fit" data-testid="expense-tabs-list">{["overview", "ledger", "breakdown", "rates"].map(key => <TabsTrigger key={key} value={key} data-testid={`expense-tab-${key}`}>{text(key)}</TabsTrigger>)}</TabsList>
      <TabsContent value="overview" className="mt-6"><ExpenseOverview data={data.overview} trend={data.trend} onBudget={row => setDialog({ type: "budget", row })} /></TabsContent>
      <TabsContent value="ledger" className="mt-6"><ExpenseLedger data={data.ledger} providers={data.overview.providers} evidence={evidence} setEvidence={v => { setEvidence(v); setPage(1); }} setPage={setPage} onEdit={row => setDialog({ type: "entry", row })} onSaved={() => load()} /></TabsContent>
      <TabsContent value="breakdown" className="mt-6"><ExpenseBreakdown data={data} /></TabsContent>
      <TabsContent value="rates" className="mt-6"><ExpenseRates rates={data.rates} providers={data.overview.providers} onAdd={() => setDialog({ type: "rate" })} onSaved={() => load()} /></TabsContent>
    </Tabs>}
    {dialog && data && <ExpenseDialog config={dialog} month={filters.month} providers={data.overview.providers} options={data.options} onClose={() => setDialog(null)} onSaved={() => { setDialog(null); load(); }} />}
  </section>;
};