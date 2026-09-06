import { Sparkles, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

export function EstimateDialog({
  open, onOpenChange,
  estProjectType, setEstProjectType,
  estFinishLevel, setEstFinishLevel,
  estimateBusy, estimateResult,
  runEstimation, proceedToDevis,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="rounded-sm max-w-lg" data-testid="estimate-dialog">
        <DialogHeader>
          <DialogTitle>Créer une estimation depuis le plan</DialogTitle>
          <DialogDescription>
            Envoie automatiquement les surfaces mesurées au service Estimateur.
            Vous pourrez ensuite générer un devis client directement depuis ce résultat.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-1">
              <Label className="text-xs">Type de projet</Label>
              <Select value={estProjectType} onValueChange={setEstProjectType}>
                <SelectTrigger data-testid="estimate-project-type" className="rounded-sm h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="renovation_complete">Rénovation complète</SelectItem>
                  <SelectItem value="renovation_partielle">Rénovation partielle</SelectItem>
                  <SelectItem value="renovation_energetique">Rénovation énergétique</SelectItem>
                  <SelectItem value="salle_de_bain">Salle de bain</SelectItem>
                  <SelectItem value="cuisine">Cuisine</SelectItem>
                  <SelectItem value="construction_neuve">Construction neuve</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="grid gap-1">
              <Label className="text-xs">Gamme finition</Label>
              <Select value={estFinishLevel} onValueChange={setEstFinishLevel}>
                <SelectTrigger data-testid="estimate-finish" className="rounded-sm h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="eco">Éco</SelectItem>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="premium">Premium</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {!estimateResult && (
            <Button onClick={runEstimation} disabled={estimateBusy}
                    data-testid="estimate-run-btn"
                    className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Sparkles className="h-4 w-4" />
              {estimateBusy ? "Estimation en cours…" : "Lancer l'estimation"}
            </Button>
          )}
          {estimateResult && (
            <div className="border border-primary/40 bg-primary/5 rounded-sm p-4 space-y-2"
                 data-testid="estimate-result">
              <div className="flex items-center justify-between">
                <p className="overline text-primary">Résultat</p>
                {estimateResult?.is_renovation && (
                  <span className="text-[10px] bg-primary text-white px-2 py-0.5 rounded-sm">
                    Rénovation · TVA 10 %
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-[10px] text-muted-foreground">Surface totale</p>
                  <p className="num font-display text-2xl font-extrabold">
                    {estimateResult?.surface_m2 ?? "—"} <span className="text-sm">m²</span>
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">Lots</p>
                  <p className="num font-display text-2xl font-extrabold">
                    {estimateResult?.estimation?.lots?.length ?? 0}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">Estimation moyenne</p>
                  <p className="num font-display text-xl font-extrabold text-primary">
                    {estimateResult?.estimation?.total_avg?.toLocaleString("pt-PT") ?? "—"} €
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-muted-foreground">€ / m²</p>
                  <p className="num font-display text-xl font-extrabold">
                    {estimateResult?.estimation?.price_per_sqm?.toLocaleString("pt-PT") ?? "—"} €
                  </p>
                </div>
              </div>
              <p className="text-[10px] text-muted-foreground pt-2 border-t border-border">
                Fourchette : {estimateResult?.estimation?.total_min?.toLocaleString("pt-PT") ?? "—"} €
                → {estimateResult?.estimation?.total_max?.toLocaleString("pt-PT") ?? "—"} € · Durée
                estimée : {estimateResult?.estimation?.duration_weeks ?? "—"} semaine(s)
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-sm">
            Fermer
          </Button>
          {estimateResult && (
            <Button onClick={proceedToDevis} data-testid="estimate-to-devis-btn"
                    className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <FileDown className="h-4 w-4" /> Passer à la création du devis
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
