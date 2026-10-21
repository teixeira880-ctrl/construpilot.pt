import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Save, Camera } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { DictateButton } from "@/components/voice/VoiceButtons";

const URG = { low: ["Faible", "bg-muted text-muted-foreground"], normal: ["Normal", "bg-amber-500/10 text-amber-700 border-amber-500/30"], high: ["Urgent", "bg-red-500/10 text-red-700 border-red-500/30"] };
const ST = { new: "bg-red-500/10 text-red-700 border-red-500/30", in_progress: "bg-amber-500/10 text-amber-700 border-amber-500/30", scheduled: "bg-blue-500/10 text-blue-700 border-blue-500/30", resolved: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30", closed: "bg-muted text-muted-foreground" };
const date = (iso) => (iso ? new Date(iso).toLocaleDateString("pt-PT") : "");

export function IssueHeader({ issue, labels }) {
  const [ul, ucls] = URG[issue.urgency] || URG.normal;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <p className="font-semibold text-sm">{issue.title}</p>
      <Badge variant="outline" className={`rounded-sm text-[10px] ${ST[issue.status] || ""}`} data-testid={`issue-status-${issue.issue_id}`}>{labels[issue.status] || issue.status}</Badge>
      <Badge variant="outline" className={`rounded-sm text-[10px] ${ucls}`}>{ul}</Badge>
      {issue.client_confirmed === true && <Badge variant="outline" className="rounded-sm text-[10px] bg-emerald-500/10 text-emerald-700">Confirmado resolvido</Badge>}
      {issue.client_confirmed === false && <Badge variant="outline" className="rounded-sm text-[10px] bg-red-500/10 text-red-700">Cliente: não resolvido</Badge>}
      <span className="text-xs text-muted-foreground ms-auto">{issue.reporter_name} · {date(issue.created_at)}{issue.location ? ` · ${issue.location}` : ""}</span>
    </div>
  );
}

export function IssuePhotos({ photos, fileUrl, testId }) {
  if (!photos?.length) return null;
  return <div className="flex flex-wrap gap-2 mt-2" data-testid={testId}>{photos.map((p) => <a key={p.path} href={fileUrl(p.path)} target="_blank" rel="noreferrer"><img src={fileUrl(p.path)} alt={p.name} className="h-16 w-16 object-cover rounded border" loading="lazy" /></a>)}</div>;
}

function IssueRow({ issue, labels, chantierId, api, onChanged }) {
  const [form, setForm] = useState({ status: issue.status, assignee: issue.assignee || "", target_date: issue.target_date || "", pro_response: issue.pro_response || "" });
  const [open, setOpen] = useState(issue.status === "new");
  const fileUrl = (p) => `${process.env.REACT_APP_BACKEND_URL}/api/chantiers/${chantierId}/messages/file?path=${encodeURIComponent(p)}`;
  const save = async () => {
    const body = {};
    Object.entries(form).forEach(([k, v]) => { if ((issue[k] || "") !== v) body[k] = v; });
    if (Object.keys(body).length === 0) return toast.message("Nenhuma alteração");
    try { await api.put(`/chantiers/${chantierId}/issues/${issue.issue_id}`, body); toast.success("Ocorrência atualizada — o convidado é informado por e-mail"); onChanged(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível atualizar"); }
  };
  return (
    <div className="px-4 py-3 grid gap-2" data-testid={`issue-${issue.issue_id}`}>
      <button type="button" className="text-left" onClick={() => setOpen((o) => !o)} data-testid={`issue-toggle-${issue.issue_id}`}><IssueHeader issue={issue} labels={labels} /></button>
      {open && <>
        {issue.description && <p className="text-sm whitespace-pre-wrap">{issue.description}</p>}
        <IssuePhotos photos={issue.photos} fileUrl={fileUrl} testId={`issue-photos-${issue.issue_id}`} />
        {issue.reserve_id && <p className="text-[11px] text-muted-foreground">Reserva associada: {issue.reserve_id} (levantada automaticamente quando o problema é resolvido ou encerrado).</p>}
        {issue.client_comment && <p className="text-xs italic">Comentário do convidado: {issue.client_comment}</p>}
        <div className="grid sm:grid-cols-3 gap-2 pt-1 border-t border-border">
          <select value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))} className="h-9 rounded-md border border-input bg-background px-2 text-sm" data-testid={`issue-status-select-${issue.issue_id}`}>
            {Object.entries(labels).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <Input value={form.assignee} onChange={(e) => setForm((f) => ({ ...f, assignee: e.target.value }))} placeholder="Responsável (empresa / subempreiteiro)" className="h-9" data-testid={`issue-assignee-${issue.issue_id}`} />
          <Input type="date" value={form.target_date} onChange={(e) => setForm((f) => ({ ...f, target_date: e.target.value }))} className="h-9" data-testid={`issue-date-${issue.issue_id}`} />
          <div className="sm:col-span-3 grid gap-1">
            <div className="flex items-center justify-between"><span className="text-xs text-muted-foreground">Resposta publicada para o convidado (redigida e validada por si — nunca texto IA em bruto)</span>
              <DictateButton testId={`issue-dictate-${issue.issue_id}`} onText={(t) => setForm((f) => ({ ...f, pro_response: [f.pro_response, t].filter(Boolean).join(" ") }))} /></div>
            <textarea value={form.pro_response} onChange={(e) => setForm((f) => ({ ...f, pro_response: e.target.value }))} rows={2} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none" data-testid={`issue-response-${issue.issue_id}`} />
          </div>
        </div>
        <div className="flex justify-end"><Button size="sm" className="h-8 gap-1" onClick={save} data-testid={`issue-save-${issue.issue_id}`}><Save className="h-3.5 w-3.5" /> Guardar e informar</Button></div>
      </>}
    </div>
  );
}

/** Panneau pro : problèmes signalés depuis le portail (→ réserves), suivi de statut, réponse validée. */
export function ChantierIssuesPanel({ chantierId, api }) {
  const [data, setData] = useState({ issues: [], labels: {} });
  const load = useCallback(() => api.get(`/chantiers/${chantierId}/issues`).then(({ data }) => setData(data)).catch(() => {}), [api, chantierId]);
  useEffect(() => { load(); }, [load]);
  const open = data.issues.filter((i) => !["resolved", "closed"].includes(i.status)).length;
  return (
    <section className="surface" data-testid="chantier-issues">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <AlertTriangle className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Problemas assinalados</p>
        <Badge variant="outline" className="rounded-sm" data-testid="issues-open-count">{open} em aberto</Badge>
        <span className="ms-auto text-[11px] text-muted-foreground inline-flex items-center gap-1"><Camera className="h-3 w-3" /> Cada ocorrência cria uma reserva no acompanhamento da obra</span>
      </div>
      {data.issues.length === 0 ? <p className="px-4 py-4 text-sm text-muted-foreground">Nenhum problema assinalado pelos seus convidados.</p>
        : <div className="divide-y divide-border">{data.issues.map((i) => <IssueRow key={i.issue_id} issue={i} labels={data.labels} chantierId={chantierId} api={api} onChanged={load} />)}</div>}
    </section>
  );
}
