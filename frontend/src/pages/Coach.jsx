import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Send, Mic, MicOff, Sparkles, Volume2, Calculator, AlertTriangle, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { useI18n } from "@/context/I18nContext";
import { useAuth } from "@/context/AuthContext";

const EXAMPLE_KEYS = ["coach.ex1", "coach.ex2", "coach.ex3", "coach.ex4", "coach.ex5", "coach.ex6"];

export default function Coach() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isFree = user?.account_type === "particulier" && user?.role !== "admin";
  const [params] = useSearchParams();
  const projectId = params.get("project_id") || null;
  const [messages, setMessages] = useState([
    { role: "assistant", content: t("coach.greeting") },
  ]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [conversationId, setConversationId] = useState(null);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const [sendingEst, setSendingEst] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
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
    if (!msg || thinking) return;
    setInput("");
    setUnavailable(false);
    setMessages((m) => [...m, { role: "user", content: msg }]);
    setThinking(true);
    try {
      const payload = { message: msg };
      if (projectId) payload.project_id = projectId;
      if (conversationId) payload.conversation_id = conversationId;
      const { data } = await api.post("/coach/ask", payload);
      if (!data?.reply || !data.reply.trim()) {
        throw new Error("empty_reply");
      }
      setConversationId(data.conversation_id);
      setMessages((m) => [...m, {
        role: "assistant",
        content: data.reply,
        meta: data.meta,
      }]);
      if (speak && window.speechSynthesis) {
        const u = new SpeechSynthesisUtterance(data.reply.slice(0, 600));
        u.lang = "pt-PT";
        window.speechSynthesis.speak(u);
      }
    } catch (err) {
      const status = err?.response?.status;
      const detail = err?.response?.data?.detail;
      const body = err?.response?.data;
      if (status === 429) {
        // Rate limit — mensagem PT-PT com link upgrade
        const msg = body?.message || "Atingiu o limite de pedidos.";
        const upgradeUrl = body?.upgrade_url || "/pricing";
        const isFreeUser = body?.current_plan === "free";
        toast.error(msg, {
          duration: 7000,
          action: isFreeUser ? { label: "Upgrade", onClick: () => navigate(upgradeUrl) } : undefined,
          "data-testid": "coach-rate-limit-toast",
        });
      } else if (status === 503) {
        setUnavailable(true);
        toast.error(detail?.message || t("coach.unavailable"));
        if (detail?.conversation_id) setConversationId(detail.conversation_id);
      } else if (status === 401) {
        toast.error("Sessão expirada. Volte a iniciar sessão.");
      } else {
        toast.error(t("coach.unavailable") || "Erro ao contactar o assistente.");
      }
    } finally {
      setThinking(false);
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
    r.lang = "pt-PT";
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
      <SEO title="Coach IA obras" description="Ponha as suas questões sobre obras, renovação, materiais, IVA e licenças à IA do ConstruPilot. Resposta orçamentada em 30 segundos, por voz ou teclado. Gratuito." keywords="coach obras, chatbot construção, IA renovação, ajuda profissional, questões obras" canonical="/coach" />
      <SectionTitle as="h1" over={t("coach.over")} title={t("coach.title")}>
        {t("coach.subtitle")}
      </SectionTitle>

      {isFree && (
        <div
          data-testid="coach-free-banner"
          className="flex items-center justify-between gap-3 rounded-sm border border-primary/30 bg-primary/5 px-4 py-3 text-sm"
        >
          <div className="flex items-center gap-2.5">
            <Rocket className="h-4 w-4 text-primary shrink-0" />
            <span className="text-muted-foreground">
              Está no plano <strong className="text-foreground">Grátis</strong> · 20 pedidos/h.
              Faça upgrade para <strong>Pro (99 €/mês)</strong> e tenha 60 pedidos/h.
            </span>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/pricing")}
            data-testid="coach-upgrade-btn"
            className="rounded-sm shrink-0 border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground"
          >
            Ver planos
          </Button>
        </div>
      )}

      <div className="flex flex-wrap gap-2" data-testid="coach-examples">
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

      <div className="surface flex flex-col h-[62vh]" data-testid="coach-chat-panel">
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
                {m.content}
                {m.role === "assistant" && m.meta?.mode_used && (
                  <div className="mt-2 pt-2 border-t border-border/40 text-[10px] text-muted-foreground uppercase tracking-wide">
                    Aurora · {m.meta.mode_used}
                  </div>
                )}
              </div>
            </div>
          ))}
          {thinking && (
            <div className="flex gap-3" data-testid="coach-thinking">
              <span className="shrink-0 h-8 w-8 grid place-items-center bg-primary/15 border border-primary/30 rounded-sm">
                <Sparkles className="h-4 w-4 text-primary animate-pulse" />
              </span>
              <div className="max-w-[80%] p-4 rounded-sm text-sm bg-secondary text-muted-foreground italic">
                A pensar…
              </div>
            </div>
          )}
          {unavailable && !thinking && (
            <div className="flex gap-3" data-testid="coach-unavailable">
              <span className="shrink-0 h-8 w-8 grid place-items-center bg-destructive/15 border border-destructive/30 rounded-sm">
                <AlertTriangle className="h-4 w-4 text-destructive" />
              </span>
              <div className="max-w-[80%] p-4 rounded-sm text-sm bg-destructive/10 border border-destructive/30">
                O assistente IA está temporariamente indisponível. Já notificámos o administrador.
                Tente novamente em alguns minutos.
              </div>
            </div>
          )}
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
            aria-label="Réponse vocale"
          >
            <Volume2 className="h-4 w-4" />
          </Button>
          <Input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder={t("coach.placeholder")}
            data-testid="chat-input" className="rounded-sm h-11"
            disabled={thinking}
          />
          <Button onClick={() => send()} disabled={thinking || !input.trim()}
                  data-testid="chat-send-btn"
                  className="rounded-sm h-11 gap-2 hover:bg-orange-600 hover:text-white">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
