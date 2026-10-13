import { useState } from "react";
import { Smartphone, Download, X, Share, PlusSquare } from "lucide-react";
import { usePwaInstall } from "@/hooks/usePwaInstall";
import { useI18n } from "@/context/I18nContext";

// Bannière discrète d'installation pour les visiteurs de la page d'accueil.
export const LandingInstallBanner = () => {
  const { available, ios, install, dismiss } = usePwaInstall();
  const [showIos, setShowIos] = useState(false);
  const { lang } = useI18n();
  const pt = lang === "pt";

  if (!available) return null;

  return (
    <div
      className="border-b border-border bg-secondary/40"
      data-testid="landing-install-banner"
    >
      <div className="mx-auto max-w-[1500px] px-4 py-2 flex items-center gap-3 text-sm">
        <Smartphone className="h-4 w-4 text-primary shrink-0" />
        <span className="flex-1 min-w-0 truncate text-foreground/80">
          {pt ? <>Instale a app <b className="text-foreground">ConstruPilot</b> no seu telemóvel — orçamentos e obras num toque.</>
              : <>Installez l'app <b className="text-foreground">ConstruPilot</b> sur votre téléphone — devis &amp; chantier en un tap.</>}
        </span>

        {ios ? (
          <button
            onClick={() => setShowIos((v) => !v)}
            data-testid="landing-install-ios-btn"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-primary text-primary-foreground
                       px-3 py-1 text-xs font-semibold hover:opacity-90 transition-opacity"
          >
            <Download className="h-3.5 w-3.5" /> {pt ? "Instalar" : "Installer"}
          </button>
        ) : (
          <button
            onClick={install}
            data-testid="landing-install-btn"
            className="shrink-0 inline-flex items-center gap-1.5 rounded-full bg-primary text-primary-foreground
                       px-3 py-1 text-xs font-semibold hover:opacity-90 transition-opacity active:scale-95"
          >
            <Download className="h-3.5 w-3.5" /> {pt ? "Instalar a app" : "Installer l'app"}
          </button>
        )}

        <button
          onClick={dismiss}
          aria-label={pt ? "Fechar" : "Fermer"}
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
            1. {pt ? "Toque em" : "Touchez"} <Share className="h-3.5 w-3.5" /> <b>{pt ? "Partilhar" : "Partager"}</b> {pt ? "no Safari" : "dans Safari"}
          </span>
          <span className="inline-flex items-center gap-1">
            2. {pt ? "Escolha" : "Choisissez"} <PlusSquare className="h-3.5 w-3.5" /> <b>{pt ? "Adicionar ao ecrã principal" : "Sur l'écran d'accueil"}</b>
          </span>
        </div>
      )}
    </div>
  );
};
