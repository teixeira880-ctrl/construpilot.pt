import { Link } from "react-router-dom";
import { Lock, Sparkles } from "lucide-react";
import { HoverCard, HoverCardTrigger, HoverCardContent } from "@/components/ui/hover-card";
import { LEVEL_LABELS } from "@/components/workspace/navigation";

// Hover the lock → mini benefit card + "Débloquer" CTA → /tarifs.
export const UpgradeLock = ({ title, requiredLevel, benefit, iconSize = 14, className = "" }) => (
  <HoverCard openDelay={120} closeDelay={80}>
    <HoverCardTrigger asChild>
      <span className={`workspace-lock-icon inline-flex items-center ${className}`} data-testid="upgrade-lock"
        aria-label={`Fonction ${LEVEL_LABELS[requiredLevel] || "payante"} — verrouillée`}>
        <Lock size={iconSize} aria-hidden="true" />
      </span>
    </HoverCardTrigger>
    <HoverCardContent align="start" side="right" sideOffset={8} className="w-64 p-3.5" data-testid="upgrade-lock-card"
      onClick={(e) => { e.stopPropagation(); }}>
      <div className="flex items-center gap-1.5 text-primary">
        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="text-[10px] font-bold uppercase tracking-wide">{LEVEL_LABELS[requiredLevel] || "Offre payante"}</span>
      </div>
      <p className="mt-2 text-sm font-semibold leading-snug">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{benefit}</p>
      <Link to="/tarifs" data-testid="upgrade-lock-cta"
        className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-semibold text-primary-foreground transition-opacity hover:opacity-90">
        <Lock className="h-3.5 w-3.5" aria-hidden="true" /> Débloquer
      </Link>
    </HoverCardContent>
  </HoverCard>
);
