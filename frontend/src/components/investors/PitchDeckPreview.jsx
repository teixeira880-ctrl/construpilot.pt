import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Download, Loader2, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { deckSlideUrl } from "@/lib/pitchDeck";

export const PitchDeckPreview = ({ onDownload }) => {
  const [info, setInfo] = useState(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState(false);
  const [imageState, setImageState] = useState("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setError(false);
    api.get("/investors/pitch-deck").then(({ data }) => {
      if (active) setInfo(data);
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [attempt]);

  const changePage = (value) => { setImageState("loading"); setPage(value); };
  const imageUrl = info && deckSlideUrl(page, `${info.source_sha256}-${attempt}`);

  return (
    <section id="pitch-deck" data-testid="pitch-deck-preview" className="border-b border-border scroll-mt-32">
      <div className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-10 py-10 sm:py-14">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <h2 className="font-display text-base md:text-lg font-bold" data-testid="pitch-deck-preview-title">Pitch deck ConstruPilot</h2>
          <div className="flex flex-wrap gap-2">
            {["pdf", "pptx"].map((format) => (
              <Button key={format} size="sm" variant="outline" className="gap-2 rounded-full"
                data-testid={`pitch-deck-download-${format}`} onClick={() => onDownload(format)}>
                <Download className="h-4 w-4" /> {format === "pdf" ? "PDF" : "PowerPoint"}
              </Button>
            ))}
          </div>
        </div>
        {error ? (
          <div role="alert" data-testid="pitch-deck-load-error" className="py-10 text-center space-y-4">
            <p>La présentation n’a pas pu être chargée.</p>
            <Button variant="outline" data-testid="pitch-deck-retry" onClick={() => setAttempt((v) => v + 1)}><RotateCcw className="h-4 w-4 mr-2" />Réessayer</Button>
          </div>
        ) : !info ? (
          <div role="status" data-testid="pitch-deck-loading" className="aspect-video grid place-items-center"><Loader2 className="animate-spin" aria-label="Chargement" /></div>
        ) : (
          <>
            <div className="relative aspect-video bg-secondary/20 border border-border">
              {imageState === "loading" && <div role="status" data-testid="pitch-deck-slide-loading" className="absolute inset-0 grid place-items-center pointer-events-none"><Loader2 className="animate-spin" aria-label="Chargement" /></div>}
              {imageState === "error" ? (
                <div role="alert" data-testid="pitch-deck-image-error" className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-3 text-sm text-center">
                  <p>Diapositive indisponible.</p>
                  <Button variant="outline" size="sm" data-testid="pitch-deck-image-retry" onClick={() => { setImageState("loading"); setAttempt((v) => v + 1); }}>Réessayer</Button>
                </div>
              ) : (
                <a href={imageUrl} target="_blank" rel="noopener noreferrer" title="Agrandir la diapositive" data-testid="pitch-deck-enlarge" className="block h-full w-full">
                  <img key={imageUrl} src={imageUrl} alt={`ConstruPilot — diapositive ${page} sur ${info.page_count}`} width={info.width} height={info.height}
                    data-testid="pitch-deck-slide-image" onLoad={() => setImageState("loaded")} onError={() => setImageState("error")}
                    className="h-full w-full object-contain" />
                </a>
              )}
            </div>
            <div className="flex flex-wrap justify-center items-center gap-3 mt-4">
              <Button size="icon" variant="outline" title="Diapositive précédente" aria-label="Diapositive précédente" data-testid="pitch-deck-prev" disabled={page === 1} onClick={() => changePage(page - 1)}><ChevronLeft className="h-4 w-4" /></Button>
              <select aria-label="Choisir une diapositive" data-testid="pitch-deck-slide-select" value={page} onChange={(e) => changePage(Number(e.target.value))} className="h-10 max-w-full rounded-md border border-input bg-background px-3 text-sm">
                {Array.from({ length: info.page_count }, (_, i) => <option key={i + 1} value={i + 1}>{`Diapositive ${i + 1} / ${info.page_count}`}</option>)}
              </select>
              <Button size="icon" variant="outline" title="Diapositive suivante" aria-label="Diapositive suivante" data-testid="pitch-deck-next" disabled={page === info.page_count} onClick={() => changePage(page + 1)}><ChevronRight className="h-4 w-4" /></Button>
              <span className="sr-only" role="status" data-testid="pitch-deck-page-status">{page} / {info.page_count}</span>
            </div>
          </>
        )}
      </div>
    </section>
  );
};