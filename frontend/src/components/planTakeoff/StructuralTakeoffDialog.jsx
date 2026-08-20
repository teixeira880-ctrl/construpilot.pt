import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Ruler, Calculator, Loader2 } from "lucide-react";

const FIELDS = [
  ["storey_height_m", "Hauteur d'étage (m)", 2.7, 0.05],
  ["n_levels", "Nombre de niveaux", 1, 1],
  ["wall_thickness_m", "Épaisseur voiles (m)", 0.2, 0.01],
  ["slab_area_m2", "Surface dalle / niveau (m²)", "", 1],
  ["slab_thickness_m", "Épaisseur dalle (m)", 0.2, 0.01],
  ["beam_w_m", "Poutre largeur (m)", 0.2, 0.01],
  ["beam_h_m", "Poutre hauteur (m)", 0.5, 0.01],
  ["col_w_m", "Poteau largeur (m)", 0.2, 0.01],
  ["col_h_m", "Poteau hauteur (m)", 0.2, 0.01],
  ["margin_pct", "Marge (%)", 12, 1],
];

const eur = (n) => (n ?? 0).toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + " €";

export default function StructuralTakeoffDialog({ open, onClose, planId }) {
  const [metre, setMetre] = useState(null);
  const [estimate, setEstimate] = useState(null);
  const [params, setParams] = useState({ storey_height_m: 2.7, n_levels: 1, wall_thickness_m: 0.2,
    slab_area_m2: "", slab_thickness_m: 0.2, beam_w_m: 0.2, beam_h_m: 0.5, col_w_m: 0.2, col_h_m: 0.2, margin_pct: 12 });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open || !planId) return;
    api.get(`/takeoffs/${planId}/structural-metre`).then(({ data }) => {
      setMetre(data.metre); setEstimate(data.estimate || null);
    }).catch(() => toast.error("Métré indisponible"));
  }, [open, planId]);

  const run = async () => {
    setBusy(true);
    try {
      const body = { ...params };
      Object.keys(body).forEach((k) => { body[k] = body[k] === "" ? null : Number(body[k]); });
      const { data } = await api.post(`/takeoffs/${planId}/structural-estimate`, body);
      setEstimate(data);
      toast.success(`Estimation : ${eur(data.totals?.ttc)} TTC`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Estimation impossible"); }
    finally { setBusy(false); }
  };

  const M = metre || {};
  const res = M.reservations || {};
  const op = M.openings || {};
  const t = estimate?.totals;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="structural-takeoff-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Ruler className="h-5 w-5 text-primary" /> Métré structure (DWG/DXF)
          </DialogTitle>
        </DialogHeader>

        {!metre ? (
          <p className="text-sm text-muted-foreground py-6">
            Aucun métré par calques pour ce plan. Importez un DWG/DXF de coffrage avec calques nommés
            (Murs, Poutres, Poteaux, Dalle, réservations…).
          </p>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
              {[["Murs (axe)", `${M.walls_ml} ml`], ["Poutres", `${M.beams_ml} ml`],
                ["Poteaux", M.columns_count], ["Linteaux", `${M.linteaux_ml} ml`],
                ["Portes", op.portes], ["Fenêtres", op.fenetres],
                ["Réservations", res.count], ["Niveaux NGF", (M.ngf_levels || []).length]].map(([k, v]) => (
                <div key={k} className="rounded-sm border p-2" data-testid={`metre-${k}`}>
                  <div className="text-xs text-muted-foreground">{k}</div>
                  <div className="font-semibold">{v}</div>
                </div>
              ))}
            </div>
            {res.by_type && Object.keys(res.by_type).length > 0 && (
              <div className="text-xs text-muted-foreground">
                Réservations par type : {Object.entries(res.by_type).map(([k, v]) => `${k} (${v})`).join(" · ")}
                {(M.ngf_levels || []).length > 0 && <> — NGF : {(M.ngf_levels || []).join(" / ")}</>}
              </div>
            )}

            <div className="border-t pt-4">
              <div className="text-sm font-semibold mb-2">Hypothèses de calcul</div>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {FIELDS.map(([key, label, , step]) => (
                  <div key={key}>
                    <Label className="text-xs">{label}</Label>
                    <Input type="number" step={step} value={params[key]}
                           data-testid={`param-${key}`}
                           onChange={(e) => setParams((p) => ({ ...p, [key]: e.target.value }))} />
                  </div>
                ))}
              </div>
              <Button onClick={run} disabled={busy} className="mt-3 gap-2" data-testid="structural-compute-btn">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
                Calculer l'estimation
              </Button>
            </div>

            {t && (
              <div className="border-t pt-4 space-y-3">
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div className="rounded-sm bg-muted p-2"><div className="text-xs text-muted-foreground">Béton</div><div className="font-semibold">{t.beton_m3} m³</div></div>
                  <div className="rounded-sm bg-muted p-2"><div className="text-xs text-muted-foreground">Aciers</div><div className="font-semibold">{t.acier_kg} kg</div></div>
                  <div className="rounded-sm bg-muted p-2"><div className="text-xs text-muted-foreground">Coffrage</div><div className="font-semibold">{t.coffrage_m2} m²</div></div>
                </div>
                {estimate.lots.map((lot) => (
                  <div key={lot.lot}>
                    <div className="text-sm font-semibold mt-2">{lot.lot}</div>
                    <table className="w-full text-xs mt-1">
                      <tbody>
                        {lot.lines.map((ln, i) => (
                          <tr key={i} className="border-b border-border/50">
                            <td className="py-1 pr-2">{ln.designation}</td>
                            <td className="py-1 text-right whitespace-nowrap text-muted-foreground">{ln.qty} {ln.unit}</td>
                            <td className="py-1 text-right whitespace-nowrap font-medium">{eur(ln.total)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
                <div className="flex justify-end gap-6 text-sm border-t pt-2" data-testid="structural-totals">
                  <span>HT : <b>{eur(t.ht)}</b></span>
                  <span>TVA {Math.round(t.tva_rate * 100)}% : {eur(t.tva)}</span>
                  <span className="text-primary">TTC : <b>{eur(t.ttc)}</b></span>
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
