import { useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { tm06ParaLatLon } from "@/lib/pttm06";

/**
 * Maquete 3D do distrito de Braga (edifícios, ruas, rios, relevo e PDM de Braga e Guimarães), em PT-TM06/ETRS89.
 * Aplicação estática em /public/braga3d (sem backend). Vindo da página Terrenos, recebe o limite do terreno
 * em PT-TM06 e mostra-o em 3D com a leitura do PDM municipal. Cada cartão da maquete (edifício, ponto, terreno ou obra)
 * tem um botão que abre o MDT Portugal nesse local; numa obra ou num terreno, com o respetivo polígono.
 */
export default function Maquete3DBraga() {
  const loc = useLocation();
  const navigate = useNavigate();
  const quadro = useRef(null);
  useEffect(() => {
    const ouvir = (e) => {
      if (e.origin !== window.location.origin || e.source !== quadro.current?.contentWindow) return;
      const d = e.data;
      if (!d || d.type !== "cp-abrir-mdt") return;
      const ok = (q) => Array.isArray(q) && q.length === 2 && q.every((v) => Number.isFinite(v));
      const local = `Maquete 3D Braga — ${String(d.nome || "local").slice(0, 120)}`;
      if (Array.isArray(d.anel_tm06) && d.anel_tm06.length >= 3 && d.anel_tm06.length <= 500 && d.anel_tm06.every(ok)) {
        navigate("/mdt", { state: { poligono: d.anel_tm06.map(([m, p]) => tm06ParaLatLon(m, p)), local } });
      } else if (ok(d.centro_tm06)) {
        navigate("/mdt", { state: { centro: tm06ParaLatLon(d.centro_tm06[0], d.centro_tm06[1]), local } });
      }
    };
    window.addEventListener("message", ouvir);
    return () => window.removeEventListener("message", ouvir);
  }, [navigate]);
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
      <iframe ref={quadro} title="Maquete 3D Braga" src={src} className="flex-1 w-full border-0" allow="clipboard-write; fullscreen" data-testid="maquete3d-iframe" />
    </div>
  );
}
