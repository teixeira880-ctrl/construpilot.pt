import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { AlertTriangle, Camera, CheckCircle2, XCircle, X } from "lucide-react";
import { MessageList, MessageComposer } from "@/components/portal/Messaging";
import { IssueHeader, IssuePhotos } from "@/components/portal/Issues";
import { DictateButton } from "@/components/voice/VoiceButtons";

const BASE = process.env.REACT_APP_BACKEND_URL;
const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600";
const dictate = (fd) => axios.post(`${BASE}/api/speech/portal/transcribe`, fd, { withCredentials: true });

/** Onglet Messages du portail invité : un seul canal (client ↔ entreprise ou sous-traitants ↔ entreprise). */
export function PortalMessages({ portalApi, chantierRef, participantId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => portalApi.get(`/${chantierRef}/messages`).then(({ data }) => { setData(data); setError(""); }).catch((e) => setError(e?.response?.data?.detail || "Messages indisponibles")), [portalApi, chantierRef]);
  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id); }, [load]);
  const fileUrl = (p) => `${BASE}/api/portal/${chantierRef}/messages/file?path=${encodeURIComponent(p)}`;
  if (error) return <p className="text-sm text-red-600" data-testid="portal-messages-error">{error}</p>;
  if (!data) return <p className="text-sm text-slate-500">Chargement…</p>;
  return (
    <section className="rounded-2xl border bg-white" data-testid="portal-messages">
      <div className="px-4 py-3 border-b"><h2 className="font-semibold">Messages avec {data.company || "l'entreprise"}</h2><p className="text-xs text-slate-500">Vous pouvez joindre des photos ou des PDF. L'entreprise est prévenue par e-mail.</p></div>
      <MessageList messages={data.messages} mine={(m) => m.author_id === participantId} fileUrl={fileUrl} emptyText="Aucun message pour l'instant. Posez votre question ci-dessous." testId="portal-message-list" />
      <MessageComposer testId="portal-composer" dictate={dictate} placeholder="Écrire à l'entreprise…" send={async (fd) => { await portalApi.post(`/${chantierRef}/messages`, fd); await load(); }} />
    </section>
  );
}

function ReportForm({ portalApi, chantierRef, onDone, onCancel }) {
  const [form, setForm] = useState({ title: "", description: "", location: "", urgency: "normal" });
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    const fd = new FormData();
    Object.entries(form).forEach(([k, v]) => fd.append(k, v));
    files.forEach((f) => fd.append("files", f));
    try { await portalApi.post(`/${chantierRef}/issues`, fd); toast.success("Problème signalé : l'entreprise est prévenue"); onDone(); }
    catch (err) { toast.error(err?.response?.data?.detail || "Envoi impossible"); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="grid gap-3 border-t px-4 py-4 bg-slate-50" data-testid="portal-issue-form">
      <label className="text-sm grid gap-1">Que se passe-t-il ? *<div className="flex gap-2"><input className={field} value={form.title} onChange={set("title")} required minLength={3} placeholder="Ex. Fuite sous l'évier de la cuisine" data-testid="portal-issue-title" /><DictateButton request={dictate} testId="portal-issue-title-dictate" onText={(t) => setForm((f) => ({ ...f, title: [f.title, t].filter(Boolean).join(" ").slice(0, 160) }))} /></div></label>
      <label className="text-sm grid gap-1">Détails<div className="flex gap-2 items-start"><textarea className={field} rows={3} value={form.description} onChange={set("description")} placeholder="Depuis quand, où exactement, ce que vous avez constaté…" data-testid="portal-issue-desc" /><DictateButton request={dictate} testId="portal-issue-desc-dictate" onText={(t) => setForm((f) => ({ ...f, description: [f.description, t].filter(Boolean).join(" ") }))} /></div></label>
      <div className="grid sm:grid-cols-2 gap-3">
        <label className="text-sm grid gap-1">Pièce / lot<input className={field} value={form.location} onChange={set("location")} placeholder="Cuisine, salle de bain, façade…" data-testid="portal-issue-location" /></label>
        <label className="text-sm grid gap-1">Urgence<select className={field} value={form.urgency} onChange={set("urgency")} data-testid="portal-issue-urgency"><option value="low">Faible — peut attendre</option><option value="normal">Normale</option><option value="high">Urgent — dégât en cours</option></select></label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="inline-flex items-center gap-1 text-sm rounded-lg border px-3 py-1.5 cursor-pointer bg-white" data-testid="portal-issue-attach"><Camera className="h-4 w-4" /> Photos {files.length > 0 && `(${files.length}/5)`}
          <input type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={(e) => { setFiles((l) => [...l, ...Array.from(e.target.files)].slice(0, 5)); e.target.value = ""; }} data-testid="portal-issue-file-input" /></label>
        {files.map((f, i) => <span key={i} className="inline-flex items-center gap-1 text-xs rounded border px-2 py-0.5 bg-white">{f.name}<button type="button" onClick={() => setFiles((l) => l.filter((_, j) => j !== i))} aria-label="Retirer"><X className="h-3 w-3" /></button></span>)}
      </div>
      <div className="flex justify-end gap-2"><button type="button" onClick={onCancel} className="text-sm rounded-lg border px-3 py-2 bg-white" data-testid="portal-issue-cancel">Annuler</button><button type="submit" disabled={busy} className="text-sm rounded-lg bg-emerald-700 text-white px-4 py-2 font-medium disabled:opacity-60" data-testid="portal-issue-submit">{busy ? "Envoi…" : "Envoyer le signalement"}</button></div>
    </form>
  );
}

/** Onglet Problèmes du portail : signaler, suivre le statut, confirmer la résolution. */
export function PortalIssues({ portalApi, chantierRef, canReport }) {
  const [data, setData] = useState({ issues: [], labels: {} });
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);
  const load = useCallback(() => portalApi.get(`/${chantierRef}/issues`).then(({ data }) => { setData(data); setError(""); }).catch((e) => setError(e?.response?.data?.detail || "Signalements indisponibles")), [portalApi, chantierRef]);
  useEffect(() => { load(); }, [load]);
  const fileUrl = (p) => `${BASE}/api/portal/${chantierRef}/messages/file?path=${encodeURIComponent(p)}`;
  const confirm = async (issue, resolved) => {
    try { await portalApi.post(`/${chantierRef}/issues/${issue.issue_id}/confirm`, { resolved, comment: "" }); toast.success(resolved ? "Merci, le problème est clôturé" : "L'entreprise est informée que ce n'est pas réglé"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Action impossible"); }
  };
  if (error) return <p className="text-sm text-red-600" data-testid="portal-issues-error">{error}</p>;
  return (
    <section className="rounded-2xl border bg-white" data-testid="portal-issues">
      <div className="px-4 py-3 border-b flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-600" /><h2 className="font-semibold">Problèmes signalés</h2>
        {canReport && !adding && <button type="button" onClick={() => setAdding(true)} className="ms-auto text-sm rounded-lg bg-emerald-700 text-white px-3 py-1.5 font-medium" data-testid="portal-issue-new">Signaler un problème</button>}
      </div>
      {adding && <ReportForm portalApi={portalApi} chantierRef={chantierRef} onDone={() => { setAdding(false); load(); }} onCancel={() => setAdding(false)} />}
      {data.issues.length === 0 ? <p className="px-4 py-6 text-sm text-slate-500 text-center" data-testid="portal-issues-empty">Aucun problème signalé. Si quelque chose ne va pas sur le chantier, signalez-le : l'entreprise crée une réserve et vous tient informé.</p> : (
        <div className="divide-y">
          {data.issues.map((i) => (
            <article key={i.issue_id} className="px-4 py-3 grid gap-2" data-testid={`portal-issue-${i.issue_id}`}>
              <IssueHeader issue={i} labels={data.labels} />
              {i.description && <p className="text-sm text-slate-700 whitespace-pre-wrap">{i.description}</p>}
              <IssuePhotos photos={i.photos} fileUrl={fileUrl} testId={`portal-issue-photos-${i.issue_id}`} />
              {i.assignee || i.target_date ? <p className="text-xs text-slate-500">{[i.assignee && `Pris en charge par ${i.assignee}`, i.target_date && `date prévue ${new Date(i.target_date).toLocaleDateString("fr-FR")}`].filter(Boolean).join(" · ")}</p> : null}
              {i.pro_response && <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-sm" data-testid={`portal-issue-response-${i.issue_id}`}><p className="text-[11px] uppercase tracking-wide text-emerald-800">Réponse de l'entreprise</p><p className="whitespace-pre-wrap">{i.pro_response}</p></div>}
              {i.status === "resolved" && i.client_confirmed == null && (
                <div className="flex flex-wrap gap-2 items-center text-sm" data-testid={`portal-issue-confirm-${i.issue_id}`}><span>L'entreprise indique que c'est résolu. Confirmez-vous ?</span>
                  <button type="button" onClick={() => confirm(i, true)} className="inline-flex items-center gap-1 rounded-lg border border-emerald-600 text-emerald-700 px-3 py-1" data-testid={`portal-issue-yes-${i.issue_id}`}><CheckCircle2 className="h-4 w-4" /> C'est réglé</button>
                  <button type="button" onClick={() => confirm(i, false)} className="inline-flex items-center gap-1 rounded-lg border border-red-500 text-red-700 px-3 py-1" data-testid={`portal-issue-no-${i.issue_id}`}><XCircle className="h-4 w-4" /> Pas réglé</button></div>
              )}
            </article>))}
        </div>)}
    </section>
  );
}
