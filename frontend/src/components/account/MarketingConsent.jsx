import { useState } from "react";
import { Mail, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

// Consentimento para os e-mails de novidades e ofertas (campanhas do Agente CEO).
// Sem consentimento explícito, a conta não recebe campanhas (RGPD).

const TEXT = {
  title: "E-mails de novidades e ofertas",
  desc: "Receba por e-mail as novidades, guias e ofertas do ConstruPilot. Pode cancelar a qualquer momento.",
  on: "Ativado", off: "Desativado",
  saved_on: "Vai passar a receber as novidades do ConstruPilot.",
  saved_off: "Já não vai receber e-mails de novidades.",
  error: "Não foi possível guardar a sua escolha.",
  banner: "Quer receber por e-mail as novidades e ofertas do ConstruPilot?",
  yes: "Sim, quero receber", no: "Não, obrigado",
};

function useConsent() {
  const { user, setUser } = useAuth();
  const [busy, setBusy] = useState(false);
  const save = async (consent, source) => {
    setBusy(true);
    try {
      await api.put("/auth/marketing-consent", { consent, source });
      setUser((u) => (u ? { ...u, marketing_consent: consent } : u));
      toast.success(consent ? TEXT.saved_on : TEXT.saved_off);
    } catch {
      toast.error(TEXT.error);
    } finally {
      setBusy(false);
    }
  };
  return { user, busy, save };
}

/** Interruptor na página Conta. */
export function MarketingConsentCard() {
  const { user, busy, save } = useConsent();
  const on = user?.marketing_consent === true;
  return (
    <section className="surface p-4 border border-border" data-testid="marketing-consent-section">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <h2 className="font-semibold text-sm flex items-center gap-2"><Mail className="h-4 w-4" />{TEXT.title}</h2>
          <p className="text-xs text-muted-foreground">{TEXT.desc}</p>
        </div>
        <Button type="button" size="sm" variant={on ? "default" : "outline"} disabled={busy}
                onClick={() => save(!on, "account")} aria-pressed={on}
                data-testid="marketing-consent-toggle" className="rounded-sm">
          {on ? TEXT.on : TEXT.off}
        </Button>
      </div>
    </section>
  );
}

/** Aviso discreto no painel, só para quem ainda não escolheu. */
export function MarketingConsentBanner() {
  const { user, busy, save } = useConsent();
  const [hidden, setHidden] = useState(() => {
    try { return sessionStorage.getItem("cp_mkt_banner_hidden") === "1"; } catch { return false; }
  });
  let demo = false;
  try { demo = localStorage.getItem("is_demo") === "true"; } catch { /* noop */ }
  // Nunca nas contas de demonstração (stand Web Summit).
  if (!user || demo || user.marketing_consent === true || user.marketing_consent === false || hidden) return null;
  const later = () => {
    setHidden(true);
    try { sessionStorage.setItem("cp_mkt_banner_hidden", "1"); } catch { /* noop */ }
  };
  return (
    <div className="surface p-3 border border-border flex items-center gap-3 flex-wrap" role="region"
         aria-label={TEXT.title} data-testid="marketing-consent-banner">
      <Mail className="h-4 w-4 text-primary shrink-0" />
      <p className="text-sm flex-1 min-w-[12rem]">{TEXT.banner}</p>
      <div className="flex items-center gap-2">
        <Button type="button" size="sm" disabled={busy} onClick={() => save(true, "dashboard_banner")}
                className="rounded-sm" data-testid="marketing-consent-yes">{TEXT.yes}</Button>
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={() => save(false, "dashboard_banner")}
                className="rounded-sm" data-testid="marketing-consent-no">{TEXT.no}</Button>
        <button type="button" onClick={later} aria-label="Fechar" className="p-1 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
