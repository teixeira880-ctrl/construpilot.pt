import { useState } from "react";
import { ExternalLink, RefreshCw, Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const formatDate = (value) => value ? new Date(value).toLocaleDateString("pt-PT") : "—";

const ZONE_LABEL = { lisboa: "Lisboa" };
const zoneLabel = (code) => ZONE_LABEL[code] || code;

export const RadarOfficialSource = ({ sync, onRefresh }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const zones = sync?.departments || [];
  const running = zones.some((d) => d.status === "running");
  const sources = zones.flatMap((d) => d.sources || []);
  const editions = [...new Set(sources.map((s) => s.millesime).filter(Boolean))];
  const coverage = sources.map((s) => s.coverage_end).filter(Boolean).sort()[0];
  const published = sources.map((s) => s.published_at).filter(Boolean).sort().at(-1);
  const collected = zones.map((d) => d.last_success_at).filter(Boolean).sort().at(-1);
  const refresh = async () => {
    setBusy(true); setError("");
    try { await api.post("/radar/sync", { departments: zones.map((d) => d.department) }); await onRefresh(); }
    catch { setError("Atualização indisponível. Os últimos dados válidos são conservados."); }
    finally { setBusy(false); }
  };
  if (!sync) return null;
  return <section className="mt-4 border-l-4 border-primary bg-primary/5 px-4 py-3 space-y-2" data-testid="radar-official-source">
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <p className="font-semibold text-sm" data-testid="radar-data-mode">Licenças oficiais · Câmara Municipal de Lisboa</p>
        <p className="text-xs text-muted-foreground mt-1" data-testid="radar-source-window">Alvarás de {formatDate(sync.window_start)} a {formatDate(sync.window_end)} · emitidos ao abrigo do RJUE</p>
      </div>
      <Button variant="outline" size="sm" disabled={busy || running || !zones.length} onClick={refresh} className="gap-1" data-testid="radar-official-refresh">
        {busy || running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Atualizar
      </Button>
    </div>
    {editions.length > 0 && <p className="text-xs" data-testid="radar-source-publication">Publicação {editions.join(", ")} · divulgada em {formatDate(published)} · dados disponíveis até {formatDate(coverage)} · recolha em {formatDate(collected)}</p>}
    {running && <p role="status" className="text-xs flex items-center gap-2" data-testid="radar-sync-running"><Loader2 className="h-3 w-3 animate-spin shrink-0" />A carregar os dados da fonte oficial…</p>}
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {zones.map((d) => <p key={d.department} className={`text-xs ${d.status === "error" ? "text-red-700" : "text-muted-foreground"}`} data-testid={`radar-source-department-${d.department}`}>
        {zoneLabel(d.department)} : {d.status === "running" ? "a carregar…" : d.status === "error" ? "fonte indisponível" : d.status === "not_loaded" ? "não carregado" : `${d.count} licenças`}
      </p>)}
    </div>
    {zones.filter((d) => d.status === "error").map((d) => <p role="alert" key={d.department} className="text-xs text-red-700 flex gap-1" data-testid={`radar-sync-error-${d.department}`}><AlertTriangle className="h-3.5 w-3.5 shrink-0" />{zoneLabel(d.department)} : {d.error} {d.last_success_at ? "Última recolha conservada." : "Nenhuma licença disponível para esta zona."}</p>)}
    {error && <p role="alert" className="text-xs text-red-700" data-testid="radar-sync-request-error">{error}</p>}
    {sync.radius_scope && <p className="text-xs text-muted-foreground" data-testid="radar-radius-coverage">O raio aplica-se às zonas já carregadas, apresentadas acima.</p>}
    <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
      <p data-testid="radar-map-precision">Pontos no mapa e distâncias aproximados: centros das freguesias, não as localizações exatas dos terrenos.</p>
      <a href={sync.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline text-primary" data-testid="radar-official-source-link">Fonte CML <ExternalLink className="h-3 w-3" /></a>
    </div>
    <p className="text-xs text-muted-foreground" data-testid="radar-radar-coverage">
      Cobertura: concelho de Lisboa (único município com licenças em dados abertos). Outros municípios: em breve.
    </p>
    <p className="text-xs text-muted-foreground" data-testid="radar-estimate-disclaimer">Os montantes e as pontuações são estimativas ConstruPilot, não dados oficiais.</p>
  </section>;
};
