import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, ArrowRight, Sparkles, Search, Camera, Handshake, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";

/**
 * Tour produit 4 étapes, affiché une seule fois par user (localStorage flag).
 * Se déclenche automatiquement sur /dashboard si le flag est absent.
 */
const STEPS = [
  { icon: Sparkles, color: "text-primary", k: "s1", to: "/smart-project" },
  { icon: Search, color: "text-emerald-500", k: "s2", to: "/prix" },
  { icon: Camera, color: "text-amber-500", k: "s3", to: "/dashboard" },
  { icon: Handshake, color: "text-primary", k: "s4", to: "/marketplace" },
];

const KEY = "construpilot_onboarded_v1";

export const OnboardingTour = ({ forceOpen = false, onClose }) => {
  const { user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [open, setOpen] = useState(forceOpen);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!user) return;
    const done = localStorage.getItem(KEY);
    // uniquement sur le tableau de bord : ne jamais interrompre une page de travail (assistant, plans…)
    if (!forceOpen && !done && window.location.pathname === "/dashboard") { const timer = setTimeout(() => setOpen(true), 700); return () => clearTimeout(timer); }
  }, [user, forceOpen]);

  const close = () => { localStorage.setItem(KEY, new Date().toISOString()); setOpen(false); onClose?.(); };
  const next = () => {
    if (step === STEPS.length - 1) close();
    else setStep((s) => s + 1);
  };
  const skip = () => close();
  const goTo = (path) => { close(); navigate(path); };

  if (!open) return null;
  const s = STEPS[step];
  const Icon = s.icon;
  const ch = (typeof window !== "undefined" ? (sessionStorage.getItem("construpilot_utm_source") || "") : "").toLowerCase();
  const chMsg = ch.includes("linkedin") ? "Bem-vindo(a) do LinkedIn 👋"
    : ch.includes("instagram") ? "Bem-vindo(a) do Instagram 👋"
    : ch.includes("facebook") ? "Bem-vindo(a) do Facebook 👋" : "";
  return (
    <div className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm grid place-items-center p-4" data-testid="onboarding-overlay">
      <div className="surface p-8 max-w-lg w-full grid gap-6 relative animate-rise" data-testid="onboarding-tour">
        <button onClick={skip} className="absolute top-4 right-4 h-8 w-8 grid place-items-center rounded-sm hover:bg-secondary" aria-label="Fechar" data-testid="onboarding-skip">
          <X className="h-4 w-4" />
        </button>
        {step === 0 && chMsg && (
          <div className="rounded-sm bg-primary/10 border border-primary/20 px-4 py-2.5 text-sm text-primary font-semibold flex items-center gap-2" data-testid="onboarding-channel">
            <Sparkles className="h-4 w-4" /> {chMsg}
          </div>
        )}
        <div className="flex items-center gap-2 justify-center">
          {STEPS.map((_, i) => (
            <span key={i} className={`h-1.5 rounded-full transition-all ${
              i === step ? "w-8 bg-primary" : i < step ? "w-4 bg-primary/60" : "w-4 bg-border"
            }`} />
          ))}
        </div>
        <div className="flex items-start gap-4">
          <span className={`h-12 w-12 grid place-items-center rounded-sm bg-secondary/60 ${s.color}`}>
            <Icon className="h-6 w-6" />
          </span>
          <div>
            <Badge variant="outline" className="rounded-sm text-[10px] uppercase tracking-wider">
              {t("onb.step")} {step + 1} / {STEPS.length}
            </Badge>
            <p className="font-display text-2xl font-extrabold tracking-tighter mt-2">{t(`onb.${s.k}_title`)}</p>
          </div>
        </div>
        <p className="text-sm text-muted-foreground leading-relaxed">{t(`onb.${s.k}_body`)}</p>
        <div className="flex flex-wrap gap-2 justify-between items-center pt-2 border-t border-border">
          <button onClick={skip} className="text-xs text-muted-foreground hover:text-foreground">
            {t("onb.skip")}
          </button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => goTo(s.to)} data-testid="onboarding-goto" className="rounded-sm gap-1">
              {t(`onb.${s.k}_cta`)}
            </Button>
            <Button size="sm" onClick={next} data-testid="onboarding-next" className="rounded-sm gap-1 hover:bg-orange-600 hover:text-white">
              {step === STEPS.length - 1 ? (
                <><Check className="h-4 w-4" /> {t("onb.finish")}</>
              ) : (
                <>{t("onb.next")} <ArrowRight className="h-4 w-4" /></>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
