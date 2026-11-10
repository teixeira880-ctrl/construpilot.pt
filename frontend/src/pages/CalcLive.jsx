import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import {
  Activity, Calculator, CheckCircle2, XCircle, HelpCircle, Lightbulb, Database, AlertTriangle, Flag, Wrench, Trash2,
  Loader2, Sigma, ListChecks, BookOpen, ArrowDown, Pause,
} from "lucide-react";

/* Acompanhamento do cálculo ao vivo — conta CLT Rezult (o servidor recusa as outras contas).
   Cada pedido ao Assistente = uma execução; os motores escrevem o que fazem e porquê (fórmula, valores, norma). */

const TXT = {
  pt: {
    title: "Acompanhamento do cálculo", sub: "Cada motor mostra, ao vivo, os dados que lê, as fórmulas com os valores, as decisões e as verificações.",
    runs: "Pedidos", none: "Ainda não há cálculos. Faça um pedido no Assistente: aparece aqui ao vivo.", live: "A calcular", done: "Terminado",
    stopped: "Interrompido", all: "Tudo", calc: "Cálculos", dec: "Decisões", chk: "Verificações", data: "Dados", hyp: "Pressupostos",
    why: "Porquê", formula: "Fórmula", result: "Resultado", norm: "Norma", source: "Fonte", follow: "Seguir ao vivo", paused: "Pausado",
    ok: "OK", ko: "Não conforme", tbc: "A confirmar", checks: "verificações", decisions: "decisões", calcs: "cálculos",
    denied: "Esta página está reservada à conta CLT Rezult.", del: "Apagar", motor: "Motor", tool: "Ferramenta escolhida",
  },
  en: {
    title: "Calculation tracking", sub: "Every engine shows, live, the data it reads, the formulas with their values, its decisions and its checks.",
    runs: "Requests", none: "No calculation yet. Send a request in the Assistant: it appears here live.", live: "Calculating", done: "Finished",
    stopped: "Interrupted", all: "All", calc: "Calculations", dec: "Decisions", chk: "Checks", data: "Data", hyp: "Assumptions",
    why: "Why", formula: "Formula", result: "Result", norm: "Standard", source: "Source", follow: "Follow live", paused: "Paused",
    ok: "OK", ko: "Not compliant", tbc: "To confirm", checks: "checks", decisions: "decisions", calcs: "calculations",
    denied: "This page is reserved for the CLT Rezult account.", del: "Delete", motor: "Engine", tool: "Engine chosen",
  },
  fr: {
    title: "Suivi du calcul", sub: "Chaque moteur montre en direct les données lues, les formules avec leurs valeurs, ses décisions et ses vérifications.",
    runs: "Demandes", none: "Aucun calcul pour l'instant. Faites une demande dans l'Assistant : elle apparaît ici en direct.", live: "En calcul",
    done: "Terminé", stopped: "Interrompu", all: "Tout", calc: "Calculs", dec: "Décisions", chk: "Vérifications", data: "Données",
    hyp: "Hypothèses", why: "Pourquoi", formula: "Formule", result: "Résultat", norm: "Norme", source: "Source", follow: "Suivre en direct",
    paused: "En pause", ok: "OK", ko: "Non conforme", tbc: "À confirmer", checks: "vérifications", decisions: "décisions", calcs: "calculs",
    denied: "Cette page est réservée au compte CLT Rezult.", del: "Supprimer", motor: "Moteur", tool: "Moteur choisi",
  },
};

const FILTROS = [
  { k: "all", tipos: null },
  { k: "calc", tipos: ["calculo"] },
  { k: "dec", tipos: ["decisao", "ferramenta"] },
  { k: "chk", tipos: ["verificacao"] },
  { k: "data", tipos: ["dado"] },
  { k: "hyp", tipos: ["pressuposto", "aviso"] },
];

const ESTILO = {
  ferramenta: { icon: Wrench, cls: "border-violet-500/40 bg-violet-500/10", ic: "text-violet-500" },
  dado: { icon: Database, cls: "border-sky-500/30 bg-sky-500/5", ic: "text-sky-500" },
  calculo: { icon: Sigma, cls: "border-blue-500/30 bg-blue-500/5", ic: "text-blue-500" },
  decisao: { icon: Lightbulb, cls: "border-amber-500/40 bg-amber-500/10", ic: "text-amber-500" },
  pressuposto: { icon: BookOpen, cls: "border-border bg-muted/40", ic: "text-muted-foreground" },
  aviso: { icon: AlertTriangle, cls: "border-orange-500/40 bg-orange-500/10", ic: "text-orange-500" },
  erro: { icon: XCircle, cls: "border-destructive/50 bg-destructive/10", ic: "text-destructive" },
  resultado: { icon: Flag, cls: "border-emerald-500/40 bg-emerald-500/10", ic: "text-emerald-600" },
};

const hora = (t, lang) => (t ? new Date(t).toLocaleTimeString(lang === "en" ? "en-GB" : lang === "fr" ? "fr-FR" : "pt-PT") : "");

function Verif({ ok, L }) {
  if (ok === true) return <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-600"><CheckCircle2 className="h-3 w-3" /> {L.ok}</span>;
  if (ok === false) return <span className="inline-flex items-center gap-1 rounded-full bg-destructive/15 px-2 py-0.5 text-[11px] font-semibold text-destructive"><XCircle className="h-3 w-3" /> {L.ko}</span>;
  return <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-600"><HelpCircle className="h-3 w-3" /> {L.tbc}</span>;
}

function Evento({ e, L, lang }) {
  const verif = e.tipo === "verificacao";
  const st = verif
    ? { icon: ListChecks, cls: e.ok === false ? "border-destructive/50 bg-destructive/5" : e.ok === true ? "border-emerald-500/30 bg-emerald-500/5" : "border-amber-500/40 bg-amber-500/5", ic: e.ok === false ? "text-destructive" : e.ok === true ? "text-emerald-600" : "text-amber-500" }
    : ESTILO[e.tipo] || ESTILO.dado;
  const I = st.icon;
  const vals = Object.entries(e.valores || {}).filter(([, v]) => v !== null && v !== undefined && v !== "" && v !== "—");
  return (
    <div className={`rounded-lg border p-3 ${st.cls}`} data-testid={`calc-live-ev-${e.tipo}`}>
      <div className="flex items-start gap-2">
        <I className={`h-4 w-4 mt-0.5 shrink-0 ${st.ic}`} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {e.tipo === "ferramenta" && <span className="text-[10px] uppercase tracking-wide text-violet-600 font-semibold">{L.tool}</span>}
            <p className="text-sm font-medium break-words">{e.titulo}</p>
            {verif && <Verif ok={e.ok} L={L} />}
            <span className="ml-auto text-[10px] text-muted-foreground num">{hora(e.t, lang)}</span>
          </div>
          {e.formula && <p className="mt-1.5 font-mono text-[12px] rounded bg-background/70 border border-border px-2 py-1 break-words"><span className="text-muted-foreground mr-1.5">{L.formula}:</span>{e.formula}</p>}
          {vals.length > 0 && (
            <dl className="mt-1.5 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-0.5 text-[12px]">
              {vals.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-border/40 py-0.5 min-w-0">
                  <dt className="text-muted-foreground break-words max-w-[45%]">{k}</dt>
                  <dd className="font-medium text-right num break-words">{typeof v === "boolean" ? (v ? "✓" : "✗") : String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
          {e.resultado && <p className="mt-1.5 text-sm"><span className="text-muted-foreground">{L.result}: </span><b className="num">{e.resultado}</b></p>}
          {e.porque && <p className="mt-1 text-[12px] italic text-foreground/80"><span className="not-italic font-semibold">{L.why}: </span>{e.porque}</p>}
          {e.nota && <p className="mt-1 text-[12px] text-muted-foreground">{e.nota}</p>}
          {(e.norma || e.fonte) && (
            <p className="mt-1 text-[11px] text-muted-foreground break-words">
              {e.norma && <span><span className="font-semibold">{L.norm}: </span>{e.norma}</span>}
              {e.norma && e.fonte && " · "}
              {e.fonte && <span><span className="font-semibold">{L.source}: </span>{e.url ? <a href={e.url} target="_blank" rel="noreferrer" className="underline">{e.fonte}</a> : e.fonte}</span>}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

export default function CalcLive() {
  const { lang } = useI18n();
  const L = TXT[lang] || TXT.pt;
  const [search, setSearch] = useSearchParams();
  const [acesso, setAcesso] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runId, setRunId] = useState(search.get("run") || null);
  const [run, setRun] = useState(null);
  const [eventos, setEventos] = useState([]);
  const [filtro, setFiltro] = useState("all");
  const [seguir, setSeguir] = useState(true);
  const fim = useRef(null);
  const ultimo = useRef(0);
  const escolhidoPeloUtilizador = useRef(Boolean(search.get("run")));

  useEffect(() => { api.get("/calc-live/acesso").then(({ data }) => setAcesso(Boolean(data.acesso))).catch(() => setAcesso(false)); }, []);

  // lista de pedidos: a mais recente é escolhida sozinha (até o utilizador escolher outra)
  useEffect(() => {
    if (!acesso) return undefined;
    let vivo = true;
    const carregar = async () => {
      try {
        const { data } = await api.get("/calc-live/runs");
        if (!vivo) return;
        setRuns(data.runs || []);
        const novo = (data.runs || [])[0];
        if (novo && !escolhidoPeloUtilizador.current) setRunId((cur) => (cur === novo.run_id ? cur : novo.run_id));
      } catch { /* sem rede: tenta de novo */ }
    };
    carregar();
    const t = setInterval(carregar, 3000);
    return () => { vivo = false; clearInterval(t); };
  }, [acesso]);

  // eventos da execução escolhida: incrementais (só os novos), a cada 1,5 s enquanto calcula
  useEffect(() => {
    if (!acesso || !runId) return undefined;
    let vivo = true;
    let timer;
    ultimo.current = 0;
    setEventos([]);
    setRun(null);
    const passo = async () => {
      let espera = 1500;
      try {
        const { data } = await api.get(`/calc-live/runs/${encodeURIComponent(runId)}`, { params: { desde: ultimo.current } });
        if (!vivo) return;
        setRun(data);
        if (data.eventos?.length) {
          ultimo.current = data.eventos[data.eventos.length - 1].seq;
          setEventos((old) => [...old, ...data.eventos]);
        }
        if (data.estado !== "a_calcular") espera = 6000;
      } catch { espera = 4000; }
      if (vivo) timer = setTimeout(passo, espera);
    };
    passo();
    return () => { vivo = false; clearTimeout(timer); };
  }, [acesso, runId]);

  useEffect(() => { if (seguir) fim.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [eventos.length, seguir]);

  const escolher = (id) => {
    escolhidoPeloUtilizador.current = true;
    setRunId(id);
    setSearch({ run: id }, { replace: true });
  };
  const apagar = async (id) => {
    await api.delete(`/calc-live/runs/${encodeURIComponent(id)}`).catch(() => {});
    setRuns((r) => r.filter((x) => x.run_id !== id));
    if (id === runId) { escolhidoPeloUtilizador.current = false; setRunId(null); }
  };

  const contagem = useMemo(() => {
    const v = eventos.filter((e) => e.tipo === "verificacao");
    return {
      ok: v.filter((e) => e.ok === true).length, ko: v.filter((e) => e.ok === false).length, tbc: v.filter((e) => e.ok == null).length,
      dec: eventos.filter((e) => e.tipo === "decisao").length, calc: eventos.filter((e) => e.tipo === "calculo").length,
    };
  }, [eventos]);

  // agrupar por etapa (os eventos «etapa» abrem uma secção)
  const secoes = useMemo(() => {
    const tipos = FILTROS.find((f) => f.k === filtro)?.tipos;
    const out = [];
    let cur = { titulo: null, motor: null, itens: [] };
    for (const e of eventos) {
      if (e.tipo === "etapa") { if (cur.titulo || cur.itens.length) out.push(cur); cur = { titulo: e.titulo, motor: e.motor, t: e.t, itens: [] }; continue; }
      if (!tipos || tipos.includes(e.tipo) || (e.tipo === "erro")) cur.itens.push(e);
    }
    if (cur.titulo || cur.itens.length) out.push(cur);
    return tipos ? out.filter((s) => s.itens.length) : out;
  }, [eventos, filtro]);

  if (acesso === null) return <div className="p-6 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /></div>;
  if (!acesso) return <div className="p-6 text-sm text-muted-foreground" data-testid="calc-live-denied">{L.denied}</div>;

  const estadoTxt = (s) => (s === "a_calcular" ? L.live : s === "interrompido" ? L.stopped : L.done);

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 space-y-4" data-testid="calc-live-page">
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2"><Activity className="h-6 w-6 text-primary" /> {L.title}</h1>
        <p className="text-sm text-muted-foreground">{L.sub}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-2" data-testid="calc-live-runs">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{L.runs}</p>
          {runs.length === 0 && <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border p-3">{L.none}</p>}
          {runs.map((r) => (
            <div key={r.run_id} className={`group rounded-lg border p-2.5 cursor-pointer transition ${r.run_id === runId ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50"}`}
                 onClick={() => escolher(r.run_id)} data-testid="calc-live-run">
              <div className="flex items-center gap-1.5 text-[11px]">
                {r.estado === "a_calcular" ? <Loader2 className="h-3 w-3 animate-spin text-blue-500" /> : r.n_ko ? <XCircle className="h-3 w-3 text-destructive" /> : <CheckCircle2 className="h-3 w-3 text-emerald-600" />}
                <span className="font-semibold">{estadoTxt(r.estado)}</span>
                <span className="ml-auto text-muted-foreground num">{hora(r.started_at, lang)}</span>
                <button type="button" className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive" title={L.del}
                        onClick={(ev) => { ev.stopPropagation(); apagar(r.run_id); }}><Trash2 className="h-3 w-3" /></button>
              </div>
              <p className="mt-1 text-[13px] line-clamp-2">{r.pedido}</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground truncate">{(r.ferramentas || []).join(" · ")}</p>
            </div>
          ))}
        </aside>

        <section className="min-w-0 space-y-3">
          {run && (
            <div className="rounded-xl border border-border p-3 space-y-2 sticky top-0 z-10 bg-background/95 backdrop-blur" data-testid="calc-live-header">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold ${run.estado === "a_calcular" ? "border-blue-500/30 bg-blue-500/15 text-blue-600" : "border-border bg-muted"}`}>
                  {run.estado === "a_calcular" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Calculator className="h-3 w-3" />} {estadoTxt(run.estado)}
                </span>
                <p className="text-sm font-medium min-w-0 flex-1 line-clamp-2">{run.pedido}</p>
                <button type="button" onClick={() => setSeguir((s) => !s)} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px]" data-testid="calc-live-follow">
                  {seguir ? <ArrowDown className="h-3 w-3" /> : <Pause className="h-3 w-3" />} {seguir ? L.follow : L.paused}
                </button>
              </div>
              <div className="flex flex-wrap gap-2 text-[11px]">
                <span className="rounded-full bg-emerald-500/15 text-emerald-700 px-2 py-0.5 font-semibold num">{contagem.ok} {L.ok}</span>
                <span className="rounded-full bg-destructive/15 text-destructive px-2 py-0.5 font-semibold num">{contagem.ko} {L.ko}</span>
                <span className="rounded-full bg-amber-500/15 text-amber-700 px-2 py-0.5 font-semibold num">{contagem.tbc} {L.tbc}</span>
                <span className="rounded-full bg-blue-500/15 text-blue-700 px-2 py-0.5 num">{contagem.calc} {L.calcs}</span>
                <span className="rounded-full bg-amber-500/10 text-amber-700 px-2 py-0.5 num">{contagem.dec} {L.decisions}</span>
              </div>
              <div className="flex flex-wrap gap-1.5" role="tablist">
                {FILTROS.map((f) => (
                  <button key={f.k} type="button" role="tab" aria-selected={filtro === f.k} onClick={() => setFiltro(f.k)}
                          className={`rounded-full px-2.5 py-1 text-[12px] border ${filtro === f.k ? "bg-primary text-primary-foreground border-primary" : "border-border hover:bg-muted"}`}
                          data-testid={`calc-live-filter-${f.k}`}>{L[f.k]}</button>
                ))}
              </div>
            </div>
          )}

          {!runId && runs.length === 0 && null}
          {runId && !run && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /></div>}

          <div className="space-y-4" data-testid="calc-live-timeline">
            {secoes.map((s, i) => (
              <div key={`${s.titulo}-${i}`} className="space-y-2">
                {s.titulo && (
                  <div className="flex items-center gap-2 pt-1">
                    <span className="h-px flex-1 bg-border" />
                    <p className="text-[12px] font-semibold uppercase tracking-wide text-primary text-center">{s.titulo}</p>
                    <span className="h-px flex-1 bg-border" />
                  </div>
                )}
                {s.itens.map((e) => <Evento key={e.seq} e={e} L={L} lang={lang} />)}
              </div>
            ))}
            {run?.estado === "a_calcular" && <div className="flex items-center gap-2 text-sm text-blue-600"><Loader2 className="h-4 w-4 animate-spin" /> {L.live}…</div>}
            <div ref={fim} />
          </div>
        </section>
      </div>
    </div>
  );
}
