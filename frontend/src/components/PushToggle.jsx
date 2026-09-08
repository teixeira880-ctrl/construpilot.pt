import { toast } from "sonner";
import { Bell, BellOff, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePushNotifications } from "@/hooks/usePushNotifications";
import { useI18n } from "@/context/I18nContext";

/** Botão compacto de ativação das notificações push (página Dashboard).
 *  - Esconde automaticamente o botão se o browser não suportar Push.
 *  - Toast + testids para o testing agent. */
export default function PushToggle({ variant = "outline", size = "sm" }) {
  const { supported, permission, subscribed, busy, subscribe, unsubscribe } =
    usePushNotifications();
  const { t } = useI18n();

  if (!supported) return null;

  const handle = async () => {
    try {
      if (subscribed) {
        await unsubscribe();
        toast.success(t("push.toast_off"));
      } else {
        await subscribe();
        toast.success(t("push.toast_on"));
      }
    } catch (err) {
      toast.error(err?.message || t("push.toast_error"));
    }
  };

  const label = subscribed
    ? t("push.enabled")
    : permission === "denied"
    ? t("push.blocked")
    : t("push.enable");

  const Icon = subscribed ? BellRing : permission === "denied" ? BellOff : Bell;

  return (
    <Button
      onClick={handle}
      disabled={busy || permission === "denied"}
      variant={variant}
      size={size}
      data-testid="push-toggle-btn"
      data-subscribed={subscribed ? "1" : "0"}
      aria-label={label}
      title={label}
      className="rounded-sm gap-2"
    >
      <Icon className="h-4 w-4" /> {label}
    </Button>
  );
}
