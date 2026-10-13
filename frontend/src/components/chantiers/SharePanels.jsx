import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Users, Send, Copy, Ban, RefreshCw, Plus, Flag, Trash2, Pencil, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { PreviewAsGuestButton } from "@/components/portal/PreviewAsGuest";

const PERM_LABELS = { progress: "Avancement", photos: "Photos", quotes: "Orçamento", invoices: "Factures", sign: "Signer", chat: "Messages", report_issue: "Assinalar um problema", post_reports: "Entregar relatórios" };
const STATUS = { invited: ["Convite enviado", "bg-amber-500/10 text-amber-700 border-amber-500/30"], active: ["Actif", "bg-emerald-500/10 text-emerald-700 border-emerald-500/30"], revoked: ["Revogado", "bg-muted text-muted-foreground"] };
const MS_STATUS = { planned: "Previsto", in_progress: "En cours", done: "Terminado", late: "En retard" };
const copy = (text, msg) => navigator.clipboard?.writeText(text).then(() => toast.success(msg)).catch(() => toast.error("Cópia impossível"));

function InviteDialog({ open, onOpenChange, chantierId, onDone }) {
  const [form, setForm] = useState({ role: "client", email: "", name: "", lot: "" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { if (open) { setForm({ role: "client", email: "", name: "", lot: "" }); setResult(null); } }, [open]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post(`/chantiers/${chantierId}/participants`, form); setResult(data); onDone(); }
    catch (err) { toast.error(err?.response?.data?.detail || "Convite impossível"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="invite-dialog">
        <DialogHeader><DialogTitle>Convidar para esta obra</DialogTitle><DialogDescription>O convidado recebe uma ligação válida 14 dias + o identificador da obra para depois iniciar sessão por código e-mail.</DialogDescription></DialogHeader>
        {result ? (
          <div className="grid gap-3 text-sm" data-testid="invite-result">
            <div>Convite registado para <strong>{result.email}</strong>. E-mail : <Badge variant="outline" className="rounded-sm" data-testid="invite-email-status">{result.invite_email_status === "sent" ? "enviado" : "falha no envio — transmita a ligação abaixo"}</Badge></div>
            <div className="flex gap-2"><Input readOnly value={result.invite_link} data-testid="invite-link" className="text-xs" /><Button type="button" variant="outline" onClick={() => copy(result.invite_link, "Link copiado")} data-testid="invite-copy-link"><Copy className="h-4 w-4" /></Button></div>
            <Button type="button" onClick={() => onOpenChange(false)} data-testid="invite-close">Fechar</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-3">
            <div className="grid grid-cols-2 gap-2">
              {[["client", "Cliente (dono de obra)"], ["subcontractor", "Sous-traitant"]].map(([v, l]) => (
                <button key={v} type="button" onClick={() => setForm((f) => ({ ...f, role: v }))} data-testid={`invite-role-${v}`} aria-pressed={form.role === v}
                  className={`rounded-md border p-3 text-sm text-left ${form.role === v ? "border-primary bg-primary/5 font-semibold" : "hover:bg-muted"}`}>{l}</button>))}
            </div>
            <div><Label htmlFor="inv-email">E-mail *</Label><Input id="inv-email" type="email" required value={form.email} onChange={set("email")} data-testid="invite-email" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label htmlFor="inv-name">Nom</Label><Input id="inv-name" value={form.name} onChange={set("name")} data-testid="invite-name" /></div>
              {form.role === "subcontractor" && <div><Label htmlFor="inv-lot">Capítulo atribuído</Label><Input id="inv-lot" value={form.lot} onChange={set("lot")} placeholder="Plomberie" data-testid="invite-lot" /></div>}
            </div>
            <p className="text-xs text-muted-foreground">Permissões por omissão: {Object.entries(form.role === "client" ? { progress: 1, photos: 1, quotes: 1, invoices: 1, sign: 1, chat: 1, report_issue: 1 } : { progress: 1, photos: 1, chat: 1, report_issue: 1, post_reports: 1 }).map(([k]) => PERM_LABELS[k]).join(", ")} — modifiables ensuite.</p>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancelar</Button><Button type="submit" disabled={busy} data-testid="invite-submit"><Send className="h-4 w-4 me-1" /> {busy ? "Envoi…" : "Enviar o convite"}</Button></div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ShareParticipantsPanel({ chantierId }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const load = useCallback(() => api.get(`/chantiers/${chantierId}/participants`).then(({ data }) => setData(data)).catch(() => setData({ participants: [] })), [chantierId]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn, ok) => { try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(e?.response?.data?.detail || "Ação impossível"); } };
  const togglePerm = (p, key) => act(() => api.put(`/chantiers/${chantierId}/participants/${p.participant_id}/permissions`, { permissions: { [key]: !p.permissions?.[key] } }), "Permissões atualizadas");
  const parts = data?.participants || [];
  return (
    <section className="surface" data-testid="chantier-share">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <Users className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Partilha e convidados</p>
        <Badge variant="outline" className="rounded-sm">{parts.filter((p) => p.status !== "revoked").length}</Badge>
        {data?.ref && <button type="button" onClick={() => copy(data.ref, "Identificador copiado")} className="text-xs font-mono rounded-sm border px-2 py-0.5 hover:bg-muted" title="Identificador da obra (copiar)" data-testid="chantier-ref">{data.ref}</button>}
        <div className="ms-auto flex gap-1"><PreviewAsGuestButton chantierId={chantierId} participants={parts} /><Button size="sm" className="h-8 gap-1" onClick={() => setOpen(true)} data-testid="chantier-invite-btn"><Plus className="h-3.5 w-3.5" /> Inviter</Button></div>
      </div>
      {parts.length === 0 ? <p className="px-4 py-4 text-sm text-muted-foreground">Ninguém foi convidado. Convide o seu cliente ou um subempreiteiro: verá apenas esta obra, com as permissões que assinalar.</p> : (
        <div className="divide-y divide-border">
          {parts.map((p) => (
            <div key={p.participant_id} className="px-4 py-3 grid gap-2" data-testid={`participant-${p.participant_id}`}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold">{p.name || p.email}</span>
                <Badge variant="outline" className="rounded-sm text-[10px]">{p.role === "client" ? "Cliente" : `Sous-traitant${p.lot ? ` · ${p.lot}` : ""}`}</Badge>
                <Badge variant="outline" className={`rounded-sm text-[10px] ${STATUS[p.status]?.[1] || ""}`} data-testid={`participant-status-${p.participant_id}`}>{STATUS[p.status]?.[0] || p.status}</Badge>
                {p.invite_email_status === "failed" && <span className="text-[11px] text-red-600">e-mail não enviado — utilize «Reenviar» ou copie a ligação</span>}
                <span className="text-xs text-muted-foreground">{p.email}{p.last_seen_at ? `· visto em${p.last_seen_at.slice(0, 10)}` : ""}</span>
                <div className="ms-auto flex gap-1">
                  {p.status !== "revoked" && <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs" onClick={() => act(async () => { const { data: r } = await api.post(`/chantiers/${chantierId}/participants/${p.participant_id}/resend`); if (r.invite_email_status !== "sent") copy(r.invite_link, "E-mail não enviado: ligação copiada"); }, "Convite reenviado")} data-testid={`participant-resend-${p.participant_id}`}><RefreshCw className="h-3 w-3" /> Renvoyer</Button>}
                  {p.status !== "revoked" && <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs text-red-600" onClick={() => act(() => api.post(`/chantiers/${chantierId}/participants/${p.participant_id}/revoke`), "Acesso revogado")} data-testid={`participant-revoke-${p.participant_id}`}><Ban className="h-3 w-3" /> Revogar</Button>}
                </div>
              </div>
              {p.status !== "revoked" && <div className="flex flex-wrap gap-1">
                {Object.entries(PERM_LABELS).map(([k, l]) => (
                  <button key={k} type="button" onClick={() => togglePerm(p, k)} aria-pressed={!!p.permissions?.[k]} data-testid={`perm-${p.participant_id}-${k}`}
                    className={`text-[11px] rounded-sm border px-2 py-0.5 transition-colors ${p.permissions?.[k] ? "bg-primary/10 border-primary/40 text-primary" : "text-muted-foreground hover:bg-muted"}`}>{l}</button>))}
              </div>}
            </div>
          ))}
        </div>
      )}
      <InviteDialog open={open} onOpenChange={setOpen} chantierId={chantierId} onDone={load} />
    </section>
  );
}

export function MilestonesPanel({ chantierId, milestones, onChanged }) {
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(null);
  const start = (m) => { setEditing(m?.milestone_id || "new"); setForm(m ? { ...m } : { title: "", planned_start: "", planned_end: "", status: "planned", progress_pct: 0, lot: "", visible: true }); };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.type === "number" ? Number(e.target.value) : e.target.value }));
  const save = async (e) => {
    e.preventDefault();
    const body = { title: form.title, planned_start: form.planned_start || null, planned_end: form.planned_end || null, status: form.status, progress_pct: form.progress_pct, lot: form.lot || "", visible: form.visible !== false };
    try {
      if (editing === "new") await api.post(`/chantiers/${chantierId}/milestones`, body); else await api.put(`/chantiers/${chantierId}/milestones/${editing}`, body);
      toast.success("Marco guardado"); setEditing(null); onChanged();
    } catch (err) { toast.error(err?.response?.data?.detail || "Não foi possível guardar"); }
  };
  const remove = async (m) => { try { await api.delete(`/chantiers/${chantierId}/milestones/${m.milestone_id}`); toast.success("Marco eliminado"); onChanged(); } catch { toast.error("Não foi possível eliminar"); } };
  return (
    <section className="surface" data-testid="chantier-milestones">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Flag className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Jalons d'avancement</p><Badge variant="outline" className="rounded-sm">{milestones.length}</Badge>
        <div className="ms-auto"><Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => start(null)} data-testid="milestone-add"><Plus className="h-3.5 w-3.5" /> Jalon</Button></div>
      </div>
      {milestones.length === 0 && editing !== "new" && <p className="px-4 py-4 text-sm text-muted-foreground">Adicione as grandes etapas (demolição, estrutura, acabamentos…): os seus convidados vê-las-ão na página Avanço.</p>}
      <div className="divide-y divide-border">
        {milestones.map((m) => editing === m.milestone_id ? null : (
          <div key={m.milestone_id} className="px-4 py-2.5 flex items-center gap-3" data-testid={`milestone-${m.milestone_id}`}>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">{m.title}{m.lot ? <span className="text-muted-foreground"> · {m.lot}</span> : null}</p>
              <p className="text-[11px] text-muted-foreground">{[m.planned_start, m.planned_end].filter(Boolean).join(" → ") || "Datas a definir"} · {MS_STATUS[m.status]} · {m.progress_pct}%{m.visible === false ? "· oculto" : ""}</p>
            </div>
            <div className="h-1.5 w-24 rounded-full bg-border overflow-hidden"><div className="h-full bg-primary" style={{ width: `${m.progress_pct}%` }} /></div>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => start(m)} data-testid={`milestone-edit-${m.milestone_id}`}><Pencil className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => remove(m)} data-testid={`milestone-delete-${m.milestone_id}`}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
      </div>
      {editing && form && (
        <form onSubmit={save} className="px-4 py-3 grid gap-2 border-t border-border bg-muted/30" data-testid="milestone-form">
          <div className="grid sm:grid-cols-3 gap-2">
            <Input required value={form.title} onChange={set("title")} placeholder="Título do marco *" className="sm:col-span-2" data-testid="milestone-title" />
            <Input value={form.lot} onChange={set("lot")} placeholder="Lot (optionnel)" data-testid="milestone-lot" />
            <Input type="date" value={form.planned_start || ""} onChange={set("planned_start")} data-testid="milestone-start" />
            <Input type="date" value={form.planned_end || ""} onChange={set("planned_end")} data-testid="milestone-end" />
            <select value={form.status} onChange={set("status")} className="h-10 rounded-md border border-input bg-background px-3 text-sm" data-testid="milestone-status">{Object.entries(MS_STATUS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <label className="text-sm flex items-center gap-2 sm:col-span-2">Avancement <input type="range" min={0} max={100} value={form.progress_pct} onChange={set("progress_pct")} className="flex-1" data-testid="milestone-progress" /><span className="num w-10 text-right">{form.progress_pct}%</span></label>
            <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={form.visible !== false} onChange={(e) => setForm((f) => ({ ...f, visible: e.target.checked }))} data-testid="milestone-visible" /> Visível para os convidados</label>
          </div>
          <div className="flex justify-end gap-2"><Button type="button" size="sm" variant="outline" onClick={() => setEditing(null)}>Cancelar</Button><Button type="submit" size="sm" data-testid="milestone-save">Guardar</Button></div>
        </form>
      )}
    </section>
  );
}

export function PublishToggle({ chantierId, report, onChanged }) {
  const toggle = async () => {
    try { await api.put(`/chantiers/${chantierId}/reports/${report.report_id}/publish`, { published: !report.published }); toast.success(report.published ? "Relatório oculto aos convidados" : "Relatório publicado para os convidados"); onChanged(); }
    catch { toast.error("Ação impossível"); }
  };
  return (
    <Button size="sm" variant={report.published ? "default" : "outline"} className="h-7 gap-1 text-xs" onClick={toggle} data-testid={`report-publish-${report.report_id}`} title={report.published ? "Visível para os convidados — clique para ocultar" : "Interno — clique para publicar para os convidados"}>
      {report.published ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />} {report.published ? "Publicado" : "Interne"}
    </Button>
  );
}
