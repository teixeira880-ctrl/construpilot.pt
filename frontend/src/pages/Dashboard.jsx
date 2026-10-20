import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, FolderOpen, Trash2, FileSearch, Bell, HardHat, Sparkles, TrendingUp,
  FileText, Receipt, ArrowRight, Phone, Mail, MapPin, CalendarClock, Euro, User as UserIcon,
  Calculator, Lightbulb, PackageCheck,
} from "lucide-react";
import { AppTile } from "@/components/workspace/AppTile";
import { OPEN_TOOL_SEARCH } from "@/components/workspace/WorkspaceNavigation";
import { AssistantHero, WeekGoal } from "@/components/dashboard/Bento";
import "@/styles/workspace-tiles.css";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, eur, num } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { useI18n } from "@/context/I18nContext";
import { OnboardingTour } from "@/components/OnboardingTour";
import { StarterChecklist } from "@/components/StarterChecklist";
import PushToggle from "@/components/PushToggle";
import { Stat } from "@/components/Bits";
import { RevenueChart } from "@/components/RevenueChart";
import { DpgfImport } from "@/components/DpgfImport";
import { PriceLibrary } from "@/components/PriceLibrary";

const STATUS_ICON = { done: "✅", doing: "🔄", todo: "⏳" };

export default function Dashboard() {
  const { user } = useAuth();
  const isPro = user?.account_type !== "particulier" || user?.role === "admin";
  const { tier, active, flags } = useBilling();
  const { t } = useI18n();
  const [projects, setProjects] = useState([]);
  const [projectsLoaded, setProjectsLoaded] = useState(false);
  const [quotes, setQuotes] = useState([]);
  const [plans, setPlans] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [leads, setLeads] = useState([]);
  const [tab, setTab] = useState("projects");
  const [selectedLead, setSelectedLead] = useState(null);
  const unreadLeads = leads.filter((l) => !l.viewed).length;
  const markLeadsSeen = () => {
    if (unreadLeads === 0) return;
    api.post("/leads/mine/mark-viewed").catch(() => {});
    setLeads((ls) => ls.map((l) => ({ ...l, viewed: true })));
  };
  const navigate = useNavigate();

  const load = () => {
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => {}).finally(() => setProjectsLoaded(true));
    api.get("/quotes").then(({ data }) => setQuotes(data)).catch(() => {});
    api.get("/takeoffs").then(({ data }) => setPlans(data?.plans || [])).catch(() => {});
    api.get("/prices/alerts").then(({ data }) => setAlerts(data)).catch(() => {});
    api.get("/leads/mine").then(({ data }) => setLeads(data)).catch(() => {});
  };
  useEffect(load, []);

  const remove = async (id) => {
    await api.delete(`/projects/${id}`);
    toast.success(t("dash.project_deleted"));
    load();
  };

  const projectsReady = projectsLoaded;
  const totalBudget = projects.reduce((s, p) => s + (p.budget || 0), 0);
  const totalSurface = projects.reduce((s, p) => s + (p.surface || 0), 0);

  return (
    <div className="grid gap-7 sm:gap-8">
      <OnboardingTour />
      <StarterChecklist
        isPro={isPro}
        projectDone={projects.length > 0}
        planDone={plans.length > 0}
        quoteDone={quotes.length > 0}
      />
      <header className="flex flex-col lg:flex-row gap-5 lg:items-end justify-between" data-testid="dashboard-heading">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-muted-foreground first-letter:uppercase" data-testid="dashboard-date">
            {new Date().toLocaleDateString("pt-PT", { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1 className="mt-1 font-display text-[34px] sm:text-[46px] font-bold tracking-[-0.035em] leading-[1.05]" data-testid="dashboard-title">
            Olá{user?.name ? ` ${user.name.split(" ")[0]}` : ""}, <span className="cp-grad-text">bora lá?</span>
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {tier === "free" ? (
              <>{t("dash.plan")} <b>{t("dash.free_word")}</b> · {t("dash.free_desc")}</>
            ) : (
              <>{t("dash.plan")} <b className="text-primary">{active?.plan?.name || tier}</b> {t("dash.active_desc")}</>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2.5">
          {tier === "free" && (
            <Button onClick={() => navigate("/tarifs")} data-testid="upgrade-cta" variant="outline" className="rounded-xl h-11 gap-2 bg-card/70 border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground">
              <TrendingUp className="h-4 w-4" />
              {t("dash.upgrade")} {flags?.trial_enabled && flags?.trial_days ? `— ${flags.trial_days} ${t("dash.days_free")}` : ""}
            </Button>
          )}
          <PushToggle />
          <Button onClick={() => navigate("/smart-project")} data-testid="new-smart-project-btn" variant="outline" className="rounded-xl h-11 gap-2 bg-card/70">
            <Sparkles className="h-4 w-4" /> Smart Project
          </Button>
          <Button onClick={() => navigate("/estimation")} data-testid="new-project-btn" className="rounded-xl h-11 gap-2">
            <Plus className="h-4 w-4" /> {t("dash.new_est")}
          </Button>
        </div>
      </header>

      <div className="grid gap-3.5 lg:grid-cols-6" data-testid="dashboard-bento">
        <AssistantHero />
        <WeekGoal projects={projects} ready={projectsReady} />
        <div className="cp-glass cp-lift rounded-3xl p-5 flex flex-col gap-1 lg:col-span-2" data-testid="stat-budget">
          <p className="text-[13px] font-bold text-muted-foreground">{t("dash.stat_budget")}</p>
          <p className="num text-[32px] sm:text-[36px] font-bold tracking-tight leading-none mt-1 text-primary break-words">{projectsReady ? eur(totalBudget) : "—"}</p>
          <p className="text-[12.5px] font-semibold text-muted-foreground mt-auto pt-2">
            {projectsReady ? `${num(projects.length)} ${projects.length === 1 ? "projeto" : "projetos"} · ${num(totalSurface, 1)} m²` : ""}
          </p>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3.5" data-testid="dash-quick-actions">
        {(isPro ? [
          { to: "/devis-editeur", icon: FileText, family: "devis", title: "Novo orçamento", desc: "Crie um orçamento detalhado em poucos cliques", testid: "quick-new-quote" },
          { to: "/devis-editeur?type=invoice", icon: Receipt, family: "devis", title: "Nova fatura", desc: "Emita uma fatura conforme (SAF-T)", testid: "quick-new-invoice" },
          { to: "/factures", icon: TrendingUp, family: "projets", title: "Acompanhamento da faturação", desc: "Recebimentos, dívidas e documentos", testid: "quick-invoicing" },
        ] : [
          { to: "/estimation", icon: FileText, family: "devis", title: "Estimar as minhas obras", desc: "Obtenha uma estimativa detalhada em 30 s", testid: "quick-estimate" },
          { to: "/prix", icon: TrendingUp, family: "devis", title: "Preços dos materiais", desc: "Consulte os preços de mercado atualizados", testid: "quick-prices" },
          { to: "/calculateurs", icon: Calculator, family: "etudes", title: "Calculadoras", desc: "Áreas, volumes e quantidades num instante", testid: "quick-calculators" },
        ]).map((a) => (
          <button
            key={a.to}
            onClick={() => navigate(a.to)}
            data-testid={a.testid}
            className="group cp-glass cp-lift p-5 rounded-[22px] text-left flex items-center gap-4 min-h-[96px]"
          >
            <AppTile icon={a.icon} family={a.family} size={44} />
            <div className="min-w-0 flex-1">
              <p className="font-display font-semibold text-[15px] flex items-center gap-1">
                {a.title}
                <ArrowRight className="h-3.5 w-3.5 opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0" />
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">{a.desc}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="dash-stats grid grid-cols-3 gap-3 stagger">
        <Stat label={t("dash.stat_projects")} value={num(projects.length)} testId="stat-projects" />
        <Stat label={t("dash.stat_surface")} value={`${num(totalSurface, 1)} m²`} testId="stat-surface" />
        <Stat label={t("dash.stat_leads")} value={num(leads.length)} testId="stat-leads"
              badge={unreadLeads > 0 ? unreadLeads : null}
              onClick={() => {
                setTab("leads");
                markLeadsSeen();
                document.querySelector('[data-testid="dash-tab-leads"]')?.scrollIntoView({ behavior: "smooth", block: "center" });
              }} />
      </div>

      <button type="button" onClick={() => window.dispatchEvent(new Event(OPEN_TOOL_SEARCH))} data-testid="dashboard-tip"
        className="cp-glass rounded-2xl px-4 py-3 flex items-center gap-3 text-left text-sm min-h-[52px] hover:bg-card/90 transition-colors">
        <AppTile icon={Lightbulb} family="devis" size={32} />
        <span className="min-w-0"><b className="font-semibold">Dica rápida:</b> <span className="text-muted-foreground">prima <kbd className="text-[11px] border rounded px-1 py-0.5 bg-background/70">Ctrl K</kbd> para abrir qualquer ferramenta em 2 segundos.</span></span>
      </button>

      <RevenueChart />

      <a href="/appro" data-testid="appro-link" className="block cp-glass cp-lift rounded-3xl p-5 sm:p-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-start gap-4 min-w-0">
            <AppTile icon={PackageCheck} family="etudes" size={44} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-display font-bold text-lg">Análise técnica e aprovisionamento IA</span>
                <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Novo</span>
              </div>
              <p className="text-sm text-muted-foreground mt-1">Importe as suas plantas de armaduras → mapa de aço IA (ml, kg, toneladas) → quantidades a encomendar → notas de encomenda aos fornecedores.</p>
            </div>
          </div>
          <span className="text-primary font-bold shrink-0 hidden sm:inline">Abrir →</span>
        </div>
      </a>

      <PriceLibrary />

      <DpgfImport />

      <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v === "leads") markLeadsSeen(); }}>
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="projects" className="rounded-sm" data-testid="dash-tab-projects">{t("dash.tab_projects")}</TabsTrigger>
          <TabsTrigger value="quotes" className="rounded-sm" data-testid="dash-tab-quotes">{t("dash.tab_quotes")}</TabsTrigger>
          <TabsTrigger value="alerts" className="rounded-sm" data-testid="dash-tab-alerts">{t("dash.tab_alerts")}</TabsTrigger>
          <TabsTrigger value="leads" className="rounded-sm relative" data-testid="dash-tab-leads">
            {t("dash.tab_leads")}
            {unreadLeads > 0 && (
              <span className="ml-1.5 min-w-4 h-4 px-1 inline-grid place-items-center rounded-full bg-red-500 text-white text-[10px] font-bold">{unreadLeads}</span>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="projects" className="mt-6">
          {projects.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="projects-empty">
              <FolderOpen className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                {t("dash.projects_empty")}
              </p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 stagger" data-testid="projects-grid">
              {projects.map((p) => {
                const done = Object.values(p.progress || {}).filter((v) => v === "done").length;
                const total = Object.keys(p.progress || {}).length || 1;
                return (
                  <div key={p.project_id} className="surface p-6 flex flex-col transition-transform duration-200 hover:-translate-y-1" data-testid={`project-card-${p.project_id}`}>
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="overline text-muted-foreground">{p.estimation?.project_type_name}</p>
                        <h3 className="mt-2 font-display text-lg font-semibold">{p.name}</h3>
                      </div>
                      <Badge variant="outline" className="rounded-sm shrink-0 num">{num(p.surface, 0)} m²</Badge>
                    </div>
                    <p className="num mt-4 text-xl font-bold text-primary">{eur(p.budget)}</p>
                    <div className="mt-4 flex flex-wrap gap-1 text-xs">
                      {Object.entries(p.progress || {}).slice(0, 6).map(([k, v]) => (
                        <span key={k} className="px-2 py-1 rounded-sm bg-secondary text-muted-foreground">
                          {STATUS_ICON[v]} {p.estimation?.lots?.find((l) => l.key === k)?.name || k}
                        </span>
                      ))}
                    </div>
                    <p className="num mt-4 text-xs text-muted-foreground">
                      <TrendingUp className="inline h-3 w-3 mr-1" />{done}/{total} {t("dash.lots_done")}
                    </p>
                    <div className="mt-6 flex gap-2 pt-4 border-t border-border">
                      <Link to={`/projet/${p.project_id}`} className="flex-1">
                        <Button variant="outline" size="sm" className="w-full rounded-sm" data-testid={`open-project-${p.project_id}`}>
                          {t("dash.open_project")}
                        </Button>
                      </Link>
                      <Button variant="ghost" size="sm" onClick={() => remove(p.project_id)} data-testid={`delete-project-${p.project_id}`} className="rounded-sm">
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </TabsContent>

        <TabsContent value="quotes" className="mt-6">
          {quotes.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="quotes-empty">
              <FileSearch className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                {t("dash.quotes_empty")} <Link to="/scanner-devis" className="text-primary">{t("dash.scan_quote")}</Link>
              </p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="quotes-list">
              {quotes.map((q) => (
                <div key={q.quote_id} className="surface p-6">
                  <p className="overline text-muted-foreground">{q.company || t("dash.company")}</p>
                  <p className="num mt-3 text-xl font-bold">{eur(q.analysis?.total_ttc || q.analysis?.total_ht)}</p>
                  <Badge variant="outline" className="mt-3 rounded-sm">{q.analysis?.verdict}</Badge>
                  <p className="mt-3 text-xs text-muted-foreground">{q.analysis?.verdict_label}</p>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="alerts" className="mt-6">
          {alerts.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="alerts-empty">
              <Bell className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                {t("dash.alerts_empty")} <Link to="/prix" className="text-primary">{t("dash.create_alert")}</Link>
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
                    data-testid={`delete-alert-${a.alert_id}`}
                    onClick={async () => { await api.delete(`/prices/alerts/${a.alert_id}`); load(); }}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="leads" className="mt-6">
          {leads.length === 0 ? (
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
          )}
        </TabsContent>
      </Tabs>

      <Dialog open={!!selectedLead} onOpenChange={(o) => !o && setSelectedLead(null)}>
        <DialogContent className="max-w-lg" data-testid="lead-detail-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <HardHat className="h-5 w-5 text-primary" /> Pedido ConstruPilot
            </DialogTitle>
          </DialogHeader>
          {selectedLead && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-base">{selectedLead.name || t("dash.request")}</span>
                <Badge variant="outline" className="rounded-sm">{selectedLead.status || "novo"}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Info icon={Euro} label="Budget" value={selectedLead.budget ? eur(selectedLead.budget) : "—"} />
                <Info icon={MapPin} label="Morada" value={selectedLead.address || "—"} />
                <Info icon={CalendarClock} label="Disponibilidade" value={selectedLead.availability || selectedLead.delay_days ? (selectedLead.availability || `${selectedLead.delay_days} d`) : "—"} />
                <Info icon={UserIcon} label="Profissão" value={selectedLead.trade || "—"} />
              </div>
              {selectedLead.description && (
                <div>
                  <p className="overline text-muted-foreground mb-1">Descrição</p>
                  <p className="whitespace-pre-wrap">{selectedLead.description}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-2 border-t">
                {selectedLead.phone && (
                  <a href={`tel:${selectedLead.phone}`} data-testid="lead-call-btn">
                    <Button size="sm" className="gap-2 rounded-sm"><Phone className="h-4 w-4" /> Ligar</Button>
                  </a>
                )}
                {selectedLead.phone && (
                  <a href={`sms:${selectedLead.phone}`} data-testid="lead-sms-btn">
                    <Button size="sm" variant="outline" className="gap-2 rounded-sm"><Phone className="h-4 w-4" /> SMS</Button>
                  </a>
                )}
                {selectedLead.email && (
                  <a href={`mailto:${selectedLead.email}?subject=O%20seu%20pedido%20ConstruPilot`} data-testid="lead-email-btn">
                    <Button size="sm" variant="outline" className="gap-2 rounded-sm"><Mail className="h-4 w-4" /> E-mail</Button>
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

const Info = ({ icon: Icon, label, value }) => (
  <div className="rounded-sm border border-border p-2.5">
    <p className="overline text-muted-foreground flex items-center gap-1"><Icon className="h-3 w-3" /> {label}</p>
    <p className="mt-1 font-medium truncate">{value}</p>
  </div>
);
