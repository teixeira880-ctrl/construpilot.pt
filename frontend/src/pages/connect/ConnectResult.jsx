import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowRight, FileText, Lock, Pencil, PlayCircle, RotateCcw, UserPlus, Users } from "lucide-react";
import { tr, useConnectLang } from "@/connect/i18n";
import { CapabilityCard, ConnectShell, ContactForm, ProcessCompare, StatusBadge, ValueCalculator, usePageMeta } from "@/connect/components";
import DemoPlayer from "@/connect/DemoPlayer";
import { buildSteps } from "./ConnectClient";
import { CAPS, PAINS, catalog, recommend } from "@/connect/engine";
import { INVESTOR, TRACTION_AS_OF } from "@/connect/investorContent";
import { clearAll, demoProgress, getSession, loadState, queueOfflineLead, saveState, submitContact, tokenFor, track } from "@/connect/api";

function useResult(id, profileHint) {
  const [state, setState] = useState({ loading: true, profile: null, answers: null, rec: null, sid: null, token: null, denied: false });
  useEffect(() => {
    let alive = true;
    (async () => {
      const local = profileHint ? loadState(profileHint) : null;
      if (id === "local") {
        if (local && local.answers && Object.keys(local.answers).length) {
          setState({ loading: false, profile: profileHint, answers: local.answers, rec: local.rec || recommend(profileHint, local.answers), sid: null, token: null });
        } else setState((s) => ({ ...s, loading: false, denied: true }));
        return;
      }
      const tk = tokenFor(id);
      if (!tk) { if (alive) setState((s) => ({ ...s, loading: false, denied: true })); return; }
      try {
        const s = await getSession(id, tk.token);
        if (!alive) return;
        const profile = s.profile;
        const rec = s.recommendation || recommend(profile, s.answers || {});
        setState({ loading: false, profile, answers: s.answers, rec, sid: id, token: tk.token, hasContact: s.has_contact });
      } catch (e) {
        if (!alive) return;
        const p = tk.profile || profileHint;
        const st = p ? loadState(p) : null;
        if (!e.response && st && st.sid === id && st.answers) {
          setState({ loading: false, profile: p, answers: st.answers, rec: st.rec || recommend(p, st.answers), sid: id, token: tk.token });
        } else setState((s) => ({ ...s, loading: false, denied: true }));
      }
    })();
    return () => { alive = false; };
  }, [id, profileHint]);
  return state;
}

export default function ConnectResult() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const stand = sp.get("mode") === "stand";
  const { lang, setLang, t } = useConnectLang();
  const r = useResult(id, sp.get("p"));
  usePageMeta(t("result_title"), t("home_promise"));

  useEffect(() => { if (r.sid) track(r.sid, r.token, "recommendation_viewed"); }, [r.sid]); // eslint-disable-line react-hooks/exhaustive-deps

  if (r.loading) return <ConnectShell lang={lang} setLang={setLang} t={t}><p className="text-muted-foreground">{t("loading")}</p></ConnectShell>;
  if (r.denied) {
    return (
      <ConnectShell lang={lang} setLang={setLang} t={t}>
        <div className="mx-auto max-w-lg rounded-2xl border border-border bg-card p-8 text-center" data-testid="result-denied">
          <Lock className="mx-auto h-8 w-8 text-muted-foreground" aria-hidden />
          <p className="mt-3">{t("result_private")}</p>
          <Link to="/connect" className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground">{t("restart")}<ArrowRight className="h-4 w-4" aria-hidden /></Link>
        </div>
      </ConnectShell>
    );
  }
  const props = { r, lang, t, stand };
  return (
    <ConnectShell lang={lang} setLang={setLang} t={t} wide stand={stand}>
      {r.profile === "client" && <ClientResult {...props} onEdit={() => {
        const st = loadState("client");
        const at = buildSteps(st.answers || {}, st.mode || "quick").findIndex((x) => x.id === "pains");
        saveState("client", { ...st, step: Math.max(0, at) });
        navigate(`/connect/client${stand ? "?mode=stand" : ""}`);
      }} />}
      {r.profile === "investor" && <InvestorResult {...props} />}
      {r.profile === "partner" && <PartnerResult {...props} />}
      {stand && (
        <div className="mt-10 text-center">
          <button type="button" onClick={() => { clearAll(); navigate("/connect/stand"); }}
            className="inline-flex items-center gap-2 rounded-xl border border-border px-5 py-3 text-sm" data-testid="stand-reset"><RotateCcw className="h-4 w-4" aria-hidden />{t("stand_reset")}</button>
        </div>
      )}
    </ConnectShell>
  );
}

function Block({ n, title, children, id }) {
  return (
    <section aria-labelledby={id} className="mt-10 first:mt-0">
      <h2 id={id} className="flex items-baseline gap-3 font-display text-2xl font-semibold tracking-tight">
        <span className="font-mono text-sm text-[#8a5524] dark:text-[#e0a46a]">{String(n).padStart(2, "0")}</span>{title}
      </h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function useDemoTracking(r) {
  return useCallback((demoId) => (event, step) => {
    demoProgress(r.sid, r.token, demoId, event, step);
    if (event === "started") track(r.sid, r.token, "demo_started", { ref: demoId });
    if (event === "completed") track(r.sid, r.token, "demo_completed", { ref: demoId });
  }, [r.sid, r.token]);
}

function useContactSubmit(r, lang) {
  const [status, setStatus] = useState({ busy: false, sent: Boolean(r.hasContact), queued: false, error: null });
  const submit = async (form, t) => {
    setStatus((s) => ({ ...s, busy: true, error: null }));
    const payload = { ...form, email: form.email.trim() };
    try {
      if (!r.sid) {
        queueOfflineLead({ profile: r.profile, lang, answers: r.answers, payload });
        setStatus({ busy: false, sent: true, queued: true, error: null });
        return;
      }
      const res = await submitContact(r.sid, r.token, payload);
      if (form.next_step === "meeting" || form.next_step === "individual_demo") track(r.sid, r.token, "meeting_requested");
      if (form.next_step === "pilot") track(r.sid, r.token, "pilot_requested");
      setStatus({ busy: false, sent: true, queued: res.queued, error: null });
    } catch (e) {
      setStatus({ busy: false, sent: false, queued: false, error: t("err_generic") });
    }
  };
  return [status, submit];
}

function ClientResult({ r, lang, t, onEdit }) {
  const rec = r.rec;
  const [demo, setDemo] = useState(rec.demo);
  const [nextStep, setNextStep] = useState(null);
  const [status, submit] = useContactSubmit(r, lang);
  const onProgress = useDemoTracking(r);
  const challenge = rec.pains.filter((p) => PAINS[p]).map((p) => tr(PAINS[p].summary, lang));
  const challengeText = challenge.length > 1 ? `${challenge.slice(0, -1).join(", ")} ${lang === "en" ? "and" : lang === "fr" ? "et" : "e"} ${challenge.slice(-1)}` : challenge[0] || "—";
  const current = rec.process.current ? catalog.process.current[rec.process.current][lang] : catalog.process.current.none[lang];
  const withSteps = catalog.process[rec.process.with][lang];
  const painNames = (ids) => ids.map((p) => tr(PAINS[p] && PAINS[p].label, lang)).join(" · ");
  const showCalc = rec.group !== "private";

  return (
    <div data-testid="client-result">
      <p className="text-xs font-mono uppercase tracking-[0.18em] text-muted-foreground">{t("brand_tag")}</p>
      <h1 className="mt-2 font-display text-3xl sm:text-5xl font-bold tracking-tight">{t("result_title")}</h1>

      <Block n={1} id="b-challenge" title={t("your_challenge")}>
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <p className="text-lg sm:text-xl leading-relaxed" data-testid="challenge-line">{t("challenge_line", { x: challengeText })}</p>
          <ul className="mt-3 flex flex-wrap gap-2">{rec.pains.map((p) => <li key={p} className="rounded-full bg-accent px-3 py-1 text-sm">{tr(PAINS[p].label, lang)}</li>)}</ul>
          {rec.needs_human_review && <p className="mt-3 text-sm text-[#8a5524] dark:text-[#e0a46a]">{t("human_review")}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
            <button type="button" onClick={onEdit} className="inline-flex items-center gap-1.5 text-primary underline-offset-2 hover:underline" data-testid="edit-answers"><Pencil className="h-3.5 w-3.5" aria-hidden />{t("edit_answers")}</button>
            <span className="text-muted-foreground">{t("not_definitive")}</span>
          </div>
        </div>
      </Block>

      <Block n={2} id="b-process" title={t("process_title")}>
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <ProcessCompare current={current} withSteps={withSteps} generic={!rec.process.current} t={t} />
        </div>
      </Block>

      <Block n={3} id="b-help" title={t("how_help")}>
        <div className="grid gap-3">{rec.capabilities.map((c, k) => <CapabilityCard key={c.id} capId={c.id} index={k} lang={lang} t={t} pains={painNames(c.pains)} />)}</div>
      </Block>

      <Block n={4} id="b-demo" title={t("watch")}>
        <DemoPlayer demoId={demo} lang={lang} t={t} onProgress={onProgress(demo)} onSwitch={setDemo}
          alternatives={[rec.demo, ...rec.alternative_demos].filter((d) => d !== demo)} />
      </Block>

      {showCalc && (
        <Block n={5} id="b-calc" title={t("opportunity")}>
          <div className="rounded-2xl border border-border bg-card p-5 sm:p-6"><ValueCalculator defaults={rec.value_defaults} lang={lang} t={t} /></div>
        </Block>
      )}

      <Block n={showCalc ? 6 : 5} id="b-next" title={t("next_step_title")}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Link to="/inscription" className="rounded-xl border border-border bg-card p-4 hover:border-primary/60" data-testid="ns-try">
            <UserPlus className="h-5 w-5 text-primary" aria-hidden /><p className="mt-2 font-semibold">{t("ns_try")}</p><p className="text-sm text-muted-foreground">{t("ns_try_d")}</p>
          </Link>
          {[["individual_demo", PlayCircle, "ns_demo", "ns_demo_d"], ["pilot", Users, "ns_pilot", "ns_pilot_d"], ["report", FileText, "ns_report", "ns_report_d"]].map(([id, Icon, ti, d]) => (
            <button key={id} type="button" onClick={() => { setNextStep(id); setTimeout(() => document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" }), 30); }}
              className={`rounded-xl border bg-card p-4 text-left hover:border-primary/60 ${nextStep === id ? "border-primary ring-1 ring-primary" : "border-border"}`} data-testid={`ns-${id}`}>
              <Icon className="h-5 w-5 text-primary" aria-hidden /><p className="mt-2 font-semibold">{t(ti)}</p><p className="text-sm text-muted-foreground">{t(d)}</p>
            </button>
          ))}
        </div>
        {(nextStep || status.sent) && (
          <div id="contact" className="mt-6 rounded-2xl border border-border bg-card p-5 sm:p-6">
            <h3 className="mb-4 font-display text-xl font-semibold">{t("contact_title")}</h3>
            <ContactForm t={t} steps={["individual_demo", "pilot", "report"]} defaultStep={nextStep} busy={status.busy} sent={status.sent}
              queued={status.queued} error={status.error} onSubmit={(f) => submit(f, t)} />
          </div>
        )}
      </Block>
    </div>
  );
}

function List({ items }) {
  return <ul className="mt-2 space-y-1.5">{items.map((x) => <li key={x} className="flex gap-2"><span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#B87333]" />{x}</li>)}</ul>;
}

function InvestorResult({ r, lang, t }) {
  const [status, submit] = useContactSubmit(r, lang);
  const [demoOpen, setDemoOpen] = useState(false);
  const onProgress = useDemoTracking(r);
  const C = INVESTOR;
  return (
    <div data-testid="investor-result">
      <h1 className="font-display text-3xl sm:text-5xl font-bold tracking-tight">{t("inv_title")}</h1>
      <Block n={1} id="i-overview" title={tr(C.overview.title, lang)}><p className="text-lg leading-relaxed">{tr(C.overview.body, lang)}</p>
        <a href={`${process.env.REACT_APP_BACKEND_URL || ""}/api/investors/pitch-deck.pdf`} target="_blank" rel="noreferrer" className="mt-3 inline-flex items-center gap-1.5 text-sm text-primary underline-offset-2 hover:underline"><FileText className="h-4 w-4" aria-hidden />{tr(C.deck, lang)}</a></Block>
      <Block n={2} id="i-problem" title={tr(C.problem.title, lang)}><p className="leading-relaxed">{tr(C.problem.body, lang)}</p></Block>
      <Block n={3} id="i-solution" title={tr(C.solution.title, lang)}>
        <p className="leading-relaxed">{tr(C.solution.body, lang)}</p>
        <button type="button" onClick={() => setDemoOpen(true)} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 font-semibold text-primary-foreground" data-testid="see-in-action"><PlayCircle className="h-5 w-5" aria-hidden />{t("see_in_action")}</button>
        {demoOpen && <div className="mt-5"><InvestorStory lang={lang} t={t} onProgress={onProgress} /></div>}
      </Block>
      <Block n={4} id="i-seg" title={tr(C.segments.title, lang)}><List items={C.segments.items[lang]} /></Block>
      <Block n={5} id="i-model" title={tr(C.model.title, lang)}><p className="leading-relaxed">{tr(C.model.body, lang)}</p>
        <Link to="/planos" className="mt-2 inline-block text-sm text-primary underline-offset-2 hover:underline">/planos</Link></Block>
      <Block n={6} id="i-traction" title={tr(C.traction.title, lang)}><List items={C.traction.items[lang]} />
        <p className="mt-3 text-xs text-muted-foreground" data-testid="traction-source">{tr(C.traction.source, lang)} · {TRACTION_AS_OF}</p></Block>
      <Block n={7} id="i-risks" title={tr(C.risks.title, lang)}><List items={C.risks.items[lang]} /></Block>
      <Block n={8} id="i-meeting" title={tr(C.meeting.title, lang)}>
        <p className="mb-4 leading-relaxed">{tr(C.meeting.body, lang)}</p>
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <ContactForm t={t} steps={["meeting", "report"]} defaultStep="meeting" orgLabel={t("f_org")} busy={status.busy} sent={status.sent}
            queued={status.queued} error={status.error} onSubmit={(f) => submit(f, t)} />
        </div>
      </Block>
    </div>
  );
}

/** História da obra de exemplo: planta → medições → orçamento → margens (só capacidades verificadas). */
function InvestorStory({ lang, t, onProgress }) {
  const chapters = ["demo_takeoff", "demo_quote", "demo_margin"];
  const [k, setK] = useState(0);
  return (
    <div>
      <ol className="mb-3 flex flex-wrap gap-2">{chapters.map((d, i) => (
        <li key={d}><button type="button" onClick={() => setK(i)} aria-current={i === k ? "step" : undefined}
          className={`rounded-full px-3 py-1.5 text-sm ${i === k ? "bg-primary text-primary-foreground" : "border border-border"}`}>{i + 1}. {tr(catalog.demos.find((x) => x.id === d).title, lang)}</button></li>
      ))}</ol>
      <DemoPlayer demoId={chapters[k]} lang={lang} t={t} onProgress={onProgress(chapters[k])}
        alternatives={chapters.slice(k + 1, k + 2)} onSwitch={(d) => setK(chapters.indexOf(d))} />
    </div>
  );
}

function PartnerResult({ r, lang, t }) {
  const [status, submit] = useContactSubmit(r, lang);
  const onProgress = useDemoTracking(r);
  const rec = r.rec;
  const cap = CAPS[rec.use_case];
  return (
    <div data-testid="partner-result">
      <h1 className="font-display text-3xl sm:text-5xl font-bold tracking-tight">{t("par_title")}</h1>
      <Block n={1} id="p-case" title={t("par_use_case")}>
        <CapabilityCard capId={rec.use_case} index={0} lang={lang} t={t} />
      </Block>
      <Block n={2} id="p-demo" title={t("watch")}>
        <DemoPlayer demoId={rec.demo} lang={lang} t={t} onProgress={onProgress(rec.demo)} />
      </Block>
      <Block n={3} id="p-int" title={t("par_integrations")}>
        <p className="rounded-xl border border-dashed border-border p-4 text-sm leading-relaxed">{t("par_integrations_d")}</p>
        {cap && <p className="mt-2 text-xs text-muted-foreground">{tr(cap.name, lang)} · <StatusBadge status={cap.status} t={t} /></p>}
      </Block>
      <Block n={4} id="p-meet" title={t("ns_meeting")}>
        <div className="rounded-2xl border border-border bg-card p-5 sm:p-6">
          <ContactForm t={t} steps={["meeting", "report"]} defaultStep="meeting" orgLabel={t("f_org")} busy={status.busy} sent={status.sent}
            queued={status.queued} error={status.error} onSubmit={(f) => submit(f, t)} />
        </div>
      </Block>
    </div>
  );
}
