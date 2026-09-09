import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

export const PasswordForm = () => {
  const { user, setUser } = useAuth();
  // Un compte Google sans mot de passe passe en mode « définir » (pas d'ancien mot de passe).
  const hasPassword = user?.has_password !== false;
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (next.length < 8) return toast.error("Mot de passe : 8 caractères minimum");
    if (next !== confirm) return toast.error("La confirmation ne correspond pas");
    setBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: hasPassword ? current : null, new_password: next,
      });
      toast.success(hasPassword
        ? "Mot de passe changé — vos autres sessions ont été déconnectées"
        : "Mot de passe défini — vous pouvez maintenant vous connecter par email");
      setCurrent(""); setNext(""); setConfirm("");
      setUser({ ...user, must_change_password: false, has_password: true });
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Opération impossible");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="surface p-5 space-y-4" data-testid="change-password-form">
      <p className="font-semibold flex items-center gap-2">
        <KeyRound className="h-4 w-4 text-primary" />
        {hasPassword ? "Changer mon mot de passe" : "Définir un mot de passe"}
      </p>
      {!hasPassword && (
        <p className="text-xs text-muted-foreground" data-testid="set-password-hint">
          Votre compte est connecté via Google. Définissez un mot de passe pour pouvoir
          aussi vous connecter par email — aucun « ancien mot de passe » n'est requis.
        </p>
      )}
      {hasPassword && (
        <div className="grid gap-1.5">
          <Label htmlFor="cur-pw" className="text-xs">Mot de passe actuel</Label>
          <Input id="cur-pw" type="password" value={current} required
                 onChange={(e) => setCurrent(e.target.value)}
                 data-testid="current-password-input" className="rounded-sm" />
        </div>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor="new-pw" className="text-xs">
          {hasPassword ? "Nova palavra-passe" : "Palavra-passe"} (mínimo 8 caracteres)
        </Label>
        <Input id="new-pw" type="password" value={next} required minLength={8}
               onChange={(e) => setNext(e.target.value)}
               data-testid="new-password-input" className="rounded-sm" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="conf-pw" className="text-xs">Confirmer le mot de passe</Label>
        <Input id="conf-pw" type="password" value={confirm} required
               onChange={(e) => setConfirm(e.target.value)}
               data-testid="confirm-password-input" className="rounded-sm" />
      </div>
      <Button type="submit" disabled={busy} className="rounded-sm w-full gap-2"
              data-testid="change-password-submit">
        <ShieldCheck className="h-4 w-4" />
        {busy ? "…" : (hasPassword ? "Mettre à jour le mot de passe" : "Définir le mot de passe")}
      </Button>
      <p className="text-[10px] text-muted-foreground">
        Par sécurité, toutes vos autres sessions seront déconnectées.
      </p>
    </form>
  );
};
