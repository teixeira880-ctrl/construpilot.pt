import { useEffect, useRef, useState } from "react";
import { Mic, MicOff, Sparkles, Loader2, X } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { useHaptic } from "@/hooks/useHaptic";

/**
 * Barra de prompt IA transversal.
 * - Reconhecimento de voz pt-PT (Web Speech API) quando disponível
 * - Chama POST /api/prompt-fill/{appKey}; aplica no estado via onFill(data)
 * - Pergunta de clarificação devolvida pela IA via onClarify(pergunta)
 * - Nunca substitui o preenchimento manual
 */
export default function PromptBar({
  appKey,
  context,
  onFill,
  onClarify,
  placeholder,
  examples,
  disabled = false,
}) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [clarify, setClarify] = useState("");
  const haptic = useHaptic();
  const [recognitionAvailable, setRecognitionAvailable] = useState(false);
  const recRef = useRef(null);

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    setRecognitionAvailable(Boolean(SR));
    if (!SR) return;
    const r = new SR();
    r.lang = "pt-PT";
    r.continuous = false;
    r.interimResults = true;
    r.onresult = (e) => {
      const txt = Array.from(e.results)
        .map((x) => x[0].transcript)
        .join(" ");
      setValue(txt);
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recRef.current = r;
    return () => {
      try {
        r.stop();
      } catch {
        /* ignorar */
      }
    };
  }, []);

  const toggleMic = () => {
    const r = recRef.current;
    if (!r) {
      toast.info("Ditado por voz indisponível neste navegador. Escreva o pedido.");
      return;
    }
    if (listening) {
      try {
        r.stop();
      } catch {
        /* ignorar */
      }
      setListening(false);
    } else {
      try {
        r.start();
        setListening(true);
      } catch {
        /* ignorar */
      }
    }
  };

  const gerar = async () => {
    const prompt = value.trim();
    if (prompt.length < 3) return;
    setBusy(true);
    setClarify("");
    try {
      const { data } = await api.post(`/prompt-fill/${appKey}`, {
        prompt,
        contexto: context || {},
      });
      // 1) Aplicar preenchimento parcial SEMPRE que houver params, mesmo com ok=false
      const hasParams =
        data?.params && typeof data.params === "object" && Object.keys(data.params).length > 0;
      if (hasParams) {
        onFill?.(data);
      }
      // 2) Mostrar banner de clarificação (adicionalmente ao fill parcial)
      if (data?.clarification_question) {
        setClarify(data.clarification_question);
        haptic.warn();
        onClarify?.(data.clarification_question);
        // mantém o texto no input para o utilizador poder refinar
      } else if (data?.ok) {
        // sucesso total: limpar input
        haptic.success();
        setValue("");
      } else if (!hasParams) {
        // nem params nem clarificação: foi erro real
        haptic.error();
        toast.error(data?.error || "Não foi possível interpretar o pedido.");
      }
    } catch (e) {
      haptic.error();
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === "string"
          ? detail
          : "Serviço de IA indisponível. Preencha manualmente.",
      );
    } finally {
      setBusy(false);
    }
  };

  const ph =
    placeholder ||
    "Descreva o que quer (ex.: «Escada em U, 2,70 m, 90 cm»)…";

  return (
    <div
      className="rounded-xl border border-primary/20 bg-primary/5 p-3 mb-4"
      data-testid="prompt-bar"
    >
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex-1 flex gap-2">
          <input
            type="text"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && gerar()}
            placeholder={ph}
            disabled={disabled || busy}
            className="flex-1 h-10 rounded-md border border-border bg-background px-3 text-sm"
            data-testid="prompt-input"
            aria-label="Prompt da IA"
          />
          {recognitionAvailable && (
            <button
              type="button"
              onClick={toggleMic}
              aria-label={listening ? "Parar ditado" : "Ditar"}
              className={`h-10 w-10 rounded-md border flex items-center justify-center ${
                listening
                  ? "bg-red-500 text-white border-red-500 animate-pulse"
                  : "bg-background border-border hover:bg-muted"
              }`}
              data-testid="prompt-mic"
            >
              {listening ? (
                <MicOff className="h-4 w-4" />
              ) : (
                <Mic className="h-4 w-4" />
              )}
            </button>
          )}
        </div>
        <button
          type="button"
          onClick={gerar}
          disabled={disabled || busy || value.trim().length < 3}
          className="h-10 px-4 rounded-md bg-primary text-primary-foreground font-medium disabled:opacity-50 inline-flex items-center justify-center gap-2"
          data-testid="prompt-generate"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          Gerar
        </button>
      </div>

      {examples && (
        <p className="text-[11px] text-muted-foreground mt-2">{examples}</p>
      )}

      {clarify && (
        <div
          className="mt-2 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
          data-testid="prompt-clarify"
          role="status"
        >
          <Sparkles className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <span className="font-medium">A IA pergunta:</span> {clarify}
          </div>
          <button
            type="button"
            onClick={() => setClarify("")}
            aria-label="Fechar"
            className="text-amber-800 hover:text-amber-900"
            data-testid="prompt-clarify-close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
