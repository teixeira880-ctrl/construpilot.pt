import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles, MessageSquareText, ListChecks, FileText, Send, Info, X, ArrowRight, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { errMsg } from "./common";

/** Assistente BTP existente, aberto com o contexto da especialidade, fase e local (uma conversa por especialidade). */
export function AssistantPanel({ chantierId, specialty, contextLine, fase, local, onClose, onPrepareReport, intro, quick, compact = false, footnote = "Sugestões a validar pelo responsável." }) {
  const [conv, setConv] = useState(null);
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
        setConv(data.conversation_id);
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

  const actions = [...(quick || [[ListChecks, "O que falta preparar?"]]).map(([Icon, q]) => ({ Icon, label: q, run: () => ask(q) })),
    ...(onPrepareReport ? [{ Icon: FileText, label: "Preparar relatório", run: onPrepareReport }] : [])];
  return (
    <section className={`dob-card dob-assistant ${compact ? "dob-assistant-compact" : ""}`} aria-label="Assistente BTP" data-testid="dob-assistant">
      <header className="dob-assistant-head">
        <span className="dob-assistant-mark"><Sparkles size={26} aria-hidden="true" /></span>
        <div className="min-w-0 flex-1">
          <p className="dob-assistant-title">Assistente BTP</p>
          <p className="dob-assistant-ctx" data-testid="dob-assistant-context">{contextLine}</p>
        </div>
        <span className="dob-online" title="Disponível" aria-hidden="true" />
        {onClose && <button type="button" onClick={onClose} aria-label="Fechar o assistente" className="dob-assistant-close"><X size={16} /></button>}
      </header>
      <div className="dob-assistant-body" ref={bodyRef} aria-live="polite">
        {state === "error" ? <p className="text-sm" role="alert">{error}</p> : <>
          <div className="dob-bubble dob-bubble-a dob-intro"><MessageSquareText size={24} className="shrink-0" aria-hidden="true" /><span>{intro}</span></div>
          {msgs.length === 0 && !compact && <div className="dob-quick-list">{actions.map((a) => (
            <button key={a.label} type="button" className="dob-quick" onClick={a.run} disabled={!conv && a.label !== "Preparar relatório"} data-testid="dob-assistant-quick">
              <a.Icon size={20} aria-hidden="true" /><span className="flex-1">{a.label}</span><ArrowRight size={18} aria-hidden="true" /></button>))}</div>}
          {msgs.map((m, i) => <div key={i} className={`dob-bubble ${m.role === "user" ? "dob-bubble-u" : "dob-bubble-a"}`}>{m.content}</div>)}
          {state === "loading" && <p className="text-xs text-muted-foreground" role="status">A abrir a conversa…</p>}
          {state === "sending" && <p className="text-sm text-muted-foreground" role="status">O assistente está a analisar os registos…</p>}
          {error && state === "ready" && <p className="text-sm text-red-700" role="alert">{error}</p>}
        </>}
      </div>
      {!compact && <>
        <form className="dob-assistant-input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
          <label className="sr-only" htmlFor={`dob-q-${specialty}`}>Pergunta ao assistente</label>
          <input id={`dob-q-${specialty}`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Pergunte sobre este trabalho…" disabled={!conv} data-testid="dob-assistant-input" />
          <button type="submit" className="dob-send" disabled={!conv || !text.trim() || state === "sending"} aria-label="Enviar"><Send size={20} /></button>
        </form>
        <div className="dob-assistant-foot">
          <p className="dob-hint"><Info size={15} aria-hidden="true" /> {footnote}</p>
          {conv && <Link to={`/assistant?conversation=${conv}`} className="dob-hint hover:underline" title="Abrir no assistente completo"><ExternalLink size={14} /><span className="sr-only">Abrir completo</span></Link>}
        </div>
      </>}
      {compact && <div className="px-5 pb-4"><button type="button" className="dob-quick" onClick={() => ask("Revê o conteúdo selecionado e indica a informação em falta.")} disabled={!conv || state === "sending"} data-testid="dob-assistant-quick"><ListChecks size={18} /><span className="flex-1">Rever o conteúdo</span><ArrowRight size={16} /></button></div>}
    </section>
  );
}
