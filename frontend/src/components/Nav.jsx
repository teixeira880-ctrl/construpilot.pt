import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  Hammer, LayoutDashboard, Calculator, Search, Wrench, MessageSquare, Camera,
  FileSearch, Shield, Menu, X, LogOut, Sun, Moon, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const LINKS = [
  { to: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard, auth: true },
  { to: "/estimation", label: "Estimateur", icon: Hammer },
  { to: "/calculateurs", label: "Calculateurs", icon: Calculator },
  { to: "/prix", label: "Prix matériaux", icon: Search },
  { to: "/diy", label: "Je le fais moi-même", icon: Wrench },
  { to: "/photo", label: "Analyse photo", icon: Camera },
  { to: "/devis", label: "Scanner de devis", icon: FileSearch },
  { to: "/coach", label: "Coach IA", icon: MessageSquare },
];

export const Nav = () => {
  const { user, logout } = useAuth();
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

        <nav className="hidden xl:flex items-center gap-1 flex-1">
          {LINKS.filter((l) => !l.auth || user).map((l) => (
            <Link
              key={l.to}
              to={l.to}
              data-testid={`nav-link-${l.to.slice(1)}`}
              className={`px-3 py-2 text-sm rounded-sm transition-colors hover:text-primary ${
                location.pathname === l.to ? "text-primary font-semibold" : "text-muted-foreground"
              }`}
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={toggleTheme}
            data-testid="theme-toggle"
            aria-label="Changer de thème"
            className="h-9 w-9 grid place-items-center rounded-sm border border-border hover:border-primary transition-colors"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {user?.role === "admin" && (
            <Link to="/admin" data-testid="nav-link-admin">
              <Button variant="outline" size="sm" className="rounded-sm gap-2">
                <Shield className="h-4 w-4" /> Admin
              </Button>
            </Link>
          )}
          {user ? (
            <>
              <span className="hidden md:block text-sm text-muted-foreground max-w-[140px] truncate">
                {user.name}
              </span>
              <Button
                variant="ghost" size="sm" data-testid="logout-btn" className="rounded-sm"
                onClick={async () => { await logout(); navigate("/"); }}
              >
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <Link to="/login" data-testid="nav-login-btn">
              <Button size="sm" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Sparkles className="h-4 w-4" /> Commencer
              </Button>
            </Link>
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
          {LINKS.filter((l) => !l.auth || user).map((l) => (
            <Link
              key={l.to} to={l.to} onClick={() => setOpen(false)}
              className="flex items-center gap-3 px-3 py-3 text-sm rounded-sm hover:bg-secondary transition-colors"
            >
              <l.icon className="h-4 w-4 text-primary" /> {l.label}
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
