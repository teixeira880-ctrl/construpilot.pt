import { useEffect, useState } from "react";
import { Eye, EyeOff, CheckCircle2, Clock, AlertTriangle, Circle, MessageSquare } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const MS = { planned: [Circle, "text-slate-400", "Previsto"], in_progress: [Clock, "text-amber-600", "En cours"], done: [CheckCircle2, "text-emerald-600", "Terminado"], late: [AlertTriangle, "text-red-600", "En retard"] };
const FILE = `${process.env.REACT_APP_BACKEND_URL}/api/site/file?path=`;

/** « Voir comme le client » : rendu fidèle de la page Avancement + Messages + Problèmes de l'invité, avec le rappel de ce qui reste interne. */
export function PreviewAsGuestButton({ chantierId, participants = [] }) {
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState("role:client");
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!open) return;
    const [kind, v] = who.split(":");
    setData(null);
    api.get(`/chantiers/${chantierId}/preview-as`, { params: kind === "pid" ? { participant_id: v } : { role: v } }).then(({ data }) => setData(data)).catch(() => setData({ error: true }));
  }, [open, who, chantierId]);
  const active = participants.filter((p) => p.status !== "revoked");
  const accent = data?.company?.accent || "#1f6f4a";
  return (
    <>
      <Button size="sm" variant="outline" className="h-8 gap-1" onClick={() => setOpen(true)} data-testid="preview-as-guest-btn"><Eye className="h-3.5 w-3.5" /> Ver como o cliente</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="preview-as-guest-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Eye className="h-4 w-4" /> O que o convidado vê</DialogTitle>
            <DialogDescription>Pré-visualização exata do espaço do convidado com as suas permissões. O que não está publicado não aparece.</DialogDescription>
          </DialogHeader>
          <select value={who} onChange={(e) => setWho(e.target.value)} className="h-9 rounded-md border border-input bg-background px-2 text-sm w-full" data-testid="preview-as-select">
            <option value="role:client">Cliente (permissões por omissão)</option>
            <option value="role:subcontractor">Subempreiteiro (permissões por omissão)</option>
            {active.map((p) => <option key={p.participant_id} value={`pid:${p.participant_id}`}>{`${p.name || p.email} — ${p.role === "client" ? "client" : "sous-traitant"}(permissões reais)`}</option>)}
          </select>
          {!data ? <p className="text-sm text-muted-foreground">A carregar…</p> : data.error ? <p className="text-sm text-red-600">Pré-visualização indisponível</p> : (
            <div className="grid gap-3 rounded-xl bg-slate-50 p-4 text-slate-900" data-testid="preview-as-content">
              <div className="rounded-xl border bg-white p-4">
                <p className="text-[11px] uppercase tracking-wide text-slate-500">{data.company?.name} · {data.chantier?.ref}</p>
                <p className="text-lg font-semibold" data-testid="preview-chantier-name">{data.chantier?.name}</p>
                {data.progress_pct != null && <div className="mt-2"><div className="flex justify-between text-xs"><span>Avancement global</span><span className="font-semibold">{data.progress_pct}%</span></div><div className="mt-1 h-2 rounded-full bg-slate-200 overflow-hidden"><div className="h-full" style={{ width: `${data.progress_pct}%`, background: accent }} /></div></div>}
                <div className="flex flex-wrap gap-1 mt-3">{Object.entries(data.participant?.permissions || {}).map(([k, v]) => <Badge key={k} variant="outline" className={`rounded-sm text-[10px] ${v ? "" : "opacity-40 line-through"}`}>{k}</Badge>)}</div>
              </div>
              {data.participant?.permissions?.progress && <div className="rounded-xl border bg-white p-4">
                <p className="font-semibold text-sm">Etapas ({data.milestones.length})</p>
                {data.milestones.length === 0 ? <p className="text-xs text-slate-500 mt-1">Nenhuma etapa visível.</p> : <ul className="mt-2 grid gap-1">{data.milestones.map((m) => { const [I, cls, l] = MS[m.status] || MS.planned; return <li key={m.milestone_id} className="text-sm flex items-center gap-2"><I className={`h-4 w-4 ${cls}`} /> {m.title} <span className="text-xs text-slate-500">· {l} · {m.progress_pct}%</span></li>; })}</ul>}
                <p className="font-semibold text-sm mt-4">Diário de obra ({data.reports.length} publicado{data.reports.length > 1 ? "s" : ""})</p>
                {data.reports.length === 0 ? <p className="text-xs text-slate-500 mt-1">Nenhum relatório publicado.</p> : <ul className="mt-2 grid gap-1">{data.reports.map((r) => <li key={r.report_id} className="text-sm">{r.title || "Ata"} <span className="text-xs text-slate-500">· {(r.created_at || "").slice(0, 10)} · {(r.photos || []).length} photo(s)</span></li>)}</ul>}
                {data.participant.permissions.photos && data.photos.length > 0 && <div className="mt-3 grid grid-cols-6 gap-1">{data.photos.slice(0, 12).map((p, i) => <img key={i} src={FILE + encodeURIComponent(p.path)} alt="" className="h-14 w-full object-cover rounded border" loading="lazy" />)}</div>}
              </div>}
              <div className="rounded-xl border bg-white p-4 grid gap-1">
                <p className="font-semibold text-sm flex items-center gap-1"><MessageSquare className="h-4 w-4" /> Messages {data.participant?.permissions?.chat ? `(${data.messages.length}, canal ${data.participant.role === "client" ? "client" : "sous-traitants"})` : "— não autorizados"}</p>
                {data.participant?.permissions?.chat && data.messages.slice(-3).map((m) => <p key={m.message_id} className="text-xs text-slate-600 truncate">{m.author_name} : {m.body || `${m.attachments?.length}anexo(s)`}</p>)}
                <p className="font-semibold text-sm mt-2 flex items-center gap-1"><AlertTriangle className="h-4 w-4" /> Problemas {data.participant?.permissions?.report_issue ? `(${data.issues.length})` : "— não autorizados"}</p>
                {data.participant?.permissions?.report_issue && data.issues.slice(0, 5).map((i) => <p key={i.issue_id} className="text-xs text-slate-600 truncate">{i.title} · {data.issue_labels[i.status]}</p>)}
              </div>
              <div className="rounded-xl border border-dashed bg-white p-3 text-xs text-slate-600 flex items-start gap-2" data-testid="preview-hidden">
                <EyeOff className="h-4 w-4 shrink-0 text-slate-500" />
                <span><b>Fica interno (invisível para o convidado)</b> : {data.hidden.reports_internal} relatório(s) não publicado(s), {data.hidden.milestones_hidden} marco(s) oculto(s), todos os orçamentos/faturas (Sprint 3), diagnósticos IA e notas do processo.{data.simulated ? "Pré-visualização com as permissões por omissão da função: as permissões reais de um convidado podem diferir." : ""}</span>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
