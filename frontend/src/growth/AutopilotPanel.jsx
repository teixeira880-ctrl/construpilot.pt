import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Bot, Play, Check, X, RefreshCw, FileSearch, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useApi, err, dt } from "./lib";
import { Empty, ErrorBox } from "./Bits";

function Stat({ label, value, testid, tone = "" }) {
  return <div className="surface p-3" data-testid={testid}><p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p><p className={`text-xl font-bold num ${tone}`}>{value}</p></div>;
}

function OverrideRow({ o, canEdit, onDecide }) {
  const [t, setT] = useState(o.title);
  const [d, setD] = useState(o.description);
  const pending = o.status === "proposed";
  return <li className="px-3 py-2 text-sm space-y-1" data-testid={`growth-override-${o.override_id}`}>
    <div className="flex flex-wrap items-center gap-2">
      <Badge className={`rounded-sm border-0 ${o.status === "approved" ? "bg-emerald-500/15 text-emerald-700" : o.status === "rejected" ? "bg-muted" : "bg-amber-500/15 text-amber-700"}`}>{o.status === "approved" ? "appliquée" : o.status === "rejected" ? "refusée" : "à approuver"}</Badge>
      <a className="underline text-xs truncate flex-1 min-w-[160px]" href={o.url} target="_blank" rel="noreferrer">{o.path}</a>
      <span className="text-[11px] text-muted-foreground">{(o.issue_kinds || []).join(", ")}</span>
    </div>
    <p className="text-[11px] text-muted-foreground truncate">Actuel : {o.current_title || "(vide)"} — {o.current_description || "(vide)"}</p>
    {pending && canEdit ? <>
      <Input value={t} onChange={(e) => setT(e.target.value)} maxLength={60} className="h-8 text-xs" data-testid={`growth-override-title-${o.override_id}`} />
      <Input value={d} onChange={(e) => setD(e.target.value)} maxLength={160} className="h-8 text-xs" />
      <div className="flex gap-2 items-center text-[11px] text-muted-foreground"><span className="num">{t.length}/60 · {d.length}/160</span>
        <Button size="sm" className="h-7 text-xs" onClick={() => onDecide(o, "approved", t, d)} data-testid={`growth-override-approve-${o.override_id}`}><Check className="h-3.5 w-3.5" /> Approuver</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => onDecide(o, "rejected")} data-testid={`growth-override-reject-${o.override_id}`}><X className="h-3.5 w-3.5" /> Refuser</Button></div>
    </> : <p className="text-xs"><strong>{o.title}</strong> — {o.description}</p>}
  </li>;
}

export function AutopilotPanel({ projectId, canEdit, onGo }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/autopilot`, [projectId]);
  const ov = useApi(`/growth/projects/${projectId}/seo-overrides`, [projectId]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (!data?.running) return; const id = setInterval(() => { reload(); ov.reload(); }, 8000); return () => clearInterval(id); }, [data?.running]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (resume_only = false) => { setBusy(true); try { await api.post(`/growth/projects/${projectId}/autopilot/run`, { resume_only }); toast.success("Cycle auto-pilote lancé — les résultats arrivent au fil de l'eau"); setTimeout(reload, 1500); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  const decide = async (o, status, title = "", description = "") => { try { await api.put(`/growth/seo-overrides/${o.override_id}`, { status, title, description }); toast.success(status === "approved" ? "Correction appliquée sur le site" : "Proposition refusée"); ov.reload(); reload(); } catch (e) { toast.error(err(e)); } };
  const approveAll = async () => { try { const r = await api.post(`/growth/projects/${projectId}/seo-overrides/approve-all`); toast.success(`${r.data.approved} correction(s) appliquée(s)`); ov.reload(); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const last = data.runs[0];
  const pendingOv = (ov.data?.overrides || []).filter((o) => o.status === "proposed");
  const doneOv = (ov.data?.overrides || []).filter((o) => o.status !== "proposed");
  return <div className="space-y-5" data-testid="growth-autopilot">
    <div className="flex flex-wrap items-start gap-3">
      <p className="text-sm text-muted-foreground flex-1 min-w-[260px]"><Bot className="inline h-4 w-4 mr-1" />Chaque nuit (06:00 UTC, après l'audit) : clôture des problèmes disparus, propositions de corrections title/description, création et rédaction d'articles (recherche de sources vérifiées → brief → rédaction → contrôles). Rien n'est publié sans votre approbation ; le plafond budget mensuel est respecté.</p>
      {canEdit && <div className="flex gap-2">
        <Button size="sm" onClick={() => run(false)} disabled={busy || data.running} data-testid="growth-autopilot-run">{data.running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {data.running ? "Cycle en cours…" : "Lancer un cycle maintenant"}</Button>
        {data.in_progress > 0 && <Button size="sm" variant="outline" onClick={() => run(true)} disabled={busy || data.running} data-testid="growth-autopilot-resume"><RefreshCw className="h-4 w-4" /> Reprendre {data.in_progress} en cours</Button>}
      </div>}
    </div>
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
      <Stat label="Articles à relire" value={data.pending_review} testid="growth-autopilot-review" tone={data.pending_review ? "text-amber-700" : ""} />
      <Stat label="Corrections SEO à approuver" value={data.pending_overrides} testid="growth-autopilot-overrides" tone={data.pending_overrides ? "text-amber-700" : ""} />
      <Stat label="Quota restant (semaine)" value={`${data.quota_left_this_week}/${data.settings.articles_per_week}`} testid="growth-autopilot-quota" />
      <Stat label="Budget mois" value={`${data.budget.spent_usd.toFixed(2)} / ${data.budget.cap_usd} $`} testid="growth-autopilot-budget" tone={data.budget.ok ? "" : "text-red-700"} />
      <Stat label="Échecs" value={data.failed} testid="growth-autopilot-failed" tone={data.failed ? "text-red-700" : ""} />
    </div>
    {last && <div className="surface p-3 text-xs space-y-1" data-testid="growth-autopilot-last">
      <p className="font-medium">Dernier cycle · {dt(last.started_at)} · {last.trigger === "manual" ? "manuel" : "planifié"} · <span className={last.status === "failed" ? "text-red-700" : ""}>{last.status === "running" ? "en cours" : last.status === "completed" ? "terminé" : last.status}</span></p>
      <p>Problèmes clôturés : <strong className="num">{last.issues_closed}</strong> · Corrections proposées : <strong className="num">{last.overrides_proposed}</strong> · Articles créés : <strong className="num">{last.contents_created}</strong> · prêts à relire : <strong className="num">{last.contents_ready}</strong> · échecs : <strong className="num">{last.contents_failed}</strong>{last.skipped_budget && <span className="text-red-700"> · plafond budget atteint</span>}</p>
      {last.error && <p className="text-red-700">{last.error}</p>}{(last.notes || []).map((n, i) => <p key={i} className="text-muted-foreground">{n}</p>)}
    </div>}
    <section className="space-y-2">
      <div className="flex items-center gap-2"><h3 className="font-semibold text-sm flex-1">Corrections SEO proposées ({pendingOv.length})</h3>
        {canEdit && pendingOv.length > 1 && <Button size="sm" variant="outline" onClick={approveAll} data-testid="growth-overrides-approve-all"><Check className="h-4 w-4" /> Tout approuver</Button>}</div>
      <p className="text-xs text-muted-foreground">Une correction approuvée est appliquée immédiatement sur le site (title et meta description servis à chaud, visibles par Google au prochain passage) et clôture les problèmes liés.</p>
      {pendingOv.length === 0 && <Empty testid="growth-overrides-empty">Aucune proposition en attente. Lancez un audit puis un cycle pour en générer.</Empty>}
      {pendingOv.length > 0 && <ul className="divide-y border rounded-md">{pendingOv.map((o) => <OverrideRow key={o.override_id} o={o} canEdit={canEdit} onDecide={decide} />)}</ul>}
      {doneOv.length > 0 && <details className="text-xs"><summary className="cursor-pointer">Historique ({doneOv.length})</summary><ul className="divide-y border rounded-md mt-1">{doneOv.map((o) => <OverrideRow key={o.override_id} o={o} canEdit={false} onDecide={decide} />)}</ul></details>}
    </section>
    {data.pending_review > 0 && <Button variant="outline" size="sm" onClick={() => onGo("contents")} data-testid="growth-autopilot-go-contents"><FileSearch className="h-4 w-4" /> Relire les {data.pending_review} article(s) prêts</Button>}
  </div>;
}
