import { useExperienceCopy } from "@/components/workspace/experienceCopy";
import { AssistantIcon } from "@/components/workspace/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, FolderOpen, Trash2, FileSearch, Bell, HardHat, Sparkles, TrendingUp, Ruler, Search, ChevronDown, Grid2X2, Loader2, X,
  FileText, Receipt, ArrowRight, Phone, Mail, MapPin, CalendarClock, Euro, User as UserIcon, FileSpreadsheet, Wrench, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, eur, num } from "@/lib/api";
import { fetchProjects } from "@/lib/offlineProjects";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { useI18n } from "@/context/I18nContext";
import { OnboardingTour } from "@/components/OnboardingTour";
import { StarterChecklist } from "@/components/StarterChecklist";
import { TodayBlock } from "@/components/dashboard/TodayBlock";
import { Stat } from "@/components/Bits";
import { RevenueChart } from "@/components/RevenueChart";
import { PriceLibrary } from "@/components/PriceLibrary";
import { useConfirm } from "@/components/ConfirmProvider";
import { normalizeSearch, useWorkspaceCopy } from "@/components/workspace/copy";
import { usePermissions } from "@/context/PermissionContext";
import { CotesTile } from "@/components/CotesTile";
import { PermissionNotice } from "@/components/workspace/PermissionNotice";
import { UpgradeLock } from "@/components/UpgradeLock";
import { benefitFor } from "@/components/workspace/navigation";


export default function Dashboard() {
  const { user } = useAuth();
  const { tier } = useBilling();
  const { can } = usePermissions();
  const RANK = { particulier_gratuit: 0, particulier_payant: 1, pro: 2, business: 3 };
  // Source de vérité : le niveau d'offre (comme engines/access.py). Un account_type
  // nul/absent NE vaut PAS « pro » — il retombe sur particulier_gratuit.
  const level = user?.role === "admin" ? "business" : (() => {
    const base = user?.account_type === "pro" ? "pro" : "particulier_gratuit";
    const fromTier = { pro_business: "business", pro: "pro", premium: "particulier_payant", project_pass: "particulier_payant" }[tier];
    return fromTier && RANK[fromTier] > RANK[base] ? fromTier : base;
  })();
  const professionalAccount = RANK[level] >= RANK.pro;
  const canAssistant = RANK[level] >= RANK.particulier_payant;
  const isPro = professionalAccount && can("dashboard");
  const LEVEL_LABELS = { particulier_payant: "Particular Pagante", pro: "Pro", business: "Business" };
  const lockedUpsell = [
    { to: "/assistant", icon: AssistantIcon, title: "Assistente Construção", desc: "Chat, cartas e relatórios IA", min: "particulier_payant" },
    { to: "/devis-editeur", icon: FileText, title: "Orçamentos e faturas", desc: "Crie orçamentos e faturas profissionais", min: "pro" },
    { to: "/clients", icon: Users, title: "Clientes", desc: "Fichas de clientes e histórico", min: "pro" },
    { to: "/chantiers", icon: HardHat, title: "Dossiers de obra", desc: "Plantas, fotografias e acompanhamento por obra", min: "pro" },
  ].filter((f) => RANK[level] < RANK[f.min]);
  const ui = useWorkspaceCopy();
  const experience = useExperienceCopy();
  const confirm = useConfirm();
  const [projectQuery, setProjectQuery] = useState("");
  const [deleting, setDeleting] = useState(null);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [loadState, setLoadState] = useState({ projects: "loading", quotes: "loading", alerts: "loading" });
  const generation = useRef(0);
  const { t, lang } = useI18n();
  const [projects, setProjects] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [plans, setPlans] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [leads, setLeads] = useState([]);
  const [onboarding, setOnboarding] = useState(null);
  const [tab, setTab] = useState("projects");
  const [selectedLead, setSelectedLead] = useState(null);
  const unreadLeads = leads.filter((l) => !l.viewed).length;
  const markLeadsSeen = () => {
    if (unreadLeads === 0) return;
    api.post("/leads/mine/mark-viewed").catch(() => {});
    setLeads((ls) => ls.map((l) => ({ ...l, viewed: true })));
  };

  const load = useCallback(async () => {
    if (!user?.user_id) return;
    const request = ++generation.current;
    // Projects: offline-aware (cache-through) so they stay visible without network.
    setLoadState((s) => ({ ...s, projects: "loading" }));
    fetchProjects(user.user_id).then(({ list }) => {
      if (request === generation.current) { setProjects(list); setLoadState((s) => ({ ...s, projects: "ready" })); }
    }).catch(() => { if (request === generation.current) setLoadState((s) => ({ ...s, projects: "error" })); });
    const jobs = [["quotes", "/quotes", setQuotes], ["alerts", "/prices/alerts", setAlerts]];
    api.get("/onboarding/status").then(({ data }) => setOnboarding(data)).catch(() => setOnboarding(null));
    if (isPro) jobs.push(["plans", "/takeoffs", setPlans], ["leads", "/leads/mine", setLeads]);
    else { setPlans([]); setLeads([]); }
    setLoadState((s) => ({ ...s, ...Object.fromEntries(jobs.map(([key]) => [key, "loading"])) }));
    const results = await Promise.allSettled(jobs.map(([,url]) => api.get(url)));
    if (request !== generation.current) return;
    const state = {};
    results.forEach((result, index) => {
      const [key,,setter] = jobs[index];
      if (result.status === "fulfilled") {
        const data = result.value.data;
        setter(key === "plans" ? data?.plans || [] : Array.isArray(data) ? data : []);
        state[key] = "ready";
      } else state[key] = "error";
    });
    setLoadState(previous => ({ ...previous, ...state }));
  }, [isPro, user?.user_id]);
  useEffect(() => { load(); return () => { generation.current += 1; }; }, [load]);
  useEffect(() => {
    const onSynced = () => load();
    window.addEventListener("construpilot-offline-synced", onSynced);
    return () => window.removeEventListener("construpilot-offline-synced", onSynced);
  }, [load]);

  const remove = async (id) => {
    if (deleting || !await confirm({ title: ui("deleteTitle"), description: ui("deleteDesc"), confirmLabel: ui("delete"), cancelLabel: ui("cancel") })) return;
    setDeleting(id);
    try { await api.delete(`/projects/${id}`); toast.success(t("dash.project_deleted")); await load(); }
    catch { toast.error(ui("deleteError")); }
    finally { setDeleting(null); }
  };
  const filteredProjects = projects.filter(p => normalizeSearch(`${p.name || ""} ${p.estimation?.project_type_name || ""}`).includes(normalizeSearch(projectQuery)));
  const loadNotice = (key) => loadState[key] === "loading"
    ? <div className="surface p-8 flex items-center gap-3 text-sm text-muted-foreground" role="status" data-testid={`dashboard-${key}-loading`}><Loader2 className="h-4 w-4 animate-spin" />{ui("loading")}</div>
    : loadState[key] === "error" ? <div className="dashboard-error" role="alert" data-testid={`dashboard-${key}-error`}><span>{ui("loadError")}</span><Button variant="outline" onClick={load} data-testid={`dashboard-${key}-retry`}>{ui("retry")}</Button></div> : null;

  const totalBudget = projects.reduce((s, p) => s + (p.budget || 0), 0);
  const totalSurface = projects.reduce((s, p) => s + (p.surface || 0), 0);

  return (
    <div className="dashboard-workspace">
      {professionalAccount && <PermissionNotice />}
      {guideOpen && <OnboardingTour forceOpen onClose={() => setGuideOpen(false)} />}
      <header className="dashboard-heading">
        <div><p className="dashboard-greeting">{experience("hello")}{user?.name ? `, ${user.name.split(" ")[0]}` : ""}</p><h1>{experience("overview")}</h1><p>{experience("intro")}</p></div>
        <div className="dashboard-heading-actions"><span className="dashboard-date">{new Date().toLocaleDateString({pt:"pt-PT",en:"en-GB"}[lang] || "fr-FR", {weekday:"long",day:"numeric",month:"long"})}</span><Button asChild><Link to={isPro && can("devis") ? "/devis-editeur" : "/estimation"} data-testid="dashboard-primary-create"><Plus size={17} />{experience(isPro && can("devis") ? "quoteShort" : "estimateShort")}</Link></Button></div>
      </header>
      <div className="dashboard-quick-actions" data-testid="dash-quick-actions">
        {[
          canAssistant
            ? { to: "/assistant", icon: AssistantIcon, title: experience("assistantShort"), desc: ui("askDesc"), testid: "quick-assistant" }
            : { to: "/btp-solver", icon: Wrench, title: "Resolver um problema", desc: "Faça a sua pergunta sobre obras", testid: "quick-solver" },
          isPro ? { to: "/plan", icon: Ruler, title: experience("planShort"), desc: ui("planDesc"), testid: "quick-plan" } : { to: "/estimation", icon: FileText, title: ui("estimate"), desc: ui("estimateDesc"), testid: "quick-estimate" },
          isPro ? { to: "/chantiers", icon: HardHat, title: ui("chantiers"), desc: experience("sitesDesc"), testid: "quick-chantiers" } : { to: "/calculateurs", icon: Wrench, title: ui("calculators"), desc: ui("personalMore"), testid: "quick-calculators" },
          isPro && can("devis") ? { to: "/devis-editeur", icon: FileText, title: experience("quoteShort"), desc: ui("quoteDesc"), testid: "quick-new-quote" } : { to: "/prix", icon: Search, title: ui("prices"), desc: ui("pricesDesc"), testid: "quick-prices" },
        ].map(a => <Link key={a.to} to={a.to} className="dashboard-quick-action" data-testid={a.testid}><span><a.icon size={21} /></span><span className="flex-1 min-w-0"><strong>{a.title}</strong><small>{a.desc}</small></span><ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" /></Link>)}
      </div>
      <div className="dashboard-stats">
        <Stat label={t("dash.stat_projects")} value={loadState.projects === "ready" ? num(projects.length) : "—"} testId="stat-projects" />
        <Stat label={t("dash.stat_budget")} value={loadState.projects === "ready" ? eur(totalBudget) : "—"} testId="stat-budget" accent />
        <Stat label={t("dash.stat_surface")} value={loadState.projects === "ready" ? `${num(totalSurface, 1)} m²` : "—"} testId="stat-surface" />
        {isPro ? <Stat label={t("dash.stat_leads")} value={loadState.leads === "ready" ? num(leads.length) : "—"} testId="stat-leads"
              badge={unreadLeads > 0 ? unreadLeads : null}
              onClick={() => {
                setTab("leads");
                markLeadsSeen();
                document.querySelector('[data-testid="dash-tab-leads"]')?.scrollIntoView({ behavior: "smooth", block: "center" });
              }} /> : <Stat label={t("dash.tab_quotes")} value={loadState.quotes === "ready" ? num(quotes.length) : "—"} testId="stat-quotes" />}
      </div>

      <TodayBlock />
      <div className="dashboard-section-heading"><h2>{ui("activity")}</h2>
        {tab === "projects" && <div className="workspace-search-field"><Search size={17} aria-hidden="true" /><input aria-label={ui("projectSearch")} placeholder={ui("projectSearch")} value={projectQuery} onChange={e => setProjectQuery(e.target.value)} data-testid="dashboard-project-search" />{projectQuery && <button type="button" aria-label={ui("clear")} data-testid="dashboard-project-search-clear" onClick={() => setProjectQuery("")}><X size={16} /></button>}</div>}
      </div>
      <Tabs className="dashboard-tabs" value={tab} onValueChange={(v) => { setTab(v); if (v === "leads") markLeadsSeen(); }}>
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="projects" className="rounded-sm" data-testid="dash-tab-projects">{t("dash.tab_projects")}</TabsTrigger>
          <TabsTrigger value="quotes" className="rounded-sm" data-testid="dash-tab-quotes">{t("dash.tab_quotes")}</TabsTrigger>
          <TabsTrigger value="alerts" className="rounded-sm" data-testid="dash-tab-alerts">{t("dash.tab_alerts")}</TabsTrigger>
          {isPro && <TabsTrigger value="leads" className="rounded-sm relative" data-testid="dash-tab-leads">
            {t("dash.tab_leads")}
            {unreadLeads > 0 && (
              <span className="ml-1.5 min-w-4 h-4 px-1 inline-grid place-items-center rounded-full bg-red-500 text-white text-[10px] font-bold">{unreadLeads}</span>
            )}
          </TabsTrigger>}
        </TabsList>

        <TabsContent value="projects" className="mt-6">
          {loadNotice("projects") || (projects.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="projects-empty">
              <FolderOpen className="h-8 w-8 mx-auto text-muted-foreground" />
              <h3 className="mt-4 font-display text-lg font-semibold">{ui("projectEmpty")}</h3><p className="mt-2 text-sm text-muted-foreground max-w-md mx-auto">{ui("projectEmptyDesc")}</p>
              <Button asChild className="mt-5 h-11"><Link to="/estimation" data-testid="dashboard-first-estimate"><Plus size={16} />{ui("estimate")}</Link></Button>
            </div>
          ) : filteredProjects.length === 0 ? <div className="surface p-8 text-center text-sm text-muted-foreground" role="status" data-testid="dashboard-project-search-empty">{ui("noProjectsFound")}</div> : (
            <div className="grid md:grid-cols-2 2xl:grid-cols-3 gap-4" data-testid="projects-grid">
              {filteredProjects.map((p) => {
                const done = Object.values(p.progress || {}).filter((v) => v === "done").length;
                const total = Object.keys(p.progress || {}).length;
                return (
                  <div key={p.project_id} className="surface p-5 flex flex-col dashboard-project" data-testid={`project-card-${p.project_id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="overline text-muted-foreground">{p.estimation?.project_type_name}</p>
                        <h3 className="mt-2 font-display text-lg font-semibold">{p.name}</h3>
                      </div>
                      <Badge variant="outline" className="rounded-sm shrink-0 num" data-testid={`project-surface-${p.project_id}`}>{num(p.surface, 0)} m²</Badge>
                    </div>
                    <p className="num mt-4 text-xl font-bold text-primary" data-testid={`project-budget-${p.project_id}`}>{eur(p.budget)}</p>
                    <div className="dashboard-project-progress">
                      <div><span>{experience(total ? "progress" : "noLots")}</span>{total > 0 && <span>{done}/{total}</span>}</div>
                      {total > 0 && <div className="dashboard-progress-track" role="progressbar" aria-label={experience("progress")} aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}><span style={{width:`${100 * done / total}%`}} /></div>}
                    </div>
                    <div className="mt-5 flex gap-2 pt-4 border-t border-border dashboard-project-actions">
                      <Button asChild variant="outline" size="sm" className="flex-1 rounded-sm"><Link to={`/projet/${p.project_id}`} data-testid={`open-project-${p.project_id}`}>{t("dash.open_project")}</Link></Button>
                      <Button variant="ghost" size="sm" disabled={!!deleting} aria-label={`${ui("delete")} : ${p.name}`} onClick={() => remove(p.project_id)} data-testid={`delete-project-${p.project_id}`} className="rounded-sm">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </TabsContent>

        <TabsContent value="quotes" className="mt-6">
          {loadNotice("quotes") || (quotes.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="quotes-empty">
              <FileSearch className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                {t("dash.quotes_empty")} {(isPro || (tier && tier !== "free")) && <Link to="/scanner-devis" className="text-primary" data-testid="dashboard-scan-quote">{t("dash.scan_quote")}</Link>}
              </p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="quotes-list">
              {quotes.map((q) => (
                <div key={q.quote_id} className="surface p-6" data-testid={`dashboard-quote-${q.quote_id}`}>
                  <p className="overline text-muted-foreground">{q.company || t("dash.company")}</p>
                  <p className="num mt-3 text-xl font-bold">{eur(q.analysis?.total_ttc || q.analysis?.total_ht)}</p>
                  <Badge variant="outline" className="mt-3 rounded-sm">{q.analysis?.verdict}</Badge>
                  <p className="mt-3 text-xs text-muted-foreground">{q.analysis?.verdict_label}</p>
                </div>
              ))}
            </div>
          ))}
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          {loadNotice("alerts") || (alerts.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="alerts-empty">
              <Bell className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                {t("dash.alerts_empty")} <Link to="/prix" className="text-primary" data-testid="dashboard-create-price-alert">{t("dash.create_alert")}</Link>
              </p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="alerts-list">
              {alerts.map((a) => (
                <div key={a.alert_id} className="surface p-5 flex flex-wrap items-center gap-4">
                  <div className="flex-1 min-w-[200px]">
                    <p className="font-medium">{a.product}</p>
                    <p className="num text-xs text-muted-foreground">{t("dash.threshold")} {eur(a.target_price)}</p>
                  </div>
                  <p className="num text-lg font-bold">{a.best_price ? eur(a.best_price) : "—"}</p>
                  <Badge variant="outline" className={`rounded-sm ${a.triggered ? "border-emerald-500 text-emerald-500" : ""}`}>
                    {a.triggered ? t("dash.target_reached") : t("dash.watching")}
                  </Badge>
                  <Button
                    variant="ghost" size="sm" className="rounded-sm"
                    aria-label={`${ui("delete")} : ${a.product}`} data-testid={`delete-alert-${a.alert_id}`}
                    onClick={async () => { try { await api.delete(`/prices/alerts/${a.alert_id}`); load(); } catch { toast.error(ui("deleteError")); } }}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          ))}
        </TabsContent>

        <TabsContent value="leads" className="mt-6">
          {loadNotice("leads") || (leads.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="leads-empty">
              <HardHat className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">{t("dash.leads_empty")}</p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="leads-list">
              {leads.map((l) => (
                <button key={l.lead_id} onClick={() => setSelectedLead(l)}
                        data-testid={`lead-item-${l.lead_id}`}
                        className="surface p-5 flex flex-wrap items-center gap-4 text-left w-full transition-colors hover:border-primary/50">
                  <div className="flex-1 min-w-[200px]">
                    <p className="font-medium">{l.name || l.project_snapshot?.name || l.description?.slice(0, 60) || t("dash.request")}</p>
                    <p className="text-xs text-muted-foreground">{[l.address, l.phone].filter(Boolean).join(" · ")}</p>
                  </div>
                  <p className="num font-bold">{eur(l.budget)}</p>
                  <Badge variant="outline" className="rounded-sm">{l.status || "novo"}</Badge>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </button>
              ))}
            </div>
          ))}
        </TabsContent>
      </Tabs>


      {lockedUpsell.length > 0 && (
        <div className="dashboard-upsell" data-testid="dashboard-upsell">
          <div className="dashboard-upsell-head">
            <div><strong><Sparkles size={16} className="text-primary" /> {t("dash.unlock_title", "Desbloqueie mais com uma subscrição")}</strong><small>{t("dash.unlock_desc", "Estas funções estão incluídas nas ofertas pagas.")}</small></div>
            <Button asChild size="sm" className="rounded-sm"><Link to="/tarifs" data-testid="dashboard-upsell-cta">{t("dash.see_plans", "Ver as ofertas")}</Link></Button>
          </div>
          <div className="dashboard-upsell-grid">
            {lockedUpsell.map((f) => (
              <Link key={f.to} to="/tarifs" className="dashboard-upsell-tile" data-testid={`dashboard-locked-${f.to.slice(1)}`} data-locked="true" title={`Função ${LEVEL_LABELS[f.min]} — clique para desbloquear`}>
                <span className="dashboard-upsell-icon"><f.icon size={19} /></span>
                <span className="flex-1 min-w-0"><strong>{f.title}</strong><small>{f.desc}</small></span>
                <span className="dashboard-upsell-badge" onClick={(e) => e.preventDefault()}>
                  <UpgradeLock title={f.title} requiredLevel={f.min} benefit={benefitFor(f.to, f.min)} iconSize={12} />
                  {LEVEL_LABELS[f.min]}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      <details className="dashboard-disclosure" onToggle={e => setExtrasOpen(e.currentTarget.open)} data-testid="dashboard-more-tools">
        <summary data-testid="dashboard-more-tools-toggle"><Grid2X2 size={19} className="text-primary" /><span>{ui("moreTools")}<small>{ui(isPro ? "moreDesc" : "personalMore")}</small></span><ChevronDown size={18} /></summary>
        {extrasOpen && <div className="dashboard-extra-tools">
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline"><Link to="/smart-project" data-testid="dashboard-smart-project"><Sparkles size={16} />{ui("smart")}</Link></Button>
            <Button asChild variant="outline"><Link to="/estimation" data-testid="dashboard-estimate"><Plus size={16} />{ui("estimate")}</Link></Button>
            {isPro && can("factures") && <Button asChild variant="outline"><Link to="/devis-editeur?type=invoice" data-testid="dashboard-new-invoice"><Receipt size={16} />{ui("newInvoice")}</Link></Button>}
          </div>
          {isPro && <>{can("factures") && <RevenueChart />}<CotesTile />
            <Link to="/appro" data-testid="appro-link" className="surface p-5 flex gap-3 items-center"><HardHat size={20} className="text-primary" /><span className="text-sm font-semibold">{t("nav.appro", "Análise técnica & Aprovisionamento IA")}</span><ArrowRight size={17} className="ms-auto" /></Link>
            {can("factures") && <Link to="/rentabilite" data-testid="profitability-link" className="surface p-5 flex gap-3 items-center"><TrendingUp size={20} className="text-primary" /><span className="text-sm font-semibold">{t("nav.profitability", "Relatório de rentabilidade")}</span><ArrowRight size={17} className="ms-auto" /></Link>}
            {can("catalogue") && <PriceLibrary />}
            {can("devis") && <Link to="/dpgf" data-testid="dpgf-link" className="surface p-5 flex gap-3 items-center"><FileSpreadsheet size={20} className="text-primary" /><span className="text-sm font-semibold">{t("nav.dpgf", "Mapa de quantidades do arquiteto → orçamento")}</span><ArrowRight size={17} className="ms-auto" /></Link>}
          </>}
        </div>}
      </details>
      <details className="dashboard-disclosure"><summary data-testid="dashboard-get-started-toggle"><Sparkles size={19} className="text-primary" /><span>{ui("getStarted")}</span><ChevronDown size={18} /></summary><div className="dashboard-extra-tools">
        <StarterChecklist isPro={isPro} status={onboarding} />
        <Button variant="outline" onClick={() => setGuideOpen(true)} data-testid="dashboard-start-tour">{ui("getStarted")}</Button>
      </div></details>

      <Dialog open={!!selectedLead} onOpenChange={(o) => !o && setSelectedLead(null)}>
        <DialogContent className="max-w-lg" data-testid="lead-detail-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HardHat className="h-5 w-5 text-primary" /> {ui("leadTitle")}
            </DialogTitle>
          </DialogHeader>
          {selectedLead && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-base">{selectedLead.name || t("dash.request")}</span>
                <Badge variant="outline" className="rounded-sm">{selectedLead.status || "novo"}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Info icon={Euro} label={ui("budget")} testId="lead-budget" value={selectedLead.budget ? eur(selectedLead.budget) : "—"} />
                <Info icon={MapPin} label={ui("address")} testId="lead-address" value={selectedLead.address || "—"} />
                <Info icon={CalendarClock} label={ui("availability")} testId="lead-availability" value={selectedLead.availability || selectedLead.delay_days ? (selectedLead.availability || `${selectedLead.delay_days} ${ui("days")}`) : "—"} />
                <Info icon={UserIcon} label={ui("trade")} testId="lead-trade" value={selectedLead.trade || "—"} />
              </div>
              {selectedLead.description && (
                <div>
                  <p className="overline text-muted-foreground mb-1">{ui("description")}</p>
                  <p className="whitespace-pre-wrap">{selectedLead.description}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-2 border-t">
                {selectedLead.phone && (
                  <a href={`tel:${selectedLead.phone}`} data-testid="lead-call-btn">
                    <span className="inline-flex items-center gap-2"><Phone className="h-4 w-4" /> {ui("call")}</span>
                  </a>
                )}
                {selectedLead.phone && (
                  <a href={`sms:${selectedLead.phone}`} data-testid="lead-sms-btn">
                    <span className="inline-flex items-center gap-2"><Phone className="h-4 w-4" /> SMS</span>
                  </a>
                )}
                {selectedLead.email && (
                  <a href={`mailto:${selectedLead.email}?subject=${encodeURIComponent(ui("leadSubject"))}`} data-testid="lead-email-btn">
                    <span className="inline-flex items-center gap-2"><Mail className="h-4 w-4" /> E-mail</span>
                  </a>
                )}
              </div>
              {selectedLead.email && <p className="text-xs text-muted-foreground">{selectedLead.email}</p>}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const Info = ({ icon: Icon, label, value, testId }) => (
  <div className="rounded-sm border border-border p-2.5" data-testid={testId}>
    <p className="overline text-muted-foreground flex items-center gap-1"><Icon className="h-3 w-3" /> {label}</p>
    <p className="mt-1 font-medium truncate">{value}</p>
  </div>
);

