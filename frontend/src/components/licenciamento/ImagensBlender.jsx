import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Camera, Download, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

/* Imagens do projeto feitas no Blender (Cycles) sobre o ortofotomapa oficial: antes / depois por vista,
   versão Blender pura e versão com acabamento fotográfico (geometria bloqueada), modelo 3D georreferenciado. */

function useBlob(path) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    if (!path) return undefined;
    let vivo = true, u = null;
    setUrl(null);
    api.get(path, { responseType: "blob", timeout: 120000 }).then(r => { if (!vivo) return; u = URL.createObjectURL(r.data); setUrl(u); }).catch(() => {});
    return () => { vivo = false; if (u) URL.revokeObjectURL(u); };
  }, [path]);
  return url;
}

function AntesDepois({ antes, depois, titulo }) {
  const [pos, setPos] = useState(50);
  const ref = useRef(null);
  const mover = (clientX) => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  };
  if (!depois) return <div className="w-full aspect-video bg-muted animate-pulse rounded" />;
  return (
    <div ref={ref} className="relative w-full aspect-video overflow-hidden rounded select-none touch-none cursor-ew-resize bg-muted"
         onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); mover(e.clientX); }}
         onPointerMove={e => { if (e.buttons) mover(e.clientX); }} data-testid="blender-antes-depois">
      <img src={depois} alt={`${titulo} — proposta`} className="absolute inset-0 w-full h-full object-cover" draggable={false} />
      {antes && (
        <div className="absolute inset-0 overflow-hidden" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          <img src={antes} alt={`${titulo} — situação existente`} className="absolute inset-0 w-full h-full object-cover" draggable={false} />
        </div>
      )}
      {antes && <>
        <div className="absolute top-0 bottom-0 w-0.5 bg-white shadow" style={{ left: `${pos}%` }} />
        <span className="absolute left-2 top-2 rounded bg-black/60 text-white text-[11px] px-2 py-0.5">Antes</span>
        <span className="absolute right-2 top-2 rounded bg-black/60 text-white text-[11px] px-2 py-0.5">Depois</span>
      </>}
    </div>
  );
}

function Vista({ pid, camara, imgs, versao }) {
  const pick = (estado) => imgs.find(i => i.estado === estado && i.versao === versao) || imgs.find(i => i.estado === estado && i.versao === "blender");
  const a = pick("antes"), d = pick("depois");
  const base = `/urbanismo-auto/processos/${pid}/blender/`;
  const ua = useBlob(a ? base + a.ficheiro : null);
  const ud = useBlob(d ? base + d.ficheiro : null);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm font-medium">
        {d?.titulo}
        {d?.versao === "foto" ? <Badge variant="secondary" className="text-[10px]">Blender + acabamento fotográfico</Badge>
          : <Badge variant="outline" className="text-[10px]">Render Blender (Cycles)</Badge>}
      </div>
      <AntesDepois antes={ua} depois={ud} titulo={d?.titulo || camara} />
      {ud && <a href={ud} download={d.ficheiro} className="text-xs text-muted-foreground underline">Descarregar imagem</a>}
    </div>
  );
}

const QUAL = { rapido: "Rápido (pré-visualização)", normal: "Normal (Full HD)", alta: "Alta (2,5K, mais lento)" };

export default function ImagensBlender({ pid }) {
  const [st, setSt] = useState(null);
  const [versao, setVersao] = useState("foto");
  const [qual, setQual] = useState("normal");
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true, t;
    const ler = async () => {
      let espera = 8000;
      try {
        const { data } = await api.get(`/urbanismo-auto/processos/${pid}/blender`);
        if (!vivo) return;
        setSt(data);
        if (data.estado === "a_renderizar") espera = 4000; else espera = 30000;
      } catch { /* tenta de novo */ }
      if (vivo) t = setTimeout(ler, espera);
    };
    ler();
    return () => { vivo = false; clearTimeout(t); };
  }, [pid]);

  const lancar = async () => {
    setErro(null);
    try {
      await api.post(`/urbanismo-auto/processos/${pid}/blender`, { qualidade: qual, acabamento: true });
      setSt(s => ({ ...(s || {}), estado: "a_renderizar", etapa: "Na fila" }));
    } catch (e) { setErro(e?.response?.data?.detail || "Não foi possível arrancar o Blender."); }
  };

  const camaras = useMemo(() => {
    const m = new Map();
    for (const i of st?.imagens || []) { if (!m.has(i.camara)) m.set(i.camara, []); m.get(i.camara).push(i); }
    return [...m.entries()];
  }, [st]);
  const temFotos = (st?.imagens || []).some(i => i.versao === "foto");
  const a_render = st?.estado === "a_renderizar";

  return (
    <Card className="p-4 space-y-4" data-testid="lic-auto-blender">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="font-medium flex items-center gap-2"><Camera className="h-4 w-4" />Imagens do projeto — Blender, antes / depois</div>
          <p className="text-xs text-muted-foreground">Render real no Blender (Cycles) com a geometria exata do processo, sobre o ortofotomapa oficial e com o sol na posição real.
            O acabamento fotográfico só trabalha a textura e a luz: a casa, a câmara e o terreno ficam bloqueados.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {temFotos && (
            <div className="inline-flex rounded-md border overflow-hidden text-xs" role="tablist">
              {[["foto", "Acabamento fotográfico"], ["blender", "Blender puro"]].map(([k, l]) => (
                <button key={k} type="button" onClick={() => setVersao(k)} className={`px-2.5 py-1.5 ${versao === k ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>{l}</button>
              ))}
            </div>
          )}
          <select value={qual} onChange={e => setQual(e.target.value)} className="h-8 rounded-md border bg-background px-2 text-xs" aria-label="Qualidade">
            {Object.entries(QUAL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
          <Button size="sm" onClick={lancar} disabled={a_render || st?.blender_instalado === false} data-testid="lic-auto-blender-gerar">
            {a_render ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            {st?.imagens?.length ? "Gerar de novo" : "Gerar imagens"}
          </Button>
        </div>
      </div>

      {st?.blender_instalado === false && <p className="text-sm text-amber-700">O Blender ainda não está instalado neste servidor.</p>}
      {erro && <p className="text-sm text-destructive">{erro}</p>}
      {a_render && (
        <p className="text-sm text-blue-700 flex items-center gap-2" data-testid="lic-auto-blender-estado">
          <Loader2 className="h-4 w-4 animate-spin" />{st.etapa || "A renderizar"}… (alguns minutos; pode sair da página)
        </p>
      )}
      {st?.estado === "erro" && <p className="text-sm text-destructive">O Blender falhou: {st.motivo}</p>}
      {st?.estado === "interrompido" && <p className="text-sm text-amber-700">O trabalho foi interrompido (reinício do servidor). Carregue em «Gerar de novo».</p>}
      {st?.acabamento_falhou && <p className="text-xs text-amber-700">O acabamento fotográfico não respondeu: ficam as imagens do Blender.</p>}

      {camaras.length > 0 && (
        <div className="grid md:grid-cols-2 gap-4">
          {camaras.map(([cam, imgs]) => <Vista key={cam} pid={pid} camara={cam} imgs={imgs} versao={versao} />)}
        </div>
      )}

      {(st?.ficheiros || []).length > 0 && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <span className="text-xs font-medium flex items-center gap-1"><Box className="h-3.5 w-3.5" />Modelo 3D georreferenciado (ETRS89 / PT-TM06):</span>
          {st.ficheiros.map(n => (
            <Button key={n} size="sm" variant="outline" onClick={async () => {
              const r = await api.get(`/urbanismo-auto/processos/${pid}/blender/${n}`, { responseType: "blob", timeout: 180000 });
              const u = URL.createObjectURL(r.data); const a = document.createElement("a"); a.href = u; a.download = n; a.click(); setTimeout(() => URL.revokeObjectURL(u), 4000);
            }}><Download className="h-3.5 w-3.5 mr-1" />{n}</Button>
          ))}
          {st.manifesto && <span className="text-[11px] text-muted-foreground">Blender {st.manifesto.blender} · {st.manifesto.motor} · {st.manifesto.amostras} amostras · {st.manifesto.resolucao?.join("×")} px</span>}
        </div>
      )}
    </Card>
  );
}
