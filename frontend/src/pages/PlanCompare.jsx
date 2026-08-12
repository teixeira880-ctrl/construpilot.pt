import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  GitCompareArrows, TrendingUp, TrendingDown, Plus, Minus, Edit3, ArrowLeft,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useNavigate } from "react-router-dom";
import { api, num } from "@/lib/api";

/** Page de comparaison de deux plans (existant / projet).
 *  Route: /plan/compare */
export default function PlanCompare() {
  const nav = useNavigate();
  const [plans, setPlans] = useState([]);
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/takeoffs").then(({ data }) => setPlans(data.plans || []));
  }, []);

  const runCompare = async () => {
    if (!beforeId || !afterId) return toast.error("Sélectionnez les 2 plans");
    setBusy(true);
    try {
      const { data } = await api.post("/takeoffs/compare",
        { before_plan_id: beforeId, after_plan_id: afterId });
      setResult(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Comparaison impossible");
    } finally { setBusy(false); }
  };

  return (
    <div className="mx-auto max-w-[1200px] px-5 py-8 grid gap-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <p className="overline text-primary">ConstruPilot PLAN — Comparateur</p>
          <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Comparez le plan existant et le projet
          </h1>
          <p className="text-sm text-muted-foreground mt-2 max-w-xl">
            Sélectionnez deux plans : ConstruPilot identifie automatiquement les pièces
            ajoutées, supprimées ou modifiées, avec le delta de surface.
          </p>
        </div>
        <Button variant="outline" onClick={() => nav("/plan")} data-testid="compare-back"
                className="rounded-sm gap-2">
          <ArrowLeft className="h-4 w-4" /> Retour au takeoff
        </Button>
      </div>

      <div className="grid md:grid-cols-[1fr_auto_1fr_auto] gap-4 items-end surface p-6">
        <div className="grid gap-2">
          <Label>Plan existant (avant)</Label>
          <Select value={beforeId} onValueChange={setBeforeId}>
            <SelectTrigger className="rounded-sm h-11" data-testid="compare-before-select">
              <SelectValue placeholder="Choisir un plan…" />
            </SelectTrigger>
            <SelectContent>
              {plans.map(p => (
                <SelectItem key={p.plan_id} value={p.plan_id}>
                  {p.filename} — {p.rooms?.length || 0} pièces
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <GitCompareArrows className="h-6 w-6 text-primary mx-auto mb-3" />
        <div className="grid gap-2">
          <Label>Plan projet (après)</Label>
          <Select value={afterId} onValueChange={setAfterId}>
            <SelectTrigger className="rounded-sm h-11" data-testid="compare-after-select">
              <SelectValue placeholder="Choisir un plan…" />
            </SelectTrigger>
            <SelectContent>
              {plans.map(p => (
                <SelectItem key={p.plan_id} value={p.plan_id}>
                  {p.filename} — {p.rooms?.length || 0} pièces
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={runCompare} disabled={busy || !beforeId || !afterId}
                data-testid="compare-run-btn"
                className="rounded-sm gap-2 h-11 hover:bg-orange-600 hover:text-white">
          <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Comparer
        </Button>
      </div>

      {result && (
        <div className="grid gap-6" data-testid="compare-result">
          {/* Résumé */}
          <div className="grid sm:grid-cols-4 gap-4">
            <div className="surface p-5">
              <p className="overline">Avant</p>
              <p className="num mt-2 text-2xl font-bold">{result.before.total_surface_m2} m²</p>
              <p className="num text-xs text-muted-foreground">{result.before.room_count} pièces</p>
            </div>
            <div className="surface p-5">
              <p className="overline">Après</p>
              <p className="num mt-2 text-2xl font-bold">{result.after.total_surface_m2} m²</p>
              <p className="num text-xs text-muted-foreground">{result.after.room_count} pièces</p>
            </div>
            <div className={`surface p-5 border-primary`}>
              <p className="overline">Delta surface</p>
              <p className={`num mt-2 text-2xl font-bold ${result.delta_surface_m2 >= 0 ? "text-emerald-500" : "text-destructive"}`}>
                {result.delta_surface_m2 >= 0 ? "+" : ""}{result.delta_surface_m2} m²
              </p>
              <p className="num text-xs text-muted-foreground">
                {result.delta_surface_pct >= 0 ? "+" : ""}{result.delta_surface_pct} %
              </p>
            </div>
            <div className="surface p-5">
              <p className="overline">Impact</p>
              <div className="flex flex-wrap gap-1 mt-2">
                <Badge variant="outline" className="rounded-sm gap-1 text-emerald-500">
                  <Plus className="h-3 w-3" /> {result.added.length}
                </Badge>
                <Badge variant="outline" className="rounded-sm gap-1 text-destructive">
                  <Minus className="h-3 w-3" /> {result.removed.length}
                </Badge>
                <Badge variant="outline" className="rounded-sm gap-1 text-amber-500">
                  <Edit3 className="h-3 w-3" /> {result.modified.length}
                </Badge>
              </div>
            </div>
          </div>

          {/* Détails */}
          <div className="grid lg:grid-cols-3 gap-4">
            <CategoryPanel title="Pièces ajoutées" icon={Plus} tone="emerald"
                          items={result.added} type="added" testId="compare-added" />
            <CategoryPanel title="Pièces supprimées" icon={Minus} tone="rose"
                          items={result.removed} type="removed" testId="compare-removed" />
            <CategoryPanel title="Pièces modifiées" icon={Edit3} tone="amber"
                          items={result.modified} type="modified" testId="compare-modified" />
          </div>

          {result.unchanged.length > 0 && (
            <details className="surface p-5" data-testid="compare-unchanged">
              <summary className="cursor-pointer text-sm font-medium">
                {result.unchanged.length} pièce{result.unchanged.length > 1 ? "s" : ""} inchangée{result.unchanged.length > 1 ? "s" : ""}
                <span className="text-muted-foreground text-xs"> (tolérance {result.surface_tolerance_pct}%)</span>
              </summary>
              <div className="mt-3 grid gap-1 text-xs num">
                {result.unchanged.map((r, i) => (
                  <div key={i} className="flex justify-between border-b border-border pb-1">
                    <span>{r.name}</span>
                    <span>{r.surface_after_m2} m²</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function CategoryPanel({ title, icon: Icon, tone, items, type, testId }) {
  const toneMap = {
    emerald: "border-emerald-500/50", rose: "border-rose-500/50", amber: "border-amber-500/50",
  };
  const iconTone = {
    emerald: "text-emerald-500", rose: "text-destructive", amber: "text-amber-500",
  };
  return (
    <div className={`surface p-5 ${toneMap[tone]}`} data-testid={testId}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className={`h-4 w-4 ${iconTone[tone]}`} />
        <p className="font-display font-bold">{title}</p>
        <Badge variant="outline" className="ml-auto rounded-sm num">{items.length}</Badge>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">Aucune</p>
      ) : (
        <div className="grid gap-2 text-xs">
          {items.map((r, i) => (
            <div key={i} className="border-b border-border pb-2">
              <p className="font-bold">{r.name}</p>
              {type === "modified" ? (
                <div className="num text-muted-foreground">
                  <span>{r.surface_before_m2} m² → {r.surface_after_m2} m² </span>
                  <span className={r.delta_m2 >= 0 ? "text-emerald-500" : "text-destructive"}>
                    ({r.delta_m2 >= 0 ? "+" : ""}{r.delta_m2} m² · {r.delta_pct}%)
                  </span>
                </div>
              ) : (
                <p className="num text-muted-foreground">
                  {r.surface_m2} m² · périmètre {r.perimeter_m} m
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
