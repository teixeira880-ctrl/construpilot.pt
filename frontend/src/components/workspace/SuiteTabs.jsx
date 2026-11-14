import { Link, useLocation } from "react-router-dom";
import { LayoutGrid, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { usePermissions } from "@/context/PermissionContext";
import { useBilling } from "@/context/BillingContext";
import { useI18n } from "@/context/I18nContext";
import { suiteOfPath, suiteLabel } from "./suites";
import { suiteMemberLinks, routeMatches } from "./navigation";
import { translatedToolLabel } from "./translations";
import { useWorkspaceCopy } from "./copy";

const OVERVIEW = { pt: "Visão geral", fr: "Vue d'ensemble", en: "Overview" };

export const useSuiteMembers = (suite) => {
  const { user } = useAuth();
  const perms = usePermissions();
  const can = perms?.can || (() => true);
  const { tier } = useBilling();
  return suite ? suiteMemberLinks(suite.id, user, can, tier) : [];
};

export const useToolLabel = () => {
  const { t, lang } = useI18n();
  const ui = useWorkspaceCopy();
  return (item) => item.ui ? ui(item.ui) : translatedToolLabel(item, lang, t);
};

// Barra de separadores: junta as ferramentas de uma suite numa só app.
export default function SuiteTabs() {
  const { pathname } = useLocation();
  const { lang } = useI18n();
  const suite = suiteOfPath(pathname);
  const members = useSuiteMembers(suite);
  const label = useToolLabel();
  if (!suite || members.length < 1) return null;
  const current = members.filter(m => routeMatches(pathname, m.to)).sort((a, b) => b.to.length - a.to.length)[0]?.to
    || (pathname === suite.to ? suite.to : null);
  const tab = (active) => `inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1.5 text-sm border transition-colors ${active
    ? "bg-primary text-primary-foreground border-primary"
    : "bg-card text-foreground border-border hover:border-primary/50"}`;
  return (
    <nav aria-label={suiteLabel(suite, lang)} data-testid={`suite-tabs-${suite.id}`}
      className="mx-auto max-w-[1500px] px-4 lg:px-8 pt-4">
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        <Link to={suite.to} className={`${tab(current === suite.to)} font-semibold`} data-testid={`suite-tab-overview-${suite.id}`}
          aria-current={current === suite.to ? "page" : undefined}>
          <suite.icon size={15} aria-hidden="true" />{suiteLabel(suite, lang)}
        </Link>
        <span className="text-border" aria-hidden="true">|</span>
        {members.map(m => (
          <Link key={m.to} to={m.locked ? "/planos" : m.to} className={tab(current === m.to)}
            aria-current={current === m.to ? "page" : undefined} data-locked={m.locked || undefined}
            data-testid={`suite-tab-${m.to.slice(1).replace(/\//g, "-")}`}>
            <m.icon size={15} aria-hidden="true" />{label(m)}
            {m.locked && <Lock size={12} aria-hidden="true" />}
          </Link>
        ))}
        {current !== suite.to && (
          <Link to={suite.to} className="ms-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary whitespace-nowrap">
            <LayoutGrid size={13} aria-hidden="true" />{OVERVIEW[lang] || OVERVIEW.pt}
          </Link>
        )}
      </div>
    </nav>
  );
}
