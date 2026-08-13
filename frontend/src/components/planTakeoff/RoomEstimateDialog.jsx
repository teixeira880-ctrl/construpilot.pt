/**
 * RoomEstimateDialog — Devis auto-généré pour une pièce (Vague C QuoterPlan).
 *
 * Affiche les métiers appliqués (peinture, carrelage, plâtrerie, isolation, plinthes)
 * avec pour chacun les résultats + matériaux + budget estimé, et un total en bas.
 * Backend: POST /api/takeoffs/{plan_id}/rooms/{room_id}/estimate
 */
import React from "react";
import { X, Calculator, Palette, Grid3x3, Layers, Package, Ruler } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const TRADE_META = {
  paint:      { icon: Palette,    label: "Peinture",  color: "#eab308" },
  floor_tile: { icon: Grid3x3,    label: "Carrelage", color: "#f97316" },
  drywall:    { icon: Layers,     label: "Plâtrerie", color: "#22c55e" },
  insulation: { icon: Package,    label: "Isolation", color: "#a855f7" },
  plinths:    { icon: Ruler,      label: "Plinthes",  color: "#3b82f6" },
};

export default function RoomEstimateDialog({ open, estimate, planId, onClose, onAddToQuote }) {
  if (!open || !estimate) return null;

  const room = estimate.room || {};
  const trades = estimate.trades || {};

  return (
    <div
      className="fixed inset-0 z-[1000] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      data-testid="room-estimate-dialog-overlay"
      onClick={onClose}
    >
      <div
        className="bg-background border border-border rounded-md shadow-2xl w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col"
        data-testid="room-estimate-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-6 py-4 border-b border-border flex items-center justify-between bg-gradient-to-r from-orange-500/10 to-transparent">
          <div>
            <div className="flex items-center gap-2">
              <Calculator className="h-5 w-5 text-primary" />
              <p className="font-display font-bold">Devis pièce — {room.name || "Pièce"}</p>
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {room.length_m} × {room.width_m} × {room.height_m} m
              · {room.surface_m2?.toFixed?.(1)} m² sol · périmètre {room.perimeter_m?.toFixed?.(1)} m
            </p>
          </div>
          <Button size="icon" variant="ghost" onClick={onClose}
                  data-testid="room-estimate-close" className="h-8 w-8">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {Object.entries(trades).map(([key, r]) => {
            const meta = TRADE_META[key] || { icon: Calculator, label: key, color: "#71717a" };
            const Ic = meta.icon;
            return (
              <div key={key} className="surface p-5" data-testid={`estimate-trade-${key}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Ic className="h-4 w-4" style={{ color: meta.color }} />
                    <p className="font-display font-bold text-sm">{meta.label}</p>
                  </div>
                  <Badge variant="outline" className="text-xs num" style={{ borderColor: meta.color, color: meta.color }}>
                    {(r.estimated_budget ?? 0).toFixed(2)} €
                  </Badge>
                </div>
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <p className="overline text-[10px] mb-2">Résultats</p>
                    <ul className="text-xs space-y-1">
                      {(r.results || []).map((row, i) => (
                        <li key={i} className="flex justify-between border-b border-border/40 py-0.5">
                          <span className="text-muted-foreground truncate">{row.label}</span>
                          <span className="font-medium num shrink-0 ml-2">
                            {row.value} {row.unit}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="overline text-[10px] mb-2">Matériaux</p>
                    <ul className="text-xs space-y-1">
                      {(r.materials || []).map((m, i) => (
                        <li key={i} className="flex justify-between border-b border-border/40 py-0.5">
                          <span className="text-muted-foreground truncate">{m.name}</span>
                          <span className="font-medium num shrink-0 ml-2">
                            {m.quantity} {m.unit}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="px-6 py-4 border-t border-border bg-gradient-to-r from-orange-500/10 to-transparent flex items-center justify-between">
          <div>
            <p className="text-xs text-muted-foreground">Budget total estimé</p>
            <p className="font-display font-bold text-2xl num text-primary" data-testid="room-estimate-total">
              {(estimate.total_budget ?? 0).toFixed(2)} €
            </p>
          </div>
          <div className="flex gap-2">
            {onAddToQuote && (
              <Button
                size="sm"
                onClick={() => onAddToQuote(estimate)}
                data-testid="room-estimate-add-to-quote"
                className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
              >
                <Calculator className="h-4 w-4" /> Ajouter au devis
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={onClose} className="rounded-sm">
              Fermer
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
