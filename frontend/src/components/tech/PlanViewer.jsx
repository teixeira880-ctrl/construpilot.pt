import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function PlanViewer({ planId, highlight }) {
  const [img, setImg] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!planId) { setImg(null); return; }
    setLoading(true);
    api.get(`/takeoffs/${planId}/page/0`)
      .then(({ data }) => setImg(data.image_png_b64 || null))
      .catch(() => setImg(null))
      .finally(() => setLoading(false));
  }, [planId]);

  if (!planId) return null;
  return (
    <div className="surface p-3" data-testid="plan-viewer">
      <div className="relative inline-block max-w-full leading-none">
        {img ? (
          <img src={`data:image/png;base64,${img}`} alt="Plan" className="max-w-full rounded-sm border border-border" />
        ) : (
          <div className="text-sm text-muted-foreground p-8">{loading ? "Chargement de l'aperçu…" : "Aperçu du plan indisponible"}</div>
        )}
        {img && highlight && Array.isArray(highlight) && (
          <div className="absolute border-2 border-primary bg-primary/25 rounded-sm pointer-events-none shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
            data-testid="plan-highlight"
            style={{
              left: `${Math.max(0, highlight[0]) * 100}%`,
              top: `${Math.max(0, highlight[1]) * 100}%`,
              width: `${Math.max(0, highlight[2] - highlight[0]) * 100}%`,
              height: `${Math.max(0, highlight[3] - highlight[1]) * 100}%`,
              transition: "left .2s, top .2s, width .2s, height .2s",
            }} />
        )}
      </div>
      {img && (
        <p className="text-xs text-muted-foreground mt-2">
          {highlight ? "🟧 Élément surligné — cliquez une autre ligne du bordereau pour la localiser." : "Cliquez une ligne du bordereau pour la localiser sur le plan."}
        </p>
      )}
    </div>
  );
}
