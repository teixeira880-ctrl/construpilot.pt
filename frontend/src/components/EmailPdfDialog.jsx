import { useState } from "react";
import { toast } from "sonner";
import { Mail, Send } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Envoie le devis PDF par email via Resend.
 * - mode="draft": envoie {project, estimation, advice} à /api/estimation/pdf/email
 * - mode="saved": envoie {project_id} à /api/projects/{id}/pdf/email  (non implémenté ici,
 *   on utilise le même endpoint public en repassant project+estimation depuis le projet chargé).
 */
export const EmailPdfDialog = ({ project, estimation, advice = "", trigger }) => {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    to: user?.email || "",
    message: "",
  });

  const submit = async (e) => {
    e.preventDefault();
    if (!form.to) return toast.error("Adresse email requise");
    setBusy(true);
    try {
      await api.post("/estimation/pdf/email", {
        project, estimation, advice,
        to: form.to,
        message: form.message,
      });
      toast.success(`Orçamento enviado a ${form.to}`);
      setOpen(false);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Envoi impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" data-testid="email-pdf-btn" className="rounded-sm gap-2">
            <Mail className="h-4 w-4" /> Envoyer par email
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm sm:max-w-lg" data-testid="email-pdf-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Envoyer le devis par email</DialogTitle>
          <DialogDescription>
            Nous préparons un PDF détaillé et l'envoyons directement au destinataire.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-2">
            <Label>Adresse email du destinataire</Label>
            <Input
              type="email" required value={form.to}
              onChange={(e) => setForm({ ...form, to: e.target.value })}
              data-testid="email-pdf-to"
              placeholder="client@example.com"
              className="rounded-sm h-11"
            />
          </div>
          <div className="grid gap-2">
            <Label>Message (optionnel)</Label>
            <Textarea
              rows={4} value={form.message}
              onChange={(e) => setForm({ ...form, message: e.target.value })}
              data-testid="email-pdf-message"
              placeholder="Olá, segue em anexo a estimativa detalhada dos seus trabalhos..."
              className="rounded-sm"
            />
          </div>
          <div className="text-xs text-muted-foreground">
            Depuis <b>onboarding@resend.dev</b> · le destinataire reçoit le PDF en pièce jointe.
          </div>
          <Button type="submit" disabled={busy} data-testid="email-pdf-send" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Send className="h-4 w-4" /> {busy ? "Envoi…" : "Envoyer le devis"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};
