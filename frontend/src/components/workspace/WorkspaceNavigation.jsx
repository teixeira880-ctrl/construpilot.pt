import "@/styles/workspace-design.css";
import "@/styles/workspace-ambient.css";
import { WorkspaceBackdrop, useWorkspaceMotion } from "./WorkspaceBackdrop";
import { useExperienceCopy } from "./experienceCopy";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Search, Menu, ArrowRight, Plus, Sun, Moon, LogOut, Settings2, X, Grid2X2, ChevronDown, Star, PanelLeftClose, PanelLeftOpen, Download, Sparkles, LifeBuoy, Waves } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { usePermissions } from "@/context/PermissionContext";
import { useBilling } from "@/context/BillingContext";
import { LangToggle, useI18n } from "@/context/I18nContext";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import PushToggle from "@/components/PushToggle";
import { NotificationsBell } from "@/components/NotificationsBell";
import { AssistantActivity } from "@/components/assistant/AssistantActivity";
import { workspaceLinks, isProfessional, activeWorkspaceLink, OPEN_WORKSPACE_MENU, WORKSPACE_GROUPS, workspaceEssentials, benefitFor } from "./navigation";
import { normalizeSearch, useWorkspaceCopy } from "./copy";
import { translatedToolLabel } from "./translations";
import { UpgradeLock } from "@/components/UpgradeLock";
import InstallAppButton from "@/components/InstallAppButton";

export default function WorkspaceNavigation() {
  const { user, logout, setUser } = useAuth();
  const { can } = usePermissions();
  const { tier } = useBilling();
  const { t, lang } = useI18n();
  const ui = useWorkspaceCopy();
  const experience = useExperienceCopy();
  const motion = useWorkspaceMotion();
  const location = useLocation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("essentials");
  const titleRef = useRef(null);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));
  const searchRef = useRef(null);
  const returnFocus = useRef(null);
  const [sidebarPinned, setSidebarPinned] = useState(() => localStorage.getItem("construpilot_sidebar_pinned") !== "false");
  useEffect(() => {
    document.documentElement.classList.toggle("cp-sidebar-unpinned", !sidebarPinned);
    localStorage.setItem("construpilot_sidebar_pinned", sidebarPinned ? "true" : "false");
  }, [sidebarPinned]);
  const links = workspaceLinks(user, can, tier);
  const isPro = isProfessional(user);
  const active = activeWorkspaceLink(location.pathname, links);
  const label = (item) => item.ui ? ui(item.ui) : translatedToolLabel(item, lang, t);
  const deckLabel = { pt: "Apresentação", en: "Presentation", fr: "Apresentação" }[lang] || "Apresentação";
  const groups = WORKSPACE_GROUPS.filter(g => g !== "favorites");
  const favorites = Array.isArray(user?.nav_favorites) ? user.nav_favorites : [];
  const favoriteLinks = favorites.map(to => links.find(l => l.to === to)).filter(Boolean);
  const essentials = workspaceEssentials(links, isPro);
  const needle = normalizeSearch(query);
  const filtered = needle ? links.filter(item => normalizeSearch(`${label(item)} ${item.label} ${item.words || ""} ${ui(item.group)}`).includes(needle))
    : category === "essentials" ? essentials : category === "favorites" ? favoriteLinks : category === "all" ? links : links.filter(item => item.group === category);
  const extraFavorites = favoriteLinks.filter(item => !essentials.some(e => e.to === item.to));
  const currentExtra = links.find(item => item.to === active && !essentials.some(e => e.to === active) && !extraFavorites.slice(0, 4).some(e => e.to === active));
  const toggleFavorite = async (to) => {
    const next = favorites.includes(to) ? favorites.filter(f => f !== to) : [...favorites, to].slice(-30);
    setUser({ ...user, nav_favorites: next });
    try { await api.put("/auth/nav-favorites", { favorites: next }); } catch { toast.error(ui("loadError")); }
  };

  const openTools = () => {
    returnFocus.current = document.activeElement;
    setQuery(""); setCategory("essentials"); setOpen(true);
  };
  useEffect(() => {
    const shortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); openTools();
      }
    };
    window.addEventListener("keydown", shortcut);
    window.addEventListener(OPEN_WORKSPACE_MENU, openTools);
    return () => { window.removeEventListener("keydown", shortcut); window.removeEventListener(OPEN_WORKSPACE_MENU, openTools); };
  }, []);
  useEffect(() => { setOpen(false); }, [location.pathname, location.search]);
  useEffect(() => {
    const sync = () => setDark(document.documentElement.classList.contains("dark"));
    window.addEventListener("construpilot-theme", sync);
    return () => window.removeEventListener("construpilot-theme", sync);
  }, []);

  const toggleTheme = () => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("construpilot_theme", next ? "dark" : "light");
    setDark(next);
    window.dispatchEvent(new Event("construpilot-theme"));
    api.put("/auth/theme", { theme: next ? "dark" : "light" }).catch(() => {});
  };
  const signOut = async () => {
    try { await logout(); navigate("/"); } catch { toast.error(ui("loadError")); }
  };
  const primary = links.find(l => l.to === "/devis-editeur" && !l.locked) || links.find(l => l.to === "/estimation");
  const renderLink = (item, directory = false) => {
    const to = item.locked ? "/planos" : item.to;
    const lockIcon = item.locked
      ? <UpgradeLock title={label(item)} requiredLevel={item.requiredLevel} benefit={benefitFor(item.to, item.requiredLevel)} className="ms-auto" />
      : null;
    const link = <Link key={item.to} to={to} onClick={() => setOpen(false)} aria-current={!item.locked && active === item.to ? "page" : undefined}
      data-testid={`${directory ? "tool" : "workspace-nav"}-${item.to.slice(1)}`} data-tool-link={directory || undefined}
      data-locked={item.locked || undefined}
      className={`${directory ? "workspace-tool" : `workspace-nav-link ${item.to === "/assistant" ? "workspace-nav-assistant" : ""}`}${item.locked ? " workspace-locked" : ""}`}>
      <item.icon size={18} aria-hidden="true" /><span>{label(item)}</span>
      {item.locked ? lockIcon : (directory && <ArrowRight size={15} className="ms-auto" aria-hidden="true" />)}
    </Link>;
    if (!directory || item.locked) return link;
    const fav = favorites.includes(item.to);
    return <div key={item.to} className="workspace-tool-row">{link}
      <button type="button" className="workspace-fav-toggle" aria-pressed={fav} aria-label={ui(fav ? "removeFavorite" : "addFavorite")} title={ui(fav ? "removeFavorite" : "addFavorite")}
        data-testid={`tool-fav-${item.to.slice(1)}`} onClick={() => toggleFavorite(item.to)}><Star size={16} aria-hidden="true" /></button>
    </div>;
  };

  return <>
    <WorkspaceBackdrop paused={motion.paused || motion.reduced} />
    <a href="#workspace-main" className="workspace-skip" data-testid="workspace-skip-content">{ui("skip")}</a>
    <header className="workspace-header">
      {!sidebarPinned && <button type="button" className="workspace-icon-button workspace-reopen-menu" onClick={openTools} aria-label={experience("showMenu")} data-testid="workspace-reopen-menu"><Menu size={20} /></button>}
      <Link to="/dashboard" className="workspace-brand" data-testid="nav-logo" aria-label="ConstruPilot">
        <img src="/construpilot-icon.png" alt="" width="34" height="34" />
        <span>Constru<span className="text-primary">Pilot</span></span>
      </Link>
      <button type="button" onClick={openTools} className="workspace-search-trigger" data-testid="workspace-search-trigger" aria-label={ui("search")} aria-haspopup="dialog">
        <Search size={18} aria-hidden="true" /><span>{ui("search")}</span><kbd>Ctrl K</kbd>
      </button>
      <div className="workspace-header-actions">
        <div className="workspace-desktop-setting"><LangToggle /></div>
        <button type="button" onClick={toggleTheme} className="workspace-icon-button workspace-desktop-setting" aria-label={ui("theme")} data-testid="theme-toggle">{dark ? <Sun size={19} /> : <Moon size={19} />}</button>
        <AssistantActivity />
        <NotificationsBell />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button type="button" className="workspace-user-button" aria-label={ui("account")} data-testid="workspace-account-menu">
              <span className="workspace-avatar">{user?.name?.trim()?.charAt(0)?.toUpperCase() || "C"}</span><ChevronDown size={14} aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="workspace-account-dropdown" data-testid="workspace-account-dropdown">
            <div className="px-2 py-2" data-testid="workspace-account-identity"><p className="font-semibold text-sm truncate max-w-56">{user?.name}</p><p className="text-xs text-muted-foreground mt-1">{ui(isPro ? "professional" : "personal")}</p></div>
            <DropdownMenuSeparator />
            <DropdownMenuItem asChild data-testid="workspace-account-deck">
              <a href="/presentation/index.html" target="_blank" rel="noopener noreferrer"><Download size={16} />{deckLabel} (PT/FR/EN)</a>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            {links.filter(l => ["/compte", "/preferences", "/planos", "/admin"].includes(l.to)).map(item => <DropdownMenuItem asChild key={item.to}><Link to={item.to} data-testid={`workspace-account-${item.to.slice(1)}`}><item.icon size={16} />{label(item)}</Link></DropdownMenuItem>)}
            <DropdownMenuSeparator />
            <div className="px-2 py-1.5 workspace-account-install" data-testid="workspace-account-install"><InstallAppButton compact /></div>
            <DropdownMenuItem onSelect={signOut} data-testid="logout-btn"><LogOut size={16} />{ui("logout")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        <button type="button" className="workspace-icon-button workspace-mobile-menu" onClick={openTools} aria-label={ui("menu")} aria-haspopup="dialog" data-testid="mobile-menu-btn"><Menu size={21} /></button>
      </div>
    </header>
    <div className="workspace-sidebar-hotzone" aria-hidden="true" data-testid="sidebar-hover-hotzone" />
    <aside className="workspace-sidebar" aria-label={ui("workspace")}>
      <div className="workspace-sidebar-top">
        <div className="workspace-sidebar-title" data-testid="workspace-account-type">{ui(isPro ? "professional" : "personal")}</div>
        <button type="button" className="workspace-pin-toggle" onClick={() => setSidebarPinned((p) => !p)}
          aria-pressed={sidebarPinned} data-testid="sidebar-pin-toggle"
          aria-label={experience(sidebarPinned ? "unpin" : "pin")} title={experience(sidebarPinned ? "unpin" : "pin")}>
          {sidebarPinned ? <PanelLeftClose size={16} /> : <PanelLeftOpen size={16} />}
        </button>
      </div>
      {primary && <Button asChild className="workspace-create"><Link to={primary.to} data-testid="workspace-create"><Plus size={17} />{label(primary)}</Link></Button>}
      {!isPro && <Link to="/planos" className="workspace-go-pro" data-testid="workspace-go-pro"><Sparkles size={16} />{experience("upgrade")}</Link>}
      <nav className="workspace-sidebar-links" aria-label={ui("menu")}>
        <div className="workspace-nav-group" data-testid="workspace-nav-essentials"><p>{experience("essentials")}</p>{essentials.map(item => renderLink(item))}</div>
        {extraFavorites.length > 0 && <div className="workspace-nav-group" data-testid="workspace-nav-favorites"><p>{ui("favorites")}</p>
          {extraFavorites.slice(0, 4).map(item => renderLink(item))}
          {extraFavorites.length > 4 && <button type="button" className="workspace-nav-link" onClick={() => { openTools(); setCategory("favorites"); }}>{experience("moreFavorites")}</button>}
        </div>}
        {currentExtra && <div className="workspace-nav-group"><p>{experience("current")}</p>{renderLink(currentExtra)}</div>}
        <button type="button" className="workspace-nav-link workspace-all-tools" onClick={openTools} aria-haspopup="dialog" data-testid="workspace-all-tools"><Grid2X2 size={18} />{ui("allTools")}<Search size={15} className="ms-auto" /></button>
        <a className="workspace-nav-link" href="/presentation/index.html" target="_blank" rel="noopener noreferrer" data-testid="workspace-nav-deck" title="ConstruPilot — PT / FR / EN"><Download size={18} />{deckLabel}</a>
      </nav>
      <Link to="/aide" className="workspace-help-card" data-testid="workspace-help"><LifeBuoy size={19} /><span><strong>{experience("help")}</strong><small>{experience("helpHint")}</small></span><ArrowRight size={15} /></Link>
      <Link className="workspace-sidebar-account" to="/compte" data-testid="workspace-sidebar-account"><Settings2 size={17} />{ui("account")}<ArrowRight size={15} className="ms-auto" /></Link>
    </aside>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="workspace-directory" onOpenAutoFocus={(event) => { event.preventDefault(); (window.matchMedia("(max-width: 767px)").matches ? titleRef.current : searchRef.current)?.focus(); }}
        onCloseAutoFocus={(event) => { event.preventDefault(); if (returnFocus.current?.isConnected) returnFocus.current.focus(); }} data-testid="workspace-directory">
        <div className="pe-8"><DialogTitle ref={titleRef} className="workspace-directory-title" tabIndex={-1}>{experience("explore")}</DialogTitle><DialogDescription className="mt-2">{experience("exploreHint")}</DialogDescription></div>
        <div className="workspace-search-field"><Search size={18} aria-hidden="true" /><input ref={searchRef} value={query} onChange={e => setQuery(e.target.value)} aria-label={ui("search")} placeholder={ui("search")}
          onKeyDown={e => { if (["ArrowDown", "Enter"].includes(e.key) && !e.nativeEvent.isComposing) { const first = e.currentTarget.closest('[role="dialog"]')?.querySelector("[data-tool-link]"); if (first) { e.preventDefault(); if(e.key === "Enter") first.click(); else first.focus(); } } }} data-testid="workspace-tool-search" />
          {query && <button type="button" aria-label={ui("clear")} data-testid="workspace-search-clear" onClick={() => { setQuery(""); searchRef.current?.focus(); }}><X size={17} /></button>}
        </div>
        <div className="workspace-directory-filter"><label htmlFor="workspace-tool-category">{experience("category")}</label><select id="workspace-tool-category" value={category} onChange={e => { setCategory(e.target.value); setQuery(""); }} data-testid="workspace-tool-category">
          <option value="essentials">{experience("essentials")}</option><option value="all">{experience("all")}</option><option value="favorites">{ui("favorites")}</option>
          {groups.filter(group => links.some(item => item.group === group)).map(group => <option key={group} value={group}>{ui(group)}</option>)}
        </select><span role="status" aria-live="polite" data-testid="workspace-tool-count">{filtered.length}</span></div>
        <div className="workspace-directory-results">
          {!filtered.length && <p className="py-8 text-sm text-muted-foreground" role="status" data-testid="workspace-search-empty">{ui("noResults")}</p>}
          {!needle && ["essentials", "favorites"].includes(category) ? <div className="workspace-tools-grid">{filtered.map(item => renderLink(item, true))}</div> : groups.filter(group => filtered.some(l => l.group === group)).map(group => <section key={group}>
            <h2>{ui(group)}</h2><div className="workspace-tools-grid">{filtered.filter(l => l.group === group).map(item => renderLink(item, true))}</div>
          </section>)}
        </div>
        <div className="workspace-directory-settings flex-wrap"><Link to="/compte" onClick={() => setOpen(false)} className="workspace-directory-account" data-testid="workspace-directory-account"><Settings2 size={17} />{experience("settings")}<ArrowRight size={15} /></Link><div className="workspace-directory-push"><PushToggle testId="workspace-directory-push" /></div><span className="text-sm text-muted-foreground">{ui("settings")}</span><LangToggle testId="workspace-directory-language" /><button type="button" className="workspace-icon-button" aria-label={ui("theme")} data-testid="workspace-directory-theme" onClick={toggleTheme}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button>
          <button type="button" className="workspace-motion-control" data-testid="workspace-motion-toggle" aria-pressed={!motion.paused && !motion.reduced} disabled={motion.reduced} onClick={motion.toggle}>
            <Waves size={17} aria-hidden="true" /><span>{experience("animatedBackground")}</span><span>{experience(motion.reduced ? "motionReduced" : motion.paused ? "motionPaused" : "motionOn")}</span>
          </button>
        </div>
      </DialogContent>
    </Dialog>
  </>;
}

