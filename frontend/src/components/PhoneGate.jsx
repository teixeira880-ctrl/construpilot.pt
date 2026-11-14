import { useState } from "react";
import { toast } from "sonner";
import { Phone } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { api } from "@/lib/api";
import { validPhone } from "@/lib/phone";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Telefone obrigatório em todas as contas (14/11, Martinho): as contas criadas antes desta regra ou por Google
 * (sem telefone) têm de o indicar antes de continuar a usar a plataforma. Sem SMS — só validação do formato.
 */
export default function PhoneGate() {
  const { user, setUser } = useAuth();
  const { t } = useI18n();
  const [phone, setPhone] = useState("");
  const [busy, setBusy] = useState(false);
  if (!user || !user.phone_required) return null;

  const save = async (e) => {
    e.preventDefault();
    if (!validPhone(phone)) {
      toast.error(t("login.phone_invalid"));
      return;
    }
    setBusy(true);
    try {
      const { data } = await api.put("/auth/profile", { phone: phone.trim() });
      setUser({ ...user, ...(data?.user || {}), phone: data?.user?.phone || phone.trim(), phone_required: false });
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("login.phone_invalid"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 p-4" role="dialog" aria-modal="true"
         data-testid="phone-gate">
      <form onSubmit={save} className="w-full max-w-sm rounded-md bg-background p-6 shadow-xl grid gap-4">
        <div className="flex items-center gap-2 font-semibold">
          <Phone className="h-5 w-5" /> {t("login.phone")}
        </div>
        <div className="grid gap-2">
          <Label htmlFor="phone-gate-input">{t("login.phone")}</Label>
          <Input id="phone-gate-input" required type="tel" autoComplete="tel" inputMode="tel" value={phone}
                 onChange={(e) => setPhone(e.target.value)} placeholder="+351 912 345 678" data-testid="phone-gate-input" className="h-11" />
        </div>
        <Button type="submit" disabled={busy} data-testid="phone-gate-submit" className="h-11">OK</Button>
      </form>
    </div>
  );
}
