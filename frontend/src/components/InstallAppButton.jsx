import { useEffect, useState } from "react";
import { Download, Share } from "lucide-react";

// Botão «Instalar app» (PWA). Mostra-se quando o browser oferece beforeinstallprompt.
// No iOS, abre um diálogo com instruções manuais (Partilhar → Adicionar ao ecrã principal).
// Esconde-se quando a app já corre em modo standalone ou já foi instalada.
export default function InstallAppButton({ className = "", compact = false }) {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  const [showIos, setShowIos] = useState(false);

  const isStandalone =
    typeof window !== "undefined" &&
    ((window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
      window.navigator?.standalone === true);

  const isIos =
    typeof navigator !== "undefined" &&
    /iphone|ipad|ipod/i.test(navigator.userAgent) &&
    !window.MSStream;

  useEffect(() => {
    const onPrompt = (e) => {
      e.preventDefault();
      setPrompt(e);
    };
    const onInstalled = () => {
      setInstalled(true);
      setPrompt(null);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  if (isStandalone || installed) return null;
  if (!prompt && !isIos) return null;

  const onClick = async () => {
    if (prompt) {
      try {
        prompt.prompt();
        const { outcome } = await prompt.userChoice;
        if (outcome === "accepted") setPrompt(null);
      } catch {
        /* ignorar */
      }
    } else if (isIos) {
      setShowIos(true);
    }
  };

  const btnClass = compact
    ? `inline-flex items-center gap-1.5 rounded-md border border-emerald-700/20 bg-white px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-50 ${className}`
    : `inline-flex items-center gap-2 rounded-md border border-emerald-700/20 bg-white px-3 py-1.5 text-sm font-medium text-emerald-800 hover:bg-emerald-50 ${className}`;

  return (
    <>
      <button
        type="button"
        data-testid="install-app-button"
        onClick={onClick}
        className={btnClass}
        aria-label="Instalar app"
      >
        <Download className={compact ? "h-3.5 w-3.5" : "h-4 w-4"} aria-hidden="true" />
        Instalar app
      </button>

      {showIos && (
        <div
          role="dialog"
          aria-modal="true"
          data-testid="install-app-ios-dialog"
          className="fixed inset-0 z-[9999] flex items-end sm:items-center justify-center bg-black/40 p-4"
          onClick={() => setShowIos(false)}
        >
          <div
            className="w-full max-w-sm rounded-xl bg-white p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 text-emerald-800 font-semibold mb-2">
              <Share className="h-5 w-5" aria-hidden="true" />
              Instalar no iPhone / iPad
            </div>
            <p className="text-sm text-muted-foreground">
              Toque em Partilhar no Safari e depois em «Adicionar ao ecrã principal».
            </p>
            <div className="mt-4 flex justify-end">
              <button
                onClick={() => setShowIos(false)}
                data-testid="install-app-ios-close"
                className="px-4 py-1.5 rounded-md bg-emerald-700 text-white text-sm hover:bg-emerald-800"
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
