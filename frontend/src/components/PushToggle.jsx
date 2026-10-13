import { toast } from "sonner";
import { Bell, BellOff, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { useI18n } from "@/context/I18nContext";

/** Bouton compact d'activation des notifications push (page Dashboard).
 *  - Cache automatiquement le bouton si le navigateur ne supporte pas Push.
 *  - Toast + testids pour le testing agent. */
export default function PushToggle({ variant = "outline", size = "sm", testId = "push-toggle-btn" }) {
  const { lang } = useI18n();
  const copy = {
    fr: ["Não foi possível ativar", "Não foi possível ativar", "Não foi possível ativar", "Não foi possível ativar", "Não foi possível ativar", "Não foi possível ativar"],
    pt: ["Notificações ativadas", "Notificações bloqueadas", "Ativar notificações", "Notificações desativadas", "Notificações ativadas", "Não foi possível ativar"],
    en: ["Notifications enabled", "Notifications blocked", "Enable notifications", "Push notifications disabled", "Push notifications enabled", "Activation failed"],
  };
  const ui = copy[lang] || copy.fr;
  const { supported, permission, subscribed, busy, subscribe, unsubscribe } =
    usePushNotifications();

  if (!supported) return null;

  const handle = async () => {
    try {
      if (subscribed) {
        await unsubscribe();
        toast.success(ui[3]);
      } else {
        await subscribe();
        toast.success(ui[4]);
      }
    } catch (err) {
      toast.error(err?.message || ui[5]);
    }
  };

  const label = subscribed
    ? ui[0]
    : permission === "denied"
    ? ui[1]
    : ui[2];

  const Icon = subscribed ? BellRing : permission === "denied" ? BellOff : Bell;

  return (
    <Button
      onClick={handle}
      disabled={busy || permission === "denied"}
      variant={variant}
      size={size}
      data-testid={testId}
      data-subscribed={subscribed ? "1" : "0"}
      className="rounded-sm gap-2"
    >
      <Icon className="h-4 w-4" /> {label}
    </Button>
  );
}
