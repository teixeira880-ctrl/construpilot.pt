import { useState } from "react";
import { Loader2, Sparkles, Truck, Droplets } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import PlanViewer from "@/components/tech/PlanViewer";
import ApproOrder from "@/components/tech/ApproOrder";

export default function WaterproofingTab({ plans, suppliers }) {
  const [planId, setPlanId] = useState("");
  const [busy, setBusy] = useState(false);
  const [ana, setAna] = useState(null);
  const [surface, setSurface] = useState(0);
  const [perimeter, setPerimeter] = useState(0);
  const [releve, setReleve] = useState(0.5);
  const [system, setSystem] = useState("bicouche");
  const [recouv, setRecouv] = useState(10);
  const [loss, setLoss] = useState(5);
  const [cmd, setCmd] = useState(null);
  const [highlight, setHighlight] = useState(null);

  const analyze = async () => {
    if (!planId) return toast.error("Choisissez un plan");
    setBusy(true); setCmd(null);
    try {
      const { data } = await api.post(`/pro/waterproofing/${planId}/analyze`);
      setAna(data);
      setSurface(data.surface_m2 || 0);
      setPerimeter(data.perimeter_m || 0);
      setReleve(data.releve_h_m || 0.5);
      setSystem(data.system_type || "bicouche");
      setHighlight(null);
      toast.success("Étanchéité analysée");
    } catch (e) { toast.error(e?.response?.data?.detail || "Analyse impossible"); }
    finally { setBusy(false); }
  };

  const compute = async () => {
    try {
      const { data } = await api.post(`/pro/waterproofing/${planId}/recompute`,
        { surface_m2: surface, perimeter_m: perimeter, releve_h_m: releve,
          system_type: system, recouvrement_pct: recouv, loss_pct: loss });
      setCmd(data);
      toast.success("Bordereau recalculé");
    } catch (e) { toast.error(e?.response?.data?.detail || "Calcul impossible"); }
  };

  const createOrder = async (supplierId) => {
    const { data } = await api.post(`/pro/waterproofing/${planId}/order`, { supplier_id: supplierId || null });
    return data;
  };

  const items = cmd?.compute?.items || ana?.compute?.items || [];

  return (
    <div className="space-y-5" data-testid="waterproofing-tab">
      <div className="surface p-4 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[220px]">
          <label className="text-xs text-muted-foreground">Plan d'étanchéité à analyser</label>
          <select value={planId} onChange={(e) => setPlanId(e.target.value)} data-testid="wp-plan-select"
            className="w-full mt-1 rounded-sm border border-border bg-background px-3 py-2 text-sm">
            <option value="">— Choisir un plan —</option>
            {plans.map((p) => <option key={p.plan_id} value={p.plan_id}>{p.filename || p.plan_id}</option>)}
          </select>
        </div>
        <Button onClick={analyze} disabled={busy || !planId} className="gap-2 rounded-sm" data-testid="analyze-wp-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {busy ? "Analyse IA…" : "Analyser l'étanchéité"}
        </Button>
      </div>

      {ana && (
        <>
          <div className="surface p-4 space-y-3" data-testid="wp-params">
            <h3 className="font-bold flex items-center gap-2"><Droplets className="h-4 w-4 text-primary" />Paramètres du complexe</h3>
            {ana.scale_confidence != null && (
              <p className="text-xs text-muted-foreground">Échelle : {ana.scale_detected || "incertaine"} · confiance {Math.round((ana.scale_confidence || 0) * 100)}%</p>
            )}
            <div className="flex flex-wrap items-end gap-3">
              <div><label className="text-xs text-muted-foreground">Surface (m²)</label><Input type="number" value={surface} onChange={(e) => setSurface(parseFloat(e.target.value) || 0)} className="h-8 w-28" data-testid="wp-surface" /></div>
              <div><label className="text-xs text-muted-foreground">Perímetro (m)</label><Input type="number" value={perimeter} onChange={(e) => setPerimeter(parseFloat(e.target.value) || 0)} className="h-8 w-28" data-testid="wp-perimeter" /></div>
              <div><label className="text-xs text-muted-foreground">Hauteur relevé (m)</label><Input type="number" value={releve} onChange={(e) => setReleve(parseFloat(e.target.value) || 0)} className="h-8 w-28" data-testid="wp-releve" /></div>
              <div><label className="text-xs text-muted-foreground">Système</label>
                <select value={system} onChange={(e) => setSystem(e.target.value)} className="mt-1 h-8 rounded-sm border border-border bg-background px-2 text-sm" data-testid="wp-system">
                  <option value="bicouche">Bicouche</option><option value="monocouche">Monocouche</option>
                </select>
              </div>
              <div><label className="text-xs text-muted-foreground">Recouvrement %</label><Input type="number" value={recouv} onChange={(e) => setRecouv(parseFloat(e.target.value) || 0)} className="h-8 w-24" data-testid="wp-recouv" /></div>
              <div><label className="text-xs text-muted-foreground">Pertes %</label><Input type="number" value={loss} onChange={(e) => setLoss(parseFloat(e.target.value) || 0)} className="h-8 w-24" data-testid="wp-loss" /></div>
              <Button onClick={compute} className="gap-2 rounded-sm" data-testid="wp-compute-btn"><Truck className="h-4 w-4" />Recalculer</Button>
            </div>
            {cmd?.compute && (
              <p className="text-xs text-muted-foreground">Membrane : <b>{cmd.compute.membrane_area_m2} m²</b> · relevés {cmd.compute.releve_area_m2} m² · {cmd.compute.system_type}</p>
            )}
          </div>

          <PlanViewer planId={planId} highlight={highlight} />

          {items.length > 0 && (
            <div data-testid="wp-bordereau">
              <h3 className="font-bold mb-2">Bordereau étanchéité par couche</h3>
              <ApproOrder items={items} suppliers={suppliers} csvName="bon_commande_etancheite.csv"
                createOrder={createOrder} onHighlight={setHighlight} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
