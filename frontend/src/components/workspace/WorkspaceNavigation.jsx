import { Link, useLocation, useNavigate } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";
import { Search, Sun, Moon, Shield, LogOut, Menu, X, LayoutGrid, Star, ChevronRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { MarketToggle } from "@/context/I18nContext";
import { NotificationsBell } from "@/components/NotificationsBell";
import {
  Command, CommandInput, CommandList, CommandEmpty, CommandGroup, CommandItem,
} from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { AppTile } from "@/components/workspace/AppTile";
import {
  workspaceLinks, workspaceEssentials, activeWorkspaceLink, linkTarget, isProfessional, readFavorites,
  FAMILY_ORDER, FAMILY_ICONS, familyLabel, familySub, normText,
} from "@/components/workspace/navigation";
import "@/styles/workspace-tiles.css";
import "@/styles/workspace-ambient.css";

export const OPEN_TOOL_SEARCH = "cp-open-tool-search";

// Tema: claro por omissão; o escuro fica guardado em localStorage ("construpilot_theme").
export function useTheme() {
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const toggle = () => {
    const isDark = document.documentElement.classList.toggle("dark");
    try { localStorage.setItem("construpilot_theme", isDark ? "dark" : "light"); } catch { /* armazenamento indisponível */ }
    setDark(isDark);
  };
  return { dark, toggle };
}

export function useWorkspaceLinks() {
  const { user } = useAuth();
  const { tier } = useBilling();
  const { can } = usePermissions();
  return useMemo(() => workspaceLinks(user, can, tier), [user, can, tier]);
}

export function useFavorites() {
  const [favs, setFavs] = useState(readFavorites);
  useEffect(() => {
    const h = () => setFavs(readFavorites());
    window.addEventListener("cp-favorites", h);
    window.addEventListener("storage", h);
    return () => { window.removeEventListener("cp-favorites", h); window.removeEventListener("storage", h); };
  }, []);
  return favs;
}

const initials = (name = "") => name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "?";

const NavItem = ({ link, active, onClick, size = 30 }) => (
  <Link
    to={linkTarget(link)}
    onClick={onClick}
    aria-current={active ? "page" : undefined}
    data-testid={`nav-link-${link.to.slice(1)}`}
    className={`workspace-nav-link flex items-center gap-3 min-h-[44px] px-2.5 py-1.5 rounded-xl text-[13.5px] font-medium text-foreground/85 hover:bg-background/70 hover:text-foreground transition-colors ${link.locked ? "opacity-70" : ""}`}
  >
    <AppTile icon={link.icon} family={link.family} size={size} />
    <span className="truncate">{link.label}</span>
  </Link>
);

function ToolSearch({ open, onOpenChange, links }) {
  const navigate = useNavigate();
  const go = (to) => { onOpenChange(false); navigate(to); };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0 max-w-[560px] rounded-2xl" data-testid="tool-search-dialog">
      <DialogTitle className="sr-only">Pesquisar uma ferramenta</DialogTitle>
      <Command filter={(value, search) => (normText(value).includes(normText(search).trim()) ? 1 : 0)}
        className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group]]:px-2 [&_[cmdk-input]]:h-12">
      <CommandInput placeholder="Pesquisar uma ferramenta…" data-testid="tool-search-input" />
      <CommandList className="max-h-[60vh]">
        <CommandEmpty>Nenhuma ferramenta corresponde. Experimente outra palavra.</CommandEmpty>
        {FAMILY_ORDER.map((f) => {
          const items = links.filter((l) => l.family === f && !l.home);
          if (!items.length) return null;
          return (
            <CommandGroup key={f} heading={familyLabel(f)}>
              {items.map((l) => (
                <CommandItem key={l.to} value={`${l.label} ${l.words || ""} ${familyLabel(f)}`} onSelect={() => go(linkTarget(l))}
                  className="gap-3 py-2 cursor-pointer" data-testid={`tool-search-item-${l.to.slice(1)}`}>
                  <AppTile icon={l.icon} family={l.family} size={28} />
                  <span>{l.label}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          );
        })}
      </CommandList>
      </Command>
      </DialogContent>
    </Dialog>
  );
}

export function WorkspaceHeader() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useTheme();
  const links = useWorkspaceLinks();
  const location = useLocation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearchOpen((v) => !v); }
    };
    const onOpen = () => setSearchOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_TOOL_SEARCH, onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener(OPEN_TOOL_SEARCH, onOpen); };
  }, []);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);

  const active = activeWorkspaceLink(location.pathname, links);
  const iconBtn = "h-11 w-11 grid place-items-center rounded-xl text-foreground/80 hover:bg-background/70 hover:text-foreground transition-colors";

  return (
    <header className="workspace-header sticky top-0 z-50 border-b backdrop-blur-xl" data-testid="workspace-header">
      <div className="h-16 px-3 sm:px-5 lg:px-6 flex items-center gap-2 sm:gap-4">
        <Link to="/dashboard" className="flex items-center gap-2 shrink-0 group lg:w-[220px]" data-testid="nav-logo">
          <img src="/construpilot-icon.png" alt="ConstruPilot" className="h-9 w-9 rounded-xl object-cover shadow-md shadow-primary/30 transition-transform group-hover:-translate-y-0.5 group-hover:rotate-3" />
          <span className="font-display font-extrabold tracking-tight text-lg hidden min-[420px]:inline">
            Constru<span className="text-primary">Pilot</span>
          </span>
        </Link>

        <button type="button" onClick={() => setSearchOpen(true)} data-testid="tool-search-trigger"
          className="workspace-search-trigger hidden md:flex items-center gap-2.5 h-11 px-3.5 rounded-xl border bg-card/70 text-sm text-muted-foreground hover:text-foreground transition-colors w-[min(440px,36vw)]">
          <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="flex-1 text-left truncate">Pesquisar uma ferramenta…</span>
          <kbd className="text-[10px] font-semibold border rounded px-1.5 py-0.5 bg-background/70">Ctrl K</kbd>
        </button>

        <div className="ml-auto flex items-center gap-0.5 sm:gap-1.5 shrink-0">
          <button type="button" onClick={() => setSearchOpen(true)} aria-label="Pesquisar uma ferramenta" className={`${iconBtn} md:hidden`} data-testid="tool-search-trigger-mobile">
            <Search className="h-[18px] w-[18px]" />
          </button>
          <span className="hidden sm:inline-flex"><MarketToggle /></span>
          <button type="button" onClick={toggle} data-testid="theme-toggle" aria-label={dark ? "Mudar para tema claro" : "Mudar para tema escuro"} title={dark ? "Tema claro" : "Tema escuro"} className={iconBtn}>
            {dark ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
          </button>
          {user?.role === "admin" && (
            <Link to="/admin" data-testid="nav-link-admin" aria-label="Administração" title="Administração" className={`${iconBtn} hidden sm:grid`}>
              <Shield className="h-[18px] w-[18px]" />
            </Link>
          )}
          <NotificationsBell />
          <Link to="/conta" data-testid="nav-account-link" title={user?.name || "A minha conta"} className="flex items-center gap-2 h-11 px-1 rounded-xl hover:bg-background/70 transition-colors">
            {user?.picture ? (
              <img src={user.picture} alt="" data-testid="nav-avatar" className="h-9 w-9 rounded-full object-cover border-2 border-primary/30" />
            ) : (
              <span className="workspace-avatar h-9 w-9 rounded-full grid place-items-center text-[13px] font-bold">{initials(user?.name)}</span>
            )}
            <span className="hidden 2xl:block text-sm font-medium max-w-[140px] truncate">{user?.name}</span>
          </Link>
          <button type="button" data-testid="logout-btn" aria-label="Terminar sessão" title="Terminar sessão" className={`${iconBtn} hidden sm:grid`}
            onClick={async () => { await logout(); navigate("/"); }}>
            <LogOut className="h-[18px] w-[18px]" />
          </button>
          <button type="button" className={`${iconBtn} lg:hidden`} onClick={() => setMenuOpen((v) => !v)} data-testid="mobile-menu-btn" aria-label="Menu" aria-expanded={menuOpen}>
            {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {menuOpen && (
        <div className="lg:hidden border-t bg-card/95 backdrop-blur-xl px-4 py-4 max-h-[calc(100vh-4rem)] overflow-y-auto pb-28" data-testid="mobile-menu">
          <div className="flex items-center justify-between gap-2 mb-3 sm:hidden">
            <MarketToggle />
            <button type="button" className="h-11 px-3 rounded-xl border text-sm inline-flex items-center gap-2" onClick={async () => { await logout(); navigate("/"); }}>
              <LogOut className="h-4 w-4" /> Terminar sessão
            </button>
          </div>
          <Link to="/apps" className="workspace-all-tools flex items-center gap-3 min-h-[48px] px-3 rounded-2xl border border-dashed mb-4 font-semibold text-sm" data-testid="mobile-all-tools">
            <LayoutGrid className="h-5 w-5 text-primary" /> Todas as ferramentas <ChevronRight className="h-4 w-4 ml-auto text-muted-foreground" />
          </Link>
          <div className="grid gap-4 sm:grid-cols-2">
            {FAMILY_ORDER.map((f) => {
              const items = links.filter((l) => l.family === f && !l.home);
              if (!items.length) return null;
              return (
                <section key={f} className="cp-glass rounded-2xl p-3" data-testid={`mobile-family-${f}`}>
                  <p className="flex items-center gap-2.5 px-1 pb-2">
                    <AppTile icon={FAMILY_ICONS[f]} family={f} size={30} />
                    <span className="font-display font-semibold">{familyLabel(f)}</span>
                  </p>
                  <div className="grid">
                    {items.map((l) => <NavItem key={l.to} link={l} active={active === l.to} size={28} onClick={() => setMenuOpen(false)} />)}
                  </div>
                </section>
              );
            })}
          </div>
        </div>
      )}
      <ToolSearch open={searchOpen} onOpenChange={setSearchOpen} links={links} />
    </header>
  );
}

export function WorkspaceSidebar() {
  const { user } = useAuth();
  const links = useWorkspaceLinks();
  const favs = useFavorites();
  const location = useLocation();
  const active = activeWorkspaceLink(location.pathname, links);
  const essentials = workspaceEssentials(links, isProfessional(user));
  const favorites = favs.map((to) => links.find((l) => l.to === to)).filter((l) => l && !essentials.includes(l));
  const title = "px-2.5 pt-4 pb-1.5 text-[10.5px] font-bold uppercase tracking-[0.12em] text-muted-foreground";

  return (
    <aside className="workspace-sidebar hidden lg:flex flex-col w-[248px] shrink-0 sticky top-16 h-[calc(100vh-4rem)] overflow-y-auto border-r px-3 py-3" data-testid="workspace-sidebar" aria-label="Navegação">
      <p className={title}>Essenciais</p>
      {essentials.map((l) => <NavItem key={l.to} link={l} active={active === l.to} />)}
      {favorites.length > 0 && <>
        <p className={`${title} flex items-center gap-1.5`}><Star className="h-3 w-3" /> Favoritos</p>
        {favorites.map((l) => <NavItem key={l.to} link={l} active={active === l.to} />)}
      </>}
      <p className={title}>Espaços de trabalho</p>
      {FAMILY_ORDER.filter((f) => links.some((l) => l.family === f && !l.home)).map((f) => (
        <Link key={f} to={`/apps#${f}`} data-testid={`nav-family-${f}`} title={familySub(f)}
          className="workspace-nav-link flex items-center gap-3 min-h-[44px] px-2.5 py-1.5 rounded-xl text-[13.5px] font-medium text-foreground/85 hover:bg-background/70 hover:text-foreground transition-colors">
          <AppTile icon={FAMILY_ICONS[f]} family={f} size={30} />
          <span className="truncate">{familyLabel(f)}</span>
        </Link>
      ))}
      <Link to="/apps" aria-current={location.pathname === "/apps" ? "page" : undefined} data-testid="nav-all-tools"
        className="workspace-all-tools workspace-nav-link mt-4 flex items-center gap-3 min-h-[46px] px-3 rounded-xl border border-dashed text-[13.5px] font-semibold hover:bg-background/70 transition-colors">
        <LayoutGrid className="h-[18px] w-[18px] text-primary" /> Todas as ferramentas
      </Link>
      <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_TOOL_SEARCH))}
        className="mt-2 flex items-center gap-2 min-h-[40px] px-3 rounded-xl text-[12.5px] text-muted-foreground hover:text-foreground transition-colors">
        <Search className="h-3.5 w-3.5" /> Pesquisar <kbd className="ml-auto text-[10px] border rounded px-1.5 py-0.5">Ctrl K</kbd>
      </button>
    </aside>
  );
}
