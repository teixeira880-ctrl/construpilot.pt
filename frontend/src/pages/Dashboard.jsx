import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, FolderOpen, Trash2, FileSearch, Bell, HardHat, Sparkles, TrendingUp,
  FileText, Receipt, ArrowRight, Phone, Mail, MapPin, CalendarClock, Euro, User as UserIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, eur, num, IMAGES } from "@/lib/api";
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
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => {});
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

  const totalBudget = projects.reduce((s, p) => s + (p.budget || 0), 0);
  const totalSurface = projects.reduce((s, p) => s + (p.surface || 0), 0);

  return (
    <div className="grid gap-10">
      <OnboardingTour />
      <StarterChecklist
        isPro={isPro}
        projectDone={projects.length > 0}
        planDone={plans.length > 0}
        quoteDone={quotes.length > 0}
      />
      <div className="relative overflow-hidden rounded-md border border-border grain">
        <img src={IMAGES.dashboard_banner} alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-transparent" />
        <div className="relative p-8 lg:p-10 flex flex-col lg:flex-row gap-6 lg:items-end justify-between">
          <div>
            <p className="overline">{t("dash.over")}</p>
            <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
              {t("dash.hello")} {user?.name?.split(" ")[0]}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {tier === "free" ? (
                <>{t("dash.plan")} <b>{t("dash.free_word")}</b> · {t("dash.free_desc")}</>
              ) : (
                <>{t("dash.plan")} <b className="text-primary">{active?.plan?.name || tier}</b> {t("dash.active_desc")}</>
              )}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {tier === "free" && (
              <Button onClick={() => navigate("/tarifs")} data-testid="upgrade-cta" variant="outline" className="rounded-sm gap-2 border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground">
                <TrendingUp className="h-4 w-4" />
                {t("dash.upgrade")} {flags?.trial_enabled && flags?.trial_days ? `— ${flags.trial_days} ${t("dash.days_free")}` : ""}
              </Button>
            )}
            <PushToggle />
            <Button onClick={() => navigate("/smart-project")} data-testid="new-smart-project-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Sparkles className="h-4 w-4" /> Smart Project
            </Button>
            <Button variant="outline" onClick={() => navigate("/estimation")} data-testid="new-project-btn" className="rounded-sm gap-2">
              <Plus className="h-4 w-4" /> {t("dash.new_est")}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="dash-quick-actions">
        {(isPro ? [
          { to: "/devis-editeur", icon: FileText, title: "Novo orçamento", desc: "Crie um orçamento detalhado em poucos cliques", testid: "quick-new-quote" },
          { to: "/devis-editeur?type=invoice", icon: Receipt, title: "Nova factura", desc: "Emita uma factura conforme (SAF-T)", testid: "quick-new-invoice" },
          { to: "/factures", icon: TrendingUp, title: "Acompanhamento facturação", desc: "Recebimentos, dívidas e documentos", testid: "quick-invoicing" },
        ] : [
          { to: "/estimation", icon: FileText, title: "Estimar as minhas obras", desc: "Obtenha uma estimativa detalhada em 30 s", testid: "quick-estimate" },
          { to: "/prix", icon: TrendingUp, title: "Preços dos materiais", desc: "Consulte os preços de mercado actualizados", testid: "quick-prices" },
          { to: "/calculateurs", icon: Receipt, title: "Calculadoras", desc: "Superfícies, volumes e quantidades num instante", testid: "quick-calculators" },
        ]).map((a) => (
          <button
            key={a.to}
            onClick={() => navigate(a.to)}
            data-testid={a.testid}
            className="group surface p-5 rounded-md text-left flex items-center gap-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/50"
          >
            <span className="h-11 w-11 grid place-items-center rounded-sm bg-primary/10 text-primary shrink-0">
              <a.icon className="h-5 w-5" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-display font-semibold text-sm flex items-center gap-1">
                {a.title}
                <ArrowRight className="h-3.5 w-3.5 opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0" />
              </p>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{a.desc}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <Stat label={t("dash.stat_projects")} value={num(projects.length)} testId="stat-projects" />
        <Stat label={t("dash.stat_budget")} value={eur(totalBudget)} testId="stat-budget" accent />
        <Stat label={t("dash.stat_surface")} value={`${num(totalSurface, 1)} m²`} testId="stat-surface" />
        <Stat label={t("dash.stat_leads")} value={num(leads.length)} testId="stat-leads"
              badge={unreadLeads > 0 ? unreadLeads : null}
              onClick={() => {
                setTab("leads");
                markLeadsSeen();
                document.querySelector('[data-testid="dash-tab-leads"]')?.scrollIntoView({ behavior: "smooth", block: "center" });
              }} />
      </div>

      <RevenueChart />

      <a href="/appro" data-testid="appro-link" className="block surface p-6 border-2 border-primary/30 hover:border-primary transition-colors">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <i className="fa-solid fa-helmet-safety text-primary" />
              <span className="font-display font-bold text-lg">Analyse technique &amp; Approvisionnement IA</span>
              <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Novo</span>
            </div>
            <p className="text-sm text-muted-foreground mt-1">Importa as tuas plantas de armaduras → mapa de aço IA (ml, kg, tonelagem) → quantidades encomendáveis → notas de encomenda a fornecedores.</p>
          </div>
          <span className="text-primary font-bold shrink-0">Ouvrir →</span>
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
                  <Badge variant="outline" className="rounded-sm">{l.status || "nouveau"}</Badge>
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
              <HardHat className="h-5 w-5 text-primary" /> Demande ConstruPilot
            </DialogTitle>
          </DialogHeader>
          {selectedLead && (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-base">{selectedLead.name || t("dash.request")}</span>
                <Badge variant="outline" className="rounded-sm">{selectedLead.status || "nouveau"}</Badge>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Info icon={Euro} label="Budget" value={selectedLead.budget ? eur(selectedLead.budget) : "—"} />
                <Info icon={MapPin} label="Adresse" value={selectedLead.address || "—"} />
                <Info icon={CalendarClock} label="Disponibilidade" value={selectedLead.availability || selectedLead.delay_days ? (selectedLead.availability || `${selectedLead.delay_days} j`) : "—"} />
                <Info icon={UserIcon} label="Métier" value={selectedLead.trade || "—"} />
              </div>
              {selectedLead.description && (
                <div>
                  <p className="overline text-muted-foreground mb-1">Description</p>
                  <p className="whitespace-pre-wrap">{selectedLead.description}</p>
                </div>
              )}
              <div className="flex flex-wrap gap-2 pt-2 border-t">
                {selectedLead.phone && (
                  <a href={`tel:${selectedLead.phone}`} data-testid="lead-call-btn">
                    <Button size="sm" className="gap-2 rounded-sm"><Phone className="h-4 w-4" /> Appeler</Button>
                  </a>
                )}
                {selectedLead.phone && (
                  <a href={`sms:${selectedLead.phone}`} data-testid="lead-sms-btn">
                    <Button size="sm" variant="outline" className="gap-2 rounded-sm"><Phone className="h-4 w-4" /> SMS</Button>
                  </a>
                )}
                {selectedLead.email && (
                  <a href={`mailto:${selectedLead.email}?subject=Votre%20demande%20ConstruPilot`} data-testid="lead-email-btn">
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
