import { AssistantMark } from "./AssistantMark";
import { useStudioCopy } from "./studioCopy";
import { FileText, Loader2, Copy, CornerUpLeft, Download } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ActionCard } from "./ActionCard";
import { toast } from "sonner";
import { useWorkspaceCopy } from "@/components/workspace/copy";
import { PrivateImage } from "./PrivateMedia";
import { useDocumentViewer } from "./DocumentViewer";
import { ListenButton } from "@/components/voice/VoiceButtons";

export function MessageBubble({ m, live, onCorrect, testId }) {
  const ui = useWorkspaceCopy();
  const studio = useStudioCopy();
  const view = useDocumentViewer();
  const id = testId || `assistant-msg-${m.role}`;
  const mine = m.role === "user";
  return (
    <div className={`assistant-message rounded-sm border text-sm ${mine ? "ml-auto bg-primary/10" : "bg-card"}`} data-testid={id} data-message-role={m.role}>
      <div className="assistant-message-author">{!mine && <AssistantMark size={24} />}<span>{mine ? studio("you") : ui("assistant")}</span></div>
      {mine ? <div className="whitespace-pre-wrap">{m.content}</div>
        : <div className="prose prose-sm dark:prose-invert max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ img: ({ alt }) => <span>{alt}</span>, table: ({ children }) => <div className="assistant-table-scroll" tabIndex={0} role="region" aria-label={studio("table")}><table>{children}</table></div> }}>{m.content}</ReactMarkdown>{live && <span className="inline-block w-1.5 h-4 bg-primary/70 animate-pulse align-middle ml-0.5" />}</div>}
      {m.attachments?.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5" data-testid={`${id}-attachments`}>
          {m.attachments.map((f) => <div key={f.plan_id || f.doc_id} className="max-w-full grid gap-1 text-[11px] px-1.5 py-1 rounded-sm border bg-background" data-testid={`${id}-attachment-${f.plan_id || f.doc_id}`}>
            {f.doc_id && (f.kind === "photo" || f.mime?.startsWith("image/")) && <PrivateImage path={`/assistant/documents/${f.doc_id}/preview`} title={f.filename} testId={`${id}-photo-${f.doc_id}`} />}
            <span className="inline-flex gap-1 items-center break-all"><FileText className="h-3 w-3 shrink-0" /> {f.filename}</span>
          </div>)}
        </div>
      )}
      {m.status && <div className="text-[11px] text-muted-foreground flex items-center gap-1 mt-1" data-testid={`${id}-status`}><Loader2 className="h-3 w-3 animate-spin" /> {m.status}</div>}
      {m.actions?.length > 0 && <div className="grid grid-cols-1 min-w-0 max-w-full gap-1 mt-2">{m.actions.map((a, j) => <ActionCard key={j} a={a} />)}</div>}
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
      </div>}
    </div>
  );
}

