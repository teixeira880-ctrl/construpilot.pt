import { useState } from "react";
import { Smartphone, Download, X, Share, PlusSquare } from "lucide-react";
import { usePwaInstall } from "@/hooks/usePwaInstall";

// Bannière discrète d'installation pour les visiteurs de la page d'accueil.
export const LandingInstallBanner = () => {
  const { available, ios, install, dismiss } = usePwaInstall();
  const [showIos, setShowIos] = useState(false);

  if (!available) return null;

  return (
    <div
      className="border-b border-border bg-secondary/40"
      data-testid="landing-install-banner"
    >
      <div className="mx-auto max-w-[1500px] px-4 py-2 flex items-center gap-3 text-sm">
        <Smartphone className="h-4 w-4 text-primary shrink-0" />
        <span className="flex-1 min-w-0 truncate text-foreground/80">
          Installez l'app <b className="text-foreground">ConstruPilot</b> sur votre téléphone — devis &amp; chantier en un tap.
        </span>

        {ios ? (
          <button
            onClick={() => setShowIos((v) => !v)}
            data-testid="landing-install-ios-btn"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-primary text-primary-foreground
                       px-3 py-1 text-xs font-semibold hover:opacity-90 transition-opacity"
          >
            <Download className="h-3.5 w-3.5" /> Installer
          </button>
        ) : (
          <button
            onClick={install}
            data-testid="landing-install-btn"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-primary text-primary-foreground
                       px-3 py-1 text-xs font-semibold hover:opacity-90 transition-opacity active:scale-95"
          >
            <Download className="h-3.5 w-3.5" /> Installer l'app
          </button>
        )}

        <button
          onClick={dismiss}
          aria-label="Fechar"
          data-testid="landing-install-dismiss"
          className="shrink-0 text-foreground/40 hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {ios && showIos && (
        <div className="mx-auto max-w-[1500px] px-4 pb-2 text-xs text-foreground/70 flex flex-wrap gap-x-4 gap-y-1"
             data-testid="landing-install-ios-guide">
          <span className="inline-flex items-center gap-1">
            1. Touchez <Share className="h-3.5 w-3.5" /> <b>Partager</b> dans Safari
          </span>
          <span className="inline-flex items-center gap-1">
            2. Choisissez <PlusSquare className="h-3.5 w-3.5" /> <b>Sur l'écran d'accueil</b>
          </span>
        </div>
      )}
    </div>
  );
};
