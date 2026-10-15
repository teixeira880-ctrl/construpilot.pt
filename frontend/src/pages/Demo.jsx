import { useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  Mic, MicOff, Sparkles, Loader2, RotateCcw, LogOut, Footprints,
  Ruler, Receipt, LayoutDashboard, FileCheck2, CheckCircle2, ExternalLink,
} from "lucide-react";
import axios from "axios";
import { LangToggle, useI18n } from "@/context/I18nContext";
import scenarios from "@/demo/scenarios.json";
import "@/styles/demo.css";

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

export default function Demo() {
  const { lang } = useI18n();
  const [prompt, setPrompt] = useState("");
  const [current, setCurrent] = useState(null); // scenario
  const [result, setResult] = useState(null); // {output, elapsed_ms, source}
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);

  const recognitionAvailable = useMemo(
    () =>
      typeof window !== "undefined" &&
      Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    []
  );

  const toggleMic = () => {
    if (!recognitionAvailable) return;
    if (listening) {
      try {
        recRef.current?.stop();
      } catch {
        /* vazio */
      }
      setListening(false);
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const r = new SR();
    r.lang = lang === "fr" ? "fr-FR" : lang === "en" ? "en-GB" : "pt-PT";
    r.continuous = false;
    r.interimResults = true;
    r.onresult = (e) => {
      const txt = Array.from(e.results)
        .map((x) => x[0].transcript)
        .join(" ");
      setPrompt(txt);
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recRef.current = r;
    try {
      r.start();
      setListening(true);
    } catch {
      setListening(false);
    }
  };

  const runScenario = async (scen) => {
    setCurrent(scen);
    setPrompt(promptFor(scen, lang));
    setBusy(true);
    setResult(null);
    const out = await fetchWithFallback(scen, promptFor(scen, lang));
    setResult({ output: scen.output, elapsed_ms: out.elapsed_ms, source: out.source });
    setBusy(false);
  };

  const reset = () => {
    setCurrent(null);
    setPrompt("");
    setResult(null);
    setBusy(false);
  };

  return (
    <div className="demo-root" data-testid="demo-root">
      {/* Top bar */}
      <div className="demo-topbar">
        <Link to="/" data-testid="demo-exit" className="demo-top-btn">
          <LogOut className="h-4 w-4" />
          <span className="demo-top-label">Sair da demo</span>
        </Link>
        <div className="demo-brand">
          <span className="demo-brand-mark">C</span>
          <span className="demo-brand-name">ConstruPilot</span>
          <span className="demo-brand-tag">Web Summit · Lisboa 2026</span>
        </div>
        <div className="demo-lang">
          <LangToggle testId="demo-lang-toggle" />
        </div>
      </div>

      {/* Prompt bar */}
      <div className="demo-prompt-wrap">
        <div className="demo-prompt-box">
          <input
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Descreva o que quer calcular, medir ou orçamentar…"
            className="demo-prompt-input"
            data-testid="demo-prompt-input"
            disabled={busy}
          />
          {recognitionAvailable && (
            <button
              type="button"
              onClick={toggleMic}
              className={`demo-mic ${listening ? "is-listening" : ""}`}
              data-testid="demo-mic"
              aria-label={listening ? "Parar ditado" : "Ditar"}
            >
              {listening ? <MicOff className="h-6 w-6" /> : <Mic className="h-6 w-6" />}
            </button>
          )}
          <button
            type="button"
            onClick={() => current && runScenario(current)}
            disabled={busy || !current}
            className="demo-generate"
            data-testid="demo-generate"
          >
            {busy ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <Sparkles className="h-5 w-5" />
            )}
            Gerar
          </button>
        </div>
      </div>

      {/* Scenarios */}
      <div className="demo-scenarios" data-testid="demo-scenarios">
        {scenarios.scenarios.map((s) => {
          const Icon = ICONS[s.icon] || Sparkles;
          const active = current?.id === s.id;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => runScenario(s)}
              disabled={busy}
              className={`demo-scn-btn ${active ? "is-active" : ""}`}
              data-testid={`demo-scn-${s.id}`}
            >
              <Icon className="h-7 w-7" aria-hidden />
              <span className="demo-scn-label">{titleFor(s, lang)}</span>
            </button>
          );
        })}
      </div>

      {/* Result area */}
      <div className="demo-result-area" data-testid="demo-result-area">
        <AnimatePresence mode="wait">
          {busy && (
            <motion.div
              key="busy"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="demo-busy"
              data-testid="demo-busy"
            >
              <Loader2 className="h-8 w-8 animate-spin" />
              <p>A gerar com IA…</p>
            </motion.div>
          )}
          {!busy && result && (
            <motion.div
              key={current.id}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="demo-result"
              data-testid="demo-result"
            >
              <ResultView output={result.output} />
              <div className="demo-elapsed" data-testid="demo-elapsed">
                <Sparkles className="h-5 w-5" aria-hidden />
                Gerado em {fmtSec(result.elapsed_ms)} segundos
              </div>
              <button
                type="button"
                onClick={reset}
                className="demo-restart"
                data-testid="demo-restart"
              >
                <RotateCcw className="h-4 w-4" /> Reiniciar
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
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
