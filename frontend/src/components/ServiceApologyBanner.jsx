import { useState, useEffect } from "react";
import { AlertCircle, X } from "lucide-react";

const STORAGE_KEY = "apology_banner_dismissed_v1";

export function ServiceApologyBanner() {
  const [dismissed, setDismissed] = useState(true); // começa oculto para evitar flash

  useEffect(() => {
    try {
      setDismissed(localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      setDismissed(false);
    }
  }, []);

  const close = () => {
    try { localStorage.setItem(STORAGE_KEY, "1"); } catch {}
    setDismissed(true);
  };

  if (dismissed) return null;

  return (
    <div
      data-testid="service-apology-banner"
      className="w-full bg-amber-50 border-b border-amber-200"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-amber-900 leading-relaxed flex-1">
          <span className="font-semibold">📣 Pedido de desculpas · </span>
          O nosso assistente IA (Coach BTP) sofreu falhas intermitentes nas últimas
          semanas devido a problemas técnicos no provedor externo que utilizávamos.
          Já migrámos para uma infraestrutura mais fiável (Claude · OpenAI · Perplexity)
          e o serviço está totalmente operacional. Agradecemos a sua paciência e
          compreensão. — <span className="font-semibold">Equipa ConstruPilot</span>
        </p>
        <button
          type="button"
          onClick={close}
          data-testid="service-apology-banner-close"
          aria-label="Fechar aviso"
          className="shrink-0 rounded-sm p-1 text-amber-700 hover:bg-amber-100 transition-colors"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
