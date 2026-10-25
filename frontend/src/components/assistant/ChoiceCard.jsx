import { useMemo, useState } from "react";
import { Check, ListChecks, Send, Sparkles } from "lucide-react";
import { useAssistantSend } from "./assistantSend";

const OTHER = "__other__";

// Chave estável para fixar o cartão depois do envio (sobrevive ao recarregamento da conversa).
function cardKey(r) {
  const sig = (r.questions || []).map((q) => `${q.id}:${(q.options || []).map((o) => o.id).join("|")}`).join(";");
  let h = 0;
  const base = `${r.intro || ""}#${r.submit_label || ""}#${sig}`;
  for (let i = 0; i < base.length; i++) { h = (h * 31 + base.charCodeAt(i)) | 0; }
  return `cp-choices:${h}`;
}

function defaultsFor(questions) {
  const sel = {};
  for (const q of questions || []) {
    if (q.multi) sel[q.id] = q.default_option_id ? [q.default_option_id] : [];
    else sel[q.id] = q.default_option_id || (q.options?.[0]?.id ?? null);
  }
  return sel;
}

function buildMessage(questions, sel, other) {
  const lines = [];
  const refs = [];
  for (const q of questions) {
    const chosen = q.multi ? (sel[q.id] || []) : (sel[q.id] ? [sel[q.id]] : []);
    const labels = chosen.map((id) => (id === OTHER ? (other[q.id] || "Outro") : (q.options.find((o) => o.id === id)?.label || id)));
    const refIds = chosen.map((id) => (id === OTHER ? `outro:${(other[q.id] || "").trim()}` : id));
    if (labels.length) {
      lines.push(`- ${q.label}: ${labels.join(", ")}`);
      refs.push(`${q.id}=${refIds.join("|")}`);
    }
  }
  return `As minhas escolhas:\n${lines.join("\n")}\n(referências: ${refs.join(" · ")})`;
}

export function ChoiceCard({ r }) {
  const send = useAssistantSend();
  const questions = r.questions || [];
  const key = useMemo(() => cardKey(r), [r]);
  const frozen = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; }
  }, [key]);

  const [sel, setSel] = useState(() => defaultsFor(questions));
  const [other, setOther] = useState({});
  const [sent, setSent] = useState(!!frozen);
  const [busy, setBusy] = useState(false);

  const pick = (q, optId) => {
    setSel((s) => {
      if (q.multi) {
        const cur = new Set(s[q.id] || []);
        cur.has(optId) ? cur.delete(optId) : cur.add(optId);
        return { ...s, [q.id]: [...cur] };
      }
      return { ...s, [q.id]: optId };
    });
  };

  const isActive = (q, optId) => (q.multi ? (sel[q.id] || []).includes(optId) : sel[q.id] === optId);

  const submit = async (useDefaults) => {
    if (!send || busy) return;
    const finalSel = useDefaults ? defaultsFor(questions) : sel;
    const msg = buildMessage(questions, finalSel, other);
    setBusy(true);
    try {
      await send(msg);
      const snapshot = buildMessage(questions, finalSel, other);
      try { localStorage.setItem(key, JSON.stringify({ msg: snapshot })); } catch { /* ignore */ }
      setSent(true);
    } finally { setBusy(false); }
  };

  if (sent) {
    const text = frozen?.msg || buildMessage(questions, sel, other);
    return (
      <div className="mt-2 rounded-md border bg-background p-3 text-xs" data-testid="choice-card-frozen">
        <div className="flex items-center gap-1.5 font-semibold text-[#1F6F43]"><Check className="h-3.5 w-3.5" /> Escolhas enviadas</div>
        <pre className="mt-1 whitespace-pre-wrap font-sans text-muted-foreground">{text}</pre>
      </div>
    );
  }

  return (
    <div className="mt-2 rounded-md border bg-background p-3" data-testid="choice-card">
      {r.intro && <p className="mb-2 text-xs text-muted-foreground">{r.intro}</p>}
      <div className="space-y-3">
        {questions.map((q) => (
          <fieldset key={q.id} className="space-y-1.5" data-testid={`choice-q-${q.id}`}>
            <legend className="text-xs font-medium">{q.label}{q.multi && <span className="ml-1 text-[10px] text-muted-foreground">(várias escolhas possíveis)</span>}</legend>
            <div className="flex flex-wrap gap-1.5">
              {q.options.map((o) => (
                <button
                  key={o.id}
                  type="button"
                  role={q.multi ? "checkbox" : "radio"}
                  aria-checked={isActive(q, o.id)}
                  onClick={() => pick(q, o.id)}
                  title={o.hint || ""}
                  data-testid={`choice-opt-${q.id}-${o.id}`}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors focus:outline-none focus:ring-2 focus:ring-[#1F6F43]/40 ${isActive(q, o.id) ? "border-[#1F6F43] bg-[#1F6F43]/10 text-[#1F6F43] font-medium" : "border-muted-foreground/25 hover:bg-muted"}`}
                >
                  <span className={`grid h-3.5 w-3.5 shrink-0 place-items-center ${q.multi ? "rounded-[3px]" : "rounded-full"} border ${isActive(q, o.id) ? "border-[#1F6F43] bg-[#1F6F43] text-white" : "border-muted-foreground/40"}`}>{isActive(q, o.id) && <Check className="h-2.5 w-2.5" />}</span>
                  {o.label}
                </button>
              ))}
              {q.allow_other && (
                <button type="button" role={q.multi ? "checkbox" : "radio"} aria-checked={isActive(q, OTHER)} onClick={() => pick(q, OTHER)} data-testid={`choice-opt-${q.id}-other`}
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors ${isActive(q, OTHER) ? "border-[#1F6F43] bg-[#1F6F43]/10 text-[#1F6F43] font-medium" : "border-muted-foreground/25 hover:bg-muted"}`}>
                  Outro…
                </button>
              )}
            </div>
            {q.allow_other && isActive(q, OTHER) && (
              <input
                type="text"
                value={other[q.id] || ""}
                onChange={(e) => setOther((s) => ({ ...s, [q.id]: e.target.value }))}
                placeholder="Especifique…"
                data-testid={`choice-other-input-${q.id}`}
                className="mt-1 w-full rounded-md border px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-[#1F6F43]/40"
              />
            )}
          </fieldset>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={() => submit(false)} disabled={busy} data-testid="choice-submit-btn"
          className="inline-flex items-center gap-1.5 rounded-md bg-[#1F6F43] px-3 py-1.5 text-xs font-medium text-white hover:bg-[#1A5C38] disabled:opacity-60">
          <Send className="h-3.5 w-3.5" /> {r.submit_label || "Validar"}
        </button>
        <button type="button" onClick={() => submit(true)} disabled={busy} data-testid="choice-defaults-btn"
          className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs hover:bg-muted">
          <Sparkles className="h-3.5 w-3.5" /> Hipóteses correntes
        </button>
      </div>
    </div>
  );
}
