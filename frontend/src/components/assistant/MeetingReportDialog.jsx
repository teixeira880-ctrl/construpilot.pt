import { useEffect, useState } from "react";
import { ClipboardCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useDocumentViewer } from "./DocumentViewer";

const OUTCOMES = [["untouched", "Não tratado"], ["decided", "Decidido"], ["postponed", "Adiado"], ["dropped", "Abandonado"]];

/* After the meeting: each agenda item gets its outcome; the dossier is updated entry by entry and the report PDF is stored in the conversation. */
export const MeetingReportDialog = ({ open, onClose, conversationId, meeting, state, onDone }) => {
  const [attendees, setAttendees] = useState("");
  const [remarks, setRemarks] = useState("");
  const [items, setItems] = useState({});
  const [busy, setBusy] = useState(false);
  const view = useDocumentViewer();
  const agenda = [...(state?.open_points || []).map((e) => ({ ...e, section: "open_points" })), ...(state?.decisions || []).filter((e) => e.status === "to_confirm").map((e) => ({ ...e, section: "decisions" }))];
  useEffect(() => { if (open) setItems(Object.fromEntries(agenda.map((e) => [e.entry_id, { outcome: "untouched", decision_taken: "", owner: e.owner || "", deadline: e.deadline || "" }]))); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (id, patch) => setItems((s) => ({ ...s, [id]: { ...s[id], ...patch } }));
  const submit = async () => {
    const payload = Object.entries(items).filter(([, v]) => v.outcome !== "untouched").map(([entry_id, v]) => ({ entry_id, ...v, decision_taken: v.decision_taken || null, owner: v.owner || null, deadline: v.deadline || null }));
    if (payload.some((p) => p.outcome === "decided" && !p.decision_taken)) return toast.error("Indique a decisão tomada para cada ponto decidido");
    setBusy(true);
    try {
      const { data } = await api.post(`/assistant/conversations/${conversationId}/meeting-report`, { meeting: meeting || "réunion", attendees: attendees || null, remarks: remarks || null, items: payload });
      toast.success(`Ata criada:${data.counts.decided}decidido(s),${data.counts.postponed}adiado(s)`);
      onDone?.(); onClose();
      view(data.artifact.download, data.artifact.filename, data.artifact.title);
    } catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Ata impossível"); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
    <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="meeting-report-dialog">
      <DialogTitle className="text-base flex items-center gap-2"><ClipboardCheck size={16} /> Ata — reunião {meeting}</DialogTitle>
      <DialogDescription className="text-xs">Indique o desfecho de cada ponto da ordem de trabalhos: o processo é atualizado entrada a entrada e a ata em PDF é adicionada à conversa.</DialogDescription>
      <input value={attendees} onChange={(e) => setAttendees(e.target.value)} placeholder="Participantes presentes" aria-label="Participants" className="rounded-sm border px-2 py-1.5 bg-background text-sm" data-testid="meeting-attendees" />
      <div className="grid gap-3 text-xs">
        {agenda.length === 0 && <p className="text-muted-foreground">Nenhum ponto em aberto nem decisão a confirmar.</p>}
        {agenda.map((e, i) => { const v = items[e.entry_id] || {}; return <div key={e.entry_id} className="rounded-md border p-2 grid gap-1" data-testid={`meeting-item-${e.entry_id}`}>
          <div><b>{i + 1}.</b> {e.statement} <span className="text-muted-foreground">({e.section === "decisions" ? "decisão a confirmar" : "point ouvert"})</span></div>
          <div className="flex flex-wrap gap-1">
            {OUTCOMES.map(([k, l]) => <button key={k} type="button" onClick={() => set(e.entry_id, { outcome: k })} className={`rounded-sm border px-2 py-0.5 ${v.outcome === k ? "bg-primary text-primary-foreground" : "bg-background"}`} data-testid={`meeting-item-${e.entry_id}-${k}`}>{l}</button>)}
          </div>
          {v.outcome && v.outcome !== "untouched" && <>
            <textarea rows={2} value={v.decision_taken} onChange={(ev) => set(e.entry_id, { decision_taken: ev.target.value })} placeholder={v.outcome === "decided" ? "Decisão tomada (obrigatória)" : "Motif / suite (optionnel)"} aria-label="Decisão" className="rounded-sm border px-1 py-0.5 bg-background" data-testid={`meeting-item-${e.entry_id}-decision`} />
            <div className="grid grid-cols-2 gap-1">
              <input value={v.owner} onChange={(ev) => set(e.entry_id, { owner: ev.target.value })} placeholder="Responsable" aria-label="Responsable" className="rounded-sm border px-1 py-0.5 bg-background" data-testid={`meeting-item-${e.entry_id}-owner`} />
              <input value={v.deadline} onChange={(ev) => set(e.entry_id, { deadline: ev.target.value })} placeholder="Prazo" aria-label="Prazo" className="rounded-sm border px-1 py-0.5 bg-background" data-testid={`meeting-item-${e.entry_id}-deadline`} />
            </div>
          </>}
        </div>; })}
        <textarea rows={3} value={remarks} onChange={(e) => setRemarks(e.target.value)} placeholder="Observações gerais, observações de obra" aria-label="Remarques" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="meeting-remarks" />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} data-testid="meeting-cancel">Cancelar</Button>
          <Button size="sm" onClick={submit} disabled={busy} data-testid="meeting-submit">{busy ? <Loader2 size={14} className="animate-spin" /> : <ClipboardCheck size={14} />} Gerar a ata</Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>;
};
