import { useMemo } from "react";
import { useLocation } from "react-router-dom";

/**
 * Maquete 3D do distrito de Braga (edifícios, ruas, rios, relevo e PDM de Braga e Guimarães), em PT-TM06/ETRS89.
 * Aplicação estática em /public/braga3d (sem backend). Vindo da página Terrenos, recebe o limite do terreno
 * em PT-TM06 e mostra-o em 3D com a leitura do PDM municipal.
 */
export default function Maquete3DBraga() {
  const loc = useLocation();
  const src = useMemo(() => {
    const anel = loc.state?.anel_tm06;
    const q = new URLSearchParams();
    if (Array.isArray(anel) && anel.length >= 3) {
      q.set("t", anel.map(([m, p]) => `${(+m).toFixed(2)},${(+p).toFixed(2)}`).join(";"));
      if (loc.state?.nome) q.set("nome", String(loc.state.nome).slice(0, 120));
    }
    const s = q.toString();
    return `/braga3d/braga3d.html${s ? `?${s}` : ""}`;
  }, [loc.state]);
  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] min-h-[520px]" data-testid="maquete3d-page">
      <div className="px-4 py-2 text-xs text-muted-foreground border-b">
        Maquete 3D do distrito de Braga — edifícios e ruas: OpenStreetMap e Microsoft Building Footprints (ODbL); relevo SRTM;
        PDM de Braga (3.ª revisão, 2026) e de Guimarães lidos automaticamente das plantas municipais. Não substitui o pedido de
        informação prévia à câmara.
      </div>
      <iframe title="Maquete 3D Braga" src={src} className="flex-1 w-full border-0" allow="clipboard-write; fullscreen" data-testid="maquete3d-iframe" />
    </div>
  );
}
