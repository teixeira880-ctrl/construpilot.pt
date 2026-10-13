import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { CalendarRange, Save, RefreshCw, Sparkles, Flag, FileDown, Trash2, Loader2, HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api, API } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmProvider";
import { GanttChart } from "@/components/planning/GanttChart";
import { TaskTable } from "@/components/planning/TaskTable";
import { SuggestionsPanel } from "@/components/planning/SuggestionsPanel";

const fr = (d) => (d ? d.slice(8, 10) + "/" + d.slice(5, 7) + "/" + d.slice(0, 4) : "—");
const today = () => new Date().toISOString().slice(0, 10);
const pickDraft = (p) => ({ start_date: p.start_date, deadline: p.deadline || "", holidays: p.holidays || [], workdays: p.workdays || [0, 1, 2, 3, 4], capacities: p.capacities || {}, client_visible: p.client_visible !== false, tasks: p.tasks || [] });

function InitCard({ info, onInit, busy }) {
  const [start, setStart] = useState(today());
  return (
    <section className="surface p-6 grid gap-4 max-w-2xl" data-testid="planning-init">
      <div><p className="font-display font-bold">Créer le planning de ce chantier</p>
        <p className="text-sm text-muted-foreground mt-1">Les lots des devis liés deviennent des tâches, ordonnées selon l'enchaînement BTP classique. Les durées sont posées à 5 jours ouvrés par défaut et marquées « à confirmer » : rien n'est estimé par IA.</p></div>
      {info.lots_available?.length > 0 ? (
        <div className="flex flex-wrap gap-1">{info.lots_available.map((l) => <Badge key={l} variant="outline" className="rounded-sm">{l}</Badge>)}</div>
      ) : <p className="text-xs text-amber-700">Aucun devis lié avec des lots : le planning démarrera vide (ajoutez vos tâches).</p>}
      <div className="flex flex-wrap items-end gap-3">
        <label className="grid gap-1 text-xs"><span className="text-muted-foreground">Début des travaux</span>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="h-9 w-44" data-testid="planning-init-start" /></label>
        <Button className="gap-2 rounded-sm" disabled={busy} onClick={() => onInit(start)} data-testid="planning-init-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarRange className="h-4 w-4" />} Générer le planning</Button>
      </div>
    </section>
  );
}

function Kpis({ project, tasks }) {
  const gap = project.deadline_gap_days;
  const items = [
    ["Début", fr(project.start_date)], ["Fin prévue", fr(project.end_date)], ["Durée", `${project.duration_workdays} j ouvrés`],
    ["Chemin critique", `${project.critical_path.length} / ${tasks.length} tâches`],
    ["Objectif", project.deadline ? `${fr(project.deadline)} · ${gap >= 0 ? `+${gap} j` : `${gap} j`}` : "non fixé"],
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-2" data-testid="planning-kpis">
      {items.map(([l, v], i) => (
        <div key={l} className={`surface p-3 ${i === 4 && project.deadline ? (gap >= 0 ? "border-emerald-300" : "border-red-300") : ""}`}>
          <p className="text-[11px] text-muted-foreground">{l}</p><p className="font-display font-bold text-sm" data-testid={`kpi-${i}`}>{v}</p>
        </div>
      ))}
    </div>
  );
}

function Settings({ draft, setDraft, resources }) {
  const hol = (draft.holidays || []).join(", ");
  return (
    <section className="surface p-4 grid gap-3" data-testid="planning-settings">
      <div className="flex flex-wrap gap-3 items-end">
        <label className="grid gap-1 text-xs"><span className="text-muted-foreground">Début</span>
          <Input type="date" value={draft.start_date} onChange={(e) => setDraft({ ...draft, start_date: e.target.value })} className="h-9 w-40" data-testid="planning-start" /></label>
        <label className="grid gap-1 text-xs"><span className="text-muted-foreground">Objectif de fin (optionnel)</span>
          <Input type="date" value={draft.deadline || ""} onChange={(e) => setDraft({ ...draft, deadline: e.target.value })} className="h-9 w-40" data-testid="planning-deadline" /></label>
        <label className="grid gap-1 text-xs flex-1 min-w-[220px]"><span className="text-muted-foreground">Jours chômés / congés (AAAA-MM-JJ, séparés par virgule)</span>
          <Input value={hol} placeholder="2026-07-14, 2026-08-10" data-testid="planning-holidays"
                 onChange={(e) => setDraft({ ...draft, holidays: e.target.value.split(/[,\s;]+/).map((s) => s.trim()).filter((s) => /^\d{4}-\d{2}-\d{2}$/.test(s)) })} className="h-9" /></label>
        <label className="flex items-center gap-2 text-xs h-9"><input type="checkbox" checked={(draft.workdays || []).includes(5)} className="accent-primary"
                 onChange={(e) => setDraft({ ...draft, workdays: e.target.checked ? [0, 1, 2, 3, 4, 5] : [0, 1, 2, 3, 4] })} data-testid="planning-saturday" /> Samedi travaillé</label>
        <label className="flex items-center gap-2 text-xs h-9" title="Le client voit le Gantt (sans marges ni propositions internes) dans son Espace Client"><input type="checkbox" checked={draft.client_visible !== false} className="accent-primary"
                 onChange={(e) => setDraft({ ...draft, client_visible: e.target.checked })} data-testid="planning-client-visible" /> Visible par le client</label>
      </div>
      {resources.length > 0 && (
        <div className="flex flex-wrap gap-2 items-center text-xs">
          <span className="text-muted-foreground">Équipes disponibles en parallèle :</span>
          {resources.map((r) => (
            <label key={r} className="flex items-center gap-1 border border-border rounded-sm px-2 h-8">
              <span>{r}</span>
              <input type="number" min={1} max={20} value={draft.capacities?.[r] || 1} className="w-10 h-6 text-center bg-background border border-border rounded-sm"
                     onChange={(e) => setDraft({ ...draft, capacities: { ...draft.capacities, [r]: Math.max(1, Number(e.target.value) || 1) } })} data-testid={`capacity-${r}`} />
            </label>
          ))}
        </div>
      )}
    </section>
  );
}

export default function Planning() {
  const [params, setParams] = useSearchParams();
  const confirm = useConfirm();
  const chantierId = params.get("chantier") || "";
  const [chantiers, setChantiers] = useState([]);
  const [info, setInfo] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const [opt, setOpt] = useState(null);

  useEffect(() => { api.get("/chantiers").then(({ data }) => setChantiers(data.chantiers || [])).catch(() => {}); }, []);
  const load = useCallback(() => {
    if (!chantierId) return;
    api.get(`/planning/chantiers/${chantierId}`).then(({ data }) => { setInfo(data); if (data.exists) { setDraft(pickDraft(data)); setDirty(false); } })
      .catch((e) => toast.error(e?.response?.data?.detail || "Chargement impossible"));
  }, [chantierId]);
  useEffect(() => { setInfo(null); setDraft(null); load(); }, [load]);

  const apply = (data) => { setInfo(data); setDraft(pickDraft(data)); setDirty(false); };
  const run = async (fn, ok) => { setBusy(true); try { const { data } = await fn(); apply(data); if (ok) toast.success(ok); } catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); } finally { setBusy(false); } };
  const save = () => run(() => api.put(`/planning/chantiers/${chantierId}`, { ...draft, deadline: draft.deadline || null }), "Planning recalculé");
  const init = (start) => run(() => api.post(`/planning/chantiers/${chantierId}/init`, { start_date: start, from_quotes: true }), "Planning généré");
  const baseline = () => run(() => api.post(`/planning/chantiers/${chantierId}/baseline`), "Planning de référence figé");
  const progress = (tid, value) => {
    setDraft((d) => ({ ...d, tasks: d.tasks.map((t) => (t.id === tid ? { ...t, progress: value } : t)) }));
    if (dirty) return;
    run(() => api.patch(`/planning/chantiers/${chantierId}/tasks/${tid}`, { progress: value }));
  };
  const followTimesheets = (tid) => run(() => api.patch(`/planning/chantiers/${chantierId}/tasks/${tid}`, { progress_manual: false }), "Avancement suivi depuis le pointage");
  const optimize = async (applyIt = false) => {
    setBusy(true);
    try { const { data } = await api.post(`/planning/chantiers/${chantierId}/optimize?apply=${applyIt}`); setOpt(data.optimization); if (data.applied) { apply(data.plan); toast.success("Ordonnancement optimisé appliqué"); setOpt(null); } }
    catch (e) { toast.error(e?.response?.data?.detail || "Optimisation impossible"); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!(await confirm({ title: "Supprimer ce planning ?", description: "Les tâches et l'avancement saisis seront perdus." }))) return;
    await api.delete(`/planning/chantiers/${chantierId}`); toast.success("Planning supprimé"); load();
  };
  const setD = (d) => { setDraft(d); setDirty(true); };
  const resources = useMemo(() => [...new Set((draft?.tasks || []).map((t) => t.resource).filter(Boolean))], [draft]);
  const chantier = chantiers.find((c) => c.chantier_id === chantierId);

  return (
    <div className="grid gap-5" data-testid="planning-page">
      <header className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2"><CalendarRange className="h-5 w-5 text-primary" /><h1 className="font-display font-bold text-xl">Planning de chantier</h1></div>
        <select value={chantierId} onChange={(e) => setParams(e.target.value ? { chantier: e.target.value } : {})} className="h-9 rounded-sm border border-border bg-background px-2 text-sm min-w-[220px]" data-testid="planning-chantier-select">
          <option value="">— Choisir un dossier chantier —</option>
          {chantiers.map((c) => <option key={c.chantier_id} value={c.chantier_id}>{c.name}</option>)}
        </select>
        {chantier && <Link to={`/chantiers/${chantierId}`} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"><HardHat className="h-3 w-3" /> Ouvrir le dossier</Link>}
      </header>

      {!chantierId && <section className="surface p-8 text-center text-sm text-muted-foreground" data-testid="planning-empty">Sélectionnez un dossier chantier pour afficher ou créer son planning.</section>}
      {chantierId && info && !info.exists && <InitCard info={info} onInit={init} busy={busy} />}

      {chantierId && info?.exists && draft && (
        <>
          <Kpis project={info.schedule.project} tasks={info.schedule.tasks} />
          <div className="flex flex-wrap gap-2">
            <Button className="gap-2 rounded-sm" onClick={save} disabled={busy} data-testid="planning-save-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : dirty ? <Save className="h-4 w-4" /> : <RefreshCw className="h-4 w-4" />} {dirty ? "Enregistrer & recalculer" : "Recalculer"}</Button>
            <Button variant="outline" className="gap-2 rounded-sm" onClick={() => optimize(false)} disabled={busy || dirty} title={dirty ? "Enregistrez d'abord" : ""} data-testid="planning-optimize-btn"><Sparkles className="h-4 w-4" /> Optimiser (OR-Tools)</Button>
            <Button variant="outline" className="gap-2 rounded-sm" onClick={baseline} disabled={busy || dirty} data-testid="planning-baseline-btn"><Flag className="h-4 w-4" /> {info.baseline ? `Référence du ${fr(info.baseline.frozen_at?.slice(0, 10))} — refiger` : "Figer comme référence"}</Button>
            <a href={`${API}/planning/chantiers/${chantierId}/pdf`} target="_blank" rel="noreferrer" data-testid="planning-pdf-link">
              <Button variant="outline" className="gap-2 rounded-sm" disabled={dirty}><FileDown className="h-4 w-4" /> PDF Gantt</Button></a>
            <Button variant="ghost" className="gap-2 rounded-sm text-red-600 ms-auto" onClick={remove} data-testid="planning-delete-btn"><Trash2 className="h-4 w-4" /> Supprimer</Button>
          </div>
          {dirty && <p className="text-xs text-amber-700" data-testid="planning-dirty">Modifications non enregistrées : les dates affichées correspondent au dernier calcul.</p>}
          {info.timesheet_sync?.length > 0 && <p className="text-xs text-emerald-700" data-testid="planning-timesheet-sync">Pointage RH : {info.timesheet_sync.length} tâche(s) mise(s) à jour automatiquement depuis les heures validées ({info.timesheet_sync.map((s) => `${s.id} ${s.hours} h / ${s.planned} h → ${s.progress} %`).join(" · ")}).</p>}

          <Settings draft={draft} setDraft={setD} resources={resources} />
          <section className="surface p-4"><GanttChart tasks={info.schedule.tasks} project={info.schedule.project} selected={selected} onSelect={setSelected} /></section>
          <section className="surface p-4">
            <TaskTable tasks={draft.tasks} computed={info.schedule.tasks} trades={info.trades || []} selected={selected} onSelect={setSelected}
                       onChange={(tasks) => setD({ ...draft, tasks })} onProgress={progress} onFollowTimesheets={followTimesheets} />
          </section>
          <SuggestionsPanel suggestions={info.suggestions} onHighlight={setSelected}
                            onApplyCapacity={(res, val) => { const d = { ...draft, capacities: { ...draft.capacities, [res]: val } }; setDraft(d); run(() => api.put(`/planning/chantiers/${chantierId}`, { ...d, deadline: d.deadline || null }), `Capacité « ${res} » = ${val}`); }} />
        </>
      )}

      <Dialog open={!!opt} onOpenChange={(o) => !o && setOpt(null)}>
        <DialogContent className="max-w-lg" data-testid="optimize-dialog">
          <DialogHeader><DialogTitle>Optimisation OR-Tools (CP-SAT)</DialogTitle>
            <DialogDescription>Minimise la fin de chantier en respectant vos dépendances et la capacité des équipes.</DialogDescription></DialogHeader>
          {opt && (opt.ok ? (
            <div className="grid gap-3 text-sm">
              <p data-testid="optimize-result">Planning actuel : <b>{opt.baseline_days} j</b> → optimisé : <b>{opt.makespan_days} j</b> {opt.gain_days > 0 ? <span className="text-emerald-700">(−{opt.gain_days} j ouvrés, fin le {fr(opt.end_date)})</span> : <span className="text-muted-foreground">— déjà optimal</span>}{opt.optimal ? " · solution optimale prouvée" : " · meilleure solution trouvée en 8 s"}</p>
              {opt.moved.length > 0 && <ul className="text-xs grid gap-1 max-h-48 overflow-y-auto">{opt.moved.map((m) => <li key={m.id}>{m.name} : {m.moved_days > 0 ? `+${m.moved_days}` : m.moved_days} j → {fr(m.start_date)}</li>)}</ul>}
              <div className="flex gap-2 justify-end"><Button variant="outline" className="rounded-sm" onClick={() => setOpt(null)}>Fermer</Button>
                {opt.gain_days > 0 && <Button className="rounded-sm" onClick={() => optimize(true)} data-testid="optimize-apply-btn">Appliquer (dates « pas avant »)</Button>}</div>
            </div>
          ) : <p className="text-sm text-red-700">{opt.reason}</p>)}
        </DialogContent>
      </Dialog>
    </div>
  );
}
