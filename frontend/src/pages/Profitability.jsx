import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { TrendingUp, ChevronDown, ChevronUp, Plus, Trash2, CheckCircle2, RotateCcw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionTitle } from "@/components/Bits";
import { api } from "@/lib/api";

const eur = (n) => `${Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 0, maximumFractionDigits: 0 })} €`;
const pct = (p) => (p == null ? "—" : `${p} %`);
const KINDS = [["achat", "Achat matériaux"], ["main_oeuvre", "Main-d'œuvre"], ["sous_traitance", "Sous-traitance"],
  ["location", "Location matériel"], ["commande", "Bon de commande fournisseur"], ["autre", "Autre"]];
const MONTH = (m) => (m && m !== "—" ? new Date(`${m}-01T00:00:00`).toLocaleDateString("fr-FR", { month: "long", year: "numeric" }) : "Sans date");

const Kpi = ({ label, value, tid, accent }) => (
  <div className="surface p-4 rounded-xl" data-testid={tid}>
    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
    <div className={`mt-1 font-display text-2xl font-bold num ${accent || ""}`}>{value}</div>
  </div>
);

const MarginBadge = ({ p, tid }) => (
  <span data-testid={tid} className={`num font-semibold ${p == null ? "text-muted-foreground" : p < 0 ? "text-red-600" : p < 15 ? "text-amber-600" : "text-emerald-600"}`}>{pct(p)}</span>
);

const CostsPanel = ({ docId, onChange }) => {
  const [data, setData] = useState(null);
  const [form, setForm] = useState({ label: "", amount_ht: "", kind: "achat", date: "", supplier: "", order_id: "" });
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const { data: d } = await api.get(`/pro/profitability/${docId}/costs`);
    setData(d);
  }, [docId]);
  useEffect(() => { load().catch(() => toast.error("Chargement impossible")); }, [load]);

  const add = async () => {
    if (!form.label.trim() || !(Number(form.amount_ht) >= 0)) { toast.error("Libellé et montant requis"); return; }
    setBusy(true);
    try {
      const { data: d } = await api.post(`/pro/profitability/${docId}/costs`, {
        ...form, amount_ht: Number(form.amount_ht), date: form.date || null, supplier: form.supplier || null, order_id: form.order_id || null,
      });
      setData(d); setForm({ label: "", amount_ht: "", kind: "achat", date: "", supplier: "", order_id: "" });
      toast.success("Dépense ajoutée"); onChange?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Ajout impossible"); } finally { setBusy(false); }
  };
  const remove = async (id) => {
    try { await api.delete(`/pro/profitability/costs/${id}`); await load(); onChange?.(); } catch { toast.error("Suppression impossible"); }
  };
  const toggleFinish = async () => {
    try {
      const { data: d } = await api.patch(`/pro/profitability/${docId}/finish`, { finished: !data.job.finished });
      setData(d); onChange?.(); toast.success(d.job.finished ? "Chantier marqué terminé" : "Chantier rouvert");
    } catch { toast.error("Mise à jour impossible"); }
  };

  if (!data) return <div className="p-4 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Chargement…</div>;
  const j = data.job;
  return (
    <div className="p-4 bg-secondary/20 border-t border-border/50 grid gap-4" data-testid={`profit-costs-${docId}`}>
      <div className="flex flex-wrap gap-4 text-sm">
        <span>Vendu HT : <b className="num">{eur(j.revenue_ht)}</b></span>
        <span>Coût devis : <b className="num">{eur(j.quoted_cost_ht)}</b> (marge prévue <MarginBadge p={j.quoted_margin_pct} />)</span>
        <span>Achats réels : <b className="num" data-testid={`profit-real-cost-${docId}`}>{eur(j.real_cost_ht)}</b></span>
        <span>Marge réelle : <b className="num">{eur(j.margin_ht)}</b> (<MarginBadge p={j.margin_pct} tid={`profit-real-margin-${docId}`} />)</span>
        <Button size="sm" variant={j.finished ? "outline" : "default"} onClick={toggleFinish} className="rounded-sm gap-1.5 ml-auto h-8" data-testid={`profit-finish-${docId}`}>
          {j.finished ? <><RotateCcw className="h-3.5 w-3.5" /> Rouvrir le chantier</> : <><CheckCircle2 className="h-3.5 w-3.5" /> Marquer terminé</>}
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
        <label className="grid gap-1 text-xs lg:col-span-2">Libellé
          <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Ex. Carrelage Point P" className="rounded-sm h-9" data-testid={`profit-cost-label-${docId}`} />
        </label>
        <label className="grid gap-1 text-xs">Montant HT (€)
          <Input type="number" min="0" step="0.01" value={form.amount_ht} onChange={(e) => setForm({ ...form, amount_ht: e.target.value })} className="rounded-sm h-9 num" data-testid={`profit-cost-amount-${docId}`} />
        </label>
        <label className="grid gap-1 text-xs">Type
          <select value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })} className="h-9 w-full min-w-0 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`profit-cost-kind-${docId}`}>
            {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {form.kind === "commande" ? (
          <label className="grid gap-1 text-xs">Bon de commande
            <select value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })} className="h-9 w-full min-w-0 rounded-sm border border-input bg-background px-2 text-sm" data-testid={`profit-cost-order-${docId}`}>
              <option value="">—</option>
              {data.orders.map((o) => <option key={o.order_id} value={o.order_id}>{o.order_id} · {o.type}{o.supplier ? ` · ${o.supplier}` : ""}</option>)}
            </select>
          </label>
        ) : (
          <label className="grid gap-1 text-xs">Date
            <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="rounded-sm h-9" data-testid={`profit-cost-date-${docId}`} />
          </label>
        )}
        <Button onClick={add} disabled={busy} className="rounded-sm h-9 gap-1.5" data-testid={`profit-cost-add-${docId}`}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Ajouter
        </Button>
      </div>
    </div>
  );
};

export default function Profitability() {
  const [report, setReport] = useState(null);
  const [includeOpen, setIncludeOpen] = useState(false);
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/pro/profitability?months=12&include_open=${includeOpen}`);
      setReport(data);
    } catch { toast.error("Rapport indisponible"); }
  }, [includeOpen]);
  useEffect(() => { load(); }, [load]);

  const s = report?.summary;
  return (
    <div className="max-w-6xl mx-auto px-4 py-8 grid gap-6" data-testid="profitability-page">
      <SectionTitle over="Pilotage" title="Rapport de rentabilité" as="h1">Marge réelle par chantier et par mois : prix vendu vs coût prévu au devis vs achats réels (dépenses saisies, bons de commande).</SectionTitle>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={includeOpen} onChange={(e) => setIncludeOpen(e.target.checked)} data-testid="profit-include-open" />
          Inclure les chantiers en cours (devis signés non terminés)
        </label>
        <Link to="/devis" className="text-primary underline-offset-2 hover:underline ml-auto">Suivi des devis →</Link>
      </div>
      {s && (
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <Kpi label="Chantiers" value={s.jobs} tid="profit-kpi-jobs" />
          <Kpi label="Chiffre d'affaires HT" value={eur(s.revenue_ht)} tid="profit-kpi-revenue" />
          <Kpi label="Marge réelle HT" value={eur(s.margin_ht)} tid="profit-kpi-margin" accent={s.margin_ht < 0 ? "text-red-600" : "text-emerald-600"} />
          <Kpi label="Taux de marge" value={pct(s.margin_pct)} tid="profit-kpi-margin-pct" />
        </div>
      )}
      {report && (
        <div className="surface rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-border/60 font-display font-bold flex items-center gap-2"><TrendingUp className="h-4 w-4 text-primary" /> Par mois</div>
          {report.monthly.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground" data-testid="profit-monthly-empty">Aucun chantier terminé pour l'instant : marquez un devis signé comme « terminé » ci-dessous (ou cochez « inclure les chantiers en cours »).</p>
          ) : (
            <table className="w-full text-sm" data-testid="profit-monthly-table">
              <thead className="text-[11px] uppercase tracking-wide text-muted-foreground bg-secondary/30">
                <tr><th className="text-left px-4 py-2">Mois</th><th className="text-right px-2 py-2">Chantiers</th><th className="text-right px-2 py-2">CA HT</th><th className="text-right px-2 py-2">Coût devis</th><th className="text-right px-2 py-2">Coût réel</th><th className="text-right px-2 py-2">Marge</th><th className="text-right px-4 py-2">Taux</th></tr>
              </thead>
              <tbody>
                {report.monthly.map((m) => (
                  <tr key={m.month} className="border-t border-border/40" data-testid={`profit-month-${m.month}`}>
                    <td className="px-4 py-2 capitalize">{MONTH(m.month)}</td>
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
          <div className="px-4 py-3 border-b border-border/60 font-display font-bold">Par chantier</div>
          {report.jobs.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground" data-testid="profit-jobs-empty">Aucun devis signé{includeOpen ? "" : " terminé"}. Les chantiers apparaissent dès qu'un devis est signé.</p>
          ) : report.jobs.map((j) => (
            <div key={j.doc_id} className="border-t border-border/40" data-testid={`profit-job-${j.doc_id}`}>
              <button onClick={() => setOpen(open === j.doc_id ? null : j.doc_id)} className="w-full text-left px-4 py-3 grid grid-cols-2 lg:grid-cols-7 gap-2 items-center hover:bg-secondary/20" data-testid={`profit-job-toggle-${j.doc_id}`}>
                <div className="lg:col-span-2">
                  <div className="font-medium truncate">{j.number || "Brouillon"} — {j.title}</div>
                  <div className="text-xs text-muted-foreground">{j.client || "Sans client"} · {MONTH(j.month)} · {j.finished ? <span className="text-emerald-600">terminé</span> : "en cours"}</div>
                </div>
                <div className="text-right num text-sm">{eur(j.revenue_ht)}<div className="text-[10px] text-muted-foreground">vendu HT</div></div>
                <div className="text-right num text-sm text-muted-foreground">{eur(j.quoted_cost_ht)}<div className="text-[10px]">coût devis</div></div>
                <div className="text-right num text-sm">{j.cost_basis === "reel" ? eur(j.real_cost_ht) : "—"}<div className="text-[10px] text-muted-foreground">achats réels{j.costs_count ? ` (${j.costs_count})` : ""}</div></div>
                <div className="text-right num text-sm font-semibold">{eur(j.margin_ht)}<div className="text-[10px] text-muted-foreground">marge {j.cost_basis === "reel" ? "réelle" : "prévue"}</div></div>
                <div className="text-right flex items-center justify-end gap-2"><MarginBadge p={j.margin_pct} tid={`profit-job-margin-${j.doc_id}`} />{open === j.doc_id ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</div>
              </button>
              {open === j.doc_id && <CostsPanel docId={j.doc_id} onChange={load} />}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
