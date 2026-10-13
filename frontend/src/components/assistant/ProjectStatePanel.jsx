import { useCallback, useEffect, useState } from "react";
import { BookMarked, Check, ChevronDown, ChevronUp, ClipboardCheck, FileDown, ListChecks, Mail, Pencil, Plus, RotateCw, Trash2, X } from "lucide-react";
import { useDocumentViewer } from "./DocumentViewer";
import { StateEmailDialog } from "./StateEmailDialog";
import { MeetingReportDialog } from "./MeetingReportDialog";
import { EntryPhotos } from "./EntryPhotos";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const SECTIONS = [["decisions", "Decisões em vigor"], ["discarded_documents", "Documentos afastados"], ["open_points", "Points ouverts"]];
const STATUS = { current: "courante", superseded: "substituída", to_confirm: "a confirmar" };
const KIND = { schema_de_principe: "esquema de princípio", validation_execution: "validação de execução", fait: "fait", hypothese: "hipótese", action: "action" };

const Entry = ({ e, section, onSave, onRemove, conversationId, onChange }) => {
  const [editing, setEditing] = useState(false);
  const [statement, setStatement] = useState(e.statement);
  const [source, setSource] = useState(e.source);
  const [owner, setOwner] = useState(e.owner || "");
  const [deadline, setDeadline] = useState(e.deadline || "");
  const id = `state-entry-${e.entry_id}`;
  return <li className="py-1.5 border-b border-border/40 text-xs" data-testid={id}>
    {editing ? <div className="grid gap-1">
      <textarea rows={2} value={statement} onChange={(ev) => setStatement(ev.target.value)} className="w-full rounded-sm border px-1 py-0.5 bg-background" aria-label="Enunciado" data-testid={`${id}-statement`} />
      <input value={source} onChange={(ev) => setSource(ev.target.value)} className="w-full rounded-sm border px-1 py-0.5 bg-background" aria-label="Source" placeholder="Fonte (peça, página, mensagem)" data-testid={`${id}-source`} />
      <div className="grid grid-cols-2 gap-1">
        <input value={owner} onChange={(ev) => setOwner(ev.target.value)} className="rounded-sm border px-1 py-0.5 bg-background" aria-label="Responsable" placeholder="Responsable" data-testid={`${id}-owner`} />
        <input value={deadline} onChange={(ev) => setDeadline(ev.target.value)} className="rounded-sm border px-1 py-0.5 bg-background" aria-label="Prazo" placeholder="Prazo (22/09/2026)" data-testid={`${id}-deadline`} />
      </div>
      <div className="flex gap-1">
        <Button size="sm" className="h-7 text-xs gap-1" onClick={() => { onSave({ ...e, section, statement, source, owner, deadline }); setEditing(false); }} data-testid={`${id}-save`}><Check size={12} /> Guardar</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setEditing(false)} data-testid={`${id}-cancel`}><X size={12} /></Button>
      </div>
    </div> : <>
      <div><span className={`inline-block rounded-sm px-1 mr-1 ${e.status === "current" ? "bg-emerald-500/15" : e.status === "to_confirm" ? "bg-amber-500/15" : "bg-muted line-through"}`}>{STATUS[e.status] || e.status}</span>
        <span className="text-muted-foreground">{KIND[e.kind] || e.kind} · </span>{e.statement}</div>
      <div className="text-muted-foreground">Source : {e.source} · {e.author === "user" ? "vous" : "assistant"}{(e.owner || e.deadline) && <> · <b>{e.owner || "resp. a designar"}</b> · {e.deadline || "prazo a fixar"}</>}</div>
      <div className="flex gap-3 mt-0.5">
        <button type="button" className="underline text-[11px] flex items-center gap-1" onClick={() => setEditing(true)} data-testid={`${id}-edit`}><Pencil size={10} /> Corriger</button>
        {e.status !== "superseded" && <button type="button" className="underline text-[11px]" onClick={() => onSave({ ...e, section, status: "superseded" })} data-testid={`${id}-supersede`}>Marcar como substituída</button>}
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
      if (data.sent?.length) toast.success(`Remetido para${data.sent.join(", ")}(versão atual do processo)`);
      if (data.failed?.length) toast.error(`Falha para${data.failed.map((f) => f.to).join(", ")}`);
      await loadEmails();
    } catch { toast.error("Não foi possível reenviar"); } finally { setResending(null); }
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
    catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Não foi possível atualizar"); }
  };
  const save = (e) => put({ section: e.section, entry_id: e.entry_id, statement: e.statement, source: e.source || "utilisateur", status: e.status, kind: e.kind, owner: e.owner || null, deadline: e.deadline || null }, "Entrada corrigida — as outras entradas ficam inalteradas");
  const remove = (e, section) => put({ section, entry_id: e.entry_id, statement: e.statement, source: e.source, remove: true }, "Entrada removida");
  const add = () => { if (!draft.statement.trim()) return; put({ section: adding, statement: draft.statement, source: draft.source || "utilisateur" }, "Entrada adicionada").then(() => { setAdding(null); setDraft({ statement: "", source: "" }); }); };
  return <section className="mx-3 mb-2 rounded-md border border-border bg-muted/30 text-xs" data-testid="project-state-panel">
    <button type="button" className="w-full flex items-center justify-between px-3 py-2 font-semibold" onClick={() => setOpen((o) => !o)} data-testid="project-state-toggle">
      <span className="flex items-center gap-1"><BookMarked size={14} /> Estado do processo ({total}) · revisão {state.revision}</span>{open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
    </button>
    {open && <div className="px-3 pb-2 grid gap-2 max-h-80 overflow-y-auto">
      {SECTIONS.map(([key, label]) => <div key={key} data-testid={`project-state-${key}`}>
        <div className="flex items-center justify-between"><b>{label} ({state[key]?.length || 0})</b>
          <button type="button" className="underline text-[11px] flex items-center gap-1" onClick={() => { setAdding(key); setDraft({ statement: "", source: "" }); }} data-testid={`project-state-add-${key}`}><Plus size={10} /> Adicionar</button></div>
        {adding === key && <div className="grid gap-1 my-1 p-2 rounded-sm border bg-background" data-testid={`project-state-form-${key}`}>
          <textarea rows={2} value={draft.statement} onChange={(e) => setDraft((d) => ({ ...d, statement: e.target.value }))} placeholder="Enunciado factual" aria-label="Enunciado" className="rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-new-statement" />
          <input value={draft.source} onChange={(e) => setDraft((d) => ({ ...d, source: e.target.value }))} placeholder="Fonte (peça, página, e-mail…)" aria-label="Source" className="rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-new-source" />
          <div className="flex gap-1"><Button size="sm" className="h-7 text-xs" onClick={add} data-testid="project-state-new-save">Guardar</Button><Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setAdding(null)} data-testid="project-state-new-cancel">Cancelar</Button></div>
        </div>}
        <ul>{(state[key] || []).map((e) => <Entry key={e.entry_id} e={e} section={key} onSave={save} onRemove={remove} conversationId={conversationId} onChange={load} />)}</ul>
      </div>)}
      <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-border/40" data-testid="project-state-export">
        <input value={meeting} onChange={(e) => setMeeting(e.target.value)} placeholder="Reunião (ex.: 22/09/2026 9h30)" aria-label="Reunião de obra" className="flex-1 min-w-[140px] rounded-sm border px-1 py-0.5 bg-background" data-testid="project-state-meeting" />
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => view(`/assistant/conversations/${conversationId}/state/pdf${meeting ? `?meeting=${encodeURIComponent(meeting)}` : ""}`, "etat-du-dossier.pdf", "Estado do processo (PDF 1 página)")} data-testid="project-state-pdf"><FileDown size={12} /> Estado PDF</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => view(`/assistant/conversations/${conversationId}/agenda/pdf${meeting ? `?meeting=${encodeURIComponent(meeting)}` : ""}`, "ordre-du-jour.pdf", "Ordem de trabalhos (PDF 1 página)")} data-testid="project-state-agenda"><ListChecks size={12} /> Ordem de trabalhos</Button>
        <Button size="sm" className="h-7 text-xs gap-1" onClick={() => setEmailOpen(true)} data-testid="project-state-email"><Mail size={12} /> Enviar</Button>
        <Button size="sm" variant="outline" className="h-7 text-xs gap-1" onClick={() => setReportOpen(true)} data-testid="project-state-report"><ClipboardCheck size={12} /> Ata</Button>
      </div>
      {emails.length > 0 && <div className="pt-1 border-t border-border/40" data-testid="project-state-emails">
        <b>Envois ({emails.length})</b>
        <ul>{emails.map((l) => <li key={l.at} className="flex flex-wrap items-center gap-x-2 py-0.5 text-[11px]" data-testid={`state-email-log-${l.at}`}>
          <span className="text-muted-foreground">{new Date(l.at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</span>
          <span>{(l.to || []).join(", ")}{l.failed?.length ? `· falha:${l.failed.map((f) => f.to).join(", ")}` : ""}</span>
          <span className="text-muted-foreground">{(l.documents || []).map((d) => d.replace(".pdf", "")).join(" + ")}</span>
          <button type="button" className="underline flex items-center gap-1" disabled={resending === l.at} onClick={() => resend(l)} data-testid="state-email-resend"><RotateCw size={10} className={resending === l.at ? "animate-spin" : ""} /> Renvoyer</button>
        </li>)}</ul>
      </div>}
      <MeetingReportDialog open={reportOpen} onClose={() => setReportOpen(false)} conversationId={conversationId} meeting={meeting} state={state} onDone={load} />
      <StateEmailDialog open={emailOpen} onClose={() => setEmailOpen(false)} conversationId={conversationId} meeting={meeting} />
      <p className="text-muted-foreground">Um esquema de princípio ilustra uma intenção; a validação técnica de execução cabe ao gabinete de projeto ou à fiscalização.</p>
    </div>}
  </section>;
};
