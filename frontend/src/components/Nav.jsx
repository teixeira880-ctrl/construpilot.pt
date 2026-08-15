import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  Hammer, LayoutDashboard, Calculator, Search, Wrench, MessageSquare, Camera,
  FileSearch, Shield, Menu, X, LogOut, Sun, Moon, Sparkles, Handshake, Ruler, KeyRound,
  Users, LineChart, ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { NotificationsBell } from "@/components/NotificationsBell";
import { LangToggle, useI18n } from "@/context/I18nContext";

// Iter67 — nav scindée : liens principaux visibles + menu « Plus » (fin des retours à la ligne)
const PRIMARY_LINKS = [
  { to: "/dashboard", label: "Tableau de bord", key: "nav.dashboard", icon: LayoutDashboard, auth: true },
  { to: "/estimation", label: "Estimateur", key: "nav.estimator", icon: Hammer },
  { to: "/plan", label: "Mesurer", key: "nav.plan2d", icon: Ruler, auth: true },
  { to: "/calculateurs", label: "Calculateurs", key: "nav.calculators", icon: Calculator },
  { to: "/prix", label: "Prix matériaux", key: "nav.prices", icon: Search },
  { to: "/coach", label: "Coach IA", key: "nav.coach", icon: MessageSquare },
  { to: "/tarifs", label: "Tarifs", key: "nav.pricing", icon: Sparkles },
];

const MORE_LINKS = [
  { to: "/diy", label: "Je le fais moi-même", key: "nav.diy", icon: Wrench },
  { to: "/photo", label: "Analyse photo", key: "nav.photo", icon: Camera },
  { to: "/scanner-devis", label: "Scanner de devis", key: "nav.scanner", icon: FileSearch },
  { to: "/marketplace", label: "Trouver un pro", key: "nav.marketplace", icon: Wrench },
  { to: "/pro", label: "Espace pro", key: "nav.pro", icon: Handshake },
  { to: "/docs", label: "API & Développeurs", key: "nav.docs", icon: FileSearch },
  { to: "/blog", label: "Blog", key: "nav.blog", icon: FileSearch },
];

const LINKS = [...PRIMARY_LINKS, ...MORE_LINKS];

// Raccourcis utilisateur connecté — dans le menu « Plus » (plus de chevauchement header)
const USER_LINKS = [
  { to: "/devis", label: "Suivi devis", icon: LineChart },
  { to: "/mes-avis", label: "Avis clients", icon: MessageSquare },
  { to: "/etudes-pc", label: "Études PC", icon: FileSearch },
  { to: "/equipe", label: "Équipe", icon: Users },
  { to: "/inviter", label: "Parrainer", icon: Sparkles },
  { to: "/compte", label: "Mon compte", icon: KeyRound },
];

export const Nav = () => {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const location = useLocation();
  const navigate = useNavigate();

  const toggleTheme = () => {
    document.documentElement.classList.toggle("dark");
    const isDark = document.documentElement.classList.contains("dark");
    localStorage.setItem("construpilot_theme", isDark ? "dark" : "light");
    setDark(isDark);
  };

  const moreActive = MORE_LINKS.some((l) => location.pathname === l.to);

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-background/75 border-b border-border/60">
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 h-16 flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2 shrink-0" data-testid="nav-logo">
          <span className="h-8 w-8 grid place-items-center bg-primary rounded-sm">
            <Hammer className="h-4 w-4 text-primary-foreground" aria-hidden="true" />
          </span>
          <span className="font-display font-extrabold tracking-tight text-lg">
            Constru<span className="text-primary">Pilot</span>
          </span>
        </Link>

        <nav className="hidden xl:flex items-center gap-1 flex-1 min-w-0">
          {PRIMARY_LINKS.filter((l) => !l.auth || user).map((l) => (
            <Link
              key={l.to}
              to={l.to}
              data-testid={`nav-link-${l.to.slice(1)}`}
              className={`px-3 py-2 text-sm rounded-sm whitespace-nowrap transition-colors hover:text-primary ${
                location.pathname === l.to ? "text-primary font-semibold" : "text-muted-foreground"
              }`}
            >
              {t(l.key, l.label)}
            </Link>
          ))}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                data-testid="nav-more-btn"
                className={`px-3 py-2 text-sm rounded-sm whitespace-nowrap inline-flex items-center gap-1 transition-colors hover:text-primary ${
                  moreActive ? "text-primary font-semibold" : "text-muted-foreground"
                }`}
              >
                Plus <ChevronDown className="h-3.5 w-3.5" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="rounded-sm w-56" data-testid="nav-more-menu">
              {MORE_LINKS.map((l) => (
                <DropdownMenuItem key={l.to} asChild className="rounded-sm cursor-pointer">
                  <Link to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} className="flex items-center gap-2">
                    <l.icon className="h-4 w-4 text-primary" /> {t(l.key, l.label)}
                  </Link>
                </DropdownMenuItem>
              ))}
              {user && (
                <>
                  <DropdownMenuSeparator />
                  {USER_LINKS.map((l) => (
                    <DropdownMenuItem key={l.to} asChild className="rounded-sm cursor-pointer">
                      <Link to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} className="flex items-center gap-2">
                        <l.icon className="h-4 w-4 text-primary" /> {l.label}
                      </Link>
                    </DropdownMenuItem>
                  ))}
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </nav>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <button
            onClick={toggleTheme}
            data-testid="theme-toggle"
            aria-label="Changer de thème"
            className="h-9 w-9 grid place-items-center rounded-sm border border-border hover:border-primary transition-colors"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {user && (
            <Link to="/devis" data-testid="nav-link-tracking" className="hidden min-[1700px]:inline-flex">
              <Button variant="ghost" size="sm" className="rounded-sm gap-2 whitespace-nowrap">
                <LineChart className="h-4 w-4 text-primary" /> Suivi devis
              </Button>
            </Link>
          )}
          {user?.role === "admin" && (
            <Link to="/admin" data-testid="nav-link-admin">
              <Button variant="outline" size="sm" className="rounded-sm gap-2">
                <Shield className="h-4 w-4" /> Admin
              </Button>
            </Link>
          )}
          {user ? (
            <>
              <LangToggle />
              <NotificationsBell />
              <span className="hidden 2xl:flex items-center gap-2 text-sm text-muted-foreground max-w-[170px]">
                {user.picture && (
                  <img src={user.picture} alt="" data-testid="nav-avatar"
                       className="h-7 w-7 rounded-full object-cover border border-border shrink-0" />
                )}
                <span className="truncate">{user.name}</span>
              </span>
              <Button
                variant="ghost" size="sm" data-testid="logout-btn" className="rounded-sm"
                onClick={async () => { await logout(); navigate("/"); }}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <>
              <LangToggle />
              <Link to="/login" data-testid="nav-login-btn">
                <Button size="sm" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Sparkles className="h-4 w-4" /> Commencer
                </Button>
              </Link>
            </>
          )}
          <button
            className="xl:hidden h-9 w-9 grid place-items-center rounded-sm border border-border"
            onClick={() => setOpen(!open)}
            data-testid="mobile-menu-btn"
            aria-label="Menu"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="xl:hidden border-t border-border bg-background px-5 py-4 grid gap-1" data-testid="mobile-menu">
          {[...LINKS.filter((l) => !l.auth || user), ...(user ? USER_LINKS : [])].map((l) => (
            <Link
              key={l.to} to={l.to} onClick={() => setOpen(false)}
              className="flex items-center gap-3 px-3 py-3 text-sm rounded-sm hover:bg-secondary transition-colors"
            >
              <l.icon className="h-4 w-4 text-primary" /> {t(l.key, l.label)}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
};

export const Footer = () => (
  <footer className="border-t border-border mt-24">
    <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 flex flex-col md:flex-row gap-4 items-center justify-between">
      <p className="font-display font-bold tracking-tight">
        Constru<span className="text-primary">Pilot</span>
        <span className="ml-3 text-sm font-sans font-normal text-muted-foreground">
          Estimez. Comparez. Construisez.
        </span>
      </p>
      <p className="text-xs text-muted-foreground">
        Estimations indicatives — ne constituent pas un devis contractuel.
      </p>
    </div>
  </footer>
);
