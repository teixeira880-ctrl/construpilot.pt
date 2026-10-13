import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { TrendingUp, ChevronDown, ChevronUp, Plus, Trash2, CheckCircle2, RotateCcw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionTitle } from "@/components/Bits";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";

const L = {
  fr: {
    kinds: [["achat", "Outro"], ["main_oeuvre", "Outro"], ["sous_traitance", "Subempreitada"], ["location", "Outro"], ["encomenda", "Outro"], ["autre", "Outro"]],
    noDate: "Sem data", sold: "Vendido s/ IVA", quotedCost: "Custo orçam.", plannedMargin: "margem prevista", realBuy: "Compras reais", realMargin: "Margem real",
    reopen: "Reabrir a obra", finish: "Marcar concluída", label: "Descrição", labelPh: "Ex. Mosaico Point P", amount: "Montante s/ IVA (€)", type: "Tipo",
    order: "Nota de encomenda", date: "Data", add: "Adicionar", loading: "A carregar…", labelReq: "Descrição e montante obrigatórios", added: "Despesa adicionada",
    addErr: "Não foi possível adicionar", delErr: "Não foi possível eliminar", updErr: "Não foi possível atualizar", markedDone: "Obra marcada como concluída", reopened: "Obra reaberta", loadErr: "Não foi possível carregar",
    over: "Gestão", title: "Relatório de rentabilidade", sub: "Margem real por obra e por mês: preço vendido vs custo previsto no orçamento vs compras reais (despesas registadas, notas de encomenda).",
    includeOpen: "Incluir obras em curso (orçamentos assinados não concluídos)", quotesLink: "Acompanhamento de orçamentos →", kJobs: "Obras", kRev: "Volume de negócios s/ IVA", kMargin: "Margem real s/ IVA", kRate: "Taxa de margem",
    byMonth: "Por mês", monthlyEmpty: "Ainda não há obras concluídas: marque um orçamento assinado como « concluído » abaixo (ou selecione « incluir obras em curso »).",
    hMonth: "Mês", hJobs: "Obras", hRev: "CA HT", hQuoted: "Custo orçam.", hReal: "Custo real", hMargin: "Margem", hRate: "Taxa", byJob: "Por obra",
    jobsEmpty: (o) => `. As obras aparecem assim que um orçamento é assinado.${o ? "" : " . As obras aparecem assim que um orçamento é assinado."}. As obras aparecem assim que um orçamento é assinado.`, draft: "Rascunho", noClient: "Sem cliente", done: "concluída", open: "en cours",
    soldHt: "vendido s/ IVA", quotedCostS: "custo orçamento", realBuyS: "compras reais", marginS: "marge", real: "real", planned: "prevista", reportErr: "Relatório indisponível",
  },
  pt: {
    kinds: [["achat", "Compra de materiais"], ["main_oeuvre", "Mão de obra"], ["sous_traitance", "Subempreitada"], ["location", "Aluguer de equipamento"], ["commande", "Nota de encomenda fornecedor"], ["autre", "Outro"]],
    noDate: "Sem data", sold: "Vendido s/ IVA", quotedCost: "Custo orçamento", plannedMargin: "margem prevista", realBuy: "Compras reais", realMargin: "Margem real",
    reopen: "Reabrir a obra", finish: "Marcar concluída", label: "Descrição", labelPh: "Ex. Azulejo Leroy Merlin", amount: "Montante s/ IVA (€)", type: "Tipo",
    order: "Nota de encomenda", date: "Data", add: "Adicionar", loading: "A carregar…", labelReq: "Descrição e montante obrigatórios", added: "Despesa adicionada",
    addErr: "Não foi possível adicionar", delErr: "Não foi possível eliminar", updErr: "Não foi possível atualizar", markedDone: "Obra marcada como concluída", reopened: "Obra reaberta", loadErr: "Não foi possível carregar",
    over: "Gestão", title: "Relatório de rentabilidade", sub: "Margem real por obra e por mês: preço vendido vs custo previsto no orçamento vs compras reais (despesas registadas, notas de encomenda).",
    includeOpen: "Incluir obras em curso (orçamentos assinados não concluídos)", quotesLink: "Acompanhamento de orçamentos →", kJobs: "Obras", kRev: "Faturação s/ IVA", kMargin: "Margem real s/ IVA", kRate: "Taxa de margem",
    byMonth: "Por mês", monthlyEmpty: "Ainda não há obras concluídas: marque um orçamento assinado como « concluído » abaixo (ou selecione « incluir obras em curso »).",
    hMonth: "Mês", hJobs: "Obras", hRev: "Faturação", hQuoted: "Custo orçam.", hReal: "Custo real", hMargin: "Margem", hRate: "Taxa", byJob: "Por obra",
    jobsEmpty: (o) => `Nenhum orçamento assinado${o ? "" : " concluído"}. As obras aparecem assim que um orçamento é assinado.`, draft: "Rascunho", noClient: "Sem cliente", done: "concluída", open: "em curso",
    soldHt: "vendido s/ IVA", quotedCostS: "custo orçamento", realBuyS: "compras reais", marginS: "margem", real: "real", planned: "prevista", reportErr: "Relatório indisponível",
  },
};

const eur = (n) => `${Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`;
const pct = (p) => (p == null ? "—" : `${p} %`);
const MONTH = (m, T, loc) => (m && m !== "—" ? new Date(`${m}-01T00:00:00`).toLocaleDateString(loc, { month: "long", year: "numeric" }) : T.noDate);

const Kpi = ({ label, value, tid, accent }) => (
  <div className="surface p-4 rounded-xl" data-testid={tid}>
    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
    <div className={`mt-1 font-display text-2xl font-bold num ${accent || ""}`}>{value}</div>
  </div>
);

const MarginBadge = ({ p, tid }) => (
  <span data-testid={tid} className={`num font-semibold ${p == null ? "text-muted-foreground" : p < 0 ? "text-red-600" : p < 15 ? "text-amber-600" : "text-emerald-600"}`}>{pct(p)}</span>
);

const CostsPanel = ({ docId, onChange, T }) => {
  const KINDS = T.kinds;
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ label: "", amount_ht: "", kind: "achat", date: "", supplier: "", order_id: "" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const { data: d } = await api.get(`/pro/profitability/${docId}/costs`);
    setData(d);
  }, [docId]);
  useEffect(() => { load().catch(() => toast.error(T.loadErr)); }, [load]);

  const add = async () => {
    if (!form.label.trim() || !(Number(form.amount_ht) >= 0)) { toast.error(T.labelReq); return; }
    setBusy(true);
    try {
      const { data: d } = await api.post(`/pro/profitability/${docId}/costs`, {
        ...form, amount_ht: Number(form.amount_ht), date: form.date || null, supplier: form.supplier || null, order_id: form.order_id || null,
      });
      setData(d); setForm({ label: "", amount_ht: "", kind: "achat", date: "", supplier: "", order_id: "" });
      toast.success(T.added); onChange?.();
    } catch (e) { toast.error(e?.response?.data?.detail || T.addErr); } finally { setBusy(false); }
  };
  const remove = async (id) => {
    try { await api.delete(`/pro/profitability/costs/${id}`); await load(); onChange?.(); } catch { toast.error(T.delErr); }
  };
  const toggleFinish = async () => {
    try {
      const { data: d } = await api.patch(`/pro/profitability/${docId}/finish`, { finished: !data.job.finished });
      setData(d); onChange?.(); toast.success(d.job.finished ? T.markedDone : T.reopened);
    } catch { toast.error(T.updErr); }
  };

  if (!data) return <div className="p-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />{T.loading}</div>;
  const j = data.job;
  return (
    <div className="p-4 bg-secondary/20 border-t border-border/50 grid gap-4" data-testid={`profit-costs-${docId}`}>
      <div className="flex flex-wrap gap-4 text-sm">
        <span>{T.sold} : <b className="num">{eur(j.revenue_ht)}</b></span>
        <span>{T.quotedCost} : <b className="num">{eur(j.quoted_cost_ht)}</b> ({T.plannedMargin} <MarginBadge p={j.quoted_margin_pct} />)</span>
        <span>{T.realBuy} : <b className="num" data-testid={`profit-real-cost-${docId}`}>{eur(j.real_cost_ht)}</b></span>
        <span>{T.realMargin} : <b className="num">{eur(j.margin_ht)}</b> (<MarginBadge p={j.margin_pct} tid={`profit-real-margin-${docId}`} />)</span>
        <Button size="sm" variant={j.finished ? "outline" : "default"} onClick={toggleFinish} className="rounded-sm gap-1.5 ml-auto h-8" data-testid={`profit-finish-${docId}`}>
          {j.finished ? <><RotateCcw className="h-3.5 w-3.5" /> {T.reopen}</> : <><CheckCircle2 className="h-3.5 w-3.5" /> {T.finish}</>}
        </Button>
      </div>
      {data.costs.length > 0 && (
        <table className="w-full text-sm" data-testid={`profit-costs-table-${docId}`}>
          <tbody>
            {data.costs.map((c) => (
              <tr key={c.cost_id} className="border-b border-border/30" data-testid={`profit-cost-row-${c.cost_id}`}>
                <td className="py-1.5 text-muted-foreground w-24">{c.date}</td>
                <td className="py-1.5">{c.label}{c.supplier ? <span className="text-muted-foreground"> · {c.supplier}</span> : null}</td>
                <td className="py-1.5 text-xs text-muted-foreground">{KINDS.find((k) => k[0] === c.kind)?.[1] || c.kind}{c.order_id ? ` · ${c.order_id}` : ""}</td>
                <td className="py-1.5 text-right num font-medium">{eur(c.amount_ht)}</td>
                <td className="py-1.5 pl-2 w-8"><button onClick={() => remove(c.cost_id)} className="text-muted-foreground hover:text-red-600" data-testid={`profit-cost-delete-${c.cost_id}`}><Trash2 className="h-4 w-4" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="grid sm:grid-cols-2 lg:grid-cols-6 gap-2 items-end">
        <label className="grid gap-1 text-xs lg:col-span-2">{T.label}
          <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder={T.labelPh} className="rounded-sm h-9" data-testid={`profit-cost-label-${docId}`} />
        </label>
        <label className="grid gap-1 text-xs">{T.amount}
          <Input type="number" min="0" step="0.01" value={form.amount_ht} onChange={(e) => setForm({ ...form, amount_ht: e.target.value })} className="rounded-sm h-9 num" data-testid={`profit-cost-amount-${docId}`} />
        </label>
        <label className="grid gap-1 text-xs">{T.type}
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="h-9 w-full min-w-0 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`profit-cost-kind-${docId}`}>
            {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {form.kind === "encomenda" ? (
          <label className="grid gap-1 text-xs">{T.order}
            <select value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })} className="h-9 w-full min-w-0 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`profit-cost-order-${docId}`}>
              <option value="">—</option>
              {data.orders.map((o) => <option key={o.order_id} value={o.order_id}>{o.order_id} · {o.type}{o.supplier ? ` · ${o.supplier}` : ""}</option>)}
            </select>
          </label>
        ) : (
          <label className="grid gap-1 text-xs">{T.date}
            <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="rounded-sm h-9" data-testid={`profit-cost-date-${docId}`} />
          </label>
        )}
        <Button onClick={add} disabled={busy} className="rounded-sm h-9 gap-1.5" data-testid={`profit-cost-add-${docId}`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} {T.add}
        </Button>
      </div>
    </div>
  );
};

export default function Profitability() {
  const { lang } = useI18n();
  const T = L[lang === "pt" ? "pt" : "fr"];
  const loc = lang === "pt" ? "pt-PT" : "fr-FR";
  const [report, setReport] = useState(null);
  const [includeOpen, setIncludeOpen] = useState(false);
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/pro/profitability?months=12&include_open=${includeOpen}`);
      setReport(data);
    } catch { toast.error(T.reportErr); }
  }, [includeOpen]);
  useEffect(() => { load(); }, [load]);

  const s = report?.summary;
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 grid gap-6" data-testid="profitability-page">
      <SectionTitle over={T.over} title={T.title} as="h1">{T.sub}</SectionTitle>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={includeOpen} onChange={(e) => setIncludeOpen(e.target.checked)} data-testid="profit-include-open" />
          {T.includeOpen}
        </label>
        <Link to="/devis" className="text-primary underline-offset-2 hover:underline ml-auto">{T.quotesLink}</Link>
      </div>
      {s && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi label={T.kJobs} value={s.jobs} tid="profit-kpi-jobs" />
          <Kpi label={T.kRev} value={eur(s.revenue_ht)} tid="profit-kpi-revenue" />
          <Kpi label={T.kMargin} value={eur(s.margin_ht)} tid="profit-kpi-margin" accent={s.margin_ht < 0 ? "text-red-600" : "text-emerald-600"} />
          <Kpi label={T.kRate} value={pct(s.margin_pct)} tid="profit-kpi-margin-pct" />
        </div>
      )}
      {report && (
        <div className="surface rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border/60 font-display font-bold flex items-center gap-2"><TrendingUp className="h-4 w-4 text-primary" /> {T.byMonth}</div>
          {report.monthly.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground" data-testid="profit-monthly-empty">{T.monthlyEmpty}</p>
          ) : (
            <table className="w-full text-sm" data-testid="profit-monthly-table">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground bg-secondary/30">
                <tr><th className="text-left px-4 py-2">{T.hMonth}</th><th className="text-right px-2 py-2">{T.hJobs}</th><th className="text-right px-2 py-2">{T.hRev}</th><th className="text-right px-2 py-2">{T.hQuoted}</th><th className="text-right px-2 py-2">{T.hReal}</th><th className="text-right px-2 py-2">{T.hMargin}</th><th className="text-right px-4 py-2">{T.hRate}</th></tr>
              </thead>
              <tbody>
                {report.monthly.map((m) => (
                  <tr key={m.month} className="border-t border-border/40" data-testid={`profit-month-${m.month}`}>
                    <td className="px-4 py-2 capitalize">{MONTH(m.month, T, loc)}</td>
                    <td className="px-2 py-2 text-right num">{m.jobs}</td>
                    <td className="px-2 py-2 text-right num">{eur(m.revenue_ht)}</td>
                    <td className="px-2 py-2 text-right num text-muted-foreground">{eur(m.quoted_cost_ht)}</td>
                    <td className="px-2 py-2 text-right num">{eur(m.real_cost_ht)}</td>
                    <td className="px-2 py-2 text-right num font-medium">{eur(m.margin_ht)}</td>
                    <td className="px-4 py-2 text-right"><MarginBadge p={m.margin_pct} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      {report && (
        <div className="surface rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border/60 font-display font-bold">{T.byJob}</div>
          {report.jobs.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground" data-testid="profit-jobs-empty">{T.jobsEmpty(includeOpen)}</p>
          ) : report.jobs.map((j) => (
            <div key={j.doc_id} className="border-t border-border/40" data-testid={`profit-job-${j.doc_id}`}>
              <button onClick={() => setOpen(open === j.doc_id ? null : j.doc_id)} className="w-full text-left px-4 py-3 grid grid-cols-2 lg:grid-cols-7 gap-2 items-center hover:bg-secondary/20" data-testid={`profit-job-toggle-${j.doc_id}`}>
                <div className="lg:col-span-2">
                  <div className="font-medium truncate">{j.number || T.draft} — {j.title}</div>
                  <div className="text-xs text-muted-foreground">{j.client || T.noClient} · {MONTH(j.month, T, loc)} · {j.finished ? <span className="text-emerald-600">{T.done}</span> : T.open}</div>
                </div>
                <div className="text-right num text-sm">{eur(j.revenue_ht)}<div className="text-[10px] text-muted-foreground">{T.soldHt}</div></div>
                <div className="text-right num text-sm text-muted-foreground">{eur(j.quoted_cost_ht)}<div className="text-[10px]">{T.quotedCostS}</div></div>
                <div className="text-right num text-sm">{j.cost_basis === "reel" ? eur(j.real_cost_ht) : "—"}<div className="text-[10px] text-muted-foreground">{T.realBuyS}{j.costs_count ? ` (${j.costs_count})` : ""}</div></div>
                <div className="text-right num text-sm font-semibold">{eur(j.margin_ht)}<div className="text-[10px] text-muted-foreground">{T.marginS} {j.cost_basis === "reel" ? T.real : T.planned}</div></div>
                <div className="text-right flex items-center justify-end gap-2"><MarginBadge p={j.margin_pct} tid={`profit-job-margin-${j.doc_id}`} />{open === j.doc_id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</div>
              </button>
              {open === j.doc_id && <CostsPanel docId={j.doc_id} onChange={load} T={T} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
