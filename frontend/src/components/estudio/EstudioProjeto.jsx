import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Image as ImageIcon, Loader2, Maximize2, Minimize2, Plus, Save, Send, Sparkles, Trash2, Undo2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Casa3D from "@/components/licenciamento/Casa3D";
import { aplicarComando, EXEMPLOS, novoAnexo } from "./comandos";

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
const FORMA = { rectangle: "Retangular", l: "Em L", t: "Em T" };


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

// Volumes do modelo a partir do volume editado — MESMAS regras que o servidor (volumes.building_polygons): retângulo,
// L (corpo à frente + ala no tardoz) ou T (barra no tardoz + corpo central), e anexos (blocks) em coordenadas do terreno.
export function retangulosCasa(vol) {
  const L = Math.max(1, Number(vol.footprint_l_m) || 8), W = Math.max(1, Number(vol.footprint_w_m) || 6);
  const nv = (v, d) => (v === undefined || v === null || v === "" || Number.isNaN(Number(v)) ? d : Number(v));
  const x0 = Math.max(0, nv(vol.setback_side_m, 3)), y0 = Math.max(0, nv(vol.setback_front_m, 5));
  const forma = String(vol.shape || "rectangle").toLowerCase();
  const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
  if (forma === "l") {
    const wl = clamp(Number(vol.wing_l_m) || L * 0.45, 0.5, L - 0.5), wh = clamp(Number(vol.wing_w_m) || W * 0.45, 0.5, W - 0.5);
    return [[x0, y0, x0 + L, y0 + W - wh], [x0, y0 + W - wh, x0 + L - wl, y0 + W]];
  }
  if (forma === "t") {
    const td = clamp(Number(vol.wing_w_m) || W * 0.45, 0.5, W - 0.5), sw = clamp(Number(vol.wing_l_m) || L * 0.4, 0.5, L - 0.5);
    const sx = x0 + (L - sw) / 2;
    return [[x0, y0 + W - td, x0 + L, y0 + W], [sx, y0, sx + sw, y0 + W - td]];
  }
  return [[x0, y0, x0 + L, y0 + W]];
}

function compor(base, vol, estilo, vaos) {
  const pl = Number(vol.plot_l_m) || 20, pw = Number(vol.plot_w_m) || 15;
  const terreno = base?.terreno || [[0, 0], [pl, 0], [pl, pw], [0, pw]];
  const plana = estilo.telhado === "plana";
  const hCob = plana ? 0 : ((base?.volumes || []).find((v) => !v.anexo)?.altura_cobertura_m || 2);
  const rect = (r) => [[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]];
  const volumes = retangulosCasa(vol).map((r, i) => ({ nome: i ? "" : "Casa", anexo: false, pts: rect(r),
    altura_m: (vol.levels || 1) * (vol.storey_h_m || 2.8), cobertura: plana ? "plana" : "duas_aguas", altura_cobertura_m: hCob }));
  for (const b of (vol.blocks || []).slice(0, 6)) {
    const bl = Math.max(0.5, Number(b.l_m) || 4), bw = Math.max(0.5, Number(b.w_m) || 3), bx = Number(b.x_m) || 0, by = Number(b.y_m) || 0;
    volumes.push({ nome: b.name || "Anexo", anexo: true, pts: rect([bx, by, bx + bl, by + bw]), altura_m: Number(b.h_m) || 3, cobertura: "plana", altura_cobertura_m: 0 });
  }
  const corpo = volumes.filter((v) => !v.anexo).flatMap((v) => v.pts);
  const cx0 = corpo.length ? Math.min(...corpo.map((p) => p[0])) : 0;
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
    plantas: base?.plantas || null,
    materiais: { ...(base?.materiais || {}), ...(estilo.fachada ? { fachada: estilo.fachada } : {}), ...(estilo.cobertura ? { cobertura: estilo.cobertura } : {}),
      ...(estilo.caixilharia ? { caixilharia: estilo.caixilharia } : {}) },
    estilo,
  };
}

export default function EstudioProjeto({ processoId, processo, vol, setVol, gravarVolume, recarregar, inicialGrande = false }) {
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
  const [estilosCat, setEstilosCat] = useState([]);
  const [escolhidos, setEscolhidos] = useState([]);
  const [descricao, setDescricao] = useState("");
  const [imagem, setImagem] = useState(null);
  const [modelos, setModelos] = useState(null);
  const [interior, setInterior] = useState(null);   // null = exterior; n = vista em corte do piso n

  useEffect(() => {
    const e0 = processo?.estudio || {};
    const mats = processo?.auto?.materiais || {};
    setEstilo({ telhado: vol.roof_type === "plana" ? "plana" : "duas_aguas", fachada: mats.fachada, cobertura: mats.cobertura, caixilharia: mats.caixilharia, ...e0, vaos: undefined });
    if (temAuto) {
      api.get(`/urbanismo-auto/processos/${processoId}/modelo3d`).then((r) => { setBase(r.data); setVaos(e0.vaos || r.data.vaos || []); }).catch(() => setVaos(e0.vaos || []));
      api.get("/urbanismo-auto/estilos").then((r) => setEstilosCat(r.data.estilos || [])).catch(() => {});
    } else setVaos(e0.vaos || []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [processoId, temAuto]);

  const modelo0 = useMemo(() => compor(base, vol, estilo, vaos), [base, vol, estilo, vaos]);
  const modelo = useMemo(() => (interior === null ? modelo0 : { ...modelo0, corte_piso: interior }), [modelo0, interior]);
  const nPisos = Number(vol.levels) || 1;
  const verInterior = (p) => { setInterior(p); if (p !== null) setTimeout(() => casa.current?.vista("interior"), 80); };
  const guardar = () => setHist((h) => [...h.slice(-30), { vol, estilo, vaos }]);
  const mudaVol = (k, val) => { guardar(); setVol((v) => ({ ...v, [k]: val })); };
  const mudaEst = (k, val) => { guardar(); setEstilo((e) => ({ ...e, [k]: val })); };
  const mudaVao = (i, k, val) => { guardar(); setVaos((vs) => vs.map((o, j) => (j === i ? { ...o, [k]: val } : o))); };
  const desfazer = () => setHist((h) => { const u = h[h.length - 1]; if (!u) return h; setVol(u.vol); setEstilo(u.estilo); setVaos(u.vaos); return h.slice(0, -1); });

  // Vãos propostos pela IA → coordenadas relativas à casa (como os acrescentados à mão)
  const vaosIA = (lista, d, v) => {
    let vs = lista.map((o, i) => {
      const a = (d.vaos?.alterar || []).find((x) => x.indice === i);
      if (!a) return o;
      const c = (o.x0 + o.x1) / 2, w = a.largura_m ?? (o.x1 - o.x0);
      return { ...o, x0: c - w / 2, x1: c + w / 2, ...(a.altura_m ? { z1: o.z0 + a.altura_m } : {}), ...(a.tipo ? { tipo: a.tipo } : {}) };
    }).filter((_, i) => !(d.vaos?.remover || []).includes(i));
    for (const n of d.vaos?.acrescentar || []) {
      const comp = ["esquerda", "direita"].includes(n.fachada) ? Number(v.footprint_w_m) : Number(v.footprint_l_m);
      const w = Math.min(n.largura_m, Math.max(0.6, comp - 0.8));
      const x0 = n.posicao === "esquerda" ? 0.6 : n.posicao === "direita" ? Math.max(0.6, comp - 0.6 - w) : Math.max(0.4, comp / 2 - w / 2);
      vs.push({ fachada: n.fachada, piso: n.piso, tipo: n.tipo, compartimento: n.compartimento || "", x0, x1: x0 + w,
        z0: n.peitoril_m, z1: n.peitoril_m + n.altura_m, _rel: true });
    }
    return vs;
  };

  const enviar = async (texto) => {
    const t = (texto ?? cmd).trim();
    if (!t || ocupado === "ia") return;
    setCmd("");
    const r = aplicarComando(t, { vol, estilo, vaos });
    const simples = !r.falhou && t.split(/\s+/).length <= 8;
    if (simples) {
      guardar(); setVol(r.vol); setEstilo(r.estilo); setVaos(r.vaos);
      setLog((l) => [...l, { eu: t, resp: `Feito: ${r.feito.join(" · ")}.` }]);
      return;
    }
    // pedido livre ou composto → Assistente IA (alterações validadas no servidor)
    setOcupado("ia");
    setLog((l) => [...l, { eu: t, resp: "A pensar…", pendente: true }]);
    let resp;
    try {
      const { vaos: _x, ...est } = estilo;
      const { data } = await api.post(`/urbanismo-auto/processos/${processoId}/estudio/ia`,
        { texto: t, vol, estilo: est, vaos, historico: log.filter((m) => !m.pendente).slice(-6).map(({ eu, resp: rr }) => ({ eu, resp: rr })) },
        { timeout: 90000 });
      if (data.erro) {
        if (!r.falhou) { guardar(); setVol(r.vol); setEstilo(r.estilo); setVaos(r.vaos); resp = `Feito: ${r.feito.join(" · ")}.`; }
        else resp = data.erro;
      } else {
        if (data.alterou) {
          guardar();
          const v2 = { ...vol, ...data.vol };
          setVol(v2); setEstilo((e) => ({ ...e, ...data.estilo })); setVaos((vs) => vaosIA(vs, data, v2));
        }
        resp = (data.resposta || (data.alterou ? "Feito." : "Sem alterações.")) +
          (data.recusas?.length ? ` Não aplicado: ${data.recusas.join("; ")}.` : "");
      }
    } catch (e) {
      if (!r.falhou) { guardar(); setVol(r.vol); setEstilo(r.estilo); setVaos(r.vaos); resp = `Feito: ${r.feito.join(" · ")}.`; }
      else resp = "O assistente não respondeu. Tente de novo ou use um comando simples (ex.: «telhado de 4 águas»).";
    }
    setLog((l) => [...l.filter((m) => !m.pendente), { eu: t, resp }]);
    setOcupado("");
  };

  const gravar = async () => {
    setOcupado("gravar");
    try {
      const roof = estilo.telhado === "plana" ? "plana" : estilo.telhado === "uma_agua" ? "uma_agua" : "duas_aguas";
      if (roof !== vol.roof_type) setVol((v) => ({ ...v, roof_type: roof }));
      await gravarVolume({ ...vol, roof_type: roof });
      const { vaos: _v, ...est } = estilo;
      await api.patch(`/urbanismo/processos/${processoId}`, { estudio: { ...Object.fromEntries(Object.entries(est).filter(([, x]) => x !== undefined && x !== "")),
        vaos: modelo0.vaos } });                      // coordenadas absolutas (as mesmas das peças desenhadas)
      setVaos(modelo0.vaos);
      toast.success("Estúdio gravado: processo, peças desenhadas e verificação atualizados.");
    } catch (e) { toast.error(e?.response?.data?.detail?.toString?.() || "Gravação impossível."); }
    setOcupado("");
  };

  const lerImagem = (f) => {
    if (!f) return;
    if (f.size > 8 * 1024 * 1024) { toast.error("Imagem demasiado grande (máx. 8 MB)."); return; }
    const r = new FileReader(); r.onload = () => setImagem(r.result); r.readAsDataURL(f);
  };
  const gerarModelos = async () => {
    setOcupado("modelos"); setModelos(null);
    try {
      const { data } = await api.post(`/urbanismo-auto/processos/${processoId}/variantes`,
        { estilos: escolhidos, descricao: descricao || null, imagem_b64: imagem, n: 4 }, { timeout: 180000 });
      setModelos(data);
      if (!data.variantes.length) toast.error("Nenhum modelo cabe neste terreno com os afastamentos e índices — veja os motivos.");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível gerar os modelos."); }
    setOcupado("");
  };
  const usarModelo = async (v) => {
    setOcupado(`aplicar-${v.id}`);
    try {
      await api.post(`/urbanismo-auto/processos/${processoId}/variantes/${v.id}/aplicar`);
      const r = await api.get(`/urbanismo-auto/processos/${processoId}/modelo3d`);
      setBase(r.data); setVaos(r.data.vaos || []);
      setEstilo((e) => ({ ...e, ...v.estudio, cor_fachada: null, cor_cobertura: null, cor_caixilharia: null }));
      if (recarregar) await recarregar();
      setModelos(null); setTab("casa");
      toast.success(`Modelo aplicado: ${v.titulo}. Pode continuar a editar.`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível aplicar o modelo."); }
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
        {[["assistente", "Assistente"], ["modelos", "Modelos"], ["casa", "Casa"], ["materiais", "Materiais"], ["vaos", "Vãos"]].map(([k, l]) => (
          <button key={k} type="button" onClick={() => setTab(k)} className={`flex-1 py-2 ${tab === k ? "border-b-2 border-primary font-medium" : "text-muted-foreground"}`}>{l}</button>
        ))}
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3 space-y-3 text-sm">
        {tab === "assistente" && (
          <>
            <p className="text-xs text-muted-foreground">Diga o que quer mudar, como diria a um arquiteto — «quero a casa mais moderna, térrea, com uma sala virada a sul toda envidraçada» — e a casa muda logo (pode desfazer). Pedidos curtos aplicam-se de imediato: {EXEMPLOS.slice(0, 3).map((x) => `«${x}»`).join(", ")}.</p>
            <div className="space-y-2" data-testid="estudio-log">
              {log.map((m, i) => (
                <div key={i} className="space-y-1">
                  <div className="ml-8 rounded-lg bg-primary/10 px-3 py-2">{m.eu}</div>
                  <div className={`mr-8 rounded-lg bg-muted px-3 py-2 ${m.pendente ? "animate-pulse" : ""}`}>{m.resp}</div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-1">
              {EXEMPLOS.map((x) => <button key={x} type="button" onClick={() => enviar(x)} className="text-[11px] border rounded-full px-2 py-0.5 hover:bg-muted">{x}</button>)}
            </div>
          </>
        )}
        {tab === "modelos" && (!temAuto ? (
          <p className="text-xs text-muted-foreground">Os modelos adaptados precisam do terreno real: crie o processo pelo Assistente ou pelo licenciamento automático (morada ou terreno).</p>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">Escolha estilos e/ou descreva a casa (ou junte uma foto de referência). O ConstruPilot gera modelos já adaptados ao terreno: afastamentos, índices, sol e declive.</p>
            <div className="flex flex-wrap gap-1" data-testid="estudio-estilos">
              {estilosCat.map((e) => {
                const on = escolhidos.includes(e.id);
                return <button key={e.id} type="button" title={e.descricao} onClick={() => setEscolhidos((x) => (on ? x.filter((y) => y !== e.id) : [...x, e.id].slice(-4)))}
                  className={`text-[11px] border rounded-full px-2 py-0.5 ${on ? "bg-primary text-primary-foreground border-primary" : "hover:bg-muted"}`}>{e.nome}</button>;
              })}
            </div>
            <textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={3} placeholder="Ex.: moradia moderna T4 térrea com cobertura plana, grandes envidraçados e garagem"
              className="w-full border rounded p-2 text-sm bg-background" data-testid="estudio-descricao" />
            <label className="inline-flex items-center gap-2 text-xs border rounded px-3 py-2 cursor-pointer hover:bg-muted w-fit" data-testid="estudio-imagem">
              <input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => { lerImagem(e.target.files?.[0]); e.target.value = ""; }} />
              Juntar foto ou imagem de uma casa de referência
            </label>
            {imagem && <div className="flex items-center gap-2"><img src={imagem} alt="Referência" className="h-16 rounded border" /><button type="button" className="text-xs underline" onClick={() => setImagem(null)}>remover</button></div>}
            <Button size="sm" onClick={gerarModelos} disabled={!!ocupado} data-testid="estudio-gerar-modelos">
              {ocupado === "modelos" ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Sparkles className="h-4 w-4 mr-1" />}Gerar modelos para este terreno
            </Button>
            {modelos?.leitura?.imagem?.erro && <p className="text-xs text-amber-700">{modelos.leitura.imagem.erro}</p>}
            <div className="grid gap-3" data-testid="estudio-modelos">
              {(modelos?.variantes || []).map((v) => (
                <div key={v.id} className="border rounded-lg overflow-hidden">
                  {v.modelo3d && <Casa3D modelo={v.modelo3d} altura={190} />}
                  <div className="p-2 space-y-1">
                    <div className="font-medium text-sm">{v.titulo}</div>
                    <div className="text-xs text-muted-foreground">{v.area_bruta_m2} m² de área bruta · {v.area_implantacao_m2} m² de implantação</div>
                    <div className="text-xs">{v.descricao}</div>
                    <Button size="sm" className="w-full" onClick={() => usarModelo(v)} disabled={!!ocupado}>
                      {ocupado === `aplicar-${v.id}` ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : null}Usar este modelo
                    </Button>
                  </div>
                </div>
              ))}
            </div>
            {modelos?.nao_couberam?.length > 0 && (
              <details className="text-xs text-muted-foreground"><summary>Não couberam neste terreno ({modelos.nao_couberam.length})</summary>
                <ul className="list-disc pl-4">{modelos.nao_couberam.map((m, i) => <li key={i}>{m}</li>)}</ul></details>
            )}
            {modelos?.nota && <p className="text-[11px] text-muted-foreground">{modelos.nota}</p>}
          </>
        ))}
        {tab === "casa" && (
          <>
            <Sel label="Forma" value={String(vol.shape || "rectangle").toLowerCase()} options={FORMA} onChange={(x) => mudaVol("shape", x)} />
            <Num label="Frente da casa" unit="m" value={vol.footprint_l_m} min={4} max={40} onChange={(x) => mudaVol("footprint_l_m", x)} />
            <Num label="Profundidade" unit="m" value={vol.footprint_w_m} min={4} max={40} onChange={(x) => mudaVol("footprint_w_m", x)} />
            {["l", "t"].includes(String(vol.shape || "").toLowerCase()) && (<>
              <Num label={String(vol.shape).toLowerCase() === "l" ? "Recorte da ala — largura" : "Corpo central — largura"} unit="m"
                value={vol.wing_l_m || Math.round((Number(vol.footprint_l_m) || 10) * (String(vol.shape).toLowerCase() === "l" ? 0.45 : 0.4) * 10) / 10}
                min={1} max={(Number(vol.footprint_l_m) || 10) - 0.5} onChange={(x) => mudaVol("wing_l_m", x)} />
              <Num label={String(vol.shape).toLowerCase() === "l" ? "Recorte da ala — profundidade" : "Barra do tardoz — profundidade"} unit="m"
                value={vol.wing_w_m || Math.round((Number(vol.footprint_w_m) || 8) * 0.45 * 10) / 10}
                min={1} max={(Number(vol.footprint_w_m) || 8) - 0.5} onChange={(x) => mudaVol("wing_w_m", x)} />
            </>)}
            <Num label="Pisos" value={vol.levels} step={1} min={1} max={4} onChange={(x) => mudaVol("levels", x)} />
            <Num label="Piso a piso" unit="m" value={vol.storey_h_m} step={0.05} min={2.4} max={4.5} onChange={(x) => mudaVol("storey_h_m", x)} />
            <Sel label="Telhado" value={estilo.telhado} options={TELHADO} onChange={(x) => mudaEst("telhado", x)} />
            {estilo.telhado !== "plana" && <Num label="Inclinação" unit="%" value={estilo.inclinacao_pct ?? 30} step={1} min={5} max={100} onChange={(x) => mudaEst("inclinacao_pct", x)} />}
            <Num label="Beiral" unit="m" value={estilo.beiral_m ?? 0.5} step={0.05} min={0} max={1.5} onChange={(x) => mudaEst("beiral_m", x)} />
            <div className="pt-2 border-t space-y-2" data-testid="estudio-anexos">
              <div className="flex items-center justify-between"><span className="text-xs font-medium">Anexos (garagem, arrumos…)</span>
                <Button size="sm" variant="outline" className="h-7" onClick={() => mudaVol("blocks", [...(vol.blocks || []), novoAnexo(vol)])}>+ Anexo</Button></div>
              {(vol.blocks || []).map((b, i) => {
                const muda = (k, x) => mudaVol("blocks", (vol.blocks || []).map((q, j) => (j === i ? { ...q, [k]: x } : q)));
                return (
                  <div key={i} className="rounded border p-2 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <input value={b.name || ""} onChange={(e) => muda("name", e.target.value)} className="text-xs border rounded px-1 py-0.5 w-32 bg-background" />
                      <button type="button" className="text-xs underline text-muted-foreground" onClick={() => mudaVol("blocks", (vol.blocks || []).filter((_, j) => j !== i))}>remover</button>
                    </div>
                    <Num label="Frente" unit="m" value={b.l_m} min={1} max={20} onChange={(x) => muda("l_m", x)} />
                    <Num label="Profundidade" unit="m" value={b.w_m} min={1} max={20} onChange={(x) => muda("w_m", x)} />
                    <Num label="Posição x" unit="m" value={b.x_m} min={0} max={Number(vol.plot_l_m) || 100} onChange={(x) => muda("x_m", x)} />
                    <Num label="Posição y" unit="m" value={b.y_m} min={0} max={Number(vol.plot_w_m) || 100} onChange={(x) => muda("y_m", x)} />
                  </div>
                );
              })}
            </div>
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
        <Input value={cmd} onChange={(e) => setCmd(e.target.value)} onKeyDown={(e) => e.key === "Enter" && enviar()} placeholder="Ex.: quero a casa mais moderna, térrea, com a sala virada a sul toda envidraçada" data-testid="estudio-cmd" />
        <Button size="icon" onClick={() => enviar()} aria-label="Enviar" disabled={ocupado === "ia"}>
          {ocupado === "ia" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </Button>
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
          <div className="flex items-center rounded-md border px-1" data-testid="estudio-interior">
            <span className="text-xs text-muted-foreground px-1">Interior</span>
            {Array.from({ length: nPisos }, (_, p) => (
              <Button key={p} size="sm" variant={interior === p ? "default" : "ghost"} className="h-7 px-2"
                onClick={() => verInterior(interior === p ? null : p)}>{p === 0 ? "R/C" : `${p}.º`}</Button>
            ))}
            {interior !== null && <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => verInterior(null)}>Exterior</Button>}
          </div>
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
