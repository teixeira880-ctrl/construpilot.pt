import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, RefreshCw, Link2, Bot, Send } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err, dt, usd } from "./lib";
import { Empty, ErrorBox } from "./Bits";
import { AutoFixCard } from "./AutoFixCard";

export function LinksPanel({ projectId, canEdit }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/links`, [projectId]);
  const [d, setD] = useState({ kind: "opportunity", source_url: "", target_url: "", context: "", category: "média da construção", sponsored: false, status: "to_contact", proposal: "" });
  const add = async () => { try { await api.post(`/growth/projects/${projectId}/links`, d); setD({ ...d, source_url: "", context: "", proposal: "" }); reload(); } catch (e) { toast.error(err(e)); } };
  const patch = async (l, ch) => { try { await api.put(`/growth/links/${l.link_id}`, { ...l, ...ch }); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  return <div className="space-y-4" data-testid="growth-links">
    <p className="text-sm text-muted-foreground">Backlinks observados, menções sem ligação e oportunidades editoriais (média da construção, diretórios, parceiros). <strong>Nenhuma mensagem é enviada automaticamente</strong> : as propostas são preparadas aqui e enviadas por si. Ligações patrocinadas a identificar; redes de ligações artificiais excluídas.</p>
    {canEdit && <div className="surface p-3 grid sm:grid-cols-3 gap-2 text-sm" data-testid="growth-link-form">
      <select className="h-9 rounded-md border bg-background px-2" value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value })}><option value="opportunity">oportunidade</option><option value="backlink">backlink observado</option><option value="mention_no_link">menção sem ligação</option></select>
      <Input placeholder="URL source" value={d.source_url} onChange={(e) => setD({ ...d, source_url: e.target.value })} data-testid="growth-link-source" /><Input placeholder="Página alvo ConstruPilot" value={d.target_url} onChange={(e) => setD({ ...d, target_url: e.target.value })} />
      <Input placeholder="Categoria (média da construção, diretório, parceiro…)" value={d.category} onChange={(e) => setD({ ...d, category: e.target.value })} /><Input placeholder="Contexto" value={d.context} onChange={(e) => setD({ ...d, context: e.target.value })} />
      <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={d.sponsored} onChange={(e) => setD({ ...d, sponsored: e.target.checked })} /> ligação patrocinada</label>
      <textarea className="sm:col-span-3 rounded-md border bg-background p-2 text-xs" rows={2} placeholder="Proposta de parceria / mensagem personalizável (transparência sobre a afiliação ao ConstruPilot)" value={d.proposal} onChange={(e) => setD({ ...d, proposal: e.target.value })} />
      <Button size="sm" onClick={add} disabled={!d.source_url.trim()} data-testid="growth-link-add"><Plus className="h-4 w-4" /> Adicionar</Button></div>}
    {data.links.length === 0 && <Empty testid="growth-links-empty">Nenhuma ligação nem oportunidade registada.</Empty>}
    <ul className="divide-y border rounded-md">{data.links.map((l) => <li key={l.link_id} className="px-3 py-2 text-sm space-y-1" data-testid={`growth-link-${l.link_id}`}>
      <div className="flex flex-wrap gap-2 items-center"><Badge variant="outline" className="rounded-sm">{l.kind}</Badge><a className="underline truncate max-w-[320px]" href={l.source_url} target="_blank" rel="noreferrer">{l.source_url}</a>{l.sponsored && <Badge className="rounded-sm bg-amber-500/15 text-amber-700 border-0">patrocinado</Badge>}<span className="text-xs text-muted-foreground">{l.category} · verificado {dt(l.verified_at)}</span>
        {canEdit && <select className="h-7 rounded-md border bg-background px-1 text-xs ml-auto" value={l.status} onChange={(e) => patch(l, { status: e.target.value })}>{["observed", "to_contact", "contacted", "obtained", "declined"].map((s) => <option key={s} value={s}>{s}</option>)}</select>}
        {canEdit && <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={async () => { await api.delete(`/growth/links/${l.link_id}`); reload(); }}><Trash2 className="h-3.5 w-3.5" /></Button>}</div>
      <p className="text-xs text-muted-foreground">{l.context}{l.target_url && <> → <Link2 className="inline h-3 w-3" /> {l.target_url}</>}</p>{l.proposal && <p className="text-xs italic">{l.proposal}</p>}
    </li>)}</ul>
  </div>;
}

export function BudgetPanel({ projectId, canEdit, project, onSaved }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/costs`, [projectId]);
  const [b, setB] = useState(project?.settings?.budgets || { daily_usd: 0, monthly_usd: 0 });
  const [ap, setAp] = useState({ autopilot_enabled: project?.settings?.autopilot_enabled ?? true, articles_per_week: project?.settings?.articles_per_week ?? 3, seo_override_mode: project?.settings?.seo_override_mode || "review" });
  const save = async () => { try { await api.put(`/growth/projects/${projectId}/settings`, { settings: { budgets: { daily_usd: Number(b.daily_usd) || 0, monthly_usd: Number(b.monthly_usd) || 0 }, autopilot_enabled: !!ap.autopilot_enabled, articles_per_week: Math.max(0, Number(ap.articles_per_week) || 0), seo_override_mode: ap.seo_override_mode } }); toast.success("Tetos e piloto automático guardados"); onSaved?.(); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const pct = (v, cap) => (cap ? Math.min(100, Math.round(v * 100 / cap)) : null);
  return <div className="space-y-4" data-testid="growth-budget">
    <div className="grid sm:grid-cols-2 gap-3">
      {[["Hoje", data.spent_day, data.budgets?.daily_usd], ["Este mês", data.spent_month, data.budgets?.monthly_usd]].map(([l, v, cap]) => <div key={l} className="surface p-3"><p className="overline">{l}</p><p className="num text-xl font-bold">{usd(v)} <span className="text-sm font-normal text-muted-foreground">/ {cap ? `${cap} $` : "sem teto"}</span></p>
        {cap ? <div className="h-2 bg-muted rounded-full overflow-hidden mt-1"><div className={`h-full ${pct(v, cap) >= 100 ? "bg-red-500" : pct(v, cap) >= 80 ? "bg-amber-500" : "bg-primary"}`} style={{ width: `${pct(v, cap)}%` }} /></div> : null}</div>)}
    </div>
    {canEdit && <div className="surface p-3 flex flex-wrap gap-2 items-end text-sm" data-testid="growth-budget-form">
      <label className="text-xs">Plafond journalier ($)<Input type="number" step="0.5" className="num" value={b.daily_usd} onChange={(e) => setB({ ...b, daily_usd: e.target.value })} data-testid="growth-budget-daily" /></label>
      <label className="text-xs">Teto mensal ($)<Input type="number" step="1" className="num" value={b.monthly_usd} onChange={(e) => setB({ ...b, monthly_usd: e.target.value })} data-testid="growth-budget-monthly" /></label>
      <label className="text-xs">Artigos automáticos / semana<Input type="number" step="1" min="0" className="num w-24" value={ap.articles_per_week} onChange={(e) => setAp({ ...ap, articles_per_week: e.target.value })} data-testid="growth-autopilot-per-week" /></label>
      <label className="text-xs">Correções SEO<select className="block h-9 rounded-md border bg-background px-2" value={ap.seo_override_mode} onChange={(e) => setAp({ ...ap, seo_override_mode: e.target.value })} data-testid="growth-autopilot-override-mode"><option value="review">a aprovar</option><option value="auto">aplicadas automaticamente</option></select></label>
      <label className="text-xs flex items-center gap-1 h-9"><input type="checkbox" checked={!!ap.autopilot_enabled} onChange={(e) => setAp({ ...ap, autopilot_enabled: e.target.checked })} data-testid="growth-autopilot-enabled" /> Auto-pilote nocturne</label>
      <Button size="sm" onClick={save} data-testid="growth-budget-save">Guardar</Button><span className="text-xs text-muted-foreground">No teto, as campanhas param («teto atingido»); o orçamento é reservado antes de cada chamada.</span></div>}
    <div className="surface p-3 text-xs"><p className="overline mb-1">Por fornecedor e mês</p><table className="w-full"><thead><tr className="text-left text-muted-foreground"><th>Fornecedor</th><th>Mês</th><th>Tipo</th><th className="num">Chamadas</th><th className="num">USD</th></tr></thead>
      <tbody>{data.by_provider.map((r, i) => <tr key={i} className="border-t"><td>{r.provider}</td><td className="num">{r.month}</td><td>{r.estimated ? <span className="text-amber-700">estimado</span> : <span className="text-emerald-700">real</span>}</td><td className="num">{r.calls}</td><td className="num">{usd(r.usd)}</td></tr>)}{data.by_provider.length === 0 && <tr><td colSpan={5} className="py-2 text-muted-foreground">Nenhuma despesa.</td></tr>}</tbody></table>
      <p className="text-muted-foreground mt-2">{data.note}</p></div>
  </div>;
}

export function AssistantPanel({ projectId, canEdit = false, isAdmin = false }) {
  const [q, setQ] = useState("");
  const [log, setLog] = useState([]);
  const [busy, setBusy] = useState(false);
  const ask = async (text) => {
    const question = text || q; if (!question.trim()) return;
    setBusy(true); setQ("");
    try { const r = await api.post("/growth/assistant", { project_id: projectId, question }); setLog([{ question, ...r.data }, ...log]); }
    catch (e) { toast.error(err(e)); } finally { setBusy(false); }
  };
  const SUGG = ["Quais são as cinco ações prioritárias?", "Porque estamos ausentes na pergunta mais frequente?", "Prepara um artigo para Portugal", "Resume a última auditoria"];
  return <div className="space-y-3" data-testid="growth-assistant">
    <AutoFixCard projectId={projectId} canEdit={canEdit} isAdmin={isAdmin} />
    <p className="text-sm text-muted-foreground flex items-center gap-2"><Bot className="h-4 w-4" /> O assistente consulta os dados do projeto (auditoria, correções automáticas, testes, ações, Search Console), distingue observações e hipóteses e depois explica o que foi corrigido automaticamente e o que falta fazer no código.</p>
    <div className="flex flex-wrap gap-1">{SUGG.map((s) => <button key={s} className="text-xs border rounded-full px-2 py-1 hover:border-primary" onClick={() => ask(s)} disabled={busy} data-testid="growth-assistant-suggestion">{s}</button>)}</div>
    <div className="flex gap-2"><Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} placeholder="A sua pergunta…" data-testid="growth-assistant-input" /><Button onClick={() => ask()} disabled={busy || !q.trim()} data-testid="growth-assistant-send">{busy ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</Button></div>
    {log.map((l, i) => <div key={i} className="surface p-3 text-sm space-y-1" data-testid="growth-assistant-answer"><p className="font-medium">{l.question}</p><pre className="whitespace-pre-wrap font-sans text-xs">{l.answer}</pre><p className="text-[10px] text-muted-foreground">Baseado em: {l.grounded_on.tests} testes · {l.grounded_on.issues} problemas · {l.grounded_on.actions} actions · audit {l.grounded_on.has_audit ? "oui" : "non"} · campanha {l.grounded_on.has_campaign ? "oui" : "non"}</p></div>)}
  </div>;
}
