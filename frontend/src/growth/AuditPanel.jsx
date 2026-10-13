import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Play, Square, ListPlus } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useApi, err, dt, SEV, STATUS_FR } from "./lib";
import { Empty, ErrorBox } from "./Bits";

export function AuditPanel({ projectId, canEdit }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/audits`, [projectId]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [filter, setFilter] = useState({ severity: "", kind: "" });
  const current = data?.audits?.[0];
  useEffect(() => { if (current && !selected) setSelected(current.audit_id); }, [current, selected]);
  useEffect(() => {
    if (!selected) return;
    let alive = true;
    const load = async () => { try { const r = await api.get(`/growth/audits/${selected}`); if (alive) setDetail(r.data); } catch { /* ignore */ } };
    load();
    const t = setInterval(() => { if (detail?.audit?.status === "running" || detail?.audit?.status === "queued") { load(); reload(); } }, 3000);
    return () => { alive = false; clearInterval(t); };
  }, [selected, detail?.audit?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const start = async () => { try { const r = await api.post(`/growth/projects/${projectId}/audits`, {}); toast.success("Audit lancé"); await reload(); setSelected(r.data.audit_id); } catch (e) { toast.error(err(e)); } };
  const stop = async () => { try { await api.post(`/growth/audits/${selected}/stop`); toast.success("Arrêt demandé"); } catch (e) { toast.error(err(e)); } };
  const setIssue = async (i, status) => { try { await api.put(`/growth/issues/${i.issue_id}`, { status }); setDetail({ ...detail, issues: detail.issues.map((x) => x.issue_id === i.issue_id ? { ...x, status } : x) }); } catch (e) { toast.error(err(e)); } };
  const toAction = async (i) => {
    try { await api.post(`/growth/projects/${projectId}/actions`, { title: `Corriger « ${i.kind} » — ${i.url}`, problem: i.consequence, evidence: i.evidence, url: i.url, impact: { haute: "fort", moyenne: "moyen", basse: "faible" }[i.severity], effort: i.effort, kpi: `Problème « ${i.kind} » absent au prochain audit`, source: "audit", source_ref: i.issue_id }); toast.success("Action créée dans le plan d'action"); }
    catch (e) { toast.error(err(e)); }
  };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const a = detail?.audit;
  const issues = (detail?.issues || []).filter((i) => (!filter.severity || i.severity === filter.severity) && (!filter.kind || i.kind === filter.kind));
  const kinds = [...new Set((detail?.issues || []).map((i) => i.kind))];
  return <div className="space-y-4" data-testid="growth-audit">
    <div className="flex flex-wrap items-center gap-2">
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={selected || ""} onChange={(e) => { setSelected(e.target.value); setDetail(null); }} data-testid="growth-audit-select">
        {data.audits.map((x) => <option key={x.audit_id} value={x.audit_id}>{dt(x.created_at)} — {STATUS_FR[x.status] || x.status} · {x.pages_crawled} p. · {x.issues_count ?? "…"} pb</option>)}
        {data.audits.length === 0 && <option value="">Aucun audit</option>}
      </select>
      {canEdit && <Button size="sm" onClick={start} disabled={a?.status === "running" || a?.status === "queued"} data-testid="growth-audit-start"><Play className="h-4 w-4" /> Lancer un audit</Button>}
      {canEdit && (a?.status === "running" || a?.status === "queued") && <Button size="sm" variant="outline" onClick={stop} data-testid="growth-audit-stop"><Square className="h-4 w-4" /> Arrêter</Button>}
    </div>
    {a && <div className="surface p-3 text-sm space-y-1" data-testid="growth-audit-summary">
      <div className="flex flex-wrap gap-3 items-center"><Badge variant="outline" className="rounded-sm">{STATUS_FR[a.status] || a.status}</Badge>
        {(a.status === "running" || a.status === "queued") && <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden min-w-[120px]"><div className="h-full bg-primary transition-all" style={{ width: `${a.progress || 0}%` }} /></div>}
        <span className="num">{a.pages_crawled} pages explorées / {a.max_pages} max</span>{a.issues_count != null && <span className="num">{a.issues_count} problèmes</span>}</div>
      {a.facts && <p className="text-xs text-muted-foreground">robots.txt : {a.facts.robots_txt} · sitemaps : {a.facts.sitemaps?.length || 0} ({a.facts.sitemap_urls} URL) · {a.note}</p>}
      {a.error && <p className="text-xs text-red-700">{a.error}</p>}{a.note && a.status === "interrupted" && <p className="text-xs text-amber-700">{a.note}</p>}
    </div>}
    {detail && <>
      <div className="flex flex-wrap gap-2 items-center text-xs">
        <select className="h-8 rounded-md border bg-background px-2" value={filter.severity} onChange={(e) => setFilter({ ...filter, severity: e.target.value })} data-testid="growth-issue-filter-severity"><option value="">Toutes gravités</option><option value="haute">haute</option><option value="moyenne">moyenne</option><option value="basse">basse</option></select>
        <select className="h-8 rounded-md border bg-background px-2" value={filter.kind} onChange={(e) => setFilter({ ...filter, kind: e.target.value })} data-testid="growth-issue-filter-kind"><option value="">Tous types</option>{kinds.map((k) => <option key={k} value={k}>{k}</option>)}</select>
        <span className="text-muted-foreground">{issues.length} problème(s) · « fait » = mesuré, « hypothèse » = à confirmer</span>
      </div>
      {issues.length === 0 && <Empty testid="growth-issues-empty">Aucun problème pour ce filtre.</Empty>}
      <ul className="divide-y border rounded-md">
        {issues.slice(0, 300).map((i) => <li key={i.issue_id} className={`px-3 py-2 text-sm space-y-1 ${i.status !== "open" ? "opacity-50" : ""}`} data-testid={`growth-issue-${i.issue_id}`}>
          <div className="flex flex-wrap items-center gap-2"><Badge className={`rounded-sm border-0 ${SEV[i.severity]}`}>{i.severity}</Badge><span className="font-medium">{i.kind}</span>
            <Badge variant="outline" className="rounded-sm text-[10px]">{i.is_fact ? "fait" : "hypothèse"}</Badge><span className="text-[11px] text-muted-foreground">effort {i.effort} · {dt(i.observed_at)}</span>
            <a className="text-[11px] underline truncate max-w-[360px]" href={i.url} target="_blank" rel="noreferrer">{i.url}</a></div>
          <p className="text-xs"><strong>Preuve :</strong> {i.evidence}</p>
          <p className="text-xs text-muted-foreground"><strong>Conséquence :</strong> {i.consequence} · <strong>Correction :</strong> {i.fix}</p>
          {i.status === "fixing" && <p className="text-xs text-primary" data-testid={`growth-issue-fixing-${i.issue_id}`}>Correction automatique appliquée : {i.fix_applied} — confirmée au prochain ré-audit.</p>}
          {i.fix_active && <p className="text-xs text-amber-700" data-testid={`growth-issue-reappeared-${i.issue_id}`}>{i.fix_note}</p>}
          {canEdit && i.status === "open" && <div className="flex gap-2"><Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => toAction(i)} data-testid={`growth-issue-action-${i.issue_id}`}><ListPlus className="h-3.5 w-3.5" /> Créer une action</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setIssue(i, "fixed")}>Corrigé</Button><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setIssue(i, "ignored")}>Ignorer</Button></div>}
        </li>)}
      </ul>
      <details className="text-xs"><summary className="cursor-pointer text-muted-foreground">{detail.pages.length} pages explorées</summary>
        <table className="w-full mt-2"><tbody>{detail.pages.map((p) => <tr key={p.url} className="border-t"><td className="py-1 pr-2 truncate max-w-[320px]"><a className="underline" href={p.url} target="_blank" rel="noreferrer">{p.url}</a></td><td className="num pr-2">{p.status_code ?? "—"}</td><td className="truncate max-w-[280px]">{p.title || "—"}</td><td className="num pr-2">{p.word_count ?? "—"} mots</td><td className="num">{p.load_ms ?? "—"} ms</td></tr>)}</tbody></table>
      </details>
    </>}
    {!current && <Empty testid="growth-audit-empty">Aucun audit pour ce projet. Lancez le premier pour explorer les pages publiques (robots.txt respecté, espaces privés exclus).</Empty>}
  </div>;
}
