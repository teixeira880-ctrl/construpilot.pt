import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Loader2, Sparkles } from "lucide-react";
import { tr, useConnectLang } from "@/connect/i18n";
import { ConnectShell, Choices, GhostButton, PrimaryButton, Progress, QuestionCard, usePageMeta } from "@/connect/components";
import { ACTIVITIES, PAINS, catalog, deepQuestionsFor, optionsOf, recommend } from "@/connect/engine";
import { ensureSession, loadState, saveAnswers, saveState, track } from "@/connect/api";

const PROFILE = "client";

/** Lista de passos efetivamente apresentados (5–7 no modo rápido; 4 no stand; mais no aprofundado). */
export function buildSteps(answers, mode) {
  const act = ACTIVITIES[answers.activity || ""] || {};
  const group = act.group;
  const volQ = group ? catalog.volume_questions[group] : null;
  const deep = deepQuestionsFor(answers, mode === "deep" ? "deep" : mode === "stand" ? "stand" : "quick");
  const steps = [];
  if (mode === "stand") {
    steps.push({ id: "pains", kind: "pains", max: 1 }, { id: "activity", kind: "activity" });
    if (volQ) steps.push({ id: "volume", kind: "volume", q: volQ });
    steps.push({ id: "urgency", kind: "urgency" });
    return steps;
  }
  steps.push({ id: "activity", kind: "activity" });
  if (volQ) steps.push({ id: "volume", kind: "volume", q: volQ });
  if (mode === "deep" && group !== "private") {
    if (volQ && volQ.id !== "team_size") steps.push({ id: "team_size", kind: "extra", range: "team_size", label: "q_team_size" });
    steps.push({ id: "job_value", kind: "extra", range: "job_value", label: "q_job_value", optional: true });
    steps.push({ id: "market", kind: "extra", range: "market", label: "q_market", optional: true });
  }
  steps.push({ id: "pains", kind: "pains", max: 3 });
  for (const q of deep) steps.push({ id: `deep_${q.id}`, kind: "deep", q, optional: true });
  steps.push({ id: "urgency", kind: "urgency" });
  if (group !== "private") steps.push({ id: "decision", kind: "decision" });
  return steps;
}

export default function ConnectClient() {
  const { lang, setLang, t } = useConnectLang();
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const stand = sp.get("mode") === "stand";
  const initial = useMemo(() => loadState(PROFILE), []);
  const [st, setSt] = useState(() => ({ ...initial, mode: stand ? "stand" : initial.mode || "quick" }));
  const [busy, setBusy] = useState(false);
  const headingRef = useRef(null);
  usePageMeta(t("profile_client"), t("home_promise"));

  const answers = st.answers || {};
  const steps = useMemo(() => buildSteps(answers, st.mode), [answers, st.mode]);
  const idx = Math.min(st.step || 0, steps.length - 1);
  const step = steps[idx];

  useEffect(() => { saveState(PROFILE, st); }, [st]);
  useEffect(() => {
    let alive = true;
    ensureSession(PROFILE, lang, { stand }).then((s) => {
      if (!alive) return;
      setSt((x) => ({ ...x, sid: s.sid, token: s.token }));
      track(s.sid, s.token, "qualification_started");
    }).catch(() => { /* offline: tudo continua localmente */ });
    return () => { alive = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (headingRef.current) headingRef.current.focus(); }, [idx]);

  const setAns = (patch) => setSt((x) => ({ ...x, answers: { ...x.answers, ...patch } }));
  const setDeep = (qid, v) => setSt((x) => ({ ...x, answers: { ...x.answers, deep: { ...(x.answers.deep || {}), [qid]: v } } }));

  const value = (() => {
    switch (step.kind) {
      case "activity": return answers.activity;
      case "volume": return (answers.volume || {})[step.q.id];
      case "extra": return (answers.extra || {})[step.range];
      case "pains": return answers.pains || [];
      case "deep": return (answers.deep || {})[step.q.id];
      case "urgency": return answers.urgency;
      case "decision": return answers.decision;
      default: return null;
    }
  })();
  const filled = Array.isArray(value) ? value.length > 0 : Boolean(value);
  const otherOk = step.kind !== "pains" || !(answers.pains || []).includes("p_other") || (answers.other_text || "").trim().length > 2;
  const canNext = (filled || step.optional) && otherOk;

  const persist = async (nextAnswers, stepNo) => {
    if (!st.sid || !st.token) return null;
    try {
      const r = await saveAnswers(st.sid, st.token, cleanForServer(nextAnswers, st.mode), stepNo, lang);
      track(st.sid, st.token, "qualification_step_completed", { step: stepNo });
      return r;
    } catch { return null; }
  };

  const next = async () => {
    if (!canNext) return;
    if (idx < steps.length - 1) {
      setSt((x) => ({ ...x, step: idx + 1 }));
      persist(answers, idx + 1);
      return;
    }
    setBusy(true);
    const full = { ...answers, mode: st.mode, ...(ACTIVITIES[answers.activity]?.group === "private" ? { decision: "personal" } : {}) };
    const rec = recommend(PROFILE, full);
    const saved = await persist(full, idx + 1);
    const finalRec = (saved && saved.recommendation) || rec;
    setSt((x) => ({ ...x, answers: full, rec: finalRec, done: true }));
    saveState(PROFILE, { ...st, answers: full, rec: finalRec, done: true });
    track(st.sid, st.token, "qualification_completed");
    setBusy(false);
    navigate(`/connect/result/${st.sid || "local"}?p=client${stand ? "&mode=stand" : ""}`);
  };
  const back = () => setSt((x) => ({ ...x, step: Math.max(0, idx - 1) }));

  const title = (() => {
    switch (step.kind) {
      case "activity": return t("q_activity");
      case "volume": return tr(step.q.label, lang);
      case "extra": return t(step.label);
      case "pains": return t("q_pains");
      case "deep": return tr(step.q.label, lang);
      case "urgency": return t("q_urgency");
      case "decision": return t("q_decision");
      default: return "";
    }
  })();

  return (
    <ConnectShell lang={lang} setLang={setLang} t={t} stand={stand}>
      <div className="mx-auto max-w-2xl">
        <Progress step={idx} total={steps.length} t={t} />
        <div tabIndex={-1} ref={headingRef} className="outline-none" />
        <QuestionCard id={`q-${step.id}`} title={title}
          hint={step.kind === "pains" ? t("choose_up_to", { n: step.max }) : step.kind === "deep" && step.q.multi ? t("choose_many") : undefined}>
          <StepBody step={step} answers={answers} lang={lang} t={t} setAns={setAns} setDeep={setDeep} />
        </QuestionCard>

        {st.mode === "quick" && step.kind === "urgency" && (ACTIVITIES[answers.activity]?.group !== "private") && (
          <label className="mt-4 flex items-start gap-3 rounded-xl border border-dashed border-border p-4 text-sm cursor-pointer">
            <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]" data-testid="toggle-deep"
              onChange={(e) => setSt((x) => ({ ...x, mode: e.target.checked ? "deep" : "quick" }))} />
            <span><b>{t("deep_more")}</b><br /><span className="text-muted-foreground">{t("deep_more_d")}</span></span>
          </label>
        )}

        <div className="mt-6 flex items-center justify-between gap-3">
          <GhostButton onClick={back} disabled={idx === 0} testId="wizard-back"><ArrowLeft className="h-4 w-4" aria-hidden />{t("back")}</GhostButton>
          <div className="flex items-center gap-2">
            {step.optional && !filled && <GhostButton onClick={next} testId="wizard-skip">{t("skip")}</GhostButton>}
            <PrimaryButton onClick={next} disabled={!canNext || busy} testId="wizard-next">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : idx === steps.length - 1 ? <Sparkles className="h-4 w-4" aria-hidden /> : null}
              {idx === steps.length - 1 ? t("show_me") : t("next")}
              {idx < steps.length - 1 && <ArrowRight className="h-4 w-4" aria-hidden />}
            </PrimaryButton>
          </div>
        </div>
        {!st.sid && <p className="mt-4 text-xs text-muted-foreground" data-testid="offline-note">{t("offline_note")}</p>}
      </div>
    </ConnectShell>
  );
}

function StepBody({ step, answers, lang, t, setAns, setDeep }) {
  if (step.kind === "activity") {
    return <Choices name="activity" columns={2} value={answers.activity} testId="q-activity"
      onChange={(v) => setAns({ activity: v })}
      options={catalog.activities.map((a) => ({ id: a.id, label: tr(a.label, lang) }))} />;
  }
  if (step.kind === "volume") {
    return <Choices name="volume" value={(answers.volume || {})[step.q.id]} testId="q-volume"
      onChange={(v) => setAns({ volume: { [step.q.id]: v } })}
      options={catalog.ranges[step.q.id].map((r) => ({ id: r.id, label: tr(r.label, lang) }))} />;
  }
  if (step.kind === "extra") {
    return <Choices name={step.range} value={(answers.extra || {})[step.range]} testId={`q-${step.range}`}
      onChange={(v) => setAns({ extra: { ...(answers.extra || {}), [step.range]: v } })}
      options={catalog.ranges[step.range].map((r) => ({ id: r.id, label: tr(r.label, lang) }))} />;
  }
  if (step.kind === "pains") {
    const pains = answers.pains || [];
    return (
      <>
        <Choices name="pains" multi max={step.max} columns={1} value={pains} testId="q-pains"
          onChange={(v) => setAns({ pains: v })}
          options={catalog.pains.map((p) => ({ id: p.id, label: tr(p.label, lang) }))} />
        {pains.includes("p_other") && (
          <label className="mt-4 block">
            <span className="text-sm font-medium">{t("q_other_text")}</span>
            <textarea maxLength={500} value={answers.other_text || ""} onChange={(e) => setAns({ other_text: e.target.value })}
              className="mt-1 w-full min-h-[90px] rounded-lg border border-input bg-background px-3 py-2 focus:outline-none focus:ring-2 focus:ring-ring" data-testid="q-other-text" />
          </label>
        )}
      </>
    );
  }
  if (step.kind === "deep") {
    const q = step.q;
    return <Choices name={q.id} multi={Boolean(q.multi)} value={(answers.deep || {})[q.id] || (q.multi ? [] : undefined)} testId={`q-deep-${q.id}`}
      onChange={(v) => setDeep(q.id, v)} options={optionsOf(q).map((o) => ({ id: o.id, label: tr(o.label, lang) }))} />;
  }
  if (step.kind === "urgency") {
    return <Choices name="urgency" value={answers.urgency} testId="q-urgency" onChange={(v) => setAns({ urgency: v })}
      options={["immediate", "d30", "m3", "exploring"].map((id) => ({ id, label: t(`urgency.${id}`) }))} />;
  }
  if (step.kind === "decision") {
    return <Choices name="decision" value={answers.decision} testId="q-decision" onChange={(v) => setAns({ decision: v })}
      options={["decide", "evaluate", "other", "personal"].map((id) => ({ id, label: t(`decision.${id}`) }))} />;
  }
  return null;
}

/** Remove respostas a perguntas que deixaram de se aplicar (ex.: mudou de dor) antes de enviar. */
export function cleanForServer(answers, mode) {
  const out = { ...answers, mode: mode === "stand" ? "stand" : mode === "deep" ? "deep" : "quick" };
  const pains = (out.pains || []).filter((p) => PAINS[p]);
  out.pains = pains;
  if (!pains.includes("p_other")) out.other_text = "";
  const deep = out.deep || {};
  const asked = new Set(deepQuestionsFor(out, "deep").map((q) => q.id));
  out.deep = Object.fromEntries(Object.entries(deep).filter(([k, v]) => asked.has(k) && (Array.isArray(v) ? v.length : v)));
  const vol = out.volume || {};
  const act = ACTIVITIES[out.activity || ""];
  const vq = act ? catalog.volume_questions[act.group] : null;
  out.volume = vq && vol[vq.id] ? { [vq.id]: vol[vq.id] } : {};
  delete out.rec;
  return out;
}
