import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Square, Plus, Eye, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { useApi, err, dt, usd, STATUS_FR } from "./lib";
import { Metric, Empty, ErrorBox } from "./Bits";

const PROVIDERS = [["perplexity", "Perplexity Agent API (web)"], ["openai", "OpenAI (API, sem web)"], ["gemini", "Gemini (API, sem web)"], ["anthropic", "Claude (API, sem web)"]];

function NewCampaign({ projectId, onCreated, providers }) {
  const { data } = useApi(`/growth/projects/${projectId}/questions`, [projectId]);
  const [sel, setSel] = useState([]);
  const [prov, setProv] = useState({ perplexity: true, openai: false, gemini: false, anthropic: false });
  const [reps, setReps] = useState(2);
  const [name, setName] = useState("Campanha piloto");
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) setSel(data.questions.filter((q) => q.active && !q.branded).slice(0, 10).map((q) => q.question_id)); }, [data]);
  const create = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/growth/projects/${projectId}/campaigns`, { name, question_ids: sel, providers: Object.entries(prov).filter(([, v]) => v).map(([p]) => ({ provider: p })), repetitions: reps });
      toast.success(`Campanha criada — custo estimado ${usd(r.data.estimated_cost_usd)} pour ${r.data.planned_tests} tests`); onCreated(r.data);
    } catch (e) { toast.error(err(e)); } finally { setBusy(false); }
  };
  if (!data) return null;
  const intents = [...new Set(data.questions.map((q) => q.intent))];
  return <div className="surface p-3 space-y-3 text-sm" data-testid="growth-campaign-form">
    <div className="flex flex-wrap gap-2 items-center"><input className="h-9 rounded-md border bg-background px-2" value={name} onChange={(e) => setName(e.target.value)} data-testid="growth-campaign-name" />
      <label className="flex items-center gap-1">Repetições <input type="number" min={1} max={5} className="h-9 w-16 rounded-md border bg-background px-2 num" value={reps} onChange={(e) => setReps(Number(e.target.value))} data-testid="growth-campaign-reps" /></label></div>
    <div className="flex flex-wrap gap-3">{PROVIDERS.map(([k, l]) => <label key={k} className={`flex items-center gap-1 ${!providers?.[k]?.configured ? "opacity-50" : ""}`}><input type="checkbox" checked={!!prov[k]} disabled={!providers?.[k]?.configured} onChange={(e) => setProv({ ...prov, [k]: e.target.checked })} data-testid={`growth-campaign-provider-${k}`} />{l}{!providers?.[k]?.configured && " — não configurado"}</label>)}</div>
    <div className="space-y-2 max-h-64 overflow-y-auto border rounded-md p-2">
      {intents.map((it) => <div key={it}><p className="overline">{it}</p>{data.questions.filter((q) => q.intent === it && q.active).map((q) => <label key={q.question_id} className="flex items-start gap-2 py-0.5"><input type="checkbox" checked={sel.includes(q.question_id)} onChange={(e) => setSel(e.target.checked ? [...sel, q.question_id] : sel.filter((x) => x !== q.question_id))} data-testid={`growth-campaign-q-${q.question_id}`} /><span>{q.text}{q.branded && <Badge variant="outline" className="ml-1 rounded-sm text-[10px]">marque</Badge>}</span></label>)}</div>)}
    </div>
    <p className="text-xs text-muted-foreground">{sel.length} question(s) × {Object.values(prov).filter(Boolean).length} fornecedor(es) × {reps} = <strong className="num">{sel.length * Object.values(prov).filter(Boolean).length * reps} tests</strong>. As perguntas «marca» são testadas separadamente das perguntas sem marca; nenhum contexto ConstruPilot é injetado.</p>
    <Button size="sm" onClick={create} disabled={busy || !sel.length || !Object.values(prov).some(Boolean)} data-testid="growth-campaign-create"><Plus className="h-4 w-4" /> Estimar e criar</Button>
  </div>;
}

function TestDialog({ testId, onClose, canEdit }) {
  const [t, setT] = useState(null);
  useEffect(() => { if (testId) api.get(`/growth/tests/${testId}`).then((r) => setT(r.data)).catch(() => toast.error("Resposta não encontrada")); }, [testId]);
  const flag = async (m) => { try { await api.put(`/growth/tests/${testId}/mentions/${m.brand_id}`, { false_positive: !m.false_positive }); setT({ ...t, mentions: t.mentions.map((x) => x.brand_id === m.brand_id ? { ...x, false_positive: !m.false_positive } : x) }); } catch (e) { toast.error(err(e)); } };
  return <Dialog open={!!testId} onOpenChange={(o) => !o && onClose()}><DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto" data-testid="growth-test-dialog">
    <DialogTitle className="text-base">Resposta de origem</DialogTitle>
    {t && <>
      <DialogDescription className="text-xs">{t.question_text} — {t.provider} · {t.model} · resp. {t.repetition} · {dt(t.executed_at)} · recherche web : {t.web_search ? "oui" : "non"} · geolocalização aplicada: {t.geo_applied} · {t.latency_ms} ms · {usd(t.cost_usd)}{t.cost_estimated ? " (estimado)" : ""} · protocolo {t.protocol_version}</DialogDescription>
      <div className="space-y-2 text-sm">
        <p className="overline">Marcas detetadas</p>
        {(t.mentions || []).length === 0 && <p className="text-xs text-muted-foreground">Nenhuma marca acompanhada detetada.</p>}
        {(t.mentions || []).map((m) => <div key={m.brand_id} className={`border rounded-md p-2 text-xs ${m.false_positive ? "opacity-50" : ""}`} data-testid={`growth-mention-${m.brand_id}`}>
          <div className="flex flex-wrap gap-2 items-center"><strong>{m.name}</strong>{m.mention && <Badge variant="outline" className="rounded-sm">mention</Badge>}{m.domain_citation && <Badge variant="outline" className="rounded-sm">domínio citado</Badge>}{m.recommendation && <Badge className="rounded-sm">recomendação explícita</Badge>}<span>rang : {m.rank ?? "não aplicável"}</span>
            {canEdit && <button className="underline ml-auto" onClick={() => flag(m)} data-testid={`growth-mention-flag-${m.brand_id}`}>{m.false_positive ? "Repor" : "Faux positif"}</button>}</div>
          <p className="mt-1 italic">{m.evidence}</p></div>)}
        <p className="overline">Resposta completa</p>
        <pre className="whitespace-pre-wrap text-xs bg-muted/40 rounded-md p-3 font-sans" data-testid="growth-test-response">{t.response_text || t.error || t.exclusion_reason}</pre>
        {(t.citations || []).length > 0 && <><p className="overline">Ligações citadas ({t.citations.length})</p><ul className="text-xs space-y-0.5">{t.citations.map((c, i) => <li key={i}><a className="underline" href={c.url} target="_blank" rel="noreferrer">{c.title || c.url}</a> <span className="text-muted-foreground">({c.kind})</span></li>)}</ul></>}
      </div></>}
  </DialogContent></Dialog>;
}

export function VisibilityPanel({ projectId, canEdit, providers }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/campaigns`, [projectId]);
  const [selected, setSelected] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [tests, setTests] = useState(null);
  const [showNew, setShowNew] = useState(false);
  const [openTest, setOpenTest] = useState(null);
  const [qFilter, setQFilter] = useState("");
  useEffect(() => { if (data?.campaigns?.length && !selected) setSelected(data.campaigns[0].campaign_id); }, [data, selected]);
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    const load = async () => { try { const [m, t] = await Promise.all([api.get(`/growth/campaigns/${selected}`), api.get(`/growth/campaigns/${selected}/tests`)]); if (alive) { setMetrics(m.data); setTests(t.data.tests); } } catch { /* ignore */ } };
    load();
    const iv = setInterval(() => { if (metrics?.campaign?.status === "running") { load(); reload(); } }, 4000);
    return () => { alive = false; clearInterval(iv); };
  }, [selected, metrics?.campaign?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async () => { try { await api.post(`/growth/campaigns/${selected}/run`); toast.success("Campanha lançada"); setMetrics({ ...metrics, campaign: { ...metrics.campaign, status: "running" } }); } catch (e) { toast.error(err(e)); } };
  const stop = async () => { try { await api.post(`/growth/campaigns/${selected}/stop`); toast.success("Paragem pedida"); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const c = metrics?.campaign;
  const byQ = {};
  (tests || []).filter((t) => !qFilter || t.question_text.toLowerCase().includes(qFilter.toLowerCase())).forEach((t) => { (byQ[t.question_text] = byQ[t.question_text] || []).push(t); });
  return <div className="space-y-4" data-testid="growth-visibility">
    <div className="flex flex-wrap items-center gap-2">
      <select className="h-9 rounded-md border bg-background px-2 text-sm max-w-[360px]" value={selected || ""} onChange={(e) => { setSelected(e.target.value); setMetrics(null); setTests(null); }} data-testid="growth-campaign-select">
        {data.campaigns.map((x) => <option key={x.campaign_id} value={x.campaign_id}>{x.name} — {dt(x.created_at)} · {STATUS_FR[x.status] || x.status}</option>)}{data.campaigns.length === 0 && <option value="">Nenhuma campanha</option>}
      </select>
      {canEdit && <Button size="sm" variant="outline" onClick={() => setShowNew(!showNew)} data-testid="growth-campaign-new"><Plus className="h-4 w-4" /> Nova campanha</Button>}
      {canEdit && c && ["estimated", "interrupted", "stopped", "failed"].includes(c.status) && <Button size="sm" onClick={run} data-testid="growth-campaign-run">{c.status === "estimated" ? <Play className="h-4 w-4" /> : <RotateCcw className="h-4 w-4" />} {c.status === "estimated" ? "Lançar" : "Retomar"} ({c.planned_tests} testes, ≈ {usd(c.estimated_cost_usd)})</Button>}
      {canEdit && c?.status === "running" && <Button size="sm" variant="outline" onClick={stop} data-testid="growth-campaign-stop"><Square className="h-4 w-4" /> Parar</Button>}
    </div>
    {showNew && <NewCampaign projectId={projectId} providers={providers} onCreated={(x) => { setShowNew(false); reload(); setSelected(x.campaign_id); setMetrics(null); }} />}
    {c && <div className="surface p-3 text-xs space-y-1" data-testid="growth-campaign-summary">
      <div className="flex flex-wrap gap-3 items-center"><Badge variant="outline" className="rounded-sm">{STATUS_FR[c.status] || c.status}</Badge>
        {c.status === "running" && <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden min-w-[120px]"><div className="h-full bg-primary transition-all" style={{ width: `${c.progress || 0}%` }} /></div>}
        <span className="num">{c.done_tests}/{c.planned_tests} tests</span><span className="num">custo estimado {usd(c.estimated_cost_usd)} · real {usd(c.actual_cost_usd)}</span><span>{c.providers.map((p) => p.provider).join(", ")} · ×{c.repetitions} · protocolo {c.protocol_version}</span></div>
      <p className="text-muted-foreground">{c.budget_note}{c.note ? ` — ${c.note}` : ""}{c.missing_connections?.length ? ` — ligações em falta: ${c.missing_connections.join(", ")}` : ""}</p>
      <p className="text-muted-foreground">{metrics.caveat}</p>
    </div>}
    {metrics && metrics.valid > 0 && <div className="flex flex-wrap gap-3">
      <Metric label="Taxa de menção (sem marca)" m={metrics.mention_rate} testid="growth-metric-mention" /><Metric label="Taxa de menção (todas)" m={metrics.mention_rate_all} /><Metric label="Taxa de citação" m={metrics.citation_rate} testid="growth-metric-citation" />
      <Metric label="Quota de menções" m={metrics.share_of_mentions} testid="growth-metric-share" /><Metric label="Cobertura" m={metrics.coverage} testid="growth-metric-coverage" />
    </div>}
    {metrics && metrics.valid === 0 && c && c.status !== "running" && c.status !== "estimated" && <Empty testid="growth-no-valid">Nenhum teste válido: dados indisponíveis (não «0 %»). {metrics.excluded_count} teste(s) excluído(s) ou com erro — ver abaixo.</Empty>}
    {metrics?.by_brand?.length > 0 && <div className="surface p-3 text-xs" data-testid="growth-by-brand"><p className="overline mb-1">Marcas acompanhadas — âmbito: {metrics.share_of_mentions.brands_scope.join(", ")}</p>
      <table className="w-full"><thead><tr className="text-left text-muted-foreground"><th>Marca</th><th className="num">Respostas que a mencionam</th><th className="num">Domínio citado</th><th className="num">Recomendações</th><th className="num">Posição média</th></tr></thead>
        <tbody>{metrics.by_brand.map((b) => <tr key={b.name} className={`border-t ${b.is_self ? "font-semibold" : ""}`}><td>{b.name}</td><td className="num">{b.responses_mentioning}</td><td className="num">{b.responses_citing}</td><td className="num">{b.recommendations}</td><td className="num">{b.avg_rank ?? "n/a"}</td></tr>)}</tbody></table></div>}
    {metrics?.by_dimension && <div className="flex flex-wrap gap-3 text-xs">{Object.entries(metrics.by_dimension).map(([dim, vals]) => <div key={dim} className="surface p-2 min-w-[200px]"><p className="overline">Par {dim}</p>{Object.entries(vals).map(([k, v]) => <p key={k} className="flex justify-between gap-3"><span>{k}</span><span className="num">{v.display} <span className="text-muted-foreground">({v.self}/{v.valid})</span></span></p>)}</div>)}</div>}
    {tests && <div className="space-y-2" data-testid="growth-by-question">
      <div className="flex items-center gap-2"><p className="overline">Marcas por pergunta</p><input className="h-8 rounded-md border bg-background px-2 text-xs" placeholder="Filtrar…" value={qFilter} onChange={(e) => setQFilter(e.target.value)} /></div>
      {Object.entries(byQ).map(([q, ts]) => <div key={q} className="border rounded-md p-2 text-xs">
        <div className="font-medium">{q} {ts[0].branded && <Badge variant="outline" className="rounded-sm text-[10px]">marque</Badge>}</div>
        <div className="flex flex-wrap gap-2 mt-1">{ts.map((t) => <button key={t.test_id} onClick={() => setOpenTest(t.test_id)} className={`border rounded-md px-2 py-1 text-left hover:border-primary ${t.status !== "completed" ? "opacity-60" : ""}`} data-testid={`growth-test-${t.test_id}`}>
          <span className="font-medium">{t.provider}</span> · r{t.repetition} · {t.status === "completed" ? (t.self_mentioned ? <span className="text-emerald-700">ConstruPilot mencionado</span> : <span className="text-muted-foreground">absent</span>) : <span className="text-amber-700">{t.status} : {t.exclusion_reason || t.error}</span>}
          {t.status === "completed" && <span className="text-muted-foreground"> · {(t.mentions || []).filter((m) => !m.is_self && m.mention).map((m) => m.name).join(", ") || "nenhuma outra marca"}</span>} <Eye className="inline h-3 w-3 ml-1" /></button>)}</div>
      </div>)}
    </div>}
    {metrics?.excluded?.length > 0 && <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">{metrics.excluded.length} teste(s) excluídos / com erro (motivos)</summary><ul className="mt-1 space-y-0.5">{metrics.excluded.map((e) => <li key={e.test_id}>{e.provider} — {e.question} : <span className="text-amber-700">{e.status} · {e.reason}</span></li>)}</ul></details>}
    {data.campaigns.length === 0 && !showNew && <Empty testid="growth-campaigns-empty">Nenhuma campanha. Crie uma campanha piloto (10 perguntas, 1 fornecedor, 2 repetições): o custo é estimado antes do lançamento.</Empty>}
    <TestDialog testId={openTest} onClose={() => setOpenTest(null)} canEdit={canEdit} />
  </div>;
}
