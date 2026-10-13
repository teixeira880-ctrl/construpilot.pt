import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { TrendingUp } from "lucide-react";
import { useApi } from "./lib";
import { ErrorBox } from "./Bits";
import { Dashboard } from "./Dashboard";
import { BrandPanel } from "./BrandPanel";
import { AuditPanel } from "./AuditPanel";
import { VisibilityPanel } from "./VisibilityPanel";
import { QuestionsPanel, CompetitorsPanel } from "./QuestionsPanel";
import { ActionsPanel } from "./ActionsPanel";
import { AutopilotPanel } from "./AutopilotPanel";
import { MarketingPanel } from "./MarketingPanel";
import { ResultsPanel } from "./ResultsPanel";
import { ContentsPanel } from "./ContentsPanel";
import { IntegrationsPanel } from "./IntegrationsPanel";
import { LinksPanel, BudgetPanel, AssistantPanel } from "./MorePanels";

const TABS = [["dashboard", "Painel"], ["audit", "Audit"], ["visibility", "Visibilidade IA"], ["questions", "Questions"], ["competitors", "Concurrents"], ["actions", "Plan d'action"],
  ["autopilot", "Auto-pilote"], ["contents", "Contenus"], ["marketing", "Publicidade e e-mails"], ["results", "Resultados"], ["brand", "Ficha de marca"], ["links", "Liens"], ["integrations", "Integrações"], ["budget", "Budget"], ["assistant", "Assistant"]];

export default function GrowthPage() {
  const { data, error, reload } = useApi("/growth/me");
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("tab") || "dashboard";
  const projectKey = sp.get("project") || "fr";
  const contentId = sp.get("content");
  const [notice, setNotice] = useState(sp.get("google"));
  useEffect(() => { if (notice) setTimeout(() => setNotice(null), 8000); }, [notice]);
  const go = (t, p = projectKey, extra = {}) => setSp({ tab: t, project: p, ...extra });
  if (error) return <div className="p-6"><ErrorBox error={error} onRetry={reload} /></div>;
  if (!data) return <div className="p-6 text-sm text-muted-foreground">A carregar…</div>;
  const project = data.projects.find((p) => p.key === projectKey) || data.projects[0];
  const canEdit = ["admin", "editor"].includes(data.role);
  const isAdmin = data.role === "admin";
  const pid = project?.project_id;
  const needsProject = tab !== "dashboard";
  return <div className="p-4 sm:p-6 max-w-7xl space-y-4" data-testid="growth-page">
    <header className="flex flex-wrap items-center gap-3">
      <div><h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp className="h-6 w-6 text-primary" /> ConstruPilot Growth</h1>
        <p className="text-sm text-muted-foreground">Referenciação, visibilidade nas respostas das IA, conteúdos e publicação — construpilot.pt · função: <strong>{data.role}</strong></p></div>
      <div className="ml-auto flex gap-1" role="tablist" aria-label="Projet" data-testid="growth-project-switch">
        {[...data.projects.map((p) => [p.key, p.name]), ...(tab === "dashboard" ? [["all", "Vue globale"]] : [])].map(([k, l]) => <button key={k} role="tab" aria-selected={projectKey === k} onClick={() => go(tab, k)} className={`px-3 h-9 rounded-md text-sm border ${projectKey === k ? "bg-primary text-primary-foreground border-primary" : "hover:border-primary"}`} data-testid={`growth-project-${k}`}>{l}</button>)}
      </div>
    </header>
    {notice && <p className={`text-xs rounded-md p-2 ${notice === "connected" ? "bg-emerald-500/10 text-emerald-800" : "bg-red-500/10 text-red-700"}`} data-testid="growth-google-notice">{notice === "connected" ? "Google Search Console ligada." : "Ligação Google recusada ou falhada."}</p>}
    <nav className="flex flex-wrap gap-1 border-b pb-2" data-testid="growth-tabs">
      {TABS.map(([k, l]) => <button key={k} onClick={() => go(k, projectKey === "all" && k !== "dashboard" ? "fr" : projectKey)} className={`px-3 h-9 rounded-md text-sm ${tab === k ? "bg-muted font-semibold" : "hover:bg-muted/60"}`} data-testid={`growth-tab-${k}`}>{l}</button>)}
    </nav>
    {tab === "dashboard" && <Dashboard projectKey={projectKey} onGo={(t, p) => go(t, p)} />}
    {needsProject && !pid && <ErrorBox error="Projet introuvable" />}
    {pid && tab === "brand" && <BrandPanel projectId={pid} canEdit={canEdit} />}
    {pid && tab === "audit" && <AuditPanel projectId={pid} canEdit={canEdit} />}
    {pid && tab === "visibility" && <VisibilityPanel projectId={pid} canEdit={canEdit} providers={data.providers} />}
    {pid && tab === "questions" && <QuestionsPanel projectId={pid} canEdit={canEdit} />}
    {pid && tab === "competitors" && <CompetitorsPanel projectId={pid} canEdit={canEdit} />}
    {pid && tab === "actions" && <ActionsPanel projectId={pid} canEdit={canEdit} onContent={(id) => go("contents", projectKey, { content: id })} />}
    {pid && tab === "autopilot" && <AutopilotPanel projectId={pid} canEdit={canEdit} onGo={(t) => go(t, projectKey)} />}
    {pid && tab === "results" && <ResultsPanel projectId={pid} />}
    {pid && tab === "marketing" && <MarketingPanel projectId={pid} canEdit={canEdit} isAdmin={isAdmin} />}
    {pid && tab === "contents" && <ContentsPanel projectId={pid} canEdit={canEdit} isAdmin={isAdmin} openId={contentId} onOpen={(id) => go("contents", projectKey, id ? { content: id } : {})} />}
    {pid && tab === "links" && <LinksPanel projectId={pid} canEdit={canEdit} />}
    {pid && tab === "integrations" && <IntegrationsPanel projectId={pid} isAdmin={isAdmin} project={project} onSaved={reload} />}
    {pid && tab === "budget" && <BudgetPanel projectId={pid} canEdit={isAdmin} project={project} onSaved={reload} />}
    {pid && tab === "assistant" && <AssistantPanel projectId={pid} canEdit={canEdit} isAdmin={isAdmin} />}
  </div>;
}
