import { useExperienceCopy } from "@/components/workspace/experienceCopy";
import { Link, useLocation } from "react-router-dom";
import { LayoutDashboard, FileText, Calculator, Grid2X2, Plus, HardHat, Search } from "lucide-react";
import { AssistantIcon } from "@/components/workspace/navigation";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { meetsLevel, routeMatches, OPEN_WORKSPACE_MENU } from "@/components/workspace/navigation";
import { useWorkspaceCopy } from "@/components/workspace/copy";
const HIDDEN_PREFIXES = ["/pointage", "/sign/", "/e/", "/etude/", "/avis/", "/fiche/", "/login", "/inscription", "/reinitialiser", "/rendu/", "/estimation-partagee/", "/prospection/"];
const HIDDEN_PAGES = ["/", "/particuliers", "/metre", "/investisseurs", "/fonctionnalites"];
export const MobileTabBar = () => {
  const { user } = useAuth();
  const { tier } = useBilling();
  const { can } = usePermissions();
  const { pathname } = useLocation();
  const ui = useWorkspaceCopy();
  const experience = useExperienceCopy();
  if (!user || HIDDEN_PAGES.includes(pathname) || HIDDEN_PREFIXES.some(p => pathname.startsWith(p))) return null;
  const pro = meetsLevel(user, tier, "pro");
  const canAssistant = meetsLevel(user, tier, "particulier_payant");
  const quotes = pro && can("devis");
  const tabs = pro ? [
    { to: "/dashboard", label: ui("home"), icon: LayoutDashboard, test: "accueil" },
    { to: "/chantiers", label: ui("chantiers"), icon: HardHat, test: "chantiers" },
    { to: quotes ? "/devis" : "/plan", label: ui(quotes ? "quotes" : "plan"), icon: quotes ? FileText : Plus, test: quotes ? "devis" : "plan" },
    { to: "/assistant", label: experience("assistantShort"), icon: AssistantIcon, test: "assistant" },
  ] : [
    { to: "/dashboard", label: ui("home"), icon: LayoutDashboard, test: "accueil" },
    { to: "/calculateurs", label: ui("calculators"), icon: Calculator, test: "calculs" },
    canAssistant
      ? { to: "/assistant", label: experience("assistantShort"), icon: AssistantIcon, test: "assistant" }
      : { to: "/prix", label: ui("prices"), icon: Search, test: "prix" },
    { to: "/estimation", label: ui("new"), icon: Plus, test: "novo" },
  ];
  return <nav className="workspace-mobile-tabs" data-testid="mobile-tab-bar" aria-label={ui("menu")}>
    {tabs.map(({ to, label, icon: Icon, test }) => <Link key={to} to={to} aria-current={(routeMatches(pathname, to) || (to === "/devis" && routeMatches(pathname, "/devis-editeur"))) ? "page" : undefined} data-testid={`tab-${test}`}><span><Icon size={21} aria-hidden="true" /></span><span>{label}</span></Link>)}
    <button type="button" aria-haspopup="dialog" onClick={() => window.dispatchEvent(new Event(OPEN_WORKSPACE_MENU))} data-testid="tab-menu"><span><Grid2X2 size={21} aria-hidden="true" /></span><span>{ui("menu")}</span></button>
  </nav>;
};

