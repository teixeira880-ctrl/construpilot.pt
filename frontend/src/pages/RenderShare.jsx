import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Loader2, Wand2, AlertTriangle, MoveHorizontal } from "lucide-react";
import { API } from "@/lib/api";

function Comparator({ beforeSrc, afterSrc }) {
  const [pos, setPos] = useState(50);
  return (
    <div className="relative w-full rounded-xl overflow-hidden border border-white/10 select-none" data-testid="render-comparator">
      {/* Après (définit la hauteur) */}
      <img src={afterSrc} alt="após obra" className="w-full block pointer-events-none" />
      {/* Avant (superposé, rogné à droite) */}
      <img src={beforeSrc} alt="obra atual"
           className="absolute inset-0 w-full h-full object-cover pointer-events-none"
           style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
      {/* Ligne + poignée */}
      <div className="absolute top-0 bottom-0 w-0.5 bg-white/90 pointer-events-none" style={{ left: `${pos}%` }}>
        <span className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-9 w-9 rounded-full bg-white shadow grid place-items-center">
          <MoveHorizontal className="h-4 w-4 text-neutral-800" />
        </span>
      </div>
      <span className="absolute top-2 left-2 text-[11px] px-2 py-0.5 rounded bg-black/60 text-white">Hoje</span>
      <span className="absolute top-2 right-2 text-[11px] px-2 py-0.5 rounded bg-primary/80 text-white">Após trabalhos</span>
      <input type="range" min="0" max="100" value={pos} onChange={(e) => setPos(Number(e.target.value))}
             aria-label="Comparador antes depois" data-testid="render-comparator-slider"
             className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize" />
    </div>
  );
}

export default function RenderShare() {
  const { token } = useParams();
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/runway/public/${token}`)
      .then(({ data }) => setMeta(data))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [token]);

  const inputSrc = `${API}/runway/public/${token}/file?which=input`;
  const outputSrc = `${API}/runway/public/${token}/file?which=output`;

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100" data-testid="render-share-page">
      <header className="border-b border-white/10">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center gap-2">
          <span className="h-8 w-8 grid place-items-center rounded-lg bg-primary/20"><Wand2 className="h-4 w-4 text-primary" /></span>
          <span className="font-bold tracking-tight">ConstruPilot</span>
          <span className="ml-auto text-xs text-neutral-400">Renderização IA · Antes / Depois</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-10">
        {loading && <div className="py-24 text-center text-neutral-400"><Loader2 className="h-6 w-6 mx-auto animate-spin" /></div>}

        {!loading && error && (
          <div className="py-24 text-center" data-testid="render-share-error">
            <AlertTriangle className="h-8 w-8 mx-auto mb-3 text-amber-400" />
            <p className="text-neutral-300">Este link de partilha é inválido ou foi removido.</p>
          </div>
        )}

        {!loading && meta && (
          <div className="space-y-6">
            <div className="text-center">
              <h1 className="text-2xl sm:text-3xl font-bold">Projeto de renovação — projeção</h1>
              <p className="text-neutral-400 mt-1 text-sm">Visualização gerada por inteligência artificial</p>
            </div>

            {meta.kind === "video" ? (
              <div className="grid md:grid-cols-2 gap-6">
                <figure className="space-y-2">
                  <figcaption className="text-xs uppercase tracking-wide text-neutral-400">Hoje</figcaption>
                  <img src={inputSrc} alt="obra atual" className="w-full rounded-xl border border-white/10" data-testid="render-share-before" />
                </figure>
                <figure className="space-y-2">
                  <figcaption className="text-xs uppercase tracking-wide text-primary">Após trabalhos</figcaption>
                  <video src={outputSrc} controls autoPlay loop muted className="w-full rounded-xl border border-primary/30" data-testid="render-share-after" />
                </figure>
              </div>
            ) : (
              <div className="space-y-2">
                <Comparator beforeSrc={inputSrc} afterSrc={outputSrc} />
                <p className="text-center text-xs text-neutral-500 flex items-center justify-center gap-1.5">
                  <MoveHorizontal className="h-3.5 w-3.5" /> Arraste o cursor para comparar antes / depois
                </p>
                {/* balises de test conservées */}
                <img src={inputSrc} alt="avant" className="hidden" data-testid="render-share-before" />
                <img src={outputSrc} alt="após" className="hidden" data-testid="render-share-after" />
              </div>
            )}

            {meta.prompt && (
              <p className="text-center text-sm text-neutral-400 max-w-2xl mx-auto">« {meta.prompt} »</p>
            )}

            <p className="text-center text-xs text-neutral-500 max-w-xl mx-auto pt-4 border-t border-white/10">
              Visualização indicativa gerada por IA, sem valor contratual nem técnico. O resultado final pode diferir consoante os materiais e constrangimentos da obra.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
