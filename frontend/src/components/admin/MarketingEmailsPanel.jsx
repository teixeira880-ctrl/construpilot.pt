import { useState } from "react";
import { api, API } from "@/lib/api";
import { Loader2, Eye, Send, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const EMAILS = [
  {
    key: "welcome",
    title: "Bienvenue (nouveaux inscrits)",
    desc: "Envoyé automatiquement J+1 après l'inscription. Présentation produit + essai gratuit.",
    previewUrl: () => `${API}/admin/welcome-email/preview`,
    sendPath: "/admin/welcome-email/test",
    sendBody: (to) => ({ to }),
  },
  {
    key: "prospect-particulier",
    title: "Prospect — Particulier",
    desc: "Pour les leads ayant demandé une estimation. Angle : estimation, prix justes, trouver un pro.",
    previewUrl: () => `${API}/admin/prospect-email/preview?audience=particulier`,
    sendPath: "/admin/prospect-email/test",
    sendBody: (to) => ({ to, audience: "particulier" }),
  },
  {
    key: "prospect-pro",
    title: "Prospect — Professionnel",
    desc: "Pour les artisans / BET non clients. Angle : métré, devis déterministes, StructuroPilot, Factur-X.",
    previewUrl: () => `${API}/admin/prospect-email/preview?audience=pro`,
    sendPath: "/admin/prospect-email/test",
    sendBody: (to) => ({ to, audience: "pro" }),
  },
];

const parseEmails = (raw) =>
  (raw || "")
    .split(/[,;\s]+/)
    .map((e) => e.trim().toLowerCase())
    .filter((e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));

function EmailCard({ cfg }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const valid = parseEmails(to);
  const count = new Set(valid).size;

  const send = async () => {
    if (count === 0) {
      toast.error("Entrez au moins une adresse e-mail valide");
      return;
    }
    if (!window.confirm(`Envoyer « ${cfg.title} » à ${count} destinataire(s) maintenant ?`)) return;
    setBusy(true);
    try {
      const { data } = await api.post(cfg.sendPath, cfg.sendBody(to));
      toast.success(`${data.sent} envoyé(s)${data.failed ? ` · ${data.failed} échec(s)` : ""} sur ${data.recipients}`);
      setTo("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface rounded-md p-4 space-y-3" data-testid={`admin-marketing-email-${cfg.key}`}>
      <div>
        <p className="font-semibold">{cfg.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{cfg.desc}</p>
      </div>
      <Textarea
        placeholder="Plusieurs adresses — séparées par une virgule, un point-virgule ou un retour à la ligne&#10;ex : jean@exemple.fr, marie@exemple.fr"
        value={to}
        onChange={(e) => setTo(e.target.value)}
        rows={2}
        className="rounded-sm text-sm resize-y"
        data-testid={`admin-marketing-recipients-${cfg.key}`}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground" data-testid={`admin-marketing-count-${cfg.key}`}>
          {count > 0 ? `${count} destinataire(s) valide(s)` : "Aucune adresse valide"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline" size="sm" className="rounded-sm gap-2"
            onClick={() => window.open(cfg.previewUrl(), "_blank", "noopener")}
            data-testid={`admin-marketing-preview-${cfg.key}`}
          >
            <Eye className="h-4 w-4" /> Aperçu
          </Button>
          <Button
            variant="default" size="sm" className="rounded-sm gap-2"
            onClick={send} disabled={busy || count === 0}
            data-testid={`admin-marketing-send-${cfg.key}`}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Envoyer
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function MarketingEmailsPanel() {
  return (
    <div className="surface rounded-md p-5 space-y-3" data-testid="admin-marketing-emails-panel">
      <div className="flex items-start gap-2">
        <Mail className="h-5 w-5 text-primary mt-0.5" />
        <div>
          <h3 className="font-display font-bold text-lg">Emails publicitaires</h3>
          <p className="text-sm text-muted-foreground">
            Modèles prêts à l'envoi : bienvenue (auto J+1) et prospects. Prévisualisez dans un
            nouvel onglet, saisissez une ou plusieurs adresses, puis envoyez directement.
          </p>
        </div>
      </div>
      <div className="grid gap-3">
        {EMAILS.map((cfg) => <EmailCard key={cfg.key} cfg={cfg} />)}
      </div>
    </div>
  );
}
