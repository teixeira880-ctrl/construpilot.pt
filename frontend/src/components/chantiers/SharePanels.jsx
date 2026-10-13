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

const PERM_LABELS = { progress: "Avancement", photos: "Photos", quotes: "Devis", invoices: "Factures", sign: "Signer", chat: "Messages", report_issue: "Signaler un problème", post_reports: "Déposer des comptes rendus" };
const STATUS = { invited: ["Invitation envoyée", "bg-amber-500/10 text-amber-700 border-amber-500/30"], active: ["Actif", "bg-emerald-500/10 text-emerald-700 border-emerald-500/30"], revoked: ["Révoqué", "bg-muted text-muted-foreground"] };
const MS_STATUS = { planned: "Prévu", in_progress: "En cours", done: "Terminé", late: "En retard" };
const copy = (text, msg) => navigator.clipboard?.writeText(text).then(() => toast.success(msg)).catch(() => toast.error("Copie impossible"));

function InviteDialog({ open, onOpenChange, chantierId, onDone }) {
  const [form, setForm] = useState({ role: "client", email: "", name: "", lot: "" });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  useEffect(() => { if (open) { setForm({ role: "client", email: "", name: "", lot: "" }); setResult(null); } }, [open]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post(`/chantiers/${chantierId}/participants`, form); setResult(data); onDone(); }
    catch (err) { toast.error(err?.response?.data?.detail || "Invitation impossible"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="invite-dialog">
        <DialogHeader><DialogTitle>Inviter sur ce chantier</DialogTitle><DialogDescription>L'invité reçoit un lien valable 14 jours + l'identifiant du chantier pour se connecter ensuite par code e-mail.</DialogDescription></DialogHeader>
        {result ? (
          <div className="grid gap-3 text-sm" data-testid="invite-result">
            <div>Invitation enregistrée pour <strong>{result.email}</strong>. E-mail : <Badge variant="outline" className="rounded-sm" data-testid="invite-email-status">{result.invite_email_status === "sent" ? "envoyé" : "échec d'envoi — transmettez le lien ci-dessous"}</Badge></div>
            <div className="flex gap-2"><Input readOnly value={result.invite_link} data-testid="invite-link" className="text-xs" /><Button type="button" variant="outline" onClick={() => copy(result.invite_link, "Lien copié")} data-testid="invite-copy-link"><Copy className="h-4 w-4" /></Button></div>
            <Button type="button" onClick={() => onOpenChange(false)} data-testid="invite-close">Fermer</Button>
          </div>
        ) : (
          <form onSubmit={submit} className="grid gap-3">
            <div className="grid grid-cols-2 gap-2">
              {[["client", "Client (maître d'ouvrage)"], ["subcontractor", "Sous-traitant"]].map(([v, l]) => (
                <button key={v} type="button" onClick={() => setForm((f) => ({ ...f, role: v }))} data-testid={`invite-role-${v}`} aria-pressed={form.role === v}
                  className={`rounded-md border p-3 text-sm text-left ${form.role === v ? "border-primary bg-primary/5 font-semibold" : "hover:bg-muted"}`}>{l}</button>))}
            </div>
            <div><Label htmlFor="inv-email">E-mail *</Label><Input id="inv-email" type="email" required value={form.email} onChange={set("email")} data-testid="invite-email" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label htmlFor="inv-name">Nom</Label><Input id="inv-name" value={form.name} onChange={set("name")} data-testid="invite-name" /></div>
              {form.role === "subcontractor" && <div><Label htmlFor="inv-lot">Lot confié</Label><Input id="inv-lot" value={form.lot} onChange={set("lot")} placeholder="Plomberie" data-testid="invite-lot" /></div>}
            </div>
            <p className="text-xs text-muted-foreground">Droits par défaut : {Object.entries(form.role === "client" ? { progress: 1, photos: 1, quotes: 1, invoices: 1, sign: 1, chat: 1, report_issue: 1 } : { progress: 1, photos: 1, chat: 1, report_issue: 1, post_reports: 1 }).map(([k]) => PERM_LABELS[k]).join(", ")} — modifiables ensuite.</p>
            <div className="flex justify-end gap-2"><Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button><Button type="submit" disabled={busy} data-testid="invite-submit"><Send className="h-4 w-4 me-1" /> {busy ? "Envoi…" : "Envoyer l'invitation"}</Button></div>
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
  const act = async (fn, ok) => { try { await fn(); toast.success(ok); load(); } catch (e) { toast.error(e?.response?.data?.detail || "Action impossible"); } };
  const togglePerm = (p, key) => act(() => api.put(`/chantiers/${chantierId}/participants/${p.participant_id}/permissions`, { permissions: { [key]: !p.permissions?.[key] } }), "Droits mis à jour");
  const parts = data?.participants || [];
  return (
    <section className="surface" data-testid="chantier-share">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <Users className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Partage & invités</p>
        <Badge variant="outline" className="rounded-sm">{parts.filter((p) => p.status !== "revoked").length}</Badge>
        {data?.ref && <button type="button" onClick={() => copy(data.ref, "Identifiant copié")} className="text-xs font-mono rounded-sm border px-2 py-0.5 hover:bg-muted" title="Identifiant chantier (copier)" data-testid="chantier-ref">{data.ref}</button>}
        <div className="ms-auto flex gap-1"><PreviewAsGuestButton chantierId={chantierId} participants={parts} /><Button size="sm" className="h-8 gap-1" onClick={() => setOpen(true)} data-testid="chantier-invite-btn"><Plus className="h-3.5 w-3.5" /> Inviter</Button></div>
      </div>
      {parts.length === 0 ? <p className="px-4 py-4 text-sm text-muted-foreground">Personne n'est invité. Invitez votre client ou un sous-traitant : il verra uniquement ce chantier, avec les droits que vous cochez.</p> : (
        <div className="divide-y divide-border">
          {parts.map((p) => (
            <div key={p.participant_id} className="px-4 py-3 grid gap-2" data-testid={`participant-${p.participant_id}`}>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold">{p.name || p.email}</span>
                <Badge variant="outline" className="rounded-sm text-[10px]">{p.role === "client" ? "Client" : `Sous-traitant${p.lot ? ` · ${p.lot}` : ""}`}</Badge>
                <Badge variant="outline" className={`rounded-sm text-[10px] ${STATUS[p.status]?.[1] || ""}`} data-testid={`participant-status-${p.participant_id}`}>{STATUS[p.status]?.[0] || p.status}</Badge>
                {p.invite_email_status === "failed" && <span className="text-[11px] text-red-600">e-mail non envoyé — utilisez « Renvoyer » ou copiez le lien</span>}
                <span className="text-xs text-muted-foreground">{p.email}{p.last_seen_at ? ` · vu le ${p.last_seen_at.slice(0, 10)}` : ""}</span>
                <div className="ms-auto flex gap-1">
                  {p.status !== "revoked" && <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs" onClick={() => act(async () => { const { data: r } = await api.post(`/chantiers/${chantierId}/participants/${p.participant_id}/resend`); if (r.invite_email_status !== "sent") copy(r.invite_link, "E-mail non envoyé : lien copié"); }, "Invitation renvoyée")} data-testid={`participant-resend-${p.participant_id}`}><RefreshCw className="h-3 w-3" /> Renvoyer</Button>}
                  {p.status !== "revoked" && <Button size="sm" variant="ghost" className="h-7 gap-1 text-xs text-red-600" onClick={() => act(() => api.post(`/chantiers/${chantierId}/participants/${p.participant_id}/revoke`), "Accès révoqué")} data-testid={`participant-revoke-${p.participant_id}`}><Ban className="h-3 w-3" /> Révoquer</Button>}
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
      toast.success("Jalon enregistré"); setEditing(null); onChanged();
    } catch (err) { toast.error(err?.response?.data?.detail || "Enregistrement impossible"); }
  };
  const remove = async (m) => { try { await api.delete(`/chantiers/${chantierId}/milestones/${m.milestone_id}`); toast.success("Jalon supprimé"); onChanged(); } catch { toast.error("Suppression impossible"); } };
  return (
    <section className="surface" data-testid="chantier-milestones">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Flag className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Jalons d'avancement</p><Badge variant="outline" className="rounded-sm">{milestones.length}</Badge>
        <div className="ms-auto"><Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => start(null)} data-testid="milestone-add"><Plus className="h-3.5 w-3.5" /> Jalon</Button></div>
      </div>
      {milestones.length === 0 && editing !== "new" && <p className="px-4 py-4 text-sm text-muted-foreground">Ajoutez les grandes étapes (démolition, gros œuvre, finitions…) : vos invités les verront sur leur page Avancement.</p>}
      <div className="divide-y divide-border">
        {milestones.map((m) => editing === m.milestone_id ? null : (
          <div key={m.milestone_id} className="px-4 py-2.5 flex items-center gap-3" data-testid={`milestone-${m.milestone_id}`}>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium truncate">{m.title}{m.lot ? <span className="text-muted-foreground"> · {m.lot}</span> : null}</p>
              <p className="text-[11px] text-muted-foreground">{[m.planned_start, m.planned_end].filter(Boolean).join(" → ") || "Dates à définir"} · {MS_STATUS[m.status]} · {m.progress_pct}%{m.visible === false ? " · masqué" : ""}</p>
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
            <Input required value={form.title} onChange={set("title")} placeholder="Titre du jalon *" className="sm:col-span-2" data-testid="milestone-title" />
            <Input value={form.lot} onChange={set("lot")} placeholder="Lot (optionnel)" data-testid="milestone-lot" />
            <Input type="date" value={form.planned_start || ""} onChange={set("planned_start")} data-testid="milestone-start" />
            <Input type="date" value={form.planned_end || ""} onChange={set("planned_end")} data-testid="milestone-end" />
            <select value={form.status} onChange={set("status")} className="h-10 rounded-md border border-input bg-background px-3 text-sm" data-testid="milestone-status">{Object.entries(MS_STATUS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            <label className="text-sm flex items-center gap-2 sm:col-span-2">Avancement <input type="range" min={0} max={100} value={form.progress_pct} onChange={set("progress_pct")} className="flex-1" data-testid="milestone-progress" /><span className="num w-10 text-right">{form.progress_pct}%</span></label>
            <label className="text-sm flex items-center gap-2"><input type="checkbox" checked={form.visible !== false} onChange={(e) => setForm((f) => ({ ...f, visible: e.target.checked }))} data-testid="milestone-visible" /> Visible des invités</label>
          </div>
          <div className="flex justify-end gap-2"><Button type="button" size="sm" variant="outline" onClick={() => setEditing(null)}>Annuler</Button><Button type="submit" size="sm" data-testid="milestone-save">Enregistrer</Button></div>
        </form>
      )}
    </section>
  );
}

export function PublishToggle({ chantierId, report, onChanged }) {
  const toggle = async () => {
    try { await api.put(`/chantiers/${chantierId}/reports/${report.report_id}/publish`, { published: !report.published }); toast.success(report.published ? "Compte rendu masqué aux invités" : "Compte rendu publié aux invités"); onChanged(); }
    catch { toast.error("Action impossible"); }
  };
  return (
    <Button size="sm" variant={report.published ? "default" : "outline"} className="h-7 gap-1 text-xs" onClick={toggle} data-testid={`report-publish-${report.report_id}`} title={report.published ? "Visible des invités — cliquer pour masquer" : "Interne — cliquer pour publier aux invités"}>
      {report.published ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />} {report.published ? "Publié" : "Interne"}
    </Button>
  );
}
