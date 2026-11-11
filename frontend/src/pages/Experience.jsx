import { useEffect } from "react";

/* ConstruPilot Experience (/experiencia): filme 3D + diagnóstico por profissão + estimativa de ganho.
   A página é autónoma (public/cp-experience/index.html, sem dependências do bundle) e é mostrada
   aqui em ecrã inteiro. O pedido final é enviado para POST /api/experience/lead. */
export default function Experience() {
  useEffect(() => {
    const previous = document.title;
    document.title = "ConstruPilot Experience";
    return () => { document.title = previous; };
  }, []);
  return (
    <iframe
      title="ConstruPilot Experience"
      data-testid="experience-frame"
      src={`/cp-experience/index.html${window.location.search || ""}`}
      style={{ position: "fixed", inset: 0, width: "100%", height: "100%", border: 0, zIndex: 40, background: "#03060b" }}
    />
  );
}
