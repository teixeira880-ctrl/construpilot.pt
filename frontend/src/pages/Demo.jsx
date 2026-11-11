import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic, MicOff, Sparkles, Loader2, RotateCcw, LogOut, Footprints,
  Ruler, Receipt, LayoutDashboard, FileCheck2, CheckCircle2, ExternalLink,
} from "lucide-react";
import axios from "axios";
import { api } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import scenarios from "@/demo/scenarios.json";
import "@/styles/demo.css";
import { currentUiLocale } from "@/lib/uiLang";

const BACKEND = process.env.REACT_APP_BACKEND_URL;
const ICONS = { Footprints, Ruler, Receipt, LayoutDashboard, FileCheck2 };

const titleFor = (s, lang) => s[`title_${lang}`] || s.title_pt;
const promptFor = (s, lang) => s[`prompt_${lang}`] || s.prompt_pt;

// Chama o backend sem cookies de sessão. Em falha (401/timeout/offline),
// cai silenciosamente para a resposta pré-calculada do cenário.
async function fetchWithFallback(scenario, prompt) {
  const start = performance.now();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1800);
  try {
    const res = await axios.post(
      `${BACKEND}/api/prompt-fill/${scenario.app_key}`,
      { prompt },
      { signal: controller.signal, withCredentials: false, timeout: 1800 }
    );
    clearTimeout(timeout);
    if (res.data?.ok) {
      return {
        data: res.data,
        elapsed_ms: Math.round(performance.now() - start),
        source: "live",
      };
    }
  } catch {
    /* silencioso — fallback abaixo */
  }
  // tempo simulado para não parecer «instantâneo»
  await new Promise((r) => setTimeout(r, scenario.elapsed_target_ms));
  return {
    data: scenario.ai_response,
    elapsed_ms: scenario.elapsed_target_ms,
    source: "fallback",
  };
}

function fmtSec(ms) {
  return (ms / 1000).toFixed(1).replace(".", ",");
}

// Textos do ecrã (mesmo desenho que construpilot.fr/demo).
const UI = {
  pt: { tag: "Demo ConstruPilot", sub: "Descreva o seu projeto — a IA faz o resto.", examples: "Exemplos num clique", gen: "Gerar",
        placeholder: "Ex.: escada em meio quarto, 2,70 m de pé-direito, largura 90 cm", busy: "A gerar com IA…", done: (s) => `Gerado em ${s} segundos`,
        reset: "Reiniciar", exit: "Sair da demo", footer: "ConstruPilot · demonstração · dados fictícios",
        full: "Entrar numa demo completa", pro: "Demo Pro (empresa)", part: "Demo Particular", na: "Demo indisponível de momento",
        hint: "Contas de demonstração — dados fictícios, envios reais desativados, reiniciadas todos os dias." },
  fr: { tag: "Démo ConstruPilot", sub: "Décrivez votre projet — l'IA fait le reste.", examples: "Exemples en un clic", gen: "Générer",
        placeholder: "Ex. escalier demi-quart tournant, 2,70 m à monter, largeur 90 cm", busy: "Génération par l'IA…", done: (s) => `Généré en ${s} secondes`,
        reset: "Réinitialiser", exit: "Quitter la démo", footer: "ConstruPilot · démonstration · données fictives",
        full: "Entrer dans une démo complète", pro: "Démo Pro (entreprise)", part: "Démo Particulier", na: "Démo indisponible pour le moment",
        hint: "Comptes de démonstration — données fictives, envois réels désactivés, remis à zéro chaque jour." },
  en: { tag: "ConstruPilot Demo", sub: "Describe your project — AI does the rest.", examples: "One-click examples", gen: "Generate",
        placeholder: "E.g. half-turn staircase, 2.70 m rise, 90 cm wide", busy: "Generating with AI…", done: (s) => `Generated in ${s} seconds`,
        reset: "Reset", exit: "Exit demo", footer: "ConstruPilot · demo · sample data",
        full: "Enter a full demo", pro: "Pro demo (company)", part: "Homeowner demo", na: "Demo unavailable right now",
        hint: "Demo accounts — sample data, real sends disabled, reset every day." },
};

// Texto livre → cenário mais próximo (o botão Gerar funciona sempre, mesmo sem exemplo escolhido).
const KEYWORDS = [
  ["escada_meio_quarto", /escad|degra|stair|escalier|marche/i],
  ["leitura_planta", /plant|plan\b|plans\b|planta|lecture|ler a|divis(õ|o)es da/i],
  ["comunicacao_previa", /comunica|licen|autoriza|câmara|camara|permis|d[ée]claration|urbanis|anexo|marquise|muro/i],
  ["medicao_divisao", /medi|m(é|e)tr|área|area|surface|parede|pintur|teto|chão|chao|pavimento|m2|m²/i],
];
function pickScenario(text) {
  const list = scenarios.scenarios;
  for (const [id, re] of KEYWORDS) if (re.test(text)) return list.find((s) => s.id === id);
  return list.find((s) => s.id === "orcamento_remodelacao") || list[0];
}

export default function Demo() {
  const { lang, setLang } = useI18n();
  const { demoLogin } = useAuth();
  const navigate = useNavigate();
  const t = UI[lang] || UI.pt;
  const [prompt, setPrompt] = useState("");
  const [current, setCurrent] = useState(null); // scenario
  const [result, setResult] = useState(null); // {output, elapsed_ms, source}
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [avail, setAvail] = useState(null); // {pro, particular}
  const [entering, setEntering] = useState("");
  const recRef = useRef(null);

  useEffect(() => {
    api.get("/auth/demo-status", { timeout: 6000 })
      .then(({ data }) => setAvail(data || {}))
      .catch(() => setAvail({ pro: false, particular: false }));
  }, []);

  const recognitionAvailable = useMemo(
    () => typeof window !== "undefined" && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    []
  );

  const toggleMic = () => {
    if (!recognitionAvailable) return;
    if (listening) { try { recRef.current?.stop(); } catch { /* vazio */ } setListening(false); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = new SR();
    r.lang = currentUiLocale();
    r.continuous = false;
    r.interimResults = true;
    r.onresult = (e) => setPrompt(Array.from(e.results).map((x) => x[0].transcript).join(" "));
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recRef.current = r;
    try { r.start(); setListening(true); } catch { setListening(false); }
  };

  const run = async (scen, text) => {
    setCurrent(scen);
    setPrompt(text);
    setBusy(true);
    setResult(null);
    const out = await fetchWithFallback(scen, text);
    setResult({ output: scen.output, elapsed_ms: out.elapsed_ms, source: out.source });
    setBusy(false);
    if (navigator.vibrate) navigator.vibrate(12);
  };
  const runScenario = (scen) => run(scen, promptFor(scen, lang));
  const submit = (e) => {
    e?.preventDefault();
    const text = prompt.trim();
    if (busy) return;
    if (!text) { if (current) runScenario(current); return; }
    run(pickScenario(text), text);
  };
  const reset = () => { setCurrent(null); setPrompt(""); setResult(null); setBusy(false); };

  const enterDemo = async (kind) => {
    setEntering(kind);
    try {
      await demoLogin(kind);
      navigate(kind === "pro" ? "/assistant" : "/dashboard");
    } catch {
      setAvail((a) => ({ ...(a || {}), [kind]: false }));
      setEntering("");
    }
  };

  const showIntro = !busy && !result;
  return (
    <div className="fixed inset-0 z-[60] overflow-y-auto overflow-x-hidden bg-gradient-to-b from-[#0d1f17] to-[#13261c] text-white flex flex-col"
      style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }} data-testid="demo-root">
      <header className="flex items-center justify-between gap-3 px-5 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/" data-testid="demo-exit" aria-label={t.exit} title={t.exit}
            className="inline-grid place-items-center h-9 w-9 rounded-full bg-white/10 hover:bg-white/15 shrink-0"><LogOut className="h-4 w-4" /></Link>
          <div className="flex items-center gap-2 font-bold text-lg md:text-2xl tracking-tight truncate">
            <span className="text-[#5fd39a]">●</span> ConstruPilot
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {["fr", "pt", "en"].map((l) => (
            <button key={l} type="button" onClick={() => l !== lang && setLang(l)} data-testid={`demo-lang-${l}`}
              className={`text-sm md:text-base rounded-full px-3 py-1 uppercase ${lang === l ? "bg-[#5fd39a] text-[#0d1f17] font-semibold" : "bg-white/10"}`}>{l}</button>
          ))}
        </div>
      </header>

      <main className="flex-1 w-full max-w-4xl mx-auto px-4 sm:px-5 flex flex-col justify-center gap-6 pb-6">
        {showIntro && (
          <div className="text-center grid gap-2">
            <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight">{t.tag}</h1>
            <p className="text-lg md:text-2xl text-white/70">{t.sub}</p>
          </div>
        )}

        {showIntro && (
          <div className="grid gap-3 rounded-2xl bg-white/5 border border-white/10 p-4" data-testid="demo-login-banner">
            <div className="text-sm md:text-base font-semibold text-white/90">{t.full}</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {["pro", "particular"].map((kind) => {
                const ok = avail?.[kind];
                return (
                  <button key={kind} type="button" data-testid={`demo-enter-${kind}`} disabled={!ok || !!entering} onClick={() => enterDemo(kind)}
                    className={`rounded-xl px-4 py-3 text-base font-semibold transition-all active:scale-[0.98] ${ok ? "bg-[#5fd39a] text-[#0d1f17] hover:bg-[#54c78e]" : "bg-white/10 text-white/40 cursor-not-allowed"}`}>
                    {entering === kind ? <Loader2 className="h-5 w-5 animate-spin mx-auto" /> : (kind === "pro" ? t.pro : t.part)}
                  </button>
                );
              })}
            </div>
            {avail && !avail.pro && !avail.particular && <div className="text-sm text-amber-300" data-testid="demo-unavailable">{t.na}</div>}
            <div className="text-xs text-white/40">{t.hint}</div>
          </div>
        )}

        <form onSubmit={submit} className="flex items-center gap-2 bg-white rounded-2xl p-2 shadow-2xl min-w-0" data-testid="demo-prompt-box">
          <input type="text" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t.placeholder} disabled={busy}
            className="flex-1 min-w-0 bg-transparent outline-none text-[#14211d] placeholder:text-[#6b7772] text-base md:text-lg px-3 py-2"
            data-testid="demo-prompt-input" aria-label={t.placeholder} />
          {recognitionAvailable && (
            <button type="button" onClick={toggleMic} data-testid="demo-mic" aria-label={listening ? "Stop" : "Mic"}
              className={`inline-grid place-items-center h-11 w-11 shrink-0 rounded-xl border ${listening ? "bg-[#e05a4a] border-[#e05a4a] text-white" : "border-[#e2e5e0] text-[#285541]"}`}>
              {listening ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>
          )}
          <button type="submit" disabled={busy} data-testid="demo-generate"
            className="inline-flex items-center gap-2 shrink-0 h-11 rounded-xl px-3 sm:px-4 bg-[#285541] text-white font-semibold disabled:opacity-60">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <Sparkles className="h-5 w-5" />}
            <span className="hidden sm:inline">{t.gen}</span>
          </button>
        </form>

        {showIntro && (
          <div className="grid gap-2" data-testid="demo-scenarios">
            <div className="text-sm md:text-base text-white/60 uppercase tracking-wide">{t.examples}</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {scenarios.scenarios.map((s) => {
                const Icon = ICONS[s.icon] || Sparkles;
                return (
                  <button key={s.id} type="button" onClick={() => runScenario(s)} disabled={busy} data-testid={`demo-scn-${s.id}`}
                    className="flex items-center gap-3 rounded-2xl bg-white/10 hover:bg-white/15 active:scale-[0.98] transition-all p-4 text-left min-h-[64px]">
                    <Icon className="h-7 w-7 text-[#5fd39a] shrink-0" aria-hidden />
                    <span className="text-base md:text-lg font-medium leading-tight">{titleFor(s, lang)}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <AnimatePresence mode="wait">
          {busy && (
            <motion.div key="busy" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className="flex items-center justify-center gap-3 text-white/80 py-10" data-testid="demo-busy">
              <Loader2 className="h-8 w-8 animate-spin" /> <p>{t.busy}</p>
            </motion.div>
          )}
          {!busy && result && current && (
            <motion.div key={current.id} initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.4 }}
              className="demo-result" data-testid="demo-result">
              <ResultView output={result.output} />
              <div className="flex flex-wrap items-center gap-3 mt-4">
                <div className="demo-elapsed" data-testid="demo-elapsed"><Sparkles className="h-5 w-5" aria-hidden /> {t.done(fmtSec(result.elapsed_ms))}</div>
                <button type="button" onClick={reset} className="demo-restart" data-testid="demo-restart"><RotateCcw className="h-4 w-4" /> {t.reset}</button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
      <footer className="text-center text-white/40 text-xs py-3">{t.footer}</footer>
    </div>
  );
}

function ResultView({ output }) {
  if (!output) return null;
  switch (output.kind) {
    case "stairs":
      return <StairsResult o={output} />;
    case "measurements":
      return <MeasurementsResult o={output} />;
    case "budget":
      return <BudgetResult o={output} />;
    case "plan":
      return <PlanResult o={output} />;
    case "procedure":
      return <ProcedureResult o={output} />;
    default:
      return null;
  }
}

function StairsResult({ o }) {
  const n = o.num_degraus;
  const items = Array.from({ length: n }, (_, i) => i);
  return (
    <div className="demo-stairs" data-testid="demo-result-stairs">
      <h2 className="demo-title">Escada em meio quarto</h2>
      <svg viewBox="0 0 400 220" className="demo-stairs-svg" aria-label="Esquema da escada">
        {items.map((i) => (
          <motion.rect
            key={i}
            x={10 + i * (380 / n)}
            y={200 - (i + 1) * (190 / n)}
            width={380 / n - 2}
            height={(i + 1) * (190 / n)}
            fill="#3fcf8e"
            stroke="#1b3f2d"
            strokeWidth="1"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.12, duration: 0.3 }}
          />
        ))}
      </svg>
      <ul className="demo-kv">
        <li><span>Degraus</span><strong>{o.num_degraus}</strong></li>
        <li><span>Espelho</span><strong>{o.espelho_mm} mm</strong></li>
        <li><span>Cobertor</span><strong>{o.cobertor_mm} mm</strong></li>
        <li><span>Inclinação</span><strong>{String(o.inclinacao_graus).replace(".", ",")}°</strong></li>
        <li><span>Blondel</span><strong>{o.blondel_mm} mm</strong></li>
        <li><span>RGEU</span><strong className="demo-ok"><CheckCircle2 className="h-4 w-4 inline" /> conforme</strong></li>
      </ul>
    </div>
  );
}

function MeasurementsResult({ o }) {
  return (
    <div className="demo-measurements" data-testid="demo-result-measurements">
      <h2 className="demo-title">Medição da divisão</h2>
      <ul className="demo-mes-list">
        {o.items.map((it, i) => (
          <motion.li
            key={it.label}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.18, duration: 0.35 }}
          >
            <span className="demo-mes-lbl">{it.label}</span>
            <span className="demo-mes-val">
              {String(it.value).replace(".", ",")} {it.unit}
            </span>
            <span className="demo-mes-det">{it.detail}</span>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

function BudgetResult({ o }) {
  const max = Math.max(...o.lotes.map((l) => l.value));
  return (
    <div className="demo-budget" data-testid="demo-result-budget">
      <h2 className="demo-title">Estimativa de remodelação</h2>
      <div className="demo-budget-total">
        <span>Total estimado</span>
        <strong>{o.total_eur.toLocaleString("pt-PT")} €</strong>
      </div>
      <ul className="demo-budget-bars">
        {o.lotes.map((l, i) => (
          <li key={l.label}>
            <div className="demo-bar-lbl">
              <span>{l.label}</span>
              <span>{l.value.toLocaleString("pt-PT")} €</span>
            </div>
            <div className="demo-bar-track">
              <motion.div
                className="demo-bar-fill"
                initial={{ width: 0 }}
                animate={{ width: `${(l.value / max) * 100}%` }}
                transition={{ delay: 0.1 + i * 0.14, duration: 0.6, ease: "easeOut" }}
              />
            </div>
          </li>
        ))}
      </ul>
      <p className="demo-small">Valores indicativos (±15 %) · base de referência 2026.</p>
    </div>
  );
}

function PlanResult({ o }) {
  return (
    <div className="demo-plan" data-testid="demo-result-plan">
      <h2 className="demo-title">Leitura da planta</h2>
      <div className="demo-plan-canvas" aria-label="Planta esquemática">
        {o.divisoes.map((d, i) => (
          <motion.div
            key={d.nome}
            className="demo-plan-room"
            style={{
              left: `${d.x_pct}%`,
              top: `${d.y_pct}%`,
              width: `${d.w_pct}%`,
              height: `${d.h_pct}%`,
            }}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: i * 0.15, duration: 0.35 }}
          >
            <span className="demo-plan-name">{d.nome}</span>
            <span className="demo-plan-area">
              {String(d.area_m2).replace(".", ",")} m²
            </span>
          </motion.div>
        ))}
      </div>
      <p className="demo-plan-total">
        {o.piso} · Área útil total: <strong>{String(o.area_util_total_m2).replace(".", ",")} m²</strong>
      </p>
    </div>
  );
}

function ProcedureResult({ o }) {
  return (
    <div className="demo-procedure" data-testid="demo-result-procedure">
      <h2 className="demo-title">Comunicação prévia — anexo</h2>
      <div className="demo-proc-badge">
        <CheckCircle2 className="h-6 w-6" />
        <div>
          <strong>{o.procedimento_label}</strong>
          <span>{o.isento_controlo_previo ? "Isento de controlo prévio" : "Sujeito a controlo prévio"}</span>
        </div>
      </div>
      <div className="demo-proc-legal">
        <span className="demo-proc-legal-lbl">Fundamento legal</span>
        <a
          href={o.fundamento_link}
          target="_blank"
          rel="noopener noreferrer"
          className="demo-proc-legal-link"
          data-testid="demo-proc-link"
        >
          {o.fundamento_legal} <ExternalLink className="h-4 w-4 inline" />
        </a>
      </div>
      <ul className="demo-proc-reqs">
        {o.requisitos.map((r, i) => (
          <motion.li
            key={r}
            initial={{ opacity: 0, x: -16 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.1 + i * 0.12 }}
          >
            <CheckCircle2 className="h-4 w-4" /> {r}
          </motion.li>
        ))}
      </ul>
      <p className="demo-proc-next"><strong>Próximo passo:</strong> {o.proximo_passo}</p>
    </div>
  );
}
