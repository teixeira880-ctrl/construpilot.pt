import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Loader2, Wand2, AlertTriangle } from "lucide-react";
import { API } from "@/lib/api";

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
          <span className="ml-auto text-xs text-neutral-400">Rendu IA · Avant / Après</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-10">
        {loading && <div className="py-24 text-center text-neutral-400"><Loader2 className="h-6 w-6 mx-auto animate-spin" /></div>}

        {!loading && error && (
          <div className="py-24 text-center" data-testid="render-share-error">
            <AlertTriangle className="h-8 w-8 mx-auto mb-3 text-amber-400" />
            <p className="text-neutral-300">Ce lien de partage est invalide ou a été retiré.</p>
          </div>
        )}

        {!loading && meta && (
          <div className="space-y-6">
            <div className="text-center">
              <h1 className="text-2xl sm:text-3xl font-bold">Projet de rénovation — projection</h1>
              <p className="text-neutral-400 mt-1 text-sm">Visualisation générée par intelligence artificielle</p>
            </div>

            <div className="grid md:grid-cols-2 gap-6">
              <figure className="space-y-2">
                <figcaption className="text-xs uppercase tracking-wide text-neutral-400">Aujourd'hui</figcaption>
                <img src={inputSrc} alt="chantier actuel" className="w-full rounded-xl border border-white/10" data-testid="render-share-before" />
              </figure>
              <figure className="space-y-2">
                <figcaption className="text-xs uppercase tracking-wide text-primary">Après travaux</figcaption>
                {meta.kind === "video" ? (
                  <video src={outputSrc} controls autoPlay loop muted className="w-full rounded-xl border border-primary/30" data-testid="render-share-after" />
                ) : (
                  <img src={outputSrc} alt="rendu après travaux" className="w-full rounded-xl border border-primary/30" data-testid="render-share-after" />
                )}
              </figure>
            </div>

            {meta.prompt && (
              <p className="text-center text-sm text-neutral-400 max-w-2xl mx-auto">« {meta.prompt} »</p>
            )}

            <p className="text-center text-xs text-neutral-500 max-w-xl mx-auto pt-4 border-t border-white/10">
              Visualisation indicative générée par IA, sans valeur contractuelle ni technique.
              Le rendu final peut différer selon les matériaux et contraintes du chantier.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
