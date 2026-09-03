import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState } from "react";
import {
  Hammer, LayoutDashboard, Calculator, Search, Wrench, MessageSquare, Camera,
  FileSearch, Shield, Menu, X, LogOut, Sun, Moon, Sparkles, Handshake, Ruler, KeyRound,
  Users, LineChart, ChevronDown, Contact, Library, FileText, Tag, HardHat, Building2, Layers, Wand2, Inbox, Truck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { NotificationsBell } from "@/components/NotificationsBell";
import { LangToggle, useI18n } from "@/context/I18nContext";
import { usePermissions } from "@/context/PermissionContext";

// Nav v2 — menus groupés + relief (fin du débordement header)
const NAV_MAIN = [
  { to: "/dashboard", label: "Tableau de bord", key: "nav.dashboard", icon: LayoutDashboard, auth: true },
  { to: "/devis-editeur", label: "Nouveau devis", key: "nav.newquote", icon: FileText, auth: true, pro: true },
  { to: "/estimation", label: "Estimateur", key: "nav.estimator", icon: Hammer },
  { to: "/calculateurs", label: "Calculateurs", key: "nav.calculators", icon: Calculator },
  { to: "/prix", label: "Prix matériaux", key: "nav.prices", icon: Search },
  { to: "/blog", label: "Blog", key: "nav.blog", icon: FileSearch },
];

const NAV_PRO = [
  { to: "/entreprise", label: "Espace Entreprise", key: "nav.company", icon: Building2, perm: "entreprise" },
  { to: "/devis", label: "Suivi devis", key: "nav.tracking", icon: LineChart, perm: "devis" },
  { to: "/factures", label: "Factures", key: "nav.invoices", icon: FileText, perm: "factures" },
  { to: "/situations", label: "Situations de travaux", key: "nav.situations", icon: Layers, perm: "situations" },
  { to: "/suivi-chantier", label: "Suivi de chantier", key: "nav.site", icon: HardHat, perm: "chantier" },
  { to: "/rendu-ia", label: "Rendu IA (avant/après)", key: "nav.render", icon: Wand2, auth: true, pro: true },
  { to: "/appro", label: "Analyse technique & Appro IA", key: "nav.appro", icon: Truck, auth: true, pro: true, badge: "Nouveau" },
  { to: "/rh", label: "RH — Pointage", key: "hr.nav", icon: Users, perm: "rh" },
  { to: "/clients", label: "Clients", key: "nav.clients", icon: Contact },
  { to: "/mes-demandes", label: "Mes demandes", key: "nav.myleads", icon: Inbox },
  { to: "/mon-catalogue", label: "Catalogue prix", key: "nav.catalog", icon: Tag, perm: "catalogue" },
  { to: "/bibliotheque", label: "Bibliothèque", key: "nav.library", icon: Library },
  { to: "/equipe", label: "Équipe", key: "nav.team", icon: Users },
  { to: "/etudes-pc", label: "Études PC", key: "nav.studies", icon: FileSearch, hint: "Permis de construire" },
];

const NAV_DISCOVER = [
  { to: "/fonctionnalites", label: "Fonctionnalités", key: "nav.features", icon: Sparkles },
  { to: "/coach", label: "Coach IA", key: "nav.coach", icon: MessageSquare },
  { to: "/plan", label: "Mesurer 2D", key: "nav.plan2d", icon: Ruler, auth: true, pro: true },
  { to: "/mesure-photo", label: "Mesurer sur photo", key: "nav.photomeasure", icon: Ruler, auth: true, pro: true },
  { to: "/photo", label: "Analyse photo", key: "nav.photo", icon: Camera },
  { to: "/scanner-devis", label: "Scanner de devis", key: "nav.scanner", icon: FileSearch },
  { to: "/diy", label: "Je le fais moi-même", key: "nav.diy", icon: Wrench },
  { to: "/comparatif", label: "Comparatif", key: "nav.compare", icon: Tag },
  { to: "/marketplace", label: "Trouver un pro", key: "nav.marketplace", icon: Wrench },
  { to: "/docs", label: "API & Développeurs", key: "nav.docs", icon: FileSearch },
];

const ACCOUNT_LINKS = [
  { to: "/tarifs", label: "Tarifs & abonnement", key: "nav.pricing", icon: Sparkles },
  { to: "/investisseurs", label: "Investisseurs", key: "nav.investors", icon: Handshake },
  { to: "/mes-avis", label: "Avis clients", key: "nav.reviews", icon: MessageSquare },
  { to: "/inviter", label: "Parrainer", key: "nav.referral", icon: Sparkles },
  { to: "/compte", label: "Mon compte", key: "nav.account", icon: KeyRound },
];

const ALL_LINKS = [...NAV_MAIN, ...NAV_PRO, ...NAV_DISCOVER, ...ACCOUNT_LINKS];

export const Nav = () => {
  const { user, logout } = useAuth();
  const { t } = useI18n();
  const { can } = usePermissions();
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

  const pill = (active) =>
    `px-3 py-2 rounded-lg text-sm inline-flex items-center gap-1.5 whitespace-nowrap transition-all duration-200 ${
      active
        ? "bg-primary text-primary-foreground shadow-md shadow-primary/30 font-semibold"
        : "text-muted-foreground hover:text-primary hover:bg-secondary/70 hover:-translate-y-0.5"}`;
  const groupActive = (items) => items.some((l) => location.pathname === l.to);
  const isPro = user?.account_type !== "particulier" || user?.role === "admin";
  const proItems = isPro ? NAV_PRO.filter((l) => !l.perm || can(l.perm)) : [];
  const discoverItems = NAV_DISCOVER.filter((l) => (!l.auth || user) && (!l.pro || isPro));

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-border/60 shadow-lg shadow-black/5">
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 h-16 flex items-center gap-4">
        <Link to="/" className="flex items-center gap-2 shrink-0 group" data-testid="nav-logo">
          <img src="/construpilot-icon.png" alt="ConstruPilot" className="h-9 w-9 rounded-xl object-cover shadow-md shadow-primary/30 transition-transform group-hover:-translate-y-0.5 group-hover:rotate-3" />
          <span className="font-display font-extrabold tracking-tight text-lg">
            Constru<span className="text-primary">Pilot</span>
          </span>
        </Link>

        <nav className="hidden lg:flex items-center gap-1 flex-1 min-w-0 overflow-hidden">
          {NAV_MAIN.filter((l) => (!l.auth || user) && (!l.perm || can(l.perm)) && (!l.pro || isPro)).map((l) => (
            <Link key={l.to} to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} className={pill(location.pathname === l.to)}>
              <l.icon className="h-4 w-4" /> {t(l.key, l.label)}
            </Link>
          ))}

          {user && proItems.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button data-testid="nav-pro-btn" className={pill(groupActive(NAV_PRO))}>
                  <Building2 className="h-4 w-4" /> {t("nav.pro_space", "Espace Pro")} <ChevronDown className="h-3.5 w-3.5 opacity-70" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="rounded-xl w-60 p-1.5 shadow-xl" data-testid="nav-pro-menu">
                {proItems.map((l) => (
                  <DropdownMenuItem key={l.to} asChild className="rounded-lg cursor-pointer py-2">
                    <Link to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} title={l.hint || undefined} className="flex items-center gap-2.5">
                      <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span>
                      {t(l.key, l.label)}
                      {l.badge && <span data-testid={`nav-badge-${l.to.slice(1)}`} className="ml-1.5 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground">{l.badge}</span>}
                      {l.hint && <span className="ml-auto text-[10px] text-muted-foreground">{l.hint}</span>}
                    </Link>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button data-testid="nav-more-btn" className={pill(groupActive(NAV_DISCOVER))}>
                <Sparkles className="h-4 w-4" /> {t("nav.discover", "Découvrir")} <ChevronDown className="h-3.5 w-3.5 opacity-70" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="rounded-xl w-60 p-1.5 shadow-xl" data-testid="nav-more-menu">
              {discoverItems.map((l) => (
                <DropdownMenuItem key={l.to} asChild className="rounded-lg cursor-pointer py-2">
                  <Link to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} className="flex items-center gap-2.5">
                    <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span>
                    {t(l.key, l.label)}
                  </Link>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              {ACCOUNT_LINKS.filter((l) => ["/tarifs", "/investisseurs"].includes(l.to)).map((l) => (
                <DropdownMenuItem key={l.to} asChild className="rounded-lg cursor-pointer py-2">
                  <Link to={l.to} data-testid={`nav-link-${l.to.slice(1)}`} className="flex items-center gap-2.5">
                    <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span>
                    {t(l.key, l.label)}
                  </Link>
                </DropdownMenuItem>
              ))}
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
          {user?.role === "admin" && (
            <Link to="/admin" data-testid="nav-link-admin">
              <Button variant="outline" size="sm" className="rounded-sm gap-2">
                <Shield className="h-4 w-4" /> {t("nav.admin")}
              </Button>
            </Link>
          )}
          {user ? (
            <>
              <LangToggle />
              <NotificationsBell />
              <Link to="/compte" data-testid="nav-account-link" className="hidden 2xl:flex items-center gap-2 text-sm text-muted-foreground max-w-[170px] hover:text-primary transition-colors">
                {user.picture && (
                  <img src={user.picture} alt="" data-testid="nav-avatar"
                       className="h-8 w-8 rounded-full object-cover border-2 border-primary/30 shrink-0" />
                )}
                <span className="truncate">{user.name}</span>
              </Link>
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
                  <Sparkles className="h-4 w-4" /> {t("nav.start")}
                </Button>
              </Link>
            </>
          )}
          <button
            className="lg:hidden h-9 w-9 grid place-items-center rounded-lg border border-border"
            onClick={() => setOpen(!open)}
            data-testid="mobile-menu-btn"
            aria-label="Menu"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {open && (
        <div className="lg:hidden border-t border-border bg-background px-5 py-4 grid gap-1 max-h-[75vh] overflow-y-auto" data-testid="mobile-menu">
          {ALL_LINKS.filter((l) => (!l.auth || user) && (!l.perm || can(l.perm)) && (!l.pro || isPro) && (!NAV_PRO.includes(l) || isPro)).map((l) => (
            <Link
              key={l.to} to={l.to} onClick={() => setOpen(false)}
              className="flex items-center gap-3 px-3 py-3 text-sm rounded-lg hover:bg-secondary transition-colors"
            >
              <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span> {t(l.key, l.label)}
              {l.badge && <span className="ml-auto text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground">{l.badge}</span>}
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
      <div className="flex flex-col md:items-end gap-1">
        <a
          href="mailto:info@construpilot.fr"
          className="text-xs text-primary hover:underline"
          data-testid="footer-contact-email"
        >
          info@construpilot.fr
        </a>
        <div className="flex items-center gap-3">
          <Link
            to="/investisseurs"
            className="text-[11px] text-muted-foreground/70 hover:text-primary transition-colors"
            data-testid="footer-investors-link"
          >
            Investisseurs
          </Link>
          <span className="text-[11px] text-muted-foreground">
            Estimations indicatives — ne constituent pas un devis contractuel.
          </span>
        </div>
      </div>
    </div>
    <div className="border-t border-border">
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-4 text-center" data-testid="footer-legal">
        <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mb-2 text-[11px]">
          <a href="/mentions-legales" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-mentions">Mentions légales</a>
          <a href="/confidentialite" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-confidentialite">Politique de confidentialité</a>
          <a href="/cgv" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-cgv">CGU / CGV</a>
        </div>
        <p className="text-[11px] text-muted-foreground">
          © {new Date().getFullYear()} ConstruPilot — Tous droits réservés · Brevet n° FR261104
        </p>
      </div>
    </div>
  </footer>
);
