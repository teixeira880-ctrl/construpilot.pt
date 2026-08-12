import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, FolderOpen, Trash2, FileSearch, Bell, HardHat, Sparkles, TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, eur, num, IMAGES } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Stat } from "@/components/Bits";

const STATUS_ICON = { done: "✅", doing: "🔄", todo: "⏳" };

export default function Dashboard() {
  const { user } = useAuth();
  const [projects, setProjects] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [leads, setLeads] = useState([]);
  const navigate = useNavigate();

  const load = () => {
    api.get("/projects").then(({ data }) => setProjects(data)).catch(() => {});
    api.get("/quotes").then(({ data }) => setQuotes(data)).catch(() => {});
    api.get("/prices/alerts").then(({ data }) => setAlerts(data)).catch(() => {});
    api.get("/leads/mine").then(({ data }) => setLeads(data)).catch(() => {});
  };
  useEffect(load, []);

  const remove = async (id) => {
    await api.delete(`/projects/${id}`);
    toast.success("Projet supprimé");
    load();
  };

  const totalBudget = projects.reduce((s, p) => s + (p.budget || 0), 0);
  const totalSurface = projects.reduce((s, p) => s + (p.surface || 0), 0);

  return (
    <div className="grid gap-10">
      <div className="relative overflow-hidden rounded-md border border-border grain">
        <img src={IMAGES.dashboard_banner} alt="" className="absolute inset-0 h-full w-full object-cover opacity-20" />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-transparent" />
        <div className="relative p-8 lg:p-10 flex flex-col lg:flex-row gap-6 lg:items-end justify-between">
          <div>
            <p className="overline">Espace client</p>
            <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
              Bonjour {user?.name?.split(" ")[0]}
            </h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Plan {user?.plan} · vos projets, estimations, matériaux, devis et demandes ConstruPilot.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => navigate("/smart-project")} data-testid="new-smart-project-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Sparkles className="h-4 w-4" /> Smart Project
            </Button>
            <Button variant="outline" onClick={() => navigate("/estimation")} data-testid="new-project-btn" className="rounded-sm gap-2">
              <Plus className="h-4 w-4" /> Nouvelle estimation
            </Button>
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger">
        <Stat label="Mes projets" value={num(projects.length)} testId="stat-projects" />
        <Stat label="Budget cumulé" value={eur(totalBudget)} testId="stat-budget" accent />
        <Stat label="Surface totale" value={`${num(totalSurface, 1)} m²`} testId="stat-surface" />
        <Stat label="Demandes ConstruPilot" value={num(leads.length)} testId="stat-leads" />
      </div>

      <Tabs defaultValue="projects">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="projects" className="rounded-sm" data-testid="dash-tab-projects">Mes projets</TabsTrigger>
          <TabsTrigger value="quotes" className="rounded-sm" data-testid="dash-tab-quotes">Mes devis analysés</TabsTrigger>
          <TabsTrigger value="alerts" className="rounded-sm" data-testid="dash-tab-alerts">Mes alertes prix</TabsTrigger>
          <TabsTrigger value="leads" className="rounded-sm" data-testid="dash-tab-leads">Mes demandes ConstruPilot</TabsTrigger>
        </TabsList>

        <TabsContent value="projects" className="mt-6">
          {projects.length === 0 ? (
            <div className="surface p-12 text-center" data-testid="projects-empty">
              <FolderOpen className="h-8 w-8 mx-auto text-muted-foreground" />
              <p className="mt-4 text-sm text-muted-foreground">
                Aucun projet. Décrivez votre chantier avec Smart Project pour commencer.
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
                      <TrendingUp className="inline h-3 w-3 mr-1" />{done}/{total} lots terminés
                    </p>
                    <div className="mt-6 flex gap-2 pt-4 border-t border-border">
                      <Link to={`/projet/${p.project_id}`} className="flex-1">
                        <Button variant="outline" size="sm" className="w-full rounded-sm" data-testid={`open-project-${p.project_id}`}>
                          Ouvrir le projet
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
                Aucun devis analysé. <Link to="/devis" className="text-primary">Scanner un devis</Link>
              </p>
            </div>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="quotes-list">
              {quotes.map((q) => (
                <div key={q.quote_id} className="surface p-6">
                  <p className="overline text-muted-foreground">{q.company || "Entreprise"}</p>
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
                Aucune alerte prix. <Link to="/prix" className="text-primary">Créer une alerte</Link>
              </p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="alerts-list">
              {alerts.map((a) => (
                <div key={a.alert_id} className="surface p-5 flex flex-wrap items-center gap-4">
                  <div className="flex-1 min-w-[200px]">
                    <p className="font-medium">{a.product}</p>
                    <p className="num text-xs text-muted-foreground">Seuil : {eur(a.target_price)}</p>
                  </div>
                  <p className="num text-lg font-bold">{a.best_price ? eur(a.best_price) : "—"}</p>
                  <Badge variant="outline" className={`rounded-sm ${a.triggered ? "border-emerald-500 text-emerald-500" : ""}`}>
                    {a.triggered ? "Objectif atteint" : "En surveillance"}
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
              <p className="mt-4 text-sm text-muted-foreground">Aucune demande envoyée à ConstruPilot.</p>
            </div>
          ) : (
            <div className="grid gap-3" data-testid="leads-list">
              {leads.map((l) => (
                <div key={l.lead_id} className="surface p-5 flex flex-wrap items-center gap-4">
                  <div className="flex-1 min-w-[200px]">
                    <p className="font-medium">{l.project_snapshot?.name || l.description?.slice(0, 60) || "Demande"}</p>
                    <p className="text-xs text-muted-foreground">{l.address} · {l.phone}</p>
                  </div>
                  <p className="num font-bold">{eur(l.budget)}</p>
                  <Badge variant="outline" className="rounded-sm">{l.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
