import { useEffect, useState } from "react";
import { Loader2, Sparkles, Trash2, Plus, Download, Truck, ShoppingCart, HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

const conf = (c) => (c >= 0.85 ? { cls: "bg-emerald-500/15 text-emerald-600", lbl: "🟢" }
  : c >= 0.6 ? { cls: "bg-amber-500/15 text-amber-600", lbl: "🟠" }
    : { cls: "bg-red-500/15 text-red-600", lbl: "🔴" });
const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR");

export default function TechAnalysis() {
  const [tab, setTab] = useState("acier");
  const [plans, setPlans] = useState([]);
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ana, setAna] = useState(null);
  const [loss, setLoss] = useState(7);
  const [barLen, setBarLen] = useState(12);
  const [cmd, setCmd] = useState(null);
  const [supplierId, setSupplierId] = useState("");
  const [suppliers, setSuppliers] = useState([]);

  useEffect(() => {
    api.get("/takeoffs").then(({ data }) => {
      const items = Array.isArray(data) ? data : (data.items || data.takeoffs || []);
      setPlans(items);
    }).catch(() => {});
    loadSuppliers();
  }, []);

  const loadSuppliers = () => api.get("/pro/suppliers").then(({ data }) => setSuppliers(data.items || [])).catch(() => {});

  const analyze = async () => {
    if (!planId) return toast.error("Choisissez un plan");
    setBusy(true); setCmd(null);
    try {
      const { data } = await api.post(`/pro/steel/${planId}/analyze`);
      setAna(data);
      toast.success("Ferraillage analysé");
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse impossible"); }
    finally { setBusy(false); }
  };

  const updateLine = (i, field, val) => {
    const lines = [...ana.lines];
    lines[i] = { ...lines[i], [field]: field === "ml" ? parseFloat(val) || 0 : val };
    setAna({ ...ana, lines });
  };
  const removeLine = (i) => setAna({ ...ana, lines: ana.lines.filter((_, k) => k !== i) });
  const addLine = () => setAna({ ...ana, lines: [...(ana?.lines || []), { diameter: "HA12", ml: 0, zone: "", confidence: 1 }] });

  const save = async () => {
    try {
      const { data } = await api.put(`/pro/steel/${planId}`, { lines: ana.lines, treillis: ana.treillis || [] });
      setAna({ ...ana, ...data });
      toast.success("Bordereau enregistré");
    } catch { toast.error("Enregistrement impossible"); }
  };

  const compute = async () => {
    try {
      const { data } = await api.post(`/pro/steel/${planId}/commandable`,
        { loss_pct: loss, bar_length_m: barLen, supplier_id: supplierId || null });
      setCmd(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Calcul impossible"); }
  };

  const downloadCsv = () => {
    if (!cmd?.csv) return;
    const blob = new Blob([cmd.csv], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = "bon_commande_acier.csv"; a.click();
  };

  const createOrder = async () => {
    try {
      await api.post(`/pro/steel/${planId}/order`, { loss_pct: loss, bar_length_m: barLen, supplier_id: supplierId || null });
      toast.success("Bon de commande créé (brouillon) — validez l'envoi au fournisseur");
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossible"); }
  };

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6" data-testid="tech-analysis-page">
      <div className="flex items-center gap-3">
        <HardHat className="h-6 w-6 text-primary" />
        <h1 className="font-display text-2xl font-bold">Analyse technique &amp; Approvisionnement IA</h1>
        <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro · Phase 1 · Acier</span>
      </div>

      <div className="flex gap-2 border-b border-border">
        {[["acier", "Ferraillage / Acier"], ["fournisseurs", "Mes fournisseurs"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>{l}</button>
        ))}
      </div>

      {tab === "acier" && (
        <div className="space-y-5">
          <div className="surface p-4 flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[220px]">
              <label className="text-xs text-muted-foreground">Plan à analyser</label>
              <select value={planId} onChange={(e) => setPlanId(e.target.value)} data-testid="plan-select"
                className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm">
                <option value="">— Choisir un plan —</option>
                {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
              </select>
            </div>
            <Button onClick={analyze} disabled={busy || !planId} className="gap-2 rounded-sm" data-testid="analyze-rebar-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {busy ? "Analyse IA…" : "Analyser le ferraillage"}
            </Button>
          </div>

          {ana && (
            <>
              <div className="surface p-4" data-testid="rebar-bordereau">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-bold">Bordereau acier</h3>
                  <div className="flex gap-2">
                    <Button size="sm" variant="outline" onClick={addLine} className="gap-1 rounded-sm"><Plus className="h-3.5 w-3.5" />Ligne</Button>
                    <Button size="sm" onClick={save} className="rounded-sm" data-testid="save-bordereau">Enregistrer</Button>
                  </div>
                </div>
                {ana.scale_confidence != null && (
                  <p className="text-xs text-muted-foreground mb-2">Échelle : {ana.scale_detected || "incertaine"} · confiance {Math.round((ana.scale_confidence || 0) * 100)}%
                    {(ana.scale_confidence || 0) < 0.6 && <span className="text-red-600"> — calibration conseillée</span>}</p>
                )}
                <div className="overflow-auto rounded-sm border border-border">
                  <table className="w-full text-xs">
                    <thead className="bg-secondary/40"><tr>
                      <th className="text-left p-2">Ø</th><th className="p-2">Zone</th><th className="p-2 text-right">ml</th>
                      <th className="p-2 text-right">Poids kg</th><th className="p-2">Confiance</th><th className="p-2"></th>
                    </tr></thead>
                    <tbody>
                      {(ana.lines || []).map((l, i) => {
                        const c = conf(l.confidence ?? 1);
                        return (
                          <tr key={i} className="border-t border-border/60" data-testid={`rebar-row-${i}`}>
                            <td className="p-1"><Input value={l.diameter} onChange={(e) => updateLine(i, "diameter", e.target.value)} className="h-7 w-20 text-xs" /></td>
                            <td className="p-1"><Input value={l.zone || ""} onChange={(e) => updateLine(i, "zone", e.target.value)} className="h-7 text-xs" /></td>
                            <td className="p-1"><Input value={l.ml} onChange={(e) => updateLine(i, "ml", e.target.value)} className="h-7 w-24 text-xs text-right" /></td>
                            <td className="p-2 text-right num">{l.kg}</td>
                            <td className="p-2 text-center"><span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${c.cls}`}>{c.lbl} {Math.round((l.confidence ?? 1) * 100)}%</span></td>
                            <td className="p-2 text-center"><button onClick={() => removeLine(i)} data-testid={`del-rebar-${i}`}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" /></button></td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 flex flex-wrap gap-4 text-sm">
                  <span>Tonnage : <b>{ana.summary?.tonnage_t ?? 0} t</b></span>
                  {(ana.treillis || []).length > 0 && <span>Treillis : <b>{ana.summary?.treillis_panels ?? 0} panneaux</b></span>}
                </div>
              </div>

              <div className="surface p-4 space-y-3" data-testid="commandable-block">
                <h3 className="font-bold flex items-center gap-2"><Truck className="h-4 w-4 text-primary" />Quantités commandables</h3>
                <div className="flex flex-wrap items-end gap-3">
                  <div><label className="text-xs text-muted-foreground">Pertes/chutes %</label><Input type="number" value={loss} onChange={(e) => setLoss(parseFloat(e.target.value) || 0)} className="h-8 w-24" data-testid="loss-input" /></div>
                  <div><label className="text-xs text-muted-foreground">Longueur barre (m)</label><Input type="number" value={barLen} onChange={(e) => setBarLen(parseFloat(e.target.value) || 12)} className="h-8 w-24" data-testid="barlen-input" /></div>
                  <div className="min-w-[200px]"><label className="text-xs text-muted-foreground">Fournisseur</label>
                    <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)} className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm" data-testid="supplier-select">
                      <option value="">— Aucun —</option>
                      {suppliers.map((s) => <option key={s.supplier_id} value={s.supplier_id}>{s.name}{s.agency ? ` (${s.agency})` : ""}</option>)}
                    </select>
                  </div>
                  <Button onClick={compute} className="gap-2 rounded-sm" data-testid="compute-order-btn"><ShoppingCart className="h-4 w-4" />Calculer</Button>
                </div>
                {cmd && (
                  <div>
                    <div className="overflow-auto rounded-sm border border-border">
                      <table className="w-full text-xs"><thead className="bg-secondary/40"><tr>
                        <th className="text-left p-2">Désignation</th><th className="p-2 text-right">ml cmd</th><th className="p-2 text-right">Qté</th><th className="p-2">Unité</th>
                      </tr></thead>
                        <tbody>{cmd.commandable.items.map((it, i) => (
                          <tr key={i} className="border-t border-border/60" data-testid={`cmd-row-${i}`}>
                            <td className="p-2">{it.designation}</td><td className="p-2 text-right num">{it.ml_commande ?? "—"}</td>
                            <td className="p-2 text-right num font-semibold">{it.qty}</td><td className="p-2 text-center">{it.unit}</td>
                          </tr>))}</tbody>
                      </table>
                    </div>
                    <div className="flex gap-2 mt-3">
                      <Button size="sm" variant="outline" onClick={downloadCsv} className="gap-2 rounded-sm" data-testid="csv-btn"><Download className="h-4 w-4" />CSV</Button>
                      <Button size="sm" onClick={createOrder} className="gap-2 rounded-sm" data-testid="create-order-btn">Créer le bon de commande</Button>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-2">Aucune commande n'est envoyée sans votre validation. Le bon de commande est créé en brouillon.</p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {tab === "fournisseurs" && <SupplierManager suppliers={suppliers} reload={loadSuppliers} />}
    </div>
  );
}

const SupplierManager = ({ suppliers, reload }) => {
  const empty = { name: "", agency: "", client_number: "", email: "", phone: "", delivery_address: "", categories: [] };
  const [form, setForm] = useState(empty);
  const save = async () => {
    if (!form.name) return toast.error("Nom requis");
    try { await api.post("/pro/suppliers", { ...form, categories: form.categories || [] }); toast.success("Fournisseur ajouté"); setForm(empty); reload(); }
    catch { toast.error("Impossible"); }
  };
  const del = async (id) => { try { await api.delete(`/pro/suppliers/${id}`); reload(); } catch { toast.error("Impossible"); } };
  return (
    <div className="grid md:grid-cols-2 gap-5" data-testid="suppliers-tab">
      <div className="surface p-4 space-y-2">
        <h3 className="font-bold mb-1">Ajouter un fournisseur</h3>
        {[["name", "Nom *"], ["agency", "Agence"], ["client_number", "N° client"], ["email", "Email"], ["phone", "Téléphone"], ["delivery_address", "Adresse de livraison"]].map(([k, l]) => (
          <div key={k}><label className="text-xs text-muted-foreground">{l}</label>
            <Input value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="h-8" data-testid={`supplier-${k}`} /></div>
        ))}
        <Button onClick={save} className="mt-2 rounded-sm gap-2" data-testid="add-supplier-btn"><Plus className="h-4 w-4" />Ajouter</Button>
      </div>
      <div className="surface p-4">
        <h3 className="font-bold mb-2">Mes fournisseurs ({suppliers.length})</h3>
        {suppliers.length === 0 && <p className="text-sm text-muted-foreground">Aucun fournisseur enregistré.</p>}
        <div className="space-y-2">
          {suppliers.map((s) => (
            <div key={s.supplier_id} className="flex items-center justify-between rounded-sm border border-border p-2 text-sm" data-testid={`supplier-item-${s.supplier_id}`}>
              <div><div className="font-semibold">{s.name}{s.agency ? ` · ${s.agency}` : ""}</div>
                <div className="text-xs text-muted-foreground">{[s.client_number, s.email, s.phone].filter(Boolean).join(" · ")}</div></div>
              <button onClick={() => del(s.supplier_id)} data-testid={`del-supplier-${s.supplier_id}`}><Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" /></button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
