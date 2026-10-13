import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck, RefreshCw, ArrowUpRight, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const STATES = { unchecked: "À contrôler", stale: "Modifié depuis le contrôle", needs_review: "À vérifier", checked: "Cohérence contrôlée" };
const RUNS = { proposed: "Proposé", queued: "En attente", running: "En cours", done: "Terminé", error: "Interrompu", cancelled: "Arrêté" };
export function ChantierPilot({ chantierId }) {
  const [data, setData] = useState(null), [error, setError] = useState("");
  const sequence = useRef(0);
  const [busy, setBusy] = useState(false), [repair, setRepair] = useState(false);
  const load = useCallback(async () => {
    const request = ++sequence.current;
    try { const { data } = await api.get(`/chantiers/${chantierId}/pilot`); if (request === sequence.current) { setData(data); setError(""); } }
    catch { if (request === sequence.current) setError("Le suivi du Pilote est indisponible. Réessayez."); }
  }, [chantierId]);
  useEffect(() => { load(); const timer = setInterval(load, 8000); return () => { clearInterval(timer); sequence.current += 1; }; }, [load]);
  const launch = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/agents/plan", { agent: "supervise", chantier_id: chantierId });
      await api.post(`/agents/${data.run.run_id}/launch`, { mode: repair ? "repair" : "audit" });
      toast.success("Contrôle lancé pour ce dossier. Vous pouvez changer de page.");
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Le contrôle n'a pas pu démarrer."); }
    finally { setBusy(false); }
  };
  const active = data?.runs.some(r => ["queued", "running"].includes(r.status));
  return <section className="surface overflow-hidden" data-testid="chantier-pilot">
    <div className="p-5 sm:p-6 bg-gradient-to-br from-primary/10 via-transparent to-amber-700/10">
      <p className="flex gap-2 items-center text-xs uppercase tracking-wider text-primary font-semibold"><ShieldCheck size={17} /> Pilote du dossier</p>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-xl"><h2 className="font-display text-xl font-semibold">Une vue claire, des chiffres vérifiables.</h2>
          <p className="mt-2 text-sm text-muted-foreground">Contrôlez les plans, métrés et devis de cette opération. Les tâches continuent lorsque vous changez de page.</p></div>
        <div className="grid gap-2 w-full sm:w-auto sm:max-w-xs">
          <button type="button" className="rounded-xl bg-primary text-primary-foreground min-h-11 px-4 py-3 text-sm font-semibold inline-flex gap-2 justify-center items-center disabled:opacity-50" disabled={busy || active || data?.truncated} onClick={launch} data-testid="chantier-pilot-launch">{busy || active ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}{active ? "Contrôle en cours" : repair ? "Contrôler et corriger" : "Contrôler le dossier"}</button>
          <label className="flex gap-2 items-start text-xs text-muted-foreground"><input type="checkbox" checked={repair} onChange={e => setRepair(e.target.checked)} disabled={busy || active} className="mt-0.5" /> Corriger les valeurs recalculables, avec historique et restauration.</label>
        </div>
      </div>
    </div>
    <div className="p-5 sm:p-6 grid gap-4">
      {error && <p role="alert" className="text-sm text-destructive">{error} <button className="underline" onClick={load}>Réessayer</button></p>}
      {data && <>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{Object.entries(STATES).map(([key, label]) => <div key={key} className="rounded-xl border border-border/70 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold tabular-nums" data-testid={`pilot-count-${key}`}>{data.summary[key]}</p></div>)}</div>
        {data.truncated && <p role="alert" className="text-sm text-amber-700">Plus de 200 ressources par type : ouvrez le Pilote et sélectionnez un lot. Le suivi affiché est partiel.</p>}
        {data.runs.length > 0 && <div className="flex flex-wrap items-center gap-2 text-xs"><RefreshCw size={14} className={active ? "animate-spin" : ""} /><span>Dernier contrôle : {RUNS[data.runs[0].status] || data.runs[0].status}</span><Link className="text-primary underline" to={`/agents?chantier=${encodeURIComponent(chantierId)}&run=${data.runs[0].run_id}`}>Résultats et historique</Link></div>}
        <details className="group"><summary className="cursor-pointer text-sm font-medium py-2">Plans et devis · {data.resources.length} ressource(s)</summary>
          <div className="grid gap-2 mt-2 max-h-80 overflow-auto">{data.resources.map(r => <div key={r.kind + r.id} className="flex flex-wrap justify-between gap-2 border-b border-border/60 py-3 text-sm"><div className="min-w-0 flex-1"><p className="font-medium break-words">{r.label}</p><p className="text-xs text-muted-foreground mt-1">{STATES[r.state]}{r.issues > 0 ? ` · ${r.issues} point(s)` : ""}</p></div><Link className="text-primary inline-flex items-center gap-1 text-xs min-h-10" to={r.kind === "plan" ? `/analyse/${encodeURIComponent(r.id)}` : `/devis-editeur/${encodeURIComponent(r.id)}`}>{r.kind === "plan" ? "Sources & révisions" : "Ouvrir"}<ArrowUpRight size={14} /></Link></div>)}{!data.resources.length && <p className="text-sm text-muted-foreground">Ajoutez un plan ou rattachez un devis pour commencer.</p>}</div>
        </details>
        <p className="text-xs text-muted-foreground">{data.note}</p>
      </>}
    </div>
  </section>;
}
