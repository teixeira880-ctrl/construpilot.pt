import { useState } from "react";
import { toast } from "sonner";
import { Wrench, RefreshCw, CheckCircle2, Clock, AlertTriangle, ChevronDown } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useApi, err, dt } from "./lib";

/** Correction automatique des erreurs d'audit : état, bascule, exécution manuelle, détail corrigé / manuel. */
export function AutoFixCard({ projectId, canEdit, isAdmin }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/autofix`, [projectId]);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  if (error) return <p className="text-sm text-destructive" data-testid="growth-autofix-error">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Chargement de la correction automatique…</p>;
  const run = data.last_run;
  const c = run?.counts || {};
  const toggle = async () => {
    try { await api.put(`/growth/projects/${projectId}/autofix`, { enabled: !data.enabled }); toast.success(data.enabled ? "Correction automatique désactivée" : "Correction automatique activée"); reload(); }
    catch (e) { toast.error(err(e)); }
  };
  const runNow = async () => {
    setBusy(true);
    try { const r = await api.post(`/growth/projects/${projectId}/autofix/run`); toast.success(`${r.data.counts?.fixed ?? 0} correction(s) appliquée(s), ${r.data.counts?.manual ?? 0} à traiter manuellement`); reload(); }
    catch (e) { toast.error(err(e)); } finally { setBusy(false); }
  };
  return <div className="surface p-4 space-y-3" data-testid="growth-autofix">
    <div className="flex flex-wrap items-center gap-2">
      <Wrench className="h-4 w-4 text-primary" /><p className="font-semibold text-sm">Correction automatique des erreurs</p>
      <Badge variant="outline" className={`rounded-sm ${data.enabled ? "border-primary text-primary" : ""}`} data-testid="growth-autofix-state">{data.enabled ? "activée" : "désactivée"}</Badge>
      <div className="ms-auto flex gap-2">
        {isAdmin && <Button size="sm" variant="outline" className="h-8" onClick={toggle} data-testid="growth-autofix-toggle">{data.enabled ? "Désactiver" : "Activer"}</Button>}
        {canEdit && <Button size="sm" className="h-8 gap-1" onClick={runNow} disabled={busy || data.running} data-testid="growth-autofix-run"><RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Corriger maintenant</Button>}
      </div>
    </div>
    <p className="text-xs text-muted-foreground">Après chaque audit et chaque nuit : titres et descriptions réécrits et appliqués, canonicals forcées, redirections 404 vers la page la plus proche. Une correction n'est comptée « corrigée » qu'une fois le ré-audit ne retrouve plus le problème. Ce qui exige une modification du code est listé avec sa raison — jamais de faux succès.</p>
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
      {[["Problèmes ouverts", data.open, AlertTriangle, "open"], ["Corrections appliquées", c.fixed ?? 0, CheckCircle2, "fixed"], ["En attente de ré-audit", data.fixing.length, Clock, "awaiting"], ["Manuelles", c.manual ?? 0, Wrench, "manual"]].map(([l, v, I, t]) => (
        <div key={l} className="rounded-md border p-2" data-testid={`growth-autofix-${t}`}><p className="text-[10px] uppercase text-muted-foreground flex items-center gap-1"><I className="h-3 w-3" /> {l}</p><p className="font-display font-bold text-lg num">{v}</p></div>))}
    </div>
    {data.reappeared > 0 && <p className="text-xs rounded-md border border-amber-400/50 bg-amber-50 dark:bg-amber-950/30 p-2" data-testid="growth-autofix-reappeared"><AlertTriangle className="inline h-3.5 w-3.5 me-1 text-amber-600" /> {data.reappeared} problème(s) re-détecté(s) alors qu'une correction est appliquée : la version déployée du site n'inclut probablement pas encore ces corrections (redéployer).</p>}
    {run && <p className="text-[11px] text-muted-foreground">Dernière exécution : {dt(run.finished_at || run.started_at)} · déclencheur {run.trigger} · {run.status}{run.error ? ` · ${run.error}` : ""}</p>}
    {run && (run.fixed?.length > 0 || run.manual?.length > 0) && <>
      <button type="button" className="text-xs text-primary inline-flex items-center gap-1" onClick={() => setOpen(!open)} data-testid="growth-autofix-details">{open ? "Masquer le détail" : "Voir le détail"} <ChevronDown className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`} /></button>
      {open && <div className="grid md:grid-cols-2 gap-3 text-xs">
        <div><p className="font-semibold mb-1 flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-primary" /> Corrigé automatiquement ({run.fixed.length})</p>
          <ul className="space-y-1 max-h-64 overflow-y-auto">{run.fixed.map((f, i) => <li key={i} className="border rounded p-1.5" data-testid="growth-autofix-fixed-item"><span className="text-muted-foreground break-all">{f.url}</span><br />{f.how}</li>)}</ul></div>
        <div><p className="font-semibold mb-1 flex items-center gap-1"><Wrench className="h-3.5 w-3.5" /> À traiter dans le code ({run.manual.length})</p>
          <ul className="space-y-1 max-h-64 overflow-y-auto">{run.manual.map((m, i) => <li key={i} className="border rounded p-1.5" data-testid="growth-autofix-manual-item"><Badge variant="outline" className="rounded-sm text-[10px] me-1">{m.kind}</Badge><span className="text-muted-foreground break-all">{m.url}</span><br />{m.reason}</li>)}</ul></div>
      </div>}
    </>}
  </div>;
}
