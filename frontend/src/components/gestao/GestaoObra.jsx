import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { BookOpen, ShieldCheck, HelpCircle, TrendingUp, Boxes, Bot, History, Webhook, Plus, Download, Upload, Loader2, Check, X, PenLine, Eye, EyeOff, AlertTriangle, Sparkles, Send, RotateCcw } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ResponsiveContainer } from "recharts";
import { T, LOCALE, SEV_CLS } from "./txt";

/**
 * Gestão de obra — diário, qualidade e segurança, pedidos de esclarecimento, curva S e alertas, stock, copiloto,
 * histórico e webhooks. O mesmo componente serve o titular (`client` = api, `base` = /chantiers/{id}/gestao)
 * e os intervenientes do portal (`client` = portalApi, `base` = /{ref}/gestao). O servidor decide o que cada perfil
 * vê (`capacidades`); aqui só se esconde o que não é permitido.
 */
const num = (v, d = 2) => new Intl.NumberFormat(LOCALE, { maximumFractionDigits: d }).format(Number(v || 0));
const day = (s) => (s ? String(s).slice(0, 10).split("-").reverse().join("/") : "—");
const when = (s) => (s ? `${day(s)} ${String(s).slice(11, 16)}` : "—");
const today = () => new Date().toISOString().slice(0, 10);
const err = (e) => toast.error(e?.response?.data?.detail || T.erro);
const card = "rounded-2xl border border-slate-200 bg-white text-slate-900";
const field = "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-emerald-600";
const btn = "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium min-h-10 disabled:opacity-50";
const primary = `${btn} bg-emerald-700 text-white hover:bg-emerald-800`;
const ghost = `${btn} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`;
const Pill = ({ cls = "bg-slate-100 text-slate-600", children }) => <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{children}</span>;
const Empty = ({ children }) => <p className="p-6 text-center text-sm text-slate-500">{children}</p>;
const Head = ({ title, sub, children }) => (
  <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 p-4">
    <div className="min-w-0"><h3 className="font-semibold">{title}</h3>{sub && <p className="mt-0.5 text-xs text-slate-500 max-w-3xl">{sub}</p>}</div>
    <div className="flex flex-wrap gap-2">{children}</div>
  </div>
);
const Lbl = ({ children }) => <span className="mb-1 block text-xs font-medium text-slate-600">{children}</span>;
const ESTADO_CLS = { aberto: "bg-amber-100 text-amber-800", em_tratamento: "bg-sky-100 text-sky-800", fechado: "bg-emerald-100 text-emerald-800",
  respondido: "bg-sky-100 text-sky-800", rascunho: "bg-slate-100 text-slate-600", assinado: "bg-emerald-100 text-emerald-800",
  aberta: "bg-amber-100 text-amber-800", em_curso: "bg-sky-100 text-sky-800", feita: "bg-indigo-100 text-indigo-800", verificada: "bg-emerald-100 text-emerald-800" };
const GRAV_CLS = { baixa: "bg-slate-100 text-slate-600", media: "bg-amber-100 text-amber-800", alta: "bg-orange-100 text-orange-800", critica: "bg-red-100 text-red-800" };

function useGestao(client, base) {
  const [info, setInfo] = useState(null);
  const load = useCallback(() => client.get(base).then(({ data }) => setInfo(data)).catch(() => setInfo(false)), [client, base]);
  useEffect(() => { load(); }, [load]);
  return [info, load];
}

function SignaturePad({ onChange }) {
  const ref = useRef(null);
  const drawing = useRef(false);
  const dirty = useRef(false);
  const pos = (e) => { const r = ref.current.getBoundingClientRect(); const p = e.touches ? e.touches[0] : e; return [p.clientX - r.left, p.clientY - r.top]; };
  const start = (e) => { e.preventDefault(); drawing.current = true; const c = ref.current.getContext("2d"); const [x, y] = pos(e); c.beginPath(); c.moveTo(x, y); };
  const move = (e) => { if (!drawing.current) return; e.preventDefault(); const c = ref.current.getContext("2d"); c.lineWidth = 2.2; c.lineCap = "round"; c.strokeStyle = "#0f172a"; const [x, y] = pos(e); c.lineTo(x, y); c.stroke(); dirty.current = true; };
  const end = () => { if (!drawing.current) return; drawing.current = false; onChange(dirty.current ? ref.current.toDataURL("image/png") : null); };
  const clear = () => { const c = ref.current.getContext("2d"); c.clearRect(0, 0, ref.current.width, ref.current.height); dirty.current = false; onChange(null); };
  return (
    <div>
      <canvas ref={ref} width={480} height={160} className="w-full max-w-[480px] h-40 rounded-lg border border-dashed border-slate-400 bg-white touch-none"
        onMouseDown={start} onMouseMove={move} onMouseUp={end} onMouseLeave={end} onTouchStart={start} onTouchMove={move} onTouchEnd={end} data-testid="signature-pad" />
      <button type="button" className="mt-1 text-xs text-slate-500 underline" onClick={clear}>{T.limpar}</button>
    </div>
  );
}

const Voice = ({ onText }) => {
  const [C, setC] = useState(null);
  useEffect(() => { import("@/components/VoiceNoteButton").then((m) => setC(() => m.default)).catch(() => {}); }, []);
  return C ? <C onText={onText} label={T.ditar} /> : null;
};

// ====================================================================== diário
function DiarioPanel({ client, base, fileBase, info }) {
  const caps = info.capacidades;
  const [itens, setItens] = useState(null);
  const [aberto, setAberto] = useState(null);
  const [novo, setNovo] = useState(null);
  const load = useCallback(() => client.get(`${base}/diario`).then(({ data }) => setItens(data.itens)).catch(() => setItens([])), [client, base]);
  useEffect(() => { load(); }, [load]);
  const preparar = async (data) => {
    try { const { data: p } = await client.get(`${base}/diario/preparar`, { params: { data } });
      if (p.existente) { setAberto(p.existente); return; }
      setNovo({ ...p, trabalhos: "", ocorrencias: "", entregas: (p.entregas || []).map((e) => e.fornecedor).join(", "), visitas: "", observacoes: "", efetivos: [], fotos_operarios: [] });
    } catch (e) { err(e); }
  };
  const criar = async () => {
    try { const { data } = await client.post(`${base}/diario`, { data: novo.data, trabalhos: novo.trabalhos, ocorrencias: novo.ocorrencias, entregas: novo.entregas,
      visitas: novo.visitas, observacoes: novo.observacoes, efetivos: novo.efetivos.filter((x) => x.equipa), fotos_operarios: novo.fotos_operarios });
      setNovo(null); load(); setAberto(data.diario_id); } catch (e) { err(e); }
  };
  if (aberto) return <DiarioEntrada client={client} base={base} fileBase={fileBase} id={aberto} caps={caps} onBack={() => { setAberto(null); load(); }} />;
  return (
    <section className={card} data-testid="gestao-diario">
      <Head title={T.diario} sub={T.diario_sub}>
        {caps["diario.editar"] && !novo && <><input type="date" max={today()} defaultValue={today()} className={`${field} w-40`} id="gd-dia" />
          <button className={primary} onClick={() => preparar(document.getElementById("gd-dia").value || today())} data-testid="gestao-diario-novo"><Plus className="h-4 w-4" /> {T.novo_dia}</button></>}
      </Head>
      {novo && (
        <div className="grid gap-3 p-4 border-b border-slate-200 bg-slate-50/60">
          <p className="font-semibold">{day(novo.data)}</p>
          <div className="grid sm:grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-white border p-3"><Lbl>{T.meteo}</Lbl>{novo.meteo ? <p>{novo.meteo.descricao} · {novo.meteo.tmin}/{novo.meteo.tmax} °C · {novo.meteo.precipitacao_mm} mm · {novo.meteo.vento_max_kmh} km/h{novo.meteo.alerta && <span className="block text-amber-700 text-xs mt-1"><AlertTriangle className="inline h-3 w-3" /> {novo.meteo.alerta}</span>}<span className="block text-[11px] text-slate-500">{T.meteo_auto}</span></p> : <p className="text-slate-500">{T.meteo_falta}</p>}</div>
            <div className="rounded-lg bg-white border p-3"><Lbl>{T.efetivo}</Lbl><p>{T.efetivo_auto.replace("{n}", novo.efetivo_auto.trabalhadores).replace("{h}", num(novo.efetivo_auto.horas))}</p>
              {novo.efetivo_auto.pendentes > 0 && <p className="text-xs text-amber-700">{T.pendentes_ponto.replace("{n}", novo.efetivo_auto.pendentes)}</p>}
              {novo.efetivo_auto.nomes?.length > 0 && <p className="text-xs text-slate-500">{novo.efetivo_auto.nomes.join(", ")}</p>}</div>
          </div>
          <div><Lbl>{T.equipas}</Lbl>
            {novo.efetivos.map((e, i) => <div key={i} className="flex gap-2 mb-1"><input className={field} placeholder={T.equipa} value={e.equipa} onChange={(ev) => setNovo((n) => ({ ...n, efetivos: n.efetivos.map((x, j) => j === i ? { ...x, equipa: ev.target.value } : x) }))} />
              <input type="number" min={0} className={`${field} w-24`} placeholder={T.n_pessoas} value={e.n} onChange={(ev) => setNovo((n) => ({ ...n, efetivos: n.efetivos.map((x, j) => j === i ? { ...x, n: Number(ev.target.value) } : x) }))} /></div>)}
            <button type="button" className="text-xs text-emerald-700 underline" onClick={() => setNovo((n) => ({ ...n, efetivos: [...n.efetivos, { equipa: "", n: 1 }] }))}>+ {T.equipa}</button></div>
          {["trabalhos", "ocorrencias", "entregas", "visitas", "observacoes"].map((k) => (
            <label key={k}><span className="flex items-center justify-between"><Lbl>{T[k]}</Lbl><Voice onText={(t) => setNovo((n) => ({ ...n, [k]: (n[k] ? n[k] + "\n" : "") + t }))} /></span>
              <textarea className={field} rows={k === "trabalhos" ? 4 : 2} value={novo[k]} onChange={(e) => setNovo((n) => ({ ...n, [k]: e.target.value }))} data-testid={`gestao-diario-${k}`} /></label>))}
          {(novo.operarios?.notas?.length > 0 || novo.operarios?.fotos?.length > 0) && <div className="rounded-lg bg-white border p-3 text-sm"><Lbl>{T.oper_registos}</Lbl>
            {novo.operarios.notas.map((n) => <p key={n.note_id} className="text-xs">• <b>{n.worker_name}</b> ({n.type}): {n.message}</p>)}
            {novo.operarios.fotos.length > 0 && <label className="mt-2 flex items-center gap-2 text-xs"><input type="checkbox" onChange={(e) => setNovo((n) => ({ ...n, fotos_operarios: e.target.checked ? n.operarios.fotos.map((f) => f.photo_id) : [] }))} /> {T.anexar_fotos_oper} ({novo.operarios.fotos.length})</label>}</div>}
          <div className="flex gap-2"><button className={primary} onClick={criar} data-testid="gestao-diario-criar"><Check className="h-4 w-4" /> {T.criar}</button><button className={ghost} onClick={() => setNovo(null)}>{T.cancelar}</button></div>
        </div>)}
      {itens === null ? <Empty>{T.carregar}</Empty> : itens.length === 0 ? <Empty>{T.diario_vazio}</Empty> : (
        <ul className="divide-y divide-slate-100">{itens.map((d) => (
          <li key={d.diario_id}><button type="button" className="w-full text-left flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-slate-50" onClick={() => setAberto(d.diario_id)} data-testid={`gestao-diario-${d.data}`}>
            <span className="font-semibold w-24">{day(d.data)}</span>
            <span className="text-sm text-slate-600 flex-1 min-w-0 truncate">{d.trabalhos || "—"}</span>
            {d.meteo && <span className="text-xs text-slate-500">{d.meteo.descricao} {d.meteo.tmax}°</span>}
            <span className="text-xs text-slate-500">{d.efetivo_auto?.trabalhadores || 0} 👷 · {d.fotos.length} 📷</span>
            <Pill cls={ESTADO_CLS[d.estado]}>{d.estado === "assinado" ? T.assinado : T.rascunho}</Pill>
            {d.visto_fiscal && <Pill cls="bg-emerald-100 text-emerald-800">{T.visto}</Pill>}
            {caps.historico && <Pill>{d.publicado ? T.publicado : T.privado}</Pill>}
          </button></li>))}</ul>)}
    </section>
  );
}

function DiarioEntrada({ client, base, fileBase, id, caps, onBack }) {
  const [d, setD] = useState(null);
  const [edit, setEdit] = useState(null);
  const [sig, setSig] = useState(null);
  const [nome, setNome] = useState("");
  const [assinar, setAssinar] = useState(false);
  const [adit, setAdit] = useState("");
  const [vistoObs, setVistoObs] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => client.get(`${base}/diario/${id}`).then(({ data }) => { setD(data); setEdit(null); }).catch(err), [client, base, id]);
  useEffect(() => { load(); }, [load]);
  if (!d) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  const editavel = caps["diario.editar"] && d.estado === "rascunho";
  const act = async (fn) => { setBusy(true); try { await fn(); await load(); } catch (e) { err(e); } finally { setBusy(false); } };
  const foto = (e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); act(() => client.post(`${base}/diario/${id}/fotos`, fd)); e.target.value = ""; };
  return (
    <section className={card} data-testid="gestao-diario-entrada">
      <Head title={`${T.diario} — ${day(d.data)}`} sub={d.assinatura ? `${T.assinado}: ${d.assinatura.nome} · ${when(d.assinatura.at)}` : T.rascunho}>
        <button className={ghost} onClick={onBack}>←</button>
        <a className={ghost} href={`${fileBase}/diario/${id}/pdf`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> {T.pdf}</a>
        {caps["diario.editar"] && <button className={ghost} disabled={busy} onClick={() => act(() => client.post(`${base}/diario/${id}/publicar`, { publicado: !d.publicado }))}>{d.publicado ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />} {d.publicado ? T.despublicar : T.publicar}</button>}
        {editavel && <button className={primary} onClick={() => setAssinar(true)} data-testid="gestao-diario-assinar"><PenLine className="h-4 w-4" /> {T.assinar}</button>}
      </Head>
      <div className="grid gap-3 p-4 text-sm">
        <p><b>{T.meteo}:</b> {d.meteo ? `${d.meteo.descricao} · ${d.meteo.tmin}/${d.meteo.tmax} °C · ${d.meteo.precipitacao_mm} mm · ${d.meteo.vento_max_kmh} km/h` : T.meteo_falta}</p>
        <p><b>{T.efetivo}:</b> {T.efetivo_auto.replace("{n}", d.efetivo_auto?.trabalhadores || 0).replace("{h}", num(d.efetivo_auto?.horas))}{(d.efetivos || []).length > 0 && ` — ${d.efetivos.map((e) => `${e.equipa}: ${e.n}`).join("; ")}`}</p>
        {["trabalhos", "ocorrencias", "entregas", "visitas", "observacoes"].map((k) => edit ? (
          <label key={k}><Lbl>{T[k]}</Lbl><textarea className={field} rows={k === "trabalhos" ? 4 : 2} value={edit[k] || ""} onChange={(e) => setEdit((x) => ({ ...x, [k]: e.target.value }))} /></label>
        ) : d[k] ? <div key={k}><Lbl>{T[k]}</Lbl><p className="whitespace-pre-wrap">{d[k]}</p></div> : null)}
        {editavel && (edit ? <div className="flex gap-2"><button className={primary} disabled={busy} onClick={() => act(() => client.put(`${base}/diario/${id}`, { ...edit, expected_version: d.versao || 0 }))}>{T.guardar}</button><button className={ghost} onClick={() => setEdit(null)}>{T.cancelar}</button></div>
          : <button className={`${ghost} w-fit`} onClick={() => setEdit({ trabalhos: d.trabalhos, ocorrencias: d.ocorrencias, entregas: d.entregas, visitas: d.visitas, observacoes: d.observacoes })}><PenLine className="h-4 w-4" /> {T.editar}</button>)}
        <div><Lbl>{T.fotos} ({d.fotos.length})</Lbl>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">{d.fotos.map((f) => <a key={f.n} href={`${fileBase}/diario/${id}/fotos/${f.n}`} target="_blank" rel="noreferrer"><img src={`${fileBase}/diario/${id}/fotos/${f.n}`} alt={f.filename || T.foto} loading="lazy" className="h-24 w-full object-cover rounded-md border" /></a>)}</div>
          {editavel && <label className={`${ghost} mt-2 w-fit cursor-pointer`}><Upload className="h-4 w-4" /> {T.foto}<input type="file" accept="image/*" capture="environment" className="hidden" onChange={foto} /></label>}</div>
        {(d.aditamentos || []).length > 0 && <div><Lbl>{T.aditamento}</Lbl>{d.aditamentos.map((a, i) => <p key={i} className="text-xs border-l-2 border-amber-400 pl-2 mb-1"><b>{when(a.at)} — {a.por?.nome}</b>: {a.texto}</p>)}</div>}
        {caps["diario.editar"] && d.estado === "assinado" && <div className="flex gap-2"><input className={field} placeholder={T.aditamento_ph} value={adit} onChange={(e) => setAdit(e.target.value)} />
          <button className={ghost} disabled={!adit.trim() || busy} onClick={() => act(async () => { await client.post(`${base}/diario/${id}/aditamento`, { texto: adit }); setAdit(""); })}><Plus className="h-4 w-4" /></button></div>}
        {d.assinatura && <img src={`${fileBase}/diario/${id}/assinatura`} alt="" className="h-16 w-auto" />}
        {d.visto_fiscal ? <p className="text-emerald-700"><Check className="inline h-4 w-4" /> {T.visto}: {d.visto_fiscal.nome} · {when(d.visto_fiscal.at)}{d.visto_fiscal.observacao && ` — ${d.visto_fiscal.observacao}`}</p>
          : caps["diario.visar"] && d.estado === "assinado" && <div className="flex gap-2"><input className={field} placeholder={T.visto_obs} value={vistoObs} onChange={(e) => setVistoObs(e.target.value)} />
            <button className={primary} disabled={busy} onClick={() => act(() => client.post(`${base}/diario/${id}/visto`, { observacao: vistoObs }))}><Check className="h-4 w-4" /> {T.dar_visto}</button></div>}
      </div>
      {assinar && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-lg rounded-2xl bg-white p-5 grid gap-3">
            <h4 className="font-semibold">{T.assinar_titulo}</h4>
            <p className="text-xs text-amber-700">{T.assinar_aviso}</p>
            <label><Lbl>{T.nome_assinante}</Lbl><input className={field} value={nome} onChange={(e) => setNome(e.target.value)} /></label>
            <div><Lbl>{T.desenhe}</Lbl><SignaturePad onChange={setSig} /></div>
            <div className="flex gap-2 justify-end"><button className={ghost} onClick={() => setAssinar(false)}>{T.cancelar}</button>
              <button className={primary} disabled={!sig || nome.trim().length < 2 || busy} onClick={() => act(async () => { await client.post(`${base}/diario/${id}/assinar`, { nome, imagem: sig }); setAssinar(false); })} data-testid="gestao-diario-confirmar-assinatura"><PenLine className="h-4 w-4" /> {T.assinar}</button></div>
          </div>
        </div>)}
    </section>
  );
}

// ====================================================================== qualidade e segurança
const ACAO_VAZIA = { o_que: "", porque: "", quem: "", quem_empresa_id: "", onde: "", quando: "", como: "", quanto: "" };
function AcaoForm({ empresas, onSave, onCancel }) {
  const [a, setA] = useState(ACAO_VAZIA);
  const set = (k) => (e) => setA((x) => ({ ...x, [k]: e.target.value }));
  return (
    <div className="grid sm:grid-cols-2 gap-2 rounded-lg border border-emerald-200 bg-emerald-50/40 p-3">
      {["o_que", "porque", "quem", "onde", "como"].map((k) => <label key={k} className={k === "o_que" || k === "como" ? "sm:col-span-2" : ""}><Lbl>{T[k]} *</Lbl><input className={field} value={a[k]} onChange={set(k)} /></label>)}
      <label><Lbl>{T.quando} *</Lbl><input type="date" className={field} value={a.quando} onChange={set("quando")} /></label>
      <label><Lbl>{T.quanto}</Lbl><input type="number" min={0} step="0.01" className={field} value={a.quanto} onChange={set("quanto")} /></label>
      {empresas.length > 0 && <label className="sm:col-span-2"><Lbl>{T.responsavel}</Lbl><select className={field} value={a.quem_empresa_id} onChange={set("quem_empresa_id")}><option value="">—</option>{empresas.map((e) => <option key={e.id} value={e.id}>{e.nome}{e.lote ? ` · ${e.lote}` : ""}</option>)}</select></label>}
      <div className="sm:col-span-2 flex gap-2"><button className={primary} onClick={() => onSave({ ...a, quem_empresa_id: a.quem_empresa_id || null, quanto: a.quanto === "" ? null : Number(a.quanto) })}><Check className="h-4 w-4" /> {T.guardar}</button>{onCancel && <button className={ghost} onClick={onCancel}>{T.cancelar}</button>}</div>
    </div>
  );
}

function QsePanel({ client, base, fileBase, info, gestor }) {
  const caps = info.capacidades;
  const R = info.referenciais;
  const empresas = info.intervenientes.filter((p) => p.perfil === "empresa");
  const [itens, setItens] = useState(null);
  const [filtro, setFiltro] = useState("");
  const [aberto, setAberto] = useState(null);
  const [novo, setNovo] = useState(null);
  const [ops, setOps] = useState([]);
  const load = useCallback(() => client.get(`${base}/qse`, { params: filtro ? { tipo: filtro } : {} }).then(({ data }) => setItens(data.itens)).catch(() => setItens([])), [client, base, filtro]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (gestor) client.get(`${base}/qse-operarios`).then(({ data }) => setOps(data.itens)).catch(() => {}); }, [client, base, gestor, itens]);
  const criar = async () => {
    try { const body = { ...novo, acoes: novo.acao ? [novo.acao] : [], participantes: (novo.participantesTxt || "").split("\n"), dias_baixa: novo.dias_baixa === "" || novo.dias_baixa == null ? null : Number(novo.dias_baixa), gravidade: novo.gravidade || null, empresa_id: novo.empresa_id || null };
      delete body.acao; delete body.participantesTxt;
      const { data } = await client.post(`${base}/qse`, body); setNovo(null); setAberto(data.item_id); load(); } catch (e) { err(e); }
  };
  if (aberto) return <QseItem client={client} base={base} fileBase={fileBase} id={aberto} info={info} onBack={() => { setAberto(null); load(); }} />;
  return (
    <section className={card} data-testid="gestao-qse">
      <Head title={T.qse} sub={T.qse_sub}>
        <select className={`${field} w-56`} value={filtro} onChange={(e) => setFiltro(e.target.value)}><option value="">{T.todos}</option>{Object.entries(R.qse_tipos).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
        <a className={ghost} href={`${fileBase}/qse/registo.pdf`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> {T.registo_pdf}</a>
        {caps["qse.criar"] && !novo && <button className={primary} onClick={() => setNovo({ tipo: "nao_conformidade", titulo: "", descricao: "", gravidade: "media", lote: "", local: "", data: today(), checklist_modelo: "" })} data-testid="gestao-qse-novo"><Plus className="h-4 w-4" /> {T.novo_registo}</button>}
      </Head>
      {gestor && ops.length > 0 && <div className="p-4 border-b border-amber-200 bg-amber-50"><p className="text-sm font-semibold mb-2"><AlertTriangle className="inline h-4 w-4 text-amber-600" /> {T.alertas_operarios} ({ops.length})</p>
        {ops.map((o) => <div key={o.note_id} className="flex flex-wrap items-center gap-2 text-sm mb-1"><span className="flex-1 min-w-0">{when(o.created_at)} · <b>{o.worker_name}</b>: {o.message}</span>
          {["quase_acidente", "incidente", "nao_conformidade"].map((t) => <button key={t} className={ghost} onClick={async () => { try { await client.post(`${base}/qse-operarios/${o.note_id}`, { tipo: t, gravidade: t === "incidente" ? "alta" : "media" }); load(); } catch (e) { err(e); } }}>{T.qualificar}: {R.qse_tipos[t]}</button>)}</div>)}</div>}
      {novo && (
        <div className="grid sm:grid-cols-2 gap-3 p-4 border-b border-slate-200 bg-slate-50/60">
          <label><Lbl>{T.tipo}</Lbl><select className={field} value={novo.tipo} onChange={(e) => setNovo((n) => ({ ...n, tipo: e.target.value }))} data-testid="gestao-qse-tipo">{Object.entries(R.qse_tipos).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          <label><Lbl>{T.gravidade}</Lbl><select className={field} value={novo.gravidade} onChange={(e) => setNovo((n) => ({ ...n, gravidade: e.target.value }))}>{Object.entries(R.gravidade).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
          {R.lembretes[novo.tipo] && <p className="sm:col-span-2 text-xs rounded-lg bg-sky-50 border border-sky-200 p-2 text-sky-900"><b>{T.lembrete}:</b> {R.lembretes[novo.tipo]}</p>}
          <label className="sm:col-span-2"><Lbl>{T.titulo} *</Lbl><input className={field} value={novo.titulo} onChange={(e) => setNovo((n) => ({ ...n, titulo: e.target.value }))} data-testid="gestao-qse-titulo" /></label>
          {novo.tipo === "inspecao" && <label className="sm:col-span-2"><Lbl>{T.modelo}</Lbl><select className={field} value={novo.checklist_modelo} onChange={(e) => setNovo((n) => ({ ...n, checklist_modelo: e.target.value, titulo: n.titulo || R.checklists[e.target.value]?.label || "" }))}><option value="">—</option>
            {Object.entries(R.tipos_obra).map(([k, t]) => <optgroup key={k} label={t.label}>{t.fases.map((f) => <option key={`${k}-${f}`} value={f}>{R.checklists[f].label}</option>)}</optgroup>)}</select></label>}
          {novo.tipo === "dialogo_seguranca" && <><label><Lbl>{T.tema}</Lbl><input list="gd-dds" className={field} value={novo.tema || ""} onChange={(e) => setNovo((n) => ({ ...n, tema: e.target.value, titulo: n.titulo || e.target.value }))} /><datalist id="gd-dds">{R.dds_temas.map((t) => <option key={t} value={t} />)}</datalist></label>
            <label><Lbl>{T.participantes}</Lbl><textarea className={field} rows={3} value={novo.participantesTxt || ""} onChange={(e) => setNovo((n) => ({ ...n, participantesTxt: e.target.value }))} /></label></>}
          {novo.tipo === "incidente" && <label><Lbl>{T.dias_baixa}</Lbl><input type="number" min={0} className={field} value={novo.dias_baixa ?? ""} onChange={(e) => setNovo((n) => ({ ...n, dias_baixa: e.target.value }))} /></label>}
          <label><Lbl>{T.data}</Lbl><input type="date" max={today()} className={field} value={novo.data} onChange={(e) => setNovo((n) => ({ ...n, data: e.target.value }))} /></label>
          <label><Lbl>{T.lote}</Lbl><input className={field} value={novo.lote} onChange={(e) => setNovo((n) => ({ ...n, lote: e.target.value }))} /></label>
          <label><Lbl>{T.local}</Lbl><input className={field} value={novo.local} onChange={(e) => setNovo((n) => ({ ...n, local: e.target.value }))} /></label>
          {gestor && empresas.length > 0 && <label><Lbl>{T.empresa}</Lbl><select className={field} value={novo.empresa_id || ""} onChange={(e) => setNovo((n) => ({ ...n, empresa_id: e.target.value }))}><option value="">—</option>{empresas.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}</select></label>}
          <label className="sm:col-span-2"><Lbl>{T.descricao}</Lbl><textarea className={field} rows={3} value={novo.descricao} onChange={(e) => setNovo((n) => ({ ...n, descricao: e.target.value }))} /></label>
          {["nao_conformidade", "incidente", "quase_acidente", "ambiente"].includes(novo.tipo) && <div className="sm:col-span-2"><Lbl>{T.acoes}</Lbl>
            {novo.acao ? <p className="text-xs text-emerald-700"><Check className="inline h-3 w-3" /> {novo.acao.o_que} — {novo.acao.quem} · {day(novo.acao.quando)}</p> : <AcaoForm empresas={gestor ? empresas : []} onSave={(a) => setNovo((n) => ({ ...n, acao: a }))} />}</div>}
          <div className="sm:col-span-2 flex gap-2"><button className={primary} disabled={novo.titulo.trim().length < 2} onClick={criar} data-testid="gestao-qse-criar"><Check className="h-4 w-4" /> {T.criar}</button><button className={ghost} onClick={() => setNovo(null)}>{T.cancelar}</button></div>
        </div>)}
      {itens === null ? <Empty>{T.carregar}</Empty> : itens.length === 0 ? <Empty>{T.nenhum}</Empty> : (
        <ul className="divide-y divide-slate-100">{itens.map((q) => (
          <li key={q.item_id}><button type="button" className="w-full text-left flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-slate-50" onClick={() => setAberto(q.item_id)}>
            <span className="text-xs font-mono text-slate-500 w-28">{q.ref_label}</span>
            <span className="flex-1 min-w-0 truncate text-sm font-medium">{q.titulo}</span>
            {q.resultado?.conformidade_pct != null && <span className="text-xs">{T.conformidade} {q.resultado.conformidade_pct} %</span>}
            {q.gravidade && <Pill cls={GRAV_CLS[q.gravidade]}>{R.gravidade[q.gravidade]}</Pill>}
            {q.acoes_em_atraso > 0 && <Pill cls="bg-red-100 text-red-800">{q.acoes_em_atraso} {T.atraso}</Pill>}
            <Pill cls={ESTADO_CLS[q.estado]}>{R.qse_estados[q.estado]}</Pill>
            <span className="text-xs text-slate-500">{day(q.data)}</span>
          </button></li>))}</ul>)}
    </section>
  );
}

function QseItem({ client, base, fileBase, id, info, onBack }) {
  const caps = info.capacidades;
  const R = info.referenciais;
  const empresas = info.intervenientes.filter((p) => p.perfil === "empresa");
  const [q, setQ] = useState(null);
  const [ck, setCk] = useState(null);
  const [novaAcao, setNovaAcao] = useState(false);
  const [just, setJust] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => client.get(`${base}/qse/${id}`).then(({ data }) => { setQ(data); setCk(data.checklist); }).catch(err), [client, base, id]);
  useEffect(() => { load(); }, [load]);
  if (!q) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  const act = async (fn) => { setBusy(true); try { await fn(); await load(); } catch (e) { err(e); } finally { setBusy(false); } };
  const gestao = caps["qse.gerir"];
  const fechado = q.estado === "fechado";
  const foto = (e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); act(() => client.post(`${base}/qse/${id}/fotos`, fd)); e.target.value = ""; };
  return (
    <section className={card} data-testid="gestao-qse-item">
      <Head title={`${q.ref_label} — ${q.titulo}`} sub={`${R.qse_tipos[q.tipo]} · ${day(q.data)}${q.lote ? ` · ${q.lote}` : ""}${q.local ? ` · ${q.local}` : ""}`}>
        <button className={ghost} onClick={onBack}>←</button>
        <Pill cls={ESTADO_CLS[q.estado]}>{R.qse_estados[q.estado]}</Pill>
        {gestao && fechado && <button className={ghost} disabled={busy} onClick={() => act(() => client.post(`${base}/qse/${id}/reabrir`))}><RotateCcw className="h-4 w-4" /> {T.reabrir}</button>}
      </Head>
      <div className="grid gap-4 p-4 text-sm">
        {R.lembretes[q.tipo] && <p className="text-xs rounded-lg bg-sky-50 border border-sky-200 p-2 text-sky-900"><b>{T.lembrete}:</b> {R.lembretes[q.tipo]}</p>}
        {q.descricao && <p className="whitespace-pre-wrap">{q.descricao}</p>}
        {q.tema && <p><b>{T.tema}:</b> {q.tema}</p>}
        {q.participantes?.length > 0 && <p><b>{T.participantes.split(" (")[0]}:</b> {q.participantes.join(", ")}</p>}
        {ck?.length > 0 && <div><Lbl>{T.checklist}{q.resultado?.conformidade_pct != null && ` — ${T.conformidade} ${q.resultado.conformidade_pct} %`}</Lbl>
          <div className="divide-y rounded-lg border">{ck.map((c, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2 px-3 py-2"><span className="flex-1 min-w-[12rem]">{c.item}</span>
              {["ok", "nok", "na"].map((r) => <button key={r} type="button" disabled={fechado || !(gestao || caps["qse.criar"])} onClick={() => setCk((x) => x.map((y, j) => j === i ? { ...y, resultado: r } : y))}
                className={`rounded-md px-2 py-1 text-xs border ${c.resultado === r ? (r === "ok" ? "bg-emerald-600 text-white" : r === "nok" ? "bg-red-600 text-white" : "bg-slate-500 text-white") : "bg-white"}`}>{T[r]}</button>)}
              {c.resultado === "nok" && <input className={`${field} sm:w-64`} placeholder={T.observacoes} value={c.obs || ""} disabled={fechado} onChange={(e) => setCk((x) => x.map((y, j) => j === i ? { ...y, obs: e.target.value } : y))} />}
            </div>))}</div>
          {!fechado && <div className="flex gap-2 mt-2"><button className={primary} disabled={busy} onClick={() => act(() => client.put(`${base}/qse/${id}`, { checklist: ck }))}>{T.guardar}</button>
            {gestao && q.tipo === "inspecao" && (q.resultado?.nok || 0) > 0 && <button className={ghost} disabled={busy} onClick={() => act(async () => { const { data } = await client.post(`${base}/qse/${id}/gerar-nc`); toast.success(`NC: ${data.criadas.join(", ") || "—"}`); })}>{T.gerar_nc}</button>}</div>}</div>}
        <div><Lbl>{T.fotos} ({q.fotos.length})</Lbl>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">{q.fotos.map((f) => <div key={f.n} className="relative"><a href={`${fileBase}/qse/${id}/fotos/${f.n}`} target="_blank" rel="noreferrer"><img src={`${fileBase}/qse/${id}/fotos/${f.n}`} alt={f.filename || T.foto} className="h-24 w-full object-cover rounded-md border" /></a>
            {caps["qse.criar"] && <button type="button" title={T.analisar_ia} className="absolute bottom-1 right-1 rounded-md bg-white/90 p-1" disabled={busy} onClick={() => act(() => client.post(`${base}/qse/${id}/analisar-foto/${f.n}`))}><Sparkles className="h-4 w-4 text-violet-600" /></button>}</div>)}</div>
          {!fechado && caps["qse.criar"] && <label className={`${ghost} mt-2 w-fit cursor-pointer`}><Upload className="h-4 w-4" /> {T.foto}<input type="file" accept="image/*" capture="environment" className="hidden" onChange={foto} /></label>}</div>
        {(q.analises_ia || []).map((a, i) => <div key={i} className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-xs"><p className="font-semibold mb-1"><Sparkles className="inline h-3 w-3" /> {T.analise_ia} — {T.foto} {a.n + 1}{a.gravidade && ` · ${R.gravidade[a.gravidade] || a.gravidade}`}</p>
          {[["perigos", T.perigos], ["nao_conformidades", T.ncs], ["medidas", T.medidas]].map(([k, l]) => a[k]?.length > 0 && <p key={k}><b>{l}:</b> {a[k].join(" · ")}</p>)}</div>)}
        {["nao_conformidade", "incidente", "quase_acidente", "ambiente"].includes(q.tipo) && <div><Lbl>{T.acoes}</Lbl>
          {(q.acoes || []).length === 0 && <p className="text-slate-500 text-xs">{T.nenhum}</p>}
          <div className="grid gap-2">{(q.acoes || []).map((a) => {
            const resp = info.eu.empresa_id && a.quem_empresa_id === info.eu.empresa_id;
            const atraso = a.quando && a.quando < today() && !["feita", "verificada"].includes(a.estado);
            return (
              <div key={a.acao_id} className="rounded-lg border p-3">
                <div className="flex flex-wrap items-center gap-2"><b className="flex-1 min-w-0">{a.o_que}</b><Pill cls={ESTADO_CLS[a.estado]}>{R.acao_estados[a.estado]}</Pill>{atraso && <Pill cls="bg-red-100 text-red-800">{T.atraso}</Pill>}</div>
                <p className="text-xs text-slate-600 mt-1">{T.porque}: {a.porque} · {T.quem}: {a.quem} · {T.onde}: {a.onde} · {T.quando}: {day(a.quando)} · {T.como}: {a.como}{a.quanto != null && ` · ${T.quanto}: ${num(a.quanto)}`}</p>
                {!fechado && (gestao || resp) && <div className="flex flex-wrap gap-1 mt-2">
                  {a.estado === "aberta" && <button className={ghost} onClick={() => act(() => client.patch(`${base}/qse/${id}/acoes/${a.acao_id}`, { estado: "em_curso" }))}>{R.acao_estados.em_curso}</button>}
                  {["aberta", "em_curso"].includes(a.estado) && <button className={ghost} onClick={() => act(() => client.patch(`${base}/qse/${id}/acoes/${a.acao_id}`, { estado: "feita" }))}>{R.acao_estados.feita}</button>}
                  {gestao && a.estado === "feita" && <><button className={primary} onClick={() => act(() => client.patch(`${base}/qse/${id}/acoes/${a.acao_id}`, { estado: "verificada" }))}><Check className="h-4 w-4" /> {R.acao_estados.verificada}</button>
                    <button className={ghost} onClick={() => act(() => client.patch(`${base}/qse/${id}/acoes/${a.acao_id}`, { estado: "em_curso" }))}><X className="h-4 w-4" /> {R.acao_estados.em_curso}</button></>}
                </div>}
              </div>);
          })}</div>
          {!fechado && (gestao || q.autor?.id === info.eu.id) && (novaAcao ? <div className="mt-2"><AcaoForm empresas={gestao ? empresas : []} onCancel={() => setNovaAcao(false)} onSave={(a) => act(async () => { await client.post(`${base}/qse/${id}/acoes`, a); setNovaAcao(false); })} /></div>
            : <button className={`${ghost} mt-2`} onClick={() => setNovaAcao(true)}><Plus className="h-4 w-4" /> {T.nova_acao}</button>)}</div>}
        {gestao && !fechado && <div className="flex flex-wrap gap-2 items-end border-t pt-3"><label className="flex-1 min-w-[16rem]"><Lbl>{T.justificacao}</Lbl><input className={field} value={just} onChange={(e) => setJust(e.target.value)} /></label>
          <button className={primary} disabled={busy} onClick={() => act(() => client.post(`${base}/qse/${id}/fechar`, { justificacao: just }))} data-testid="gestao-qse-fechar"><Check className="h-4 w-4" /> {T.fechar_reg}</button></div>}
        {q.fecho && <p className="text-xs text-emerald-700">{T.fechar}: {q.fecho.por?.nome} · {when(q.fecho.at)}{q.fecho.justificacao && ` — ${q.fecho.justificacao}`}</p>}
      </div>
    </section>
  );
}

// ====================================================================== pedidos de esclarecimento
function RfiPanel({ client, base, fileBase, info }) {
  const caps = info.capacidades;
  const R = info.referenciais;
  const [itens, setItens] = useState(null);
  const [novo, setNovo] = useState(null);
  const [aberto, setAberto] = useState(null);
  const [resp, setResp] = useState("");
  const load = useCallback(() => client.get(`${base}/rfi`).then(({ data }) => setItens(data.itens)).catch(() => setItens([])), [client, base]);
  useEffect(() => { load(); }, [load]);
  const criar = async () => {
    const [kind, val] = (novo.dest || "").split(":");
    try { await client.post(`${base}/rfi`, { assunto: novo.assunto, pergunta: novo.pergunta, lote: novo.lote || "", prazo: novo.prazo || null, visibilidade: novo.visibilidade,
      impacto_custo: !!novo.impacto_custo, impacto_prazo: !!novo.impacto_prazo, destinatario_perfil: kind === "perfil" ? val : null, destinatario_id: kind === "id" ? val : null });
      setNovo(null); load(); } catch (e) { err(e); }
  };
  const act = async (fn) => { try { await fn(); await load(); } catch (e) { err(e); } };
  return (
    <section className={card} data-testid="gestao-rfi">
      <Head title={T.rfi} sub={T.rfi_sub}>{caps["rfi.criar"] && !novo && <button className={primary} onClick={() => setNovo({ assunto: "", pergunta: "", visibilidade: "todos", dest: "perfil:fiscalizacao", prazo: "" })} data-testid="gestao-rfi-novo"><Plus className="h-4 w-4" /> {T.novo_rfi}</button>}</Head>
      {novo && <div className="grid sm:grid-cols-2 gap-3 p-4 border-b bg-slate-50/60">
        <label className="sm:col-span-2"><Lbl>{T.assunto} *</Lbl><input className={field} value={novo.assunto} onChange={(e) => setNovo((n) => ({ ...n, assunto: e.target.value }))} data-testid="gestao-rfi-assunto" /></label>
        <label className="sm:col-span-2"><Lbl>{T.pergunta} *</Lbl><textarea className={field} rows={3} value={novo.pergunta} onChange={(e) => setNovo((n) => ({ ...n, pergunta: e.target.value }))} data-testid="gestao-rfi-pergunta" /></label>
        <label><Lbl>{T.destinatario}</Lbl><select className={field} value={novo.dest} onChange={(e) => setNovo((n) => ({ ...n, dest: e.target.value }))}>
          {Object.entries(T.perfil_dest).map(([k, l]) => <option key={k} value={`perfil:${k}`}>{l}</option>)}
          {info.intervenientes.map((p) => <option key={p.id} value={`id:${p.id}`}>{p.nome}{p.lote ? ` · ${p.lote}` : ""}</option>)}</select></label>
        <label><Lbl>{T.prazo}</Lbl><input type="date" className={field} value={novo.prazo} onChange={(e) => setNovo((n) => ({ ...n, prazo: e.target.value }))} /></label>
        <label><Lbl>{T.lote}</Lbl><input className={field} value={novo.lote || ""} onChange={(e) => setNovo((n) => ({ ...n, lote: e.target.value }))} /></label>
        <label><Lbl>{T.visibilidade}</Lbl><select className={field} value={novo.visibilidade} onChange={(e) => setNovo((n) => ({ ...n, visibilidade: e.target.value }))}><option value="todos">{T.vis_todos}</option><option value="restrito">{T.vis_restrito}</option></select></label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!novo.impacto_custo} onChange={(e) => setNovo((n) => ({ ...n, impacto_custo: e.target.checked }))} /> {T.impacto_custo}</label>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!novo.impacto_prazo} onChange={(e) => setNovo((n) => ({ ...n, impacto_prazo: e.target.checked }))} /> {T.impacto_prazo}</label>
        <div className="sm:col-span-2 flex gap-2"><button className={primary} disabled={novo.assunto.trim().length < 3 || novo.pergunta.trim().length < 3} onClick={criar} data-testid="gestao-rfi-criar"><Send className="h-4 w-4" /> {T.enviar}</button><button className={ghost} onClick={() => setNovo(null)}>{T.cancelar}</button></div>
      </div>}
      {itens === null ? <Empty>{T.carregar}</Empty> : itens.length === 0 ? <Empty>{T.rfi_vazio}</Empty> : <ul className="divide-y divide-slate-100">{itens.map((r) => (
        <li key={r.rfi_id} className="px-4 py-3">
          <button type="button" className="w-full text-left flex flex-wrap items-center gap-3" onClick={() => setAberto(aberto === r.rfi_id ? null : r.rfi_id)}>
            <span className="font-mono text-xs w-16">{r.numero}</span><span className="flex-1 min-w-0 truncate text-sm font-medium">{r.assunto}</span>
            <span className="text-xs text-slate-500">{r.autor?.nome} → {r.destinatario?.nome || "—"}</span>
            {r.prazo && <span className={`text-xs ${r.em_atraso ? "text-red-700 font-semibold" : "text-slate-500"}`}>{day(r.prazo)}</span>}
            <Pill cls={ESTADO_CLS[r.estado]}>{R.rfi_estados[r.estado]}</Pill></button>
          {aberto === r.rfi_id && <div className="mt-3 grid gap-2 text-sm">
            <p className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3">{r.pergunta}</p>
            {(r.impacto?.custo || r.impacto?.prazo) && <p className="text-xs text-amber-700">{r.impacto.custo && T.impacto_custo}{r.impacto.custo && r.impacto.prazo && " · "}{r.impacto.prazo && T.impacto_prazo}</p>}
            {r.respostas.map((x, i) => <div key={i} className={`rounded-lg p-3 ${x.e_resposta ? "bg-emerald-50 border border-emerald-200" : "bg-white border"}`}><p className="text-xs text-slate-500">{x.por?.nome} · {when(x.at)}</p><p className="whitespace-pre-wrap">{x.texto}</p></div>)}
            {r.anexos.length > 0 && <p className="text-xs">{r.anexos.map((a) => <a key={a.n} className="underline mr-3" href={`${fileBase}/rfi/${r.rfi_id}/anexos/${a.n}`} target="_blank" rel="noreferrer">{a.filename}</a>)}</p>}
            {r.pode_responder && <div className="flex gap-2"><textarea className={field} rows={2} value={resp} onChange={(e) => setResp(e.target.value)} placeholder={T.resposta} />
              <button className={primary} disabled={!resp.trim()} onClick={() => act(async () => { await client.post(`${base}/rfi/${r.rfi_id}/respostas`, { texto: resp }); setResp(""); })}><Send className="h-4 w-4" /></button></div>}
            <div className="flex gap-2">{r.estado !== "fechado" && <label className={`${ghost} cursor-pointer`}><Upload className="h-4 w-4" /> {T.anexo}<input type="file" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; const fd = new FormData(); fd.append("file", f); act(() => client.post(`${base}/rfi/${r.rfi_id}/anexos`, fd)); e.target.value = ""; }} /></label>}
              {r.pode_fechar && <button className={ghost} onClick={() => act(() => client.post(`${base}/rfi/${r.rfi_id}/fechar`))}><Check className="h-4 w-4" /> {T.fechar}</button>}</div>
          </div>}
        </li>))}</ul>}
    </section>
  );
}

// ====================================================================== curva S e alertas
export function AlertasResumo({ client, base, max = 4, onOpen }) {
  const [al, setAl] = useState(null);
  useEffect(() => { client.get(`${base}/alertas`).then(({ data }) => setAl(data.itens)).catch(() => setAl(null)); }, [client, base]);
  if (!al || al.length === 0) return null;
  return (
    <section className={`${card} p-4`} data-testid="gestao-alertas-resumo">
      <div className="flex items-center gap-2 mb-2"><AlertTriangle className="h-4 w-4 text-amber-600" /><p className="font-semibold text-sm">{T.alertas} ({al.length})</p>{onOpen && <button className="ms-auto text-xs underline text-emerald-700" onClick={onOpen}>{T.abrir}</button>}</div>
      <ul className="grid gap-1">{al.slice(0, max).map((a, i) => <li key={i} className="text-sm flex gap-2 items-start"><Pill cls={SEV_CLS[a.severidade]}>{a.severidade_label}</Pill><span>{a.texto}</span></li>)}</ul>
    </section>
  );
}

function IndicadoresPanel({ client, base }) {
  const [c, setC] = useState(null);
  const [al, setAl] = useState(null);
  useEffect(() => {
    client.get(`${base}/curva-s`).then(({ data }) => setC(data)).catch(() => setC({ disponivel: false, motivo: T.erro }));
    client.get(`${base}/alertas`).then(({ data }) => setAl(data.itens)).catch(() => setAl([]));
  }, [client, base]);
  return (
    <div className="grid gap-4">
      <section className={card} data-testid="gestao-curva">
        <Head title={T.indicadores} sub={T.curva_sub} />
        {!c ? <Empty>{T.carregar}</Empty> : !c.disponivel ? <Empty>{c.motivo}</Empty> : <div className="p-4 grid gap-3">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm">
            {[[T.previsto, `${num(c.previsto_hoje_pct, 1)} %`], [T.real, `${num(c.real_hoje_pct, 1)} %`], [T.desvio, `${c.desvio_pp > 0 ? "+" : ""}${num(c.desvio_pp, 1)} pp`], [T.spi, c.spi ?? "—"], [T.cpi, c.cpi ?? "—"]].map(([l, v]) => (
              <div key={l} className="rounded-lg border p-3"><p className="text-[11px] uppercase text-slate-500">{l}</p><p className="text-lg font-bold">{v}</p></div>))}
          </div>
          <div className="h-72"><ResponsiveContainer width="100%" height="100%"><LineChart data={c.pontos} margin={{ top: 8, right: 16, bottom: 0, left: -8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" /><XAxis dataKey="data" tickFormatter={day} fontSize={11} /><YAxis domain={[0, 100]} unit="%" fontSize={11} /><Tooltip labelFormatter={day} formatter={(v) => (v == null ? "—" : `${num(v, 1)} %`)} /><Legend />
            <Line type="monotone" dataKey="previsto_pct" name={T.previsto} stroke="#64748b" strokeDasharray="5 4" dot={false} />
            <Line type="monotone" dataKey="real_pct" name={T.real} stroke="#047857" strokeWidth={2.5} connectNulls={false} />
            {c.pontos.some((p) => p.custo_real_pct != null) && <Line type="monotone" dataKey="custo_real_pct" name={T.custo_real} stroke="#b45309" strokeWidth={2} />}
          </LineChart></ResponsiveContainer></div>
          <ul className="text-xs text-slate-500 list-disc ps-5">{c.notas.map((n) => <li key={n}>{n}</li>)}{c.usa_referencia && <li>{T.ref_congelada}</li>}</ul>
        </div>}
      </section>
      <section className={card} data-testid="gestao-alertas">
        <Head title={T.alertas} />
        {al === null ? <Empty>{T.carregar}</Empty> : al.length === 0 ? <Empty>{T.sem_alertas}</Empty> : <ul className="divide-y">{al.map((a, i) => <li key={i} className="px-4 py-2 text-sm flex gap-2 items-start"><Pill cls={SEV_CLS[a.severidade]}>{a.severidade_label}</Pill><span>{a.texto}</span></li>)}</ul>}
      </section>
    </div>
  );
}

// ====================================================================== stock (titular)
function StockPanel({ client, base }) {
  const [s, setS] = useState(null);
  const [enc, setEnc] = useState([]);
  const [mov, setMov] = useState(null);
  const [rec, setRec] = useState(null);
  const load = useCallback(() => {
    client.get(`${base}/stock`).then(({ data }) => setS(data)).catch(() => setS({ saldos: [], movimentos: [] }));
    client.get(`${base}/stock/encomendas`).then(({ data }) => setEnc(data.itens)).catch(() => setEnc([]));
  }, [client, base]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn) => { try { await fn(); load(); } catch (e) { err(e); } };
  return (
    <div className="grid gap-4">
      <section className={card} data-testid="gestao-stock">
        <Head title={T.stock} sub={T.stock_sub}>{!mov && <button className={primary} onClick={() => setMov({ tipo: "saida", material: "", unidade: "", quantidade: "", nota: "" })}><Plus className="h-4 w-4" /> {T.movimento}</button>}</Head>
        {mov && <div className="grid sm:grid-cols-5 gap-2 p-4 border-b bg-slate-50/60">
          <select className={field} value={mov.tipo} onChange={(e) => setMov((m) => ({ ...m, tipo: e.target.value }))}>{["entrada", "saida", "ajuste"].map((k) => <option key={k} value={k}>{T[k]}</option>)}</select>
          <input list="gd-mat" className={`${field} sm:col-span-2`} placeholder={T.material} value={mov.material} onChange={(e) => { const v = e.target.value; const m = (s?.saldos || []).find((x) => x.material === v); setMov((x) => ({ ...x, material: v, unidade: m ? m.unidade : x.unidade })); }} />
          <datalist id="gd-mat">{(s?.saldos || []).map((x) => <option key={x.chave} value={x.material} />)}</datalist>
          <input className={field} placeholder={T.unidade} value={mov.unidade} onChange={(e) => setMov((m) => ({ ...m, unidade: e.target.value }))} />
          <input type="number" step="0.001" className={field} placeholder={T.quantidade} value={mov.quantidade} onChange={(e) => setMov((m) => ({ ...m, quantidade: e.target.value }))} />
          <input className={`${field} sm:col-span-3`} placeholder={T.nota} value={mov.nota} onChange={(e) => setMov((m) => ({ ...m, nota: e.target.value }))} />
          <div className="sm:col-span-2 flex gap-2"><button className={primary} onClick={() => act(async () => { await client.post(`${base}/stock/movimentos`, { ...mov, quantidade: Number(mov.quantidade) }); setMov(null); })}><Check className="h-4 w-4" /> {T.guardar}</button><button className={ghost} onClick={() => setMov(null)}>{T.cancelar}</button></div>
        </div>}
        {!s ? <Empty>{T.carregar}</Empty> : s.saldos.length === 0 ? <Empty>{T.nenhum}</Empty> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="text-left p-2">{T.material}</th><th className="p-2">{T.entrada}</th><th className="p-2">{T.saida}</th><th className="p-2">{T.ajuste}</th><th className="p-2">{T.saldo}</th><th className="p-2">{T.minimo}</th></tr></thead>
          <tbody>{s.saldos.map((x) => <tr key={x.chave} className="border-t"><td className="p-2">{x.material} <span className="text-xs text-slate-500">{x.unidade}</span></td><td className="p-2 text-right">{num(x.entradas, 3)}</td><td className="p-2 text-right">{num(x.saidas, 3)}</td><td className="p-2 text-right">{num(x.ajustes, 3)}</td>
            <td className={`p-2 text-right font-semibold ${x.abaixo_minimo ? "text-red-700" : ""}`}>{num(x.saldo, 3)}{x.abaixo_minimo && ` (${T.abaixo_min})`}</td>
            <td className="p-2"><input type="number" min={0} className={`${field} w-24`} defaultValue={x.minimo ?? ""} onBlur={(e) => act(() => client.put(`${base}/stock/minimos`, { chave: x.chave, minimo: e.target.value === "" ? null : Number(e.target.value) }))} /></td></tr>)}</tbody></table></div>}
      </section>
      <section className={card}>
        <Head title={T.encomendas} />
        {enc.length === 0 ? <Empty>{T.nenhum}</Empty> : enc.map((o) => (
          <div key={o.order_id} className="border-t p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2"><b className="flex-1">{o.fornecedor}</b><Pill>{o.entrega || o.estado}</Pill>{o.linhas.some((l) => l.em_falta > 0) && rec?.order_id !== o.order_id && <button className={primary} onClick={() => setRec({ order_id: o.order_id, guia: "", linhas: o.linhas.map((l) => ({ linha: l.linha, quantidade: l.em_falta, conforme: true, nota: "" })) })}>{T.rececionar}</button>}</div>
            <table className="w-full mt-2 text-xs"><thead className="text-slate-500"><tr><th className="text-left">{T.material}</th><th>{T.pedida}</th><th>{T.recebida}</th><th>{T.em_falta}</th>{rec?.order_id === o.order_id && <><th>{T.quantidade}</th><th>{T.conforme}</th><th>{T.nota}</th></>}</tr></thead>
              <tbody>{o.linhas.map((l, i) => <tr key={l.linha} className="border-t"><td>{l.material} <span className="text-slate-500">{l.unidade}</span></td><td className="text-right">{num(l.pedida, 3)}</td><td className="text-right">{num(l.recebida, 3)}</td><td className="text-right">{num(l.em_falta, 3)}</td>
                {rec?.order_id === o.order_id && <><td><input type="number" min={0} step="0.001" className={`${field} w-24`} value={rec.linhas[i].quantidade} onChange={(e) => setRec((r) => ({ ...r, linhas: r.linhas.map((x, j) => j === i ? { ...x, quantidade: e.target.value } : x) }))} /></td>
                  <td className="text-center"><input type="checkbox" checked={rec.linhas[i].conforme} onChange={(e) => setRec((r) => ({ ...r, linhas: r.linhas.map((x, j) => j === i ? { ...x, conforme: e.target.checked } : x) }))} /></td>
                  <td><input className={field} value={rec.linhas[i].nota} onChange={(e) => setRec((r) => ({ ...r, linhas: r.linhas.map((x, j) => j === i ? { ...x, nota: e.target.value } : x) }))} /></td></>}</tr>)}</tbody></table>
            {rec?.order_id === o.order_id && <div className="flex flex-wrap gap-2 mt-2"><input className={`${field} w-48`} placeholder={T.guia} value={rec.guia} onChange={(e) => setRec((r) => ({ ...r, guia: e.target.value }))} />
              <button className={primary} onClick={() => act(async () => { await client.post(`${base}/stock/rececao/${o.order_id}`, { guia_remessa: rec.guia, linhas: rec.linhas.map((x) => ({ ...x, quantidade: Number(x.quantidade) || 0 })) }); setRec(null); })}><Check className="h-4 w-4" /> {T.guardar}</button><button className={ghost} onClick={() => setRec(null)}>{T.cancelar}</button></div>}
          </div>))}
      </section>
      {s?.movimentos?.length > 0 && <section className={card}><Head title={T.movimentos} /><ul className="divide-y text-xs">{s.movimentos.slice(0, 50).map((m) => <li key={m.mov_id} className="px-4 py-2 flex gap-2"><span className="w-20">{day(m.data)}</span><span className="w-16">{T[m.tipo]}</span><span className="flex-1">{m.material}</span><span>{num(m.quantidade, 3)} {m.unidade}</span><span className="text-slate-500">{m.por?.nome}</span></li>)}</ul></section>}
    </div>
  );
}

// ====================================================================== copiloto, histórico, webhooks (titular)
function CopilotoPanel({ client, base, fileBase }) {
  const [p, setP] = useState("");
  const [conversa, setConversa] = useState([]);
  const [busy, setBusy] = useState(false);
  const [resumo, setResumo] = useState(null);
  const perguntar = async (q) => {
    const pergunta = (q ?? p).trim(); if (!pergunta) return;
    setBusy(true); setP("");
    try { const { data } = await client.post(`${base}/copiloto/pergunta`, { pergunta }, { timeout: 120000 }); setConversa((c) => [...c, { q: pergunta, a: data.resposta, fonte: data.fonte }]); }
    catch (e) { err(e); } finally { setBusy(false); }
  };
  const gerar = async () => { setBusy(true); try { const { data } = await client.post(`${base}/copiloto/resumo`, null, { timeout: 120000 }); setResumo(data); } catch (e) { err(e); } finally { setBusy(false); } };
  return (
    <section className={card} data-testid="gestao-copiloto">
      <Head title={T.copiloto} sub={T.copiloto_sub}>
        <button className={ghost} disabled={busy} onClick={gerar}><Sparkles className="h-4 w-4" /> {T.resumo_semana}</button>
        <a className={ghost} href={`${fileBase}/relatorio-semanal.pdf`} target="_blank" rel="noreferrer"><Download className="h-4 w-4" /> {T.relatorio_pdf}</a>
      </Head>
      <div className="p-4 grid gap-3">
        {resumo && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm whitespace-pre-wrap">{resumo.texto}{resumo.fonte === "calculo" && <p className="text-xs text-slate-500 mt-1">{T.fonte_calculo}</p>}</div>}
        {conversa.map((c, i) => <div key={i} className="grid gap-1"><p className="justify-self-end rounded-2xl bg-slate-100 px-3 py-2 text-sm max-w-[85%]">{c.q}</p><p className="rounded-2xl border px-3 py-2 text-sm whitespace-pre-wrap max-w-[95%]"><Bot className="inline h-4 w-4 text-emerald-700" /> {c.a}{c.fonte === "calculo" && <span className="block text-xs text-slate-500">{T.fonte_calculo}</span>}</p></div>)}
        {conversa.length === 0 && <div className="flex flex-wrap gap-2">{T.sugestoes.map((s) => <button key={s} className={ghost} disabled={busy} onClick={() => perguntar(s)}>{s}</button>)}</div>}
        <div className="flex gap-2"><input className={field} placeholder={T.pergunta_ph} value={p} onChange={(e) => setP(e.target.value)} onKeyDown={(e) => e.key === "Enter" && perguntar()} data-testid="gestao-copiloto-input" />
          <button className={primary} disabled={busy || !p.trim()} onClick={() => perguntar()}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {T.perguntar}</button></div>
      </div>
    </section>
  );
}

function HistoricoPanel({ client, base }) {
  const [h, setH] = useState(null);
  useEffect(() => { client.get(`${base}/historico`).then(({ data }) => setH(data.itens)).catch(() => setH([])); }, [client, base]);
  return (
    <section className={card} data-testid="gestao-historico">
      <Head title={T.historico} sub={T.historico_sub} />
      {h === null ? <Empty>{T.carregar}</Empty> : h.length === 0 ? <Empty>{T.nenhum}</Empty> : <ul className="divide-y text-sm">{h.map((x) => <li key={x.hist_id} className="px-4 py-2 flex gap-3"><span className="w-32 text-xs text-slate-500">{when(x.at)}</span><span><b>{x.quem?.nome}</b> {x.texto}</span></li>)}</ul>}
    </section>
  );
}

function WebhooksPanel({ client, eventos }) {
  const [hooks, setHooks] = useState(null);
  const [novo, setNovo] = useState(null);
  const [segredo, setSegredo] = useState(null);
  const load = useCallback(() => client.get("/webhooks-saida").then(({ data }) => setHooks(data.itens)).catch(() => setHooks([])), [client]);
  useEffect(() => { load(); }, [load]);
  const act = async (fn) => { try { await fn(); load(); } catch (e) { err(e); } };
  return (
    <section className={card} data-testid="gestao-webhooks">
      <Head title={T.webhooks} sub={T.webhooks_sub}>{!novo && (hooks || []).length < 5 && <button className={primary} onClick={() => setNovo({ url: "https://", eventos: [...eventos], descricao: "" })}><Plus className="h-4 w-4" /> {T.criar}</button>}</Head>
      {segredo && <p className="m-4 rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs break-all"><b>{T.segredo}:</b> <code>{segredo}</code></p>}
      {novo && <div className="grid gap-2 p-4 border-b bg-slate-50/60">
        <input className={field} placeholder={T.url} value={novo.url} onChange={(e) => setNovo((n) => ({ ...n, url: e.target.value }))} />
        <div className="flex flex-wrap gap-3 text-xs">{eventos.map((ev) => <label key={ev} className="flex items-center gap-1"><input type="checkbox" checked={novo.eventos.includes(ev)} onChange={(e) => setNovo((n) => ({ ...n, eventos: e.target.checked ? [...n.eventos, ev] : n.eventos.filter((x) => x !== ev) }))} /> <code>{ev}</code></label>)}</div>
        <div className="flex gap-2"><button className={primary} onClick={() => act(async () => { const { data } = await client.post("/webhooks-saida", novo); setSegredo(data.segredo); setNovo(null); })}>{T.guardar}</button><button className={ghost} onClick={() => setNovo(null)}>{T.cancelar}</button></div>
      </div>}
      {(hooks || []).map((h) => <div key={h.hook_id} className="border-t px-4 py-3 text-sm flex flex-wrap items-center gap-2"><code className="flex-1 min-w-0 truncate">{h.url}</code><span className="text-xs text-slate-500">{h.eventos.length} · {h.envios || 0}✓ {h.falhas || 0}✗ · …{h.segredo_fim}</span>
        <button className={ghost} onClick={() => act(async () => { const { data } = await client.post(`/webhooks-saida/${h.hook_id}/testar`); toast[data.ok ? "success" : "error"](`${data.status || data.erro}`); })}>{T.testar}</button>
        <button className={ghost} onClick={() => act(() => client.delete(`/webhooks-saida/${h.hook_id}`))}>{T.apagar}</button></div>)}
    </section>
  );
}

// ====================================================================== contentor
const SECOES = [
  ["diario", T.diario, BookOpen, (c) => c["diario.ver"]],
  ["qse", T.qse, ShieldCheck, (c) => c["qse.ver"]],
  ["rfi", T.rfi, HelpCircle, (c) => c["rfi.ver"]],
  ["indicadores", T.indicadores, TrendingUp, (c) => c["indicadores.ver"]],
  ["stock", T.stock, Boxes, (c) => c.stock],
  ["copiloto", T.copiloto, Bot, (c) => c.copiloto],
  ["historico", T.historico, History, (c) => c.historico],
  ["webhooks", T.webhooks, Webhook, (c) => c.historico],
];

export function GestaoObra({ client, base, fileBase, only, initial }) {
  const [info] = useGestao(client, base);
  const disponiveis = info ? SECOES.filter(([k, , , ok]) => ok(info.capacidades) && (!only || only.includes(k))) : [];
  const [sec, setSec] = useState(initial || null);
  if (info === null) return <section className={card}><Empty>{T.carregar}</Empty></section>;
  if (info === false || disponiveis.length === 0) return null;
  const atual = disponiveis.some(([k]) => k === sec) ? sec : disponiveis[0][0];
  const props = { client, base, fileBase, info, gestor: !!info.eu.gestor };
  return (
    <div className="grid gap-3 min-w-0" data-testid="gestao-obra">
      {disponiveis.length > 1 && <nav className="flex flex-wrap gap-1 rounded-2xl border border-slate-200 bg-white p-1.5" aria-label={T.diario}>
        {disponiveis.map(([k, l, I]) => <button key={k} type="button" onClick={() => setSec(k)} aria-pressed={atual === k} data-testid={`gestao-sec-${k}`}
          className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm min-h-10 ${atual === k ? "bg-emerald-700 text-white" : "text-slate-600 hover:bg-slate-100"}`}><I className="h-4 w-4" /> {l}
          {k === "qse" && info.contadores.qse_abertos > 0 && <span className="text-xs opacity-80">({info.contadores.qse_abertos})</span>}
          {k === "rfi" && info.contadores.rfi_abertos > 0 && <span className="text-xs opacity-80">({info.contadores.rfi_abertos})</span>}</button>)}
      </nav>}
      {atual === "diario" && <DiarioPanel {...props} />}
      {atual === "qse" && <QsePanel {...props} />}
      {atual === "rfi" && <RfiPanel {...props} />}
      {atual === "indicadores" && <IndicadoresPanel {...props} />}
      {atual === "stock" && <StockPanel {...props} />}
      {atual === "copiloto" && <CopilotoPanel {...props} />}
      {atual === "historico" && <HistoricoPanel {...props} />}
      {atual === "webhooks" && <WebhooksPanel client={client} eventos={info.referenciais.webhook_eventos} />}
    </div>
  );
}
