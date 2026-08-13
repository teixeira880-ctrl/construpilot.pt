/**
 * LiveTotalBar — Compact floating bar "Coût total plan" (Iter 60).
 *
 * Somme le budget de chaque pièce estimée via /api/takeoffs/{id}/rooms/{room_id}/estimate.
 * S'affiche en bas centre du canvas, cliquable pour re-estimer toutes les pièces d'un coup.
 */
import React, { useState, useCallback, useEffect } from "react";
import { Calculator, RefreshCw, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api, eur } from "@/lib/api";

export function LiveTotalBar({ planId, rooms, onOpenEstimate }) {
  const [totals, setTotals] = useState({}); // { room_id: total_budget }
  const [computing, setComputing] = useState(false);

  const computeAll = useCallback(async () => {
    if (!planId || !rooms?.length) return;
    setComputing(true);
    const map = {};
    try {
      await Promise.all(
        rooms.map(async (r) => {
          try {
            const { data } = await api.post(
              `/takeoffs/${planId}/rooms/${r.room_id}/estimate`, {}
            );
            map[r.room_id] = data.total_budget || 0;
          } catch { /* skip room */ }
        })
      );
      setTotals(map);
      const total = Object.values(map).reduce((a, b) => a + b, 0);
      toast.success(`Coût total : ${eur(total)} (${Object.keys(map).length} pièces)`);
    } finally {
      setComputing(false);
    }
  }, [planId, rooms]);

  // Reset totals when plan changes
  useEffect(() => {
    setTotals({});
  }, [planId]);

  const total = Object.values(totals).reduce((a, b) => a + b, 0);
  const nEstimated = Object.keys(totals).length;
  const hasEstimates = nEstimated > 0;

  if (!rooms || rooms.length === 0) return null;

  return (
    <div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40"
      data-testid="live-total-bar"
    >
      <div className="bg-background border border-border rounded-full shadow-xl px-4 py-2 flex items-center gap-3">
        <Calculator className="h-4 w-4 text-primary" />
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {hasEstimates
              ? `Coût total plan (${nEstimated}/${rooms.length} pièces)`
              : "Estimez toutes les pièces"}
          </span>
          {hasEstimates && (
            <span className="font-display font-bold text-sm num" data-testid="live-total-value">
              {eur(total)}
            </span>
          )}
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={computeAll}
          disabled={computing}
          data-testid="live-total-compute-btn"
          className="h-7 gap-1.5 rounded-full text-xs"
          title="Recalculer toutes les pièces"
        >
          {computing ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          {computing ? "Calcul…" : hasEstimates ? "Actualiser" : "Calculer"}
        </Button>
        {hasEstimates && onOpenEstimate && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              // Ouvre l'estimation de la pièce ayant le plus gros budget
              const biggest = Object.entries(totals).sort((a, b) => b[1] - a[1])[0];
              if (biggest) onOpenEstimate(biggest[0]);
            }}
            data-testid="live-total-open-biggest"
            className="h-7 gap-1 rounded-full text-xs"
            title="Voir la pièce la plus coûteuse"
          >
            <ArrowUp className="h-3 w-3" /> Détails
          </Button>
        )}
      </div>
    </div>
  );
}
