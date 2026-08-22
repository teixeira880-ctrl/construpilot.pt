import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  FlaskConical, Play, Loader2, Users, Boxes, Activity, TrendingUp, AlertTriangle, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const CAT_LABEL = {
  measurement: "Métrés", material_waste: "Matériaux + pertes", pricing: "Chiffrage",
  phase_sequence: "Ordre des phases", robustness: "Robustesse (adversarial)",
};

export default function EvolutionLab() {
  const [cfg, setCfg] = useState(null);
  const [dash, setDash] = useState(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);

  const load = async () => {
    const [c, d] = await Promise.all([
      api.get("/admin/evolution/config"),
      api.get("/admin/evolution/dashboard"),
    ]);
    setCfg(c.data); setDash(d.data);
  };
  useEffect(() => { load().catch(() => {}); }, []);

  const save = async (patch) => {
    setBusy(true);
    try {
      const { data } = await api.put("/admin/evolution/config", patch);
      setCfg(data);
      toast.success("Configuration enregistrée");
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossible"); }
    finally { setBusy(false); }
  };

  const runBatch = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/evolution/run", {});
      toast.success(`Lot #${data.generation} : ${data.passed}/${data.size} réussis · fitness ${data.fitness_score}`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Lancement impossible"); }
    finally { setRunning(false); }
  };

  if (!cfg || !dash) return <div className="text-sm text-muted-foreground">Chargement du laboratoire…</div>;

  const last = dash.last_run;
  const graph = dash.evolution_graph || [];
  const maxFit = Math.max(100, ...graph.map((g) => g.fitness || 0));

  return (
    <div className="space-y-6" data-testid="evolution-lab">
      <div className="flex items-center gap-3">
        <FlaskConical className="h-6 w-6 text-primary" />
        <div>
          <h2 className="font-display text-xl font-bold">ConstruPilot AI Evolution Lab</h2>
          <p className="text-xs text-muted-foreground">Simulation d'utilisateurs virtuels + tests continus des moteurs (sandbox, sans déploiement automatique).</p>
        </div>
      </div>

      {/* Configuration */}
      <div className="surface p-4 space-y-4" data-testid="evo-config">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-bold flex items-center gap-2"><Activity className="h-4 w-4 text-primary" />Activer les tests</div>
            <p className="text-xs text-muted-foreground">Active/désactive l'exécution des lots de tests synthétiques.</p>
          </div>
          <Switch checked={cfg.enabled} onCheckedChange={(v) => save({ enabled: v })} disabled={busy} data-testid="evo-toggle-enabled" />
        </div>

        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">Niveau de difficulté (1→6)</label>
            <Input type="number" min={1} max={6} value={cfg.level} onChange={(e) => setCfg({ ...cfg, level: +e.target.value })}
              onBlur={(e) => save({ level: Math.min(6, Math.max(1, +e.target.value || 2)) })} className="h-8" data-testid="evo-level" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Taille du lot</label>
            <Input type="number" min={1} max={20000} value={cfg.batch_size} onChange={(e) => setCfg({ ...cfg, batch_size: +e.target.value })}
              onBlur={(e) => save({ batch_size: Math.min(20000, Math.max(1, +e.target.value || 2000)) })} className="h-8" data-testid="evo-batch" />
          </div>
          <div className="flex flex-col justify-end">
            <label className="text-xs text-muted-foreground mb-1">Mode évolution maximale</label>
            <div className="flex items-center gap-2 h-8">
              <Switch checked={cfg.max_evolution_mode} onCheckedChange={(v) => save({ max_evolution_mode: v })} disabled={busy} data-testid="evo-toggle-max" />
              <span className="text-xs text-muted-foreground flex items-center gap-1"><Zap className="h-3.5 w-3.5" />×4 volume, difficulté ≥4</span>
            </div>
          </div>
        </div>

        <div className="rounded-sm border border-amber-500/30 bg-amber-500/5 p-3 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-xs text-muted-foreground">
            <div className="flex items-center justify-between gap-3">
              <span><b>Tests IA/vision</b> (coûteux — appels LLM). Désactivés par défaut pour maîtriser les coûts.</span>
              <Switch checked={cfg.ai_enabled} onCheckedChange={(v) => save({ ai_enabled: v })} disabled={busy} data-testid="evo-toggle-ai" />
            </div>
            {cfg.ai_enabled && (
              <div className="mt-2 flex items-center gap-2">
                <span>Plafond d'appels IA / lot :</span>
                <Input type="number" min={0} max={5000} value={cfg.ai_budget_calls} onChange={(e) => setCfg({ ...cfg, ai_budget_calls: +e.target.value })}
                  onBlur={(e) => save({ ai_budget_calls: Math.min(5000, Math.max(0, +e.target.value || 0)) })} className="h-7 w-24" data-testid="evo-ai-budget" />
              </div>
            )}
          </div>
        </div>

        <Button onClick={runBatch} disabled={running || !cfg.enabled} className="gap-2 rounded-sm" data-testid="evo-run-btn">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Exécution du lot…" : "Lancer un lot de tests"}
        </Button>
        {!cfg.enabled && <p className="text-xs text-amber-600">Activez « les tests » ci-dessus pour lancer un lot.</p>}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="evo-kpis">
        {[
          { icon: Users, label: "Utilisateurs virtuels", value: dash.personas + " personas" },
          { icon: Boxes, label: "Types de projets", value: dash.project_types },
          { icon: Activity, label: "Tests exécutés (total)", value: (dash.tests_total || 0).toLocaleString("fr-FR") },
          { icon: TrendingUp, label: "Taux de réussite global", value: pct(dash.global_pass_rate) },
        ].map((k, i) => (
          <div key={i} className="surface p-4" data-testid={`evo-kpi-${i}`}>
            <k.icon className="h-4 w-4 text-primary" />
            <div className="mt-2 text-xl font-bold num">{k.value}</div>
            <div className="text-xs text-muted-foreground">{k.label}</div>
          </div>
        ))}
      </div>

      {/* Dernier lot : fitness + précision par catégorie */}
      {last && (
        <div className="surface p-4" data-testid="evo-last-run">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold">Dernier lot · Génération #{last.generation}</h3>
            <span className="text-sm">Fitness Score : <b className="text-primary num">{last.fitness_score}</b> / 100</span>
          </div>
          <div className="grid sm:grid-cols-5 gap-2">
            {Object.entries(last.accuracy || {}).map(([cat, v]) => (
              <div key={cat} className="rounded-sm border border-border p-2" data-testid={`evo-acc-${cat}`}>
                <div className="text-[11px] text-muted-foreground">{CAT_LABEL[cat] || cat}</div>
                <div className="text-lg font-bold num">{pct(v)}</div>
                <div className="h-1.5 rounded-full bg-secondary mt-1 overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${(v || 0) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          {(last.failure_clusters || []).length > 0 ? (
            <div className="mt-3">
              <div className="text-xs font-semibold mb-1 flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-600" />Clusters d'échecs</div>
              <div className="space-y-1">
                {last.failure_clusters.map((c, i) => (
                  <div key={i} className="flex justify-between text-xs border-t border-border/60 py-1" data-testid={`evo-cluster-${i}`}>
                    <span className="text-muted-foreground">{c.cluster}</span><span className="font-bold num">{c.count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <p className="mt-3 text-xs text-emerald-600">Aucun échec sur ce lot — les moteurs respectent la vérité-terrain. 🟢</p>}
        </div>
      )}

      {/* Graphe d'évolution des générations */}
      {graph.length > 0 && (
        <div className="surface p-4" data-testid="evo-graph">
          <h3 className="font-bold mb-3">Évolution du Fitness par génération</h3>
          <div className="flex items-end gap-1 h-32">
            {graph.slice(-40).map((g, i) => (
              <div key={i} className="flex-1 bg-primary/80 rounded-t-sm min-w-[3px] hover:bg-primary transition-colors"
                style={{ height: `${((g.fitness || 0) / maxFit) * 100}%` }}
                title={`Gen ${g.generation} · ${g.fitness}`} data-testid={`evo-bar-${i}`} />
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">{graph.length} génération(s) · dernière : {last?.fitness_score}/100</p>
        </div>
      )}
    </div>
  );
}
