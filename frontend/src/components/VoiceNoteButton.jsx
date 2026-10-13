import { useRef, useState } from "react";
import { Mic, Square, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function VoiceNoteButton({ onText, size = "sm", className = "", label = "Dicter" }) {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [secs, setSecs] = useState(0);
  const recRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  const stop = () => {
    recRef.current?.state !== "inactive" && recRef.current?.stop();
    clearInterval(timerRef.current);
    setRecording(false);
  };

  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia) { toast.error("Microfone não disponível neste dispositivo"); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "audio/webm" });
        if (blob.size < 2000) { toast.error("Enregistrement trop court"); return; }
        setBusy(true);
        try {
          const fd = new FormData();
          fd.append("file", blob, "note-vocale.webm");
          const { data } = await api.post("/documents/video-transcribe", fd, { timeout: 120000 });
          if (data.transcript?.trim()) { onText?.(data.transcript.trim()); toast.success("Note vocale transcrite"); }
          else toast.error("Nenhuma fala detetada");
        } catch (e) {
          toast.error(e?.response?.data?.detail || "Transcrição impossível");
        } finally { setBusy(false); }
      };
      recRef.current = rec;
      rec.start();
      setSecs(0);
      timerRef.current = setInterval(() => setSecs((s) => {
        if (s + 1 >= 120) stop();
        return s + 1;
      }), 1000);
      setRecording(true);
    } catch {
      toast.error("Acesso ao microfone recusado");
    }
  };

  return (
    <Button type="button" size={size} variant={recording ? "destructive" : "outline"}
            onClick={recording ? stop : start} disabled={busy}
            className={`rounded-sm gap-2 ${className}`} data-testid="voice-note-btn"
            title="Dite a sua obra: a IA transcreve a sua nota de voz">
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
      {busy ? "Transcription…" : recording ? `Stop · ${secs}s` : label}
    </Button>
  );
}
