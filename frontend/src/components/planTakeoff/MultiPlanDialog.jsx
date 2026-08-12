import { FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";

export function MultiPlanDialog({
  open, onOpenChange,
  multiProjectName, setMultiProjectName,
  multiSelected, setMultiSelected,
  allPlans, plan,
  quoteFinish, quoteFloor,
  multiBusy, downloadMultiQuote,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-lg" data-testid="multi-quote-dialog">
        <DialogHeader>
          <DialogTitle>Devis projet multi-plans</DialogTitle>
          <DialogDescription>
            Combinez plusieurs plans (RDC, étages, extensions…) en un seul devis projet.
            Les surfaces et prix sont additionnés automatiquement.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1">
            <Label className="text-xs">Nom du projet (optionnel)</Label>
            <Input value={multiProjectName} onChange={(e) => setMultiProjectName(e.target.value)}
                   placeholder="Ex : Maison Dupont — rénovation complète"
                   maxLength={120}
                   data-testid="multi-project-name" className="rounded-sm h-10" />
          </div>
          <div>
            <p className="overline mb-2">Plans à inclure ({multiSelected.length} sélectionné{multiSelected.length > 1 ? "s" : ""})</p>
            <div className="grid gap-1 max-h-60 overflow-y-auto border border-border rounded-sm p-2"
                 data-testid="multi-plans-list">
              {allPlans.length === 0 ? (
                <p className="text-xs text-muted-foreground text-center py-4">
                  Aucun plan disponible. Uploadez au moins 2 plans depuis la page /plan.
                </p>
              ) : allPlans.map(p => {
                const on = multiSelected.includes(p.plan_id);
                return (
                  <label key={p.plan_id}
                         className={`flex items-center gap-2 p-2 rounded-sm cursor-pointer border ${on ? "border-primary bg-primary/5" : "border-transparent hover:bg-secondary/40"}`}
                         data-testid={`multi-plan-item-${p.plan_id}`}>
                    <input type="checkbox" checked={on}
                           onChange={(e) => {
                             setMultiSelected(prev =>
                               e.target.checked ? [...prev, p.plan_id]
                                                : prev.filter(id => id !== p.plan_id));
                           }}
                           data-testid={`multi-plan-checkbox-${p.plan_id}`}
                           className="accent-primary h-4 w-4" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold truncate">{p.filename || p.plan_id}</p>
                      <p className="text-[10px] text-muted-foreground num">
                        {p.rooms?.length || 0} pièces · {(p.rooms?.reduce((s, r) => s + (r.surface_m2 || 0), 0) || 0).toFixed(1)} m²
                        {p.plan_id === plan?.plan_id && (
                          <span className="text-primary ml-1">(en cours)</span>
                        )}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          </div>
          <p className="text-[10px] text-muted-foreground border border-border p-2 rounded-sm bg-secondary/30">
            Gamme & sol utilisés : <b>{quoteFinish}</b> · <b>{quoteFloor}</b>. Modifiez-les
            dans le dialog Devis principal si besoin.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Annuler
          </Button>
          <Button onClick={downloadMultiQuote} disabled={multiBusy || multiSelected.length === 0}
                  data-testid="multi-quote-download-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <FileDown className="h-4 w-4" />
            {multiBusy ? "Génération…" : `Télécharger (${multiSelected.length})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
