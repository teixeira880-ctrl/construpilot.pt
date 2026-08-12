import { useMemo, useState } from "react";
import { toast } from "sonner";
import { MessageCircle, Copy, ExternalLink, Link as LinkIcon } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, eur } from "@/lib/api";

const cleanPhone = (raw) => (raw || "").replace(/[^\d+]/g, "").replace(/^00/, "+");

const buildMessage = ({ project, estimation, link }) => {
  const total = estimation?.total_avg;
  const min = estimation?.total_min;
  const max = estimation?.total_max;
  const surface = project?.surface || estimation?.surface;
  const parts = [
    `📐 *Estimation ConstruPilot — ${project?.name || "Projet"}*`,
    surface ? `Surface : ${surface} m²` : null,
    total ? `Budget estimé : *${eur(total)}*${min && max ? ` (fourchette ${eur(min)} – ${eur(max)})` : ""}` : null,
    estimation?.finish_level_name ? `Finition : ${estimation.finish_level_name}` : null,
    "",
    link ? `Voir le détail complet 👉 ${link}` : null,
    "",
    "_Estimation générée avec ConstruPilot — Estimez. Comparez. Construisez._",
  ].filter(Boolean);
  return parts.join("\n");
};

/**
 * WhatsApp share dialog.
 * - `projectId` (optionnel) : si présent, génère un lien public /e/{token} via /api/projects/{id}/share
 * - Sans projectId (estimation non enregistrée), le message est partagé sans lien.
 * - Téléphone optionnel : si absent, WhatsApp ouvre le contact picker.
 */
export function WhatsAppShare({ project, estimation, projectId, trigger }) {
  const [open, setOpen] = useState(false);
  const [phone, setPhone] = useState("");
  const [link, setLink] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const defaultMsg = useMemo(
    () => buildMessage({ project, estimation, link }),
    [project, estimation, link]
  );
  // Sync default message when link changes
  const displayMsg = message || defaultMsg;

  const generateLink = async () => {
    if (!projectId) {
      toast.info("Enregistrez d'abord le projet pour générer un lien public.");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.post(`/projects/${projectId}/share`);
      setLink(data.url);
      // Reset custom message so preview refreshes with link
      setMessage("");
      toast.success("Lien de partage prêt");
    } catch {
      toast.error("Impossible de générer le lien");
    } finally {
      setBusy(false);
    }
  };

  const sendWhatsApp = () => {
    const text = encodeURIComponent(displayMsg);
    const p = cleanPhone(phone);
    const url = p ? `https://wa.me/${p.replace("+", "")}?text=${text}`
                  : `https://wa.me/?text=${text}`;
    window.open(url, "_blank", "noopener");
    toast.success("WhatsApp ouvert");
  };

  const copyMsg = async () => {
    try {
      await navigator.clipboard.writeText(displayMsg);
      toast.success("Message copié");
    } catch {
      toast.error("Copie impossible");
    }
  };

  const copyLink = async () => {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      toast.success("Lien copié");
    } catch {
      toast.error("Copie impossible");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button
            variant="outline"
            data-testid="whatsapp-share-btn"
            className="rounded-sm gap-2 border-emerald-500/50 text-emerald-600 hover:bg-emerald-500 hover:text-white"
          >
            <MessageCircle className="h-4 w-4" /> Partager WhatsApp
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-lg" data-testid="whatsapp-share-dialog">
        <DialogHeader>
          <DialogTitle className="font-display">Envoyer l'estimation par WhatsApp</DialogTitle>
          <DialogDescription>
            Envoyez directement l'estimation à votre client — avec ou sans numéro pré-rempli.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 mt-2">
          <div className="grid gap-2">
            <Label htmlFor="wa-phone">Numéro WhatsApp du client (optionnel)</Label>
            <Input
              id="wa-phone" value={phone} onChange={(e) => setPhone(e.target.value)}
              placeholder="+33 6 12 34 56 78"
              data-testid="whatsapp-phone-input"
              className="rounded-sm h-11 num"
            />
            <p className="text-xs text-muted-foreground">
              Laissez vide pour choisir le contact directement dans WhatsApp.
            </p>
          </div>

          {projectId && (
            <div className="grid gap-2">
              <div className="flex items-center justify-between">
                <Label>Lien public de l'estimation</Label>
                {link ? (
                  <Button size="sm" variant="ghost" onClick={copyLink} data-testid="whatsapp-copy-link" className="rounded-sm gap-1 text-xs">
                    <Copy className="h-3 w-3" /> Copier
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" onClick={generateLink} disabled={busy} data-testid="whatsapp-generate-link" className="rounded-sm gap-1 text-xs">
                    <LinkIcon className="h-3 w-3" /> {busy ? "…" : "Générer un lien"}
                  </Button>
                )}
              </div>
              {link ? (
                <a href={link} target="_blank" rel="noreferrer" className="text-xs font-mono truncate text-primary hover:underline flex items-center gap-1" data-testid="whatsapp-share-link">
                  <ExternalLink className="h-3 w-3 shrink-0" /> {link}
                </a>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Un lien lecture seule sera généré pour que votre client consulte l'estimation.
                </p>
              )}
            </div>
          )}

          <div className="grid gap-2">
            <Label>Message</Label>
            <Textarea
              value={displayMsg}
              onChange={(e) => setMessage(e.target.value)}
              rows={8}
              data-testid="whatsapp-message"
              className="rounded-sm text-xs font-mono"
            />
            <div className="flex justify-between">
              <p className="text-xs text-muted-foreground">Vous pouvez modifier le message avant l'envoi.</p>
              <Button size="sm" variant="ghost" onClick={copyMsg} className="rounded-sm gap-1 text-xs h-7">
                <Copy className="h-3 w-3" /> Copier le message
              </Button>
            </div>
          </div>
        </div>

        <div className="flex gap-3 pt-4 border-t border-border">
          <Button variant="outline" onClick={() => setOpen(false)} className="rounded-sm">Fermer</Button>
          <Button
            onClick={sendWhatsApp}
            data-testid="whatsapp-send-btn"
            className="ml-auto rounded-sm gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            <MessageCircle className="h-4 w-4" /> Ouvrir WhatsApp
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default WhatsAppShare;
