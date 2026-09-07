import { useLocation, useNavigate } from "react-router-dom";
import { LayoutDashboard, FileText, Plus, Calculator, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

// Routes plein écran / publiques où la barre d'onglets ne doit pas apparaître
const HIDDEN_PREFIXES = ["/pointage", "/sign/", "/e/", "/etude/", "/avis/", "/fiche/", "/login", "/inscription"];

const TABS = [
  { to: "/dashboard", label: "Início", icon: LayoutDashboard },
  { to: "/devis", label: "Orçamentos", icon: FileText },
  { to: "/devis-editeur", label: "Novo", icon: Plus, primary: true },
  { to: "/calculateurs", label: "Cálculos", icon: Calculator },
  { to: "/compte", label: "Conta", icon: User },
];

export const MobileTabBar = () => {
  const { user } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  if (!user) return null;
  if (HIDDEN_PREFIXES.some((p) => location.pathname.startsWith(p))) return null;

  const isActive = (to) =>
    to === "/dashboard" ? location.pathname === "/dashboard" : location.pathname.startsWith(to);

  return (
    <nav
      className="md:hidden fixed inset-x-0 bottom-0 z-50 border-t border-white/10
                 bg-[#0A0D14]/95 backdrop-blur-xl pb-[env(safe-area-inset-bottom)]"
      data-testid="mobile-tab-bar"
    >
      <div className="grid grid-cols-5 h-16">
        {TABS.map((tab) => {
          const active = isActive(tab.to);
          const Icon = tab.icon;
          if (tab.primary) {
            return (
              <button
                key={tab.to}
                onClick={() => navigate(tab.to)}
                data-testid={`tab-${tab.label.toLowerCase()}`}
                className="flex flex-col items-center justify-center"
                aria-label={tab.label}
              >
                <span className="-mt-6 grid h-14 w-14 place-items-center rounded-full bg-[#FF5A00]
                                 text-white shadow-lg shadow-orange-900/40 ring-4 ring-[#0A0D14]
                                 active:scale-95 transition-transform">
                  <Icon className="h-6 w-6" strokeWidth={2.5} />
                </span>
                <span className="text-[10px] mt-0.5 text-white/70">{tab.label}</span>
              </button>
            );
          }
          return (
            <button
              key={tab.to}
              onClick={() => navigate(tab.to)}
              data-testid={`tab-${tab.label.toLowerCase()}`}
              className="flex flex-col items-center justify-center gap-1 transition-colors"
              aria-label={tab.label}
            >
              <Icon className={`h-5 w-5 ${active ? "text-[#FF5A00]" : "text-white/55"}`}
                    strokeWidth={active ? 2.5 : 2} />
              <span className={`text-[10px] ${active ? "text-[#FF5A00] font-semibold" : "text-white/55"}`}>
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
