import { useEffect, useState } from "react";
import { Loader2, Sparkles, Truck, Home } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import PlanViewer from "@/components/tech/PlanViewer";
import ApproOrder from "@/components/tech/ApproOrder";

export default function RoofingTab({ plans, suppliers }) {
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ana, setAna] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [material, setMaterial] = useState("tuiles_terre_cuite");
  const [surface, setSurface] = useState(0);
  const [pente, setPente] = useState(35);
  const [lg, setLg] = useState({ faitage_ml: 0, aretiers_ml: 0, noues_ml: 0, rives_ml: 0, egout_ml: 0 });
  const [loss, setLoss] = useState(8);
  const [cmd, setCmd] = useState(null);
  const [highlight, setHighlight] = useState(null);

  useEffect(() => {
    api.get("/pro/roofing/materials").then(({ data }) => setMaterials(data.items || [])).catch(() => {});
  }, []);

  const analyze = async () => {
    if (!planId) return toast.error("Choisissez un plan");
    setBusy(true); setCmd(null);
    try {
      const { data } = await api.post(`/pro/roofing/${planId}/analyze?material=${material}`);
      setAna(data);
      setHighlight(null);
      setSurface(data.surface_projetee_m2 || 0);
      setPente(data.pente_pct || 35);
      setLg({
        faitage_ml: data.lengths?.faitage_ml || 0, aretiers_ml: data.lengths?.aretiers_ml || 0,
        noues_ml: data.lengths?.noues_ml || 0, rives_ml: data.lengths?.rives_ml || 0,
        egout_ml: data.lengths?.egout_ml || 0,
      });
      toast.success("Toiture analysée");
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse impossible"); }
    finally { setBusy(false); }
  };

  const compute = async () => {
    try {
      const { data } = await api.post(`/pro/roofing/${planId}/recompute`,
        { surface_projetee_m2: surface, pente_pct: pente, material, loss_pct: loss, ...lg });
      setCmd(data);
      toast.success("Bordereau recalculé");
    } catch (e) { toast.error(e?.response?.data?.detail || "Calcul impossible"); }
  };

  const createOrder = async (supplierId) => {
    const { data } = await api.post(`/pro/roofing/${planId}/order`, { supplier_id: supplierId || null });
    return data;
  };

  const setL = (k, v) => setLg({ ...lg, [k]: parseFloat(v) || 0 });
  const items = cmd?.compute?.items || ana?.compute?.items || [];
  const comp = cmd?.compute || ana?.compute;

  return (
    <div className="space-y-5" data-testid="roofing-tab">
      <div className="surface p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-muted-foreground">Plan de toiture à analyser</label>
          <select value={planId} onChange={(e) => setPlanId(e.target.value)} data-testid="roof-plan-select"
            className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm">
            <option value="">— Choisir un plan —</option>
            {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
          </select>
        </div>
        <div className="min-w-[180px]"><label className="text-xs text-muted-foreground">Couverture</label>
          <select value={material} onChange={(e) => setMaterial(e.target.value)} className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm" data-testid="roof-material-select">
            {materials.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
          </select>
        </div>
        <Button onClick={analyze} disabled={busy || !planId} className="gap-2 rounded-sm" data-testid="analyze-roof-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "Analyse IA…" : "Analyser la toiture"}
        </Button>
      </div>

      {ana && (
        <>
          <div className="surface p-4 space-y-3" data-testid="roof-params">
            <h3 className="font-bold flex items-center gap-2"><Home className="h-4 w-4 text-primary" />Paramètres toiture {ana.roof_type ? `· ${ana.roof_type}` : ""}</h3>
            {ana.scale_confidence != null && (
              <p className="text-xs text-muted-foreground">Échelle : {ana.scale_detected || "incertaine"} · confiance {Math.round((ana.scale_confidence || 0) * 100)}%</p>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground">Surface projetée (m²)</label><Input type="number" value={surface} onChange={(e) => setSurface(parseFloat(e.target.value) || 0)} className="h-8 w-32" data-testid="roof-surface" /></div>
              <div><label className="text-xs text-muted-foreground">Pente (%)</label><Input type="number" value={pente} onChange={(e) => setPente(parseFloat(e.target.value) || 0)} className="h-8 w-24" data-testid="roof-pente" /></div>
              <div><label className="text-xs text-muted-foreground">Faîtage (ml)</label><Input type="number" value={lg.faitage_ml} onChange={(e) => setL("faitage_ml", e.target.value)} className="h-8 w-24" data-testid="roof-faitage" /></div>
              <div><label className="text-xs text-muted-foreground">Arêtiers (ml)</label><Input type="number" value={lg.aretiers_ml} onChange={(e) => setL("aretiers_ml", e.target.value)} className="h-8 w-24" data-testid="roof-aretiers" /></div>
              <div><label className="text-xs text-muted-foreground">Noues (ml)</label><Input type="number" value={lg.noues_ml} onChange={(e) => setL("noues_ml", e.target.value)} className="h-8 w-24" data-testid="roof-noues" /></div>
              <div><label className="text-xs text-muted-foreground">Rives (ml)</label><Input type="number" value={lg.rives_ml} onChange={(e) => setL("rives_ml", e.target.value)} className="h-8 w-24" data-testid="roof-rives" /></div>
              <div><label className="text-xs text-muted-foreground">Égout (ml)</label><Input type="number" value={lg.egout_ml} onChange={(e) => setL("egout_ml", e.target.value)} className="h-8 w-24" data-testid="roof-egout" /></div>
              <div><label className="text-xs text-muted-foreground">Pertes %</label><Input type="number" value={loss} onChange={(e) => setLoss(parseFloat(e.target.value) || 0)} className="h-8 w-20" data-testid="roof-loss" /></div>
              <Button onClick={compute} className="gap-2 rounded-sm" data-testid="roof-compute-btn"><Truck className="h-4 w-4" />Recalculer</Button>
            </div>
            {comp && (
              <p className="text-xs text-muted-foreground">Surface rampante : <b>{comp.surface_rampante_m2} m²</b> · angle {comp.angle_deg}° · {comp.material_label}</p>
            )}
          </div>

          <PlanViewer planId={planId} highlight={highlight} />

          {items.length > 0 && (
            <div data-testid="roof-bordereau">
              <h3 className="font-bold mb-2">Bordereau toiture</h3>
              <ApproOrder items={items} suppliers={suppliers} csvName="bon_commande_toiture.csv"
                createOrder={createOrder} onHighlight={setHighlight} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
