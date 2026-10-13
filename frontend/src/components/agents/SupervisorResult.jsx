import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function SupervisorResult({ run }) {
  const report = run.result || run.partial_result;
  const [rows, setRows] = useState(null);
  const [next, setNext] = useState(null);
  const [busy, setBusy] = useState(false);
  const [restored, setRestored] = useState({});
  if (report?.kind !== "supervision") return null;
  const load = async (offset = 0) => {
    setBusy(true);
    try {
      const { data } = await api.get(`/agents/${run.run_id}/checks`, { params: { offset } });
      setRows(previous => offset ? [...(previous || []), ...data.checks] : data.checks);
      setNext(data.next_offset);
    } catch { toast.error("Les détails du contrôle sont indisponibles. Réessayez."); }
    finally { setBusy(false); }
  };
  const undo = async row => {
    setBusy(true);
    try {
      await api.post(`/agents/${run.run_id}/undo`, { kind: row.kind, resource_id: row.id });
      setRestored(previous => ({ ...previous, [`${row.kind}:${row.id}`]: true }));
      toast.success("Correction annulée. Les anciennes valeurs sont restaurées.");
    } catch (error) { toast.error(error?.response?.data?.detail || "Restauration impossible"); }
    finally { setBusy(false); }
  };
  return <div className="w-full min-w-0 border-t border-border pt-3 mt-2 space-y-3" data-testid={`supervisor-result-${run.run_id}`}>
    <div className="grid grid-cols-3 gap-2 text-center">
      {[[report.checked, "documents contrôlés"], [report.corrected, "documents corrigés"], [report.needs_review, "à examiner"]].map(([count, label]) =>
        <div key={label} className="rounded-lg bg-secondary/50 px-2 py-3"><strong className="block text-xl">{count || 0}</strong><span className="text-xs text-muted-foreground">{label}</span></div>)}
    </div>
    <p className="text-xs text-muted-foreground">{report.mode === "repair" ? "Les corrections concernent les valeurs recalculables. Les données manquantes restent à compléter." : "Contrôle en lecture seule : aucune valeur modifiée."} {run.status !== "done" && "Résultat partiel : la tâche n’est pas terminée."}</p>
    <Button size="sm" variant="outline" disabled={busy} onClick={() => load()} data-testid={`supervisor-details-${run.run_id}`}>{busy ? "Chargement…" : "Voir les contrôles et corrections"}</Button>
    {rows && <div className="space-y-3" data-testid="supervisor-checks">
      {rows.length === 0 && <p className="text-sm">Aucun document dans ce contrôle.</p>}
      {rows.map(row => <article key={`${row.kind}:${row.id}`} className="rounded-lg border border-border p-3 min-w-0">
        <p className="font-semibold text-sm break-words">{row.label}</p>
        <p className="text-xs text-muted-foreground mt-1">{row.checked_elements} élément(s) vérifié(s) · {row.corrections} valeur(s) {row.applied ? "corrigée(s)" : "à recalculer"}</p>
        {!!row.issues?.length && <ul className="mt-2 space-y-1 text-xs text-amber-800 dark:text-amber-200">{row.issues.map((item, index) => <li key={`${item.code}:${index}`} className="break-words">{item.message}{item.path ? ` (${item.path})` : ""}</li>)}</ul>}
        <div className="flex flex-wrap items-center gap-3 mt-2">
          <Link className="text-sm text-primary underline" to={row.kind === "quote" ? `/devis-editeur/${encodeURIComponent(row.id)}` : `/plan?open=${encodeURIComponent(row.id)}`}>Ouvrir le document</Link>
          {row.applied && !(row.restored || restored[`${row.kind}:${row.id}`]) && <Button size="sm" variant="ghost" disabled={busy} onClick={() => undo(row)} data-testid={`supervisor-undo-${row.id}`}>Annuler cette correction</Button>}
          {(row.restored || restored[`${row.kind}:${row.id}`]) && <span className="text-xs">Correction annulée</span>}
        </div>
      </article>)}
      {next != null && <Button size="sm" variant="outline" disabled={busy} onClick={() => load(next)}>Afficher la suite</Button>}
    </div>}
  </div>;
}
