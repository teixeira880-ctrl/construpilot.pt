import { AssistantIcon } from "@/components/workspace/navigation";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import {
  Bot, Hammer, LayoutDashboard, Calculator, Search, Wrench, MessageSquare, Camera,
  FileSearch, Shield, Menu, X, LogOut, Sun, Moon, Sparkles, Handshake, Ruler, KeyRound,
  Users, LineChart, ChevronDown, Contact, Library, FileText, Tag, HardHat, Building2, Layers, Wand2, Inbox, Truck, Radar, Brain, Globe, LifeBuoy, FileSpreadsheet, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/context/AuthContext";
import { NotificationsBell } from "@/components/NotificationsBell";
import { LangToggle, MarketToggle, useI18n } from "@/context/I18nContext";
import { usePermissions } from "@/context/PermissionContext";

// Nav v2 — menus groupés + relief (fin du débordement header)
// Séparation stricte des offres : particulier_gratuit < particulier_payant < pro < business.
const RANK = { particulier_gratuit: 0, particulier_payant: 1, pro: 2, business: 3 };
const LEVEL_LABELS = { particulier_payant: "Particular Pagante", pro: "Pro", business: "Business" };

const NAV_MAIN = [
  { to: "/dashboard", label: "Painel", key: "nav.dashboard", icon: LayoutDashboard, auth: true },
  { to: "/devis-editeur", label: "Novo orçamento", key: "nav.newquote", icon: FileText, auth: true, min: "pro" },
  { to: "/assistant", label: "Assistente Construção", key: "nav.assistant", icon: AssistantIcon, auth: true, min: "particulier_payant" },
  { to: "/estimation", label: "Estimador", key: "nav.estimator", icon: Hammer },
  { to: "/calculadoras", label: "Calculadoras", key: "nav.calculators", icon: Calculator },
  { to: "/precos", label: "Preços de materiais", key: "nav.prices", icon: Search },
  { to: "/blog", label: "Blog", key: "nav.blog", icon: FileSearch },
];

const NAV_PRO = [
  { to: "/entreprise", label: "Espaço Empresa", key: "nav.company", icon: Building2, perm: "entreprise", min: "business" },
  { to: "/ma-page", label: "A minha página & documentos", key: "nav.myPage", icon: Globe, auth: true, min: "pro" },
  { to: "/devis", label: "Acompanhamento de orçamentos", key: "nav.tracking", icon: LineChart, perm: "devis", min: "pro" },
  { to: "/factures", label: "Faturas", key: "nav.invoices", icon: FileText, perm: "factures", min: "pro" },
  { to: "/situations", label: "Autos de medição", key: "nav.situations", icon: Layers, perm: "situations", min: "business" },
  { to: "/dpgf", label: "Mapa de quantidades do arquiteto → orçamento", key: "nav.dpgf", icon: FileSpreadsheet, perm: "devis", badge: "Novo", min: "pro" },
  { to: "/suivi-chantier", label: "Acompanhamento de obra", key: "nav.site", icon: HardHat, perm: "chantier", min: "pro" },
  { to: "/appro", label: "Análise técnica & Aprovisionamento IA", key: "nav.appro", icon: Truck, auth: true, badge: "Novo", min: "pro" },
  { to: "/controle-cotes", label: "Analisar cotas das plantas", key: "nav.cotes", icon: Ruler, auth: true, badge: "Novo", min: "pro" },
  { to: "/radar", label: "Radar Obras", key: "nav.radar", icon: Radar, auth: true, badge: "Novo", min: "pro" },
  { to: "/rh", label: "RH — Ponto", key: "hr.nav", icon: Users, perm: "rh", min: "business" },
  { to: "/clients", label: "Clientes", key: "nav.clients", icon: Contact, min: "pro" },
  { to: "/mon-catalogue", label: "Catálogo de preços", key: "nav.catalog", icon: Tag, perm: "catalogue", min: "pro" },
  { to: "/bibliotheque", label: "Biblioteca", key: "nav.library", icon: Library, min: "pro" },
  { to: "/equipe", label: "Equipa", key: "nav.team", icon: Users, min: "business" },
  { to: "/etudes-pc", label: "Estudos de licença", key: "nav.studies", icon: FileSearch, hint: "Licença de construção", min: "pro" },
  { to: "/plans-pro", label: "Análise de planta Pro", key: "nav.plansPro", icon: Layers, auth: true, min: "pro" },
];

const NAV_DISCOVER = [
  { to: "/fonctionnalites", label: "Funcionalidades", key: "nav.features", icon: Sparkles },
  { to: "/coach", label: "Coach IA", key: "nav.coach", icon: MessageSquare },
  { to: "/rendu-ia", label: "Renderização IA (antes/depois)", key: "nav.render", icon: Wand2, auth: true, min: "particulier_payant" },
  { to: "/mesure-photo", label: "Medir em fotografia", key: "nav.photomeasure", icon: Ruler, auth: true, min: "particulier_payant" },
  { to: "/plan", label: "Editor de plantas", key: "nav.plan2d", icon: Ruler, auth: true, min: "pro" },
  { to: "/btp-solver", label: "Resolver um problema", key: "nav.solver", icon: Wrench, auth: true },
  { to: "/mes-demandes", label: "Os meus pedidos", key: "nav.myleads", icon: Inbox, auth: true },
  { to: "/photo", label: "Análise de fotografia", key: "nav.photo", icon: Camera },
  { to: "/scanner-devis", label: "Scanner de orçamentos", key: "nav.scanner", icon: FileSearch },
  { to: "/diy", label: "Faço eu mesmo", key: "nav.diy", icon: Wrench },
  { to: "/comparatif", label: "Comparativo", key: "nav.compare", icon: Tag },
  { to: "/marketplace", label: "Encontrar um profissional", key: "nav.marketplace", icon: Wrench },
  { to: "/docs", label: "API e Programadores", key: "nav.docs", icon: FileSearch, min: "business" },
];

const ACCOUNT_LINKS = [
  { to: "/planos", label: "Preços & subscrição", key: "nav.pricing", icon: Sparkles },
  { to: "/aide", label: "Ajuda e assistência", key: "nav.help", icon: LifeBuoy },
  { to: "/investisseurs", label: "Investidores", key: "nav.investors", icon: Handshake },
  { to: "/mes-avis", label: "Opiniões de clientes", key: "nav.reviews", icon: MessageSquare },
  { to: "/inviter", label: "Recomendar", key: "nav.referral", icon: Sparkles },
  { to: "/preferences", label: "Memória e preferências", key: "nav.preferences", icon: Brain, auth: true },
  { to: "/compte", label: "A minha conta", key: "nav.account", icon: KeyRound },
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
    if (user) api.put("/auth/theme", { theme: isDark ? "dark" : "light" }).catch(() => {});
  };
  useEffect(() => {
    const sync = () => setDark(document.documentElement.classList.contains("dark"));
    window.addEventListener("construpilot-theme", sync);
    return () => window.removeEventListener("construpilot-theme", sync);
  }, []);

  const pill = (active) =>
    `px-3 py-2 rounded-lg text-sm inline-flex items-center gap-1.5 whitespace-nowrap transition-all duration-200 ${
      active
        ? "bg-primary text-primary-foreground shadow-md shadow-primary/30 font-semibold"
        : "text-muted-foreground hover:text-primary hover:bg-secondary/70 hover:-translate-y-0.5"}`;
  const groupActive = (items) => items.some((l) => location.pathname === l.to);
  const [level, setLevel] = useState("particulier_gratuit");
  useEffect(() => {
    if (!user) { setLevel("particulier_gratuit"); return; }
    if (user.role === "admin") { setLevel("business"); return; }
    api.get("/billing/me").then(({ data }) => setLevel(data.level || "particulier_gratuit")).catch(() => {
      setLevel(user.account_type === "pro" ? "pro" : "particulier_gratuit");
    });
  }, [user]);
  // Paid/pro links stay visible to logged-in users as locked upsells (→ /tarifs).
  const stateOf = (l) => {
    if (l.auth && !user) return "hidden";
    const tierOk = !l.min || RANK[level] >= RANK[l.min];
    if (!tierOk) return user ? "locked" : "hidden";
    if (l.perm && !can(l.perm)) return "hidden";
    return "ok";
  };
  const annotate = (arr) => arr.map((l) => ({ ...l, _state: stateOf(l) })).filter((l) => l._state !== "hidden");
  const mainItems = annotate(NAV_MAIN);
  const proItems = annotate(NAV_PRO);
  const discoverItems = annotate(NAV_DISCOVER);
  const lockHint = (l) => `Função ${LEVEL_LABELS[l.min] || ""} — clique para desbloquear`;

  return (
    <header className="sticky top-0 z-50 backdrop-blur-xl bg-background/80 border-b border-border/60 shadow-lg shadow-black/5">
      <div className="mx-auto max-w-[1500px] px-3 sm:px-5 lg:px-8 min-h-16 py-2 lg:py-0 lg:h-16 flex flex-wrap lg:flex-nowrap items-center gap-2 lg:gap-4">
        <Link to="/" className="flex items-center gap-2 shrink-0 group" data-testid="nav-logo">
          <img src="/construpilot-icon.png" alt="ConstruPilot" className="h-9 w-9 rounded-xl object-cover shadow-md shadow-primary/30 transition-transform group-hover:-translate-y-0.5 group-hover:rotate-3" />
          <span className="font-display font-extrabold tracking-tight text-lg">
            Constru<span className="text-primary">Pilot</span>
          </span>
        </Link>

        <nav className="hidden lg:flex items-center gap-1 flex-1 min-w-0" data-testid="nav-desktop">
          <div className="flex items-center gap-1 min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {mainItems.map((l) => {
              const locked = l._state === "locked";
              return (
              <Link key={l.to} to={locked ? "/planos" : l.to} data-testid={`nav-link-${l.to.slice(1)}`} data-locked={locked || undefined} title={locked ? lockHint(l) : t(l.key, l.label)} className={pill(!locked && location.pathname === l.to)}>
                <l.icon className="h-4 w-4" /> <span className="hidden xl:inline">{t(l.key, l.label)}</span>{locked && <Lock className="h-3 w-3 opacity-70" />}
              </Link>
            );})}
          </div>

          {user && proItems.length > 0 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button data-testid="nav-pro-btn" className={pill(groupActive(NAV_PRO)) + " shrink-0"}>
                  <Building2 className="h-4 w-4" /> {t("nav.pro_space", "Espaço Pro")} <ChevronDown className="h-3.5 w-3.5 opacity-70" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="rounded-xl w-60 p-1.5 shadow-xl" data-testid="nav-pro-menu">
                {proItems.map((l) => {
                  const locked = l._state === "locked";
                  return (
                  <DropdownMenuItem key={l.to} asChild className="rounded-lg cursor-pointer py-2">
                    <Link to={locked ? "/planos" : l.to} data-testid={`nav-link-${l.to.slice(1)}`} data-locked={locked || undefined} title={locked ? lockHint(l) : (l.hint || undefined)} className="flex items-center gap-2.5">
                      <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span>
                      {t(l.key, l.label)}
                      {locked ? <Lock data-testid={`nav-lock-${l.to.slice(1)}`} className="ml-auto h-3.5 w-3.5 text-primary/70" /> : <>
                        {l.badge && <span data-testid={`nav-badge-${l.to.slice(1)}`} className="ml-1.5 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground">{l.badge}</span>}
                        {l.hint && <span className="ml-auto text-[10px] text-muted-foreground">{l.hint}</span>}
                      </>}
                    </Link>
                  </DropdownMenuItem>
                );})}
              </DropdownMenuContent>
            </DropdownMenu>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button data-testid="nav-more-btn" className={pill(groupActive(NAV_DISCOVER)) + " shrink-0"}>
                <Sparkles className="h-4 w-4" /> {t("nav.discover", "Descobrir")} <ChevronDown className="h-3.5 w-3.5 opacity-70" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="rounded-xl w-60 p-1.5 shadow-xl" data-testid="nav-more-menu">
              {discoverItems.map((l) => {
                const locked = l._state === "locked";
                return (
                <DropdownMenuItem key={l.to} asChild className="rounded-lg cursor-pointer py-2">
                  <Link to={locked ? "/planos" : l.to} data-testid={`nav-link-${l.to.slice(1)}`} data-locked={locked || undefined} title={locked ? lockHint(l) : undefined} className="flex items-center gap-2.5">
                    <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span>
                    {t(l.key, l.label)}
                    {locked && <Lock data-testid={`nav-lock-${l.to.slice(1)}`} className="ml-auto h-3.5 w-3.5 text-primary/70" />}
                  </Link>
                </DropdownMenuItem>
              );})}
              <DropdownMenuSeparator />
              {ACCOUNT_LINKS.filter((l) => ["/planos", "/investisseurs"].includes(l.to) || (l.to === "/preferences" && user)).map((l) => (
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

        <div className="ml-auto flex flex-wrap items-center justify-end gap-1 sm:gap-2 max-w-full min-w-0" data-testid="nav-actions">
          <button
            onClick={toggleTheme}
            data-testid="theme-toggle"
            aria-label="Mudar de tema"
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
              <MarketToggle />
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
              <MarketToggle />
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
          {annotate(ALL_LINKS.filter((l, i, all) => all.findIndex((item) => item.to === l.to) === i)).map((l) => {
            const locked = l._state === "locked";
            return (
            <Link
              key={l.to} to={locked ? "/planos" : l.to} onClick={() => setOpen(false)} data-testid={`mobile-nav-link-${l.to.slice(1)}`} data-locked={locked || undefined}
              className="flex items-center gap-3 px-3 py-3 text-sm rounded-lg hover:bg-secondary transition-colors"
            >
              <span className="h-7 w-7 grid place-items-center rounded-md bg-primary/10"><l.icon className="h-4 w-4 text-primary" /></span> {t(l.key, l.label)}
              {locked ? <Lock className="ml-auto h-4 w-4 text-primary/70" /> : (l.badge && <span className="ml-auto text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full bg-primary text-primary-foreground">{l.badge}</span>)}
            </Link>
          );})}
        </div>
      )}
    </header>
  );
};

export const Footer = () => (
  <footer className="border-t border-border mt-24">
    <div className="azulejo-band" aria-hidden="true" />
    <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-10 flex flex-col md:flex-row gap-4 items-center justify-between">
      <p className="font-display font-bold tracking-tight">
        Constru<span className="text-primary">Pilot</span>
        <span className="ml-3 text-sm font-sans font-normal text-muted-foreground">
          Estime. Compare. Construa.
        </span>
      </p>
      <div className="flex flex-col md:items-end gap-1">
        <a
          href="mailto:info@construpilot.pt"
          className="text-xs text-primary hover:underline"
          data-testid="footer-contact-email"
        >
          info@construpilot.pt
        </a>
        <div className="flex items-center gap-3">
          <Link
            to="/aide"
            className="text-[11px] text-muted-foreground/70 hover:text-primary transition-colors"
            data-testid="footer-help-link"
          >
            Ajuda e assistência
          </Link>
          <Link
            to="/portugal"
            className="text-[11px] text-muted-foreground/70 hover:text-primary transition-colors"
            data-testid="footer-portugal-link"
          >
            🇵🇹 Portugal
          </Link>
          <Link
            to="/investisseurs"
            className="text-[11px] text-muted-foreground/70 hover:text-primary transition-colors"
            data-testid="footer-investors-link"
          >
            Investidores
          </Link>
          <span className="text-[11px] text-muted-foreground">
            Estimativas indicativas — não constituem um orçamento contratual.
          </span>
        </div>
      </div>
    </div>
    <div className="border-t border-border">
      <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-4 text-center" data-testid="footer-legal">
        <div className="flex flex-wrap justify-center gap-x-4 gap-y-1 mb-2 text-[11px]">
          <a href="/mentions-legales" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-mentions">Informação legal</a>
          <a href="/confidentialite" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-confidentialite">Política de privacidade</a>
          <a href="/eliminar-conta" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-suppression-compte">Eliminar a minha conta</a>
          <a href="/eliminar-dados" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-suppression-donnees">Eliminar os meus dados</a>
          <a href="/cgv" className="text-muted-foreground hover:text-primary transition-colors" data-testid="footer-link-cgv">Termos e condições</a>
        </div>
        <p className="text-[11px] text-muted-foreground">
          © {new Date().getFullYear()} ConstruPilot — Todos os direitos reservados · Patente n.º FR2611044
        </p>
      </div>
    </div>
  </footer>
);
