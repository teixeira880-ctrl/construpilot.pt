import { BarChart3, ExternalLink } from "lucide-react";
import { useApi, dt } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const Num = ({ v }) => <td className="px-2 py-1.5 text-right num">{v ?? "—"}</td>;

export function ResultsPanel({ projectId }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/results`, [projectId]);
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const t = data.totals;
  return <div className="space-y-4" data-testid="growth-results">
    <p className="text-sm text-muted-foreground flex items-start gap-2"><BarChart3 className="h-4 w-4 mt-0.5 shrink-0" />Cada artigo publicado ligado aos seus cliques e impressões na Search Console (últimos 28 dias{data.gsc.period ? `, ${data.gsc.period.start} → ${data.gsc.period.end}` : ""}) e às inscrições que gerou (primeiro contacto: orgânico, anúncios, e-mail), bem como aos pedidos de estimativa.</p>
    {!data.gsc.connected && <p className="text-xs text-amber-700" data-testid="growth-results-no-gsc">Search Console não sincronizada: colunas de cliques/impressões vazias. Integrações → Ligar e depois Sincronizar.</p>}
    <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-center">
      {[["Cliques", t.clicks], ["Impressões", t.impressions], ["Inscr. organiques", t.signups_organic], ["Inscr. anúncios", t.signups_ads], ["Inscr. e-mail", t.signups_email], ["Pedidos de estimativa", t.leads]].map(([l, v]) => <div key={l} className="surface p-2"><p className="text-[10px] uppercase tracking-wider text-muted-foreground">{l}</p><p className="text-lg font-bold num">{v}</p></div>)}
    </div>
    {data.rows.length === 0 ? <Empty testid="growth-results-empty">Nenhum artigo publicado por agora.</Empty> :
      <div className="overflow-x-auto border rounded-md"><table className="w-full text-xs" data-testid="growth-results-table">
        <thead className="bg-muted/50 text-left"><tr><th className="px-2 py-1.5">Artigo</th><th className="px-2 py-1.5">Publicado</th><th className="px-2 py-1.5 text-right">Cliques</th><th className="px-2 py-1.5 text-right">Impr.</th><th className="px-2 py-1.5 text-right">CTR %</th><th className="px-2 py-1.5 text-right">Posição</th><th className="px-2 py-1.5 text-right">Inscr. org.</th><th className="px-2 py-1.5 text-right">Inscr. pub</th><th className="px-2 py-1.5 text-right">Inscr. e-mail</th><th className="px-2 py-1.5 text-right">Pedidos</th><th className="px-2 py-1.5 text-right">Anúncios</th></tr></thead>
        <tbody>{data.rows.map((r) => <tr key={r.content_id} className="border-t" data-testid={`growth-results-row-${r.content_id}`}>
          <td className="px-2 py-1.5 max-w-[360px]"><a className="underline inline-flex items-center gap-1" href={r.published_url} target="_blank" rel="noreferrer">{r.title}<ExternalLink className="h-3 w-3" /></a>{r.created_by === "autopilot" && <span className="ml-1 text-[10px] text-muted-foreground">auto</span>}</td>
          <td className="px-2 py-1.5 whitespace-nowrap">{dt(r.published_at)}</td>
          <Num v={r.gsc_available ? r.clicks : null} /><Num v={r.gsc_available ? r.impressions : null} /><Num v={r.gsc_available ? r.ctr : null} /><Num v={r.gsc_available ? r.position : null} />
          <Num v={r.signups_organic} /><Num v={r.signups_ads} /><Num v={r.signups_email} /><Num v={r.leads} /><Num v={r.ads_ready} />
        </tr>)}</tbody>
      </table></div>}
    {data.newsletters.length > 0 && <div className="text-xs"><p className="font-semibold mb-1">Newsletters enviadas</p><ul className="space-y-0.5">{data.newsletters.map((n) => <li key={n.newsletter_id}>{dt(n.sent_at)} · {n.subject} · {n.sent} envoi(s) · <span className="num">{n.signups}</span> inscrição(ões)</li>)}</ul></div>}
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">Limites de medição</summary><ul className="list-disc ml-5 mt-1">{data.limits.map((l) => <li key={l}>{l}</li>)}</ul><p className="mt-1">Inscrições atribuíveis acompanhadas: {data.attributed_users}.</p></details>
  </div>;
}
