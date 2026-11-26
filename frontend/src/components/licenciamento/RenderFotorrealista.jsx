import { useEffect, useRef, useState } from "react";
import { Sparkles, Loader2, Download, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { errorText } from "@/lib/errorText";
import { promptDoModelo } from "./promptRender";

// Render fotorrealista com um clique: captura a vista 3D do Estúdio tal como está (geometria, enquadramento, sol) e
// envia-a ao serviço de imagem do ConstruPilot (/api/runway/generate — Runway gen4_image, imagem de referência exata).
// O texto do pedido é escrito a partir do próprio modelo: materiais da fachada, cobertura, caixilharia, exteriores.

const T = {
  pt: { botao: "Render fotorrealista (IA)", gerar: "A gerar o render…", demora: "Demora cerca de 1 minuto. Pode continuar a trabalhar.",
        titulo: "Render fotorrealista", antes: "Vista 3D", depois: "Render", baixar: "Descarregar", fechar: "Fechar", erro: "O render falhou." },
  fr: { botao: "Rendu photoréaliste (IA)", gerar: "Rendu en cours…", demora: "Environ 1 minute. Vous pouvez continuer à travailler.",
        titulo: "Rendu photoréaliste", antes: "Vue 3D", depois: "Rendu", baixar: "Télécharger", fechar: "Fermer", erro: "Le rendu a échoué." },
  en: { botao: "Photoreal render (AI)", gerar: "Rendering…", demora: "About 1 minute. You can keep working.",
        titulo: "Photoreal render", antes: "3D view", depois: "Render", baixar: "Download", fechar: "Close", erro: "The render failed." },
};

export default function RenderFotorrealista({ capturar, derivado, lang = "pt" }) {
  const t = T[lang] || T.pt;
  const [estado, setEstado] = useState(null);       // null | "gerar" | "pronto" | "erro"
  const [erro, setErro] = useState("");
  const [urls, setUrls] = useState({ antes: null, depois: null });
  const vivo = useRef(true);
  useEffect(() => () => {
    vivo.current = false;
    Object.values(urls).forEach((u) => u && URL.revokeObjectURL(u));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const gerar = async () => {
    setErro(""); setEstado("gerar");
    try {
      const blob = await capturar();
      if (!blob) throw new Error(t.erro);
      const antes = URL.createObjectURL(blob);
      setUrls({ antes, depois: null });
      const fd = new FormData();
      fd.append("file", blob, "vista-3d.jpg");
      fd.append("prompt", promptDoModelo(derivado));
      fd.append("kind", "image");
      fd.append("ratio", "1280:720");
      const { data } = await api.post("/runway/generate", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const id = data.render_id;
      const fim = Date.now() + 6 * 60 * 1000;
      while (vivo.current && Date.now() < fim) {
        await new Promise((r) => setTimeout(r, 4000));
        const { data: d } = await api.get(`/runway/renders/${id}`);
        if (d.status === "failed") throw new Error(d.error || t.erro);
        if (d.status === "done" && d.has_output) {
          const { data: img } = await api.get(`/runway/renders/${id}/file`, { responseType: "blob" });
          if (!vivo.current) return;
          setUrls({ antes, depois: URL.createObjectURL(img) });
          setEstado("pronto");
          return;
        }
      }
      throw new Error(t.erro);
    } catch (e) {
      if (!vivo.current) return;
      setErro(errorText(e, t.erro)); setEstado("erro");
    }
  };

  const aberto = estado === "pronto" || estado === "erro" || (estado === "gerar" && !!urls.antes);
  return (
    <>
      <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={gerar} disabled={estado === "gerar"} data-testid="estudio-3d-render-ia">
        {estado === "gerar" ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 mr-1" />}
        {estado === "gerar" ? t.gerar : t.botao}
      </Button>
      {aberto ? (
        <div className="fixed inset-0 z-50 bg-black/60 grid place-items-center p-4" data-testid="estudio-3d-render-painel">
          <div className="bg-card rounded-2xl shadow-2xl max-w-5xl w-full p-4 space-y-3">
            <div className="flex items-center justify-between">
              <p className="font-semibold">{t.titulo}</p>
              <Button size="icon" variant="ghost" onClick={() => setEstado(null)} aria-label={t.fechar}><X className="h-4 w-4" /></Button>
            </div>
            {estado === "erro" && <p className="text-sm text-red-700">{erro}</p>}
            <div className="grid gap-3 md:grid-cols-2">
              {urls.antes && <figure><img src={urls.antes} alt={t.antes} className="rounded-lg w-full" /><figcaption className="text-xs text-muted-foreground mt-1">{t.antes}</figcaption></figure>}
              <figure className="grid place-items-center min-h-48 rounded-lg bg-secondary/40">
                {urls.depois ? <img src={urls.depois} alt={t.depois} className="rounded-lg w-full" />
                  : estado === "gerar" ? <p className="text-sm text-muted-foreground flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" />{t.demora}</p> : null}
                {urls.depois && <figcaption className="text-xs text-muted-foreground mt-1">{t.depois}</figcaption>}
              </figure>
            </div>
            {urls.depois && (
              <div className="flex justify-end">
                <Button size="sm" asChild><a href={urls.depois} download="render-construpilot.png"><Download className="h-4 w-4 mr-1" />{t.baixar}</a></Button>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </>
  );
}
