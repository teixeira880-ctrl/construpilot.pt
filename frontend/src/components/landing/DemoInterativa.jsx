import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Mic, Square, Sparkles, Check, ArrowRight, BookOpen, Boxes, ShieldAlert, HelpCircle, Map as MapIcon, Calculator } from "lucide-react";
import { D, VOC, LOCALE, LANG_VOZ } from "./demoTxt";

/**
 * Demonstração interativa da página inicial: funciona 100 % no navegador, sem conta, sem servidor e sem internet
 * (o ditado usa o reconhecimento de voz do navegador quando existe). Dados fictícios; nada é gravado.
 */
const eur = (v) => new Intl.NumberFormat(LOCALE, { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(v);
const norm = (s) => (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/(\d),(\d)/g, "$1.$2").replace(/[^a-z0-9%.\s]/g, " ").replace(/\s+/g, " ").trim();
const cor = (p) => (p <= 0 ? "#e2e8f0" : p < 25 ? "#fde68a" : p < 50 ? "#fcd34d" : p < 75 ? "#a7f3d0" : p < 100 ? "#34d399" : "#047857");
const num = (t) => { const n = parseFloat(t); return Number.isFinite(n) ? n : VOC.numeros[t]; };

export function interpretar(texto, divisoes) {
  const out = { trabalhos: [], efetivos: [], stock: [], seg: [], pedidos: [], visitas: [], ocorrencias: [], avanco: [] };
  const frases = (texto || "").split(/(?<=[.!?;])\s+|\n+/).map((f) => f.trim().replace(/[.;]$/, "")).filter(Boolean);
  for (const f of frases) {
    const n = norm(f);
    let usada = false;
    const ent = n.match(VOC.entrada), sai = n.match(VOC.saida);
    if (ent || sai) {
      const mov = ent && (!sai || ent.index <= sai.index) ? "entrada" : "saida";
      const resto = n.slice((ent || sai).index);
      const rx = /\b(\d+(?:\.\d+)?|[a-z]+)\s+(sacos|saco|m3|m2|paletes|palete|kg|unidades|tijolos)\b(?:\s+(?:de|do|da))?\s*([a-z ]*)/g;
      let m;
      while ((m = rx.exec(resto))) {
        const q = num(m[1]);
        if (!q) continue;
        const mat = m[3].split(" ").filter(Boolean);
        const nome = [];
        for (const w of mat) { if (VOC.fim.includes(w) || nome.length >= 3) break; nome.push(w); }
        const material = m[2] === "tijolos" ? "tijolo" : nome.join(" ");
        if (!material) continue;
        out.stock.push({ mov, q, un: VOC.unidades[m[2]], material: material.charAt(0).toUpperCase() + material.slice(1) });
        usada = true;
      }
    }
    const pe = [...n.matchAll(new RegExp(VOC.pessoas.source, "g"))];
    pe.forEach((p) => { const q = num(p[1]); if (q) { out.efetivos.push(`${p[5] ? p[5].charAt(0).toUpperCase() + p[5].slice(1) : p[2].charAt(0).toUpperCase() + p[2].slice(1)}: ${q}`); usada = true; } });
    if (VOC.seg.test(n)) { out.seg.push(f); out.ocorrencias.push(f); usada = true; }
    if (VOC.pedido.test(n) || f.endsWith("?")) { out.pedidos.push(f); usada = true; }
    if (VOC.visita.test(n)) { out.visitas.push(f); usada = true; } else if (VOC.ocorrencia.test(n) && !out.ocorrencias.includes(f)) { out.ocorrencias.push(f); usada = true; }
    const pct = n.match(/(\d{1,3})\s?%/);
    const p = pct ? Number(pct[1]) : VOC.concluido.test(n) ? 100 : null;
    const div = divisoes.find((d) => new RegExp(`\\b${norm(d[0])}\\b`).test(n));
    if (p != null && p <= 100 && div) { out.avanco.push({ divisao: div[0], pct: p }); }
    if (!usada || (p != null && div)) out.trabalhos.push(f);
  }
  return out;
}

function Bloco({ icon: I, titulo, cls, children }) {
  return (
    <div className={`rounded-xl border p-3 ${cls}`}>
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide mb-1.5"><I className="h-4 w-4" /> {titulo}</p>
      <div className="text-sm space-y-1">{children}</div>
    </div>
  );
}

function DemoVoz({ divisoes, onAvanco }) {
  const [texto, setTexto] = useState("");
  const [res, setRes] = useState(null);
  const [ok, setOk] = useState(false);
  const [ouvir, setOuvir] = useState(false);
  const recRef = useRef(null);
  const SR = typeof window !== "undefined" ? (window.SpeechRecognition || window.webkitSpeechRecognition) : null;
  const ditar = () => {
    if (ouvir) { recRef.current?.stop(); return; }
    const r = new SR();
    r.lang = LANG_VOZ; r.interimResults = false; r.continuous = true;
    r.onresult = (e) => { const t = Array.from(e.results).slice(e.resultIndex).map((x) => x[0].transcript).join(" "); setTexto((x) => (x ? x + " " : "") + t.trim()); };
    r.onend = () => setOuvir(false); r.onerror = () => setOuvir(false);
    recRef.current = r; setOuvir(true); r.start();
  };
  const correr = (t = texto) => { setOk(false); setRes(interpretar(t, divisoes)); };
  const vazio = res && !Object.values(res).some((v) => v.length);
  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <div className="grid gap-3 content-start">
        <p className="text-sm text-slate-600">{D.voz_intro}</p>
        <textarea className="w-full rounded-xl border border-slate-300 bg-white p-3 text-sm min-h-36 focus:outline-none focus:ring-2 focus:ring-emerald-600" value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={D.voz_ph} data-testid="demo-voz-texto" />
        <div className="flex flex-wrap gap-2">
          {SR && <button type="button" onClick={ditar} className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold min-h-10 ${ouvir ? "bg-red-600 text-white animate-pulse" : "border border-slate-300 bg-white"}`}>{ouvir ? <><Square className="h-4 w-4" /> {D.parar}</> : <><Mic className="h-4 w-4" /> {D.ditar}</>}</button>}
          <button type="button" className="inline-flex items-center gap-1.5 rounded-full bg-emerald-700 text-white px-4 py-2 text-sm font-semibold min-h-10 hover:bg-emerald-800 disabled:opacity-50" disabled={!texto.trim()} onClick={() => correr()} data-testid="demo-voz-interpretar"><Sparkles className="h-4 w-4" /> {D.interpretar}</button>
        </div>
        {ouvir && <p className="text-xs text-red-700">{D.a_ouvir}</p>}
        <div className="flex flex-wrap gap-2">{D.exemplos.map((e, i) => <button key={i} type="button" className="text-left text-xs rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-2 hover:bg-white max-w-full" onClick={() => { setTexto(e); correr(e); }} data-testid={`demo-voz-exemplo-${i}`}>«{e.slice(0, 90)}…»</button>)}</div>
      </div>
      <div className="grid gap-2 content-start" aria-live="polite">
        {!res && <div className="rounded-xl border border-dashed p-6 text-sm text-slate-500 grid place-items-center min-h-48 text-center">{D.usar_exemplo} ↖</div>}
        {vazio && <p className="text-sm text-slate-500">{D.nada}</p>}
        {res && !vazio && <>
          {(res.trabalhos.length || res.efetivos.length || res.visitas.length || res.ocorrencias.length) > 0 && <Bloco icon={BookOpen} titulo={D.t_diario} cls="bg-sky-50 border-sky-200 text-sky-900">
            {res.efetivos.length > 0 && <p><b>{D.efetivos}:</b> {res.efetivos.join(" · ")}</p>}
            {res.trabalhos.length > 0 && <p><b>{D.trabalhos}:</b> {res.trabalhos.join(" · ")}</p>}
            {res.visitas.length > 0 && <p><b>{D.visitas}:</b> {res.visitas.join(" · ")}</p>}
            {res.ocorrencias.length > 0 && <p><b>{D.ocorrencias}:</b> {res.ocorrencias.join(" · ")}</p>}
          </Bloco>}
          {res.stock.length > 0 && <Bloco icon={Boxes} titulo={D.t_stock} cls="bg-amber-50 border-amber-200 text-amber-900">
            {res.stock.map((s, i) => <p key={i}><b>{s.mov === "entrada" ? `+ ${D.entrada}` : `− ${D.saida}`}</b> · {String(s.q).replace(".", ",")} {s.un} · {s.material}</p>)}</Bloco>}
          {res.seg.length > 0 && <Bloco icon={ShieldAlert} titulo={D.t_seg} cls="bg-red-50 border-red-200 text-red-900">{res.seg.map((s, i) => <p key={i}>{s}</p>)}</Bloco>}
          {res.pedidos.length > 0 && <Bloco icon={HelpCircle} titulo={D.t_pedido} cls="bg-indigo-50 border-indigo-200 text-indigo-900">{res.pedidos.map((s, i) => <p key={i}>{s}</p>)}</Bloco>}
          {res.avanco.length > 0 && <Bloco icon={MapIcon} titulo={D.t_avanco} cls="bg-emerald-50 border-emerald-200 text-emerald-900">{res.avanco.map((a, i) => <p key={i}><b>{a.divisao}</b> → {a.pct} %</p>)}</Bloco>}
          <button type="button" disabled={ok} onClick={() => { setOk(true); onAvanco(res.avanco); }} className="inline-flex items-center justify-center gap-1.5 rounded-full bg-emerald-700 text-white px-4 py-2 text-sm font-semibold min-h-10 disabled:bg-emerald-100 disabled:text-emerald-800" data-testid="demo-voz-confirmar"><Check className="h-4 w-4" /> {ok ? D.confirmado : D.confirmar}</button>
        </>}
      </div>
    </div>
  );
}

function DemoOrcamento() {
  const [area, setArea] = useState(90);
  const [nivel, setNivel] = useState("medio");
  const mult = { economico: 0.85, medio: 1, premium: 1.4 }[nivel];
  const linhas = D.linhas.map(([nome, un, f, pu]) => {
    const q = f == null ? 1 : Math.max(1, un === "un" ? Math.round(area * f) : Math.round(area * f));
    const p = Math.round(pu * mult * 100) / 100;
    return { nome, un, q, p, t: q * p };
  });
  const sub = linhas.reduce((s, l) => s + l.t, 0);
  return (
    <div className="grid gap-4">
      <p className="text-sm text-slate-600">{D.orc_intro}</p>
      <div className="flex flex-wrap items-center gap-5">
        <label className="grid gap-1 text-sm min-w-64 flex-1"><span className="flex justify-between"><b>{D.area}</b><span>{area} m²</span></span>
          <input type="range" min={20} max={300} step={5} value={area} onChange={(e) => setArea(Number(e.target.value))} className="accent-emerald-700" data-testid="demo-orc-area" /></label>
        <div className="flex gap-1 rounded-full border p-1">{Object.entries(D.niveis).map(([k, l]) => <button key={k} type="button" onClick={() => setNivel(k)} aria-pressed={nivel === k} className={`rounded-full px-3 py-1.5 text-sm min-h-9 ${nivel === k ? "bg-emerald-700 text-white" : "text-slate-600"}`}>{l}</button>)}</div>
      </div>
      <div className="overflow-x-auto rounded-xl border"><table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="text-left p-2">{D.artigo}</th><th className="p-2 text-right">{D.qtd}</th><th className="p-2">{D.un}</th><th className="p-2 text-right">{D.preco}</th><th className="p-2 text-right">{D.total}</th></tr></thead>
        <tbody>{linhas.map((l) => <tr key={l.nome} className="border-t"><td className="p-2">{l.nome}</td><td className="p-2 text-right tabular-nums">{l.q}</td><td className="p-2 text-center">{l.un}</td><td className="p-2 text-right tabular-nums">{eur(l.p)}</td><td className="p-2 text-right tabular-nums font-medium">{eur(l.t)}</td></tr>)}</tbody>
        <tfoot className="text-sm">
          <tr className="border-t"><td colSpan={4} className="p-2 text-right">{D.subtotal}</td><td className="p-2 text-right tabular-nums">{eur(sub)}</td></tr>
          <tr><td colSpan={4} className="p-2 text-right">{D.iva}</td><td className="p-2 text-right tabular-nums">{eur(sub * 0.23)}</td></tr>
          <tr className="bg-emerald-50"><td colSpan={4} className="p-2 text-right font-bold">{D.total_iva}</td><td className="p-2 text-right tabular-nums font-bold text-emerald-800" data-testid="demo-orc-total">{eur(sub * 1.23)}</td></tr>
        </tfoot></table></div>
      <p className="text-xs text-slate-500">{D.precos_ficticios}</p>
    </div>
  );
}

function DemoMapa({ avanco, setAvanco }) {
  const [sel, setSel] = useState(null);
  const global = Math.round(D.divisoes.reduce((s, d) => s + (avanco[d[0]] * d[3] * d[4]), 0) / D.divisoes.reduce((s, d) => s + d[3] * d[4], 0));
  return (
    <div className="grid lg:grid-cols-[1fr_18rem] gap-5 items-start">
      <div>
        <p className="text-sm text-slate-600 mb-3">{D.mapa_intro}</p>
        <div className="relative aspect-[16/10] rounded-xl border-4 border-slate-800 bg-white" data-testid="demo-mapa">
          {D.divisoes.map(([nome, x, y, w, h]) => { const p = avanco[nome]; return (
            <button key={nome} type="button" onClick={() => setSel(nome)} className={`absolute grid place-items-center border-2 border-slate-700 transition-colors ${sel === nome ? "ring-4 ring-sky-400 z-10" : ""}`}
              style={{ left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`, background: cor(p) }} data-testid={`demo-mapa-${nome}`}>
              <span className="rounded bg-white/85 px-2 py-0.5 text-xs font-semibold shadow-sm">{nome}<br />{p} %</span>
            </button>); })}
        </div>
      </div>
      <div className="grid gap-3">
        <div className="rounded-xl border p-4"><p className="text-[11px] uppercase text-slate-500">{D.global}</p><p className="text-4xl font-bold text-emerald-800" data-testid="demo-mapa-global">{global} %</p>
          <div className="mt-2 h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-emerald-600 transition-all" style={{ width: `${global}%` }} /></div></div>
        {sel ? <label className="rounded-xl border p-4 grid gap-2 text-sm"><span className="flex justify-between"><b>{sel}</b><span>{avanco[sel]} %</span></span>
          <input type="range" min={0} max={100} step={5} value={avanco[sel]} onChange={(e) => setAvanco((a) => ({ ...a, [sel]: Number(e.target.value) }))} className="accent-emerald-700" /></label>
          : <p className="text-sm text-slate-500">{D.escolha_divisao}</p>}
        <p className="text-[11px] text-slate-500 flex items-center gap-1">{[0, 30, 60, 100].map((p) => <span key={p} className="h-3 w-5 rounded-sm inline-block" style={{ background: cor(p) }} />)} {D.legenda}</p>
      </div>
    </div>
  );
}

export default function DemoInterativa() {
  const [tab, setTab] = useState("voz");
  const inicial = useMemo(() => Object.fromEntries(D.divisoes.map((d) => [d[0], d[5]])), []);
  const [avanco, setAvanco] = useState(inicial);
  const tabs = [["voz", D.tabs.voz, Mic], ["orcamento", D.tabs.orcamento, Calculator], ["mapa", D.tabs.mapa, MapIcon]];
  const aplicarAvanco = (lista) => { if (!lista?.length) return; setAvanco((a) => ({ ...a, ...Object.fromEntries(lista.map((x) => [x.divisao, x.pct])) })); };
  return (
    <section className="landing-section" id="landing-demo-interativa" data-testid="demo-interativa">
      <div className="mx-auto max-w-6xl">
        <p className="landing-eyebrow">{D.eyebrow}</p>
        <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mt-2">{D.titulo}</h2>
        <p className="mt-2 text-slate-600">{D.sub}</p>
        <div className="mt-6 rounded-3xl border border-slate-200 bg-white shadow-xl overflow-hidden text-slate-900">
          <nav className="flex gap-1 overflow-x-auto whitespace-nowrap border-b border-slate-200 bg-slate-50 p-2" role="tablist">
            {tabs.map(([k, l, I]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`demo-tab-${k}`}
              className={`inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium min-h-10 ${tab === k ? "bg-emerald-700 text-white shadow" : "text-slate-600 hover:bg-white"}`}><I className="h-4 w-4" /> {l}</button>)}
          </nav>
          <div className="p-5 md:p-7">
            {tab === "voz" && <DemoVoz divisoes={D.divisoes} onAvanco={aplicarAvanco} />}
            {tab === "orcamento" && <DemoOrcamento />}
            {tab === "mapa" && <DemoMapa avanco={avanco} setAvanco={setAvanco} />}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-4">
            <p className="text-xs text-slate-500">{D.aviso}</p>
            <div className="flex items-center gap-3"><span className="text-xs text-slate-500 hidden sm:inline">{D.cta_sub}</span>
              <Link to="/inscription" className="landing-button" data-testid="demo-cta">{D.cta} <ArrowRight size={18} /></Link></div>
          </div>
        </div>
      </div>
    </section>
  );
}
