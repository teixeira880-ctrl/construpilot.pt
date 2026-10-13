import { useState } from "react";
import { toast } from "sonner";
import { Trash2, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";

export const DeleteAccountCard = () => {
  const { user } = useAuth();
  const hasPassword = user?.has_password !== false;
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (confirm.trim().toUpperCase() !== "SUPPRIMER") {
      return toast.error("Tapez SUPPRIMER pour confirmer");
    }
    setBusy(true);
    try {
      await api.delete("/auth/account", {
        data: { password: hasPassword ? password : null, confirm: confirm.trim() },
      });
      toast.success("Compte supprimé. Vos données ont été effacées.");
      window.location.href = "/";
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Suppression impossible");
    } finally { setBusy(false); }
  };

  return (
    <div className="surface p-5 space-y-3 border border-destructive/40" data-testid="delete-account-card">
      <p className="font-semibold flex items-center gap-2 text-destructive">
        <Trash2 className="h-4 w-4" /> Supprimer mon compte
      </p>
      <p className="text-xs text-muted-foreground">
        Suppression définitive et immédiate de votre compte, vos chantiers, devis, documents,
        photos et messages. Seules les pièces comptables légalement obligatoires sont
        conservées de façon anonymisée. Cette action est irréversible.
      </p>

      {!open ? (
        <Button type="button" variant="outline" onClick={() => setOpen(true)}
                className="rounded-sm w-full gap-2 border-destructive/50 text-destructive hover:bg-destructive/10"
                data-testid="delete-account-open">
          <Trash2 className="h-4 w-4" /> Je veux supprimer mon compte
        </Button>
      ) : (
        <form onSubmit={submit} className="space-y-3" data-testid="delete-account-form">
          <div className="flex items-start gap-2 rounded-sm bg-destructive/10 p-3">
            <AlertTriangle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
            <p className="text-xs text-destructive">
              Toutes vos données seront effacées. Aucune restauration possible.
            </p>
          </div>
          {hasPassword && (
            <div className="grid gap-1.5">
              <Label htmlFor="del-pw" className="text-xs">Votre mot de passe</Label>
              <Input id="del-pw" type="password" value={password} required
                     onChange={(e) => setPassword(e.target.value)}
                     data-testid="delete-account-password" className="rounded-sm" />
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="del-confirm" className="text-xs">
              Tapez <strong>SUPPRIMER</strong> pour confirmer
            </Label>
            <Input id="del-confirm" value={confirm} required placeholder="SUPPRIMER"
                   onChange={(e) => setConfirm(e.target.value)}
                   data-testid="delete-account-confirm" className="rounded-sm" />
          </div>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}
                    className="rounded-sm flex-1" data-testid="delete-account-cancel">
              Annuler
            </Button>
            <Button type="submit" disabled={busy} variant="destructive"
                    className="rounded-sm flex-1 gap-2" data-testid="delete-account-submit">
              <Trash2 className="h-4 w-4" /> {busy ? "…" : "Supprimer définitivement"}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
};
