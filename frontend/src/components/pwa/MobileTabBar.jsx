import { useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Plus, Calculator, User, LayoutGrid } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import "@/styles/workspace-ambient.css";

// Rotas em ecrã inteiro / públicas onde a barra de separadores não deve aparecer
const HIDDEN_PREFIXES = ["/pointage", "/sign/", "/e/", "/etude/", "/avis/", "/fiche/", "/login", "/registo", "/inscription"];

// `id` mantém os data-testid históricos (tab-accueil, tab-devis…).
const PRO_TABS = [
  { to: "/dashboard", id: "accueil", label: "Início", icon: LayoutDashboard },
  { to: "/orcamentos", id: "devis", label: "Orçamentos", icon: FileText, match: ["/orcamentos", "/devis"] },
  { to: "/devis-editeur", id: "nouveau", label: "Novo", icon: Plus, primary: true },
  { to: "/apps", id: "ferramentas", label: "Ferramentas", icon: LayoutGrid },
  { to: "/conta", id: "compte", label: "Conta", icon: User, match: ["/conta", "/compte"] },
];
const PERSONAL_TABS = [
  { to: "/dashboard", id: "accueil", label: "Início", icon: LayoutDashboard },
  { to: "/calculadoras", id: "calculs", label: "Cálculos", icon: Calculator, match: ["/calculadoras", "/calculateurs"] },
  { to: "/estimativa", id: "nouveau", label: "Estimar", icon: Plus, primary: true },
  { to: "/apps", id: "ferramentas", label: "Ferramentas", icon: LayoutGrid },
  { to: "/conta", id: "compte", label: "Conta", icon: User, match: ["/conta", "/compte"] },
];

export const MobileTabBar = () => {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  if (!user) return null;
  if (HIDDEN_PREFIXES.some((p) => location.pathname.startsWith(p))) return null;
  const isPro = user.account_type !== "particulier" || user.role === "admin";
  const tabs = isPro ? PRO_TABS : PERSONAL_TABS;

  const isActive = (tab) =>
    tab.to === "/dashboard" ? location.pathname === "/dashboard"
      : (tab.match || [tab.to]).some((p) => location.pathname.startsWith(p));

  return (
    <nav
      className="workspace-mobile-tabs md:hidden fixed inset-x-0 bottom-0 z-50 border-t pb-[env(safe-area-inset-bottom)]"
      data-testid="mobile-tab-bar"
      aria-label="Navegação principal"
    >
      <div className="grid grid-cols-5 h-16">
        {tabs.map((tab) => {
          const active = isActive(tab);
          const Icon = tab.icon;
          if (tab.primary) {
            return (
              <button
                key={tab.id}
                onClick={() => navigate(tab.to)}
                data-testid={`tab-${tab.id}`}
                className="flex flex-col items-center justify-center min-h-[44px]"
                aria-label={tab.label}
              >
                <span className="-mt-6 grid h-14 w-14 place-items-center rounded-2xl text-white rotate-[-6deg]
                                 shadow-lg shadow-emerald-900/30 ring-4 ring-background active:scale-95 transition-transform"
                      style={{ backgroundImage: "linear-gradient(135deg, #34d399 0%, #16a34a 55%, #0f766e 100%)" }}>
                  <Icon className="h-6 w-6 rotate-[6deg]" strokeWidth={2.5} />
                </span>
                <span className="text-[11px] mt-0.5 font-semibold text-foreground/80">{tab.label}</span>
              </button>
            );
          }
          return (
            <button
              key={tab.id}
              onClick={() => navigate(tab.to)}
              data-testid={`tab-${tab.id}`}
              aria-current={active ? "page" : undefined}
              className="flex flex-col items-center justify-center gap-1 min-h-[44px] transition-colors"
              aria-label={tab.label}
            >
              <span className={`grid place-items-center h-8 w-12 rounded-full transition-colors ${active ? "bg-primary/15 text-primary" : "text-muted-foreground"}`}>
                <Icon className="h-5 w-5" strokeWidth={active ? 2.5 : 2} />
              </span>
              <span className={`text-[11px] leading-none ${active ? "text-foreground font-bold" : "text-muted-foreground"}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
