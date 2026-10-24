import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { SupervisorResult } from "@/components/agents/SupervisorResult";
import {
  Bot, FileText, ReceiptText, Ruler, ScanLine, GitCompare, ArrowLeft, Loader2,
  CheckCircle2, AlertTriangle, Download, Pencil, Clock, Play, ThumbsUp, ThumbsDown, Check, ShieldCheck, ListChecks,
} from "lucide-react";

const ICONS = { FileText, ReceiptText, Ruler, ScanLine, GitCompare, ShieldCheck };
const STATUS = {
  queued: { label: "En file", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30", icon: Clock },
  running: { label: "Em curso", cls: "bg-blue-500/15 text-blue-600 border-blue-500/30", icon: Loader2, spin: true },
  done: { label: "Terminado", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30", icon: CheckCircle2 },
  error: { label: "Falha", cls: "bg-destructive/15 text-destructive border-destructive/30", icon: AlertTriangle },
  proposed: { label: "Proposto", cls: "bg-muted text-muted-foreground border-border", icon: Clock },
};

const resultSummary = (r) => {
  const x = r.result || {};
  if (x.kind === "summary") return `${x.total_measures} medição(ões) · ${x.total_openings} vão(s)`;
  if (x.kind === "detect") return `${x.total_walls} parede(s) · ${x.total_openings} vão(s) — calibração necessária`;
  if (x.kind === "pdf") return `${x.levels} nível(is) · processo PDF pronto`;
  if (x.kind === "quote") return "Orçamento consolidado criado";
  if (x.kind === "compare") return "Comparação de plantas pronta";
  if (x.kind === "mission") return `${x.done}/${(x.steps || []).length} opção(ões) terminada(s)`;
  return "";
};

export default function AgentsHub() {
  const [search] = useSearchParams();
  return <AgentsHubContent key={search.get("chantier") || "account"} />;
}

function AgentsHubContent() {
  const nav = useNavigate();
  const [search] = useSearchParams();
  const chantierId = search.get("chantier");
  const [catalog, setCatalog] = useState([]);
  const [plans, setPlans] = useState([]);
  const [runs, setRuns] = useState([]);
  const [box, setBox] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const pollRef = useRef(null);

  const loadRuns = async () => {
    try { const { data } = await api.get("/agents/runs", { params: chantierId ? { chantier_id: chantierId } : {} }); setRuns(data.runs || []); setLoadError(false); } catch { setLoadError(true); }
  };

  useEffect(() => {
    api.get("/agents/catalog").then(({ data }) => setCatalog(data.agents || [])).catch(() => {});
    api.get(chantierId ? `/chantiers/${encodeURIComponent(chantierId)}` : "/takeoffs").then(({ data }) => setPlans(data.plans || [])).catch(() => setPlans([]));
    loadRuns();
    pollRef.current = setInterval(loadRuns, 6000);
    return () => clearInterval(pollRef.current);
  }, [chantierId]);

  const startFlow = (agent) => setBox({
    step: "pick", agent: agent.key, meta: agent, selected: [], prompt: "", loading: false, run: null,
    params: { mode: "repair", margin_pct: 0, project_name: "", client_name: "", client_company: "", client_address: "", client_city: "", client_email: "", client_phone: "" },
  });
  const toggle = (pid) => setBox((b) => ({ ...b, selected: b.selected.includes(pid) ? b.selected.filter((x) => x !== pid) : [...b.selected, pid] }));
  const setParam = (k, v) => setBox((b) => ({ ...b, params: { ...b.params, [k]: v } }));
  const setLevel = (pid, level) => setBox((b) => ({ ...b, run: { ...b.run, plan_status: b.run.plan_status.map((s) => s.plan_id === pid ? { ...s, level } : s) } }));

  const propose = async () => {
    if (box.meta.needs_plans && !box.selected.length) return toast.error("Selecione pelo menos uma planta");
    if (box.agent === "compare" && box.selected.length !== 2) return toast.error("Selecione exatamente 2 plantas (antes / depois)");
    setBox((b) => ({ ...b, loading: true }));
    try {
      const { data } = await api.post("/agents/plan", { agent: box.agent, plan_ids: box.selected, prompt: box.prompt, chantier_id: chantierId || undefined });
      setBox((b) => ({ ...b, step: "review", loading: false, run: data.run, params: { ...b.params, margin_pct: data.defaults?.margin_pct || 0 } }));
    } catch (e) { setBox((b) => ({ ...b, loading: false })); toast.error(e?.response?.data?.detail || "Proposta impossível"); }
  };

  const launch = async () => {
    setBox((b) => ({ ...b, loading: true }));
    try {
      let runId = box.run.run_id;
      if (box.agent === "report" || box.agent === "devis") {
        const labels = Object.fromEntries(box.run.plan_status.map((s) => [s.plan_id, s.level]));
        const { data: rev } = await api.post(`/agents/${runId}/revise`, { level_labels: labels, margin_pct: box.params.margin_pct });
        runId = rev.run.run_id;
      }
      await api.post(`/agents/${runId}/launch`, box.params);
      toast.success("Agente lançado em segundo plano", { description: "Pode mudar de página — será notificado no fim." });
      setBox(null);
      loadRuns();
    } catch (e) { setBox((b) => ({ ...b, loading: false })); toast.error(e?.response?.data?.detail || "Lançamento impossível"); }
  };

  const download = async (r) => {
    const dl = r?.result?.download; if (!dl) return;
    try {
      const res = await api.get(dl, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url;
      a.download = r.result.kind === "quote" ? "devis.pdf" : "dossier.pdf";
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { toast.error("Transferência impossível"); }
  };

  const feedback = async (r, rating) => {
    try { await api.post(`/agents/${r.run_id}/feedback`, { rating });
      toast.success(rating === "ok" ? "A sua opinião foi registada" : "Resultado assinalado como a corrigir");
    } catch { toast.error("Envio impossível"); }
  };

  const cancel = async run => {
    try {
      await api.post(`/agents/${run.run_id}/cancel`);
      toast.info("Paragem pedida. As correções já efetuadas continuam consultáveis.");
      loadRuns();
    } catch (error) { toast.error(error?.response?.data?.detail || "Paragem impossível"); }
  };

  const withPlans = (box?.meta?.needs_plans) ?? true;
  const needsParams = box && (box.agent === "report" || box.agent === "devis");

  return (
    <div className="mx-auto max-w-5xl px-5 py-8" data-testid="agents-hub">
      <header className="mb-6">
        {chantierId && <Button variant="ghost" className="mb-3" onClick={() => nav(`/chantiers/${encodeURIComponent(chantierId)}`)}><ArrowLeft size={16} /> Voltar ao processo · controlo limitado a esta obra</Button>}
        <p className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center gap-2">
          <Bot className="h-4 w-4" /> Agentes IA
        </p>
        <h1 className="font-display text-3xl lg:text-4xl font-extrabold mt-1">O seu piloto de projeto</h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-2xl">
          Verifique os seus dados, identifique as incoerências e corrija os valores recalculáveis. O seu piloto trabalha <strong>em segundo plano</strong>, mesmo quando muda de página. Cada resultado precisa o que foi controlado e o que falta confirmar.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={() => nav(`/missions${chantierId ? `?chantier=${encodeURIComponent(chantierId)}` : ""}`)} data-testid="agents-open-missions"><ListChecks className="h-4 w-4 mr-1" /> Programa de opções</Button>
          <Button variant="outline" onClick={() => nav(`/assistant?intent=supervise${chantierId ? `&chantier=${encodeURIComponent(chantierId)}` : ""}`)}>Descrever o meu pedido ao assistente</Button>
        </div>
      </header>

      {!box && (
        <>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="agents-catalog">
            {catalog.map((a) => {
              const Icon = ICONS[a.icon] || Bot;
              return (
                <button key={a.key} type="button" data-testid={`agent-card-${a.key}`} onClick={() => startFlow(a)}
                  className="text-left rounded-xl border border-border bg-card p-5 hover:border-primary/50 hover:-translate-y-0.5 transition-all">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center"><Icon className="h-5 w-5 text-primary" /></span>
                    <h3 className="font-display font-bold">{a.name}</h3>
                  </div>
                  <p className="text-sm text-muted-foreground">{a.desc}</p>
                  <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-primary"><Play className="h-3.5 w-3.5" /> Lançar</span>
                </button>
              );
            })}
          </div>

          <section className="mt-10" data-testid="agent-runs-section">
            {loadError && <p role="alert" className="text-sm text-destructive mb-3">Impossível carregar as tarefas. Atualize para tentar novamente.</p>}
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display text-xl font-bold">Execuções recentes</h2>
              <Button size="sm" variant="ghost" onClick={loadRuns} data-testid="agent-runs-refresh">Atualizar</Button>
            </div>
            {runs.length === 0 ? (
              <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">
                Nenhuma execução por agora. Escolha um agente acima.
              </p>
            ) : (
              <div className="space-y-2" data-testid="agent-runs-list">
                {runs.map((r) => {
                  const st = STATUS[r.status] || STATUS.proposed; const SI = st.icon;
                  return (
                    <div key={r.run_id} data-testid={`agent-run-${r.run_id}`} className="rounded-lg border border-border bg-card p-3 flex items-center gap-3 flex-wrap">
                      <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${st.cls}`}>
                        <SI className={`h-3 w-3 ${st.spin ? "animate-spin" : ""}`} /> {st.label}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-semibold text-sm truncate">{r.agent === "mission"
                          ? <button type="button" className="hover:underline" onClick={() => nav(`/missions?run=${encodeURIComponent(r.run_id)}`)} data-testid={`agent-open-mission-${r.run_id}`}>{r.agent_name}</button>
                          : r.agent_name}</p>
                        <p className="text-[11px] text-muted-foreground num">{new Date(r.created_at).toLocaleString("pt-PT")}</p>
                      </div>
                      {r.status === "done" && (
                        <div className="flex items-center gap-2 flex-wrap">
                          {resultSummary(r) && <span className="text-xs text-muted-foreground">{resultSummary(r)}</span>}
                          {r.result?.download && (
                            <Button size="sm" variant="outline" onClick={() => download(r)} data-testid={`agent-dl-${r.run_id}`}>
                              <Download className="h-3.5 w-3.5 mr-1" /> PDF
                            </Button>
                          )}
                          {r.result?.edit && (
                            <Button size="sm" variant="outline" onClick={() => nav(r.result.edit)} data-testid={`agent-open-${r.run_id}`}>
                              <Pencil className="h-3.5 w-3.5 mr-1" /> Abrir
                            </Button>
                          )}
                          {r.result?.needs_calibration && r.result?.edit_plan_id && (
                            <Button size="sm" variant="outline" onClick={() => nav("/plan")} data-testid={`agent-cal-${r.run_id}`}>
                              <Ruler className="h-3.5 w-3.5 mr-1" /> Calibrar
                            </Button>
                          )}
                          <Button size="icon" variant="ghost" className="h-8 w-8" title="Bom resultado" onClick={() => feedback(r, "ok")} data-testid={`agent-fb-ok-${r.run_id}`}><ThumbsUp className="h-3.5 w-3.5" /></Button>
                          <Button size="icon" variant="ghost" className="h-8 w-8" title="A corrigir" onClick={() => feedback(r, "error")} data-testid={`agent-fb-no-${r.run_id}`}><ThumbsDown className="h-3.5 w-3.5" /></Button>
                        </div>
                      )}
                      {r.status === "error" && <span className="text-xs text-destructive max-w-full truncate">{r.error || "Falha"}</span>}
                      {(r.status === "queued" || r.status === "running") && <span className="text-xs text-muted-foreground">A trabalhar em segundo plano…</span>}
                      {(r.status === "queued" || r.status === "running") && <Button size="sm" variant="ghost" disabled={r.cancel_requested} onClick={() => cancel(r)} data-testid={`agent-cancel-${r.run_id}`}>{r.cancel_requested ? "Paragem pedida" : "Parar"}</Button>}
                      <SupervisorResult run={r} />
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </>
      )}

      {box && (
        <div className="rounded-xl border border-border bg-card p-5" data-testid="agent-flow">
          <button type="button" onClick={() => setBox(null)} className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-4" data-testid="agent-flow-back">
            <ArrowLeft className="h-4 w-4" /> Voltar aos agentes
          </button>
          <h2 className="font-display text-2xl font-bold">{box.meta?.name}</h2>
          <p className="text-sm text-muted-foreground mb-5">{box.meta?.desc}</p>

          {box.step === "pick" && (
            <div className="space-y-4">
              {withPlans && (
                <div>
                  <p className="text-sm font-semibold mb-2">
                    {box.agent === "compare" ? "Selecione 2 plantas (antes / depois)" : "Selecione as plantas"}
                  </p>
                  {plans.length === 0 ? (
                    <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-5">
                      Nenhuma planta importada. Adicione plantas em <button className="text-primary underline" onClick={() => nav("/plan")}>Plantas &amp; medições</button>.
                    </p>
                  ) : (
                    <div className="max-h-72 overflow-y-auto rounded-lg border border-border divide-y divide-border" data-testid="agent-plan-list">
                      {plans.map((p) => {
                        const on = box.selected.includes(p.plan_id);
                        return (
                          <button key={p.plan_id} type="button" onClick={() => toggle(p.plan_id)} data-testid={`agent-plan-${p.plan_id}`}
                            className={`w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm hover:bg-secondary/40 ${on ? "bg-primary/5" : ""}`}>
                            <span className={`h-4 w-4 rounded border grid place-items-center shrink-0 ${on ? "bg-primary border-primary text-primary-foreground" : "border-border"}`}>
                              {on && <Check className="h-3 w-3" />}
                            </span>
                            <span className="truncate flex-1">{p.filename || p.plan_id}</span>
                            {p.kind && <span className="text-[10px] uppercase text-muted-foreground">{p.kind}</span>}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
              {box.agent === "supervise" ? <div className="rounded-xl border border-border bg-secondary/30 p-4 space-y-3" data-testid="supervisor-mode">
                <p className="text-sm">O controlo incide sobre as plantas e orçamentos acessíveis da sua conta, até 200 de cada tipo. Para visar um processo preciso, descreva o seu pedido ao assistente.</p>
                <label className="flex items-start gap-3 text-sm"><input type="radio" name="supervisor-mode" checked={box.params.mode === "repair"} onChange={() => setParam("mode", "repair")} className="mt-1" /><span><strong>Controlar e corrigir automaticamente</strong><br />Recálculo dos valores derivados, histórico e opção de anulação.</span></label>
                <label className="flex items-start gap-3 text-sm"><input type="radio" name="supervisor-mode" checked={box.params.mode === "audit"} onChange={() => setParam("mode", "audit")} className="mt-1" /><span><strong>Apenas controlar</strong><br />Ver as diferenças antes de alterar os dados.</span></label>
              </div> : <div>
                <p className="text-sm font-semibold mb-1.5">Instrução (opcional)</p>
                <Textarea rows={2} value={box.prompt} onChange={(e) => setBox((b) => ({ ...b, prompt: e.target.value }))}
                  placeholder="Ex.: agrupar por piso, chamar ao projeto «Moradia Duarte»…" data-testid="agent-prompt" />
              </div>}
              <Button onClick={propose} disabled={box.loading} data-testid="agent-propose-btn" className="gap-2">
                {box.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Propor o plano de ação
              </Button>
            </div>
          )}

          {box.step === "review" && box.run && (
            <div className="space-y-5">
              <div>
                <p className="text-sm font-semibold mb-2">Plano de ação proposto</p>
                <ol className="space-y-2" data-testid="agent-steps">
                  {(box.run.steps || []).map((s) => (
                    <li key={s.key} className="rounded-lg border border-border p-3">
                      <p className="text-sm font-semibold">{s.label}</p>
                      {s.detail && <p className="text-xs text-muted-foreground mt-0.5">{s.detail}</p>}
                    </li>
                  ))}
                </ol>
              </div>

              {(box.run.warnings || []).length > 0 && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" data-testid="agent-warnings">
                  {box.run.warnings.map((w, i) => (
                    <p key={i} className="text-xs text-amber-700 flex items-start gap-1.5"><AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {w}</p>
                  ))}
                </div>
              )}

              {needsParams && (box.run.plan_status || []).length > 0 && (
                <div>
                  <p className="text-sm font-semibold mb-2">Pisos (editáveis)</p>
                  <div className="space-y-2">
                    {box.run.plan_status.map((s) => (
                      <div key={s.plan_id} className="flex items-center gap-3">
                        <span className="text-sm text-muted-foreground truncate flex-1">{s.filename}</span>
                        <Input value={s.level} onChange={(e) => setLevel(s.plan_id, e.target.value)} className="w-32 h-8" data-testid={`agent-level-${s.plan_id}`} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {needsParams && (
                <div className="grid sm:grid-cols-2 gap-3">
                  <div>
                    <p className="text-xs font-semibold mb-1">Margem alvo (%)</p>
                    <Input type="number" value={box.params.margin_pct} onChange={(e) => setParam("margin_pct", parseFloat(e.target.value) || 0)} data-testid="agent-margin" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold mb-1">Nome do projeto</p>
                    <Input value={box.params.project_name} onChange={(e) => setParam("project_name", e.target.value)} placeholder="Ex.: Moradia Duarte" data-testid="agent-project-name" />
                  </div>
                  <div><p className="text-xs font-semibold mb-1">Cliente</p><Input value={box.params.client_name} onChange={(e) => setParam("client_name", e.target.value)} placeholder="Nome do cliente" data-testid="agent-client-name" /></div>
                  <div><p className="text-xs font-semibold mb-1">E-mail cliente</p><Input value={box.params.client_email} onChange={(e) => setParam("client_email", e.target.value)} placeholder="client@email.fr" data-testid="agent-client-email" /></div>
                </div>
              )}

              <div className="flex items-center gap-2">
                <Button onClick={launch} disabled={box.loading} data-testid="agent-launch-btn" className="gap-2">
                  {box.loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />} Lançar em segundo plano
                </Button>
                <Button variant="ghost" onClick={() => setBox((b) => ({ ...b, step: "pick" }))} data-testid="agent-back-pick">Alterar a seleção</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
