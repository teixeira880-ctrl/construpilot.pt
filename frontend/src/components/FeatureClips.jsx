import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Film, Clock } from "lucide-react";

// rend un texte avec **gras** markdown simple
const RichText = ({ text }) =>
  text.split("**").map((part, i) =>
    i % 2 === 1 ? <strong key={i} className="text-foreground font-semibold">{part}</strong> : <span key={i}>{part}</span>
  );

export const FeatureClips = ({ title = "Cada função em vídeo", subtitle = "Demos curtas e reais, narradas, com uma explicação detalhada de cada ferramenta.", keys = null }) => {
  const [features, setFeatures] = useState([]);

  useEffect(() => {
    fetch("/demo/features.json").then((r) => (r.ok ? r.json() : null)).then((d) => setFeatures(d?.features || [])).catch(() => {});
  }, []);

  let list = features;
  if (keys && keys.length) {
    const byKey = Object.fromEntries(features.map((f) => [f.key, f]));
    list = keys.map((k) => byKey[k]).filter(Boolean);
  }
  if (!list.length) return null;

  return (
    <section className="max-w-6xl mx-auto px-4 py-14 w-full" data-testid="feature-clips">
      <div className="text-center mb-10">
        <p className="text-xs uppercase tracking-widest text-primary font-semibold flex items-center justify-center gap-2">
          <Film className="h-4 w-4" /> Função a função
        </p>
        <h2 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight mt-2">{title}</h2>
        <p className="text-sm text-muted-foreground mt-3 max-w-2xl mx-auto">{subtitle}</p>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        {list.map((f) => (
          <article
            key={f.key}
            data-testid={`feature-clip-${f.key}`}
            onMouseEnter={(e) => { const v = e.currentTarget.querySelector("video"); if (v) { v.muted = true; v.play().catch(() => {}); } }}
            onMouseLeave={(e) => { const v = e.currentTarget.querySelector("video"); if (v) { v.pause(); } }}
            className="rounded-xl border border-border bg-card overflow-hidden flex flex-col transition-all hover:border-primary/50 hover:shadow-lg"
          >
            <div className="bg-black relative">
              <video
                src={f.clip}
                poster={f.poster}
                controls
                muted
                playsInline
                preload="metadata"
                className="w-full aspect-video bg-black"
                data-testid={`feature-clip-video-${f.key}`}
              />
              <span className="absolute top-2 right-2 inline-flex items-center gap-1 rounded-full bg-black/70 text-white text-[11px] font-semibold px-2 py-0.5 backdrop-blur">
                <Clock className="h-3 w-3" /> {Math.round(f.duration)} s
              </span>
            </div>
            <div className="p-5 flex flex-col gap-3 flex-1">
              <h3 className="font-display text-lg font-bold">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed flex-1">
                <RichText text={f.description} />
              </p>
              <Link
                to={f.route}
                data-testid={`feature-clip-cta-${f.key}`}
                className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:gap-2.5 transition-all self-start"
              >
                Abrir a função <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
};

export default FeatureClips;
