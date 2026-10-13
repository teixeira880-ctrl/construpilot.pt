import { useCallback, useEffect, useState } from "react";
import { BookMarked, Check, ChevronDown, ChevronUp, ClipboardCheck, FileDown, ListChecks, Mail, Pencil, Plus, RotateCw, Trash2, X } from "lucide-react";
import { useDocumentViewer } from "./DocumentViewer";
import { StateEmailDialog } from "./StateEmailDialog";
import { MeetingReportDialog } from "./MeetingReportDialog";
import { EntryPhotos } from "./EntryPhotos";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const SECTIONS = [["decisions", "Décisions courantes"], ["discarded_documents", "Documents écartés"], ["open_points", "Points ouverts"]];
const STATUS = { current: "courante", superseded: "remplacée", to_confirm: "à confirmer" };
const KIND = { schema_de_principe: "schéma de principe", validation_execution: "validation d'exécution", fait: "fait", hypothese: "hypothèse", action: "action" };

const Entry = ({ e, section, onSave, onRemove, conversationId, onChange }) => {
  const [editing, setEditing] = useState(false);
  const [statement, setStatement] = useState(e.statement);
  const [source, setSource] = useState(e.source);
  const [owner, setOwner] = useState(e.owner || "");
  const [deadline, setDeadline] = useState(e.deadline || "");
  const id = `state-entry-${e.entry_id}`;
  return <li className="py-1.5 border-b border-border/40 text-xs" data-testid={id}>
    {editing ? <div className="grid gap-1">
      <textarea rows={2} value={statement} onChange={(ev) => setStatement(ev.target.value)} className="w-full rounded-sm border px-1 py-0.5 bg-background" aria-label="Énoncé" data-testid={`${id}-statement`} />
      <input value={source} onChange={(ev) => setSource(ev.target.value)} className="w-full rounded-sm border px-1 py-0.5 bg-background" aria-label="Source" placeholder="Source (pièce, page, message)" data-testid={`${id}-source`} />
      <div className="grid grid-cols-2 gap-1">
        <input value={owner} onChange={(ev) => setOwner(ev.target.value)} className="rounded-sm border px-1 py-0.5 bg-background" aria-label="Responsable" placeholder="Responsable" data-testid={`${id}-owner`} />
        <input value={deadline} onChange={(ev) => setDeadline(ev.target.value)} className="rounded-sm border px-1 py-0.5 bg-background" aria-label="Échéance" placeholder="Échéance (22/09/2026)" data-testid={`${id}-deadline`} />
      </div>
      <div className="flex gap-1">
        <Button size="sm" className="h-7 text-xs gap-1" onClick={() => { onSave({ ...e, section, statement, source, owner, deadline }); setEditing(false); }} data-testid={`${id}-save`}><Check size={12} /> Enregistrer</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(false)} data-testid={`${id}-cancel`}><X size={12} /></Button>
      </div>
    </div> : <>
      <div><span className={`inline-block rounded-sm px-1 mr-1 ${e.status === "current" ? "bg-emerald-500/15" : e.status === "to_confirm" ? "bg-amber-500/15" : "bg-muted line-through"}`}>{STATUS[e.status] || e.status}</span>
        <span className="text-muted-foreground">{KIND[e.kind] || e.kind} · </span>{e.statement}</div>
      <div className="text-muted-foreground">Source : {e.source} · {e.author === "user" ? "vous" : "assistant"}{(e.owner || e.deadline) && <> · <b>{e.owner || "resp. à désigner"}</b> · {e.deadline || "échéance à fixer"}</>}</div>
      <div className="flex gap-3 mt-0.5">
        <button type="button" className="underline text-[11px] flex items-center gap-1" onClick={() => setEditing(true)} data-testid={`${id}-edit`}><Pencil size={10} /> Corriger</button>
        {e.status !== "superseded" && <button type="button" className="underline text-[11px]" onClick={() => onSave({ ...e, section, status: "superseded" })} data-testid={`${id}-supersede`}>Marquer remplacée</button>}
        <button type="button" className="underline text-[11px] flex items-center gap-1 text-destructive" onClick={() => onRemove(e, section)} data-testid={`${id}-remove`}><Trash2 size={10} /> Retirer</button>
      </div>
      <EntryPhotos conversationId={conversationId} entry={e} onChange={onChange} />
    </>}
  </li>;
};

export const ProjectStatePanel = ({ conversationId, refreshKey }) => {
  const [state, setState] = useState(null);
  const [open, setOpen] = useState(true);
  const [adding, setAdding] = useState(null);
  const [draft, setDraft] = useState({ statement: "", source: "" });
  const [meeting, setMeeting] = useState("22/09/2026 9h30");
  const [emailOpen, setEmailOpen] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [emails, setEmails] = useState([]);
  const [resending, setResending] = useState(null);
  const loadEmails = useCallback(async () => {
    if (!conversationId) return;
    try { const { data } = await api.get(`/assistant/conversations/${conversationId}/state/emails`); setEmails(data); } catch { setEmails([]); }
  }, [conversationId]);
  useEffect(() => { loadEmails(); }, [loadEmails, refreshKey, emailOpen]);
  const resend = async (log) => {
    setResending(log.at);
    try {
      const { data } = await api.post(`/assistant/conversations/${conversationId}/state/email`, { to: log.to, meeting: log.meeting || null, include_agenda: (log.documents || []).includes("ordre-du-jour.pdf"), include_state: (log.documents || []).includes("etat-du-dossier.pdf"), message: "" });
      if (data.sent?.length) toast.success(`Renvoyé à ${data.sent.join(", ")} (version actuelle du dossier)`);
      if (data.failed?.length) toast.error(`Échec pour ${data.failed.map((f) => f.to).join(", ")}`);
      await loadEmails();
    } catch { toast.error("Renvoi impossible"); } finally { setResending(null); }
  };
  const view = useDocumentViewer();
  const load = useCallback(async () => {
    if (!conversationId) { setState(null); return; }
    try { const { data } = await api.get(`/assistant/conversations/${conversationId}/state`); setState(data); } catch { setState(null); }
  }, [conversationId]);
  useEffect(() => { load(); }, [load, refreshKey]);
  if (!state) return null;
  const total = SECTIONS.reduce((n, [k]) => n + (state[k]?.length || 0), 0);
  const put = async (body, success) => {
    try { await api.put(`/assistant/conversations/${conversationId}/state`, body); toast.success(success); await load(); }
    catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Mise à jour impossible"); }
  };
  const save = (e) => put({ section: e.section, entry_id: e.entry_id, statement: e.statement, source: e.source || "utilisateur", status: e.status, kind: e.kind, owner: e.owner || null, deadline: e.deadline || null }, "Entrée corrigée — les autres entrées sont inchangées");
  const remove = (e, section) => put({ section, entry_id: e.entry_id, statement: e.statement, source: e.source, remove: true }, "Entrée retirée");
  const add = () => { if (!draft.statement.trim()) return; put({ section: adding, statement: draft.statement, source: draft.source || "utilisateur" }, "Entrée ajoutée").then(() => { setAdding(null); setDraft({ statement: "", source: "" }); }); };
  return <section className="mx-3 mb-2 rounded-md border border-border bg-muted/30 text-xs" data-testid="project-state-panel">
    <button type="button" className="w-full flex items-center justify-between px-3 py-2 font-semibold" onClick={() => setOpen((o) => !o)} data-testid="project-state-toggle">
      <span className="flex items-center gap-1"><BookMarked size={14} /> État du dossier ({total}) · révision {state.revision}</span>{open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
    </button>
    {open && <div className="px-3 pb-2 grid gap-2 max-h-80 overflow-y-auto">
      {SECTIONS.map(([key, label]) => <div key={key} data-testid={`project-state-${key}`}>
        <div className="flex items-center justify-between"><b>{label} ({state[key]?.length || 0})</b>
          <button type="button" className="underline text-[11px] flex items-center gap-1" onClick={() => { setAdding(key); setDraft({ statement: "", source: "" }); }} data-testid={`project-state-add-${key}`}><Plus size={10} /> Ajouter</button></div>
        {adding === key && <div className="grid gap-1 my-1 p-2 rounded-sm border bg-background" data-testid={`project-state-form-${key}`}>
          <textarea rows={2} value={draft.statement} onChange={(e) => setDraft((d) => ({ ...d, statement: e.target.value }))} placeholder="Énoncé factuel" aria-label="Énoncé" className="rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-new-statement" />
          <input value={draft.source} onChange={(e) => setDraft((d) => ({ ...d, source: e.target.value }))} placeholder="Source (pièce, page, mail…)" aria-label="Source" className="rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-new-source" />
          <div className="flex gap-1"><Button size="sm" className="h-7 text-xs" onClick={add} data-testid="project-state-new-save">Enregistrer</Button><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setAdding(null)} data-testid="project-state-new-cancel">Annuler</Button></div>
        </div>}
        <ul>{(state[key] || []).map((e) => <Entry key={e.entry_id} e={e} section={key} onSave={save} onRemove={remove} conversationId={conversationId} onChange={load} />)}</ul>
      </div>)}
      <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-border/40" data-testid="project-state-export">
        <input value={meeting} onChange={(e) => setMeeting(e.target.value)} placeholder="Réunion (ex. 22/09/2026 9h30)" aria-label="Réunion de chantier" className="flex-1 min-w-[140px] rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-meeting" />
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => view(`/assistant/conversations/${conversationId}/state/pdf${meeting ? `?meeting=${encodeURIComponent(meeting)}` : ""}`, "etat-du-dossier.pdf", "État du dossier (PDF 1 page)")} data-testid="project-state-pdf"><FileDown size={12} /> État PDF</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => view(`/assistant/conversations/${conversationId}/agenda/pdf${meeting ? `?meeting=${encodeURIComponent(meeting)}` : ""}`, "ordre-du-jour.pdf", "Ordre du jour (PDF 1 page)")} data-testid="project-state-agenda"><ListChecks size={12} /> Ordre du jour</Button>
        <Button size="sm" className="h-7 text-xs gap-1" onClick={() => setEmailOpen(true)} data-testid="project-state-email"><Mail size={12} /> Envoyer</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setReportOpen(true)} data-testid="project-state-report"><ClipboardCheck size={12} /> Compte rendu</Button>
      </div>
      {emails.length > 0 && <div className="pt-1 border-t border-border/40" data-testid="project-state-emails">
        <b>Envois ({emails.length})</b>
        <ul>{emails.map((l) => <li key={l.at} className="flex flex-wrap items-center gap-x-2 py-0.5 text-[11px]" data-testid={`state-email-log-${l.at}`}>
          <span className="text-muted-foreground">{new Date(l.at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</span>
          <span>{(l.to || []).join(", ")}{l.failed?.length ? ` · échec : ${l.failed.map((f) => f.to).join(", ")}` : ""}</span>
          <span className="text-muted-foreground">{(l.documents || []).map((d) => d.replace(".pdf", "")).join(" + ")}</span>
          <button type="button" className="underline flex items-center gap-1" disabled={resending === l.at} onClick={() => resend(l)} data-testid="state-email-resend"><RotateCw size={10} className={resending === l.at ? "animate-spin" : ""} /> Renvoyer</button>
        </li>)}</ul>
      </div>}
      <MeetingReportDialog open={reportOpen} onClose={() => setReportOpen(false)} conversationId={conversationId} meeting={meeting} state={state} onDone={load} />
      <StateEmailDialog open={emailOpen} onClose={() => setEmailOpen(false)} conversationId={conversationId} meeting={meeting} />
      <p className="text-muted-foreground">Un schéma de principe illustre une intention ; la validation technique d'exécution relève du BET ou du contrôleur.</p>
    </div>}
  </section>;
};
