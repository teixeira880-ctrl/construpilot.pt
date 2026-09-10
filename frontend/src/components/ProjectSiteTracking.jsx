import { useEffect, useState } from "react";
import { Camera, ClipboardList, AlertTriangle, Activity } from "lucide-react";
import { api } from "@/lib/api";

export const ProjectSiteTracking = ({ projectId, acceptedQuote }) => {
  const [data, setData] = useState(null);
  const [zoom, setZoom] = useState(null);
  useEffect(() => {
    if (!acceptedQuote) return;
    api.get(`/projects/${projectId}/site`).then(({ data: d }) => setData(d)).catch(() => setData(null));
  }, [projectId, acceptedQuote?.doc_id]);
  if (!acceptedQuote || !data) return null;
  const openReserves = data.reserves.filter((r) => !r.resolved && r.status !== "levee").length;
  const empty = !data.reports.length && !data.reserves.length && !data.checklist.total;
  return (
    <div className="grid gap-4 rounded-sm border border-border/60 p-4" data-testid="project-site-tracking">
      <div className="flex flex-wrap items-center gap-3">
        <Activity className="h-4 w-4 text-primary" />
        <h3 className="font-semibold">Suivi du chantier par l'artisan</h3>
        {data.progress != null && <span className="text-xs text-muted-foreground">Avancement {data.progress} %</span>}
        <span className="ml-auto text-xs text-muted-foreground">{data.reports.length} compte{data.reports.length > 1 ? "s" : ""}-rendu{data.reports.length > 1 ? "s" : ""} · {data.checklist.done}/{data.checklist.total} tâches · {openReserves} réserve{openReserves > 1 ? "s" : ""} ouverte{openReserves > 1 ? "s" : ""}</span>
      </div>
      {data.progress != null && (
        <div className="h-2.5 w-full rounded-full bg-secondary overflow-hidden" data-testid="project-site-progress">
          <div className="h-full bg-primary transition-[width] duration-700" style={{ width: `${Math.min(100, data.progress)}%` }} />
        </div>
      )}
      {empty && <p className="text-sm text-muted-foreground" data-testid="project-site-empty">Le chantier n'a pas encore démarré : les comptes-rendus et photos de l'artisan apparaîtront ici.</p>}
      {data.reports.slice(0, 5).map((r) => (
        <div key={r.report_id} className="rounded-sm bg-secondary/20 p-3 grid gap-2" data-testid={`project-site-report-${r.report_id}`}>
          <div className="flex items-center gap-2 text-sm"><ClipboardList className="h-4 w-4 text-primary" /><span className="font-medium">{r.title || "Compte-rendu de visite"}</span>
            <span className="text-xs text-muted-foreground ml-auto">{new Date(r.created_at).toLocaleDateString("fr-FR")}</span></div>
          {r.notes && <p className="text-sm text-muted-foreground whitespace-pre-line">{r.notes}</p>}
          {r.lots?.length > 0 && <div className="flex flex-wrap gap-1.5">{r.lots.map((l, i) => <span key={i} className="text-[11px] rounded-full bg-primary/10 text-primary px-2 py-0.5">{l.name} {l.progress != null ? `${l.progress} %` : ""}</span>)}</div>}
          {r.photos?.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {r.photos.map((ph, i) => <button key={i} onClick={() => setZoom(ph)} className="h-20 w-28 overflow-hidden rounded-sm border border-border/60" data-testid={`project-site-photo-${r.report_id}-${i}`}><img src={ph} alt="" className="h-full w-full object-cover" loading="lazy" /></button>)}
            </div>
          )}
        </div>
      ))}
      {data.reserves.length > 0 && (
        <div className="grid gap-1.5" data-testid="project-site-reserves">
          {data.reserves.slice(0, 8).map((r) => (
            <div key={r.reserve_id} className="flex items-start gap-2 text-sm"><AlertTriangle className={`h-4 w-4 mt-0.5 ${r.resolved || r.status === "levee" ? "text-emerald-600" : "text-amber-500"}`} />
              <span>{r.lot ? <b>{r.lot} · </b> : null}{r.description}</span>
              <span className="ml-auto text-xs text-muted-foreground whitespace-nowrap">{r.resolved || r.status === "levee" ? "levée" : "ouverte"}</span></div>
          ))}
        </div>
      )}
      {zoom && (
        <button className="fixed inset-0 z-50 bg-black/80 grid place-items-center p-6" onClick={() => setZoom(null)} data-testid="project-site-photo-zoom">
          <img src={zoom} alt="" className="max-h-full max-w-full rounded-sm" />
          <Camera className="absolute top-4 right-4 h-5 w-5 text-white/70" />
        </button>
      )}
    </div>
  );
};
