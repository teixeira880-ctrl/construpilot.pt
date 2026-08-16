import { useState } from "react";
import { toast } from "sonner";
import { ShieldCheck, ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

export const TwoFaCard = () => {
  const { user, setUser } = useAuth();
  const [pwd, setPwd] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [tfaEmail, setTfaEmail] = useState(user?.two_fa_email || "");
  const [savingEmail, setSavingEmail] = useState(false);

  if (user?.role !== "admin") return null;
  const enabled = !!user.two_fa_enabled;

  const saveEmail = async (e) => {
    e.preventDefault();
    setSavingEmail(true);
    try {
      const { data } = await api.put("/auth/profile", { two_fa_email: tfaEmail.trim() });
      setUser(data.user);
      toast.success(tfaEmail.trim()
        ? "Les codes 2FA seront envoyés à " + tfaEmail.trim()
        : "Adresse de réception réinitialisée (email du compte)");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Enregistrement impossible");
    } finally { setSavingEmail(false); }
  };

  const enable = async () => {
    setBusy(true);
    try {
      const { data } = await api.put("/auth/2fa", { enabled: true });
      setUser(data.user);
      toast.success("Double authentification activée");
    } catch {
      toast.error("Activation impossible");
    } finally { setBusy(false); }
  };

  const disable = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.put("/auth/2fa", { enabled: false, current_password: pwd });
      setUser(data.user);
      setPwd("");
      setConfirming(false);
      toast.success("Double authentification désactivée");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Désactivation impossible");
    } finally { setBusy(false); }
  };

  return (
    <div className="surface p-5 space-y-4" data-testid="twofa-card">
      <div className="flex items-center justify-between gap-2">
        <p className="font-semibold flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-primary" /> Double authentification
        </p>
        <Badge variant={enabled ? "default" : "secondary"} className="rounded-sm"
               data-testid="twofa-status-badge">
          {enabled ? "Activée" : "Désactivée"}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        À chaque connexion admin, un code à 6 chiffres vous est envoyé par email.
        Personne ne peut accéder à votre compte sans ce code, même avec votre mot de passe.
      </p>

      <form onSubmit={saveEmail} className="space-y-2 rounded-sm border border-border/60 p-3">
        <Label htmlFor="tfa-email" className="text-xs font-medium">
          E-mail de réception des codes 2FA
        </Label>
        <p className="text-[11px] text-muted-foreground">
          Laissez vide pour utiliser l'email du compte ({user.email}). Renseignez une autre adresse
          (ex. votre Gmail) pour y recevoir les codes.
        </p>
        <div className="flex gap-2">
          <Input id="tfa-email" type="email" value={tfaEmail}
                 onChange={(e) => setTfaEmail(e.target.value)}
                 placeholder={user.email}
                 data-testid="twofa-email-input" className="rounded-sm" />
          <Button type="submit" variant="outline" disabled={savingEmail}
                  className="rounded-sm shrink-0" data-testid="twofa-email-save-btn">
            Enregistrer
          </Button>
        </div>
      </form>
      {!enabled ? (
        <Button type="button" onClick={enable} disabled={busy}
                className="rounded-sm w-full gap-2" data-testid="twofa-enable-btn">
          <ShieldCheck className="h-4 w-4" /> Activer la double authentification
        </Button>
      ) : confirming ? (
        <form onSubmit={disable} className="space-y-3">
          <div className="grid gap-1.5">
            <Label htmlFor="tfa-pwd" className="text-xs">
              Mot de passe actuel (requis pour désactiver)
            </Label>
            <Input id="tfa-pwd" type="password" value={pwd} required
                   onChange={(e) => setPwd(e.target.value)}
                   data-testid="twofa-password-input" className="rounded-sm" />
          </div>
          <div className="flex gap-2">
            <Button type="submit" variant="destructive" disabled={busy}
                    className="rounded-sm flex-1" data-testid="twofa-disable-confirm-btn">
              Confirmer la désactivation
            </Button>
            <Button type="button" variant="outline" className="rounded-sm"
                    onClick={() => { setConfirming(false); setPwd(""); }}
                    data-testid="twofa-disable-cancel-btn">
              Annuler
            </Button>
          </div>
        </form>
      ) : (
        <Button type="button" variant="outline" onClick={() => setConfirming(true)}
                className="rounded-sm w-full gap-2" data-testid="twofa-disable-btn">
          <ShieldOff className="h-4 w-4" /> Désactiver
        </Button>
      )}
    </div>
  );
};
