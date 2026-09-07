import { toast } from "sonner";
import { Bell, BellOff, BellRing } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePushNotifications } from "@/hooks/usePushNotifications";

/** Botão compacto de ativação das notificações push (página Dashboard).
 *  - Esconde automaticamente o botão se o browser não suportar Push.
 *  - Toast + testids para o testing agent. */
export default function PushToggle({ variant = "outline", size = "sm" }) {
  const { supported, permission, subscribed, busy, subscribe, unsubscribe } =
    usePushNotifications();

  if (!supported) return null;

  const handle = async () => {
    try {
      if (subscribed) {
        await unsubscribe();
        toast.success("Notificações push desativadas");
      } else {
        await subscribe();
        toast.success("Notificações push ativadas");
      }
    } catch (err) {
      toast.error(err?.message || "Falha na ativação");
    }
  };

  const label = subscribed
    ? "Notificações ativadas"
    : permission === "denied"
    ? "Notificações bloqueadas"
    : "Ativar notificações";

  const Icon = subscribed ? BellRing : permission === "denied" ? BellOff : Bell;

  return (
    <Button
      onClick={handle}
      disabled={busy || permission === "denied"}
      variant={variant}
      size={size}
      data-testid="push-toggle-btn"
      data-subscribed={subscribed ? "1" : "0"}
      className="rounded-sm gap-2"
    >
      <Icon className="h-4 w-4" /> {label}
    </Button>
  );
}
