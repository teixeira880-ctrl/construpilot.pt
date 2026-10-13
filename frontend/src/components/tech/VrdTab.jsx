import { useEffect, useState } from "react";
import { Loader2, Sparkles, Truck, Waves, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import PlanViewer from "@/components/tech/PlanViewer";
import ApproOrder from "@/components/tech/ApproOrder";

export default function VrdTab({ plans, suppliers }) {
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ana, setAna] = useState(null);
  const [catalog, setCatalog] = useState([]);
  const [nets, setNets] = useState([]);
  const [loss, setLoss] = useState(5);
  const [cmd, setCmd] = useState(null);
  const [highlight, setHighlight] = useState(null);
  const [addKey, setAddKey] = useState("EP");

  useEffect(() => {
    api.get("/pro/vrd/networks").then(({ data }) => setCatalog(data.items || [])).catch(() => {});
  }, []);

  const label = (k) => catalog.find((c) => c.key === k)?.label || k;

  const analyze = async () => {
    if (!planId) return toast.error("Escolha uma planta");
    setBusy(true); setCmd(null); setHighlight(null);
    try {
      const { data } = await api.post(`/pro/vrd/${planId}/analyze`);
      setAna(data);
      setNets((data.networks || []).map((n) => ({
        key: n.key, length_ml: n.length_ml || 0,
        larg_m: n.larg_m || catalog.find((c) => c.key === n.key)?.larg || 0.4,
        prof_m: n.prof_m || catalog.find((c) => c.key === n.key)?.prof || 0.8,
        bbox: n.bbox || null, confidence: n.confidence || 0.9,
      })));
      toast.success((data.networks || []).length ? "VRD analisado" : "Nenhuma rede detetada — adicione-as manualmente");
    } catch (e) { toast.error(e?.response?.data?.detail || "Análise impossível"); }
    finally { setBusy(false); }
  };

  const setNet = (i, field, val) => {
    const n = [...nets];
    n[i] = { ...n[i], [field]: field === "key" ? val : (parseFloat(val) || 0) };
    setNets(n);
  };
  const removeNet = (i) => setNets(nets.filter((_, k) => k !== i));
  const addNet = () => {
    const c = catalog.find((x) => x.key === addKey);
    setNets([...nets, { key: addKey, length_ml: 0, larg_m: c?.larg || 0.4, prof_m: c?.prof || 0.8, confidence: 0.9 }]);
  };

  const compute = async () => {
    if (!nets.length) return toast.error("Adicione pelo menos uma rede");
    try {
      const { data } = await api.post(`/pro/vrd/${planId}/recompute`, { networks: nets, loss_pct: loss });
      setCmd(data);
      toast.success("Mapa VRD recalculado");
    } catch (e) { toast.error(e?.response?.data?.detail || "Cálculo impossível"); }
  };

  const createOrder = async (supplierId) => {
    const { data } = await api.post(`/pro/vrd/${planId}/order`, { supplier_id: supplierId || null });
    return data;
  };

  const items = cmd?.compute?.items || ana?.compute?.items || [];
  const totals = cmd?.compute?.totals || ana?.compute?.totals;

  return (
    <div className="space-y-5" data-testid="vrd-tab">
      <div className="surface p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-muted-foreground">Planta VRD / planta de implantação</label>
          <select value={planId} onChange={(e) => setPlanId(e.target.value)} data-testid="vrd-plan-select"
            className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm">
            <option value="">— Escolher uma planta —</option>
            {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
          </select>
        </div>
        <Button onClick={analyze} disabled={busy || !planId} className="gap-2 rounded-sm" data-testid="analyze-vrd-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "Análise IA…" : "Analisar o VRD"}
        </Button>
      </div>

      {ana && (
        <>
          <div className="surface p-4 space-y-3" data-testid="vrd-networks">
            <h3 className="font-bold flex items-center gap-2"><Waves className="h-4 w-4 text-primary" />Redes &amp; valas</h3>
            {ana.scale_confidence != null && (
              <p className="text-xs text-muted-foreground">Escala: {ana.scale_detected || "incertaine"} · confiança {Math.round((ana.scale_confidence || 0) * 100)}%</p>
            )}
            <div className="overflow-auto rounded-sm border border-border">
              <table className="w-full text-xs">
                <thead className="bg-secondary/40"><tr>
                  <th className="text-left p-2">Rede</th><th className="p-2 text-right">Comprimento (ml)</th>
                  <th className="p-2 text-right">Largura (m)</th><th className="p-2 text-right">Profundidade (m)</th><th className="p-2"></th>
                </tr></thead>
                <tbody>
                  {nets.map((n, i) => (
                    <tr key={i} className="border-t border-border/60" data-testid={`vrd-net-${i}`}>
                      <td className="p-1">
                        <select value={n.key} onChange={(e) => setNet(i, "key", e.target.value)} className="h-7 rounded-sm border border-border bg-background px-2 text-xs" data-testid={`vrd-net-key-${i}`}>
                          {catalog.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                        </select>
                      </td>
                      <td className="p-1"><Input type="number" value={n.length_ml} onChange={(e) => setNet(i, "length_ml", e.target.value)} className="h-7 w-24 text-xs text-right" data-testid={`vrd-net-len-${i}`} /></td>
                      <td className="p-1"><Input type="number" value={n.larg_m} onChange={(e) => setNet(i, "larg_m", e.target.value)} className="h-7 w-20 text-xs text-right" /></td>
                      <td className="p-1"><Input type="number" value={n.prof_m} onChange={(e) => setNet(i, "prof_m", e.target.value)} className="h-7 w-20 text-xs text-right" /></td>
                      <td className="p-2 text-center"><button onClick={() => removeNet(i)} data-testid={`vrd-net-del-${i}`}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" /></button></td>
                    </tr>
                  ))}
                  {nets.length === 0 && <tr><td colSpan={5} className="p-3 text-center text-muted-foreground">Nenhuma rede — adicione uma abaixo.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground">Adicionar uma rede</label>
                <select value={addKey} onChange={(e) => setAddKey(e.target.value)} className="mt-1 h-8 rounded-sm border border-border bg-background px-2 text-sm block" data-testid="vrd-add-key">
                  {catalog.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
                </select>
              </div>
              <Button size="sm" variant="outline" onClick={addNet} className="gap-1 rounded-sm" data-testid="vrd-add-net"><Plus className="h-3.5 w-3.5" />Adicionar</Button>
              <div><label className="text-xs text-muted-foreground">Perdas %</label><Input type="number" value={loss} onChange={(e) => setLoss(parseFloat(e.target.value) || 0)} className="h-8 w-20" data-testid="vrd-loss" /></div>
              <Button onClick={compute} className="gap-2 rounded-sm" data-testid="vrd-compute-btn"><Truck className="h-4 w-4" />Recalcular</Button>
            </div>
            {totals && (
              <p className="text-xs text-muted-foreground">Escavação: <b>{totals.deblai_m3} m³</b> · sable {totals.sable_m3} m³ · aterro {totals.remblai_m3} m³ · reparação {totals.refection_m2} m²</p>
            )}
          </div>

          <PlanViewer planId={planId} highlight={highlight} />

          {items.length > 0 && (
            <div data-testid="vrd-bordereau">
              <h3 className="font-bold mb-2">Mapa VRD</h3>
              <ApproOrder items={items} suppliers={suppliers} csvName="bon_commande_vrd.csv"
                createOrder={createOrder} onHighlight={setHighlight} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
