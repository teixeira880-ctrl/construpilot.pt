import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { WebGLPathTracer } from "three-gpu-pathtracer";
import { AMOSTRAS, PRAZO_VISTA_S, W, H, avaliarGPU, camaraThree, cena } from "./rendupcCena";
import { Cpu, Loader2, MonitorSmartphone, Server, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/* Rendu híbrido: o servidor (sem GPU) só prepara a cena exata no Blender e exporta o .glb; a placa gráfica do PC do
   utilizador faz o path tracing no navegador (mesmo princípio do Cycles). Mesmas câmaras, mesmo sol (posição real do
   terreno) e mesma geometria do que o render do servidor. Se o PC for fraco, o cálculo continua no servidor. */

async function carregarGLB(pid, nome) {
  const r = await api.get(`/urbanismo-auto/processos/${pid}/blender/${nome}`, { responseType: "arraybuffer", timeout: 180000 });
  return new GLTFLoader().parseAsync(r.data, "");
}

const b64 = (blob) => new Promise((ok, ko) => { const f = new FileReader(); f.onload = () => ok(f.result); f.onerror = ko; f.readAsDataURL(blob); });

export { avaliarGPU };

export default function RenduPC({ pid, onImagem, onServidor }) {
  const canvas = useRef(null);
  const parar = useRef(false);
  const [gpu] = useState(avaliarGPU);
  const [st, setSt] = useState(null);           // estado da cena preparada no servidor
  const [corre, setCorre] = useState(null);     // { vista, estado, amostras, alvo }
  const [msg, setMsg] = useState(null);
  const [erro, setErro] = useState(null);

  useEffect(() => {
    let vivo = true, t;
    const ler = async () => {
      let espera = 30000;
      try {
        const { data } = await api.get(`/urbanismo-auto/processos/${pid}/blender-pc`);
        if (!vivo) return;
        setSt(data);
        if (data.estado === "a_preparar") espera = 3000;
      } catch { /* tenta de novo */ }
      if (vivo) t = setTimeout(ler, espera);
    };
    ler();
    return () => { vivo = false; clearTimeout(t); };
  }, [pid]);

  const preparar = async () => {
    setErro(null);
    try {
      await api.post(`/urbanismo-auto/processos/${pid}/blender-pc`);
      setSt(s => ({ ...(s || {}), estado: "a_preparar" }));
    } catch (e) { setErro(e?.response?.data?.detail || "Não foi possível preparar a cena no servidor."); }
  };

  const renderizar = async () => {
    setErro(null); setMsg(null); parar.current = false;
    const nivel = gpu.nivel === "forte" ? "forte" : "medio";
    const alvo = AMOSTRAS[nivel];
    let renderer = null, pt = null, feitas = 0;
    try {
      const [depois, antes] = await Promise.all([carregarGLB(pid, "pc_modelo.glb"),
        (st.ficheiros || []).includes("pc_modelo_antes.glb") ? carregarGLB(pid, "pc_modelo_antes.glb") : Promise.resolve(null)]);
      renderer = new THREE.WebGLRenderer({ canvas: canvas.current, antialias: false, preserveDrawingBuffer: true });
      renderer.setPixelRatio(1);
      renderer.setSize(W, H, false);
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = 1.1;
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      pt = new WebGLPathTracer(renderer);
      pt.renderDelay = 0; pt.fadeDuration = 0; pt.minSamples = 1;
      pt.bounces = 6; pt.filterGlossyFactor = 0.5;
      pt.tiles.set(nivel === "forte" ? 1 : 2, nivel === "forte" ? 1 : 2);
      const vistas = (st.camaras || []).filter(c => !c.ortografica);
      for (const c of vistas) {
        for (const est of c.so_depois ? ["depois"] : ["antes", "depois"]) {
          const g = est === "antes" ? antes : depois;
          if (!g || parar.current) continue;
          const cam = camaraThree(c);
          pt.setScene(cena(g, st.sol), cam);          // BVH síncrono: cena de uma casa, sem worker
          const t0 = performance.now();
          setCorre({ vista: c.titulo, estado: est, amostras: 0, alvo });
          await new Promise((ok) => {
            const passo = () => {
              if (parar.current) return ok();
              pt.renderSample();
              const n = Math.floor(pt.samples);
              setCorre(x => (x && x.amostras !== n ? { ...x, amostras: n } : x));
              if (n >= alvo || (performance.now() - t0) / 1000 > PRAZO_VISTA_S[nivel]) return ok();
              requestAnimationFrame(passo);
            };
            requestAnimationFrame(passo);
          });
          if (parar.current) break;
          const blob = await new Promise(ok => canvas.current.toBlob(ok, "image/jpeg", 0.92));
          await api.post(`/urbanismo-auto/processos/${pid}/blender-pc/imagem`, {
            camara: c.id, estado: est, titulo: c.titulo, b64: await b64(blob),
            segundos: (performance.now() - t0) / 1000, amostras: Math.floor(pt.samples),
          }, { timeout: 120000 });
          feitas += 1;
          onImagem?.();
        }
        if (parar.current) break;
      }
      setMsg(parar.current ? `Parado: ${feitas} imagem(ns) guardada(s).` : `${feitas} imagens calculadas no seu PC e guardadas no processo.`);
    } catch (e) {
      setErro((e?.response?.data?.detail || e?.message || "Falha no cálculo no PC.") + " Pode calcular no servidor.");
    } finally {
      try { pt?.dispose(); } catch { /* nada */ }
      try { renderer?.dispose(); } catch { /* nada */ }
      setCorre(null);
    }
  };

  const pronto = st?.estado === "pronto" && (st.ficheiros || []).includes("pc_modelo.glb");
  const aPreparar = st?.estado === "a_preparar";

  return (
    <div className="border-t pt-3 space-y-2" data-testid="lic-auto-rendu-pc">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-medium flex items-center gap-2"><Cpu className="h-4 w-4" />Calcular as imagens no seu PC</div>
          <p className="text-xs text-muted-foreground">
            O servidor prepara a cena exata (segundos); a placa gráfica deste computador calcula a imagem (path tracing).
            Placa detetada: <span className="font-mono">{gpu.nome}</span>
            {gpu.ok ? (gpu.nivel === "forte" ? " — potente." : " — média (mais lento).") : ` — ${gpu.motivo}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!corre && (
            <Button size="sm" variant="outline" onClick={preparar} disabled={aPreparar || st?.blender_instalado === false} data-testid="lic-auto-pc-preparar">
              {aPreparar ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}{pronto ? "Preparar a cena de novo" : "1. Preparar a cena"}
            </Button>
          )}
          {!corre && gpu.ok && (
            <Button size="sm" onClick={renderizar} disabled={!pronto} data-testid="lic-auto-pc-renderizar">
              <MonitorSmartphone className="h-4 w-4 mr-2" />2. Calcular neste PC
            </Button>
          )}
          {corre && (
            <Button size="sm" variant="destructive" onClick={() => { parar.current = true; }}><Square className="h-4 w-4 mr-2" />Parar</Button>
          )}
          {!corre && onServidor && (
            <Button size="sm" variant="ghost" onClick={onServidor} data-testid="lic-auto-pc-servidor"><Server className="h-4 w-4 mr-2" />Calcular no servidor</Button>
          )}
        </div>
      </div>
      {st?.estado === "erro" && <p className="text-sm text-destructive">A preparação da cena falhou: {st.motivo}</p>}
      {st?.estado === "interrompido" && <p className="text-sm text-amber-700">A preparação foi interrompida. Carregue em «Preparar a cena de novo».</p>}
      {erro && <p className="text-sm text-destructive">{erro}</p>}
      {msg && <p className="text-sm text-emerald-700">{msg}</p>}
      {corre && (
        <p className="text-sm text-blue-700 flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />{corre.vista} — {corre.estado === "antes" ? "situação existente" : "proposta"}: {corre.amostras}/{corre.alvo} amostras
        </p>
      )}
      <canvas ref={canvas} width={W} height={H} className={corre ? "w-full aspect-video rounded bg-muted" : "hidden"} />
    </div>
  );
}
