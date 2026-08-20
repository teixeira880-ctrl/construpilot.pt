import { useLocation } from "react-router-dom";
import { Download, X, Share, PlusSquare } from "lucide-react";
import { usePwaInstall } from "@/hooks/usePwaInstall";

// Carte flottante d'installation — affichée sur les pages applicatives.
// Sur la page d'accueil ("/"), c'est LandingInstallBanner qui prend le relais.
export const InstallPrompt = () => {
  const location = useLocation();
  const { available, ios, install, dismiss } = usePwaInstall();

  if (location.pathname === "/") return null;
  if (!available) return null;

  return (
    <div
      className="fixed inset-x-3 bottom-[84px] md:bottom-6 md:left-auto md:right-6 md:w-[380px] z-[60]
                 rounded-2xl border border-white/10 bg-[#0F1420]/95 backdrop-blur-xl shadow-2xl
                 p-4 animate-in slide-in-from-bottom-4 fade-in duration-300"
      data-testid="pwa-install-prompt"
    >
      <button
        onClick={dismiss}
        aria-label="Fermer"
        data-testid="pwa-install-dismiss"
        className="absolute right-3 top-3 text-white/40 hover:text-white transition-colors"
      >
        <X className="h-4 w-4" />
      </button>

      <div className="flex items-start gap-3">
        <img src="/logo192.png" alt="ConstruPilot" className="h-11 w-11 rounded-xl shrink-0" />
        <div className="min-w-0">
          <div className="text-sm font-semibold text-white">Installer ConstruPilot</div>
          <p className="text-xs text-white/60 mt-0.5">
            Ajoutez l'app à votre écran d'accueil : accès en un tap sur le chantier, plein écran, même hors-ligne.
          </p>
        </div>
      </div>

      {ios ? (
        <div className="mt-3 text-xs text-white/70 space-y-1.5" data-testid="pwa-ios-guide">
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-white/10 shrink-0">1</span>
            Touchez <Share className="inline h-3.5 w-3.5 mx-0.5" /> <b>Partager</b> dans Safari
          </div>
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 place-items-center rounded-md bg-white/10 shrink-0">2</span>
            Choisissez <PlusSquare className="inline h-3.5 w-3.5 mx-0.5" /> <b>Sur l'écran d'accueil</b>
          </div>
        </div>
      ) : (
        <button
          onClick={install}
          data-testid="pwa-install-button"
          className="mt-3 w-full inline-flex items-center justify-center gap-2 rounded-xl
                     bg-[#FF5A00] hover:bg-[#ff6f1f] text-white text-sm font-semibold py-2.5
                     transition-colors active:scale-[0.98]"
        >
          <Download className="h-4 w-4" /> Installer l'application
        </button>
      )}
    </div>
  );
};
