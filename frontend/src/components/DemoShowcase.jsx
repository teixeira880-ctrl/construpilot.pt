import { useEffect, useRef, useState } from "react";
import { Play, Download, Film, Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";

export const DemoShowcase = () => {
  const [data, setData] = useState(null);
  const [active, setActive] = useState(0);
  const [muted, setMuted] = useState(true);
  const videoRef = useRef(null);

  useEffect(() => {
    fetch("/demo/demo.json").then((r) => r.ok ? r.json() : null).then(setData).catch(() => {});
  }, []);

  if (!data?.chapters?.length) return null;

  const seekTo = (i) => {
    setActive(i);
    const v = videoRef.current;
    if (v) { v.currentTime = (data.chapters[i].start ?? 0) + 0.05; v.play().catch(() => {}); }
  };

  const onTime = () => {
    const t = videoRef.current?.currentTime || 0;
    let idx = 0;
    for (let i = 0; i < data.chapters.length; i++) if (t >= (data.chapters[i].start ?? 0)) idx = i;
    if (idx !== active) setActive(idx);
  };

  const toggleSound = () => {
    const v = videoRef.current;
    if (!v) return;
    const next = !muted;
    v.muted = next;
    setMuted(next);
    if (!next) v.play().catch(() => {});
  };

  return (
    <section className="max-w-6xl mx-auto px-5 w-full py-14" data-testid="demo-showcase">
      <div className="text-center mb-8">
        <p className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center justify-center gap-2">
          <Film className="h-4 w-4" /> Visita guiada
        </p>
        <h2 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight mt-2">
          Descubra o ConstruPilot em vídeo
        </h2>
        <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
          Uma demonstração narrada de todas as funções — clique num capítulo para lá aceder diretamente.
        </p>
      </div>

      <div className="grid lg:grid-cols-[1fr_320px] gap-6 items-start">
        <div className="rounded-xl overflow-hidden border border-border bg-black shadow-lg relative group">
          <video
            ref={videoRef}
            src={data.video}
            controls
            autoPlay
            muted
            loop
            playsInline
            onTimeUpdate={onTime}
            onCanPlay={() => videoRef.current?.play().catch(() => {})}
            className="w-full aspect-video bg-black"
            data-testid="demo-video"
          />
          <button
            onClick={toggleSound}
            data-testid="demo-sound-toggle"
            className="absolute top-3 left-3 inline-flex items-center gap-2 rounded-full bg-primary text-primary-foreground text-xs font-semibold px-3.5 py-2 shadow-lg hover:scale-105 transition-transform"
          >
            {muted ? <><Volume2 className="h-4 w-4" /> Ativar o som</> : <><VolumeX className="h-4 w-4" /> Cortar o som</>}
          </button>
        </div>

        <div className="grid gap-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">Chapitres</p>
            <a href={data.video} download data-testid="demo-download"
               className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary hover:underline">
              <Download className="h-3.5 w-3.5" /> Transferir (MP4)
            </a>
          </div>
          <div className="grid gap-1.5 max-h-[430px] overflow-auto pr-1">
            {data.chapters.map((c, i) => (
              <button
                key={c.key}
                onClick={() => seekTo(i)}
                data-testid={`demo-chapter-${c.key}`}
                className={`text-left rounded-lg border p-2.5 flex items-center gap-3 transition-colors ${
                  active === i ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                }`}
              >
                <span className={`h-8 w-8 shrink-0 grid place-items-center rounded-full text-xs font-bold ${
                  active === i ? "bg-primary text-primary-foreground" : "bg-secondary"
                }`}>
                  {active === i ? <Play className="h-3.5 w-3.5" /> : i + 1}
                </span>
                <span className="min-w-0">
                  <span className="block text-sm font-medium truncate">{c.title}</span>
                  <span className="block text-[11px] text-muted-foreground">{Math.round(c.start || 0)} s</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default DemoShowcase;
