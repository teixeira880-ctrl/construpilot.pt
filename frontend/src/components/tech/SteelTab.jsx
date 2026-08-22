import { useState } from "react";
import { Loader2, Sparkles, Trash2, Plus, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import PlanViewer from "@/components/tech/PlanViewer";
import ApproOrder from "@/components/tech/ApproOrder";

const conf = (c) => (c >= 0.85 ? { cls: "bg-emerald-500/15 text-emerald-600", lbl: "🟢" }
  : c >= 0.6 ? { cls: "bg-amber-500/15 text-amber-600", lbl: "🟠" }
    : { cls: "bg-red-500/15 text-red-600", lbl: "🔴" });

export default function SteelTab({ plans, suppliers }) {
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ana, setAna] = useState(null);
  const [loss, setLoss] = useState(7);
  const [barLen, setBarLen] = useState(12);
  const [count, setCount] = useState(1);
  const [cmd, setCmd] = useState(null);
  const [highlight, setHighlight] = useState(null);

  const analyze = async () => {
    if (!planId) return toast.error("Choisissez un plan");
    setBusy(true); setCmd(null); setHighlight(null);
    try {
      const { data } = await api.post(`/pro/steel/${planId}/analyze`);
      setAna(data);
      setCount(data.element_count || 1);
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
        { loss_pct: loss, bar_length_m: barLen, element_count: count });
      setCmd(data);
      toast.success("Quantités commandables calculées");
    } catch (e) { toast.error(e?.response?.data?.detail || "Calcul impossible"); }
  };

  const createOrder = async (supplierId) => {
    const { data } = await api.post(`/pro/steel/${planId}/order`,
      { loss_pct: loss, bar_length_m: barLen, element_count: count, supplier_id: supplierId || null });
    return data;
  };

  const items = cmd?.commandable?.items || [];

  return (
    <div className="space-y-5" data-testid="steel-tab">
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

      {ana && (ana.lines || []).length === 0 && (
        <div className="surface p-4 text-sm text-muted-foreground" data-testid="steel-empty-analysis">
          Aucun ferraillage détecté sur ce plan. Choisissez un plan de structure/armatures, ou ajoutez des lignes manuellement.
          <Button size="sm" variant="outline" onClick={addLine} className="ml-2 h-7 gap-1 rounded-sm"><Plus className="h-3.5 w-3.5" />Ajouter une ligne</Button>
        </div>
      )}

      {ana && (ana.lines || []).length > 0 && (
        <>
          <PlanViewer planId={planId} highlight={highlight} />
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
                  <th className="p-2 text-right">Poids kg</th><th className="p-2">Confiance</th><th className="p-2"></th><th className="p-2"></th>
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
                        <td className="p-2 text-center">
                          {l.bbox ? <button onClick={() => setHighlight(l.bbox)} title="Localiser sur le plan" data-testid={`rebar-locate-${i}`}><MapPin className="h-3.5 w-3.5 text-primary hover:scale-125 transition-transform" /></button> : null}
                        </td>
                        <td className="p-2 text-center"><button onClick={() => removeLine(i)} data-testid={`del-rebar-${i}`}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" /></button></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="mt-3 flex flex-wrap gap-4 text-sm">
              <span>Tonnage : <b>{ana.summary?.tonnage_t ?? 0} t</b></span>
              {ana.element_count > 1 && <span className="text-amber-600">Nombre d'éléments identiques détecté : <b>{ana.element_count}</b> (appliqué au calcul commandable)</span>}
              {(ana.treillis || []).length > 0 && <span>Treillis : <b>{ana.summary?.treillis_panels ?? 0} panneaux</b></span>}
            </div>
          </div>

          <div className="surface p-4 space-y-3">
            <h3 className="font-bold">Quantités commandables</h3>
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground">Pertes/chutes %</label><Input type="number" value={loss} onChange={(e) => setLoss(parseFloat(e.target.value) || 0)} className="h-8 w-24" data-testid="loss-input" /></div>
              <div><label className="text-xs text-muted-foreground">Longueur barre (m)</label><Input type="number" value={barLen} onChange={(e) => setBarLen(parseFloat(e.target.value) || 12)} className="h-8 w-24" data-testid="barlen-input" /></div>
              <div><label className="text-xs text-muted-foreground">Nb éléments identiques</label><Input type="number" value={count} onChange={(e) => setCount(parseInt(e.target.value) || 1)} className="h-8 w-24" data-testid="count-input" /></div>
              <Button onClick={compute} className="gap-2 rounded-sm" data-testid="compute-order-btn"><Sparkles className="h-4 w-4" />Calculer</Button>
            </div>
          </div>

          {items.length > 0 && (
            <ApproOrder items={items} suppliers={suppliers} csvName="bon_commande_acier.csv"
              createOrder={createOrder} onHighlight={setHighlight} />
          )}
          {cmd && items.length === 0 && (
            <div className="surface p-4 text-sm text-muted-foreground" data-testid="steel-empty-commandable">
              Aucune quantité commandable — vérifiez que des lignes d'acier sont présentes dans le bordereau ci-dessus.
            </div>
          )}
        </>
      )}
    </div>
  );
}
