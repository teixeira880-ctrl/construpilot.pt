import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Flame, Mic, Sparkles } from "lucide-react";

const CHIPS = ["Orçamentar uma casa de banho", "Armadura de uma viga", "Lembrar um cliente"];
export const ASSISTANT_PREFILL = "cp_assistant_prefill";
export const ASSISTANT_VOICE = "cp_assistant_voice";

// Abre o Assistente (/coach) com o pedido pré-preenchido (lido ao montar a página do Assistente).
const openAssistant = (navigate, text, voice = false) => {
  try {
    if (text) sessionStorage.setItem(ASSISTANT_PREFILL, text);
    if (voice) sessionStorage.setItem(ASSISTANT_VOICE, "1");
  } catch { /* armazenamento indisponível */ }
  navigate("/coach");
};

export function AssistantHero() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const submit = (e) => { e.preventDefault(); openAssistant(navigate, text.trim()); };
  return (
    <section aria-label="Assistente ConstruPilot"
      className="cp-lift relative overflow-hidden rounded-3xl p-5 sm:p-6 text-white flex flex-col gap-4 lg:col-span-4 lg:row-span-2 min-h-[270px]"
      style={{ background: "radial-gradient(ellipse 70% 80% at 100% 0%, #2f9e77 0%, #2f9e7700 60%), radial-gradient(ellipse 60% 70% at 0% 100%, #6d5bd0 0%, #6d5bd000 60%), #17483f" }}
      data-testid="dashboard-assistant-hero">
      <div className="flex items-center gap-2.5">
        <span className="cp-app-tile inline-grid place-items-center h-10 w-10 rounded-xl rotate-[-6deg]" data-family="ia"
          style={{ backgroundImage: "linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 50%, #d946ef 100%)" }}>
          <Sparkles size={22} color="#fff" aria-hidden="true" />
        </span>
        <span className="font-display text-xl font-semibold">Assistente</span>
      </div>
      <p className="font-display text-[24px] sm:text-[30px] font-semibold leading-tight tracking-tight max-w-[560px]">
        Um cálculo, um orçamento, uma carta… diga, está feito.
      </p>
      <form onSubmit={submit} className="mt-auto flex items-center gap-2 h-14 rounded-2xl bg-white text-foreground ps-4 pe-2" data-testid="dashboard-assistant-form">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ex.: pré-certificado REH da moradia Silva" aria-label="Pedido ao Assistente"
          className="flex-1 min-w-0 bg-transparent outline-none text-[15px] text-[#14211d] placeholder:text-[#5f6b66]" data-testid="dashboard-assistant-input" />
        <button type="button" aria-label="Ditar" title="Ditar" onClick={() => openAssistant(navigate, text.trim(), true)} data-testid="dashboard-assistant-mic"
          className="inline-grid place-items-center h-11 w-11 rounded-xl border border-[#e2e5e0] text-[#33403b] hover:bg-[#f3f4f1] transition-colors"><Mic size={18} aria-hidden="true" /></button>
        <button type="submit" aria-label="Enviar ao Assistente" title="Enviar ao Assistente" className="inline-grid place-items-center h-11 w-11 rounded-xl text-white"
          style={{ backgroundImage: "linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 50%, #d946ef 100%)" }} data-testid="dashboard-assistant-send">
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {CHIPS.map((chip) => (
          <button key={chip} type="button" onClick={() => openAssistant(navigate, chip)}
            className="min-h-[36px] px-3 rounded-full border border-white/25 bg-white/10 text-[13px] font-semibold hover:bg-white/20 transition-colors">{chip}</button>
        ))}
      </div>
    </section>
  );
}

const WEEK = 7 * 864e5;
const weekStart = (d) => { const x = new Date(d); const day = (x.getDay() + 6) % 7; x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - day); return x.getTime(); };

// Objetivo semanal e série, calculados sobre os projetos reais (data de criação); objetivo ajustável, guardado localmente.
export function WeekGoal({ projects, ready }) {
  const [goal, setGoal] = useState(() => { try { return Math.max(1, Number(localStorage.getItem("cp_week_goal")) || 3); } catch { return 3; } });
  const weeks = new Set((projects || []).map((p) => p.created_at && weekStart(p.created_at)).filter(Boolean));
  const now = weekStart(Date.now());
  const done = (projects || []).filter((p) => p.created_at && weekStart(p.created_at) === now).length;
  let streak = 0;
  for (let w = weeks.has(now) ? now : now - WEEK; weeks.has(w); w = weekStart(w - WEEK / 2)) streak += 1;
  const pct = Math.min(1, done / goal);
  const C = 2 * Math.PI * 36;
  const cycle = () => { const next = goal >= 10 ? 1 : goal + 1; setGoal(next); try { localStorage.setItem("cp_week_goal", String(next)); } catch { /* ignorar */ } };
  return (
    <section className="cp-glass cp-lift rounded-3xl p-5 flex items-center gap-4 lg:col-span-2" data-testid="dashboard-week-goal">
      <svg width="88" height="88" viewBox="0 0 88 88" role="img" aria-label={`Objetivo da semana: ${done} de ${goal}`} className="shrink-0">
        <circle cx="44" cy="44" r="36" fill="none" stroke="hsl(var(--muted))" strokeWidth="10" />
        <circle cx="44" cy="44" r="36" fill="none" stroke="#16a34a" strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(ready ? pct : 0) * C} ${C}`} transform="rotate(-90 44 44)" style={{ transition: "stroke-dasharray .6s ease" }} />
        <text x="44" y="50" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="20" fontWeight="700" fill="currentColor">{ready ? `${done}/${goal}` : "—"}</text>
      </svg>
      <div className="min-w-0">
        <p className="text-[13px] font-bold text-muted-foreground">Esta semana</p>
        <p className="font-display text-xl font-semibold leading-tight">novos projetos</p>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          {streak > 0 && (
            <span className="inline-flex items-center gap-1.5 text-[12.5px] font-bold text-[#9a3412] bg-[#ffedd5] rounded-full px-2.5 py-1" data-testid="dashboard-streak">
              <Flame size={13} className="text-[#ea580c]" aria-hidden="true" />{streak} semana{streak > 1 ? "s" : ""} seguida{streak > 1 ? "s" : ""}
            </span>
          )}
          <button type="button" onClick={cycle} className="min-h-[32px] text-[12px] font-semibold text-muted-foreground underline-offset-2 hover:underline" data-testid="dashboard-goal-change">
            Objetivo: {goal}
          </button>
        </div>
      </div>
    </section>
  );
}
