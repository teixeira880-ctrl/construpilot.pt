import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  ListChecks, ArrowLeft, Loader2, CheckCircle2, AlertTriangle, Clock, Check, Download, Pencil,
  ArrowUpRight, Ban, Sparkles, Play,
} from "lucide-react";

// Nome do ficheiro devolvido pelo servidor (Content-Disposition), senão um nome por defeito.
const fileName = (res, fallback, ext = "pdf") => {
  const cd = res?.headers?.["content-disposition"] || "";
  const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  try { return m ? decodeURIComponent(m[1] || m[2]) : `${fallback}.${ext}`; } catch { return `${fallback}.${ext}`; }
};
const num = (x, d = 1) => (x === null || x === undefined ? "—" : Number(x).toLocaleString("pt-PT", { maximumFractionDigits: d }));

const STEP = {
  pending: { label: "Em espera", cls: "bg-muted text-muted-foreground border-border", icon: Clock },
  running: { label: "Em curso", cls: "bg-blue-500/15 text-blue-600 border-blue-500/30", icon: Loader2, spin: true },
  done: { label: "Terminado", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30", icon: CheckCircle2 },
  error: { label: "Falhou", cls: "bg-destructive/15 text-destructive border-destructive/30", icon: AlertTriangle },
  skipped: { label: "Não lançada", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30", icon: Ban },
};
const RUN = {
  proposed: { label: "A validar", cls: STEP.pending.cls, icon: Clock },
  queued: { label: "Em fila", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30", icon: Clock },
  running: STEP.running,
  done: STEP.done,
  error: STEP.error,
};

const Badge = ({ st }) => {
  const Icon = st.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${st.cls}`}>
      <Icon className={`h-3 w-3 ${st.spin ? "animate-spin" : ""}`} /> {st.label}
    </span>
  );
};

// Assinala uma opção com os seus pré-requisitos; desmarca também as que dela dependem.
const withDeps = (key, options, set) => {
  const next = new Set(set);
  const add = (k) => { if (next.has(k)) return; next.add(k); (options.find((o) => o.key === k)?.depends_on || []).forEach(add); };
  add(key);
  return next;
};
const withoutDependents = (key, options, set) => {
  const next = new Set(set);
  const drop = (k) => { next.delete(k); options.filter((o) => o.depends_on.includes(k) && next.has(o.key)).forEach((o) => drop(o.key)); };
  drop(key);
  return next;
};

export default function Missions() {
  const [search] = useSearchParams();
  return <MissionsContent key={search.get("chantier") || "account"} />;
}

function MissionsContent() {
  const nav = useNavigate();
  const [search, setSearch] = useSearchParams();
  const chantierId = search.get("chantier");
  const [options, setOptions] = useState([]);
  const [plans, setPlans] = useState([]);
  const [chantiers, setChantiers] = useState([]);
  const [picked, setPicked] = useState(new Set());
  const [selectedPlans, setSelectedPlans] = useState([]);
  const [note, setNote] = useState("");
  const [recap, setRecap] = useState(null);
  const [params, setParams] = useState({ margin_pct: 0, project_name: "", client_name: "", client_email: "" });
  const [busy, setBusy] = useState(false);
  const [runs, setRuns] = useState([]);
  const [openRun, setOpenRun] = useState(null);
  const pollRef = useRef(null);

  const loadRuns = async () => {
    try {
      const { data } = await api.get("/agents/runs", { params: chantierId ? { chantier_id: chantierId } : {} });
      setRuns((data.runs || []).filter((r) => r.agent === "mission" && r.status !== "proposed"));
    } catch { /* rede: volta a tentar */ }
  };

  useEffect(() => {
    api.get("/missions/catalog").then(({ data }) => setOptions(data.options || [])).catch(() => toast.error("Catálogo indisponível"));
    api.get("/chantiers").then(({ data }) => setChantiers(data.chantiers || [])).catch(() => {});
    api.get(chantierId ? `/chantiers/${encodeURIComponent(chantierId)}` : "/takeoffs").then(({ data }) => setPlans(data.plans || [])).catch(() => setPlans([]));
    loadRuns();
    pollRef.current = setInterval(loadRuns, 5000);
    return () => clearInterval(pollRef.current);
  }, [chantierId]);

  useEffect(() => {
    const id = search.get("run");
    if (!id) { setOpenRun(null); return undefined; }
    let alive = true;
    const load = () => api.get(`/missions/${encodeURIComponent(id)}`).then(({ data }) => { if (alive) setOpenRun(data.run); }).catch(() => {});
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [search]);

  const groups = useMemo(() => {
    const out = [];
    options.forEach((o) => {
      let g = out.find((x) => x.name === o.group);
      if (!g) { g = { name: o.group, items: [] }; out.push(g); }
      g.items.push(o);
    });
    return out;
  }, [options]);
  const nameOf = (k) => options.find((o) => o.key === k)?.name || k;
  const needsPricing = picked.has("devis") || picked.has("dossier");

  const toggleOption = (o) => setPicked((s) => (s.has(o.key) ? withoutDependents(o.key, options, s) : withDeps(o.key, options, s)));
  const togglePlan = (pid) => setSelectedPlans((s) => (s.includes(pid) ? s.filter((x) => x !== pid) : [...s, pid]));

  const review = async () => {
    if (!picked.size) return toast.error("Assinale pelo menos uma opção");
    setBusy(true);
    try {
      const { data } = await api.post("/missions/plan", {
        options: [...picked], plan_ids: selectedPlans, note, chantier_id: chantierId || undefined,
      });
      setRecap(data.run);
    } catch (e) { toast.error(e?.response?.data?.detail || "Resumo impossível"); }
    finally { setBusy(false); }
  };

  const launch = async () => {
    setBusy(true);
    try {
      await api.post(`/agents/${recap.run_id}/launch`, params);
      toast.success("Programa lançado", { description: "A IA executa apenas as opções validadas. Será notificado no fim." });
      setSearch((s) => { const n = new URLSearchParams(s); n.set("run", recap.run_id); return n; });
      setRecap(null); setPicked(new Set()); setSelectedPlans([]); setNote("");
      loadRuns();
    } catch (e) { toast.error(e?.response?.data?.detail || "Lançamento impossível"); }
    finally { setBusy(false); }
  };

  const cancel = async (run) => {
    try { await api.post(`/agents/${run.run_id}/cancel`); toast.info("Paragem pedida"); loadRuns(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Paragem impossível"); }
  };

  const download = async (path, label, ext = "pdf") => {
    try {
      const res = await api.get(path, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = fileName(res, label, ext);
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { toast.error("Descarga impossível"); }
  };

  const openDetail = (runId) => setSearch((s) => { const n = new URLSearchParams(s); n.set("run", runId); return n; });
  const closeDetail = () => setSearch((s) => { const n = new URLSearchParams(s); n.delete("run"); return n; });

  return (
    <div className="mx-auto max-w-5xl px-5 py-8" data-testid="missions-page">
      <header className="mb-6">
        <Button variant="ghost" className="mb-3" onClick={() => nav(`/agents${chantierId ? `?chantier=${encodeURIComponent(chantierId)}` : ""}`)}><ArrowLeft size={16} /> Agentes IA</Button>
        <p className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center gap-2"><ListChecks className="h-4 w-4" /> Programa IA de opções</p>
        <h1 className="font-display text-3xl lg:text-4xl font-extrabold mt-1">Assinale, valide, a IA trata do resto</h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-2xl">
          Escolha os entregáveis que quer para este processo. Depois da sua validação, a IA realiza-os sozinha, em segundo plano,
          e <strong>apenas esses</strong>. Nada é enviado ao cliente sem o seu clique.
        </p>
      </header>

      {openRun && <MissionDetail run={openRun} onClose={closeDetail} onCancel={cancel} onDownload={download} nav={nav} />}

      {!openRun && !recap && (
        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-card p-5" data-testid="missions-dossier">
            <h2 className="font-display text-lg font-bold mb-3">1. O processo de base</h2>
            <div className="mb-3 max-w-sm">
              <p className="text-xs font-semibold mb-1">Processo de obra</p>
              <select className="w-full h-9 rounded-md border border-border bg-background px-2 text-sm" value={chantierId || ""}
                onChange={(e) => setSearch(e.target.value ? { chantier: e.target.value } : {})} data-testid="missions-chantier">
                <option value="">Nenhum (plantas da conta)</option>
                {chantiers.map((c) => <option key={c.chantier_id} value={c.chantier_id}>{c.name || c.chantier_id}</option>)}
              </select>
            </div>
            <p className="text-xs font-semibold mb-1">Plantas a utilizar</p>
            {plans.length === 0 ? (
              <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-4">
                Nenhuma planta. Adicione plantas em <button className="text-primary underline" onClick={() => nav("/plan")}>Plantas &amp; medições</button>.
              </p>
            ) : (
              <div className="max-h-56 overflow-y-auto rounded-lg border border-border divide-y divide-border" data-testid="missions-plans">
                {plans.map((p) => {
                  const on = selectedPlans.includes(p.plan_id);
                  return (
                    <button key={p.plan_id} type="button" onClick={() => togglePlan(p.plan_id)} data-testid={`missions-plan-${p.plan_id}`}
                      className={`w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-secondary/40 ${on ? "bg-primary/5" : ""}`}>
                      <span className={`h-4 w-4 rounded border grid place-items-center shrink-0 ${on ? "bg-primary border-primary text-primary-foreground" : "border-border"}`}>{on && <Check className="h-3 w-3" />}</span>
                      <span className="truncate flex-1">{p.filename || p.plan_id}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-border bg-card p-5" data-testid="missions-options">
            <h2 className="font-display text-lg font-bold mb-1">2. As opções</h2>
            <p className="text-xs text-muted-foreground mb-4">Uma opção que exige outra assinala-a automaticamente; vê-a antes de validar.</p>
            <div className="space-y-5">
              {groups.map((g) => (
                <div key={g.name}>
                  <p className="text-xs uppercase tracking-wider text-muted-foreground font-semibold mb-2">{g.name}</p>
                  <div className="grid sm:grid-cols-2 gap-2">
                    {g.items.map((o) => {
                      const on = picked.has(o.key);
                      const requiredBy = options.filter((x) => picked.has(x.key) && x.depends_on.includes(o.key)).map((x) => x.name);
                      return (
                        <button key={o.key} type="button" onClick={() => toggleOption(o)} data-testid={`missions-option-${o.key}`}
                          className={`text-left rounded-lg border p-3 transition-colors ${on ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"}`}>
                          <span className="flex items-start gap-3">
                            <span className={`mt-0.5 h-4 w-4 rounded border grid place-items-center shrink-0 ${on ? "bg-primary border-primary text-primary-foreground" : "border-border"}`}>{on && <Check className="h-3 w-3" />}</span>
                            <span className="min-w-0">
                              <span className="block font-semibold text-sm">{o.name}</span>
                              <span className="block text-xs text-muted-foreground mt-0.5">{o.desc}</span>
                              {o.depends_on.length > 0 && <span className="block text-[11px] text-muted-foreground mt-1">Exige: {o.depends_on.map(nameOf).join(", ")}</span>}
                              {on && requiredBy.length > 0 && <span className="block text-[11px] text-primary mt-1">Exigida por: {requiredBy.join(", ")}</span>}
                            </span>
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4">
              <p className="text-xs font-semibold mb-1">Indicação para a IA (opcional)</p>
              <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ex.: moradia R/C + 1, cliente particular" data-testid="missions-note" />
            </div>
            <Button className="mt-4 gap-2" onClick={review} disabled={busy || !picked.size} data-testid="missions-review">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListChecks className="h-4 w-4" />} Ver o resumo ({picked.size})
            </Button>
          </section>

          <section data-testid="missions-runs">
            <h2 className="font-display text-xl font-bold mb-3">Programas lançados</h2>
            {runs.length === 0 ? (
              <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-6 text-center">Ainda nenhum programa.</p>
            ) : (
              <div className="space-y-2">
                {runs.map((r) => {
                  const steps = (r.result || r.partial_result || r.mission || {}).steps || [];
                  const done = steps.filter((s) => s.status === "done").length;
                  return (
                    <button key={r.run_id} type="button" onClick={() => openDetail(r.run_id)} data-testid={`missions-run-${r.run_id}`}
                      className="w-full rounded-lg border border-border bg-card p-3 flex items-center gap-3 text-left hover:border-primary/50">
                      <Badge st={RUN[r.status] || RUN.proposed} />
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-semibold truncate">{(r.mission?.steps || []).map((s) => s.name).join(" · ") || "Programa"}</span>
                        <span className="block text-[11px] text-muted-foreground num">{new Date(r.created_at).toLocaleString("pt-PT")} · {done}/{steps.length} opção(ões) terminada(s)</span>
                      </span>
                      <ArrowUpRight className="h-4 w-4 text-muted-foreground shrink-0" />
                    </button>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      )}

      {!openRun && recap && (
        <section className="rounded-xl border border-border bg-card p-5 space-y-5" data-testid="missions-recap">
          <button type="button" onClick={() => setRecap(null)} className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"><ArrowLeft className="h-4 w-4" /> Alterar a seleção</button>
          <div>
            <h2 className="font-display text-2xl font-bold">3. Resumo antes da validação</h2>
            <p className="text-sm text-muted-foreground">A IA vai realizar estas opções, por esta ordem, e nada mais.</p>
          </div>
          <ol className="space-y-2" data-testid="missions-recap-steps">
            {recap.mission.steps.map((s, i) => (
              <li key={s.key} className="rounded-lg border border-border p-3 flex gap-3">
                <span className="h-6 w-6 rounded-full bg-primary/10 text-primary text-xs font-bold grid place-items-center shrink-0">{i + 1}</span>
                <span><span className="block text-sm font-semibold">{s.name}</span><span className="block text-xs text-muted-foreground">{s.deliverable}</span></span>
              </li>
            ))}
          </ol>
          {recap.warnings?.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-1" data-testid="missions-warnings">
              {recap.warnings.map((w, i) => <p key={i} className="text-xs text-amber-700 flex items-start gap-1.5"><AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {w}</p>)}
            </div>
          )}
          {needsPricing && (
            <div className="grid sm:grid-cols-2 gap-3" data-testid="missions-params">
              <div><p className="text-xs font-semibold mb-1">Margem alvo (%)</p><Input type="number" value={params.margin_pct} onChange={(e) => setParams((p) => ({ ...p, margin_pct: parseFloat(e.target.value) || 0 }))} /></div>
              <div><p className="text-xs font-semibold mb-1">Nome do projeto</p><Input value={params.project_name} onChange={(e) => setParams((p) => ({ ...p, project_name: e.target.value }))} placeholder="Ex.: Moradia Silva" /></div>
              <div><p className="text-xs font-semibold mb-1">Cliente</p><Input value={params.client_name} onChange={(e) => setParams((p) => ({ ...p, client_name: e.target.value }))} /></div>
              <div><p className="text-xs font-semibold mb-1">E-mail do cliente</p><Input value={params.client_email} onChange={(e) => setParams((p) => ({ ...p, client_email: e.target.value }))} /></div>
            </div>
          )}
          <Button onClick={launch} disabled={busy} className="gap-2" data-testid="missions-launch">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Validar e lançar
          </Button>
        </section>
      )}
    </div>
  );
}

function MissionDetail({ run, onClose, onCancel, onDownload, nav }) {
  const steps = (run.result || run.partial_result || run.mission || {}).steps || [];
  const active = run.status === "queued" || run.status === "running";
  return (
    <section className="rounded-xl border border-border bg-card p-5 space-y-4" data-testid="missions-detail">
      <button type="button" onClick={onClose} className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"><ArrowLeft className="h-4 w-4" /> Voltar</button>
      <div className="flex items-center gap-3 flex-wrap">
        <Badge st={RUN[run.status] || RUN.proposed} />
        <h2 className="font-display text-xl font-bold">Programa de {new Date(run.created_at).toLocaleString("pt-PT")}</h2>
        {active && <Button size="sm" variant="ghost" disabled={run.cancel_requested} onClick={() => onCancel(run)} data-testid="missions-cancel">{run.cancel_requested ? "Paragem pedida" : "Parar"}</Button>}
      </div>
      {active && <p className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> A IA está a trabalhar. Esta página atualiza-se sozinha; pode sair dela.</p>}
      {run.error && <p className="text-sm text-destructive">{run.error}</p>}
      <ol className="space-y-3">
        {steps.map((s) => (
          <li key={s.key} className="rounded-lg border border-border p-4" data-testid={`missions-step-${s.key}`}>
            <div className="flex items-center gap-2 flex-wrap">
              <Badge st={STEP[s.status] || STEP.pending} />
              <p className="font-semibold text-sm">{s.name}</p>
            </div>
            {s.error && <p className="text-xs text-destructive mt-2">{s.error}</p>}
            {s.synthese && <p className="text-sm mt-2 whitespace-pre-line flex gap-2"><Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" /><span>{s.synthese}</span></p>}
            {s.status === "done" && <StepResult result={s.result || {}} onDownload={onDownload} nav={nav} />}
          </li>
        ))}
      </ol>
    </section>
  );
}

function StepResult({ result: r, onDownload, nav }) {
  const btn = "h-8";
  if (r.kind === "analysis") return (
    <ul className="mt-2 space-y-1 text-xs">
      {(r.plans || []).map((p) => (
        <li key={p.plan_id} className="flex items-center gap-2 flex-wrap">
          <span className="font-medium">{p.filename}</span>
          {p.error ? <span className="text-destructive">{p.error}</span> : <span className="text-muted-foreground">{p.state} · {p.elements} elemento(s) · {p.missing} em falta</span>}
          {p.link && <button className="text-primary underline" onClick={() => nav(p.link)}>Abrir</button>}
        </li>
      ))}
    </ul>
  );
  if (r.kind === "mep") return (
    <ul className="mt-2 space-y-1 text-xs">
      {(r.studies || []).map((s) => (
        <li key={s.plan_id} className="flex items-center gap-2 flex-wrap">
          <span className="font-medium">{s.filename}</span>
          {s.error ? <span className="text-destructive">{s.error}</span> : (
            <Button size="sm" variant="outline" className={btn} onClick={() => onDownload(s.pdf, "Planos de execução")}><Download className="h-3.5 w-3.5 mr-1" /> PDF</Button>
          )}
        </li>
      ))}
    </ul>
  );
  if (r.kind === "notes") return (
    <ul className="mt-2 space-y-1 text-xs">
      {(r.notes || []).map((n) => (
        <li key={n.note_id || n.plan_id} className="flex items-center gap-2 flex-wrap">
          <span className="font-medium">{n.filename}</span>
          {n.error ? <span className="text-destructive">{n.error}</span> : (
            <>
              <span className="text-muted-foreground">
                {r.lot === "thermique"
                  ? `perdas ${num(n.perdas_w / 1000, 2)} kW · bomba de calor ${num(n.bomba_calor_kw)} kW · ${n.nao_conformes} não conformidade(s)${n.concelho ? "" : " · concelho não indicado"}`
                  : r.lot === "dpe"
                    ? `classe ${n.classe} · Ntc/Nt ${num(n.rnt, 2)} · ${num(n.area_util_m2)} m² · ${n.concelho}`
                    : `implantação ${(n.implantacao_m || []).map((v) => num(v, 2)).join(" × ")} m · ${(n.pisos || []).length} piso(s) · ${n.linteis} lintel(éis)`}
              </span>
              <Button size="sm" variant="outline" className={btn} onClick={() => onDownload(n.pdf, n.title || "Nota")}><Download className="h-3.5 w-3.5 mr-1" /> PDF</Button>
            </>
          )}
        </li>
      ))}
      {r.lot === "dpe" && <li className="text-muted-foreground">Indicativo: não substitui o certificado energético SCE emitido por Perito Qualificado (ADENE).</li>}
    </ul>
  );
  if (r.kind === "files") return (
    <div className="mt-2 flex items-center gap-2 flex-wrap text-xs">
      <span className="text-muted-foreground">{(r.lotes || []).length} especialidade(s) · total {num(r.total, 2)} € sem IVA{(r.lotes || []).some((l) => l.por_orcamentar) ? " · linhas por orçamentar" : ""}</span>
      {(r.files || []).map((f) => (
        <Button key={f.note_id} size="sm" variant="outline" className={btn} onClick={() => onDownload(f.url, f.title, f.ext)}>
          <Download className="h-3.5 w-3.5 mr-1" /> {(f.ext || "").toUpperCase()}
        </Button>
      ))}
    </div>
  );
  if (r.kind === "share") return <ShareResult result={r} />;
  if (r.kind === "planning") return (
    <div className="mt-2 flex items-center gap-2 flex-wrap text-xs">
      <span className="text-muted-foreground">{r.kept_existing ? "Já existia um planeamento: foi mantido tal como estava." : `${r.tasks} tarefa(s)${r.end_date ? ` · fim previsto a ${new Date(r.end_date).toLocaleDateString("pt-PT")}` : ""}`}</span>
      <Button size="sm" variant="outline" className={btn} onClick={() => nav(r.link)}><Pencil className="h-3.5 w-3.5 mr-1" /> Abrir o planeamento</Button>
    </div>
  );
  if (r.kind === "summary") return <p className="mt-2 text-xs text-muted-foreground">{r.total_measures} medição(ões) · {r.total_openings} abertura(s){r.total_rooms !== undefined ? ` · ${r.total_rooms} divisão(ões) (${num(r.total_surface_m2)} m²)` : ""}</p>;
  if (r.kind === "supervision") return <p className="mt-2 text-xs text-muted-foreground">{r.checked} recurso(s) controlado(s) · {r.needs_review} ponto(s) a verificar</p>;
  return (
    <div className="mt-2 flex items-center gap-2 flex-wrap">
      {r.download && <Button size="sm" variant="outline" className={btn} onClick={() => onDownload(r.download, r.kind === "quote" ? "Orcamento" : "Processo")}><Download className="h-3.5 w-3.5 mr-1" /> PDF</Button>}
      {r.edit && <Button size="sm" variant="outline" className={btn} onClick={() => nav(r.edit)}><Pencil className="h-3.5 w-3.5 mr-1" /> Abrir o orçamento</Button>}
    </div>
  );
}


function ShareResult({ result: r }) {
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);
  const activate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(r.activate, { days: 30 });
      setLink(data.url);
      toast.success("Ligação ativada por 30 dias");
    } catch (e) { toast.error(e?.response?.data?.detail || "Ativação impossível"); }
    finally { setBusy(false); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(link); toast.success("Ligação copiada"); } catch { toast.error("Cópia impossível"); }
  };
  return (
    <div className="mt-2 space-y-1 text-xs">
      <p className="text-muted-foreground">{(r.files || []).length} documento(s) pronto(s): {(r.files || []).join(", ")}</p>
      {link ? (
        <div className="flex items-center gap-2 flex-wrap">
          <Input readOnly value={link} className="h-8 text-xs max-w-md" />
          <Button size="sm" variant="outline" className="h-8" onClick={copy}>Copiar</Button>
        </div>
      ) : (
        <Button size="sm" variant="outline" className="h-8" disabled={busy} onClick={activate}>Ativar a ligação (30 dias)</Button>
      )}
      <p className="text-muted-foreground">A ligação não é enviada a ninguém: é o próprio a transmiti-la.</p>
    </div>
  );
}
