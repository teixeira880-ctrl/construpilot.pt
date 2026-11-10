import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { tr, useConnectLang } from "@/connect/i18n";
import { ConnectShell, Choices, PrimaryButton, QuestionCard, usePageMeta } from "@/connect/components";
import { catalog, recommend } from "@/connect/engine";
import { ensureSession, loadState, saveAnswers, saveState, track } from "@/connect/api";

const opts = (list, lang) => list.map((o) => ({ id: o.id, label: tr(o.label, lang) }));

/** Formulário de qualificação partilhado por investidores e parceiros (uma página, sem dados de contacto). */
export function QualifyPage({ profile, title, fields, required, validate }) {
  const { lang, setLang, t } = useConnectLang();
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const stand = sp.get("mode") === "stand";
  const initial = useMemo(() => loadState(profile), [profile]);
  const [st, setSt] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [touched, setTouched] = useState(false);
  usePageMeta(t(title), t("home_promise"));
  const a = st.answers || {};
  const set = (k) => (v) => setSt((x) => ({ ...x, answers: { ...x.answers, [k]: v } }));

  useEffect(() => { saveState(profile, st); }, [st, profile]);
  useEffect(() => {
    ensureSession(profile, lang, { stand }).then((s) => {
      setSt((x) => ({ ...x, sid: s.sid, token: s.token }));
      track(s.sid, s.token, "profile_selected", { ref: profile });
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const ok = required.every((k) => (Array.isArray(a[k]) ? a[k].length : a[k])) && (!validate || validate(a));
  const submit = async () => {
    setTouched(true);
    if (!ok) return;
    setBusy(true);
    let rec = recommend(profile, a);
    if (st.sid && st.token) {
      try { const r = await saveAnswers(st.sid, st.token, a, 1, lang); rec = r.recommendation || rec; } catch { /* offline */ }
    }
    const next = { ...st, rec, done: true };
    setSt(next);
    saveState(profile, next);
    setBusy(false);
    navigate(`/connect/result/${st.sid || "local"}?p=${profile}${stand ? "&mode=stand" : ""}`);
  };

  return (
    <ConnectShell lang={lang} setLang={setLang} t={t} stand={stand}>
      <div className="mx-auto max-w-3xl">
        <h1 className="font-display text-3xl sm:text-4xl font-bold tracking-tight" data-testid={`${profile}-title`}>{t(title)}</h1>
        <div className="mt-8 space-y-5">
          {fields.map((f) => (
            <QuestionCard key={f.key} id={`q-${f.key}`} title={`${t(f.label)}${required.includes(f.key) ? " *" : ""}`}
              hint={f.multi ? t("choose_many") : undefined}>
              {f.kind === "text" ? (
                <input value={a[f.key] || ""} onChange={(e) => set(f.key)(e.target.value)} maxLength={f.max || 120}
                  className="w-full rounded-lg border border-input bg-background px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-ring" data-testid={`q-${f.key}`} />
              ) : f.kind === "textarea" ? (
                <textarea value={a[f.key] || ""} onChange={(e) => set(f.key)(e.target.value)} maxLength={f.max || 300}
                  className="w-full min-h-[80px] rounded-lg border border-input bg-background px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-ring" data-testid={`q-${f.key}`} />
              ) : (
                <Choices name={f.key} multi={f.multi} columns={f.columns || 2} value={a[f.key] || (f.multi ? [] : undefined)}
                  onChange={set(f.key)} options={opts(f.options, lang)} testId={`q-${f.key}`} />
              )}
            </QuestionCard>
          ))}
        </div>
        {touched && !ok && <p className="mt-4 text-sm text-destructive" role="alert">{t("err_required")}</p>}
        <div className="mt-6 flex justify-end">
          <PrimaryButton onClick={submit} disabled={busy} testId={`${profile}-submit`}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : null}{t("show_me")}<ArrowRight className="h-4 w-4" aria-hidden />
          </PrimaryButton>
        </div>
      </div>
    </ConnectShell>
  );
}

export default function ConnectInvestor() {
  const inv = catalog.investor;
  return (
    <QualifyPage profile="investor" title="inv_title" required={["investor_type"]}
      validate={(a) => !a.website || /^(https?:\/\/)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(\/\S*)?$/.test(a.website)}
      fields={[
        { key: "investor_type", label: "inv_q_type", options: inv.types },
        { key: "organization", label: "f_org", kind: "text", max: 120 },
        { key: "website", label: "f_website", kind: "text", max: 200 },
        { key: "sectors", label: "inv_q_sectors", options: inv.sectors, multi: true, columns: 3 },
        { key: "stages", label: "inv_q_stages", options: inv.stages, multi: true },
        { key: "geos", label: "inv_q_geos", options: inv.geos, multi: true },
        { key: "ticket", label: "inv_q_ticket", options: inv.tickets },
        { key: "collab", label: "inv_q_collab", options: inv.collab },
        { key: "availability", label: "inv_q_avail", options: inv.availability, columns: 3 },
      ]} />
  );
}
