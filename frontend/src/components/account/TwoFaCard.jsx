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

  if (user?.role !== "admin") return null;
  const enabled = !!user.two_fa_enabled;

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
