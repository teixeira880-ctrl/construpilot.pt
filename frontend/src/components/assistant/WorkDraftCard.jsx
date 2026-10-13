import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";

export function WorkDraftCard({ initial }) {
  const instance = useId().replace(/:/g, "");
  const testId = (name) => `work-draft-${name}-${initial.draft_id}-${instance}`;
  const [draft, setDraft] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [conflict, setConflict] = useState(false);
  const [error, setError] = useState("");
  const [versions, setVersions] = useState(null);
  const [dirty, setDirty] = useState(false);
  const draftRef = useRef(initial), dirtyRef = useRef(false);
  const install = (next) => {
    draftRef.current = next; setDraft(next); dirtyRef.current = false;
    setDirty(false); setConflict(false); setError(""); setVersions(null);
  };
  const modify = (fields) => {
    const next = { ...draftRef.current, ...fields }; draftRef.current = next; setDraft(next);
    dirtyRef.current = true; setDirty(true);
  };
  useEffect(() => {
    let active = true;
    setLoading(true);
    api.get(`/assistant/work-drafts/${initial.draft_id}`).then(r => {
      if (active && !dirtyRef.current && (r.data.revision || 0) >= (draftRef.current.revision || 0)) install(r.data);
    }).catch(() => { if (active) setError("A versão guardada está indisponível. Tente novamente antes de alterar este rascunho."); })
      .finally(() => { if (active) setLoading(false); });
    const receive = (event) => {
      const next = event.detail;
      if (next?.draft_id !== initial.draft_id || (next.revision || 0) <= (draftRef.current.revision || 0)) return;
      if (dirtyRef.current) setConflict(true); else install(next);
    };
    window.addEventListener("construpilot:draft-updated", receive);
    return () => { active = false; window.removeEventListener("construpilot:draft-updated", receive); };
  }, [initial.draft_id]);
  const reload = async () => {
    setLoading(true);
    try { const r = await api.get(`/assistant/work-drafts/${initial.draft_id}`); install(r.data); }
    catch { setError("Carregamento impossível. O seu texto continua no editor."); }
    finally { setLoading(false); }
  };
  const save = async () => {
    const current = draftRef.current;
    const { kind, title, recipient, body } = current;
    const r = await api.put(`/assistant/work-drafts/${current.draft_id}`, { kind, title, recipient, body, expected_revision: current.revision || 0 });
    install(r.data);
    window.dispatchEvent(new CustomEvent("construpilot:draft-updated", { detail: r.data }));
    return r.data;
  };
  const act = async (action) => {
    setSaving(true);
    try {
      if (action === "copy") {
        await navigator.clipboard.writeText(`${draftRef.current.title}\n\n${draftRef.current.body}`);
        toast.success("Texto do editor copiado"); return;
      }
      const d = dirtyRef.current ? await save() : draftRef.current;
      if (action === "save") toast.success("Rascunho guardado");
      else if (action === "mail") window.location.href = `mailto:${encodeURIComponent(d.recipient)}?subject=${encodeURIComponent(d.title)}&body=${encodeURIComponent(d.body)}`;
      else {
        const r = await api.get(`/assistant/work-drafts/${d.draft_id}/export?format=${action}`, { responseType: "blob" });
        const url = URL.createObjectURL(r.data); const link = document.createElement("a");
        link.href = url; link.download = `brouillon-construpilot.${action}`; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (e) {
      if (e?.response?.status === 409) setConflict(true);
      toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Ação impossível; o seu texto continua no editor.");
    } finally { setSaving(false); }
  };
  const history = async () => {
    try { const r = await api.get(`/assistant/work-drafts/${draft.draft_id}/versions`); setVersions(r.data.versions); }
    catch { toast.error("Histórico indisponível"); }
  };
  return <div className="grid grid-cols-1 gap-2 mt-2 text-sm min-w-0" data-testid={testId("editor")} data-draft-id={initial.draft_id}>
    <div className="text-xs text-muted-foreground" data-testid={testId("version")}>Rascunho · Versão {draft.revision || 0}{dirty ? " · alterações não guardadas" : ""}{loading ? " · a carregar…" : ""}</div>
    {(conflict || error) && <div role="alert" className="border border-amber-500 rounded-sm p-2 text-xs" data-testid={testId("conflict")}>
      {error || "Existe uma versão mais recente. O seu texto fica aqui; pode copiá-lo antes de carregar a versão atual."}
      <button className="underline ml-2" disabled={loading || saving} onClick={reload} data-testid={testId("reload")}>Carregar a versão atual</button>
    </div>}
    <fieldset disabled={loading || saving || !!error} className="grid gap-2 disabled:opacity-60">
      <label>Título / assunto<input className="w-full border rounded-sm px-2 py-1 bg-background" maxLength={200} value={draft.title} onChange={e => modify({ title: e.target.value })} data-testid={testId("title")} /></label>
      {draft.kind === "email" && <label>Destinatário<input className="w-full border rounded-sm px-2 py-1 bg-background" placeholder="Morada a completar" value={draft.recipient} onChange={e => modify({ recipient: e.target.value })} data-testid={testId("recipient")} /></label>}
      <textarea aria-label="Texto do rascunho" rows={10} className="w-full border rounded-sm px-2 py-2 bg-background" value={draft.body} onChange={e => modify({ body: e.target.value })} data-testid={testId("body")} />
    </fieldset>
    <div className="flex flex-wrap gap-2 text-xs">
      {[["save", "Guardar"], ["copy", "Copiar este texto"], ["txt", "Transferir o texto"], ...(draft.kind === "email" ? [["eml", "Transferir o e-mail"], ["mail", "Abrir o meu e-mail"]] : [])].map(([action, label]) => <button key={action} disabled={saving || (action !== "copy" && (loading || !!error || conflict))} className="border rounded-sm px-2 py-1 bg-background disabled:opacity-50" onClick={() => act(action)} data-testid={testId(action)}>{label}</button>)}
      <button className="underline" disabled={loading || saving} onClick={history} data-testid={testId("history")}>Histórico</button>
    </div>
    {versions && <div className="border rounded-sm p-2 text-xs grid gap-2">
      <p>As 10 versões anteriores são conservadas. Retomar uma versão coloca-a no editor antes de guardar.</p>
      {!versions.length && <p>Nenhuma versão anterior.</p>}
      {versions.map(v => <button key={v.revision} className="text-left underline" disabled={saving || loading} onClick={() => modify({ kind: v.kind, title: v.title, recipient: v.recipient, body: v.body })} data-testid={testId(`restore-${v.revision}`)}>Retomar a versão {v.revision} — {v.title}</button>)}
    </div>}
    <p className="text-xs text-muted-foreground">Rascunho editável. O envio é feito no seu e-mail.</p>
  </div>;
}
