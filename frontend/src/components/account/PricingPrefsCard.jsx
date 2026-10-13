import { useState } from "react";
import { Percent, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Marge par défaut de l'entreprise : pré-remplie à chaque chiffrage (Éditeur de plans).
export function PricingPrefsCard() {
  const { user, checkAuth } = useAuth();
  const [margin, setMargin] = useState(() => {
    const v = Number(user?.target_margin_pct);
    return Number.isFinite(v) && v > 0 ? String(v) : "";
  });
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const v = Number(margin);
    if (margin !== "" && (!Number.isFinite(v) || v < 0 || v > 90)) {
      return toast.error("Introduza uma margem entre 0 e 90 %.");
    }
    setBusy(true);
    try {
      await api.put("/users/me/preferences", { target_margin_pct: margin === "" ? 0 : v });
      await checkAuth();
      toast.success("Margem por omissão guardada");
    } catch {
      toast.error("Não foi possível guardar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface p-5 rounded-md space-y-3" data-testid="pricing-prefs-card">
      <div className="flex items-center gap-2">
        <div className="h-9 w-9 rounded-lg bg-primary/10 grid place-items-center"><Percent className="h-4 w-4 text-primary" /></div>
        <div>
          <p className="font-display font-semibold">Margem por omissão</p>
          <p className="text-xs text-muted-foreground">Pré-preenchida em cada orçamentação no Editor de plantas.</p>
        </div>
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1 max-w-[160px]">
          <Label htmlFor="default-margin" className="text-xs">Marge (%)</Label>
          <Input id="default-margin" type="number" step="1" min="0" max="90" value={margin}
                 onChange={(e) => setMargin(e.target.value)} placeholder="ex : 15"
                 className="rounded-sm num mt-1" data-testid="default-margin-input" />
        </div>
        <Button onClick={save} disabled={busy} className="rounded-sm gap-2" data-testid="default-margin-save">
          <Save className="h-4 w-4" /> Guardar
        </Button>
      </div>
    </div>
  );
}
