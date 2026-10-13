import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  FlaskConical, Play, Loader2, Users, Boxes, Activity, TrendingUp, AlertTriangle, Zap, Mail,
  Swords, Trophy, History,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

const pct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
const CAT_LABEL = {
  measurement: "Medições", material_waste: "Materiais + perdas", pricing: "Orçamentação",
  phase_sequence: "Ordem das fases", robustness: "Robustez (adversarial)",
};

export default function EvolutionLab() {
  const [cfg, setCfg] = useState(null);
  const [dash, setDash] = useState(null);
  const [busy, setBusy] = useState(false);
  const [running, setRunning] = useState(false);
  const [cmp, setCmp] = useState({ champion_model: "opus", challenger_model: "sonnet", ai_calls: 8 });
  const [cmpRes, setCmpRes] = useState(null);
  const [cmpBusy, setCmpBusy] = useState(false);
  const [reports, setReports] = useState(null);

  const load = async () => {
    const [c, d, r] = await Promise.all([
      api.get("/admin/evolution/config"),
      api.get("/admin/evolution/dashboard"),
      api.get("/admin/evolution/reports").catch(() => ({ data: { items: [], weekly: [] } })),
    ]);
    setCfg(c.data); setDash(d.data); setReports(r.data);
  };
  useEffect(() => { load().catch(() => {}); }, []);

  const runCompare = async () => {
    setCmpBusy(true);
    try {
      const { data } = await api.post("/admin/evolution/compare", cmp);
      setCmpRes(data);
      toast.success(`Arena concluída — vencedor: ${data.winner === "champion" ? cmp.champion_model : cmp.challenger_model}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Comparação impossível"); }
    finally { setCmpBusy(false); }
  };

  const save = async (patch) => {
    setBusy(true);
    try {
      const { data } = await api.put("/admin/evolution/config", patch);
      setCfg(data);
      toast.success("Configuração guardada");
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível"); }
    finally { setBusy(false); }
  };

  const runBatch = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/evolution/run", {});
      const aiTxt = data.ai_calls ? ` · IA ${data.ai_passed}/${data.ai_calls}` : "";
      toast.success(`Lot #${data.generation} : ${data.passed}/${data.size} bem-sucedidos · fitness ${data.fitness_score}${aiTxt}`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Lançamento impossível"); }
    finally { setRunning(false); }
  };

  const sendReport = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/evolution/send-report", {});
      toast.success(`Relatório enviado a ${data.sent_to}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };

  const promote = async (model_key) => {
    setBusy(true);
    try {
      const { data } = await api.put("/admin/evolution/config", { active_ai_model: model_key });
      setCfg(data);
      toast.success(`Modelo ativo: ${model_key} — aplicado ao chatbot e aos testes IA`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Impossível"); }
    finally { setBusy(false); }
  };

  if (!cfg || !dash) return <div className="text-sm text-muted-foreground">Carregamento do laboratório…</div>;

  const last = dash.last_run;
  const graph = dash.evolution_graph || [];
  const maxFit = Math.max(100, ...graph.map((g) => g.fitness || 0));

  return (
    <div className="space-y-6" data-testid="evolution-lab">
      <div className="flex items-center gap-3">
        <FlaskConical className="h-6 w-6 text-primary" />
        <div>
          <h2 className="font-display text-xl font-bold">ConstruPilot AI Evolution Lab</h2>
          <p className="text-xs text-muted-foreground">Simulação de utilizadores virtuais + testes contínuos dos motores (sandbox, sem implementação automática).</p>
        </div>
      </div>

      {/* Configuration */}
      <div className="surface p-4 space-y-4" data-testid="evo-config">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-bold flex items-center gap-2"><Activity className="h-4 w-4 text-primary" />Ativar os testes</div>
            <p className="text-xs text-muted-foreground">Ativa/desativa a execução dos lotes de testes sintéticos.</p>
          </div>
          <Switch checked={cfg.enabled} onCheckedChange={(v) => save({ enabled: v })} disabled={busy} data-testid="evo-toggle-enabled" />
        </div>

        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">Nível de dificuldade (1→6)</label>
            <Input type="number" min={1} max={6} value={cfg.level} onChange={(e) => setCfg({ ...cfg, level: +e.target.value })}
              onBlur={(e) => save({ level: Math.min(6, Math.max(1, +e.target.value || 2)) })} className="h-8" data-testid="evo-level" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Tamanho do lote</label>
            <Input type="number" min={1} max={20000} value={cfg.batch_size} onChange={(e) => setCfg({ ...cfg, batch_size: +e.target.value })}
              onBlur={(e) => save({ batch_size: Math.min(20000, Math.max(1, +e.target.value || 2000)) })} className="h-8" data-testid="evo-batch" />
          </div>
          <div className="flex flex-col justify-end">
            <label className="text-xs text-muted-foreground mb-1">Modo evolução máxima</label>
            <div className="flex items-center gap-2 h-8">
              <Switch checked={cfg.max_evolution_mode} onCheckedChange={(v) => save({ max_evolution_mode: v })} disabled={busy} data-testid="evo-toggle-max" />
              <span className="text-xs text-muted-foreground flex items-center gap-1"><Zap className="h-3.5 w-3.5" />×4 volume, dificuldade ≥4</span>
            </div>
          </div>
        </div>

        <div className="rounded-sm border border-amber-500/30 bg-amber-500/5 p-3 flex items-start gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-xs text-muted-foreground">
            <div className="flex items-center justify-between gap-3">
              <span><b>Testes IA/visão</b> (dispendioso — chamadas LLM). Desativados por defeito para controlar os custos.</span>
              <Switch checked={cfg.ai_enabled} onCheckedChange={(v) => save({ ai_enabled: v })} disabled={busy} data-testid="evo-toggle-ai" />
            </div>
            {cfg.ai_enabled && (
              <div className="mt-2 flex items-center gap-2">
                <span>Limite de chamadas IA / lote:</span>
                <Input type="number" min={0} max={5000} value={cfg.ai_budget_calls} onChange={(e) => setCfg({ ...cfg, ai_budget_calls: +e.target.value })}
                  onBlur={(e) => save({ ai_budget_calls: Math.min(5000, Math.max(0, +e.target.value || 0)) })} className="h-7 w-24" data-testid="evo-ai-budget" />
              </div>
            )}
          </div>
        </div>

        <Button onClick={runBatch} disabled={running || !cfg.enabled} className="gap-2 rounded-sm" data-testid="evo-run-btn">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running ? "Execução da especialidade…" : "Lançar um lote de testes"}
        </Button>
        {!cfg.enabled && <p className="text-xs text-amber-600">Ative « os testes » acima para lançar um lote.</p>}
      </div>

      {/* Rapports planifiés */}
      <div className="surface p-4 space-y-3" data-testid="evo-nightly">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-bold flex items-center gap-2"><Mail className="h-4 w-4 text-primary" />Relatório noturno por e-mail</div>
            <p className="text-xs text-muted-foreground">Um lote é executado todas as noites (03:00 UTC) e o relatório (Fitness + novos clusters) é-lhe enviado.</p>
          </div>
          <Switch checked={cfg.nightly_enabled} onCheckedChange={(v) => save({ nightly_enabled: v })} disabled={busy} data-testid="evo-toggle-nightly" />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[220px]">
            <label className="text-xs text-muted-foreground">E-mail destinatário do relatório</label>
            <Input type="email" value={cfg.nightly_email || ""} onChange={(e) => setCfg({ ...cfg, nightly_email: e.target.value })}
              onBlur={(e) => e.target.value && save({ nightly_email: e.target.value })} placeholder="vous@exemple.fr" className="h-8" data-testid="evo-nightly-email" />
          </div>
          <Button variant="outline" onClick={sendReport} disabled={busy} className="gap-2 rounded-sm" data-testid="evo-send-report-btn">
            <Mail className="h-4 w-4" />Enviar o relatório agora
          </Button>
        </div>
      </div>

      {/* Alerte régression */}
      <div className="surface p-4 space-y-3" data-testid="evo-alert">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-bold flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-primary" />Alerta regressão</div>
            <p className="text-xs text-muted-foreground">Envio de e-mail imediato se o Fitness Score de um lote ficar abaixo do limiar.</p>
          </div>
          <Switch checked={cfg.alert_enabled} onCheckedChange={(v) => save({ alert_enabled: v })} disabled={busy} data-testid="evo-toggle-alert" />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="text-xs text-muted-foreground">Limiar Fitness (/100)</label>
            <Input type="number" min={0} max={100} value={cfg.alert_threshold} onChange={(e) => setCfg({ ...cfg, alert_threshold: +e.target.value })}
              onBlur={(e) => save({ alert_threshold: Math.min(100, Math.max(0, +e.target.value || 90)) })} className="h-8 w-28" data-testid="evo-alert-threshold" /></div>
          <div className="flex-1 min-w-[200px]"><label className="text-xs text-muted-foreground">E-mail de alerta (senão o do relatório)</label>
            <Input type="email" value={cfg.alert_email || ""} onChange={(e) => setCfg({ ...cfg, alert_email: e.target.value })}
              onBlur={(e) => e.target.value && save({ alert_email: e.target.value })} placeholder="alerte@exemple.fr" className="h-8" data-testid="evo-alert-email" /></div>
        </div>
      </div>

      {/* Arène Champion vs Challenger */}
      <div className="surface p-4 space-y-3" data-testid="evo-compare">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="font-bold flex items-center gap-2"><Swords className="h-4 w-4 text-primary" />Comparação Campeão vs Desafiante</div>
          <span className="text-xs text-muted-foreground">Modelo IA ativo: <b className="text-primary" data-testid="evo-active-model">{cfg.active_ai_model}</b></span>
        </div>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <Switch checked={cfg.arena_nightly_enabled} onCheckedChange={(v) => save({ arena_nightly_enabled: v })} disabled={busy} data-testid="evo-toggle-arena-nightly" />
          Arena noturna: todas as noites, alertar-me por e-mail se um modelo mais rápido iguala a precisão do ativo.
        </label>
        <p className="text-xs text-muted-foreground">Dois modelos IA enfrentam os mesmos cenários (mesma seed). O vencedor: melhor precisão, depois velocidade.</p>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="text-xs text-muted-foreground">Campeão</label>
            <select value={cmp.champion_model} onChange={(e) => setCmp({ ...cmp, champion_model: e.target.value })} className="mt-1 h-8 rounded-sm border border-border bg-background px-2 text-sm block" data-testid="evo-cmp-champion">
              {["opus", "sonnet", "haiku", "gemini"].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-muted-foreground">Challenger</label>
            <select value={cmp.challenger_model} onChange={(e) => setCmp({ ...cmp, challenger_model: e.target.value })} className="mt-1 h-8 rounded-sm border border-border bg-background px-2 text-sm block" data-testid="evo-cmp-challenger">
              {["opus", "sonnet", "haiku", "gemini"].map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div><label className="text-xs text-muted-foreground">Testes IA / modelo</label>
            <Input type="number" min={1} max={100} value={cmp.ai_calls} onChange={(e) => setCmp({ ...cmp, ai_calls: Math.min(100, Math.max(1, +e.target.value || 8)) })} className="h-8 w-24" data-testid="evo-cmp-calls" /></div>
          <Button onClick={runCompare} disabled={cmpBusy} className="gap-2 rounded-sm" data-testid="evo-cmp-run">
            {cmpBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Swords className="h-4 w-4" />}{cmpBusy ? "Arena em curso…" : "Comparar"}
          </Button>
        </div>
        {cmpRes && (
          <div className="grid sm:grid-cols-2 gap-3" data-testid="evo-cmp-result">
            {[["champion", cmpRes.champion], ["challenger", cmpRes.challenger]].map(([side, r]) => (
              <div key={side} className={`rounded-sm border p-3 ${cmpRes.winner === side ? "border-primary bg-primary/5" : "border-border"}`} data-testid={`evo-cmp-${side}`}>
                <div className="flex items-center justify-between">
                  <span className="text-xs uppercase text-muted-foreground">{side === "champion" ? "Campeão" : "Challenger"}</span>
                  {cmpRes.winner === side && <span className="text-[10px] font-bold text-primary flex items-center gap-1"><Trophy className="h-3.5 w-3.5" />Vencedor</span>}
                </div>
                <div className="font-bold text-lg">{r.model}</div>
                <div className="text-sm">Precisão: <b>{pct(r.ai_accuracy)}</b> ({r.ai_passed}/{r.ai_calls})</div>
                <div className="text-xs text-muted-foreground">Latência méd.: {r.ai_avg_latency_s ?? "—"} s</div>
              </div>
            ))}
          </div>
        )}
        {cmpRes && (() => {
          const winnerModel = cmpRes.winner === "champion" ? cmp.champion_model : cmp.challenger_model;
          return (
            <div className="flex items-center justify-between flex-wrap gap-2 pt-1">
              <span className="text-xs text-muted-foreground">Vencedor da arena: <b>{winnerModel}</b></span>
              <Button size="sm" onClick={() => promote(winnerModel)} disabled={busy || cfg.active_ai_model === winnerModel} className="gap-2 rounded-sm" data-testid="evo-promote-btn">
                <Trophy className="h-4 w-4" />{cfg.active_ai_model === winnerModel ? "Já ativo" : "Promover o vencedor"}
              </Button>
            </div>
          );
        })()}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="evo-kpis">
        {[
          { icon: Users, label: "Utilizadores virtuais", value: dash.personas + " personas" },
          { icon: Boxes, label: "Tipos de projetos", value: dash.project_types },
          { icon: Activity, label: "Testes executados (total)", value: (dash.tests_total || 0).toLocaleString("fr-FR") },
          { icon: TrendingUp, label: "Taxa de sucesso global", value: pct(dash.global_pass_rate) },
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
            <h3 className="font-bold">Última especialidade · Geração #{last.generation}</h3>
            <span className="text-sm">Fitness Score: <b className="text-primary num">{last.fitness_score}</b> / 100</span>
          </div>
          {last.ai_calls ? (
            <p className="text-xs mb-2 flex items-center gap-1 text-primary" data-testid="evo-ai-result">
              <Activity className="h-3.5 w-3.5" />Testes IA reais: <b>{last.ai_passed}/{last.ai_calls}</b> bem-sucedidos (precisão {pct(last.ai_accuracy)})
            </p>
          ) : null}
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
              <div className="text-xs font-semibold mb-1 flex items-center gap-1"><AlertTriangle className="h-3.5 w-3.5 text-amber-600" />Clusters de falhas</div>
              <div className="space-y-1">
                {last.failure_clusters.map((c, i) => (
                  <div key={i} className="flex justify-between text-xs border-t border-border/60 py-1" data-testid={`evo-cluster-${i}`}>
                    <span className="text-muted-foreground">{c.cluster}</span><span className="font-bold num">{c.count}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <p className="mt-3 text-xs text-emerald-600">Nenhuma falha neste lote — os motores respeitam a verdade-terreno. 🟢</p>}
        </div>
      )}

      {/* Graphe d'évolution des générations */}
      {graph.length > 0 && (
        <div className="surface p-4" data-testid="evo-graph">
          <h3 className="font-bold mb-3">Evolução do Fitness por geração</h3>
          <div className="flex items-end gap-1 h-32">
            {graph.slice(-40).map((g, i) => (
              <div key={i} className="flex-1 bg-primary/80 rounded-t-sm min-w-[3px] hover:bg-primary transition-colors"
                style={{ height: `${((g.fitness || 0) / maxFit) * 100}%` }}
                title={`Gen ${g.generation} · ${g.fitness}`} data-testid={`evo-bar-${i}`} />
            ))}
          </div>
          <p className="text-[11px] text-muted-foreground mt-2">{graph.length} geração(ões) · última: {last?.fitness_score}/100</p>
        </div>
      )}

      {/* Historique des rapports nocturnes */}
      <div className="surface p-4" data-testid="evo-reports">
        <h3 className="font-bold mb-3 flex items-center gap-2"><History className="h-4 w-4 text-primary" />Histórico dos relatórios noturnos</h3>
        {(reports?.weekly || []).length > 0 && (
          <div className="mb-4">
            <div className="text-xs font-semibold mb-1">Evolução semana a semana</div>
            <div className="overflow-auto rounded-sm border border-border">
              <table className="w-full text-xs">
                <thead className="bg-secondary/40"><tr><th className="text-left p-2">Semana</th><th className="p-2 text-right">Capítulos</th><th className="p-2 text-right">Fitness médio</th><th className="p-2 text-right">Taxa de sucesso méd.</th></tr></thead>
                <tbody>
                  {reports.weekly.map((w, i) => (
                    <tr key={i} className="border-t border-border/60" data-testid={`evo-week-${i}`}>
                      <td className="p-2">{w.week}</td><td className="p-2 text-right num">{w.runs}</td>
                      <td className="p-2 text-right num font-semibold text-primary">{w.avg_fitness}</td>
                      <td className="p-2 text-right num">{Math.round(w.avg_pass_rate * 100)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {(reports?.items || []).length > 0 ? (
          <div className="space-y-1">
            {reports.items.slice(0, 10).map((r, i) => (
              <div key={i} className="flex justify-between items-center text-xs border-t border-border/60 py-1.5" data-testid={`evo-report-${i}`}>
                <span className="text-muted-foreground">Ger. #{r.generation} · {new Date(r.created_at).toLocaleDateString("fr-FR")} · {r.size} tests</span>
                <span>Fitness <b className="text-primary num">{r.fitness_score}</b> · {Math.round((r.pass_rate || 0) * 100)}%{r.ai_calls ? ` · IA ${r.ai_passed}/${r.ai_calls}` : ""}</span>
              </div>
            ))}
          </div>
        ) : <p className="text-xs text-muted-foreground">Nenhum relatório noturno por agora. Ative o relatório noturno: um lote executar-se-á todas as noites (ou utilize «Enviar o relatório agora» para testar).</p>}
      </div>
    </div>
  );
}
