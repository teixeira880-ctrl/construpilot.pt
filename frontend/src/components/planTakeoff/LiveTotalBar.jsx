/**
 * LiveTotalBar — Compact floating bar "Coût total plan" (Iter 60 + 61).
 *
 * - Somme le budget de chaque pièce estimée via /api/takeoffs/{id}/rooms/{room_id}/estimate.
 * - Se contracte en pill au scroll pour ne pas cacher le plan (Iter 61).
 * - Chip "Voir vainqueur prix" collecte tous les matériaux et navigue vers /prix
 *   pré-filtré (Iter 61).
 */
import React, { useState, useCallback, useEffect, useRef } from "react";
import { Calculator, RefreshCw, ArrowUp, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api, eur } from "@/lib/api";

export function LiveTotalBar({ planId, rooms, onOpenEstimate }) {
  const [totals, setTotals] = useState({}); // { room_id: total_budget }
  const [materialsByRoom, setMaterialsByRoom] = useState({}); // { room_id: [material] }
  const [computing, setComputing] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const scrollTargetRef = useRef(null);

  // Iter 61 — collapse en pill quand l'utilisateur scrolle activement le canvas
  useEffect(() => {
    const target = document.querySelector("[data-testid='plan-canvas']")?.parentElement
                   || window;
    let lastScroll = 0;
    let hideTimer = null;
    const onScroll = () => {
      const now = Date.now();
      if (now - lastScroll < 150) return; // throttle
      lastScroll = now;
      setCollapsed(true);
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => setCollapsed(false), 2000);
    };
    target.addEventListener("scroll", onScroll, { passive: true });
    scrollTargetRef.current = target;
    return () => {
      target.removeEventListener("scroll", onScroll);
      clearTimeout(hideTimer);
    };
  }, [planId]);

  const computeAll = useCallback(async () => {
    if (!planId || !rooms?.length) return;
    setComputing(true);
    const totalsMap = {};
    const materialsMap = {};
    try {
      await Promise.all(
        rooms.map(async (r) => {
          try {
            const { data } = await api.post(
              `/takeoffs/${planId}/rooms/${r.room_id}/estimate`, {}
            );
            totalsMap[r.room_id] = data.total_budget || 0;
            // Agrège les matériaux tous métiers pour /prix
            const mats = [];
            Object.values(data.trades || {}).forEach((t) => {
              (t.materials || []).forEach((m) => mats.push(m));
            });
            materialsMap[r.room_id] = mats;
          } catch { /* skip room */ }
        })
      );
      setTotals(totalsMap);
      setMaterialsByRoom(materialsMap);
      const total = Object.values(totalsMap).reduce((a, b) => a + b, 0);
      toast.success(`Coût total : ${eur(total)} (${Object.keys(totalsMap).length} pièces)`);
    } finally {
      setComputing(false);
    }
  }, [planId, rooms]);

  // Reset totals when plan changes
  useEffect(() => {
    setTotals({});
    setMaterialsByRoom({});
  }, [planId]);

  const total = Object.values(totals).reduce((a, b) => a + b, 0);
  const nEstimated = Object.keys(totals).length;
  const hasEstimates = nEstimated > 0;

  const compareBestPrices = () => {
    // Agrège tous les matériaux et navigue vers /prix pré-loadé
    const allMaterials = [];
    Object.values(materialsByRoom).forEach((list) => list.forEach((m) => allMaterials.push(m)));
    if (allMaterials.length === 0) return toast.error("Estime pelo menos uma divisão primeiro");
    sessionStorage.setItem("construpilot_price_search_batch", JSON.stringify({
      items: allMaterials,
      source: "plan_total",
      project_name: `Plan complet — ${nEstimated} pièces`,
      total_avg: total,
      ts: Date.now(),
    }));
    toast.success(`A pesquisar preços para ${allMaterials.length} materiais…`);
    window.location.href = "/prix?from=plan-total";
  };

  if (!rooms || rooms.length === 0) return null;

  // Mode pill collapsed (scroll active)
  if (collapsed && hasEstimates) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        data-testid="live-total-bar-pill"
        className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-primary text-white rounded-full shadow-lg px-4 py-1.5 flex items-center gap-2 text-xs font-medium hover:bg-orange-600 transition"
      >
        <Calculator className="h-3.5 w-3.5" />
        <span className="num" data-testid="live-total-pill-value">{eur(total)}</span>
      </button>
    );
  }

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
              : "Estime todas as divisões"}
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
          title="Recalcular todas as divisões"
        >
          {computing ? (
            <RefreshCw className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
          {computing ? "Calcul…" : hasEstimates ? "Actualiser" : "Calculer"}
        </Button>
        {hasEstimates && (
          <Button
            size="sm"
            variant="ghost"
            onClick={compareBestPrices}
            data-testid="live-total-compare-prices"
            className="h-7 gap-1 rounded-full text-xs text-primary hover:bg-primary/10"
            title="Ver os melhores preços nos fornecedores"
          >
            <Trophy className="h-3 w-3" /> Voir vainqueur prix
          </Button>
        )}
        {hasEstimates && onOpenEstimate && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              const biggest = Object.entries(totals).sort((a, b) => b[1] - a[1])[0];
              if (biggest) onOpenEstimate(biggest[0]);
            }}
            data-testid="live-total-open-biggest"
            className="h-7 gap-1 rounded-full text-xs"
            title="Ver a divisão mais cara"
          >
            <ArrowUp className="h-3 w-3" /> Détails
          </Button>
        )}
      </div>
    </div>
  );
}
