import { useRef, useState } from "react";
import { Camera, Loader2, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PrivateImage } from "./PrivateMedia";

/* Dated site photos pinned to a dossier entry: « avant » / « après » the decision. */
export const EntryPhotos = ({ conversationId, entry, onChange }) => {
  const [phase, setPhase] = useState("before");
  const [busy, setBusy] = useState(false);
  const input = useRef(null);
  const photos = entry.photos || [];
  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData(); fd.append("file", file); fd.append("kind", "photo");
      const { data: doc } = await api.post("/assistant/documents", fd);
      await api.post(`/assistant/conversations/${conversationId}/state/${entry.entry_id}/photos`, { doc_id: doc.doc_id, phase, taken_at: null, caption: null });
      toast.success(`Photo « ${phase === "before" ? "avant" : "após" }» fixada`);
      onChange?.();
    } catch (e) { toast.error(typeof e?.response?.data?.detail === "string" ? e.response.data.detail : "Fotografia não fixada"); }
    finally { setBusy(false); if (input.current) input.current.value = ""; }
  };
  const unpin = async (p) => {
    try { await api.delete(`/assistant/conversations/${conversationId}/state/${entry.entry_id}/photos/${p.doc_id}`); onChange?.(); }
    catch { toast.error("Remoção impossível"); }
  };
  const fmt = (d) => d ? new Date(d).toLocaleDateString("fr-FR") : "date inconnue";
  const group = (ph) => photos.filter((p) => p.phase === ph);
  return <div className="mt-1 grid gap-1" data-testid={`entry-photos-${entry.entry_id}`}>
    {photos.length > 0 && <div className="grid grid-cols-2 gap-2">
      {["before", "after"].map((ph) => <div key={ph}>
        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{ph === "before" ? "Avant" : "Após"} ({group(ph).length})</div>
        <div className="flex flex-wrap gap-1">
          {group(ph).map((p) => <div key={p.doc_id} className="relative w-16" data-testid={`entry-photo-${p.doc_id}`}>
            <PrivateImage path={`/assistant/documents/${p.doc_id}/preview`} title={`${ph === "before" ? "Avant" : "Após"} · ${fmt(p.taken_at)}`} testId={`entry-photo-img-${p.doc_id}`} small />
            <div className="text-[10px] leading-tight">{fmt(p.taken_at)} <span className="text-muted-foreground">({p.date_source})</span></div>
            <button type="button" aria-label="Remover a fotografia" className="absolute -top-1 -right-1 rounded-full bg-background border p-0.5" onClick={() => unpin(p)} data-testid={`entry-photo-unpin-${p.doc_id}`}><X size={10} /></button>
          </div>)}
        </div>
      </div>)}
    </div>}
    <div className="flex items-center gap-1 text-[11px]">
      <select value={phase} onChange={(e) => setPhase(e.target.value)} className="rounded-sm border bg-background px-1 py-0.5" aria-label="Phase" data-testid={`entry-photo-phase-${entry.entry_id}`}>
        <option value="before">Avant</option><option value="after">Após</option>
      </select>
      <button type="button" className="underline flex items-center gap-1" disabled={busy} onClick={() => input.current?.click()} data-testid={`entry-photo-add-${entry.entry_id}`}>{busy ? <Loader2 size={10} className="animate-spin" /> : <Camera size={10} />} Adicionar uma fotografia datada</button>
      <input ref={input} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid={`entry-photo-input-${entry.entry_id}`} />
    </div>
  </div>;
};
