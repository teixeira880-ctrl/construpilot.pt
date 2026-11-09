// Offre commerciale B2B : Solo · Professional · Business · Enterprise.
// Fichier IDENTIQUE dans construpilot.fr et construpilot.pt. Montants fournis par l'API
// /commercial/plans (source unique côté serveur). Enterprise : aucun montant affiché.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight, Sparkles, Trophy, Building2, Check, CreditCard, Landmark, Loader2, Lock, Minus, RefreshCw, Ruler, ShieldCheck, Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { api } from "@/lib/api";
import { copyFor, featureLabel } from "@/lib/commercialCopy";
import { CATEGORIES, guideFor, recommendPlan } from "@/lib/commercialGuide";
import { formatEur, formatInt, formatStorage } from "@/lib/market";
import EnterpriseLeadForm from "@/components/pricing/EnterpriseLeadForm";

const ICONS = { solo: Ruler, professional: Users, business: Building2, enterprise: Landmark };
const LIMIT_KEYS = ["seats", "active_projects", "pages_monthly", "storage_bytes"];

function limitText(c, key, value, lang) {
  if (key === "storage_bytes") return c.limits.storage_bytes(formatStorage(value, lang));
  return c.limits[key](key === "seats" ? value : formatInt(value, lang));
}

// Coût mensuel effectif (centimes) selon la périodicité choisie.
function monthlyCents(plan, interval) {
  if (!plan.price) return null;
  return interval === "year" ? plan.price.year_monthly_equiv_cents : plan.price.month_cents;
}

// Offre au meilleur coût par page (calculé, pas affirmé) → badge « meilleur rapport qualité-prix ».
export function bestValueKey(plans) {
  const priced = plans.filter((p) => p.price);
  if (!priced.length) return null;
  return priced.reduce((a, b) => (b.price.month_cents / b.limits.pages_monthly < a.price.month_cents / a.limits.pages_monthly ? b : a)).key;
}

function ValueLine({ g, plan, interval, lang }) {
  const m = monthlyCents(plan, interval);
  if (m == null) return null;
  return (
    <p className="mt-2 text-xs text-muted-foreground" data-testid={`value-${plan.key}`}>
      {g.per_page(formatEur(m / plan.limits.pages_monthly, lang, { decimals: 2 }))}
      {" · "}
      {g.per_user(formatEur(m / plan.limits.seats, lang, { decimals: 2 }))}
    </p>
  );
}

function UpgradeHint({ g, c, plan, next, interval, lang }) {
  if (!next?.price || !plan.price) return null;
  const diff = monthlyCents(next, interval) - monthlyCents(plan, interval);
  const factor = Math.round((next.limits.pages_monthly / plan.limits.pages_monthly) * 10) / 10;
  return (
    <p className="mt-3 flex gap-2 rounded-lg bg-primary/5 p-3 text-xs leading-snug" data-testid={`upgrade-hint-${plan.key}`}>
      <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden />
      <span>{g.upgrade_hint(formatEur(diff, lang, { decimals: diff % 100 ? 2 : 0 }), c.names[next.key], String(factor).replace(".", ","))}</span>
    </p>
  );
}

export function BillingToggle({ c, interval, onChange }) {
  const opts = [["month", c.monthly], ["year", c.yearly]];
  return (
    <div role="radiogroup" aria-label={c.billing_label} data-testid="billing-toggle"
      className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 shadow-sm">
      {opts.map(([v, label]) => {
        const on = interval === v;
        return (
          <button key={v} type="button" role="radio" aria-checked={on} data-testid={`billing-${v}`}
            onClick={() => onChange(v)}
            className={`relative rounded-full px-5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              on ? "bg-primary text-primary-foreground shadow" : "text-muted-foreground hover:text-foreground"}`}>
            {label}
            {v === "year" && (
              <span className={`ml-2 rounded-full px-2 py-0.5 text-[11px] font-semibold ${on ? "bg-white/20" : "bg-accent text-accent-foreground"}`}>
                {c.save}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function PriceBlock({ c, plan, interval, lang }) {
  if (!plan.price) {
    return (
      <div className="min-h-[92px]" data-testid={`price-${plan.key}`}>
        <p className="font-display text-3xl font-extrabold tracking-tight">{c.on_quote}</p>
        <p className="text-xs text-muted-foreground mt-1">{c.ent_price_note}</p>
      </div>
    );
  }
  const p = plan.price;
  if (interval === "month") {
    return (
      <div className="min-h-[92px]" data-testid={`price-${plan.key}`}>
        <p><span className="num font-display text-4xl font-extrabold tracking-tighter">{formatEur(p.month_cents, lang)}</span>
          <span className="text-sm text-muted-foreground ml-1">{c.per_month}</span></p>
      </div>
    );
  }
  const saving = p.month_cents * 12 - p.year_cents;
  return (
    <div className="min-h-[92px]" data-testid={`price-${plan.key}`}>
      <p><span className="num font-display text-4xl font-extrabold tracking-tighter">
        {formatEur(p.year_monthly_equiv_cents, lang, { decimals: 2 })}</span>
        <span className="text-sm text-muted-foreground ml-1">{c.per_month}</span></p>
      <p className="text-xs text-muted-foreground mt-1" data-testid={`price-${plan.key}-yearly-total`}>
        {c.billed_yearly(formatEur(p.year_cents, lang, { decimals: 2 }))}</p>
      <p className="text-xs font-medium text-primary mt-0.5">{c.yearly_saving(formatEur(saving, lang, { decimals: 2 }))}</p>
    </div>
  );
}

function StatusTag({ c, status }) {
  if (status === "available") return null;
  return (
    <span className="ml-1.5 rounded-sm border border-border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
      {c.status[status]}
    </span>
  );
}

function PlanCard({ c, g, lang, plan, parent, next, bestValue, interval, busy, onChoose, onContact }) {
  const Icon = ICONS[plan.key] || Ruler;
  const hi = plan.highlight;
  const best = bestValue === plan.key && !hi;
  const inherited = new Set(parent ? parent.features.map((f) => f.key) : []);
  const own = plan.features.filter((f) => !inherited.has(f.key));
  const isEnt = plan.key === "enterprise";
  return (
    <article data-testid={`plan-card-${plan.key}`} aria-labelledby={`plan-${plan.key}-name`}
      className={`relative flex flex-col rounded-xl border bg-card p-6 transition-all duration-200 motion-safe:hover:-translate-y-0.5 ${
        hi ? "border-primary shadow-[0_18px_50px_-24px_hsl(var(--primary)/0.65)] ring-1 ring-primary/40 lg:-mt-3 lg:pb-9"
          : best ? "border-accent ring-1 ring-accent/60 shadow-md lg:-mt-3 lg:pb-9" : "border-border shadow-sm hover:shadow-md"}`}>
      {best && (
        <span data-testid="badge-best-value"
          className="absolute -top-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full bg-accent px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-accent-foreground shadow">
          <Trophy className="h-3 w-3" aria-hidden />{g.value_badge}
        </span>
      )}
      {hi && (
        <span data-testid="badge-popular"
          className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-primary px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary-foreground shadow">
          {c.popular}
        </span>
      )}
      <div className="flex items-center gap-3">
        <span className={`grid h-10 w-10 place-items-center rounded-lg ${hi ? "bg-primary/15 text-primary" : "bg-secondary text-foreground"}`}>
          <Icon className="h-5 w-5" aria-hidden />
        </span>
        <div>
          <h3 id={`plan-${plan.key}-name`} className="font-display text-xl font-bold uppercase tracking-wide">{c.names[plan.key]}</h3>
          <p className="text-xs text-muted-foreground leading-snug">{c.audiences[plan.key]}</p>
        </div>
      </div>
      <p className="mt-4 text-sm font-medium leading-snug min-h-[40px]">{c.taglines[plan.key]}</p>
      <div className="mt-4"><PriceBlock c={c} plan={plan} interval={interval} lang={lang} /></div>
      <ValueLine g={g} plan={plan} interval={interval} lang={lang} />
      <p className="mt-3 rounded-lg border border-dashed border-border p-2.5 text-xs leading-snug" data-testid={`best-for-${plan.key}`}>{g.best_for[plan.key]}</p>

      <div className="mt-4">
        {isEnt ? (
          <Button variant="outline" className="w-full gap-2 rounded-lg h-11" onClick={onContact} data-testid="plan-cta-enterprise">
            {c.cta_contact} <ArrowRight className="h-4 w-4" aria-hidden />
          </Button>
        ) : (
          <Button className="w-full gap-2 rounded-lg h-11" variant={hi || best ? "default" : "outline"} disabled={!!busy}
            onClick={() => onChoose(plan)} data-testid={`plan-cta-${plan.key}`} aria-busy={busy === plan.key}>
            {busy === plan.key ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {c.redirecting}</>
              : <>{c.cta_choose(c.names[plan.key])} <ArrowRight className="h-4 w-4" aria-hidden /></>}
          </Button>
        )}
        <UpgradeHint g={g} c={c} plan={plan} next={next} interval={interval} lang={lang} />
      </div>

      <ul className="mt-6 grid gap-2 border-t border-border pt-5" aria-label={c.compare_limits}>
        {isEnt && <li className="text-[11px] uppercase tracking-wider text-muted-foreground">{c.enterprise_limits_prefix}</li>}
        {LIMIT_KEYS.map((k) => (
          <li key={k} className="flex items-start gap-2 text-sm font-medium">
            <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden />{limitText(c, k, plan.limits[k], lang)}
          </li>
        ))}
        {isEnt && <li className="text-xs text-muted-foreground">{c.enterprise_limits_note}</li>}
      </ul>

      <div className="mt-5 grid gap-2">
        {parent && <p className="text-xs font-semibold text-muted-foreground">{c.everything_in(c.names[parent.key])}</p>}
        <ul className="grid gap-2">
          {own.map((f) => (
            <li key={f.key} className="flex items-start gap-2 text-sm">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary/80" aria-hidden />
              <span>{featureLabel(lang, f.key)}<StatusTag c={c} status={f.status} /></span>
            </li>
          ))}
        </ul>
      </div>
    </article>
  );
}

function ComparisonTable({ c, g, lang, plans, interval, bestValue, onChoose, onContact }) {
  const has = (plan, key) => plan.features.some((f) => f.key === key);
  const status = Object.fromEntries(plans[plans.length - 1].features.map((f) => [f.key, f.status]));
  const colCls = (p) => (p.key === bestValue ? "bg-accent/10" : p.highlight ? "bg-primary/5" : "");
  return (
    <section aria-labelledby="compare-title" className="grid gap-4" data-testid="pricing-compare">
      <h2 id="compare-title" className="font-display text-2xl font-bold tracking-tight text-center">{c.compare_title}</h2>
      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">{c.compare_title}</caption>
          <thead className="sticky top-0 z-10 bg-card">
            <tr className="border-b border-border align-bottom">
              <th scope="col" className="sticky left-0 z-10 bg-card p-4 text-left font-medium text-muted-foreground w-[34%]">{c.compare_limits}</th>
              {plans.map((p) => (
                <th key={p.key} scope="col" className={`p-4 text-center ${colCls(p)}`}>
                  {p.key === bestValue && <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-accent-foreground">{g.recommended}</span>}
                  {p.highlight && <span className="mb-1 block text-[10px] font-bold uppercase tracking-wider text-primary">{c.popular}</span>}
                  <span className="block font-display text-base font-bold">{c.names[p.key]}</span>
                  <span className="block text-xs font-normal text-muted-foreground num">
                    {p.price ? `${formatEur(monthlyCents(p, interval), lang, { decimals: interval === "year" ? 2 : 0 })}${c.per_month}` : c.on_quote}
                  </span>
                  <Button size="sm" variant={p.key === bestValue || p.highlight ? "default" : "outline"} className="mt-2 h-8 w-full text-xs"
                    onClick={() => (p.price ? onChoose(p) : onContact())} data-testid={`compare-cta-${p.key}`}>
                    {p.price ? g.choose_this : c.cta_contact}
                  </Button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {LIMIT_KEYS.map((k) => (
              <tr key={k} className="border-b border-border/60">
                <th scope="row" className="sticky left-0 bg-card p-3 text-left font-medium">{c.limit_labels[k]}</th>
                {plans.map((p) => (
                  <td key={p.key} className={`p-3 text-center num font-semibold ${colCls(p)}`}>
                    {k === "storage_bytes" ? formatStorage(p.limits[k], lang) : formatInt(p.limits[k], lang)}
                    {p.limits_are_reference ? "*" : ""}
                  </td>
                ))}
              </tr>
            ))}
            {CATEGORIES.map(([cat, keys]) => (
              <Fragment key={cat}>
                <tr>
                  <th colSpan={plans.length + 1} scope="colgroup" data-testid={`compare-cat-${cat}`}
                    className="bg-secondary/60 p-3 text-left text-xs font-semibold uppercase tracking-wider text-foreground">
                    {g.categories[cat]}
                  </th>
                </tr>
                {keys.map((key) => (
                  <tr key={key} className="border-b border-border/40">
                    <th scope="row" className="sticky left-0 bg-card p-3 text-left font-normal">
                      <span className="font-medium">{featureLabel(lang, key)}</span><StatusTag c={c} status={status[key] || "available"} />
                      <span className="mt-0.5 block text-xs text-muted-foreground">{g.help[key]}</span>
                    </th>
                    {plans.map((p) => (
                      <td key={p.key} className={`p-3 text-center ${colCls(p)}`}>
                        {has(p, key)
                          ? <Check className="mx-auto h-4 w-4 text-primary" aria-label={g.included} />
                          : <Minus className="mx-auto h-4 w-4 text-muted-foreground/40" aria-label={g.not_included} />}
                      </td>
                    ))}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">* {c.enterprise_limits_note}</p>
    </section>
  );
}

function PlanFinder({ c, g, plans, onChoose, onContact }) {
  const [a, setA] = useState({ users: 3, projects: 15, site: true });
  const pick = recommendPlan(plans, a);
  const plan = plans.find((p) => p.key === pick);
  const opt = (field, values) => (
    <div className="flex flex-wrap gap-2">
      {values.map(([v, label]) => (
        <button key={String(v)} type="button" aria-pressed={a[field] === v} onClick={() => setA((s) => ({ ...s, [field]: v }))}
          data-testid={`finder-${field}-${v}`}
          className={`rounded-full border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            a[field] === v ? "border-primary bg-primary text-primary-foreground" : "border-border hover:border-primary/50"}`}>
          {label}
        </button>
      ))}
    </div>
  );
  return (
    <section aria-labelledby="finder-title" className="grid gap-6 rounded-2xl border border-border bg-card p-6 md:grid-cols-[1.4fr_1fr] md:p-8" data-testid="plan-finder">
      <div className="grid gap-5">
        <div>
          <h2 id="finder-title" className="font-display text-2xl font-bold tracking-tight">{g.finder_title}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{g.finder_sub}</p>
        </div>
        <div className="grid gap-2"><p className="text-sm font-medium">{g.q_users}</p>
          {opt("users", [[1, "1"], [3, "2–4"], [8, "5–10"], [20, "11–25"], [60, "25+"]])}</div>
        <div className="grid gap-2"><p className="text-sm font-medium">{g.q_projects}</p>
          {opt("projects", [[5, "< 7"], [15, "7–30"], [60, "30–120"], [200, "120+"]])}</div>
        <div className="grid gap-2"><p className="text-sm font-medium">{g.q_site}</p>
          {opt("site", [[true, g.yes], [false, g.no]])}</div>
      </div>
      <div role="status" aria-live="polite" className="flex flex-col justify-center rounded-xl bg-primary/10 p-6" data-testid="finder-result">
        <p className="text-xs uppercase tracking-wider text-muted-foreground">{c.names[pick]}</p>
        <p className="mt-1 font-display text-2xl font-bold" data-testid={`finder-pick-${pick}`}>{g.result(c.names[pick])}</p>
        <p className="mt-2 text-sm leading-relaxed">{g.result_why[pick]}</p>
        <Button className="mt-4 h-11 gap-2" onClick={() => (plan?.price ? onChoose(plan) : onContact())} data-testid="finder-cta">
          {plan?.price ? g.choose_this : c.cta_contact} <ArrowRight className="h-4 w-4" aria-hidden />
        </Button>
      </div>
    </section>
  );
}

export default function CommercialPricing({ lang, user }) {
  const c = copyFor(lang);
  const g = guideFor(lang);
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "loading", data: null });
  const [interval, setIntervalState] = useState(() => {
    // Annuel par défaut : prix mensuel équivalent le plus bas affiché d'abord.
    try { return localStorage.getItem("cp_billing_interval") === "month" ? "month" : "year"; } catch { return "year"; }
  });
  const [busy, setBusy] = useState(null);
  const entRef = useRef(null);

  const load = useCallback(() => {
    setState({ status: "loading", data: null });
    api.get("/commercial/plans")
      .then(({ data }) => setState({ status: "ready", data }))
      .catch(() => setState({ status: "error", data: null }));
  }, []);
  useEffect(load, [load]);

  const setInterval = (v) => {
    setIntervalState(v);
    try { localStorage.setItem("cp_billing_interval", v); } catch { /* stockage indisponible */ }
  };

  const plans = useMemo(() => state.data?.plans || [], [state.data]);
  const byKey = useMemo(() => Object.fromEntries(plans.map((p) => [p.key, p])), [plans]);
  const bestValue = useMemo(() => bestValueKey(plans), [plans]);

  const contact = () => {
    entRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setTimeout(() => entRef.current?.querySelector("input")?.focus({ preventScroll: true }), 450);
  };

  const openPortal = async () => {
    try {
      const { data } = await api.post("/commercial/portal", {});
      window.location.href = data.url;
    } catch { toast.error(c.checkout_error); }
  };

  const choose = async (plan) => {
    if (!state.data?.checkout_open) {
      toast.info(c.checkout_soon);
      navigate(`/inscription?signup=1&plan=${plan.key}&billing=${interval}`);
      return;
    }
    if (!user) {
      toast.info(c.login_needed);
      navigate(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setBusy(plan.key);
    try {
      const { data } = await api.post("/commercial/checkout", {
        plan: plan.key, interval, origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (err) {
      const code = err?.response?.data?.detail?.code;
      if (code === "use_portal") { toast.info(c.use_portal); openPortal(); }
      else if (code === "checkout_not_open") toast.info(c.checkout_soon);
      else toast.error(c.checkout_error);
      setBusy(null);
    }
  };

  return (
    <div className="grid gap-14" data-testid="commercial-pricing">
      <div className="flex flex-col items-center gap-3">
        <BillingToggle c={c} interval={interval} onChange={setInterval} />
        {state.status === "ready" && !state.data.checkout_open && (
          <p className="text-xs text-muted-foreground" data-testid="checkout-soon-note">{c.checkout_soon}</p>
        )}
      </div>

      {state.status === "loading" && (
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-live="polite">
          <span className="sr-only">{c.loading}</span>
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-[560px] animate-pulse rounded-xl border border-border bg-card/60" />)}
        </div>
      )}

      {state.status === "error" && (
        <div role="alert" className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-xl border border-border bg-card p-8 text-center" data-testid="pricing-error">
          <p className="text-sm">{c.load_error}</p>
          <Button variant="outline" onClick={load} className="gap-2"><RefreshCw className="h-4 w-4" aria-hidden />{c.retry}</Button>
        </div>
      )}

      {state.status === "ready" && (
        <>
          <div className="grid items-start gap-6 md:grid-cols-2 xl:grid-cols-4" data-testid="pricing-grid-b2b">
            {plans.map((p) => (
              <PlanCard key={p.key} c={c} g={g} lang={lang} plan={p} parent={p.inherits ? byKey[p.inherits] : null}
                next={plans[plans.indexOf(p) + 1]} bestValue={bestValue}
                interval={interval} busy={busy} onChoose={choose} onContact={contact} />
            ))}
          </div>
          <p className="-mt-8 text-center text-xs text-muted-foreground" data-testid="tax-note">{c.tax_note}</p>

          <section aria-labelledby="addons-title" className="grid gap-4" data-testid="pricing-addons">
            <h2 id="addons-title" className="font-display text-2xl font-bold tracking-tight text-center">{c.addons_title}</h2>
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              {["extra_seat", "pages_500", "onboarding", "custom_integration"].map((k) => {
                const [name, price, scope] = c.addons[k];
                return (
                  <div key={k} className="rounded-xl border border-border bg-card p-5" data-testid={`addon-${k}`}>
                    <p className="font-display font-semibold">{name}</p>
                    <p className="mt-1 num text-lg font-bold">{price}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{scope}</p>
                  </div>
                );
              })}
            </div>
            <p className="text-center text-xs text-muted-foreground">{c.addons_note}</p>
          </section>

          <section className="grid gap-4 md:grid-cols-3" aria-label="trust">
            {c.trust.map(([t, d], i) => {
              const I = [CreditCard, Lock, ShieldCheck][i];
              return (
                <div key={t} className="flex gap-3 rounded-xl border border-border bg-card p-5">
                  <I className="h-5 w-5 shrink-0 text-primary" aria-hidden />
                  <div><p className="font-display font-semibold">{t}</p><p className="mt-1 text-xs text-muted-foreground">{d}</p></div>
                </div>
              );
            })}
          </section>

          <PlanFinder c={c} g={g} plans={plans} onChoose={choose} onContact={contact} />

          <ComparisonTable c={c} g={g} lang={lang} plans={plans} interval={interval} bestValue={bestValue}
            onChoose={choose} onContact={contact} />
        </>
      )}

      <section ref={entRef} id="enterprise" className="scroll-mt-24" aria-labelledby="enterprise-title">
        <EnterpriseLeadForm lang={lang} />
      </section>

      <section aria-labelledby="faq-title" className="mx-auto w-full max-w-3xl" data-testid="pricing-faq">
        <h2 id="faq-title" className="font-display text-2xl font-bold tracking-tight text-center">{c.faq_title}</h2>
        <Accordion type="single" collapsible className="mt-6">
          {c.faq.map(([q, a], i) => (
            <AccordionItem key={q} value={`f${i}`}>
              <AccordionTrigger className="text-base">{q}</AccordionTrigger>
              <AccordionContent className="text-sm text-muted-foreground leading-relaxed">{a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>
    </div>
  );
}
