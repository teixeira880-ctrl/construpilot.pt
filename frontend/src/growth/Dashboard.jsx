import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Metric, Empty, ErrorBox, Stale } from "./Bits";
import { useApi, dt, usd, STATUS_FR } from "./lib";

export function Dashboard({ projectKey, onGo }) {
  const { data, error, loading, reload } = useApi("/growth/overview");
  if (loading) return <p className="text-sm text-muted-foreground">A carregar…</p>;
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  const rows = data.projects.filter((p) => projectKey === "all" || p.project.key === projectKey);
  const missing = Object.entries(data.providers).filter(([, v]) => !v.configured).map(([k]) => k);
  return <div className="space-y-5" data-testid="growth-dashboard">
    {missing.length > 0 && <p className="text-xs rounded-md bg-amber-500/10 text-amber-800 p-2" data-testid="growth-missing-connections">Ligações em falta: {missing.join(", ")} — ver o separador Integrações.</p>}
    {rows.map(({ project, last_audit, last_campaign, open_issues, open_actions, contents, spent_month_usd, spent_day_usd, gsc, connections }) => <section key={project.project_id} className="surface p-4 space-y-3" data-testid={`growth-project-card-${project.key}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display font-bold text-lg">{project.name}</h2>
        <Badge variant="outline" className="rounded-sm">{project.language} · {project.market}</Badge>
        <span className="ml-auto text-xs text-muted-foreground num">Gasto: {usd(spent_day_usd)} hoje · {usd(spent_month_usd)} este mês</span>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <button className="surface p-3 text-left hover:border-primary" onClick={() => onGo("audit", project.key)} data-testid={`growth-card-audit-${project.key}`}>
          <p className="overline">Auditoria do site</p>
          {last_audit ? <><p className="num text-xl font-bold">{last_audit.issues_count} <span className="text-sm font-normal">problemas</span></p><p className="text-[11px] text-muted-foreground">{last_audit.pages_crawled} páginas · {dt(last_audit.finished_at)}<Stale at={last_audit.finished_at} /></p>
            <p className="text-[11px] text-muted-foreground">{open_issues} em aberto · H {last_audit.summary?.by_severity?.haute ?? 0} / M {last_audit.summary?.by_severity?.moyenne ?? 0} / B {last_audit.summary?.by_severity?.basse ?? 0}</p></>
            : <p className="text-sm text-muted-foreground">Nenhuma auditoria — lançar a primeira</p>}
        </button>
        <button className="surface p-3 text-left hover:border-primary" onClick={() => onGo("visibility", project.key)} data-testid={`growth-card-visibility-${project.key}`}>
          <p className="overline">Visibilidade IA (testes API)</p>
          {last_campaign ? <><p className="num text-xl font-bold">{last_campaign.mention_rate.display}</p><p className="text-[11px] text-muted-foreground">taxa de menção (sem marca) · {last_campaign.valid} respostas válidas · {last_campaign.excluded_count} exclues</p><p className="text-[11px] text-muted-foreground">{last_campaign.campaign.name} · {STATUS_FR[last_campaign.campaign.status]}</p></>
            : <p className="text-sm text-muted-foreground">Nenhuma campanha concluída</p>}
        </button>
        <button className="surface p-3 text-left hover:border-primary" onClick={() => onGo("actions", project.key)} data-testid={`growth-card-actions-${project.key}`}>
          <p className="overline">Plan d'action</p><p className="num text-xl font-bold">{open_actions} <span className="text-sm font-normal">ações em aberto</span></p>
          <p className="text-[11px] text-muted-foreground">Conteúdos: {contents.draft} rascunhos · {contents.review} a rever · {contents.approved + contents.scheduled} prontos · {contents.published} publicados</p>
        </button>
        <button className="surface p-3 text-left hover:border-primary" onClick={() => onGo("integrations", project.key)} data-testid={`growth-card-gsc-${project.key}`}>
          <p className="overline">Google Search Console</p>
          {connections.search_console && gsc ? <><p className="num text-xl font-bold">{gsc.totals.clicks} <span className="text-sm font-normal">cliques · {gsc.totals.impressions} impr.</span></p><p className="text-[11px] text-muted-foreground">{gsc.start} → {gsc.end}<Stale at={gsc.synced_at} /></p></>
            : <p className="text-sm text-muted-foreground">Não ligada — dados indisponíveis</p>}
        </button>
      </div>
      {last_campaign && <div className="flex flex-wrap gap-3">
        <Metric label="Taxa de citação" m={last_campaign.citation_rate} /><Metric label="Quota de menções" m={last_campaign.share_of_mentions} /><Metric label="Cobertura" m={last_campaign.coverage} />
      </div>}
    </section>)}
    {rows.length === 0 && <Empty>Nenhum projeto.</Empty>}
    <p className="text-[11px] text-muted-foreground">Os testes IA são feitos via API: não reproduzem necessariamente as respostas das interfaces para o grande público. Indexação Google: desconhecida enquanto a Search Console não estiver ligada. <Link className="underline" to="/blog">Ver o blogue</Link>.</p>
  </div>;
}
