import { AssistantMark } from "./AssistantMark";
import { useStudioCopy } from "./studioCopy";
import { FileText, Loader2, Copy, CornerUpLeft, Download, ThumbsUp, ThumbsDown } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ActionCard } from "./ActionCard";
import { toast } from "sonner";
import { useWorkspaceCopy } from "@/components/workspace/copy";
import { PrivateImage, downloadAssistantFile } from "./PrivateMedia";
import { useDocumentViewer } from "./DocumentViewer";
import { ListenButton } from "@/components/voice/VoiceButtons";


// Un devis construit en plusieurs appels (par étage/lot) : seuls les fichiers PDF/Excel de sa dernière version sont affichés.
function onlyLatestQuoteFiles(actions) {
  const last = {};
  actions.forEach((a, j) => { const d = a?.result?.doc_id; if (d && Array.isArray(a.result.artifacts)) last[d] = j; });
  return actions.map((a, j) => {
    const d = a?.result?.doc_id;
    return d && Array.isArray(a.result.artifacts) && last[d] !== j ? { ...a, result: { ...a.result, artifacts: undefined } } : a;
  });
}

export function MessageBubble({ m, live, onCorrect, testId, queued, question }) {
  const ui = useWorkspaceCopy();
  const studio = useStudioCopy();
  const view = useDocumentViewer();
  const id = testId || `assistant-msg-${m.role}`;
  const mine = m.role === "user";
  const [rated, setRated] = useState(null);
  const [comment, setComment] = useState("");
  const [commentSent, setCommentSent] = useState(false);
  // Aprendizagem por feedback : 👍 → caso de referência ; 👎 + comentário → correção memorizada para este cliente.
  const sendFeedback = async (rating, note) => {
    setRated(rating);
    try {
      await api.post("/learning/feedback", {
        engine: "assistant", conversation_id: m.conversation_id || null, message_id: m.message_id || null,
        rating, answer: m.content, question: question || m.prompt || null, comment: note || null,
        cites_norm: /\b(NP\s?EN|EN\s?199\d|Eurocódigo|Eurocode|RGEU|RTIEBT|REH|RECS|LNEC)\b/i.test(m.content || ""),
      });
      toast.success(note ? "Obrigado — a correção fica memorizada" : "Obrigado pelo seu feedback");
      if (note) setCommentSent(true);
    } catch { if (!note) setRated(null); }
  };
  return (
    <div className={`assistant-message rounded-sm border text-sm ${mine ? "ml-auto bg-primary/10" : "bg-card"}${queued ? " assistant-message-queued" : ""}`} data-testid={id} data-message-role={m.role} data-queued={queued ? "true" : undefined}>
      <div className="assistant-message-author">{!mine && <AssistantMark size={24} />}<span>{mine ? studio("you") : ui("assistant")}</span></div>
      {mine ? <div className="whitespace-pre-wrap">{m.content}</div>
        : <div className="prose prose-sm dark:prose-invert max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>{alt}</span>, a: ({ href, children }) => {
            const h = href || "";
            const path = h.startsWith("http") ? (() => { try { const u = new URL(h); return u.pathname + u.search; } catch { return h; } })() : h;
            if (path.includes("/assistant/artifacts/")) {
              const fname = typeof children === "string" ? children : "ficheiro";
              return <button type="button" className="underline inline-flex items-center gap-1 text-primary" onClick={() => downloadAssistantFile(path.replace(/^\/api/, ""), fname).catch(() => toast.error("Descarga impossível"))} data-testid="assistant-inline-artifact"><Download className="inline h-3 w-3" />{children}</button>;
            }
            const ext = /^https?:/.test(h);
            return <a href={h} target={ext ? "_blank" : undefined} rel={ext ? "noreferrer" : undefined}>{children}</a>;
          }, table: ({ children }) => <div className="assistant-table-scroll" tabIndex={0} role="region" aria-label={studio("table")}><table>{children}</table></div> }}>{m.content}</ReactMarkdown>{live && <span className="inline-block w-1.5 h-4 bg-primary/70 animate-pulse align-middle ml-0.5" />}</div>}
      {m.attachments?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5" data-testid={`${id}-attachments`}>
          {m.attachments.map((f) => <div key={f.plan_id || f.doc_id} className="max-w-full grid gap-1 text-[11px] px-1.5 py-1 rounded-sm border bg-background" data-testid={`${id}-attachment-${f.plan_id || f.doc_id}`}>
            {f.doc_id && (f.kind === "photo" || f.mime?.startsWith("image/")) && <PrivateImage path={`/assistant/documents/${f.doc_id}/preview`} title={f.filename} testId={`${id}-photo-${f.doc_id}`} />}
            <span className="inline-flex gap-1 items-center break-all"><FileText className="h-3 w-3 shrink-0" /> {f.filename}</span>
          </div>)}
        </div>
      )}
      {m.status && <div className="text-[11px] text-muted-foreground flex items-center gap-1 mt-1" data-testid={`${id}-status`}><Loader2 className="h-3 w-3 animate-spin" /> {m.status}</div>}
      {m.actions?.length > 0 && <div className="grid grid-cols-1 min-w-0 max-w-full gap-1 mt-2">{onlyLatestQuoteFiles(m.actions).map((a, j) => <ActionCard key={j} a={a} />)}</div>}
      {m.sources?.length > 0 && (
        <div className="mt-2 text-[11px] text-muted-foreground" data-testid={`${id}-sources`}>
          {ui("sources")} : {m.sources.map((s, j) => <a key={j} href={s.url} data-testid={`${id}-source-${j}`} target="_blank" rel="noreferrer" className="underline mr-2">{s.title}</a>)}
        </div>
      )}
      {m.interrupted && <div className="text-[11px] text-amber-600 mt-1" data-testid={`${id}-interrupted`}>{ui("interrupted")}</div>}
      {!mine && !live && <div className="assistant-message-actions flex flex-wrap gap-3 mt-2 text-xs text-muted-foreground">
        <button className="underline" data-testid={`${id}-copy`} onClick={async () => { try { await navigator.clipboard.writeText(m.content); toast.success(ui("copied")); } catch { toast.error(ui("copyError")); } }}><Copy size={13} />{ui("copy")}</button>
        {onCorrect && <button className="underline" data-testid={`${id}-correct`} onClick={() => onCorrect(m)}><CornerUpLeft size={13} />{ui("correct")}</button>}
        {!mine && m.content && !live && <ListenButton label={studio("listen")} text={m.content} testId={`${id}-listen`} className="ms-1" />}
        {m.message_id && <button className="underline" data-testid={`${id}-export-pdf`} onClick={() => view(`/assistant/messages/${m.message_id}/pdf`, "ConstruPilot-solution-technique.pdf", "Solução técnica (PDF)")}><Download size={13} />PDF</button>}
        {m.model && <span data-testid={`${id}-model`}>{ui(m.response_mode === "thorough" ? "thorough" : "fast")}</span>}
        {m.message_id && <span className="inline-flex items-center gap-2 ms-auto" data-testid={`${id}-feedback`}>
          <button className={`transition-colors ${rated === "up" ? "text-emerald-600" : "hover:text-emerald-600"}`} disabled={!!rated} aria-label="Resposta útil" data-testid={`${id}-thumbs-up`} onClick={() => sendFeedback("up")}><ThumbsUp size={13} /></button>
          <button className={`transition-colors ${rated === "down" ? "text-red-600" : "hover:text-red-600"}`} disabled={!!rated} aria-label="Resposta a melhorar" data-testid={`${id}-thumbs-down`} onClick={() => sendFeedback("down")}><ThumbsDown size={13} /></button>
        </span>}
      </div>}
      {!mine && !live && rated === "down" && !commentSent && <form className="mt-2 flex gap-2 items-center" data-testid={`${id}-feedback-comment`} onSubmit={(e) => { e.preventDefault(); if (comment.trim()) sendFeedback("down", comment.trim()); }}>
        <input value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} placeholder="O que estava errado? (ex.: preço do m² de pintura é 9 €)" className="flex-1 min-w-0 rounded-sm border bg-background px-2 py-1 text-xs" aria-label="O que estava errado?" data-testid={`${id}-feedback-input`} />
        <button type="submit" className="underline text-xs" disabled={!comment.trim()} data-testid={`${id}-feedback-send`}>Enviar</button>
      </form>}
    </div>
  );
}

