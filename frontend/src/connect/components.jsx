import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Check, CheckCircle2, CircleDashed, Globe, Info, Loader2, ShieldCheck, WifiOff } from "lucide-react";
import { CONNECT_LANGS, formatEurLang, formatNum, tr } from "./i18n";
import { CAPS } from "./engine";

export const COPPER = "#B87333";

/** Título e descrição da página (o projeto não usa HelmetProvider). */
export function usePageMeta(title, description) {
  useEffect(() => {
    const prev = document.title;
    document.title = `${title} · ConstruPilot`;
    let tag = document.querySelector('meta[name="description"]');
    const prevDesc = tag ? tag.getAttribute("content") : null;
    if (description && tag) tag.setAttribute("content", description);
    return () => { document.title = prev; if (tag && prevDesc != null) tag.setAttribute("content", prevDesc); };
  }, [title, description]);
}

/** Moldura das páginas /connect: cabeçalho, seletor de idioma, rodapé de privacidade. */
export function ConnectShell({ lang, setLang, t, children, stand = false, wide = false }) {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  return (
    <div className="min-h-screen bg-background text-foreground cp-connect" data-testid="connect-shell" data-no-translate="">
      <div aria-hidden className="pointer-events-none fixed inset-0 opacity-[0.35] [background-image:linear-gradient(hsl(var(--border))_1px,transparent_1px),linear-gradient(90deg,hsl(var(--border))_1px,transparent_1px)] [background-size:32px_32px] [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <header className="relative border-b border-border/80 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className={`mx-auto ${wide ? "max-w-6xl" : "max-w-5xl"} px-4 sm:px-6 h-14 flex items-center justify-between gap-3`}>
          <Link to={stand ? "/connect/stand" : "/connect"} className="flex items-center gap-2 font-display font-bold tracking-tight" data-testid="connect-home-link">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-primary text-primary-foreground text-[13px]">CP</span>
            ConstruPilot
            <span className="hidden sm:inline text-[11px] font-mono uppercase tracking-[0.18em] text-muted-foreground border-l border-border pl-2 ml-1">{t("brand_tag")}</span>
          </Link>
          <div className="flex items-center gap-2">
            {!online && (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200 px-2 py-0.5 text-[11px]" role="status">
                <WifiOff className="h-3 w-3" aria-hidden /> offline
              </span>
            )}
            <LangSwitch lang={lang} setLang={setLang} t={t} />
          </div>
        </div>
      </header>
      <main className={`relative mx-auto ${wide ? "max-w-6xl" : "max-w-5xl"} px-4 sm:px-6 py-8 sm:py-12`}>{children}</main>
      <footer className="relative border-t border-border/80 py-6 text-center text-xs text-muted-foreground px-4">
        <p className="inline-flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" aria-hidden /> {t("footer_privacy")}{" "}
          <Link to="/privacidade" className="underline underline-offset-2">{t("f_privacy_link")}</Link></p>
      </footer>
    </div>
  );
}

export function LangSwitch({ lang, setLang, t }) {
  return (
    <div role="group" aria-label={t("lang_label")} className="inline-flex items-center rounded-full border border-border bg-card p-0.5">
      <Globe className="h-3.5 w-3.5 mx-1.5 text-muted-foreground" aria-hidden />
      {CONNECT_LANGS.map((l) => (
        <button key={l} type="button" onClick={() => setLang(l)} aria-pressed={lang === l}
          data-testid={`connect-lang-${l}`}
          className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${lang === l ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
          {l}
        </button>
      ))}
    </div>
  );
}

export function Progress({ step, total, t }) {
  const pct = Math.round(((step + 1) / total) * 100);
  return (
    <div className="mb-6" data-testid="connect-progress">
      <div className="flex items-center justify-between text-xs text-muted-foreground mb-2 font-mono">
        <span>{t("step_of", { a: step + 1, b: total })}</span><span>{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden" role="progressbar" aria-label={t("step_of", { a: step + 1, b: total })} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <div className="h-full bg-primary transition-[width] duration-500 motion-reduce:transition-none" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

/**
 * Grelha de escolhas acessível (radio ou checkbox) — navegável por teclado.
 * options: [{id, label, description?}]
 */
export function Choices({ name, options, value, onChange, multi = false, max = 99, columns = 2, testId }) {
  const selected = multi ? (Array.isArray(value) ? value : []) : value;
  const toggle = (id) => {
    if (!multi) return onChange(id);
    const set = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    if (set.length <= max) onChange(set);
  };
  const cols = columns === 1 ? "" : columns === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2";
  return (
    <div role={multi ? "group" : "radiogroup"} className={`grid gap-2.5 ${cols}`} data-testid={testId}>
      {options.map((o) => {
        const on = multi ? selected.includes(o.id) : selected === o.id;
        const disabled = multi && !on && selected.length >= max;
        return (
          <label key={o.id}
            className={`group relative flex cursor-pointer items-start gap-3 rounded-xl border bg-card px-4 py-3.5 text-left transition-all focus-within:ring-2 focus-within:ring-ring ${on ? "border-primary bg-accent/60 shadow-sm" : "border-border hover:border-primary/50"} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
            data-testid={`${testId || name}-${o.id}`}>
            <input type={multi ? "checkbox" : "radio"} name={name} className="sr-only" checked={on} disabled={disabled}
              onChange={() => toggle(o.id)} />
            <span aria-hidden className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-${multi ? "md" : "full"} border ${on ? "border-primary bg-primary text-primary-foreground" : "border-muted-foreground/40"}`}>
              {on && <Check className="h-3.5 w-3.5" />}
            </span>
            <span className="min-w-0">
              <span className="block text-[15px] font-medium leading-snug">{o.label}</span>
              {o.description && <span className="mt-0.5 block text-sm text-muted-foreground">{o.description}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

export function QuestionCard({ title, hint, children, id }) {
  return (
    <section aria-labelledby={id} className="rounded-2xl border border-border bg-card/90 p-5 sm:p-7 shadow-sm">
      <h2 id={id} className="font-display text-xl sm:text-2xl font-semibold tracking-tight">{title}</h2>
      {hint && <p className="mt-1 text-sm text-muted-foreground">{hint}</p>}
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function StatusBadge({ status, t }) {
  const verified = status === "VERIFICADA";
  return (
    <span title={t(`status_help.${status}`)}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${verified ? "bg-accent text-accent-foreground" : "bg-[#B87333]/12 text-[#7a4a1f] dark:text-[#e0a46a]"}`}>
      {verified ? <CheckCircle2 className="h-3 w-3" aria-hidden /> : <CircleDashed className="h-3 w-3" aria-hidden />}
      {t(`status.${status}`)}
    </span>
  );
}

export function CapabilityCard({ capId, lang, t, index, pains }) {
  const c = CAPS[capId];
  if (!c) return null;
  return (
    <article className="rounded-xl border border-border bg-card p-4 sm:p-5" data-testid={`cap-${capId}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
        <h3 className="font-display text-lg font-semibold">{tr(c.name, lang)}</h3>
        <StatusBadge status={c.status} t={t} />
      </div>
      <p className="mt-2 text-sm leading-relaxed">{tr(c.description, lang)}</p>
      {pains && pains.length > 0 && (
        <p className="mt-2 text-xs text-muted-foreground">↳ {pains}</p>
      )}
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
        <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("needs")}</dt><dd className="mt-0.5">{tr(c.inputs, lang)}</dd></div>
        <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("limits")}</dt><dd className="mt-0.5">{tr(c.limitations, lang)}</dd></div>
        <div><dt className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("human_checks")}</dt><dd className="mt-0.5">{tr(c.human_checks, lang)}</dd></div>
      </dl>
      <p className="mt-3 text-[11px] text-muted-foreground">{t("validated_on", { d: c.validated_at })}</p>
    </article>
  );
}

export function ProcessCompare({ current, withSteps, generic, t }) {
  const Row = ({ label, steps, accent }) => (
    <div>
      <p className={`mb-2 text-xs font-semibold uppercase tracking-[0.14em] ${accent ? "text-primary" : "text-muted-foreground"}`}>{label}</p>
      <ol className="flex flex-wrap items-center gap-1.5">
        {steps.map((s, i) => (
          <li key={i} className="flex items-center gap-1.5">
            <span className={`rounded-lg border px-2.5 py-1.5 text-sm ${accent ? "border-primary/40 bg-accent/60" : "border-border bg-muted/50"}`}>{s}</span>
            {i < steps.length - 1 && <ArrowRight className={`h-3.5 w-3.5 ${accent ? "text-primary" : "text-muted-foreground"}`} aria-hidden />}
          </li>
        ))}
      </ol>
    </div>
  );
  return (
    <div className="space-y-4" data-testid="process-compare">
      <Row label={generic ? t("process_generic") : t("process_now")} steps={current} />
      <Row label={t("process_with")} steps={withSteps} accent />
    </div>
  );
}

function CalcField({ id, label, value, set, step = "1" }) {
  return (
    <label htmlFor={id} className="block">
      <span className="text-sm font-medium">{label}</span>
      <input id={id} inputMode="decimal" type="number" min="0" step={step} value={value}
        onChange={(e) => set(e.target.value)} data-testid={id}
        className="mt-1 w-full rounded-lg border border-input bg-background px-3 py-2 font-mono text-base focus:outline-none focus:ring-2 focus:ring-ring" />
    </label>
  );
}

/** Calculadora transparente: separa dados do cliente, hipóteses e resultados matemáticos. */
export function ValueCalculator({ defaults, lang, t, onChange }) {
  const [q, setQ] = useState(defaults?.quotes_per_month ?? "");
  const [h, setH] = useState(defaults?.hours_per_quote ?? "");
  const [r, setR] = useState(defaults?.hourly_cost ?? "");
  const [custom, setCustom] = useState("");
  const num = (v) => {
    if (v === null || v === undefined || String(v).trim() === "") return null; // vazio ≠ zero
    const n = Number(String(v).replace(",", "."));
    return Number.isFinite(n) && n >= 0 ? n : null;
  };
  const qn = num(q), hn = num(h), rn = num(r);
  const hours = qn != null && hn != null ? qn * hn : null;
  const cost = hours != null && rn != null ? hours * rn : null;
  const scen = useMemo(() => {
    const base = [10, 20, 30];
    const c = num(custom);
    if (c != null && c > 0 && c <= 90 && !base.includes(c)) base.push(c);
    return base;
  }, [custom]);
  useEffect(() => { if (onChange) onChange({ quotes: qn, hours: hn, rate: rn }); }, [qn, hn, rn]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="space-y-5" data-testid="value-calculator">
      <p className="text-sm text-muted-foreground">{t("calc_intro")}</p>
      <fieldset>
        <legend className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">① {t("calc_your_data")}</legend>
        <div className="grid gap-3 sm:grid-cols-3">
          <CalcField id="calc-quotes" label={t("calc_quotes")} value={q} set={setQ} />
          <CalcField id="calc-hours" label={t("calc_hours")} value={h} set={setH} step="0.25" />
          <CalcField id="calc-rate" label={t("calc_rate")} value={r} set={setR} />
        </div>
      </fieldset>
      <div aria-live="polite">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">② {t("calc_math")}</p>
        <div className="rounded-xl border border-border bg-muted/40 p-4 font-mono text-sm space-y-1" data-testid="calc-math">
          <p>{qn ?? "—"} × {hn ?? "—"} h = <b>{hours != null ? t("calc_hours_month", { h: formatNum(hours, lang, 1) }) : "—"}</b></p>
          <p>{hours != null ? formatNum(hours, lang, 1) : "—"} h × {rn != null ? formatEurLang(rn, lang) : "—"} = <b>{cost != null ? t("calc_cost_month", { c: formatEurLang(cost, lang) }) : "—"}</b></p>
        </div>
      </div>
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#8a5524] dark:text-[#e0a46a]">③ {t("calc_scenarios")}</p>
        <ul className="space-y-1.5 text-sm" data-testid="calc-scenarios">
          {scen.map((p) => (
            <li key={p} className="flex items-center gap-2"><span className="rounded bg-[#B87333]/12 px-1.5 py-0.5 font-mono text-xs">{p}%</span>
              {hours != null ? t("calc_scenario_line", { p, h: formatNum(hours * p / 100, lang, 1), c: cost != null ? formatEurLang(cost * p / 100, lang) : "—" }) : "—"}
            </li>
          ))}
        </ul>
        <label className="mt-3 inline-flex items-center gap-2 text-sm">
          {t("calc_custom")}
          <input type="number" min="1" max="90" value={custom} onChange={(e) => setCustom(e.target.value)}
            className="w-20 rounded-md border border-input bg-background px-2 py-1 font-mono" data-testid="calc-custom" />
        </label>
        <p className="mt-3 flex gap-2 rounded-lg border border-dashed border-border p-3 text-xs text-muted-foreground"><Info className="h-4 w-4 shrink-0" aria-hidden />{t("calc_disclaimer")}</p>
      </div>
    </div>
  );
}

const COUNTRIES = ["Portugal", "France", "España", "Belgique", "Suisse", "Luxembourg", "Deutschland", "United Kingdom", "Brasil", "Angola", "Ukraine"];

/**
 * Formulário de contacto mínimo + consentimentos separados (marketing nunca pré-selecionado).
 * steps: lista de próximos passos permitidos para o perfil.
 */
export function ContactForm({ t, onSubmit, defaultStep, steps, orgLabel, busy, sent, queued, error }) {
  const [f, setF] = useState({ name: "", company: "", email: "", phone: "", country: "", channel: "email", message: "",
    next_step: defaultStep || steps[0], privacy_ack: false, marketing_consent: false, email_copy: false, website_url: "" });
  const [touched, setTouched] = useState(false);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  useEffect(() => { if (defaultStep) setF((x) => ({ ...x, next_step: defaultStep })); }, [defaultStep]);
  const valid = f.name.trim() && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim()) && f.privacy_ack;
  if (sent) {
    return (
      <div className="rounded-2xl border border-primary/40 bg-accent/50 p-6" role="status" data-testid="contact-sent">
        <p className="font-display text-xl font-semibold flex items-center gap-2"><CheckCircle2 className="h-5 w-5 text-primary" aria-hidden />{t("sent_title")}</p>
        <p className="mt-2 text-sm">{queued ? t("sent_queued") : t("sent_body")}</p>
      </div>
    );
  }
  const input = "mt-1 w-full rounded-lg border border-input bg-background px-3 py-2.5 text-base focus:outline-none focus:ring-2 focus:ring-ring";
  return (
    <form noValidate onSubmit={(e) => { e.preventDefault(); setTouched(true); if (valid && !busy) onSubmit(f); }}
      className="space-y-4" data-testid="contact-form">
      <fieldset>
        <legend className="sr-only">{t("next_step_title")}</legend>
        <Choices name="next_step" value={f.next_step} onChange={(v) => setF((x) => ({ ...x, next_step: v }))}
          options={steps.map((s) => ({ id: s, label: t({ meeting: "ns_meeting", individual_demo: "ns_demo", pilot: "ns_pilot", report: "ns_report" }[s]) }))}
          testId="contact-next-step" />
      </fieldset>
      <p className="text-sm text-muted-foreground">{t("contact_why")}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block"><span className="text-sm font-medium">{t("f_name")} *</span>
          <input className={input} value={f.name} onChange={set("name")} autoComplete="name" maxLength={120} required aria-invalid={touched && !f.name.trim()} data-testid="f-name" /></label>
        <label className="block"><span className="text-sm font-medium">{orgLabel || t("f_company")}</span>
          <input className={input} value={f.company} onChange={set("company")} autoComplete="organization" maxLength={120} data-testid="f-company" /></label>
        <label className="block"><span className="text-sm font-medium">{t("f_email")} *</span>
          <input className={input} type="email" value={f.email} onChange={set("email")} autoComplete="email" maxLength={160} required aria-invalid={touched && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email)} data-testid="f-email" /></label>
        <label className="block"><span className="text-sm font-medium">{t("f_phone")}</span>
          <input className={input} type="tel" value={f.phone} onChange={set("phone")} autoComplete="tel" maxLength={25} data-testid="f-phone" /></label>
        <label className="block"><span className="text-sm font-medium">{t("f_country")}</span>
          <input className={input} list="cp-countries" value={f.country} onChange={set("country")} autoComplete="country-name" maxLength={60} data-testid="f-country" />
          <datalist id="cp-countries">{COUNTRIES.map((c) => <option key={c} value={c} />)}</datalist></label>
        <label className="block"><span className="text-sm font-medium">{t("f_channel")}</span>
          <select className={input} value={f.channel} onChange={set("channel")} data-testid="f-channel">
            {["email", "phone", "whatsapp", "video"].map((c) => <option key={c} value={c}>{t(`channel.${c}`)}</option>)}
          </select></label>
      </div>
      <label className="block"><span className="text-sm font-medium">{t("f_message")}</span>
        <textarea className={`${input} min-h-[84px]`} value={f.message} onChange={set("message")} maxLength={1000} data-testid="f-message" /></label>
      {/* honeypot anti-spam: invisível para pessoas e tecnologias de apoio */}
      <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
        <label>Website<input tabIndex={-1} autoComplete="off" value={f.website_url} onChange={set("website_url")} /></label>
      </div>
      <div className="space-y-2.5 rounded-xl border border-border bg-muted/30 p-4 text-sm">
        <label className="flex gap-2.5"><input type="checkbox" checked={f.privacy_ack} onChange={set("privacy_ack")} className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]" data-testid="f-privacy" required />
          <span>{t("f_privacy")} <Link to="/privacidade" target="_blank" className="underline underline-offset-2">{t("f_privacy_link")}</Link> *</span></label>
        <label className="flex gap-2.5"><input type="checkbox" checked={f.marketing_consent} onChange={set("marketing_consent")} className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]" data-testid="f-marketing" />
          <span>{t("f_marketing")}</span></label>
        {f.next_step !== "report" && steps.includes("report") && (
          <label className="flex gap-2.5"><input type="checkbox" checked={f.email_copy} onChange={set("email_copy")} className="mt-1 h-4 w-4 accent-[hsl(var(--primary))]" data-testid="f-copy" />
            <span>{t("f_copy")}</span></label>
        )}
      </div>
      {touched && !valid && <p className="text-sm text-destructive" role="alert">{t("err_required")}</p>}
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      <button type="submit" disabled={busy}
        className="inline-flex w-full sm:w-auto items-center justify-center gap-2 rounded-xl bg-primary px-6 py-3 text-base font-semibold text-primary-foreground shadow-sm transition hover:opacity-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
        data-testid="contact-submit">
        {busy ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <ArrowRight className="h-4 w-4" aria-hidden />} {t("submit")}
      </button>
    </form>
  );
}

export function PrimaryButton({ children, onClick, disabled, testId, type = "button" }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} data-testid={testId}
      className="inline-flex items-center justify-center gap-2 rounded-xl bg-primary px-5 py-3 text-base font-semibold text-primary-foreground shadow-sm transition hover:opacity-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50">
      {children}
    </button>
  );
}

export function GhostButton({ children, onClick, disabled, testId }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} data-testid={testId}
      className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-card px-4 py-3 text-sm font-medium transition hover:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50">
      {children}
    </button>
  );
}
