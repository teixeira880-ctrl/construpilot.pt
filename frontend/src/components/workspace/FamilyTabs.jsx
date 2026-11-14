import { Link, useLocation } from "react-router-dom";
import { LayoutGrid, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { usePermissions } from "@/context/PermissionContext";
import { useBilling } from "@/context/BillingContext";
import { useI18n } from "@/context/I18nContext";
import { familyOfPath, familyLabel } from "./families";
import { familyMemberLinks, routeMatches } from "./navigation";
import { translatedToolLabel } from "./translations";
import { useWorkspaceCopy } from "./copy";

const OVERVIEW = { pt: "Visão geral", en: "Overview", fr: "Vue d'ensemble" };

export const useFamilyMembers = (family) => {
  const { user } = useAuth();
  const { can } = usePermissions();
  const { tier } = useBilling();
  return family ? familyMemberLinks(family.id, user, can, tier) : [];
};

export const useToolLabel = () => {
  const { t, lang } = useI18n();
  const ui = useWorkspaceCopy();
  return (item) => item.ui ? ui(item.ui) : translatedToolLabel(item, lang, t);
};

// Barra de separadores: transforma as ferramentas de uma família numa só app.
export default function FamilyTabs() {
  const { pathname } = useLocation();
  const { lang } = useI18n();
  const family = familyOfPath(pathname);
  const members = useFamilyMembers(family);
  const label = useToolLabel();
  if (!family || members.length < 1) return null;
  const current = members.filter(m => routeMatches(pathname, m.to)).sort((a, b) => b.to.length - a.to.length)[0]?.to
    || (pathname === family.to ? family.to : null);
  const tab = (active) => `inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-sm border transition-colors ${active
    ? "bg-primary text-primary-foreground border-primary"
    : "bg-card text-foreground border-border hover:border-primary/50"}`;
  return (
    <nav aria-label={familyLabel(family, lang)} data-testid={`family-tabs-${family.id}`}
      className="mx-auto max-w-[1500px] px-4 lg:px-8 pt-4">
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        <Link to={family.to} className={`${tab(current === family.to)} font-semibold`} data-testid={`family-tab-overview-${family.id}`}
          aria-current={current === family.to ? "page" : undefined}>
          <family.icon size={15} aria-hidden="true" />{familyLabel(family, lang)}
        </Link>
        <span className="text-border" aria-hidden="true">|</span>
        {members.map(m => (
          <Link key={m.to} to={m.locked ? "/planos" : m.to} className={tab(current === m.to)}
            aria-current={current === m.to ? "page" : undefined} data-locked={m.locked || undefined}
            data-testid={`family-tab-${m.to.slice(1).replace(/\//g, "-")}`}>
            <m.icon size={15} aria-hidden="true" />{label(m)}
            {m.locked && <Lock size={12} aria-hidden="true" />}
          </Link>
        ))}
        {current !== family.to && (
          <Link to={family.to} className="ms-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary whitespace-nowrap">
            <LayoutGrid size={13} aria-hidden="true" />{OVERVIEW[lang] || OVERVIEW.pt}
          </Link>
        )}
      </div>
    </nav>
  );
}
