import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, MessageSquareText, ListChecks, Link2, FileText, Send, Info, X, ArrowRight, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { errMsg } from "./common";

const QUICK = [
  [ListChecks, "O que falta preparar?"],
  [Link2, "Que trabalhos dependem deste?"],
  [Sparkles, "Que materiais preciso de confirmar?"],
  [FileText, "Que documentos estão em falta?"],
];

/** Assistente BTP existente, aberto com o contexto da especialidade, fase e local (uma conversa por especialidade). */
export function AssistantPanel({ chantierId, specialty, specialtyLabel, fase, local, onClose, onPrepareReport, intro }) {
  const [conv, setConv] = useState(null);
  const [label, setLabel] = useState(`Assistente BTP · ${specialtyLabel}`);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [state, setState] = useState("loading");
  const [error, setError] = useState("");
  const bodyRef = useRef(null);

  useEffect(() => {
    let alive = true;
    setState("loading");
    api.post(`/dossier-obra/${chantierId}/especialidades/${specialty}/assistente`, { fase: fase || null, local: local || null })
      .then(async ({ data }) => {
        if (!alive) return;
        setConv(data.conversation_id); setLabel(data.label);
        try {
          const { data: c } = await api.get(`/assistant/conversations/${data.conversation_id}`);
          if (alive) setMsgs((c.messages || []).filter((m) => m.role === "user" || m.role === "assistant").map((m) => ({ role: m.role, content: m.content })));
        } catch { /* conversa nova */ }
        if (alive) setState("ready");
      })
      .catch((e) => { if (alive) { setState("error"); setError(e?.response?.status === 402 || e?.response?.status === 403 ? "O assistente não está incluído no seu plano ou na sua função." : errMsg(e, "Assistente indisponível de momento.")); } });
    return () => { alive = false; };
  }, [chantierId, specialty, fase, local]);

  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" }); }, [msgs, state]);

  const ask = async (q) => {
    const question = (q ?? text).trim();
    if (!question || !conv || state === "sending") return;
    setText(""); setError("");
    setMsgs((m) => [...m, { role: "user", content: question }]);
    setState("sending");
    try {
      const { data } = await api.post("/assistant/message", { conversation_id: conv, text: question, response_mode: "thorough" });
      setMsgs((m) => [...m, { role: "assistant", content: data?.content || "Sem resposta." }]);
    } catch (e) {
      setError(errMsg(e, "O assistente não respondeu. Tente novamente."));
    } finally { setState("ready"); }
  };

  return (
    <div className="dob-assistant-wrap">
      <section className="dob-card dob-assistant" aria-label="Assistente BTP" data-testid="dob-assistant">
        <header className="dob-assistant-head">
          <span className="dob-assistant-mark"><Sparkles size={22} aria-hidden="true" /></span>
          <div className="min-w-0 flex-1">
            <p className="font-bold text-lg leading-tight">Assistente BTP</p>
            <p className="text-xs text-muted-foreground" data-testid="dob-assistant-context">{label.replace(/^Assistente BTP · /, "")}</p>
          </div>
          {onClose && <button type="button" onClick={onClose} aria-label="Fechar o assistente" className="p-1 rounded-md hover:bg-muted"><X size={18} /></button>}
        </header>
        <div className="dob-assistant-body" ref={bodyRef} aria-live="polite">
          {state === "loading" && <p className="text-sm text-muted-foreground" role="status">A abrir a conversa desta especialidade…</p>}
          {state === "error" && <p className="text-sm" role="alert">{error}</p>}
          {state !== "loading" && state !== "error" && msgs.length === 0 && (
            <>
              <div className="dob-bubble dob-bubble-a flex gap-2"><MessageSquareText size={18} className="shrink-0 mt-0.5" aria-hidden="true" />{intro || "Estou a acompanhar esta especialidade. Quer verificar o que falta antes de avançar?"}</div>
              {QUICK.map(([Icon, q]) => <button key={q} type="button" className="dob-quick" onClick={() => ask(q)} data-testid="dob-assistant-quick"><Icon size={18} aria-hidden="true" /><span className="flex-1">{q}</span><ArrowRight size={16} aria-hidden="true" /></button>)}
              {onPrepareReport && <button type="button" className="dob-quick" onClick={onPrepareReport}><FileText size={18} aria-hidden="true" /><span className="flex-1">Preparar relatório</span><ArrowRight size={16} aria-hidden="true" /></button>}
            </>
          )}
          {msgs.map((m, i) => <div key={i} className={`dob-bubble ${m.role === "user" ? "dob-bubble-u" : "dob-bubble-a"}`}>{m.content}</div>)}
          {state === "sending" && <p className="text-sm text-muted-foreground" role="status">O assistente está a analisar os registos…</p>}
          {error && state === "ready" && <p className="text-sm text-red-700" role="alert">{error}</p>}
        </div>
        <form className="dob-assistant-input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <label className="sr-only" htmlFor="dob-assistant-q">Pergunta ao assistente</label>
          <textarea id="dob-assistant-q" rows={2} value={text} onChange={(e) => setText(e.target.value)} placeholder="Pergunte sobre este trabalho…"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }} disabled={!conv} data-testid="dob-assistant-input" />
          <button type="submit" className="dob-send" disabled={!conv || !text.trim() || state === "sending"} aria-label="Enviar"><Send size={18} /></button>
        </form>
        <div className="flex items-center justify-between gap-2 px-4 pb-3 pt-1">
          <p className="dob-hint"><Info size={14} aria-hidden="true" /> Sugestões a validar pelo responsável.</p>
          {conv && <Link to={`/assistant?conversation=${conv}`} className="dob-hint hover:underline"><ExternalLink size={13} /> Abrir completo</Link>}
        </div>
      </section>
    </div>
  );
}
