import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Flame, Mic } from "lucide-react";
import { AssistantIcon } from "@/components/workspace/navigation";

const T = {
  fr: { punch: "Un calcul, un devis, un courrier… dis-le, c'est fait.", ph: "Ex. : DPE avant / après de la maison Martin", send: "Envoyer à l'Assistant", dictate: "Dicter",
        chips: ["Chiffrer une salle de bain", "Ferraillage d'une poutre", "Relancer un client"],
        goal: "Cette semaine", goalLabel: "nouveaux projets", streak: (n) => `${n} semaine${n > 1 ? "s" : ""} d'affilée`, goalAria: (a, b) => `Objectif de la semaine : ${a} sur ${b}`, change: "Objectif" },
  pt: { punch: "Um cálculo, um orçamento, uma carta… diga, está feito.", ph: "Ex.: pré-certificado REH da moradia Silva", send: "Enviar ao Assistente", dictate: "Ditar",
        chips: ["Orçamentar uma casa de banho", "Armadura de uma viga", "Lembrar um cliente"],
        goal: "Esta semana", goalLabel: "novos projetos", streak: (n) => `${n} semana${n > 1 ? "s" : ""} seguida${n > 1 ? "s" : ""}`, goalAria: (a, b) => `Objetivo da semana: ${a} de ${b}`, change: "Objetivo" },
  en: { punch: "A calculation, a quote, a letter… say it, it's done.", ph: "E.g. energy rating before / after for the Martin house", send: "Send to the Assistant", dictate: "Dictate",
        chips: ["Price a bathroom", "Reinforce a beam", "Chase a client"],
        goal: "This week", goalLabel: "new projects", streak: (n) => `${n}-week streak`, goalAria: (a, b) => `Weekly goal: ${a} of ${b}`, change: "Goal" },
};
const copy = (lang) => T[lang] || T.pt;

// Ouvre l'Assistant avec la demande pré-remplie (lue au montage de la page Assistant).
const openAssistant = (navigate, text) => {
  try { if (text) sessionStorage.setItem("cp_assistant_prefill", text); } catch { /* stockage indisponible */ }
  navigate("/assistant");
};

export function AssistantHero({ lang, title }) {
  const c = copy(lang);
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const submit = (e) => { e.preventDefault(); openAssistant(navigate, text.trim()); };
  return (
    <section aria-label={title} className="cp-lift relative overflow-hidden rounded-3xl p-6 text-white flex flex-col gap-4 lg:col-span-4 lg:row-span-2 min-h-[270px]"
      style={{ background: "radial-gradient(ellipse 70% 80% at 100% 0%, #2f9e77 0%, #2f9e7700 60%), radial-gradient(ellipse 60% 70% at 0% 100%, #6d5bd0 0%, #6d5bd000 60%), #17483f" }}
      data-testid="dashboard-assistant-hero">
      <div className="flex items-center gap-2.5">
        <span className="inline-grid place-items-center h-10 w-10 rounded-xl overflow-hidden rotate-[-6deg] shadow-lg"><AssistantIcon size={40} /></span>
        <span className="font-display text-xl font-semibold">{title}</span>
      </div>
      <p className="font-display text-[26px] sm:text-[30px] font-semibold leading-tight tracking-tight max-w-[560px]">{c.punch}</p>
      <form onSubmit={submit} className="mt-auto flex items-center gap-2 h-14 rounded-2xl bg-white text-foreground ps-4 pe-2" data-testid="dashboard-assistant-form">
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder={c.ph} aria-label={c.ph}
          className="flex-1 min-w-0 bg-transparent outline-none text-[15px] text-[#14211d] placeholder:text-[#5f6b66]" data-testid="dashboard-assistant-input" />
        <button type="button" aria-label={c.dictate} title={c.dictate} onClick={() => openAssistant(navigate, text.trim())}
          className="inline-grid place-items-center h-10 w-10 rounded-xl border border-[#e2e5e0] text-[#33403b]"><Mic size={18} aria-hidden="true" /></button>
        <button type="submit" aria-label={c.send} title={c.send} className="inline-grid place-items-center h-10 w-10 rounded-xl text-white"
          style={{ backgroundImage: "linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 50%, #d946ef 100%)" }} data-testid="dashboard-assistant-send">
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {c.chips.map((chip) => (
          <button key={chip} type="button" onClick={() => openAssistant(navigate, chip)}
            className="h-8 px-3 rounded-full border border-white/25 bg-white/10 text-[13px] font-semibold hover:bg-white/20 transition-colors">{chip}</button>
        ))}
      </div>
    </section>
  );
}

const weekStart = (d) => { const x = new Date(d); const day = (x.getDay() + 6) % 7; x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - day); return x.getTime(); };

// Objectif hebdomadaire et série, calculés sur les vrais projets (date de création) ; objectif réglable, mémorisé localement.
export function WeekGoal({ projects, ready, lang, wide }) {
  const c = copy(lang);
  const [goal, setGoal] = useState(() => { try { return Math.max(1, Number(localStorage.getItem("cp_week_goal")) || 3); } catch { return 3; } });
  const weeks = new Set((projects || []).map((p) => p.created_at && weekStart(p.created_at)).filter(Boolean));
  const now = weekStart(Date.now());
  const done = (projects || []).filter((p) => p.created_at && weekStart(p.created_at) === now).length;
  let streak = 0;
  for (let w = weeks.has(now) ? now : now - 7 * 864e5; weeks.has(w); w -= 7 * 864e5) streak += 1;
  const pct = Math.min(1, done / goal);
  const C = 2 * Math.PI * 36;
  const cycle = () => { const next = goal >= 10 ? 1 : goal + 1; setGoal(next); try { localStorage.setItem("cp_week_goal", String(next)); } catch { /* ignore */ } };
  return (
    <section className={`cp-glass cp-lift rounded-3xl p-5 flex items-center gap-4 ${wide ? "lg:col-span-4" : "lg:col-span-2"}`} data-testid="dashboard-week-goal">
      <svg width="88" height="88" viewBox="0 0 88 88" role="img" aria-label={c.goalAria(done, goal)} className="shrink-0">
        <circle cx="44" cy="44" r="36" fill="none" stroke="hsl(var(--muted))" strokeWidth="10" />
        <circle cx="44" cy="44" r="36" fill="none" stroke="#16a34a" strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(ready ? pct : 0) * C} ${C}`} transform="rotate(-90 44 44)" style={{ transition: "stroke-dasharray .6s ease" }} />
        <text x="44" y="50" textAnchor="middle" fontFamily="Outfit, sans-serif" fontSize="20" fontWeight="700" fill="currentColor">{ready ? `${done}/${goal}` : "—"}</text>
      </svg>
      <div className="min-w-0">
        <p className="text-[13px] font-bold text-muted-foreground">{c.goal}</p>
        <p className="font-display text-xl font-semibold leading-tight">{c.goalLabel}</p>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          {streak > 0 && <span className="inline-flex items-center gap-1.5 text-[12.5px] font-bold text-[#9a3412] bg-[#ffedd5] rounded-full px-2.5 py-1" data-testid="dashboard-streak">
            <Flame size={13} className="text-[#ea580c]" aria-hidden="true" />{c.streak(streak)}</span>}
          <button type="button" onClick={cycle} className="text-[12px] font-semibold text-muted-foreground underline-offset-2 hover:underline" data-testid="dashboard-goal-change">{c.change}{lang === "fr" ? " :" : ":"} {goal}</button>
        </div>
      </div>
    </section>
  );
}
