import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { MessageSquare, Paperclip, Send, FileText, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DictateButton } from "@/components/voice/VoiceButtons";

const fmt = (iso) => { const d = new Date(iso); return `${d.toLocaleDateString("fr-FR")} ${d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`; };

/** Fil de messages partagé pro / portail. `mine(m)` dit si le message est de l'utilisateur courant ; `fileUrl(path)` construit l'URL d'une pièce jointe. */
export function MessageList({ messages, mine, fileUrl, emptyText, testId = "message-list" }) {
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest" }); }, [messages.length]);
  if (messages.length === 0) return <p className="text-sm text-muted-foreground px-4 py-6 text-center" data-testid={`${testId}-empty`}>{emptyText}</p>;
  return (
    <div className="grid gap-2 px-4 py-3 max-h-[420px] overflow-y-auto" data-testid={testId}>
      {messages.map((m) => (
        <div key={m.message_id} className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${mine(m) ? "ms-auto bg-primary text-primary-foreground" : "bg-muted"}`} data-testid={`message-${m.message_id}`}>
          <p className={`text-[11px] ${mine(m) ? "opacity-80" : "text-muted-foreground"}`}>{m.author_name} · {fmt(m.created_at)}</p>
          {m.body && <p className="whitespace-pre-wrap mt-0.5">{m.body}</p>}
          {m.attachments?.length > 0 && (
            <div className="flex flex-wrap gap-2 mt-2">
              {m.attachments.map((a) => a.content_type?.startsWith("image/")
                ? <a key={a.path} href={fileUrl(a.path)} target="_blank" rel="noreferrer" data-testid={`attachment-${m.message_id}`}><img src={fileUrl(a.path)} alt={a.name} className="h-20 w-20 object-cover rounded border" loading="lazy" /></a>
                : <a key={a.path} href={fileUrl(a.path)} target="_blank" rel="noreferrer" className={`inline-flex items-center gap-1 rounded border px-2 py-1 text-xs ${mine(m) ? "border-white/40" : "bg-background"}`} data-testid={`attachment-${m.message_id}`}><FileText className="h-3.5 w-3.5" /> {a.name}</a>)}
            </div>
          )}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}

/** Zone de saisie : texte + dictée + pièces jointes (photos/PDF, 5 max). `send(formData)` envoie ; `dictate(formData)` = client STT optionnel. */
export function MessageComposer({ send, dictate, placeholder = "A sua mensagem…", testId = "composer" }) {
  const [body, setBody] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!body.trim() && files.length === 0) return;
    const fd = new FormData();
    fd.append("body", body);
    files.forEach((f) => fd.append("files", f));
    setBusy(true);
    try { await send(fd); setBody(""); setFiles([]); }
    catch (err) { toast.error(err?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="border-t border-border px-4 py-3 grid gap-2" data-testid={testId}>
      {files.length > 0 && <div className="flex flex-wrap gap-1">{files.map((f, i) => <span key={i} className="inline-flex items-center gap-1 text-xs rounded border px-2 py-0.5 bg-muted" data-testid={`${testId}-file-${i}`}>{f.name}<button type="button" onClick={() => setFiles((l) => l.filter((_, j) => j !== i))} aria-label="Remover"><X className="h-3 w-3" /></button></span>)}</div>}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} placeholder={placeholder} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary" data-testid={`${testId}-input`} />
      <div className="flex items-center gap-2">
        <label className="inline-flex items-center gap-1 text-xs rounded-sm border px-2 py-1 cursor-pointer hover:bg-muted" data-testid={`${testId}-attach`}>
          <Paperclip className="h-3.5 w-3.5" /> Anexar {files.length > 0 && `(${files.length}/5)`}
          <input type="file" accept="image/jpeg,image/png,image/webp,application/pdf" multiple className="hidden" onChange={(e) => { setFiles((l) => [...l, ...Array.from(e.target.files)].slice(0, 5)); e.target.value = ""; }} data-testid={`${testId}-file-input`} />
        </label>
        <DictateButton testId={`${testId}-dictate`} request={dictate} onText={(t) => setBody((b) => [b, t].filter(Boolean).join(" "))} />
        <Button type="submit" size="sm" disabled={busy || (!body.trim() && files.length === 0)} className="ms-auto gap-1 h-8" data-testid={`${testId}-send`}><Send className="h-3.5 w-3.5" /> {busy ? "A enviar…" : "Enviar"}</Button>
      </div>
    </form>
  );
}

const CHANNELS = [["client", "Cliente"], ["subcontractors", "Subempreiteiros"]];

/** Panneau pro : messagerie par canal sur la fiche chantier, rafraîchie toutes les 10 s. */
export function ChantierMessagesPanel({ chantierId, api, initialChannel = "client", unread = {} }) {
  const [channel, setChannel] = useState(CHANNELS.some(([c]) => c === initialChannel) ? initialChannel : "client");
  const [messages, setMessages] = useState([]);
  const load = useCallback(() => api.get(`/chantiers/${chantierId}/messages`, { params: { channel } }).then(({ data }) => setMessages(data.messages)).catch(() => {}), [api, chantierId, channel]);
  useEffect(() => { load(); const id = setInterval(load, 10000); return () => clearInterval(id); }, [load]);
  const fileUrl = (p) => `${process.env.REACT_APP_BACKEND_URL}/api/chantiers/${chantierId}/messages/file?path=${encodeURIComponent(p)}`;
  return (
    <section className="surface" data-testid="chantier-messages">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 border-b border-border">
        <MessageSquare className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">Mensagens</p>
        <div className="ms-auto flex gap-1">
          {CHANNELS.map(([c, l]) => <button key={c} type="button" onClick={() => setChannel(c)} aria-pressed={channel === c} data-testid={`messages-channel-${c}`}
            className={`text-xs rounded-sm border px-2 py-1 inline-flex items-center gap-1 ${channel === c ? "bg-primary/10 border-primary/40 text-primary font-semibold" : "hover:bg-muted"}`}>{l}{unread[c] > 0 && channel !== c && <Badge className="rounded-sm h-4 px-1 text-[10px]" data-testid={`messages-unread-${c}`}>{unread[c]}</Badge>}</button>)}
        </div>
      </div>
      <MessageList messages={messages} mine={(m) => m.author_type === "pro"} fileUrl={fileUrl}
        emptyText={channel === "client" ? "Nenhuma mensagem com o cliente. Só os convidados «cliente» com a permissão Mensagens veem este canal." : "Nenhuma mensagem com os subempreiteiros. O cliente nunca vê este canal."} />
      <MessageComposer testId="pro-composer" placeholder={channel === "client" ? "Escrever ao cliente…" : "Escrever aos subempreiteiros…"}
        send={async (fd) => { fd.append("channel", channel); await api.post(`/chantiers/${chantierId}/messages`, fd); await load(); }} />
    </section>
  );
}
