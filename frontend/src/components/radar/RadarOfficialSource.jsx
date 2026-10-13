import { useState } from "react";
import { ExternalLink, RefreshCw, Loader2, AlertTriangle } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";

const formatDate = (value) => value ? new Date(value).toLocaleDateString("fr-FR") : "—";
export const RadarOfficialSource = ({ sync, onRefresh }) => {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const departments = sync?.departments || [];
  const running = departments.some((d) => d.status === "running");
  const sources = departments.flatMap((d) => d.sources || []);
  const editions = [...new Set(sources.map((s) => s.millesime))];
  const coverage = sources.map((s) => s.coverage_end).filter(Boolean).sort()[0];
  const published = sources.map((s) => s.published_at).filter(Boolean).sort().at(-1);
  const collected = departments.map((d) => d.last_success_at).filter(Boolean).sort().at(-1);
  const refresh = async () => {
    setBusy(true); setError("");
    try { await api.post("/radar/sync", { departments: departments.map((d) => d.department) }); await onRefresh(); }
    catch { setError("Actualisation indisponible. Les dernières données valides sont conservées."); }
    finally { setBusy(false); }
  };
  if (!sync) return null;
  return <section className="mt-4 border-l-4 border-primary bg-primary/5 px-4 py-3 space-y-2" data-testid="radar-official-source">
    <div className="flex items-start justify-between flex-wrap gap-3">
      <div>
        <p className="font-semibold text-sm" data-testid="radar-data-mode">Permis officiels · SDES / SITADEL</p>
        <p className="text-xs text-muted-foreground mt-1" data-testid="radar-source-window">Autorisations du {formatDate(sync.window_start)} au {formatDate(sync.window_end)} · autorisés ou commencés, hors annulés et terminés</p>
      </div>
      <Button variant="outline" size="sm" disabled={busy || running || !departments.length} onClick={refresh} className="gap-1" data-testid="radar-official-refresh">
        {busy || running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />} Actualiser
      </Button>
    </div>
    {editions.length > 0 && <p className="text-xs" data-testid="radar-source-publication">Publication {editions.join(", ")} · diffusée le {formatDate(published)} · données disponibles jusqu'au {formatDate(coverage)} · collecte le {formatDate(collected)}</p>}
    {running && <p role="status" className="text-xs flex items-center gap-2" data-testid="radar-sync-running"><Loader2 className="h-3 w-3 animate-spin shrink-0" />Chargement depuis la source officielle en cours…</p>}
    <div className="flex flex-wrap gap-x-4 gap-y-1">
      {departments.map((d) => <p key={d.department} className={`text-xs ${d.status === "error" ? "text-red-700" : "text-muted-foreground"}`} data-testid={`radar-source-department-${d.department}`}>
        {d.department} : {d.status === "running" ? "chargement…" : d.status === "error" ? "source indisponible" : d.status === "not_loaded" ? "non chargé" : `${d.count} permis`}
      </p>)}
    </div>
    {departments.filter((d) => d.status === "error").map((d) => <p role="alert" key={d.department} className="text-xs text-red-700 flex gap-1" data-testid={`radar-sync-error-${d.department}`}><AlertTriangle className="h-3.5 w-3.5 shrink-0" />{d.department} : {d.error} {d.last_success_at ? "Dernière collecte conservée." : "Aucun permis disponible pour ce département."}</p>)}
    {error && <p role="alert" className="text-xs text-red-700" data-testid="radar-sync-request-error">{error}</p>}
    {sync.radius_scope && <p className="text-xs text-muted-foreground" data-testid="radar-radius-coverage">Le rayon s'applique aux départements déjà chargés, affichés ci-dessus.</p>}
    <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
      <p data-testid="radar-map-precision">Points de carte et distances approximatifs : centres des communes, pas positions exactes des terrains.</p>
      <a href={sync.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 underline text-primary" data-testid="radar-official-source-link">Source SDES <ExternalLink className="h-3 w-3" /></a>
    </div>
    <p className="text-xs text-muted-foreground" data-testid="radar-estimate-disclaimer">Les montants et scores sont des estimations ConstruPilot, pas des données officielles du SDES.</p>
  </section>;
};