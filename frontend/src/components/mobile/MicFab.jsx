import { useLocation, useNavigate } from "react-router-dom";
import { Mic } from "lucide-react";

/**
 * FAB «microfone» global (mobile). Encaminha para o Assistente.
 * Oculto em /demo, /assistant e páginas públicas de assinatura.
 */
const EXCLUDED = ["/demo", "/assistant", "/login", "/inscription"];
const EXCLUDED_PREFIXES = ["/subscrever/", "/sign/", "/e/", "/appel-offres/"];

export default function MicFab() {
  const loc = useLocation();
  const nav = useNavigate();
  const hidden =
    EXCLUDED.some((p) => loc.pathname === p || loc.pathname.startsWith(p + "/")) ||
    EXCLUDED_PREFIXES.some((p) => loc.pathname.startsWith(p));
  if (hidden) return null;
  return (
    <button
      type="button"
      data-testid="mic-fab"
      onClick={() => nav("/assistant")}
      aria-label="Abrir Assistente"
      className="fixed right-4 bottom-20 md:hidden z-30 w-12 h-12 rounded-full bg-primary text-primary-foreground shadow-lg flex items-center justify-center active:scale-95 transition-transform touch-target"
    >
      <Mic className="h-5 w-5" aria-hidden="true" />
    </button>
  );
}
