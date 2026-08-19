import { useEffect, useRef, useState } from "react";
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
  const [beforeRooms, setBeforeRooms] = useState([]);
  const [afterRooms, setAfterRooms] = useState([]);
  const [afterImage, setAfterImage] = useState(null);
  const [afterMime, setAfterMime] = useState("image/png");
  const [showAdded, setShowAdded] = useState(true);
  const [showRemoved, setShowRemoved] = useState(true);
  const [showModified, setShowModified] = useState(true);
  const [hideUnchanged, setHideUnchanged] = useState(false);
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const [showAddedWalls, setShowAddedWalls] = useState(true);
  const [showRemovedWalls, setShowRemovedWalls] = useState(true);

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
      // Charge les rooms des 2 plans et l'image du after (page 0) pour overlay
      const [{ data: beforePlan }, { data: afterPlan }, { data: afterPage }] =
        await Promise.all([
          api.get(`/takeoffs/${beforeId}`),
          api.get(`/takeoffs/${afterId}`),
          api.get(`/takeoffs/${afterId}/page/0`),
        ]);
      setBeforeRooms((beforePlan.rooms || []).filter(r => r.page_index === 0));
      setAfterRooms((afterPlan.rooms || []).filter(r => r.page_index === 0));
      setAfterImage(afterPage.image_png_b64);
      setAfterMime(afterPage.img_mime || "image/png");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Comparaison impossible");
    } finally { setBusy(false); }
  };

  // Rendu du canvas overlay
  useEffect(() => {
    const c = canvasRef.current;
    if (!c || !afterImage) return;
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      const maxW = 1000;
      const scale = img.width > maxW ? maxW / img.width : 1;
      c.width = img.width * scale;
      c.height = img.height * scale;
      const ctx = c.getContext("2d");
      ctx.clearRect(0, 0, c.width, c.height);
      ctx.save();
      ctx.scale(scale, scale);
      ctx.globalAlpha = 0.6;
      ctx.drawImage(img, 0, 0);
      ctx.globalAlpha = 1;

      const drawRoom = (r, fill, stroke, label) => {
        if (!r.points || r.points.length < 3) return;
        ctx.beginPath();
        r.points.forEach((p, i) =>
          i === 0 ? ctx.moveTo(p[0], p[1]) : ctx.lineTo(p[0], p[1]));
        ctx.closePath();
        ctx.fillStyle = fill;
        ctx.fill();
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 3 / scale;
        ctx.stroke();
        const cx = r.points.reduce((s, p) => s + p[0], 0) / r.points.length;
        const cy = r.points.reduce((s, p) => s + p[1], 0) / r.points.length;
        ctx.font = `bold ${14 / scale}px system-ui`;
        ctx.fillStyle = stroke;
        ctx.textAlign = "center";
        ctx.fillText(`${label} · ${r.name}`, cx, cy);
        ctx.font = `${11 / scale}px system-ui`;
        ctx.fillStyle = "#111";
        ctx.fillText(`${r.surface_m2} m²`, cx, cy + 14 / scale);
      };

      const _n = (s) => (s || "").trim().toLowerCase();
      const afterNames = new Set(afterRooms.map(r => _n(r.name)));
      const beforeNames = new Set(beforeRooms.map(r => _n(r.name)));

      // Rouge : rooms de BEFORE qui n'existent plus dans AFTER
      if (showRemoved) {
        beforeRooms.forEach(r => {
          if (!afterNames.has(_n(r.name))) {
            drawRoom(r, "rgba(239,68,68,0.28)", "rgba(220,38,38,0.9)", "SUPPR.");
          }
        });
      }
      // Vert : rooms de AFTER qui n'étaient pas dans BEFORE
      if (showAdded) {
        afterRooms.forEach(r => {
          if (!beforeNames.has(_n(r.name))) {
            drawRoom(r, "rgba(34,197,94,0.28)", "rgba(22,163,74,0.9)", "AJOUT");
          }
        });
      }
      // Ambre : rooms modifiées
      if (showModified) {
        (result?.modified || []).forEach(mod => {
          const ra = afterRooms.find(r => _n(r.name) === _n(mod.name));
          if (ra) drawRoom(ra, "rgba(251,191,36,0.25)", "rgba(217,119,6,0.9)",
                          `MOD (${mod.delta_m2 >= 0 ? "+" : ""}${mod.delta_m2} m²)`);
        });
      }

      // ============ WALL SEGMENTS DIFF (Compare Vecteurs) ============
      const drawSeg = (s, color) => {
        ctx.beginPath();
        ctx.moveTo(s.x1, s.y1);
        ctx.lineTo(s.x2, s.y2);
        ctx.strokeStyle = color;
        ctx.lineWidth = 4 / scale;
        ctx.lineCap = "round";
        ctx.stroke();
      };
      const walls = result?.walls;
      if (walls) {
        if (showAddedWalls) {
          (walls.added || []).filter(w => w.page === 0).forEach(w => {
            drawSeg(w, "rgba(34,197,94,0.95)");
          });
        }
        if (showRemovedWalls) {
          (walls.removed || []).filter(w => w.page === 0).forEach(w => {
            drawSeg(w, "rgba(220,38,38,0.85)");
          });
        }
      }

      ctx.restore();
    };
    img.src = `data:${afterMime};base64,${afterImage}`;
  }, [afterImage, beforeRooms, afterRooms, result, showAdded, showRemoved, showModified,
      showAddedWalls, showRemovedWalls]);

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
          {/* Overlay visuel */}
          {afterImage && (
            <div className="surface p-4" data-testid="compare-overlay">
              <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
                <p className="overline">Superposition visuelle</p>
                <div className="flex gap-3 text-xs items-center flex-wrap">
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" checked={showAdded} onChange={(e) => setShowAdded(e.target.checked)}
                           data-testid="compare-filter-added" className="accent-emerald-500 h-4 w-4" />
                    <Badge variant="outline" className="rounded-sm gap-1 border-emerald-500/50 text-emerald-500">
                      <Plus className="h-3 w-3" /> Ajouté ({result.added.length})
                    </Badge>
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" checked={showRemoved} onChange={(e) => setShowRemoved(e.target.checked)}
                           data-testid="compare-filter-removed" className="accent-red-500 h-4 w-4" />
                    <Badge variant="outline" className="rounded-sm gap-1 border-destructive text-destructive">
                      <Minus className="h-3 w-3" /> Supprimé ({result.removed.length})
                    </Badge>
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" checked={showModified} onChange={(e) => setShowModified(e.target.checked)}
                           data-testid="compare-filter-modified" className="accent-amber-500 h-4 w-4" />
                    <Badge variant="outline" className="rounded-sm gap-1 border-amber-500/50 text-amber-500">
                      <Edit3 className="h-3 w-3" /> Modifié ({result.modified.length})
                    </Badge>
                  </label>
                  <label className="flex items-center gap-1 cursor-pointer text-muted-foreground">
                    <input type="checkbox" checked={hideUnchanged} onChange={(e) => setHideUnchanged(e.target.checked)}
                           data-testid="compare-filter-hide-unchanged" className="accent-primary h-4 w-4" />
                    Masquer inchangées
                  </label>
                  {result.walls && (result.walls.added.length + result.walls.removed.length > 0) && (
                    <>
                      <span className="text-xs text-muted-foreground ml-2 border-l border-border pl-3">
                        Murs :
                      </span>
                      <label className="flex items-center gap-1 cursor-pointer">
                        <input type="checkbox" checked={showAddedWalls}
                               onChange={(e) => setShowAddedWalls(e.target.checked)}
                               data-testid="compare-filter-walls-added"
                               className="accent-emerald-500 h-4 w-4" />
                        <Badge variant="outline" className="rounded-sm border-emerald-500/50 text-emerald-500">
                          + Murs ({result.walls.added.length})
                        </Badge>
                      </label>
                      <label className="flex items-center gap-1 cursor-pointer">
                        <input type="checkbox" checked={showRemovedWalls}
                               onChange={(e) => setShowRemovedWalls(e.target.checked)}
                               data-testid="compare-filter-walls-removed"
                               className="accent-red-500 h-4 w-4" />
                        <Badge variant="outline" className="rounded-sm border-destructive text-destructive">
                          – Murs ({result.walls.removed.length})
                        </Badge>
                      </label>
                    </>
                  )}
                </div>
              </div>
              <div className="overflow-auto bg-secondary/30">
                <canvas ref={canvasRef} className="block mx-auto" data-testid="compare-canvas" />
              </div>
            </div>
          )}

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
              {result.walls && (result.walls.before_count + result.walls.after_count > 0) && (
                <p className="text-[10px] text-muted-foreground mt-2 num" data-testid="walls-summary">
                  Murs détectés : {result.walls.before_count} → {result.walls.after_count}
                  {" · "}+{result.walls.added.length} / −{result.walls.removed.length}
                </p>
              )}
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

          {result.unchanged.length > 0 && !hideUnchanged && (
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
