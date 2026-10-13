import { useEffect, useState } from "react";
import {
  Camera, Wallet, CheckCircle2, PlayCircle, PhoneCall, Sparkles, Clock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { api, eur2 } from "@/lib/api";

const ICON = {
  project: Sparkles, photo: Camera, expense: Wallet,
  progress: CheckCircle2, lead: PhoneCall,
};

const COLOR = {
  project: "text-primary bg-primary/15 border-primary/40",
  photo_before: "text-slate-500 bg-slate-500/10 border-slate-500/30",
  photo_after: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
  photo_progress: "text-orange-500 bg-orange-500/10 border-orange-500/30",
  expense: "text-amber-500 bg-amber-500/10 border-amber-500/30",
  progress_doing: "text-orange-500 bg-orange-500/10 border-orange-500/30",
  progress_done: "text-emerald-500 bg-emerald-500/10 border-emerald-500/30",
  lead: "text-primary bg-primary/10 border-primary/30",
};

const style = (ev) => {
  if (ev.type === "photo") return COLOR[`photo_${ev.kind}`] || COLOR.photo_progress;
  if (ev.type === "progress") return COLOR[`progress_${ev.kind}`] || COLOR.progress_doing;
  return COLOR[ev.type] || COLOR.project;
};

const iconFor = (ev) => {
  if (ev.type === "progress" && ev.kind === "doing") return PlayCircle;
  return ICON[ev.type] || Clock;
};

const formatDate = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("pt-PT", {
      day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
};

const PhotoPreview = ({ projectId, photoId }) => {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let url;
    let alive = true;
    api.get(`/projects/${projectId}/photos/${photoId}/download`, { responseType: "blob" })
      .then((r) => {
        if (!alive) return;
        url = URL.createObjectURL(r.data);
        setSrc(url);
      })
      .catch(() => setSrc(null));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [projectId, photoId]);
  if (!src) return <div className="mt-3 h-32 w-32 bg-secondary/40 rounded-sm animate-pulse" />;
  return <img src={src} alt="" className="mt-3 h-32 w-32 object-cover rounded-sm border border-border" />;
};

export const Timeline = ({ projectId }) => {
  const [events, setEvents] = useState(null);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    api.get(`/projects/${projectId}/timeline`)
      .then(({ data }) => setEvents(data.events || []))
      .catch(() => setEvents([]));
  }, [projectId]);

  if (events === null) {
    return <div className="h-40 grid place-items-center"><div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>;
  }

  const filtered = filter === "all" ? events : events.filter((e) => e.type === filter);
  const counts = events.reduce((acc, e) => ({ ...acc, [e.type]: (acc[e.type] || 0) + 1 }), {});

  const filters = [
    { key: "all", label: "Todos", count: events.length },
    { key: "photo", label: "Fotografias", count: counts.photo || 0 },
    { key: "expense", label: "Despesas", count: counts.expense || 0 },
    { key: "progress", label: "Avanço", count: counts.progress || 0 },
    { key: "lead", label: "Pedidos", count: counts.lead || 0 },
  ];

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap gap-2" data-testid="timeline-filters">
        {filters.map((f) => (
          <button
            key={f.key} onClick={() => setFilter(f.key)}
            data-testid={`timeline-filter-${f.key}`}
            className={`px-3 py-2 text-xs rounded-sm border transition-colors ${
              filter === f.key ? "border-primary bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:border-primary/50"
            }`}
          >
            {f.label}
            {f.count > 0 && <span className="num ml-2 opacity-70">{f.count}</span>}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div className="surface p-10 text-center text-muted-foreground text-sm" data-testid="timeline-empty">
          Nada a apresentar para este filtro.
        </div>
      ) : (
        <ol className="relative border-l-2 border-border ml-4" data-testid="timeline-list">
          {filtered.map((ev, i) => {
            const Icon = iconFor(ev);
            return (
              <li key={i} className="pl-8 pb-8 relative" data-testid={`timeline-event-${ev.type}`}>
                <span className={`absolute -left-[17px] h-8 w-8 grid place-items-center rounded-full border ${style(ev)}`}>
                  <Icon className="h-4 w-4" />
                </span>
                <div className="surface p-4">
                  <div className="flex items-start justify-between gap-3 flex-wrap">
                    <div>
                      <p className="font-display font-semibold text-sm">{ev.title}</p>
                      <p className="num text-xs text-muted-foreground mt-1">{formatDate(ev.at)}</p>
                    </div>
                    {ev.amount != null && (
                      <Badge variant="outline" className="rounded-sm num text-primary border-primary/40">
                        {eur2(ev.amount)}
                      </Badge>
                    )}
                  </div>
                  {ev.detail && <p className="mt-3 text-sm text-muted-foreground">{ev.detail}</p>}
                  {ev.lot && ev.type !== "photo" && (
                    <Badge variant="outline" className="rounded-sm mt-3 text-[10px] uppercase tracking-wider">
                      {ev.lot}
                    </Badge>
                  )}
                  {ev.type === "photo" && ev.photo_id && (
                    <PhotoPreview projectId={projectId} photoId={ev.photo_id} />
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
};
