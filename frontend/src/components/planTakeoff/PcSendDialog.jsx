import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mail, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

export default function PcSendDialog({ open, onClose, planId, onSent, startDate }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [templates, setTemplates] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/emails/templates")
      .then(({ data }) => setTemplates(data.templates || []))
      .catch(() => {});
  }, [open]);

  const saveTemplate = async () => {
    const body = message.trim();
    if (!body) return toast.error("Écrivez d'abord un message à enregistrer");
    const name = body.split("\n")[0].slice(0, 40) || "Modèle";
    try {
      const { data } = await api.post("/emails/templates", { name, body });
      setTemplates((prev) => [data.template, ...prev]);
      toast.success(`Modèle enregistré : ${data.template.name}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
  };

  const deleteTemplate = async (templateId) => {
    try {
      await api.delete(`/emails/templates/${templateId}`);
      setTemplates((prev) => prev.filter((t) => t.template_id !== templateId));
    } catch { toast.error("Suppression impossible"); }
  };

  const send = async () => {
    if (!email.trim()) return toast.error("Saisissez l'email du client");
    setBusy(true);
    try {
      const { data } = await api.post(`/takeoffs/${planId}/pc-study/send`, {
        to_email: email.trim(), message, start_date: startDate || null,
      });
      toast.success(`Étude PC envoyée à ${data.sent_to}`);
      onSent?.();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-sm" data-testid="pc-send-dialog">
        <DialogHeader>
          <DialogTitle>Envoyer l'étude PC au client</DialogTitle>
          <DialogDescription>
            Le PDF de l'étude gros œuvre (quantités, devis, planning) sera joint à l'email.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="pc-send-email">Email du client</Label>
            <Input id="pc-send-email" type="email" placeholder="client@exemple.fr"
                   value={email} onChange={(e) => setEmail(e.target.value)}
                   data-testid="pc-send-email-input" className="rounded-sm" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="pc-send-message">Mot personnalisé (optionnel)</Label>
            {templates.length > 0 && (
              <div className="flex flex-wrap gap-1.5" data-testid="pc-msg-templates-row">
                {templates.map((t) => (
                  <span key={t.template_id}
                        className="inline-flex items-center gap-1 border border-primary/40 bg-primary/5 rounded-sm px-2 py-0.5 text-[11px]">
                    <button onClick={() => setMessage(t.body)}
                            className="hover:text-primary transition max-w-[160px] truncate"
                            title={t.body} data-testid={`pc-msg-template-${t.template_id}`}>
                      {t.name}
                    </button>
                    <button onClick={() => deleteTemplate(t.template_id)}
                            className="text-muted-foreground hover:text-destructive transition"
                            title="Supprimer ce modèle"
                            data-testid={`pc-msg-template-delete-${t.template_id}`}>
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <Textarea id="pc-send-message" rows={4}
                      placeholder="Bonjour, veuillez trouver ci-joint l'étude gros œuvre de votre projet…"
                      value={message} onChange={(e) => setMessage(e.target.value)}
                      data-testid="pc-send-message-input" className="rounded-sm" />
            {message.trim() && (
              <button onClick={saveTemplate}
                      className="justify-self-start text-[11px] text-primary hover:text-orange-600 transition underline underline-offset-2"
                      data-testid="pc-save-msg-template-btn">
                + Enregistrer ce message comme modèle
              </button>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-sm"
                  data-testid="pc-send-cancel">Annuler</Button>
          <Button onClick={send} disabled={busy} className="rounded-sm gap-2"
                  data-testid="pc-send-confirm">
            <Mail className="h-3.5 w-3.5" />
            {busy ? "Envoi…" : "Envoyer l'étude"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
