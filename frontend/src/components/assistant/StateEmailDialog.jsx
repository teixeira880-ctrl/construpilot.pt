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
    if (!list.length) return toast.error("Indiquez au moins un destinataire");
    setBusy(true);
    try {
      const { data } = await api.post(`/assistant/conversations/${conversationId}/state/email`, { to: list, message, meeting: meeting || null, attendees: attendees || null, include_agenda: agenda, include_state: state });
      if (data.failed?.length) toast.error(`Échec pour ${data.failed.map((f) => f.to).join(", ")}`);
      if (data.sent?.length) { toast.success(`Envoyé à ${data.sent.join(", ")}`); onClose(); }
    } catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Envoi impossible"); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
    <DialogContent className="max-w-md" data-testid="state-email-dialog">
      <DialogTitle className="text-base">Envoyer le dossier par e-mail</DialogTitle>
      <DialogDescription className="text-xs">Ordre du jour et état du dossier en PDF, envoyés depuis ConstruPilot ; les réponses vous parviennent directement.</DialogDescription>
      <div className="grid gap-2 text-sm">
        <input value={to} onChange={(e) => setTo(e.target.value)} placeholder="architecte@exemple.fr, conducteur@exemple.fr" aria-label="Destinataires" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-to" />
        <input value={attendees} onChange={(e) => setAttendees(e.target.value)} placeholder="Participants (optionnel)" aria-label="Participants" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-attendees" />
        <textarea rows={3} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Message d'accompagnement (optionnel)" aria-label="Message" className="rounded-sm border px-2 py-1.5 bg-background" data-testid="state-email-message" />
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={agenda} onChange={(e) => setAgenda(e.target.checked)} data-testid="state-email-agenda" /> Ordre du jour{meeting ? ` (${meeting})` : ""}</label>
        <label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={state} onChange={(e) => setState(e.target.checked)} data-testid="state-email-state" /> État du dossier (1 page)</label>
        <div className="flex justify-end gap-2 pt-1">
          <Button variant="ghost" size="sm" onClick={onClose} data-testid="state-email-cancel">Annuler</Button>
          <Button size="sm" onClick={send} disabled={busy || (!agenda && !state)} data-testid="state-email-send">{busy ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />} Envoyer</Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>;
};
