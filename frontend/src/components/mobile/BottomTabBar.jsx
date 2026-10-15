import { NavLink, useLocation } from "react-router-dom";
import { Home, LayoutGrid, Sparkles, Hammer, User } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

/**
 * Bottom tab bar global (mobile) para visitantes e páginas públicas.
 * O workspace autenticado continua a usar `MobileTabBar` contextual
 * (components/pwa/MobileTabBar.jsx) com permissões/billing.
 *
 * Regra para evitar sobreposição:
 *  - Esta barra APARECE quando a contextual se esconde (sem sessão OU em
 *    landings públicas) e em viewports <768px.
 *  - Esconde-se em rotas de dossier público, assinatura técnica, demo, etc.
 */
const HIDE_ON_PATHS = ["/demo", "/login", "/inscription", "/reinitialiser"];
const HIDE_PREFIXES = [
  "/subscrever/",
  "/sign/",
  "/e/",
  "/etude/",
  "/avis/",
  "/fiche/",
  "/rendu/",
  "/estimation-partagee/",
  "/pointage",
  "/appel-offres/",
];
// Páginas onde a MobileTabBar contextual se esconde — a nova pode aparecer
const PUBLIC_LANDING_PAGES = ["/", "/particulares", "/medicoes", "/investisseurs", "/fonctionnalites", "/portugal", "/apps"];

const TABS = [
  { to: "/", icon: Home, label: "Início", testId: "mobile-tab-inicio", end: true },
  { to: "/apps", icon: LayoutGrid, label: "Apps", testId: "mobile-tab-apps" },
  { to: "/assistant", icon: Sparkles, label: "Assistente", testId: "mobile-tab-assistente", highlight: true },
  { to: "/chantiers", icon: Hammer, label: "Projetos", testId: "mobile-tab-projetos" },
  { to: "/compte", icon: User, label: "Perfil", testId: "mobile-tab-perfil" },
];

export default function BottomTabBar() {
  const loc = useLocation();
  const { user } = useAuth();
  const hidden =
    HIDE_ON_PATHS.includes(loc.pathname) ||
    HIDE_PREFIXES.some((p) => loc.pathname.startsWith(p));
  if (hidden) return null;
  // Se o utilizador está autenticado e NÃO está numa landing pública, a
  // MobileTabBar contextual trata — não duplicar.
  if (user && !PUBLIC_LANDING_PAGES.includes(loc.pathname)) return null;

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 border-t border-border bg-background/95 backdrop-blur md:hidden pb-safe"
      data-testid="bottom-tabs"
      aria-label="Navegação principal"
    >
      <div className="grid grid-cols-5 h-14">
        {TABS.map(({ to, icon: Icon, label, testId, highlight, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            data-testid={testId}
            className={({ isActive }) =>
              `flex flex-col items-center justify-center gap-0.5 text-[10px] touch-target ${
                highlight
                  ? "text-primary"
                  : isActive
                    ? "text-primary font-medium"
                    : "text-muted-foreground"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon
                  className={`${highlight ? "h-6 w-6" : "h-5 w-5"} ${
                    isActive ? "scale-110" : ""
                  } transition-transform`}
                  aria-hidden="true"
                />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
