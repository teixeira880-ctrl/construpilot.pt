import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Mailbox, Save, Loader2, CheckCircle2, Send, Unplug, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

const PRESETS = {
  gmail: { label: "Gmail / Google Workspace", host: "smtp.gmail.com", port: 465, security: "ssl" },
  outlook: { label: "Outlook / Microsoft 365", host: "smtp.office365.com", port: 587, security: "starttls" },
  ionos: { label: "IONOS", host: "smtp.ionos.fr", port: 465, security: "ssl" },
  ovh: { label: "OVH", host: "ssl0.ovh.net", port: 465, security: "ssl" },
  other: { label: "Autre (manuel)", host: "", port: 465, security: "ssl" },
};

/** Connecte la boîte e-mail de l'entreprise (SMTP) — les devis/factures partent
 *  depuis cette boîte et une copie apparaît dans « Envoyés » (comme Obat). */
export function MailboxDialog({ trigger }) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("gmail");
  const [host, setHost] = useState(PRESETS.gmail.host);
  const [port, setPort] = useState(PRESETS.gmail.port);
  const [security, setSecurity] = useState(PRESETS.gmail.security);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fromName, setFromName] = useState("");
  const [configured, setConfigured] = useState(false);
  const [verified, setVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.get("/users/me/mailbox").then(({ data }) => {
      setConfigured(!!data.configured);
      setVerified(!!data.verified);
      if (data.host) setHost(data.host);
      if (data.port) setPort(data.port);
      if (data.security) setSecurity(data.security);
      setEmail(data.email || "");
      setFromName(data.from_name || "");
      setPassword("");
      const match = Object.entries(PRESETS).find(([, p]) => p.host === data.host);
      setProvider(match ? match[0] : (data.host ? "other" : "gmail"));
    });
  }, [open]);

  const applyPreset = (key) => {
    setProvider(key);
    const p = PRESETS[key];
    if (key !== "other") { setHost(p.host); setPort(p.port); setSecurity(p.security); }
  };

  const save = async () => {
    if (!email || (!password && !configured)) {
      toast.error("E-mail et mot de passe d'application requis");
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.put("/users/me/mailbox", {
        host, port: Number(port) || null, security, email,
        password: password || null, from_name: fromName || null,
      });
      setConfigured(!!data.configured);
      setVerified(!!data.verified);
      setPassword("");
      toast.success("Boîte e-mail connectée et vérifiée ✅");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Connexion impossible");
    } finally { setBusy(false); }
  };

  const sendTest = async () => {
    setTesting(true);
    try {
      const { data } = await api.post("/users/me/mailbox/test");
      toast.success(`E-mail de test envoyé à ${data.sent_to} — vérifiez « Envoyés »`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Test échoué");
    } finally { setTesting(false); }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await api.delete("/users/me/mailbox");
      setConfigured(false); setVerified(false); setEmail(""); setPassword("");
      toast.success("Boîte e-mail déconnectée");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Déconnexion impossible");
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger || (
          <Button variant="outline" size="sm" data-testid="mailbox-open-btn" className="rounded-sm gap-2">
            <Mailbox className="h-4 w-4" /> Boîte e-mail
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-lg max-h-[88vh] overflow-y-auto" data-testid="mailbox-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mailbox className="h-5 w-5 text-primary" /> Connecter ma boîte e-mail
            {verified && (
              <Badge className="bg-emerald-600 hover:bg-emerald-600 gap-1" data-testid="mailbox-verified-badge">
                <CheckCircle2 className="h-3 w-3" /> Connectée
              </Badge>
            )}
          </DialogTitle>
          <DialogDescription>
            Vos devis et factures partiront depuis votre propre boîte et une copie apparaîtra
            automatiquement dans votre dossier <b>« Envoyés »</b> (comme Obat).
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label>Fournisseur</Label>
            <div className="flex flex-wrap gap-2" data-testid="mailbox-providers">
              {Object.entries(PRESETS).map(([key, p]) => (
                <button key={key} type="button" onClick={() => applyPreset(key)}
                        data-testid={`mailbox-provider-${key}`}
                        className={`rounded-sm border px-3 py-1.5 text-xs transition-colors ${
                          provider === key ? "border-primary bg-primary/10 text-primary"
                                           : "border-border hover:border-primary/40"}`}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          {provider === "gmail" && (
            <div className="rounded-sm border border-primary/30 bg-primary/5 p-3 text-xs text-muted-foreground">
              Gmail exige un <b>mot de passe d'application</b> (pas votre mot de passe habituel).
              Activez d'abord la validation en 2 étapes, puis créez-en un ici :{" "}
              <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer"
                 className="text-primary inline-flex items-center gap-1 underline" data-testid="mailbox-gmail-help">
                myaccount.google.com/apppasswords <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          )}

          <div className="grid grid-cols-3 gap-3">
            <div className="grid gap-2 col-span-2">
              <Label>Serveur SMTP</Label>
              <Input value={host} onChange={(e) => setHost(e.target.value)}
                     disabled={provider !== "other"} placeholder="smtp.gmail.com"
                     data-testid="mailbox-host-input" className="rounded-sm h-11" />
            </div>
            <div className="grid gap-2">
              <Label>Port</Label>
              <Input value={port} onChange={(e) => setPort(e.target.value)}
                     disabled={provider !== "other"} inputMode="numeric"
                     data-testid="mailbox-port-input" className="rounded-sm h-11 num" />
            </div>
          </div>

          <div className="grid gap-2">
            <Label>E-mail (adresse d'envoi)</Label>
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="contact@votre-entreprise.fr"
                   data-testid="mailbox-email-input" className="rounded-sm h-11" />
          </div>

          <div className="grid gap-2">
            <Label>Mot de passe d'application</Label>
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                   placeholder={configured ? "•••••••••• (inchangé)" : "Collez le mot de passe d'application"}
                   data-testid="mailbox-password-input" className="rounded-sm h-11" autoComplete="off" />
          </div>

          <div className="grid gap-2">
            <Label>Nom d'expéditeur affiché (optionnel)</Label>
            <Input value={fromName} onChange={(e) => setFromName(e.target.value)}
                   placeholder="Ex : CM Rénovation"
                   data-testid="mailbox-fromname-input" className="rounded-sm h-11" maxLength={80} />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <div className="flex gap-2">
              {verified && (
                <Button variant="outline" onClick={sendTest} disabled={testing}
                        className="rounded-sm gap-2" data-testid="mailbox-test-btn">
                  {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Envoyer un test
                </Button>
              )}
              {configured && (
                <Button variant="ghost" onClick={disconnect} disabled={busy}
                        className="rounded-sm gap-2 text-destructive" data-testid="mailbox-disconnect-btn">
                  <Unplug className="h-4 w-4" /> Déconnecter
                </Button>
              )}
            </div>
            <Button onClick={save} disabled={busy} className="rounded-sm gap-2 bg-primary" data-testid="mailbox-save-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {configured ? "Mettre à jour" : "Connecter"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default MailboxDialog;
