import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Play, Smartphone } from "lucide-react";
import { useI18n } from "@/context/I18nContext";

/**
 * MarketingTeaser — 20 s loop of the app in action, framed inside a mobile mockup.
 *
 * Video source: `/marketing-teaser.mp4` (dropped in `/app/frontend/public/`).
 * If missing, a friendly gradient fallback with a Play icon is shown.
 */
export function MarketingTeaser() {
  const { lang } = useI18n();
  const pt = lang === "pt";
  const [failed, setFailed] = useState(false);
  const videoRef = useRef(null);
  const VIDEO_URL =
    process.env.REACT_APP_MARKETING_VIDEO_URL || "/marketing-teaser.mp4";
  const POSTER_URL =
    process.env.REACT_APP_MARKETING_VIDEO_POSTER || "/marketing-teaser.jpg";

  // Autoplay fiable : React ne pose pas toujours l'attribut `muted` sur la balise
  // (bug connu) → Chrome bloque alors l'autoplay. On force muted + play() quand
  // la vidéo entre dans le viewport, et on met en pause hors écran (économie data).
  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    el.muted = true;
    el.play?.().catch(() => {});
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) el.play?.().catch(() => {});
        else el.pause?.();
      },
      { threshold: 0.25 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [failed]);

  return (
    <section
      className="mx-auto max-w-[1500px] px-6 lg:px-10 py-16 lg:py-24"
      data-testid="marketing-teaser"
    >
      <div className="grid lg:grid-cols-[1fr_auto] gap-12 items-center">
        {/* Left : copy */}
        <div>
          <div className="inline-flex items-center gap-2 text-primary text-xs font-bold uppercase tracking-widest mb-4">
            <Smartphone className="h-4 w-4" /> ConstruPilot Mobile
          </div>
          <h2 className="font-display text-3xl lg:text-5xl font-bold tracking-tight leading-tight">
            {pt ? "Orçamente uma obra" : "Chiffrez un chantier"} <br />
            <span className="text-primary italic">{pt ? "a partir da obra." : "depuis le chantier."}</span>
          </h2>
          <p className="mt-5 text-base text-muted-foreground max-w-md leading-relaxed">
            {pt
              ? "Tire uma foto da planta, descreva o projeto em voz alta e envie o orçamento assinado ao cliente — tudo em 30 s, sem sair da carrinha."
              : "Prenez une photo du plan, décrivez le projet à voix haute, envoyez le devis signé au client — le tout en 30 s, sans quitter le camion."}
          </p>
          <ul className="mt-8 grid gap-2 text-sm text-muted-foreground">
            {(pt
              ? ["Análise IA de estrutura em 8 s", "Render 3D fotorrealista (Nano Banana)", "Orçamento assinado + PDF enviado por e-mail"]
              : ["Analyse IA gros œuvre en 8 s", "Rendu 3D photoréaliste (Nano Banana)", "Devis signé + PDF envoyé par email"]
            ).map((f) => (
              <li key={f} className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" /> {f}
              </li>
            ))}
          </ul>
        </div>

        {/* Right : phone mockup with looping video */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.7 }}
          className="relative mx-auto"
        >
          <div
            className="relative rounded-[2.5rem] p-3 bg-gradient-to-b from-neutral-800 to-neutral-950 shadow-2xl"
            style={{ width: 280, height: 570 }}
          >
            {/* Notch */}
            <div className="absolute top-3 left-1/2 -translate-x-1/2 w-24 h-6 bg-neutral-950 rounded-b-2xl z-10" />
            {/* Screen */}
            <div className="relative w-full h-full rounded-[2rem] overflow-hidden bg-secondary">
              {!failed ? (
                <video
                  ref={videoRef}
                  src={VIDEO_URL}
                  poster={POSTER_URL}
                  autoPlay
                  muted
                  loop
                  playsInline
                  preload="auto"
                  onError={() => setFailed(true)}
                  className="w-full h-full object-cover"
                  data-testid="teaser-video"
                >
                  {pt ? "O seu navegador não suporta vídeo." : "Votre navigateur ne prend pas en charge la vidéo."}
                </video>
              ) : (
                <div
                  className="w-full h-full grid place-items-center bg-gradient-to-br from-primary/25 via-primary/10 to-secondary"
                  data-testid="teaser-fallback"
                >
                  <div className="text-center px-6">
                    <div className="h-16 w-16 mx-auto grid place-items-center rounded-full bg-primary/25">
                      <Play className="h-7 w-7 text-primary fill-primary" />
                    </div>
                    <p className="mt-4 font-display font-bold text-lg">
                      {pt ? "Pré-visualização da app" : "Aperçu de l'app"}
                    </p>
                    <p className="mt-2 text-xs text-muted-foreground">
                      {pt ? "Vídeo indisponível neste navegador" : "Vidéo indisponible sur ce navigateur"}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
          {/* Ambient glow */}
          <div
            aria-hidden
            className="absolute inset-0 -z-10 blur-3xl bg-primary/20 rounded-full"
          />
        </motion.div>
      </div>
    </section>
  );
}
