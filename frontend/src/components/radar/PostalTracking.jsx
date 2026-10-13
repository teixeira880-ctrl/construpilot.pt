import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Loader2, Mail, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { usePostalCopy } from "./postalCopy";

const STAGES = ["accepted", "printed", "posted", "delivered"];
const MODE_LABELS = { normal: "Lettre simple", suivi: "Lettre suivie", lrar: "Registado (LRAR)" };
const STATUS_LABELS = { submitting: "Verificação necessária — pedido em curso", unknown: "Resultado por verificar — não reenviar", rejected: "Recusado · não enviado" };

export const PostalTimeline = ({ send }) => {
  const ui = usePostalCopy();
  const returned = send.stage === "returned";
  const reached = returned ? STAGES.indexOf("posted") : Math.max(0, STAGES.indexOf(send.stage || "accepted"));
  if (send.status !== "submitted") return <span className="text-xs text-muted-foreground" data-testid={`postal-status-${send.postal_id}`}>{STATUS_LABELS[send.status] || send.status}</span>;
  return <div className="space-y-1" data-testid={`postal-timeline-${send.postal_id}`}>
    <ol className="flex items-center gap-1 text-[10px] leading-none">
      {STAGES.map((stage, i) => {
        const done = i <= reached && !(returned && stage === "delivered");
        return <li key={stage} className="flex items-center gap-1" data-testid={`postal-stage-${send.postal_id}-${stage}`} data-done={done}>
          <span className={`h-4 w-4 rounded-full grid place-items-center border ${done ? "bg-primary border-primary text-primary-foreground" : "border-border text-transparent"}`}><Check size={10} /></span>
          <span className={done ? "font-semibold" : "text-muted-foreground"}>{ui(`st${stage[0].toUpperCase()}${stage.slice(1)}`)}</span>
          {i < STAGES.length - 1 && <span className={`h-px w-3 sm:w-5 ${i < reached ? "bg-primary" : "bg-border"}`} />}
        </li>;
      })}
    </ol>
    {returned && <p role="alert" className="flex items-center gap-1 text-xs text-red-700 font-semibold" data-testid={`postal-returned-${send.postal_id}`}><AlertTriangle size={13} /> {ui("returnedAlert")}</p>}
    {send.provider_status && <p className="text-[11px] text-muted-foreground truncate" data-testid={`postal-status-${send.postal_id}`}>{send.provider_status}{send.tracking_ref ? ` · ${send.tracking_ref}` : ""}</p>}
  </div>;
};

export const PostalSendRow = ({ send }) => (
  <li className="border-b border-border/40 py-2 space-y-1" data-testid={`postal-history-${send.postal_id}`}>
    <div className="flex justify-between gap-2 text-xs">
      <span className="truncate font-medium">{send.recipient?.nom} · {send.recipient?.ville} · {MODE_LABELS[send.mode] || send.mode}</span>
      <span className="text-muted-foreground shrink-0">{send.envoi_id ? `n° ${send.envoi_id}` : ""}</span>
    </div>
    <PostalTimeline send={send} />
  </li>
);

export const PostalTrackingPanel = () => {
  const ui = usePostalCopy();
  const [sends, setSends] = useState(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/radar/postal/sends"); setSends(data.sends || []); } catch { setSends([]); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const refresh = async () => {
    setBusy(true);
    try { const { data } = await api.post("/radar/postal/tracking/refresh", {}, { timeout: 60000 }); if (data.errors) toast.warning("Acompanhamento parcialmente atualizado"); await load(); }
    catch { toast.error("Suivi indisponible"); } finally { setBusy(false); }
  };
  return <div className="mt-4 border-t border-border pt-3" data-testid="postal-tracking-panel">
    <div className="flex items-center justify-between mb-2">
      <p className="text-sm font-bold flex items-center gap-1"><Mail className="h-4 w-4" /> {ui("trackingTitle")} {sends && `(${sends.length})`}</p>
      <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={refresh} disabled={busy || !sends?.length} data-testid="postal-tracking-refresh">
        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />} {ui("trackingRefresh")}
      </Button>
    </div>
    {!sends && <p className="text-xs text-muted-foreground flex gap-2"><Loader2 className="h-3 w-3 animate-spin" /> …</p>}
    {sends?.length === 0 && <p className="text-xs text-muted-foreground" data-testid="postal-tracking-empty">{ui("trackingEmpty")}</p>}
    {sends?.length > 0 && <ul className="max-h-72 overflow-y-auto">{sends.map((s) => <PostalSendRow key={s.postal_id} send={s} />)}</ul>}
  </div>;
};
