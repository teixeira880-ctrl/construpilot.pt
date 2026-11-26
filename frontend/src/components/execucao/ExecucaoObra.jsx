import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Mic, Map as MapIcon, Wallet, Video, Loader2, Check, X, Plus, Trash2, Upload, Download, Sparkles, PenLine, RotateCcw, AlertTriangle } from "lucide-react";
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from "recharts";
import { T, LOCALE } from "./txt";

/**
 * Execução de obra — assessor de voz, mapa de avanço por zona (sobre a planta), tesouraria e câmaras.
 * O mesmo componente serve o titular (`client` = api, `base` = /chantiers/{id}/execucao) e o portal
 * (`client` = portalApi, `base` = /{ref}/execucao). O servidor decide o que cada perfil vê (`capacidades`).
 * `gestaoBase` aponta para a Gestão de obra (diário, stock, QSE, pedidos) onde o assessor grava após confirmação.
 */
const num = (v, d = 2) => new Intl.NumberFormat(LOCALE, { maximumFractionDigits: d }).format(Number(v || 0));
const eur = (v) => new Intl.NumberFormat(LOCALE, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(Number(v || 0));
const day = (s) => (s ? String(s).slice(0, 10).split("-").reverse().join("/") : "—");
const today = () => new Date().toISOString().slice(0, 10);
const err = (e) => toast.error(e?.response?.data?.detail || T.erro);
const card = "rounded-2xl border border-slate-200 bg-white text-slate-900";
const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600";
const btn = "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-10 disabled:opacity-50";
const primary = `${btn} bg-emerald-700 text-white hover:bg-emerald-800`;
const ghost = `${btn} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`;
const Pill = ({ cls = "bg-slate-100 text-slate-600", children }) => <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
const Empty = ({ children }) => <p className="p-6 text-center text-sm text-slate-500">{children}</p>;
const Lbl = ({ children }) => <span className="mb-1 block text-xs font-medium text-slate-600">{children}</span>;
const Head = ({ title, sub, children }) => (
  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-4">
    <div className="min-w-0"><h3 className="font-semibold">{title}</h3>{sub && <p className="mt-0.5 text-xs text-slate-500 max-w-3xl">{sub}</p>}</div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);
const cor = (p) => (p <= 0 ? "#e2e8f0" : p < 25 ? "#fde68a" : p < 50 ? "#fcd34d" : p < 75 ? "#a7f3d0" : p < 100 ? "#34d399" : "#047857");

const Voice = ({ onText, label }) => {
  const [C, setC] = useState(null);
  useEffect(() => { import("@/components/VoiceNoteButton").then((m) => setC(() => m.default)).catch(() => {}); }, []);
  return C ? <C onText={onText} label={label || T.ditar} size="default" /> : null;
};

export function useExecucao(client, base) {
  const [info, setInfo] = useState(null);
  useEffect(() => { client.get(base).then(({ data }) => setInfo(data)).catch(() => setInfo(false)); }, [client, base]);
  return info;
}

function useBlobUrl(client, url, deps = []) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    let alive = true, obj = null;
    if (!url) { setSrc(null); return undefined; }
    client.get(url, { responseType: "blob" }).then(({ data }) => { if (alive) { obj = URL.createObjectURL(data); setSrc(obj); } }).catch(() => alive && setSrc(null));
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, url, ...deps]);
  return src;
}

// ====================================================================== assessor de voz
const TIPO_CLS = { diario: "bg-sky-100 text-sky-800", stock: "bg-amber-100 text-amber-800", qse: "bg-red-100 text-red-800", rfi: "bg-indigo-100 text-indigo-800", avanco: "bg-emerald-100 text-emerald-800" };
const juntar = (a, b) => { const ex = new Set((a || "").split("\n").map((x) => x.trim().toLowerCase())); const novas = (b || "").split("\n").filter((x) => x.trim() && !ex.has(x.trim().toLowerCase())); return [a, ...novas].filter(Boolean).join("\n"); };

export function AssessorPanel({ client, base, gestaoBase }) {
  const [texto, setTexto] = useState("");
  const [data, setData] = useState(today());
  const [ia, setIa] = useState(true);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [props, setProps] = useState([]);
  const [feito, setFeito] = useState(null);
  const interpretar = async () => {
    if (!texto.trim()) return;
    setBusy(true); setFeito(null);
    try { const { data: r } = await client.post(`${base}/assessor/interpretar`, { texto, data, usar_ia: ia }, { timeout: 90000 }); setRes(r); setProps(r.propostas); if (r.aviso) toast.message(r.aviso); }
    catch (e) { err(e); } finally { setBusy(false); }
  };
  const upd = (id, patch) => setProps((ps) => ps.map((p) => (p.id === id ? { ...p, ...patch } : p)));
  const updCampo = (id, k, v) => setProps((ps) => ps.map((p) => (p.id === id ? { ...p, campos: { ...p.campos, [k]: v } } : p)));
  const sel = props.filter((p) => p.selecionada);

  const gravar = async () => {
    setBusy(true);
    const out = [];
    const nota = (p) => `${T.assessor}: «${(p.frase || "").slice(0, 300)}»`;
    const ordem = { diario: 0, stock: 1, qse: 2, rfi: 3, avanco: 4 };
    const fila = [...sel].sort((a, b) => ordem[a.tipo] - ordem[b.tipo] || (a.tipo === "stock" ? (a.mov === "entrada" ? -1 : 1) - (b.mov === "entrada" ? -1 : 1) : 0));
    const avancos = fila.filter((p) => p.tipo === "avanco");
    for (const p of fila.filter((x) => x.tipo !== "avanco")) {
      try {
        if (p.tipo === "diario") {
          const c = p.campos;
          const ef = (c.efetivos || []).filter((e) => e.equipa && e.n > 0);
          const ex = res.diario_existente;
          if (!ex) {
            await client.post(`${gestaoBase}/diario`, { data: res.data, trabalhos: c.trabalhos, ocorrencias: c.ocorrencias, entregas: c.entregas, visitas: c.visitas, observacoes: c.observacoes, efetivos: ef });
          } else {
            const { data: d } = await client.get(`${gestaoBase}/diario/${ex.diario_id}`);
            if (d.estado === "assinado") {
              const txt = [["trabalhos", c.trabalhos], ["ocorrencias", c.ocorrencias], ["entregas", c.entregas], ["visitas", c.visitas], ["observacoes", c.observacoes]]
                .filter(([, v]) => v).map(([k, v]) => `${T[k]}: ${v}`).join("\n");
              await client.post(`${gestaoBase}/diario/${ex.diario_id}/aditamento`, { texto: txt.slice(0, 4000) });
            } else {
              const efs = [...(d.efetivos || [])];
              ef.forEach((e) => { if (!efs.some((x) => x.equipa.toLowerCase() === e.equipa.toLowerCase())) efs.push(e); });
              await client.put(`${gestaoBase}/diario/${ex.diario_id}`, { trabalhos: juntar(d.trabalhos, c.trabalhos), ocorrencias: juntar(d.ocorrencias, c.ocorrencias),
                entregas: juntar(d.entregas, c.entregas), visitas: juntar(d.visitas, c.visitas), observacoes: juntar(d.observacoes, c.observacoes), efetivos: efs.slice(0, 40), expected_version: d.versao || 0 });
            }
          }
        } else if (p.tipo === "stock") {
          await client.post(`${gestaoBase}/stock/movimentos`, { tipo: p.mov, material: p.material, unidade: p.unidade, quantidade: Number(p.quantidade), data: res.data, nota: nota(p).slice(0, 500) });
        } else if (p.tipo === "qse") {
          await client.post(`${gestaoBase}/qse`, { tipo: p.qse_tipo, titulo: p.titulo, descricao: p.descricao, data: res.data, local: p.local, gravidade: p.gravidade });
        } else if (p.tipo === "rfi") {
          await client.post(`${gestaoBase}/rfi`, { assunto: p.assunto, pergunta: p.pergunta, destinatario_perfil: p.destinatario_perfil || null });
        }
        out.push({ id: p.id, ok: true });
      } catch (e) { out.push({ id: p.id, ok: false, msg: e?.response?.data?.detail || T.erro }); }
    }
    if (avancos.length) {
      try { await client.post(`${base}/mapa/avanco`, { origem: "assessor", itens: avancos.map((p) => ({ zona_id: p.zona_id, atividade_id: p.atividade_id, pct: Number(p.pct), nota: (p.frase || "").slice(0, 500) })) });
        avancos.forEach((p) => out.push({ id: p.id, ok: true })); }
      catch (e) { avancos.forEach((p) => out.push({ id: p.id, ok: false, msg: e?.response?.data?.detail || T.erro })); }
    }
    setFeito(Object.fromEntries(out.map((o) => [o.id, o])));
    setBusy(false);
    if (out.every((o) => o.ok)) toast.success(T.gravado_tudo); else toast.error(`${out.filter((o) => !o.ok).length} × ${T.resultado_erro}`);
  };
  const reset = () => { setTexto(""); setRes(null); setProps([]); setFeito(null); };

  return (
    <section className={card} data-testid="exec-assessor">
      <Head title={T.assessor} sub={T.assessor_sub} />
      <div className="p-4 grid gap-3">
        <div className="flex flex-wrap items-end gap-2">
          <label><Lbl>{T.data}</Lbl><input type="date" max={today()} className={`${field} w-44`} value={data} onChange={(e) => setData(e.target.value)} /></label>
          <Voice onText={(t) => setTexto((x) => (x ? x + " " : "") + t)} />
          <label className="flex items-center gap-2 text-sm min-h-10"><input type="checkbox" checked={ia} onChange={(e) => setIa(e.target.checked)} /> {T.usar_ia}</label>
        </div>
        <textarea className={field} rows={5} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={T.relato_ph} maxLength={6000} data-testid="exec-assessor-texto" />
        <div className="flex flex-wrap gap-2">
          <button className={primary} disabled={busy || !texto.trim()} onClick={interpretar} data-testid="exec-assessor-interpretar">{busy && !res ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} {T.interpretar}</button>
          {res && <button className={ghost} onClick={reset}><RotateCcw className="h-4 w-4" /> {T.novo_relato}</button>}
        </div>
        {res && <div className="grid gap-3">
          <p className="text-xs text-slate-500">{res.fonte === "ia" ? T.fonte_ia : T.fonte_local} · {T.rever}</p>
          {res.zonas === 0 && <p className="text-xs text-slate-500">{T.assessor_dica}</p>}
          {props.length === 0 && <Empty>{T.nada_proposto}</Empty>}
          {props.map((p) => <Proposta key={p.id} p={p} res={res} feito={feito?.[p.id]} upd={upd} updCampo={updCampo} />)}
          {props.length > 0 && !feito && <div><button className={primary} disabled={busy || sel.length === 0} onClick={gravar} data-testid="exec-assessor-gravar">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />} {T.gravar_n.replace("{n}", sel.length)}</button></div>}
        </div>}
      </div>
    </section>
  );
}

function Proposta({ p, res, feito, upd, updCampo }) {
  const titulo = { diario: T.t_diario, stock: `${T.t_stock} · ${p.mov === "entrada" ? T.entrada : T.saida}`, qse: T.t_qse, rfi: T.t_rfi, avanco: T.t_avanco }[p.tipo];
  const ro = !!feito;
  return (
    <div className={`rounded-xl border p-3 ${p.selecionada ? "border-emerald-300 bg-emerald-50/30" : "border-slate-200 opacity-70"}`} data-testid={`exec-prop-${p.tipo}`}>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <input type="checkbox" checked={p.selecionada} disabled={ro} onChange={(e) => upd(p.id, { selecionada: e.target.checked })} aria-label={titulo} />
        <Pill cls={TIPO_CLS[p.tipo]}>{titulo}</Pill>
        {p.tipo === "stock" && <Pill>{p.material_conhecido ? T.material_conhecido : T.material_novo}</Pill>}
        {feito && <Pill cls={feito.ok ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"}>{feito.ok ? `✓ ${T.resultado_ok}` : `✗ ${feito.msg}`}</Pill>}
      </div>
      {p.tipo === "diario" && <div className="grid gap-2">
        {res.diario_existente && <p className="text-xs text-amber-700">{res.diario_existente.estado === "assinado" ? T.diario_assinado : T.diario_existe}</p>}
        {["trabalhos", "ocorrencias", "entregas", "visitas", "observacoes"].filter((k) => p.campos[k] || k === "trabalhos").map((k) => (
          <label key={k}><Lbl>{T[k]}</Lbl><textarea disabled={ro} className={field} rows={Math.min(5, Math.max(1, (p.campos[k] || "").split("\n").length))} value={p.campos[k]} onChange={(e) => updCampo(p.id, k, e.target.value)} /></label>))}
        {p.campos.efetivos?.length > 0 && <div><Lbl>{T.efetivos}</Lbl>{p.campos.efetivos.map((e, i) => <div key={i} className="flex gap-2 mb-1">
          <input disabled={ro} className={field} value={e.equipa} onChange={(ev) => updCampo(p.id, "efetivos", p.campos.efetivos.map((x, j) => (j === i ? { ...x, equipa: ev.target.value } : x)))} />
          <input disabled={ro} type="number" min={0} className={`${field} w-24`} value={e.n} onChange={(ev) => updCampo(p.id, "efetivos", p.campos.efetivos.map((x, j) => (j === i ? { ...x, n: Number(ev.target.value) } : x)))} /></div>)}</div>}
      </div>}
      {p.tipo === "stock" && <div className="grid sm:grid-cols-5 gap-2">
        <select disabled={ro} className={field} value={p.mov} onChange={(e) => upd(p.id, { mov: e.target.value })}><option value="entrada">{T.entrada}</option><option value="saida">{T.saida}</option></select>
        <input disabled={ro} className={`${field} sm:col-span-2`} value={p.material} onChange={(e) => upd(p.id, { material: e.target.value })} aria-label={T.material} />
        <input disabled={ro} className={field} value={p.unidade} onChange={(e) => upd(p.id, { unidade: e.target.value })} aria-label={T.unidade} placeholder={T.unidade} />
        <input disabled={ro} type="number" step="0.001" min={0} className={field} value={p.quantidade} onChange={(e) => upd(p.id, { quantidade: e.target.value })} aria-label={T.quantidade} />
      </div>}
      {p.tipo === "qse" && <div className="grid sm:grid-cols-4 gap-2">
        <select disabled={ro} className={field} value={p.qse_tipo} onChange={(e) => upd(p.id, { qse_tipo: e.target.value })}>{Object.entries(T.qse_tipos).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input disabled={ro} className={`${field} sm:col-span-2`} value={p.titulo} onChange={(e) => upd(p.id, { titulo: e.target.value })} aria-label={T.titulo} />
        <select disabled={ro} className={field} value={p.gravidade} onChange={(e) => upd(p.id, { gravidade: e.target.value })}>{Object.entries(T.gravidades).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <input disabled={ro} className={`${field} sm:col-span-4`} value={p.local} placeholder={T.local} onChange={(e) => upd(p.id, { local: e.target.value })} />
      </div>}
      {p.tipo === "rfi" && <div className="grid sm:grid-cols-4 gap-2">
        <input disabled={ro} className={`${field} sm:col-span-3`} value={p.assunto} onChange={(e) => upd(p.id, { assunto: e.target.value })} aria-label={T.assunto} />
        <select disabled={ro} className={field} value={p.destinatario_perfil || ""} onChange={(e) => upd(p.id, { destinatario_perfil: e.target.value || null })}>{Object.entries(T.perfis).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <textarea disabled={ro} className={`${field} sm:col-span-4`} rows={2} value={p.pergunta} onChange={(e) => upd(p.id, { pergunta: e.target.value })} />
      </div>}
      {p.tipo === "avanco" && <div className="flex flex-wrap items-center gap-3 text-sm">
        <b>{p.zona}</b><span>·</span><span>{p.atividade}</span>
        <input disabled={ro} type="range" min={0} max={100} step={5} value={p.pct} onChange={(e) => upd(p.id, { pct: Number(e.target.value) })} className="w-40 accent-emerald-700" />
        <b>{num(p.pct, 0)} %</b>
      </div>}
      {p.frase && p.tipo !== "diario" && <p className="mt-2 text-[11px] text-slate-500">{T.frase}: «{p.frase}»</p>}
    </div>
  );
}

// ====================================================================== mapa da obra
function PlantaZonas({ client, base, piso, zonas, resumoZonas, onZona, desenhar, onRet, selecionada, versao }) {
  const src = useBlobUrl(client, piso?.tem_planta ? `${base}/mapa/planta/${piso.piso_id}` : null, [versao]);
  const ref = useRef(null);
  const [drag, setDrag] = useState(null);
  const pt = (e) => { const r = ref.current.getBoundingClientRect(); const p = e.touches ? e.touches[0] : e;
    return [Math.min(100, Math.max(0, ((p.clientX - r.left) / r.width) * 100)), Math.min(100, Math.max(0, ((p.clientY - r.top) / r.height) * 100))]; };
  const down = (e) => { if (!desenhar) return; e.preventDefault(); const [x, y] = pt(e); setDrag({ x0: x, y0: y, x1: x, y1: y }); };
  const move = (e) => { if (!drag) return; e.preventDefault(); const [x, y] = pt(e); setDrag((d) => ({ ...d, x1: x, y1: y })); };
  const up = () => { if (!drag) return; const r = { x: Math.min(drag.x0, drag.x1), y: Math.min(drag.y0, drag.y1), w: Math.abs(drag.x1 - drag.x0), h: Math.abs(drag.y1 - drag.y0) };
    setDrag(null); if (r.w > 1 && r.h > 1) onRet(Object.fromEntries(Object.entries(r).map(([k, v]) => [k, Math.round(v * 100) / 100]))); };
  const avz = Object.fromEntries((resumoZonas || []).map((z) => [z.zona_id, z.avanco]));
  if (!piso) return null;
  if (!piso.tem_planta) return <Empty>{T.sem_planta}</Empty>;
  return (
    <div className="relative select-none touch-none overflow-hidden rounded-xl border bg-slate-50" ref={ref}
      onMouseDown={down} onMouseMove={move} onMouseUp={up} onMouseLeave={up} onTouchStart={down} onTouchMove={move} onTouchEnd={up}
      style={{ cursor: desenhar ? "crosshair" : "default" }} data-testid="exec-planta">
      {src ? <img src={src} alt={piso.nome} className="block w-full h-auto pointer-events-none" draggable={false} /> : <div className="h-64 grid place-items-center"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>}
      {zonas.filter((z) => z.ret).map((z) => { const p = avz[z.zona_id] || 0; return (
        <button key={z.zona_id} type="button" onClick={(e) => { e.stopPropagation(); if (!desenhar) onZona(z.zona_id); }}
          className={`absolute grid place-items-center text-center rounded-sm border-2 transition ${selecionada === z.zona_id ? "ring-4 ring-sky-400" : ""}`}
          style={{ left: `${z.ret.x}%`, top: `${z.ret.y}%`, width: `${z.ret.w}%`, height: `${z.ret.h}%`, background: `${cor(p)}99`, borderColor: cor(p), pointerEvents: desenhar ? "none" : "auto" }}
          data-testid={`exec-zona-${z.zona_id}`}>
          <span className="rounded bg-white/85 px-1.5 py-0.5 text-[11px] font-semibold leading-tight text-slate-900 shadow-sm">{z.nome}<br />{num(p, 0)} %</span>
        </button>); })}
      {drag && <div className="absolute border-2 border-dashed border-sky-600 bg-sky-300/30" style={{ left: `${Math.min(drag.x0, drag.x1)}%`, top: `${Math.min(drag.y0, drag.y1)}%`, width: `${Math.abs(drag.x1 - drag.x0)}%`, height: `${Math.abs(drag.y1 - drag.y0)}%` }} />}
    </div>
  );
}

function EditorEstrutura({ client, base, mapa, onSaved, onCancel }) {
  const [e, setE] = useState(() => ({ pisos: mapa.pisos.map(({ piso_id, nome }) => ({ piso_id, nome })), zonas: mapa.zonas.map((z) => ({ ...z })), atividades: mapa.atividades.map((a) => ({ ...a })) }));
  const [modelo, setModelo] = useState(Object.keys(mapa.modelos)[0] || "");
  const [busy, setBusy] = useState(false);
  const uid = (p) => `${p}_${Math.random().toString(36).slice(2, 9)}`;
  const set = (k, i, patch) => setE((x) => ({ ...x, [k]: x[k].map((v, j) => (j === i ? { ...v, ...patch } : v)) }));
  const del = (k, i) => setE((x) => {
    const n = { ...x, [k]: x[k].filter((_, j) => j !== i) };
    if (k === "pisos") n.zonas = n.zonas.filter((z) => n.pisos.some((p) => p.piso_id === z.piso_id));
    return n; });
  const aplicarModelo = async () => { try { const { data } = await client.get(`${base}/mapa/modelo/${modelo}`);
    setE((x) => ({ ...x, atividades: [...x.atividades, ...data.atividades.filter((a) => !x.atividades.some((b) => b.nome.toLowerCase() === a.nome.toLowerCase())).map((a) => ({ ...a, atividade_id: uid("atv") }))] })); } catch (er) { err(er); } };
  const guardar = async () => { setBusy(true);
    try { const { data } = await client.put(`${base}/mapa/estrutura`, { ...e, zonas: e.zonas.map((z) => ({ zona_id: z.zona_id, piso_id: z.piso_id, nome: z.nome, ret: z.ret || null, area_m2: z.area_m2 ? Number(z.area_m2) : null })),
      atividades: e.atividades.map((a) => ({ atividade_id: a.atividade_id, nome: a.nome, peso: Number(a.peso) || 1 })), expected_version: mapa.versao }); onSaved(data); }
    catch (er) { err(er); } finally { setBusy(false); } };
  return (
    <div className="grid gap-4 p-4 border-b bg-slate-50/60" data-testid="exec-mapa-editor">
      <div className="grid lg:grid-cols-3 gap-4">
        <div><div className="flex items-center justify-between"><Lbl>{T.pisos}</Lbl><button className="text-xs text-emerald-700 underline" onClick={() => setE((x) => ({ ...x, pisos: [...x.pisos, { piso_id: uid("piso"), nome: `${T.novo_piso} ${x.pisos.length + 1}` }] }))}>+ {T.novo_piso}</button></div>
          {e.pisos.map((p, i) => <div key={p.piso_id} className="flex gap-1 mb-1"><input className={field} value={p.nome} onChange={(ev) => set("pisos", i, { nome: ev.target.value })} /><button className={ghost} onClick={() => del("pisos", i)} aria-label={T.apagar}><Trash2 className="h-4 w-4" /></button></div>)}</div>
        <div><div className="flex items-center justify-between"><Lbl>{T.zonas}</Lbl>{e.pisos.length > 0 && <button className="text-xs text-emerald-700 underline" onClick={() => setE((x) => ({ ...x, zonas: [...x.zonas, { zona_id: uid("zona"), piso_id: x.pisos[0].piso_id, nome: `${T.nova_zona} ${x.zonas.length + 1}`, ret: null, area_m2: "" }] }))}>+ {T.nova_zona}</button>}</div>
          <div className="max-h-80 overflow-y-auto pr-1">{e.zonas.map((z, i) => <div key={z.zona_id} className="grid grid-cols-[1fr_7rem_5rem_auto] gap-1 mb-1">
            <input className={field} value={z.nome} onChange={(ev) => set("zonas", i, { nome: ev.target.value })} />
            <select className={field} value={z.piso_id} onChange={(ev) => set("zonas", i, { piso_id: ev.target.value })}>{e.pisos.map((p) => <option key={p.piso_id} value={p.piso_id}>{p.nome}</option>)}</select>
            <input type="number" min={0} className={field} placeholder="m²" value={z.area_m2 || ""} onChange={(ev) => set("zonas", i, { area_m2: ev.target.value })} aria-label={T.area} />
            <button className={ghost} onClick={() => del("zonas", i)} aria-label={T.apagar}><Trash2 className="h-4 w-4" /></button></div>)}</div></div>
        <div><div className="flex items-center justify-between"><Lbl>{T.atividades}</Lbl><button className="text-xs text-emerald-700 underline" onClick={() => setE((x) => ({ ...x, atividades: [...x.atividades, { atividade_id: uid("atv"), nome: `${T.nova_atividade} ${x.atividades.length + 1}`, peso: 1 }] }))}>+ {T.nova_atividade}</button></div>
          <div className="flex gap-1 mb-2"><select className={field} value={modelo} onChange={(ev) => setModelo(ev.target.value)} aria-label={T.modelo}>{Object.entries(mapa.modelos).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select><button className={ghost} onClick={aplicarModelo}>{T.aplicar_modelo}</button></div>
          <div className="max-h-72 overflow-y-auto pr-1">{e.atividades.map((a, i) => <div key={a.atividade_id} className="grid grid-cols-[1fr_4.5rem_auto] gap-1 mb-1">
            <input className={field} value={a.nome} onChange={(ev) => set("atividades", i, { nome: ev.target.value })} />
            <input type="number" min={0.1} step={0.5} className={field} value={a.peso} onChange={(ev) => set("atividades", i, { peso: ev.target.value })} aria-label={T.peso} title={T.peso} />
            <button className={ghost} onClick={() => del("atividades", i)} aria-label={T.apagar}><Trash2 className="h-4 w-4" /></button></div>)}</div></div>
      </div>
      <div className="flex gap-2"><button className={primary} disabled={busy} onClick={guardar} data-testid="exec-mapa-guardar"><Check className="h-4 w-4" /> {T.guardar}</button><button className={ghost} onClick={onCancel}>{T.cancelar}</button></div>
    </div>
  );
}

export function MapaPanel({ client, base, fileBase }) {
  const [m, setM] = useState(null);
  const [piso, setPiso] = useState(null);
  const [editar, setEditar] = useState(false);
  const [desenhar, setDesenhar] = useState(null);   // zona_id a desenhar
  const [zona, setZona] = useState(null);
  const [edits, setEdits] = useState({});
  const [plantaV, setPlantaV] = useState(0);
  const fileRef = useRef(null);
  const load = useCallback(() => client.get(`${base}/mapa`).then(({ data }) => setM(data)).catch((e) => { setM(false); err(e); }), [client, base]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (m && (!piso || !m.pisos.some((p) => p.piso_id === piso))) setPiso(m.pisos[0]?.piso_id || null); }, [m, piso]);
  const pisoObj = m?.pisos.find((p) => p.piso_id === piso);
  const zonasPiso = useMemo(() => (m ? m.zonas.filter((z) => z.piso_id === piso) : []), [m, piso]);
  const resumoZona = (id) => m?.resumo.zonas.find((z) => z.zona_id === id);
  if (m === null) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  if (m === false) return null;
  const abrirZona = (id) => { setZona(id); setEdits({}); };
  const guardarRet = async (ret) => {
    try { const { data } = await client.put(`${base}/mapa/estrutura`, { pisos: m.pisos.map(({ piso_id, nome }) => ({ piso_id, nome })),
      zonas: m.zonas.map((z) => ({ zona_id: z.zona_id, piso_id: z.piso_id, nome: z.nome, area_m2: z.area_m2, ret: z.zona_id === desenhar ? ret : z.ret })),
      atividades: m.atividades, expected_version: m.versao }); setM(data); } catch (e) { err(e); }
    setDesenhar(null);
  };
  const enviarPlanta = async (f) => { if (!f) return; const fd = new FormData(); fd.append("file", f);
    try { const { data } = await client.post(`${base}/mapa/planta/${piso}`, fd); setM(data); setPlantaV((v) => v + 1); } catch (e) { err(e); } };
  const guardarAvanco = async () => {
    const itens = Object.entries(edits).map(([aid, pct]) => ({ zona_id: zona, atividade_id: aid, pct: Number(pct) }));
    if (!itens.length) { setZona(null); return; }
    try { const { data } = await client.post(`${base}/mapa/avanco`, { itens }); setM(data); setZona(null); } catch (e) { err(e); }
  };
  const r = m.resumo;
  const zonaSel = m.zonas.find((z) => z.zona_id === zona);
  return (
    <div className="grid gap-4">
      <section className={card} data-testid="exec-mapa">
        <Head title={T.mapa} sub={T.mapa_sub}>
          {m.pode_editar && !editar && <button className={ghost} onClick={() => setEditar(true)} data-testid="exec-mapa-editar"><PenLine className="h-4 w-4" /> {T.editar_estrutura}</button>}
          {m.pode_editar && fileBase && m.zonas.length > 0 && <a className={ghost} href={`${fileBase}/mapa.pdf`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> {T.pdf}</a>}
        </Head>
        {editar && <EditorEstrutura client={client} base={base} mapa={m} onSaved={(d) => { setM(d); setEditar(false); }} onCancel={() => setEditar(false)} />}
        {m.zonas.length === 0 && !editar ? <Empty>{T.mapa_vazio}</Empty> : <div className="p-4 grid gap-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <div className="rounded-xl border p-3 col-span-2 sm:col-span-1"><p className="text-[11px] uppercase text-slate-500">{T.global}</p><p className="text-3xl font-bold text-emerald-800">{num(r.global, 1)} %</p>
              <div className="mt-1 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-emerald-600" style={{ width: `${Math.min(100, r.global)}%` }} /></div></div>
            <div className="rounded-xl border p-3"><p className="text-[11px] uppercase text-slate-500">{T.zonas}</p><p className="text-lg font-bold">{m.zonas.length}</p><p className="text-xs text-slate-500">{r.concluidas} {T.concluidas} · {r.por_iniciar} {T.por_iniciar}</p></div>
            {r.pisos.slice(0, 2).map((p) => <div key={p.piso_id} className="rounded-xl border p-3"><p className="text-[11px] uppercase text-slate-500">{p.nome}</p><p className="text-lg font-bold">{num(p.avanco, 1)} %</p></div>)}
          </div>
          <p className="text-xs text-slate-500">{r.base === "area" ? T.base_area : T.base_zonas}</p>
          {m.pisos.length > 0 && <div className="flex flex-wrap items-center gap-2">
            {m.pisos.map((p) => <button key={p.piso_id} type="button" onClick={() => { setPiso(p.piso_id); setZona(null); }} aria-pressed={piso === p.piso_id}
              className={`rounded-xl px-3 py-2 text-sm min-h-10 ${piso === p.piso_id ? "bg-emerald-700 text-white" : "border border-slate-300 text-slate-700"}`}>{p.nome} · {num(r.pisos.find((x) => x.piso_id === p.piso_id)?.avanco, 0)} %</button>)}
            {m.pode_editar && piso && <>
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(e) => { enviarPlanta(e.target.files?.[0]); e.target.value = ""; }} />
              <button className={ghost} onClick={() => fileRef.current?.click()}><Upload className="h-4 w-4" /> {T.carregar_planta}</button>
              {pisoObj?.tem_planta && zonasPiso.length > 0 && <select className={`${field} w-56`} value={desenhar || ""} onChange={(e) => setDesenhar(e.target.value || null)} aria-label={T.desenhar}>
                <option value="">{T.desenhar}…</option>{zonasPiso.map((z) => <option key={z.zona_id} value={z.zona_id}>{z.nome}{z.ret ? "" : ` (${T.sem_ret})`}</option>)}</select>}
            </>}
          </div>}
          {desenhar && <p className="text-xs text-sky-700">{T.desenhar_ajuda}</p>}
          <div className="grid lg:grid-cols-[1fr_20rem] gap-4 items-start">
            <PlantaZonas client={client} base={base} piso={pisoObj} zonas={zonasPiso} resumoZonas={r.zonas} onZona={abrirZona} desenhar={!!desenhar} onRet={guardarRet} selecionada={zona} versao={plantaV} />
            <div className="grid gap-2">
              {zonaSel ? <div className="rounded-xl border p-3" data-testid="exec-zona-painel">
                <div className="flex items-center justify-between mb-2"><b>{zonaSel.nome}</b><button className="text-slate-500" onClick={() => setZona(null)} aria-label={T.fechar}><X className="h-4 w-4" /></button></div>
                {m.atividades.map((a) => { const v = edits[a.atividade_id] ?? resumoZona(zonaSel.zona_id)?.por_atividade[a.atividade_id] ?? 0; return (
                  <label key={a.atividade_id} className="block mb-2"><span className="flex justify-between text-xs"><span>{a.nome}</span><b>{num(v, 0)} %</b></span>
                    <input type="range" min={0} max={100} step={5} value={v} disabled={!m.pode_editar} onChange={(e) => setEdits((x) => ({ ...x, [a.atividade_id]: Number(e.target.value) }))} className="w-full accent-emerald-700" /></label>); })}
                {m.pode_editar && <button className={`${primary} w-full`} onClick={guardarAvanco} data-testid="exec-avanco-guardar"><Check className="h-4 w-4" /> {T.guardar_avanco}</button>}
              </div> : <ul className="rounded-xl border divide-y text-sm">{zonasPiso.map((z) => { const p = resumoZona(z.zona_id)?.avanco || 0; return (
                <li key={z.zona_id}><button type="button" className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 text-left" onClick={() => abrirZona(z.zona_id)}>
                  <span className="h-3 w-3 rounded-sm shrink-0" style={{ background: cor(p) }} /><span className="flex-1 truncate">{z.nome}</span><b>{num(p, 0)} %</b></button></li>); })}</ul>}
              <p className="text-[11px] text-slate-500 flex items-center gap-1">{[0, 30, 60, 100].map((p) => <span key={p} className="h-3 w-5 rounded-sm inline-block" style={{ background: cor(p) }} />)} {T.legenda}</p>
            </div>
          </div>
          {m.atividades.length > 0 && zonasPiso.length > 0 && <div className="overflow-x-auto"><Lbl>{T.matriz}</Lbl>
            <table className="text-xs border-collapse min-w-full"><thead><tr><th className="text-left p-1.5 bg-slate-50">{T.zona}</th>{m.atividades.map((a) => <th key={a.atividade_id} className="p-1.5 bg-slate-50 font-medium" title={a.nome}>{a.nome.length > 12 ? a.nome.slice(0, 11) + "…" : a.nome}</th>)}<th className="p-1.5 bg-slate-50">{T.media}</th></tr></thead>
              <tbody>{zonasPiso.map((z) => { const rz = resumoZona(z.zona_id); return <tr key={z.zona_id} className="border-t">
                <td className="p-1.5 font-medium whitespace-nowrap"><button type="button" className="underline-offset-2 hover:underline" onClick={() => abrirZona(z.zona_id)}>{z.nome}</button></td>
                {m.atividades.map((a) => { const v = rz?.por_atividade[a.atividade_id] || 0; return <td key={a.atividade_id} className="p-1.5 text-center" style={{ background: cor(v), color: v >= 100 ? "white" : undefined }}>{num(v, 0)}</td>; })}
                <td className="p-1.5 text-center font-semibold">{num(rz?.avanco, 0)} %</td></tr>; })}</tbody></table></div>}
        </div>}
      </section>
    </div>
  );
}

// ====================================================================== tesouraria
export function TesourariaPanel({ client, base }) {
  const [t, setT] = useState(null);
  const [mov, setMov] = useState(null);
  const [cfg, setCfg] = useState(null);
  const load = useCallback(() => client.get(`${base}/tesouraria`).then(({ data }) => setT(data)).catch((e) => { setT(false); err(e); }), [client, base]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn) => { try { await fn(); await load(); } catch (e) { err(e); } };
  if (t === null) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  if (t === false) return null;
  const k = t.kpis;
  const dados = t.meses.map((m) => ({ ...m, mes: m.mes.split("-").reverse().join("/"), saidas_n: -m.saidas, saidas_prev_n: -m.saidas_previstas }));
  const kp = [[T.recebido, k.recebido, "text-emerald-700"], [T.pago, k.pago, "text-slate-800"], [T.saldo_atual, k.saldo_atual, k.saldo_atual < 0 ? "text-red-700" : "text-emerald-800"],
    [T.por_receber, k.por_receber, "text-sky-700"], [T.por_pagar, k.por_pagar, "text-amber-700"], [T.saldo_final, k.saldo_final_previsto, k.saldo_final_previsto < 0 ? "text-red-700" : "text-slate-800"]];
  return (
    <div className="grid gap-4">
      <section className={card} data-testid="exec-tesouraria">
        <Head title={T.tesouraria} sub={T.tes_sub}>
          {!cfg && <button className={ghost} onClick={() => setCfg({ ...t.cfg })}>{T.cfg}</button>}
          {!mov && <button className={primary} onClick={() => setMov({ tipo: "saida", valor: "", data: today(), realizado: false, categoria: "subempreiteiro", descricao: "", contraparte: "" })}><Plus className="h-4 w-4" /> {T.movimento}</button>}
        </Head>
        {cfg && <div className="flex flex-wrap items-end gap-2 p-4 border-b bg-slate-50/60">
          <label><Lbl>{T.prazo_fornecedor}</Lbl><input type="number" min={0} max={180} className={`${field} w-32`} value={cfg.prazo_fornecedor} onChange={(e) => setCfg((c) => ({ ...c, prazo_fornecedor: e.target.value }))} /></label>
          <label><Lbl>{T.saldo_inicial}</Lbl><input type="number" className={`${field} w-40`} value={cfg.saldo_inicial} onChange={(e) => setCfg((c) => ({ ...c, saldo_inicial: e.target.value }))} /></label>
          <button className={primary} onClick={() => act(async () => { await client.put(`${base}/tesouraria/cfg`, { prazo_fornecedor: Number(cfg.prazo_fornecedor) || 0, saldo_inicial: Number(cfg.saldo_inicial) || 0 }); setCfg(null); })}><Check className="h-4 w-4" /> {T.guardar}</button>
          <button className={ghost} onClick={() => setCfg(null)}>{T.cancelar}</button></div>}
        {mov && <MovForm mov={mov} setMov={setMov} categorias={t.categorias} onSave={() => act(async () => {
          const body = { ...mov, valor: Number(mov.valor) };
          if (mov.mov_id) await client.put(`${base}/tesouraria/movimentos/${mov.mov_id}`, body); else await client.post(`${base}/tesouraria/movimentos`, body);
          setMov(null); })} />}
        <div className="p-4 grid gap-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">{kp.map(([l, v, c]) => <div key={l} className="rounded-xl border p-3"><p className="text-[11px] uppercase text-slate-500">{l}</p><p className={`text-lg font-bold ${c}`}>{eur(v)}</p></div>)}</div>
          {(t.alertas.length > 0 || !t.taxa_horaria) && <ul className="grid gap-1">{t.alertas.map((a) => <li key={a} className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm flex gap-2"><AlertTriangle className="h-4 w-4 text-amber-700 shrink-0 mt-0.5" />{a}</li>)}
            {!t.taxa_horaria && <li className="text-xs text-slate-500">{T.taxa_falta}</li>}</ul>}
          {dados.length === 0 ? <Empty>{T.sem_dados}</Empty> : <div className="h-80"><ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={dados} margin={{ top: 8, right: 16, bottom: 0, left: 8 }} stackOffset="sign">
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="mes" fontSize={11} /><YAxis fontSize={11} tickFormatter={(v) => `${num(v / 1000, 0)}k`} />
              <Tooltip formatter={(v) => eur(Math.abs(v))} /><Legend />
              <Bar dataKey="entradas" name={T.entradas} stackId="a" fill="#047857" /><Bar dataKey="entradas_previstas" name={T.entradas_prev} stackId="a" fill="#6ee7b7" />
              <Bar dataKey="saidas_n" name={T.saidas} stackId="a" fill="#b45309" /><Bar dataKey="saidas_prev_n" name={T.saidas_prev} stackId="a" fill="#fcd34d" />
              <Line type="monotone" dataKey="saldo" name={T.saldo} stroke="#0f172a" strokeWidth={2.5} dot />
            </ComposedChart></ResponsiveContainer></div>}
          {k.pior_saldo_data && <p className="text-sm"><b>{T.pior_saldo}:</b> <span className={k.pior_saldo < 0 ? "text-red-700 font-semibold" : ""}>{eur(k.pior_saldo)}</span> · {day(k.pior_saldo_data)}</p>}
          <ul className="text-xs text-slate-500 list-disc ps-5">{t.notas.map((n) => <li key={n}>{n}</li>)}</ul>
        </div>
      </section>
      <section className={card}>
        <Head title={T.movimentos} />
        {t.movimentos.length === 0 ? <Empty>{T.nenhum}</Empty> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr>
          <th className="text-left p-2">{T.data}</th><th className="text-left p-2">{T.categoria}</th><th className="text-left p-2">{T.descricao}</th><th className="p-2 text-right">{T.valor}</th><th className="p-2">{T.estado || ""}</th><th /></tr></thead>
          <tbody>{t.movimentos.map((m) => <tr key={m.mov_id} className="border-t"><td className="p-2">{day(m.data)}</td><td className="p-2">{t.categorias[m.categoria] || m.categoria}</td><td className="p-2">{m.descricao}{m.contraparte && <span className="text-slate-500"> · {m.contraparte}</span>}</td>
            <td className={`p-2 text-right font-semibold ${m.tipo === "entrada" ? "text-emerald-700" : "text-amber-800"}`}>{m.tipo === "entrada" ? "+" : "−"}{eur(m.valor)}</td>
            <td className="p-2 text-center"><Pill cls={m.realizado ? "bg-emerald-100 text-emerald-800" : ""}>{m.realizado ? T.realizado : T.previsto}</Pill></td>
            <td className="p-2 whitespace-nowrap text-right"><button className="text-slate-500 hover:text-slate-800 me-2" onClick={() => setMov({ ...m })} aria-label={T.editar}><PenLine className="h-4 w-4" /></button>
              <button className="text-slate-500 hover:text-red-700" onClick={() => act(() => client.delete(`${base}/tesouraria/movimentos/${m.mov_id}`))} aria-label={T.apagar}><Trash2 className="h-4 w-4" /></button></td></tr>)}</tbody></table></div>}
      </section>
      {t.eventos.length > 0 && <section className={card}><Head title={T.eventos} />
        <ul className="divide-y text-xs max-h-96 overflow-y-auto">{[...t.eventos].reverse().map((e, i) => <li key={i} className="px-4 py-2 flex flex-wrap gap-2 items-center">
          <span className="w-20">{day(e.data)}</span><Pill>{T.origens[e.origem] || e.origem}</Pill><span className="flex-1 min-w-0 truncate">{e.descricao}</span>
          {e.vencido && <Pill cls="bg-red-100 text-red-800">{T.em_atraso}</Pill>}<Pill cls={e.estado === "realizado" ? "bg-emerald-100 text-emerald-800" : ""}>{e.estado === "realizado" ? T.realizado : T.previsto}</Pill>
          <b className={e.valor >= 0 ? "text-emerald-700" : "text-amber-800"}>{e.valor >= 0 ? "+" : "−"}{eur(Math.abs(e.valor))}</b></li>)}</ul></section>}
    </div>
  );
}

function MovForm({ mov, setMov, categorias, onSave }) {
  const s = (k) => (e) => setMov((m) => ({ ...m, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  return (
    <div className="grid sm:grid-cols-6 gap-2 p-4 border-b bg-slate-50/60">
      <select className={field} value={mov.tipo} onChange={s("tipo")} aria-label={T.tipo}><option value="entrada">{T.entradas}</option><option value="saida">{T.saidas}</option></select>
      <input type="number" min={0} step="0.01" className={field} placeholder={T.valor} value={mov.valor} onChange={s("valor")} aria-label={T.valor} />
      <input type="date" className={field} value={mov.data} onChange={s("data")} aria-label={T.data} />
      <select className={field} value={mov.categoria} onChange={s("categoria")} aria-label={T.categoria}>{Object.entries(categorias).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={mov.realizado} onChange={s("realizado")} /> {T.realizado}</label>
      <span />
      <input className={`${field} sm:col-span-3`} placeholder={T.descricao} value={mov.descricao} onChange={s("descricao")} maxLength={200} />
      <input className={`${field} sm:col-span-2`} placeholder={T.contraparte} value={mov.contraparte} onChange={s("contraparte")} maxLength={120} />
      <div className="flex gap-2"><button className={primary} disabled={!(Number(mov.valor) > 0)} onClick={onSave}><Check className="h-4 w-4" /> {T.guardar}</button><button className={ghost} onClick={() => setMov(null)}><X className="h-4 w-4" /></button></div>
    </div>
  );
}

// ====================================================================== câmaras
function CamaraTile({ c }) {
  const [tick, setTick] = useState(0);
  const [falha, setFalha] = useState(false);
  useEffect(() => { if (c.tipo !== "imagem") return undefined; const id = setInterval(() => setTick((x) => x + 1), (c.atualizar_s || 30) * 1000); return () => clearInterval(id); }, [c]);
  const sep = c.url.includes("?") ? "&" : "?";
  return (
    <figure className="rounded-xl border overflow-hidden bg-slate-900">
      <div className="aspect-video grid place-items-center">
        {c.tipo === "imagem" && (falha ? <p className="text-xs text-slate-300">{T.cam_erro}</p> :
          <img src={`${c.url}${sep}_t=${tick}`} alt={c.nome} className="w-full h-full object-contain" referrerPolicy="no-referrer" onError={() => setFalha(true)} onLoad={() => setFalha(false)} />)}
        {c.tipo === "video" && <video src={c.url} className="w-full h-full" controls muted autoPlay playsInline />}
        {c.tipo === "embed" && <iframe src={c.url} title={c.nome} className="w-full h-full" allow="autoplay; fullscreen" sandbox="allow-scripts allow-same-origin allow-presentation" referrerPolicy="no-referrer" />}
      </div>
      <figcaption className="bg-white px-3 py-2 text-sm flex justify-between"><b>{c.nome}</b>{c.zona && <span className="text-xs text-slate-500">{c.zona}</span>}</figcaption>
    </figure>
  );
}

export function CamarasPanel({ client, base, podeEditar }) {
  const [c, setC] = useState(null);
  const [ed, setEd] = useState(null);
  const load = useCallback(() => client.get(`${base}/camaras`).then(({ data }) => setC(data)).catch(() => setC(false)), [client, base]);
  useEffect(() => { load(); }, [load]);
  if (c === null) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  if (c === false) return null;
  const guardar = async () => { try { const { data } = await client.put(`${base}/camaras`, { camaras: ed.map((x) => ({ ...x, atualizar_s: Number(x.atualizar_s) || 30 })) }); setC(data); setEd(null); } catch (e) { err(e); } };
  const set = (i, patch) => setEd((l) => l.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <section className={card} data-testid="exec-camaras">
      <Head title={T.camaras} sub={T.cam_sub}>{podeEditar && !ed && <button className={ghost} onClick={() => setEd(c.itens.map((x) => ({ ...x })))}><PenLine className="h-4 w-4" /> {T.editar}</button>}</Head>
      {ed && <div className="grid gap-2 p-4 border-b bg-slate-50/60">
        {ed.map((x, i) => <div key={i} className="grid sm:grid-cols-12 gap-2 items-center">
          <input className={`${field} sm:col-span-2`} placeholder={T.nome} value={x.nome} onChange={(e) => set(i, { nome: e.target.value })} />
          <select className={`${field} sm:col-span-3`} value={x.tipo} onChange={(e) => set(i, { tipo: e.target.value })}>{Object.entries(T.cam_tipos).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <input className={`${field} sm:col-span-4`} placeholder={T.url} value={x.url} onChange={(e) => set(i, { url: e.target.value })} />
          <input type="number" min={5} max={600} className={`${field} sm:col-span-1`} title={T.atualizar} value={x.atualizar_s} onChange={(e) => set(i, { atualizar_s: e.target.value })} />
          <label className="sm:col-span-1 flex items-center gap-1 text-xs" title={T.partilhar}><input type="checkbox" checked={!!x.partilhar} onChange={(e) => set(i, { partilhar: e.target.checked })} /> 👁</label>
          <button className={`${ghost} sm:col-span-1`} onClick={() => setEd((l) => l.filter((_, j) => j !== i))} aria-label={T.apagar}><Trash2 className="h-4 w-4" /></button></div>)}
        <p className="text-[11px] text-slate-500">👁 = {T.partilhar} · {T.cam_hosts} {c.hosts_embed.join(", ")}</p>
        <div className="flex gap-2">{ed.length < 12 && <button className={ghost} onClick={() => setEd((l) => [...l, { nome: "", tipo: "imagem", url: "https://", atualizar_s: 30, partilhar: false, zona: "" }])}><Plus className="h-4 w-4" /> {T.adicionar}</button>}
          <button className={primary} onClick={guardar}><Check className="h-4 w-4" /> {T.guardar}</button><button className={ghost} onClick={() => setEd(null)}>{T.cancelar}</button></div>
      </div>}
      {c.itens.length === 0 ? <Empty>{T.cam_vazio}</Empty> : <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3 p-4">{c.itens.map((x) => <CamaraTile key={x.camara_id} c={x} />)}</div>}
    </section>
  );
}

// ====================================================================== separadores (para a Gestão de obra)
export const SECOES_EXECUCAO = [
  ["assessor", T.assessor, Mic, (c) => c.assessor],
  ["mapa", T.mapa, MapIcon, (c) => c["mapa.ver"]],
  ["tesouraria", T.tesouraria, Wallet, (c) => c.tesouraria],
  ["camaras", T.camaras, Video, (c) => c["camaras.ver"]],
];

export function ExecucaoSecao({ sec, client, execBase, gestaoBase, fileBase, caps }) {
  if (sec === "assessor") return <AssessorPanel client={client} base={execBase} gestaoBase={gestaoBase} />;
  if (sec === "mapa") return <MapaPanel client={client} base={execBase} fileBase={caps["mapa.editar"] ? fileBase : null} />;
  if (sec === "tesouraria") return <TesourariaPanel client={client} base={execBase} />;
  if (sec === "camaras") return <CamarasPanel client={client} base={execBase} podeEditar={caps["camaras.editar"]} />;
  return null;
}
