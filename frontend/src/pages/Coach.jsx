import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Send, Mic, MicOff, Sparkles, Volume2, Calculator } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API, api } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { useI18n } from "@/context/I18nContext";

const EXAMPLE_KEYS = ["coach.ex1", "coach.ex2", "coach.ex3", "coach.ex4", "coach.ex5", "coach.ex6"];

export default function Coach() {
  const { t } = useI18n();
  const [messages, setMessages] = useState([
    { role: "assistant", content: t("coach.greeting") },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [sendingEst, setSendingEst] = useState(false);
  const bottom = useRef(null);
  const recognition = useRef(null);
  const navigate = useNavigate();

  const hasUserMsg = messages.some((m) => m.role === "user" && m.content.trim());

  const goEstimate = async () => {
    const desc = messages.filter((m) => m.role === "user").map((m) => m.content).join("\n").trim();
    if (!desc || sendingEst) return;
    setSendingEst(true);
    try {
      const { data } = await api.post("/estimation/analyse", { description: desc });
      sessionStorage.setItem("estimator_prefill",
        JSON.stringify({ ...(data.analysis || {}), _raw: desc }));
      toast.success(t("coach.sent_toast"));
      navigate("/estimation?from=coach");
    } catch {
      sessionStorage.setItem("estimator_prefill", JSON.stringify({ description: desc, _raw: desc }));
      toast.message(t("coach.sent_toast_fallback"));
      navigate("/estimation?from=coach");
    } finally { setSendingEst(false); }
  };

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const send = async (text = input) => {
    const msg = text.trim();
    if (!msg || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: msg }, { role: "assistant", content: "" }]);
    setStreaming(true);
    try {
      const res = await fetch(`${API}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message: msg, session_id: sessionId }),
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let full = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop();
        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          const payload = JSON.parse(part.slice(6));
          if (payload.session_id) setSessionId(payload.session_id);
          if (payload.delta) {
            full += payload.delta;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: "assistant", content: full };
              return copy;
            });
          }
        }
      }
      if (speak && full && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(full.slice(0, 600));
        u.lang = "fr-FR";
        window.speechSynthesis.speak(u);
      }
    } catch {
      toast.error(t("coach.unavailable"));
    } finally {
      setStreaming(false);
    }
  };

  const toggleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast.error(t("coach.mic_unsupported"));
    if (listening) {
      recognition.current?.stop();
      setListening(false);
      return;
    }
    const r = new SR();
    r.lang = "fr-FR";
    r.interimResults = false;
    r.onresult = (e) => {
      const text = e.results[0][0].transcript;
      setInput(text);
      send(text);
    };
    r.onend = () => setListening(false);
    r.onerror = () => { setListening(false); toast.error(t("coach.mic_error")); };
    recognition.current = r;
    r.start();
    setListening(true);
  };

  return (
    <div className="grid gap-8">
      <SEO title="Coach IA travaux" description="Coloque as suas questões sobre obras, renovação, materiais, IVA, licenças à IA ConstruPilot. Resposta quantificada em 30 segundos, por voz ou teclado. Gratuito." keywords="coach de obras, chatbot construção, IA remodelação, ajuda ao profissional, perguntas sobre obras" canonical="/coach" />
      <SectionTitle as="h1" over={t("coach.over")} title={t("coach.title")}>
        {t("coach.subtitle")}
      </SectionTitle>

      <div className="flex flex-wrap gap-2">
        {EXAMPLE_KEYS.map((k) => (
          <button
            key={k} onClick={() => send(t(k))} data-testid={`coach-example-${k}`}
            className="px-3 py-1.5 text-xs rounded-sm border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          >
            {t(k)}
          </button>
        ))}
      </div>

      {hasUserMsg && (
        <div className="flex items-center justify-between gap-3 flex-wrap surface p-3 border-primary/40"
             data-testid="coach-to-estimator-bar">
          <p className="text-sm text-muted-foreground">
            {t("coach.to_estimator_hint")}
          </p>
          <Button onClick={goEstimate} disabled={sendingEst}
                  data-testid="coach-to-estimator-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white shrink-0">
            <Calculator className="h-4 w-4" />
            {sendingEst ? t("coach.analyzing") : t("coach.to_estimator_btn")}
          </Button>
        </div>
      )}

      <div className="surface flex flex-col h-[62vh]">
        <div className="flex-1 overflow-y-auto p-6 grid gap-5" data-testid="chat-messages">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`}>
              {m.role === "assistant" && (
                <span className="shrink-0 h-8 w-8 grid place-items-center bg-primary/15 border border-primary/30 rounded-sm">
                  <Sparkles className="h-4 w-4 text-primary" />
                </span>
              )}
              <div
                data-testid={`chat-message-${m.role}`}
                className={`max-w-[80%] p-4 rounded-sm text-sm whitespace-pre-wrap ${
                  m.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary"
                }`}
              >
                {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>

        <div className="border-t border-border p-3 flex gap-2">
          <Button
            variant="outline" onClick={toggleMic} data-testid="mic-btn"
            className={`rounded-sm shrink-0 ${listening ? "border-primary text-primary" : ""}`}
            aria-label="Assistant vocal"
          >
            {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </Button>
          <Button
            variant="outline" onClick={() => setSpeak(!speak)} data-testid="speak-toggle-btn"
            className={`rounded-sm shrink-0 ${speak ? "border-primary text-primary" : ""}`}
            aria-label="Resposta por voz"
          >
            <Volume2 className="h-4 w-4" />
          </Button>
          <Input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={t("coach.placeholder")}
            data-testid="chat-input" className="rounded-sm h-11"
          />
          <Button onClick={() => send()} disabled={streaming} data-testid="chat-send-btn" className="rounded-sm h-11 gap-2 hover:bg-orange-600 hover:text-white">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
