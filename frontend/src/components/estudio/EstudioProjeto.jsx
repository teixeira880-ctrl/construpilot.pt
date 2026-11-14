import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Image as ImageIcon, Loader2, Maximize2, Minimize2, Plus, Save, Send, Sparkles, Trash2, Undo2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Casa3D from "@/components/licenciamento/Casa3D";
import { aplicarComando, EXEMPLOS } from "./comandos";

/**
 * Estúdio de Projeto (14/11): a casa do processo em 3D, editável ao vivo — dimensões, pisos, telhado, materiais, cores e vãos —
 * por formulário ou por frases ao Assistente; «Gravar» atualiza o processo (peças desenhadas, verificação, memória).
 * Os dados de partida são os MESMOS das peças desenhadas (modelo3d do processo, ou o volume introduzido).
 */
const FACHADA = { reboco_branco: "Reboco branco", granito: "Granito", madeira: "Ripado de madeira", xisto: "Xisto", tijolo: "Tijolo à vista",
  betao: "Betão aparente", misto_granito_reboco: "Granito + reboco", misto_madeira_reboco: "Reboco + madeira" };
const COBERTURA = { telha_ceramica: "Telha cerâmica vermelha", telha_preta: "Telha cerâmica preta", zinco: "Zinco", plana_seixo: "Plana (seixo)" };
const CAIXILHARIA = { aluminio_antracite: "Alumínio antracite", aluminio_branco: "Alumínio branco", madeira: "Madeira", pvc_branco: "PVC branco" };
const TELHADO = { duas_aguas: "2 águas", quatro_aguas: "4 águas", uma_agua: "1 água", plana: "Plana" };
const FACHADAS_V = ["frente", "tardoz", "esquerda", "direita"];

function Num({ label, value, onChange, step = 0.1, min = 0, max = 100, unit }) {
  return (
    <label className="grid gap-1 text-xs">
      <span>{label}{unit ? ` (${unit})` : ""}</span>
      <div className="flex items-center gap-2">
        <input type="range" min={min} max={max} step={step} value={Number(value) || 0} onChange={(e) => onChange(Number(e.target.value))} className="flex-1" />
        <Input type="number" step={step} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))} className="h-8 w-20" />
      </div>
    </label>
  );
}

function Sel({ label, value, options, onChange }) {
  return (
    <label className="grid gap-1 text-xs">{label}
      <select className="h-8 border rounded px-2 bg-background" value={value || ""} onChange={(e) => onChange(e.target.value)}>
        {Object.entries(options).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
    </label>
  );
}

function Cor({ label, value, onChange }) {
  return (
    <label className="flex items-center justify-between gap-2 text-xs">{label}
      <span className="flex items-center gap-1">
        <input type="color" value={value || "#ffffff"} onChange={(e) => onChange(e.target.value)} className="h-7 w-10 border rounded" />
        {value && <button type="button" className="text-muted-foreground underline" onClick={() => onChange(null)}>material</button>}
      </span>
    </label>
  );
}

// volumes do modelo a partir do volume editado (mantendo a posição da implantação do processo)
function compor(base, vol, estilo, vaos) {
  const L = Number(vol.footprint_l_m) || 8, W = Number(vol.footprint_w_m) || 6;
  let terreno, volumes;
  if (base?.volumes?.length) {
    terreno = base.terreno;
    volumes = base.volumes.map((v) => {
      if (v.anexo) return v;
      const xs = v.pts.map((p) => p[0]), ys = v.pts.map((p) => p[1]);
      const x0 = Math.min(...xs), y0 = Math.min(...ys);
      return { ...v, pts: [[x0, y0], [x0 + L, y0], [x0 + L, y0 + W], [x0, y0 + W]],
        cobertura: estilo.telhado === "plana" ? "plana" : "duas_aguas", altura_cobertura_m: estilo.telhado === "plana" ? 0 : (v.altura_cobertura_m || 2) };
    });
  } else {
    const pl = Number(vol.plot_l_m) || 20, pw = Number(vol.plot_w_m) || 15;
    const x0 = Number(vol.setback_side_m) || 0, y0 = Number(vol.setback_front_m) || 0;
    terreno = [[0, 0], [pl, 0], [pl, pw], [0, pw]];
    volumes = [{ nome: "Casa", anexo: false, pts: [[x0, y0], [x0 + L, y0], [x0 + L, y0 + W], [x0, y0 + W]], altura_m: (vol.levels || 1) * (vol.storey_h_m || 2.8),
      cobertura: estilo.telhado === "plana" ? "plana" : "duas_aguas", altura_cobertura_m: estilo.telhado === "plana" ? 0 : 2 }];
    for (const b of vol.blocks || []) {
      volumes.push({ nome: b.name || "Anexo", anexo: true, pts: [[b.x_m, b.y_m], [b.x_m + b.l_m, b.y_m], [b.x_m + b.l_m, b.y_m + b.w_m], [b.x_m, b.y_m + b.w_m]],
        altura_m: b.h_m || 3, cobertura: "plana", altura_cobertura_m: 0 });
    }
  }
  const casa = volumes.find((v) => !v.anexo);
  const cx0 = casa ? Math.min(...casa.pts.map((p) => p[0])) : 0;
  const sh = Number(vol.storey_h_m) || 2.8, n = Number(vol.levels) || 1;
  // vãos: frente/tardoz em coordenadas do terreno; os acrescentados no Estúdio (_rel) são relativos à casa
  const vs = vaos.map((o) => (o._rel && ["frente", "tardoz"].includes(o.fachada) ? { ...o, x0: o.x0 + cx0, x1: o.x1 + cx0 } : o))
    .filter((o) => (o.piso ?? 0) < n)
    .map((o) => {
      // cota relativa ao pavimento do piso: os vãos acompanham a mudança de piso a piso
      const pz = (o.piso ?? 0), ref = o._rel ? 0 : pz * (base?.piso_a_piso_m || sh);
      const { _rel, ...q } = o;
      return { ...q, z0: pz * sh + (o.z0 - ref), z1: pz * sh + (o.z1 - ref) };
    });
  return {
    terreno, volumes, pisos: n, piso_a_piso_m: sh, vaos: vs, terreno_grelha: base?.terreno_grelha || [], azimutes: base?.azimutes,
    materiais: { ...(base?.materiais || {}), ...(estilo.fachada ? { fachada: estilo.fachada } : {}), ...(estilo.cobertura ? { cobertura: estilo.cobertura } : {}),
      ...(estilo.caixilharia ? { caixilharia: estilo.caixilharia } : {}) },
    estilo,
  };
}

export default function EstudioProjeto({ processoId, processo, vol, setVol, gravarVolume, inicialGrande = false }) {
  const temAuto = !!processo?.auto;
  const [base, setBase] = useState(null);
  const [estilo, setEstilo] = useState({});
  const [vaos, setVaos] = useState([]);
  const [grande, setGrande] = useState(inicialGrande);
  const [tab, setTab] = useState("assistente");
  const [cmd, setCmd] = useState("");
  const [log, setLog] = useState([]);
  const [hist, setHist] = useState([]);
  const [ocupado, setOcupado] = useState("");
  const [render, setRender] = useState(null);
  const casa = useRef(null);

  useEffect(() => {
    const e0 = processo?.estudio || {};
    const mats = processo?.auto?.materiais || {};
    setEstilo({ telhado: vol.roof_type === "plana" ? "plana" : "duas_aguas", fachada: mats.fachada, cobertura: mats.cobertura, caixilharia: mats.caixilharia, ...e0, vaos: undefined });
    if (temAuto) {
      api.get(`/urbanismo-auto/processos/${processoId}/modelo3d`).then((r) => { setBase(r.data); setVaos(e0.vaos || r.data.vaos || []); }).catch(() => setVaos(e0.vaos || []));
    } else setVaos(e0.vaos || []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [processoId, temAuto]);

  const modelo = useMemo(() => compor(base, vol, estilo, vaos), [base, vol, estilo, vaos]);
  const guardar = () => setHist((h) => [...h.slice(-30), { vol, estilo, vaos }]);
  const mudaVol = (k, val) => { guardar(); setVol((v) => ({ ...v, [k]: val })); };
  const mudaEst = (k, val) => { guardar(); setEstilo((e) => ({ ...e, [k]: val })); };
  const mudaVao = (i, k, val) => { guardar(); setVaos((vs) => vs.map((o, j) => (j === i ? { ...o, [k]: val } : o))); };
  const desfazer = () => setHist((h) => { const u = h[h.length - 1]; if (!u) return h; setVol(u.vol); setEstilo(u.estilo); setVaos(u.vaos); return h.slice(0, -1); });

  const enviar = (texto) => {
    const t = (texto ?? cmd).trim();
    if (!t) return;
    const r = aplicarComando(t, { vol, estilo, vaos });
    if (!r.falhou) { guardar(); setVol(r.vol); setEstilo(r.estilo); setVaos(r.vaos); }
    setLog((l) => [...l, { eu: t, resp: r.falhou ? `Não percebi. Experimente, por exemplo: «${EXEMPLOS[Math.floor(Math.random() * EXEMPLOS.length)]}».` : `Feito: ${r.feito.join(" · ")}.` }]);
    setCmd("");
  };

  const gravar = async () => {
    setOcupado("gravar");
    try {
      const roof = estilo.telhado === "plana" ? "plana" : estilo.telhado === "uma_agua" ? "uma_agua" : "duas_aguas";
      if (roof !== vol.roof_type) setVol((v) => ({ ...v, roof_type: roof }));
      await gravarVolume({ ...vol, roof_type: roof });
      const { vaos: _v, ...est } = estilo;
      await api.patch(`/urbanismo/processos/${processoId}`, { estudio: { ...Object.fromEntries(Object.entries(est).filter(([, x]) => x !== undefined && x !== "")),
        vaos: modelo.vaos } });                      // coordenadas absolutas (as mesmas das peças desenhadas)
      setVaos(modelo.vaos);
      toast.success("Estúdio gravado: processo, peças desenhadas e verificação atualizados.");
    } catch (e) { toast.error(e?.response?.data?.detail?.toString?.() || "Gravação impossível."); }
    setOcupado("");
  };

  const fotorrealista = async () => {
    const img = casa.current?.snapshot();
    if (!img) return;
    setOcupado("render");
    try {
      const { data } = await api.post(`/urbanismo-auto/processos/${processoId}/render`, { imagem_b64: img }, { timeout: 180000 });
      setRender(`data:${data.mime};base64,${data.imagem_b64}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Imagem fotorrealista indisponível agora."); }
    setOcupado("");
  };

  const painel = (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex border-b text-xs">
        {[["assistente", "Assistente"], ["casa", "Casa"], ["materiais", "Materiais e cores"], ["vaos", "Janelas e portas"]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`flex-1 py-2 ${tab === k ? "border-b-2 border-primary font-medium" : "text-muted-foreground"}`}>{l}</button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 text-sm">
        {tab === "assistente" && (
          <>
            <p className="text-xs text-muted-foreground">Diga o que quer mudar e a casa muda logo. Ex.: {EXEMPLOS.slice(0, 4).map((x) => `«${x}»`).join(", ")}.</p>
            <div className="space-y-2" data-testid="estudio-log">
              {log.map((m, i) => (
                <div key={i} className="space-y-1">
                  <div className="ml-8 rounded-lg bg-primary/10 px-3 py-2">{m.eu}</div>
                  <div className="mr-8 rounded-lg bg-muted px-3 py-2">{m.resp}</div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {EXEMPLOS.map((x) => <button key={x} type="button" onClick={() => enviar(x)} className="text-[11px] border rounded-full px-2 py-0.5 hover:bg-muted">{x}</button>)}
            </div>
          </>
        )}
        {tab === "casa" && (
          <>
            <Num label="Frente da casa" unit="m" value={vol.footprint_l_m} min={4} max={40} onChange={(x) => mudaVol("footprint_l_m", x)} />
            <Num label="Profundidade" unit="m" value={vol.footprint_w_m} min={4} max={40} onChange={(x) => mudaVol("footprint_w_m", x)} />
            <Num label="Pisos" value={vol.levels} step={1} min={1} max={4} onChange={(x) => mudaVol("levels", x)} />
            <Num label="Piso a piso" unit="m" value={vol.storey_h_m} step={0.05} min={2.4} max={4.5} onChange={(x) => mudaVol("storey_h_m", x)} />
            <Sel label="Telhado" value={estilo.telhado} options={TELHADO} onChange={(x) => mudaEst("telhado", x)} />
            {estilo.telhado !== "plana" && <Num label="Inclinação" unit="%" value={estilo.inclinacao_pct ?? 30} step={1} min={5} max={100} onChange={(x) => mudaEst("inclinacao_pct", x)} />}
            <Num label="Beiral" unit="m" value={estilo.beiral_m ?? 0.5} step={0.05} min={0} max={1.5} onChange={(x) => mudaEst("beiral_m", x)} />
          </>
        )}
        {tab === "materiais" && (
          <>
            <Sel label="Fachadas" value={estilo.fachada || "reboco_branco"} options={FACHADA} onChange={(x) => mudaEst("fachada", x)} />
            <Cor label="Cor da fachada" value={estilo.cor_fachada} onChange={(x) => mudaEst("cor_fachada", x)} />
            <Sel label="Cobertura" value={estilo.cobertura || "telha_ceramica"} options={COBERTURA} onChange={(x) => mudaEst("cobertura", x)} />
            <Cor label="Cor da cobertura" value={estilo.cor_cobertura} onChange={(x) => mudaEst("cor_cobertura", x)} />
            <Sel label="Caixilharia" value={estilo.caixilharia || "aluminio_antracite"} options={CAIXILHARIA} onChange={(x) => mudaEst("caixilharia", x)} />
            <Cor label="Cor da caixilharia" value={estilo.cor_caixilharia} onChange={(x) => mudaEst("cor_caixilharia", x)} />
          </>
        )}
        {tab === "vaos" && (
          <>
            {vaos.map((o, i) => (
              <div key={i} className="border rounded p-2 space-y-1">
                <div className="flex items-center justify-between text-xs font-medium">
                  <span>{o.compartimento || "Vão"} — {o.fachada}, piso {o.piso ?? 0}</span>
                  <button type="button" onClick={() => { guardar(); setVaos((vs) => vs.filter((_, j) => j !== i)); }} title="Remover"><Trash2 className="h-3.5 w-3.5" /></button>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  <Sel label="Tipo" value={o.tipo} options={{ janela: "Janela", envidracado: "Envidraçado", porta: "Porta" }} onChange={(x) => mudaVao(i, "tipo", x)} />
                  <Sel label="Fachada" value={o.fachada} options={Object.fromEntries(FACHADAS_V.map((f) => [f, f]))} onChange={(x) => mudaVao(i, "fachada", x)} />
                </div>
                <Num label="Largura" unit="m" value={Number((o.x1 - o.x0).toFixed(2))} step={0.05} min={0.4} max={8}
                  onChange={(w) => { const c = (o.x0 + o.x1) / 2; guardar(); setVaos((vs) => vs.map((q, j) => (j === i ? { ...q, x0: c - w / 2, x1: c + w / 2 } : q))); }} />
                <Num label="Posição (centro)" unit="m" value={Number(((o.x0 + o.x1) / 2).toFixed(2))} step={0.05} min={0} max={60}
                  onChange={(c) => { const w = o.x1 - o.x0; guardar(); setVaos((vs) => vs.map((q, j) => (j === i ? { ...q, x0: c - w / 2, x1: c + w / 2 } : q))); }} />
                <Num label="Altura" unit="m" value={Number((o.z1 - o.z0).toFixed(2))} step={0.05} min={0.4} max={3}
                  onChange={(h) => { guardar(); setVaos((vs) => vs.map((q, j) => (j === i ? { ...q, z1: q.z0 + h } : q))); }} />
              </div>
            ))}
            <Button size="sm" variant="outline" onClick={() => enviar("acrescenta uma janela na fachada frente")}><Plus className="h-4 w-4 mr-1" />Janela na frente</Button>
          </>
        )}
      </div>
      <div className="border-t p-2 flex gap-2">
        <Input value={cmd} onChange={(e) => setCmd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && enviar()} placeholder="Ex.: fachada em granito e telhado de 4 águas" data-testid="estudio-cmd" />
        <Button size="icon" onClick={() => enviar()} aria-label="Enviar"><Send className="h-4 w-4" /></Button>
      </div>
    </div>
  );

  return (
    <div className={grande ? "fixed inset-0 z-50 bg-background flex flex-col" : "rounded-xl border bg-card overflow-hidden"} data-testid="estudio-projeto">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b">
        <Sparkles className="h-4 w-4 text-primary" /><span className="font-semibold">Estúdio de Projeto</span>
        <span className="text-xs text-muted-foreground hidden md:inline">— edite a casa ao vivo; «Gravar» atualiza as peças desenhadas e a verificação</span>
        <div className="ml-auto flex flex-wrap gap-1">
          {["perspetiva", "frente", "tardoz", "aerea"].map((n) => <Button key={n} size="sm" variant="ghost" onClick={() => casa.current?.vista(n)}>{n === "aerea" ? "Aérea" : n[0].toUpperCase() + n.slice(1)}</Button>)}
          <Button size="sm" variant="ghost" onClick={desfazer} disabled={!hist.length}><Undo2 className="h-4 w-4" /></Button>
          {temAuto && <Button size="sm" variant="outline" onClick={fotorrealista} disabled={!!ocupado}>{ocupado === "render" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <ImageIcon className="h-4 w-4 mr-1" />}Imagem real</Button>}
          <Button size="sm" onClick={gravar} disabled={!!ocupado} data-testid="estudio-gravar">{ocupado === "gravar" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Save className="h-4 w-4 mr-1" />}Gravar</Button>
          <Button size="sm" variant="outline" onClick={() => setGrande((g) => !g)} aria-label="Ecrã inteiro">{grande ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}</Button>
        </div>
      </div>
      <div className={`flex flex-col lg:flex-row min-h-0 ${grande ? "flex-1" : "h-[640px]"}`}>
        <div className="relative flex-1 min-h-[320px]">
          <Casa3D ref={casa} modelo={modelo} altura="100%" />
          {render && (
            <div className="absolute inset-0 bg-black/80 flex flex-col items-center justify-center p-4 gap-2">
              <img src={render} alt="Imagem fotorrealista" className="max-h-[85%] rounded" />
              <div className="flex gap-2"><a href={render} download="casa.png"><Button size="sm">Descarregar</Button></a><Button size="sm" variant="outline" onClick={() => setRender(null)}>Fechar</Button></div>
            </div>
          )}
        </div>
        <div className="w-full lg:w-[380px] border-t lg:border-t-0 lg:border-l min-h-0 h-[420px] lg:h-auto">{painel}</div>
      </div>
    </div>
  );
}
