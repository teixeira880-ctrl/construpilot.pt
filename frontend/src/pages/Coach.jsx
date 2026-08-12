import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Send, Mic, MicOff, Sparkles, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { API } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";

const EXAMPLES = [
  "Combien coûte la rénovation d'un appartement de 70 m² ?",
  "Combien de plaques de placo pour un mur de 5 m sur 2,50 m ?",
  "Quelle épaisseur d'isolation choisir pour mes combles ?",
  "Comment préparer un mur avant peinture ?",
  "Quel carrelage choisir pour ma salle de bain ?",
  "Pourquoi mon mur est humide ?",
];

export default function Coach() {
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Bonjour, je suis ConstruPilot. Décrivez votre chantier ou posez-moi votre question travaux : estimation, matériaux, étapes, choix techniques." },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [listening, setListening] = useState(false);
  const [speak, setSpeak] = useState(false);
  const bottom = useRef(null);
  const recognition = useRef(null);

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
      toast.error("Le coach IA est momentanément indisponible");
    } finally {
      setStreaming(false);
    }
  };

  const toggleMic = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return toast.error("Reconnaissance vocale non supportée par ce navigateur");
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
    r.onerror = () => { setListening(false); toast.error("Micro indisponible"); };
    recognition.current = r;
    r.start();
    setListening(true);
  };

  return (
    <div className="grid gap-8">
      <SectionTitle over="Coach IA ConstruPilot" title="Votre copilote travaux, à la voix ou au clavier">
        Explications, ordres de grandeur, matériaux, étapes et recommandations professionnelles.
        Les chiffrages définitifs passent toujours par le moteur de calcul.
      </SectionTitle>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((e) => (
          <button
            key={e} onClick={() => send(e)} data-testid={`coach-example-${e.slice(0, 10)}`}
            className="px-3 py-1.5 text-xs rounded-sm border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          >
            {e}
          </button>
        ))}
      </div>

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
            aria-label="Réponse vocale"
          >
            <Volume2 className="h-4 w-4" />
          </Button>
          <Input
            value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Posez votre question travaux…"
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
