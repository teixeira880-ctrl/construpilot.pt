import { useCallback, useEffect, useRef, useState } from "react";
import { useReducedMotion, motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Cpu, Expand, Minimize, RotateCcw, CheckCircle2, AlertTriangle, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { DEMO_STEPS, FLOW_LABELS } from "./demoSteps";
import { CAPS, DEMOS } from "./engine";
import { formatEurLang, formatNum, tr } from "./i18n";
import { StatusBadge } from "./components";
import { computeDemo } from "./api";
import snapshots from "./demo_snapshots.json";

const ENGINE_DEMOS = ["demo_takeoff", "demo_painting", "demo_quote", "demo_margin"];

/** Obtém os números do motor real; sem rede usa o instantâneo gerado pelo mesmo motor (parâmetros por defeito). */
function useDemoData(demoId, params) {
  const [state, setState] = useState({ data: ENGINE_DEMOS.includes(demoId) ? snapshots[demoId] : null, live: false, offline: false, error: null });
  const key = JSON.stringify(params);
  useEffect(() => {
    if (!ENGINE_DEMOS.includes(demoId)) return undefined;
    let alive = true;
    const h = setTimeout(async () => {
      try {
        const data = await computeDemo(demoId, params);
        if (alive) setState({ data, live: true, offline: false, error: null });
      } catch (e) {
        if (!alive) return;
        if (e.response && e.response.status === 422) setState((s) => ({ ...s, error: "invalid" }));
        else setState({ data: snapshots[demoId], live: false, offline: true, error: null });
      }
    }, 250);
    return () => { alive = false; clearTimeout(h); };
  }, [demoId, key]); // eslint-disable-line react-hooks/exhaustive-deps
  return state;
}

export default function DemoPlayer({ demoId, lang, t, onProgress, onSwitch, alternatives = [], compact = false }) {
  const demo = DEMOS[demoId];
  const steps = DEMO_STEPS[demoId] || [];
  const [i, setI] = useState(0);
  const [params, setParams] = useState({});
  const [full, setFull] = useState(false);
  const reduce = useReducedMotion();
  const box = useRef(null);
  const { data, offline, error } = useDemoData(demoId, params);
  const done = i === steps.length - 1;

  useEffect(() => { setI(0); setParams({}); }, [demoId]);
  useEffect(() => { onProgress && onProgress(i === 0 ? "started" : done ? "completed" : "step", i); }, [i, demoId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const f = () => setFull(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", f);
    return () => document.removeEventListener("fullscreenchange", f);
  }, []);

  const go = useCallback((d) => setI((x) => Math.min(steps.length - 1, Math.max(0, x + d))), [steps.length]);
  const onKey = (e) => {
    if (e.target.closest("input,select,textarea")) return;
    if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
    if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
  };
  const toggleFull = async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (box.current && box.current.requestFullscreen) await box.current.requestFullscreen();
    } catch { /* navegador sem suporte */ }
  };

  if (!demo) return null;
  const step = steps[i];
  const caps = demo.capabilities.map((c) => CAPS[c]).filter(Boolean);

  return (
    <section ref={box} tabIndex={0} onKeyDown={onKey} aria-roledescription="carousel" aria-label={tr(demo.title, lang)}
      className={`rounded-2xl border border-border bg-card shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring ${full ? "fixed inset-0 z-50 overflow-auto rounded-none p-6 sm:p-10" : ""}`}
      data-testid={`demo-player-${demoId}`}>
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4 sm:p-5">
        <div className="min-w-0">
          <p className="text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground">{t("watch")}</p>
          <h3 className={`font-display font-semibold tracking-tight ${full ? "text-3xl" : "text-xl"}`}>{tr(demo.title, lang)}</h3>
          <p className={`mt-1.5 inline-flex items-start gap-1.5 text-xs ${demo.kind === "engine" ? "text-primary" : "text-[#8a5524] dark:text-[#e0a46a]"}`} data-testid="demo-kind">
            {demo.kind === "engine" ? <Cpu className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden /> : <AlertTriangle className="h-3.5 w-3.5 mt-px shrink-0" aria-hidden />}
            {t(`demo_kind.${demo.kind}`)}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">{caps.map((c) => <span key={c.id} className="inline-flex items-center gap-1.5 text-xs">{tr(c.name, lang)} <StatusBadge status={c.status} t={t} /></span>)}</div>
        </div>
        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => setI(0)} className="rounded-lg border border-border p-2 hover:bg-muted" aria-label={t("demo_replay")} title={t("demo_replay")} data-testid="demo-replay"><RotateCcw className="h-4 w-4" /></button>
          <button type="button" onClick={toggleFull} className="rounded-lg border border-border p-2 hover:bg-muted" aria-label={full ? t("demo_exit_fullscreen") : t("demo_fullscreen")} title={full ? t("demo_exit_fullscreen") : t("demo_fullscreen")} data-testid="demo-fullscreen">
            {full ? <Minimize className="h-4 w-4" /> : <Expand className="h-4 w-4" />}
          </button>
        </div>
      </div>

      <ol className="flex gap-1 px-4 sm:px-5 pt-4" aria-label="steps">
        {steps.map((s, k) => (
          <li key={s.id} className="flex-1">
            <button type="button" onClick={() => setI(k)} aria-current={k === i ? "step" : undefined}
              className={`h-1.5 w-full rounded-full transition-colors ${k <= i ? "bg-primary" : "bg-muted"}`} aria-label={`${k + 1}. ${tr(s.title, lang)}`} />
          </li>
        ))}
      </ol>

      <div className={`grid gap-5 p-4 sm:p-5 ${compact ? "" : "lg:grid-cols-[1.35fr_1fr]"}`}>
        <div className="min-h-[260px] rounded-xl border border-border bg-background/60 p-3 sm:p-4 overflow-hidden" aria-live="polite">
          <AnimatePresence mode="wait">
            <motion.div key={`${demoId}-${step.id}`} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              exit={reduce ? undefined : { opacity: 0, y: -6 }} transition={{ duration: reduce ? 0 : 0.25 }}>
              <Visual step={step} data={data} lang={lang} t={t} params={params} setParams={setParams} index={i} />
            </motion.div>
          </AnimatePresence>
        </div>
        <div className="flex flex-col">
          <p className="font-mono text-xs text-muted-foreground">{String(i + 1).padStart(2, "0")} / {String(steps.length).padStart(2, "0")}</p>
          <h4 className={`mt-1 font-display font-semibold ${full ? "text-3xl" : "text-lg"}`}>{tr(step.title, lang)}</h4>
          <p className={`mt-2 leading-relaxed ${full ? "text-xl" : "text-[15px]"}`}>{tr(step.body, lang)}</p>
          <Controls step={step} params={params} setParams={setParams} data={data} lang={lang} t={t} />
          {error === "invalid" && <p className="mt-2 text-xs text-destructive" role="alert">⚠ valor fora do intervalo permitido</p>}
          {offline && <p className="mt-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 p-2.5 text-xs text-amber-900 dark:text-amber-200" data-testid="demo-offline">{t("demo_offline")}</p>}
          {data && ENGINE_DEMOS.includes(demoId) && (
            <p className="mt-3 font-mono text-[11px] text-muted-foreground">{t("demo_engine")}: {(data.takeoff && data.takeoff.engine) || (data.quote && data.quote.engine)}</p>
          )}
          <div className="mt-auto flex flex-wrap items-center gap-2 pt-5">
            <button type="button" onClick={() => go(-1)} disabled={i === 0} className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm disabled:opacity-40" data-testid="demo-prev"><ChevronLeft className="h-4 w-4" aria-hidden />{t("demo_prev")}</button>
            {!done ? (
              <button type="button" onClick={() => go(1)} className="inline-flex items-center gap-1 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground" data-testid="demo-next">{t("demo_next")}<ChevronRight className="h-4 w-4" aria-hidden /></button>
            ) : (
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary" data-testid="demo-done"><CheckCircle2 className="h-4 w-4" aria-hidden />{t("demo_done")}</span>
            )}
          </div>
          {done && alternatives.length > 0 && onSwitch && (
            <div className="mt-4 border-t border-border pt-4">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{t("other_demos")}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {alternatives.map((d) => (
                  <button key={d} type="button" onClick={() => onSwitch(d)} className="rounded-full border border-border px-3 py-1.5 text-sm hover:border-primary/60" data-testid={`demo-switch-${d}`}>{tr(DEMOS[d].title, lang)}</button>
                ))}
              </div>
            </div>
          )}
          {done && (
            <Link to="/demo/entrar" className="mt-4 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-2 hover:underline" data-testid="demo-full-platform">
              {t("demo_full_platform")} <ExternalLink className="h-3.5 w-3.5" aria-hidden />
            </Link>
          )}
        </div>
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ controlos interativos

function Controls({ step, params, setParams, data, lang, t }) {
  const q = data && data.quote;
  if (step.control === "calibration") {
    const v = params.calibration_real_m ?? 5;
    return (
      <label className="mt-4 block rounded-lg border border-primary/30 bg-accent/40 p-3 text-sm">
        <span className="font-medium">↔ {lang === "en" ? "Real length of the reference (m)" : lang === "fr" ? "Longueur réelle de la cote (m)" : "Comprimento real da cota (m)"}</span>
        <input type="range" min="4" max="6" step="0.05" value={v} className="mt-2 w-full accent-[hsl(var(--primary))]"
          onChange={(e) => setParams((p) => ({ ...p, calibration_real_m: Number(e.target.value) }))} data-testid="ctl-calibration" />
        <span className="font-mono text-base">{formatNum(v, lang, 2)} m</span>
      </label>
    );
  }
  if (step.control === "coats") {
    const v = params.coats ?? 2;
    return (
      <div className="mt-4 flex items-center gap-2 text-sm" role="group" aria-label="coats">
        {[1, 2, 3].map((n) => (
          <button key={n} type="button" onClick={() => setParams((p) => ({ ...p, coats: n }))} aria-pressed={v === n}
            className={`rounded-lg border px-3 py-1.5 font-mono ${v === n ? "border-primary bg-primary text-primary-foreground" : "border-border"}`} data-testid={`ctl-coats-${n}`}>{n}×</button>
        ))}
      </div>
    );
  }
  if (!q) return null;
  const line = (k) => q.lines.find((l) => l.key === k);
  const setLine = (k, field, value) => setParams((p) => ({ ...p, lines: { ...(p.lines || {}), [k]: { ...((p.lines || {})[k] || {}), [field]: value } } }));
  if (step.control === "price" || step.control === "cost" || step.control === "discount") {
    const field = { price: "unit_price_ht", cost: "cost_price_ht", discount: "discount_pct" }[step.control];
    const l = line("parquet");
    const cur = (((params.lines || {}).parquet) || {})[field] ?? l[field];
    const range = field === "discount_pct" ? [0, 30, 1] : field === "cost_price_ht" ? [15, 45, 0.5] : [25, 60, 0.5];
    return (
      <label className="mt-4 block rounded-lg border border-primary/30 bg-accent/40 p-3 text-sm">
        <span className="font-medium">{tr(l.label, lang)} — {field === "discount_pct" ? (lang === "fr" ? "remise" : lang === "en" ? "discount" : "desconto") : field === "cost_price_ht" ? (lang === "fr" ? "coût / m²" : lang === "en" ? "cost / m²" : "custo / m²") : (lang === "fr" ? "prix / m²" : lang === "en" ? "price / m²" : "preço / m²")}</span>
        <input type="range" min={range[0]} max={range[1]} step={range[2]} value={cur} className="mt-2 w-full accent-[hsl(var(--primary))]"
          onChange={(e) => setLine("parquet", field, Number(e.target.value))} data-testid={`ctl-${step.control}`} />
        <span className="font-mono text-base">{field === "discount_pct" ? `${cur} %` : formatEurLang(cur, lang, 2)}</span>
      </label>
    );
  }
  return null;
}

// ------------------------------------------------------------------ visuais

function Visual({ step, data, lang, t, params, index }) {
  const tk = data && data.takeoff;
  const q = data && data.quote;
  switch (step.visual) {
    case "plan":
    case "plan_import":
    case "plan_calibrate":
    case "plan_area":
      return tk ? <PlanSvg tk={tk} mode={step.visual} lang={lang} t={t} /> : <Loading t={t} />;
    case "walls":
      return tk ? <Walls tk={tk} lang={lang} /> : <Loading t={t} />;
    case "check":
      return tk ? <Check tk={tk} lang={lang} /> : <Loading t={t} />;
    case "quantities":
      if (tk) return <Quantities tk={tk} lang={lang} />;
      return q ? <QuoteLines q={q} lang={lang} t={t} only="qty" /> : <Loading t={t} />;
    case "paint":
      return tk ? <Paint tk={tk} lang={lang} /> : <Loading t={t} />;
    case "quote_paint":
      return tk ? <PaintQuote tk={tk} lang={lang} t={t} /> : <Loading t={t} />;
    case "limits":
      return <Limits lang={lang} />;
    case "project":
      return <ProjectCard q={q} lang={lang} t={t} />;
    case "quote_lines":
      return q ? <QuoteLines q={q} lang={lang} t={t} /> : <Loading t={t} />;
    case "quote_total":
      return q ? <QuoteTotal q={q} lang={lang} t={t} /> : <Loading t={t} />;
    case "margin_table":
    case "margin_impact":
    case "margin_decide":
      return q ? <MarginTable q={q} lang={lang} t={t} emphasis={step.visual} /> : <Loading t={t} />;
    case "margin_cost":
    case "margin_sale":
      return q ? <QuoteLines q={q} lang={lang} t={t} only={step.visual === "margin_cost" ? "cost" : "sale"} /> : <Loading t={t} />;
    case "margin_formula":
      return q ? <MarginFormula q={q} lang={lang} /> : <Loading t={t} />;
    case "flow":
      return <Flow labels={FLOW_LABELS.documents[lang]} active={step.flowIndex} />;
    case "billing":
      return <Flow labels={FLOW_LABELS.billing[lang]} active={step.flowIndex} conceptual />;
    default:
      return null;
  }
}

function Loading({ t }) {
  return <div className="grid h-60 place-items-center text-sm text-muted-foreground">{t("loading")}</div>;
}

const m2 = (v, lang) => `${formatNum(v, lang, 2)} m²`;
const m = (v, lang) => `${formatNum(v, lang, 2)} m`;

function PlanSvg({ tk, mode, lang }) {
  const room = tk.sample.room_px;
  const cal = tk.sample.calibration_line_px;
  const chk = tk.sample.check_line_px;
  const pts = room.map((p) => p.join(",")).join(" ");
  const showCal = mode === "plan_calibrate" || mode === "plan_area";
  const showArea = mode === "plan_area";
  return (
    <figure>
      <svg viewBox="0 0 680 600" className="w-full h-auto" role="img" aria-label={tr(tk.sample.name, lang)}>
        <defs>
          <pattern id="cpgrid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" fill="none" stroke="hsl(var(--border))" strokeWidth="0.6" /></pattern>
          <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="8" stroke="hsl(var(--primary))" strokeWidth="2" opacity="0.25" /></pattern>
        </defs>
        <rect width="680" height="600" fill="url(#cpgrid)" />
        {mode === "plan_import" && <rect x="40" y="40" width="600" height="520" fill="none" stroke="hsl(var(--primary))" strokeDasharray="8 6" strokeWidth="2" />}
        {showArea && <polygon points={pts} fill="url(#hatch)" />}
        <polygon points={pts} fill="none" stroke="currentColor" strokeWidth="10" strokeLinejoin="miter" />
        {/* porta (sul) e janelas (norte) */}
        <rect x="300" y="474" width="90" height="12" fill="hsl(var(--background))" />
        <path d="M300 480 A90 90 0 0 0 390 390" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="4 4" />
        <rect x="170" y="94" width="120" height="12" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.5" />
        <rect x="350" y="94" width="120" height="12" fill="hsl(var(--background))" stroke="currentColor" strokeWidth="1.5" />
        {/* cota de calibração */}
        <g opacity={showCal ? 1 : 0.35}>
          <line x1={cal[0][0]} y1={cal[0][1]} x2={cal[1][0]} y2={cal[1][1]} stroke="#B87333" strokeWidth={showCal ? 3 : 1.5} />
          <line x1={cal[0][0]} y1={cal[0][1] - 10} x2={cal[0][0]} y2={cal[0][1] + 10} stroke="#B87333" strokeWidth="2" />
          <line x1={cal[1][0]} y1={cal[1][1] - 10} x2={cal[1][0]} y2={cal[1][1] + 10} stroke="#B87333" strokeWidth="2" />
          <text x={(cal[0][0] + cal[1][0]) / 2} y={cal[0][1] + 30} textAnchor="middle" fontFamily="ui-monospace,monospace" fontSize="20" fill="#B87333">
            {showCal ? `${formatNum(tk.calibration.reference_real_distance_m, lang, 2)} m · ${formatNum(tk.calibration.pixels_per_meter, lang, 1)} px/m` : "5,00"}
          </text>
        </g>
        <g opacity="0.5">
          <line x1={chk[0][0]} y1={chk[0][1]} x2={chk[1][0]} y2={chk[1][1]} stroke="currentColor" strokeWidth="1.5" />
          <text x={chk[0][0] - 12} y={(chk[0][1] + chk[1][1]) / 2} textAnchor="middle" fontFamily="ui-monospace,monospace" fontSize="16" transform={`rotate(-90 ${chk[0][0] - 12} ${(chk[0][1] + chk[1][1]) / 2})`}>3,80</text>
        </g>
        {showArea && (
          <g fontFamily="ui-monospace,monospace" textAnchor="middle">
            <text x="310" y="280" fontSize="34" fontWeight="700" fill="hsl(var(--primary))">{m2(tk.room.surface_m2, lang)}</text>
            <text x="310" y="316" fontSize="18" fill="currentColor">P = {m(tk.room.perimeter_m, lang)}</text>
          </g>
        )}
      </svg>
      <figcaption className="mt-1 text-xs text-muted-foreground">{tr(tk.sample.name, lang)}</figcaption>
    </figure>
  );
}

function Row({ k, v, strong, minus }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 border-b border-dashed border-border py-1.5 ${strong ? "font-semibold" : ""}`}>
      <span className="text-sm">{k}</span><span className={`font-mono text-sm ${minus ? "text-[#8a5524] dark:text-[#e0a46a]" : ""}`}>{v}</span>
    </div>
  );
}

const L = (lang, pt, en, fr) => (lang === "en" ? en : lang === "fr" ? fr : pt);

function Walls({ tk, lang }) {
  return (
    <div className="space-y-1">
      <Row k={L(lang, "Perímetro × pé-direito", "Perimeter × ceiling height", "Périmètre × hauteur")} v={`${m(tk.room.perimeter_m, lang)} × ${m(tk.room.ceiling_height_m, lang)} = ${m2(tk.room.wall_area_gross_m2, lang)}`} />
      {tk.walls.openings.map((o, k) => (
        <Row key={k} minus k={`− ${o.kind === "door" ? L(lang, "Porta", "Door", "Porte") : L(lang, "Janela", "Window", "Fenêtre")} ${formatNum(o.width_m, lang, 2)} × ${formatNum(o.height_m, lang, 2)}${o.count > 1 ? ` × ${o.count}` : ""}`} v={`− ${m2(o.area_m2, lang)}`} />
      ))}
      <Row strong k={L(lang, "Paredes líquidas", "Net walls", "Murs nets")} v={m2(tk.walls.wall_area_net_m2, lang)} />
      <Row k={L(lang, "Teto", "Ceiling", "Plafond")} v={m2(tk.room.ceiling_area_m2, lang)} />
      <Row k={L(lang, "Pavimento", "Floor", "Sol")} v={m2(tk.room.surface_m2, lang)} />
    </div>
  );
}

function Check({ tk, lang }) {
  const c = tk.calibration_check;
  return (
    <div className={`rounded-xl border p-4 ${c.ok ? "border-primary/40 bg-accent/40" : "border-amber-500/50 bg-amber-50 dark:bg-amber-900/20"}`} data-testid="calibration-check">
      <p className="flex items-center gap-2 font-semibold">{c.ok ? <CheckCircle2 className="h-5 w-5 text-primary" aria-hidden /> : <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden />}
        {c.recommendation}</p>
      <div className="mt-3 space-y-1">
        <Row k={L(lang, "Cota de controlo esperada", "Expected control dimension", "Cote de contrôle attendue")} v={m(c.expected_m, lang)} />
        <Row k={L(lang, "Medida com a escala atual", "Measured with current scale", "Mesurée avec l'échelle actuelle")} v={m(c.measured_m, lang)} />
        <Row strong k={L(lang, "Diferença", "Difference", "Écart")} v={`${formatNum(c.delta_pct, lang, 2)} %`} />
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{L(lang, "Tolerância: 2 %. Volte ao passo 3 e altere a cota para ver o alerta.", "Tolerance: 2%. Go back to step 3 and change the dimension to see the alert.", "Tolérance : 2 %. Revenez à l'étape 3 et modifiez la cote pour voir l'alerte.")}</p>
    </div>
  );
}

function Quantities({ tk, lang }) {
  const qn = tk.quantities;
  return (
    <div className="space-y-1">
      <Row k={L(lang, "Tinta (paredes + teto, 2 demãos, +15 %)", "Paint (walls + ceiling, 2 coats, +15%)", "Peinture (murs + plafond, 2 couches, +15 %)")} v={`${qn.paint.liters_recommended} L`} />
      <Row k={L(lang, "Pavimento flutuante (+7 % desperdício)", "Floating floor (+7% waste)", "Parquet flottant (+7 % de pertes)")} v={m2(qn.floor.quantity_m2, lang)} />
      <Row k={L(lang, "Rodapé (− porta, +10 %)", "Skirting (− door, +10%)", "Plinthe (− porte, +10 %)")} v={m(qn.skirting.quantity_m, lang)} />
      <p className="pt-2 text-xs text-muted-foreground">{L(lang, "Rendimentos e desperdícios por defeito, ajustáveis na plataforma.", "Default yields and waste, adjustable in the platform.", "Rendements et pertes par défaut, ajustables dans la plateforme.")}</p>
    </div>
  );
}

function Paint({ tk, lang }) {
  const p = tk.quantities.paint;
  return (
    <div className="font-mono text-sm space-y-2">
      <p>{formatNum(p.surface_m2, lang, 2)} m² × {p.coats} ÷ {formatNum(p.yield_m2_per_liter, lang, 0)} m²/L = {formatNum(p.liters_theoretical, lang, 2)} L</p>
      <p>{formatNum(p.liters_theoretical, lang, 2)} L × (1 + {formatNum(p.margin_pct, lang, 0)} %) → ⌈ ⌉ = <b className="text-2xl text-primary">{p.liters_recommended} L</b></p>
    </div>
  );
}

function PaintQuote({ tk, lang, t }) {
  const lines = [
    { k: L(lang, "Pintura de paredes", "Wall painting", "Peinture murs"), q: tk.walls.wall_area_net_m2 },
    { k: L(lang, "Pintura de teto", "Ceiling painting", "Peinture plafond"), q: tk.room.ceiling_area_m2 },
  ];
  return (
    <div>
      {lines.map((l) => <Row key={l.k} k={l.k} v={m2(l.q, lang)} />)}
      <p className="mt-2 text-xs text-muted-foreground">{t("demo_prices_note")}</p>
    </div>
  );
}

function Limits({ lang }) {
  const items = L(lang,
    ["Escolha do produto e rendimento real", "Preparação do suporte e reparações", "Acessos, andaimes e proteções", "Validação final do orçamento"],
    ["Product choice and actual yield", "Surface preparation and repairs", "Access, scaffolding and protection", "Final estimate validation"],
    ["Choix du produit et rendement réel", "Préparation du support et reprises", "Accès, échafaudages et protections", "Validation finale du devis"]);
  return <ul className="list-disc pl-5 space-y-1 text-sm">{items.map((x) => <li key={x}>{x}</li>)}</ul>;
}

function ProjectCard({ q, lang, t }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">{t("demo_sample")}</p>
      <p className="mt-1 font-display text-lg font-semibold">{L(lang, "Remodelação — Sala Moradia T3", "Renovation — 3-bed house living room", "Rénovation — séjour maison T3")}</p>
      <ul className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
        {[L(lang, "Planta", "Drawing", "Plan"), L(lang, "Medições", "Take-off", "Métré"), L(lang, "Orçamento", "Estimate", "Devis")].map((x, k) => (
          <li key={x} className={`rounded-lg border p-2 ${k === 2 ? "border-primary bg-accent/50" : "border-border"}`}>{x}</li>
        ))}
      </ul>
      {q && <p className="mt-3 font-mono text-sm">{L(lang, "Área medida", "Measured area", "Surface mesurée")}: {m2(q.takeoff.surface_m2, lang)}</p>}
    </div>
  );
}

function QuoteLines({ q, lang, t, only }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" data-testid="quote-lines">
        <thead><tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
          <th className="py-1.5 pr-2 font-medium">{L(lang, "Artigo", "Item", "Article")}</th>
          <th className="py-1.5 px-2 font-medium text-right">{L(lang, "Qtd.", "Qty", "Qté")}</th>
          {only !== "qty" && only !== "cost" && <th className="py-1.5 px-2 font-medium text-right">{L(lang, "P. unit.", "Unit", "PU")}</th>}
          {only === "cost" && <th className="py-1.5 px-2 font-medium text-right">{L(lang, "Custo unit.", "Unit cost", "Coût unit.")}</th>}
          {only !== "qty" && <th className="py-1.5 pl-2 font-medium text-right">{only === "cost" ? L(lang, "Custo", "Cost", "Coût") : L(lang, "Total s/ IVA", "Total excl. VAT", "Total HT")}</th>}
        </tr></thead>
        <tbody>
          {q.lines.map((l) => (
            <tr key={l.key} className="border-b border-dashed border-border">
              <td className="py-1.5 pr-2">{tr(l.label, lang)}{l.discount_pct > 0 && only !== "cost" ? <span className="ml-1 rounded bg-[#B87333]/15 px-1 text-[11px]">−{l.discount_pct}%</span> : null}</td>
              <td className="py-1.5 px-2 text-right font-mono whitespace-nowrap">{formatNum(l.qty, lang, 2)} {l.unit === "m2" ? "m²" : "m"}</td>
              {only !== "qty" && only !== "cost" && <td className="py-1.5 px-2 text-right font-mono">{formatEurLang(l.unit_price_ht, lang, 2)}</td>}
              {only === "cost" && <td className="py-1.5 px-2 text-right font-mono">{formatEurLang(l.cost_price_ht, lang, 2)}</td>}
              {only !== "qty" && <td className="py-1.5 pl-2 text-right font-mono">{formatEurLang(only === "cost" ? l.cost_total_ht : l.total_ht, lang, 2)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {only !== "qty" && <p className="mt-2 text-xs text-muted-foreground">{t("demo_prices_note")}</p>}
    </div>
  );
}

function QuoteTotal({ q, lang, t }) {
  return (
    <div>
      <QuoteLines q={q} lang={lang} t={t} />
      <div className="mt-3 flex items-baseline justify-between rounded-xl bg-primary/10 px-4 py-3">
        <span className="font-semibold">{L(lang, "Total sem IVA", "Total excl. VAT", "Total HT")}</span>
        <span className="font-mono text-2xl font-bold text-primary" data-testid="quote-total">{formatEurLang(q.totals.vente_ht, lang, 2)}</span>
      </div>
    </div>
  );
}

function pct(v, lang) { return v == null ? "—" : `${formatNum(v, lang, 1)} %`; }

function MarginTable({ q, lang, emphasis }) {
  return (
    <div>
      <table className="w-full text-sm" data-testid="margin-table">
        <thead><tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
          <th className="py-1.5 pr-2 font-medium">{L(lang, "Especialidade", "Trade", "Lot")}</th>
          <th className="py-1.5 px-2 text-right font-medium">{L(lang, "Venda", "Sale", "Vente")}</th>
          <th className="py-1.5 px-2 text-right font-medium">{L(lang, "Custo", "Cost", "Coût")}</th>
          <th className="py-1.5 px-2 text-right font-medium">{L(lang, "Margem", "Margin", "Marge")}</th>
          <th className="py-1.5 pl-2 text-right font-medium">Markup</th>
        </tr></thead>
        <tbody>
          {q.lots.map((g) => (
            <tr key={g.lot} className="border-b border-dashed border-border">
              <td className="py-1.5 pr-2">{tr(g.label, lang)}</td>
              <td className="py-1.5 px-2 text-right font-mono">{formatEurLang(g.vente_ht, lang, 2)}</td>
              <td className="py-1.5 px-2 text-right font-mono">{formatEurLang(g.cost_prev_ht, lang, 2)}</td>
              <td className={`py-1.5 px-2 text-right font-mono ${emphasis !== "margin_table" ? "font-bold text-primary" : ""}`}>{pct(g.margin_pct, lang)}</td>
              <td className="py-1.5 pl-2 text-right font-mono text-muted-foreground">{pct(g.markup_pct, lang)}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className="py-2 pr-2">Total</td>
            <td className="py-2 px-2 text-right font-mono">{formatEurLang(q.totals.vente_ht, lang, 2)}</td>
            <td className="py-2 px-2 text-right font-mono">{formatEurLang(q.totals.cost_prev_ht, lang, 2)}</td>
            <td className="py-2 px-2 text-right font-mono text-primary" data-testid="margin-total">{pct(q.totals.margin_pct, lang)}</td>
            <td className="py-2 pl-2 text-right font-mono">{pct(q.totals.markup_pct, lang)}</td>
          </tr>
        </tbody>
      </table>
      {emphasis === "margin_decide" && (
        <p className="mt-3 rounded-lg border border-dashed border-border p-2.5 text-xs">{L(lang,
          "Linha sem custo conhecido → margem «—» (não calculada), para não sobrestimar o resultado.",
          "Line without a known cost → margin “—” (not computed), so the result is never overstated.",
          "Ligne sans coût connu → marge « — » (non calculée), pour ne jamais surestimer le résultat.")}</p>
      )}
    </div>
  );
}

function MarginFormula({ q, lang }) {
  const s = q.totals.vente_ht, c = q.totals.cost_prev_ht;
  return (
    <div className="space-y-3 font-mono text-sm">
      <div className="rounded-xl border border-primary/30 bg-accent/40 p-3">
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-sans">{L(lang, "Margem", "Margin", "Marge")}</p>
        <p>({formatEurLang(s, lang, 2)} − {formatEurLang(c, lang, 2)}) ÷ {formatEurLang(s, lang, 2)} = <b className="text-lg text-primary">{pct(q.totals.margin_pct, lang)}</b></p>
      </div>
      <div className="rounded-xl border border-border p-3">
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-sans">Markup</p>
        <p>({formatEurLang(s, lang, 2)} − {formatEurLang(c, lang, 2)}) ÷ {formatEurLang(c, lang, 2)} = <b className="text-lg">{pct(q.totals.markup_pct, lang)}</b></p>
      </div>
      <p className="font-sans text-xs text-muted-foreground">{L(lang, "Coeficiente venda/custo", "Sale/cost coefficient", "Coefficient vente/coût")}: {formatNum(q.totals.coefficient, lang, 3)}</p>
    </div>
  );
}

function Flow({ labels, active, conceptual }) {
  return (
    <div className="py-6">
      {conceptual && <p className="mb-4 inline-block rounded bg-[#B87333]/15 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-[#8a5524] dark:text-[#e0a46a]">Ilustração · Illustration</p>}
      <ol className="grid gap-2 sm:grid-cols-5">
        {labels.map((x, k) => (
          <li key={x} className={`relative rounded-xl border p-3 text-center text-sm transition-colors ${k === active ? "border-primary bg-primary text-primary-foreground shadow" : k < active ? "border-primary/40 bg-accent/50" : "border-border bg-card text-muted-foreground"}`}>
            <span className="block font-mono text-[11px]">{String(k + 1).padStart(2, "0")}</span>{x}
          </li>
        ))}
      </ol>
    </div>
  );
}
