import { useEffect, useState } from "react";
import { Flag, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { pollCotesJob } from "@/lib/cotesJobs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const fmt = (d) => new Date(d).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export function ReportIssueButton({ plan, pageIndex, target, onReported }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ element: "", description: "", expected_value: "" });
  useEffect(() => { if (target) setForm((f) => ({ ...f, element: f.element || target })); }, [target]);
  const submit = async () => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/cotes/issues`, { page_index: pageIndex, target: target || "", ...form });
      toast.success("Erreur signalée — l'analyse est marquée « à réviser », une version a été archivée");
      setOpen(false); setForm({ element: "", description: "", expected_value: "" }); onReported?.();
    } catch (e) { toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Signalement impossible"); }
  };
  return (
    <>
      <Button size="sm" variant="outline" className="rounded-sm gap-1 border-orange-400 text-orange-700" onClick={() => setOpen(true)} data-testid="report-issue-btn"><Flag className="h-3.5 w-3.5" /> Signaler une erreur d'analyse</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="report-issue-dialog">
          <DialogHeader><DialogTitle>Signaler une erreur d'analyse</DialogTitle></DialogHeader>
          <div className="grid gap-3 text-sm">
            {target && <p className="text-xs text-muted-foreground">Élément sélectionné : <b>{target}</b></p>}
            <label className="grid gap-1">Cote / mesure / élément concerné<input className="border rounded-sm px-2 py-1.5 bg-background" value={form.element} onChange={(e) => setForm({ ...form, element: e.target.value })} placeholder="ex. Cote n° 16 (5,33 m), INT-H-006, mur M13…" data-testid="issue-element" /></label>
            <label className="grid gap-1">Description de l'erreur<textarea className="border rounded-sm px-2 py-1.5 bg-background" rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Ce qui est faux, ce que montre réellement le plan…" data-testid="issue-description" /></label>
            <label className="grid gap-1">Valeur attendue (facultatif)<input className="border rounded-sm px-2 py-1.5 bg-background" value={form.expected_value} onChange={(e) => setForm({ ...form, expected_value: e.target.value })} placeholder="ex. 4.57" data-testid="issue-expected" /></label>
            <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button><Button onClick={submit} disabled={form.element.length < 2 || form.description.length < 5} data-testid="issue-submit">Envoyer le signalement</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function VersionHistory({ plan, pageIndex, refreshKey, onChanged }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const reanalyze = async (id) => {
    setBusy(id);
    try {
      const r = await api.post(`/takeoffs/${plan.plan_id}/cotes/issues/${id}/reanalyze`);
      const res = await pollCotesJob(r.data.job_id, { timeoutMs: 600000 });
      toast[res.changed ? "success" : "info"](res.changed ? `Cible recalculée : valeur modifiée — version v${res.version}, signalement clos` : `Cible recalculée : valeur inchangée (version v${res.version} archivée)`);
      const d = await api.get(`/takeoffs/${plan.plan_id}/cotes/versions?page_index=${pageIndex}`); setData(d.data); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message || "Réanalyse impossible"); }
    finally { setBusy(null); }
  };
  useEffect(() => { if (open) api.get(`/takeoffs/${plan.plan_id}/cotes/versions?page_index=${pageIndex}`).then((r) => setData(r.data)).catch(() => setData({ versions: [], issues: [] })); }, [open, plan?.plan_id, pageIndex, refreshKey]);
  const resolve = async (id) => { await api.patch(`/takeoffs/${plan.plan_id}/cotes/issues/${id}`, { resolution: "Corrigé après recalcul" }); toast.success("Signalement clos"); setData(null); setOpen(false); setTimeout(() => setOpen(true), 50); };
  return (
    <details className="text-xs border rounded-sm p-3 bg-card" open={open} onToggle={(e) => setOpen(e.target.open)} data-testid="version-history">
      <summary className="cursor-pointer font-medium flex items-center gap-1"><History className="h-3.5 w-3.5" /> Historique des versions et signalements</summary>
      {data && (
        <div className="grid gap-2 mt-2">
          <div className="grid gap-1">
            {data.versions.length === 0 && <p className="text-muted-foreground">Aucune version archivée.</p>}
            {data.versions.map((v) => (
              <div key={v.version_id} className="flex flex-wrap gap-x-2 border-l-2 pl-2" data-testid={`version-${v.version}`}>
                <b>v{v.version}</b><span>{fmt(v.created_at)}</span>
                <span className="text-muted-foreground">{{ check: "recalcul des cotes", issue_reported: "signalement utilisateur", reanalysis: "réanalyse IA", guided_correction: "correction guidée" }[v.trigger] || v.trigger}</span>
                {v.trigger === "guided_correction" && <span className={v.changed ? "text-emerald-700" : "text-muted-foreground"}>· cible {v.changed ? "modifiée" : "inchangée"}</span>}
                {v.summary && <span>· {v.summary.ok} ok / {v.summary.warn} écarts / {v.summary.ko} incohérences</span>}
                {v.interior_validation && <span>· intérieur : {v.interior_validation.complete ? "complet" : "incomplet"}</span>}
                {v.open_issues > 0 && <span className="text-orange-600">· {v.open_issues} signalement(s) ouvert(s)</span>}
              </div>
            ))}
          </div>
          {data.issues.length > 0 && (
            <div className="grid gap-1" data-testid="issue-list">
              <b>Signalements</b>
              {data.issues.map((i) => (
                <div key={i.issue_id} className={`flex flex-wrap items-center gap-x-2 border-l-2 pl-2 ${i.status === "open" ? "border-orange-500" : "border-emerald-500"}`} data-testid={`issue-${i.issue_id}`}>
                  <span className="font-medium">{i.element}</span>{i.target && <span className="font-mono text-muted-foreground">{i.target}</span>}
                  <span>— {i.description}</span>{i.expected_value && <span>· attendu {i.expected_value}</span>}
                  <span className="text-muted-foreground">{fmt(i.created_at)}</span>
                  {i.status === "open" ? (<>
                    <button className="underline text-primary" disabled={busy === i.issue_id} onClick={() => reanalyze(i.issue_id)} data-testid={`issue-reanalyze-${i.issue_id}`}>{busy === i.issue_id ? "réanalyse en cours…" : "correction guidée (réanalyser la cible)"}</button>
                    <button className="underline" onClick={() => resolve(i.issue_id)} data-testid={`issue-resolve-${i.issue_id}`}>marquer corrigé</button>
                  </>) : <span className="text-emerald-700">corrigé</span>}
                  {i.resolution && <span className="block w-full text-muted-foreground">{i.resolution}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </details>
  );
}
