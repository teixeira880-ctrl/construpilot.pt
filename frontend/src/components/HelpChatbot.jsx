import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send, Loader2, Bot } from "lucide-react";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";

export default function HelpChatbot() {
  const { t } = useI18n();
  const SUGGESTIONS = [t("help.s1"), t("help.s2"), t("help.s3"), t("help.s4")];
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    { role: "assistant", content: t("help.greeting") },
  ]);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);
  useEffect(() => { const h = () => setOpen(true); window.addEventListener("cp:open-help", h); return () => window.removeEventListener("cp:open-help", h); }, []);

  const send = async (text) => {
    const msg = (text ?? input).trim();
    if (!msg || busy) return;
    setInput("");
    const history = messages;
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setBusy(true);
    try {
      const { data } = await api.post("/help/chat", { message: msg, session_id: sessionId, history, page: window.location.pathname });
      setSessionId(data.session_id);
      setMessages((m) => [...m, { role: "assistant", content: data.reply, actions: data.actions || [] }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: t("help.error") }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} data-testid="help-chatbot-open"
          className="fixed bottom-5 right-5 z-50 flex items-center gap-2 rounded-full bg-primary text-primary-foreground shadow-lg px-4 py-3 hover:scale-105 transition-transform">
          <MessageCircle className="h-5 w-5" />
          <span className="text-sm font-semibold hidden sm:inline">{t("help.open")}</span>
        </button>
      )}

      {open && (
        <div className="fixed bottom-5 right-5 z-50 w-[92vw] max-w-[380px] h-[70vh] max-h-[560px] flex flex-col rounded-xl border border-border bg-background shadow-2xl overflow-hidden" data-testid="help-chatbot-panel">
          <div className="flex items-center justify-between px-4 py-3 bg-primary text-primary-foreground">
            <div className="flex items-center gap-2"><Bot className="h-5 w-5" /><span className="font-bold text-sm">{t("help.title")}</span></div>
            <button onClick={() => setOpen(false)} data-testid="help-chatbot-close"><X className="h-5 w-5" /></button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`} data-testid={`help-msg-${m.role}-${i}`}>
                <div className="max-w-[85%]">
                  <div className={`rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${m.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-secondary text-foreground rounded-bl-sm"}`}>
                    {m.content}
                  </div>
                  {m.role === "assistant" && (m.actions || []).length > 0 && (
                    <div className="flex flex-wrap gap-2 mt-2">
                      {m.actions.map((a, k) => (
                        <button key={k} onClick={() => { window.location.href = a.to; }} data-testid={`help-action-${i}-${k}`}
                          className="text-xs font-semibold bg-primary text-primary-foreground rounded-full px-3 py-1.5 hover:scale-105 transition-transform">
                          {a.label} →
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start"><div className="bg-secondary rounded-2xl px-3 py-2 rounded-bl-sm"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div></div>
            )}
            {messages.length <= 1 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} onClick={() => send(s)} data-testid={`help-suggestion-${i}`}
                    className="text-xs border border-border rounded-full px-3 py-1 hover:bg-secondary/60 text-left">{s}</button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="border-t border-border p-2 flex items-center gap-2">
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(); }}
              placeholder={t("help.placeholder")} data-testid="help-chatbot-input"
              className="flex-1 rounded-full border border-border bg-background px-4 py-2 text-sm outline-none focus:border-primary" />
            <button onClick={() => send()} disabled={busy || !input.trim()} data-testid="help-chatbot-send"
              className="rounded-full bg-primary text-primary-foreground p-2.5 disabled:opacity-40 hover:scale-105 transition-transform">
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
