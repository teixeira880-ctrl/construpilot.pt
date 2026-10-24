import { useState } from "react";
import { Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export const StateEmailDialog = ({ open, onClose, conversationId, meeting }) => {
  const [to, setTo] = useState("");
  const [message, setMessage] = useState("");
  const [attendees, setAttendees] = useState("");
  const [agenda, setAgenda] = useState(true);
  const [state, setState] = useState(true);
  const [busy, setBusy] = useState(false);
  const send = async () => {
    const list = to.split(/[,;\s]+/).map((a) => a.trim()).filter(Boolean);
    if (!list.length) return toast.error("Indique pelo menos um destinatário");
    setBusy(true);
    try {
      const { data } = await api.post(`/assistant/conversations/${conversationId}/state/email`, { to: list, message, meeting: meeting || null, attendees: attendees || null, include_agenda: agenda, include_state: state });
      if (data.failed?.length) toast.error(`Falha para ${data.failed.map((f) => f.to).join(", ")}`);
      if (data.sent?.length) { toast.success(`Enviado a ${data.sent.join(", ")}`); onClose(); }
    } catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Envio impossível"); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
    <DialogContent className="max-w-md" data-testid="state-email-dialog">
      <DialogTitle className="text-base">Enviar o processo por e-mail</DialogTitle>
      <DialogDescription className="text-xs">Ordem de trabalhos e estado do processo em PDF, enviados a partir do ConstruPilot; as respostas chegam-lhe diretamente.</DialogDescription>
      <div className="grid gap-2 text-sm">
        <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="arquiteto@exemplo.pt, diretor.obra@exemplo.pt" aria-label="Destinatários" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-to" />
        <input value={attendees} onChange={(e) => setAttendees(e.target.value)} placeholder="Participantes (opcional)" aria-label="Participantes" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-attendees" />
        <textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Mensagem de acompanhamento (opcional)" aria-label="Mensagem" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-message" />
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={agenda} onChange={(e) => setAgenda(e.target.checked)} data-testid="state-email-agenda" /> Ordem de trabalhos{meeting ? ` (${meeting})` : ""}</label>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={state} onChange={(e) => setState(e.target.checked)} data-testid="state-email-state" /> Estado do processo (1 página)</label>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={onClose} data-testid="state-email-cancel">Cancelar</Button>
          <Button size="sm" onClick={send} disabled={busy || (!agenda && !state)} data-testid="state-email-send">{busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Enviar</Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>;
};
