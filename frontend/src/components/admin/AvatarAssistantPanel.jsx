import { useEffect, useRef, useState } from "react";
import { Video, PhoneOff, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

// Assistente de vídeo interno (avatar Synthesia « Kenji » via LiveKit).
// Reservado a admins: o backend (/admin/avatar/token) verifica o papel e só
// devolve um token de sala de 15 min. Nenhuma chave chega ao navegador.

const LANG_LABEL = { fr: "Français", pt: "Português (PT)", en: "English" };

// Mensagens enviadas pelo agente (topic « avatar ») quando o avatar não consegue arrancar.
const AVATAR_STATUS = {
  busy: "O avatar já está a ser usado por outro admin (uma conversa de cada vez com o plano Synthesia atual). Tente daqui a alguns minutos.",
  quota: "Quota Synthesia esgotada este mês.",
  config: "Problema de configuração do avatar (chave Synthesia ou LiveKit): ",
  error: "O avatar não conseguiu arrancar, tente de novo.",
};

export default function AvatarAssistantPanel() {
  const [status, setStatus] = useState(null);
  const [lang, setLang] = useState("pt");
  const [phase, setPhase] = useState("idle"); // idle | connecting | waiting | live
  const [message, setMessage] = useState("");
  const roomRef = useRef(null);
  const mediaRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    api.get("/admin/avatar/status")
      .then(({ data }) => { setStatus(data); setLang(data.default_lang || "pt"); })
      .catch(() => setStatus({ configured: false }));
    return () => { clearTimeout(timerRef.current); roomRef.current?.disconnect(); };
  }, []);

  const reset = (msg = "") => {
    clearTimeout(timerRef.current);
    roomRef.current = null;
    if (mediaRef.current) mediaRef.current.replaceChildren();
    setPhase("idle");
    setMessage(msg);
  };

  const start = async () => {
    setPhase("connecting");
    setMessage("");
    try {
      const { data } = await api.get("/admin/avatar/token", { params: { lang } });
      const { Room, RoomEvent } = await import("livekit-client");
      const room = new Room({ adaptiveStream: false }); // resolução máxima para o avatar
      roomRef.current = room;
      let video = null;
      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (!video) {
          video = document.createElement("video");
          video.playsInline = true;
          video.className = "w-full aspect-video rounded-md bg-black";
          mediaRef.current?.replaceChildren(video);
        }
        track.attach(video); // áudio + vídeo no mesmo elemento
        if (track.kind === "video") {
          clearTimeout(timerRef.current);
          setPhase("live");
          setMessage("");
        }
      });
      let notice = null;
      room.on(RoomEvent.DataReceived, (payload, _p, _k, topic) => {
        if (topic !== "avatar") return;
        try {
          const m = JSON.parse(new TextDecoder().decode(payload));
          if (m.type === "avatar_status") {
            clearTimeout(timerRef.current);
            notice = (AVATAR_STATUS[m.code] || AVATAR_STATUS.error) + (m.code === "config" ? (m.detail || "") : "");
            setMessage(notice);
            room.disconnect();
          }
        } catch (_) { /* mensagem ilegível: ignorada */ }
      });
      room.on(RoomEvent.Disconnected, () => reset(notice || "Conversa terminada."));
      await room.connect(data.url, data.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      setPhase((p) => (p === "live" ? p : "waiting"));
      timerRef.current = setTimeout(() => {
        setMessage("O avatar não responde: o agente está online (LiveKit Cloud)?");
      }, 60000);
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || "Erro";
      toast.error(detail);
      roomRef.current?.disconnect();
      reset(detail);
    }
  };

  const stop = async () => { await roomRef.current?.disconnect(); reset("Conversa terminada."); };

  const busy = phase === "connecting" || phase === "waiting";

  return (
    <div className="space-y-4" data-testid="admin-avatar-panel">
      <div>
        <h3 className="text-lg font-semibold">Assistente de vídeo da equipa</h3>
        <p className="text-sm text-muted-foreground">
          Uso interno apenas. Ensaiar o pitch do Web Summit, preparar respostas aos
          investidores, redigir mensagens. Não tem acesso aos dados em tempo real do site.
        </p>
      </div>

      {status && !status.configured && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm" data-testid="admin-avatar-not-configured">
          Não configurado: adicione LIVEKIT_URL, LIVEKIT_API_KEY e LIVEKIT_API_SECRET às variáveis do backend.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {(status?.langs || ["fr", "pt", "en"]).map((l) => (
          <Button key={l} type="button" size="sm" variant={lang === l ? "default" : "outline"}
            className="rounded-sm" disabled={phase !== "idle"} onClick={() => setLang(l)}
            data-testid={`admin-avatar-lang-${l}`}>
            {LANG_LABEL[l] || l}
          </Button>
        ))}
        {phase === "idle" ? (
          <Button type="button" className="rounded-sm" onClick={start}
            disabled={status && !status.configured} data-testid="admin-avatar-start">
            <Video className="mr-2 h-4 w-4" /> {{ pt: "Falar", en: "Talk" }[lang] || "Parler"}
          </Button>
        ) : (
          <Button type="button" variant="destructive" className="rounded-sm" onClick={stop}
            disabled={phase === "connecting"} data-testid="admin-avatar-stop">
            {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <PhoneOff className="mr-2 h-4 w-4" />}
            {{ pt: "Parar", en: "Stop" }[lang] || "Arrêter"}
          </Button>
        )}
      </div>

      <p className="text-sm text-muted-foreground" data-testid="admin-avatar-status">
        {message ||
          (phase === "connecting" ? "A ligar…" :
           phase === "waiting" ? "Ligado — o avatar está a chegar (até 60 s na primeira vez)…" :
           phase === "live" ? "Em direto — fale, o assistente está a ouvir." :
           "Clique em Falar e autorize o microfone.")}
      </p>

      <div ref={mediaRef} className="max-w-3xl" />
    </div>
  );
}
