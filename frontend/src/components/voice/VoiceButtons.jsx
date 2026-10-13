import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Mic, Square, Volume2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

/** Bouton « Écouter » : synthèse vocale managée Emergent (mp3), lecture/arrêt. `request` permet un client axios différent (portail). */
export function ListenButton({ text, request, className = "", testId = "listen-btn", label = "Écouter" }) {
  const [state, setState] = useState("idle");
  const audioRef = useRef(null);
  useEffect(() => () => { audioRef.current?.pause(); if (audioRef.current?.src) URL.revokeObjectURL(audioRef.current.src); }, []);
  const stop = () => { audioRef.current?.pause(); setState("idle"); };
  const play = async () => {
    if (state === "playing") return stop();
    if (!text?.trim()) return;
    setState("loading");
    try {
      const fn = request || ((body) => api.post("/speech/tts", body, { responseType: "blob" }));
      const { data } = await fn({ text: text.slice(0, 4000) });
      const url = URL.createObjectURL(data);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { setState("idle"); URL.revokeObjectURL(url); };
      audio.onerror = () => { setState("idle"); toast.error("Lecture impossible"); };
      await audio.play();
      setState("playing");
    } catch { setState("idle"); toast.error("Synthèse vocale indisponible"); }
  };
  const Icon = state === "loading" ? Loader2 : state === "playing" ? Square : Volume2;
  return (
    <button type="button" onClick={play} disabled={state === "loading"} data-testid={testId} aria-pressed={state === "playing"} title={state === "playing" ? "Arrêter" : label}
      className={`inline-flex items-center gap-1 text-xs rounded-sm border px-2 py-1 hover:bg-muted transition-colors disabled:opacity-60 ${className}`}>
      <Icon className={`h-3.5 w-3.5 ${state === "loading" ? "animate-spin" : ""}`} /> {state === "playing" ? "Arrêter" : label}
    </button>
  );
}

/** Bouton « Dicter » : enregistre le micro puis transcrit via la STT managée Emergent ; `onText(texte)` reçoit la transcription. `request(formData)` permet un client différent (portail). */
export function DictateButton({ onText, request, testId = "dictate-btn", className = "", label = "Dicter" }) {
  const [state, setState] = useState("idle");
  const recRef = useRef(null);
  const chunks = useRef([]);
  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia) return toast.error("Micro non disponible sur cet appareil");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4";
      const rec = new MediaRecorder(stream, { mimeType: mime });
      chunks.current = [];
      rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setState("transcribing");
        try {
          const blob = new Blob(chunks.current, { type: mime });
          const fd = new FormData();
          fd.append("file", blob, mime.includes("webm") ? "dictee.webm" : "dictee.mp4");
          const fn = request || ((f) => api.post("/speech/transcribe", f));
          const { data } = await fn(fd);
          if (data.text) onText(data.text); else toast.message("Rien n'a été compris, réessayez");
        } catch (e) { toast.error(e?.response?.data?.detail || "Transcription impossible"); }
        finally { setState("idle"); }
      };
      rec.start();
      recRef.current = rec;
      setState("recording");
    } catch { toast.error("Accès au micro refusé"); }
  };
  const stop = () => recRef.current?.state === "recording" && recRef.current.stop();
  const Icon = state === "transcribing" ? Loader2 : state === "recording" ? Square : Mic;
  return (
    <button type="button" onClick={state === "recording" ? stop : start} disabled={state === "transcribing"} data-testid={testId} aria-pressed={state === "recording"}
      className={`inline-flex items-center gap-1 text-xs rounded-sm border px-2 py-1 transition-colors disabled:opacity-60 ${state === "recording" ? "bg-red-500/10 border-red-500/40 text-red-600 animate-pulse" : "hover:bg-muted"} ${className}`}>
      <Icon className={`h-3.5 w-3.5 ${state === "transcribing" ? "animate-spin" : ""}`} /> {state === "recording" ? "Terminer" : state === "transcribing" ? "Transcription…" : label}
    </button>
  );
}
