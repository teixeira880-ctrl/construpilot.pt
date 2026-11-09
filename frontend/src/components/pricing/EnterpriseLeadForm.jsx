// Formulaire commercial Enterprise (fichier identique .fr / .pt).
// Validation côté client + serveur, honeypot, temps minimal, anti double-envoi, consentement RGPD.
import { useMemo, useRef, useState } from "react";
import { CheckCircle2, Loader2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { copyFor } from "@/lib/commercialCopy";

const EMPLOYEES = ["1-10", "11-50", "51-200", "201-500", "500+"];
const PROJECTS = ["<20", "20-100", "100-500", "500+"];
const INTERESTS = ["takeoff", "quotes", "site", "costs", "teams", "erp", "api", "multi_company", "sla", "onboarding", "bim"];
const FREE = /@(gmail|hotmail|outlook|yahoo|live|icloud|sapo|free|orange|laposte|aol|gmx|proton(mail)?)\./i;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONE = /^[+()\d][\d\s().-]{5,38}$/;

function newSubmissionId() {
  try { return crypto.randomUUID(); } catch { return `s${Date.now()}${Math.random().toString(16).slice(2)}`; }
}

export function validateLead(f, e) {
  const err = {};
  for (const k of ["name", "company", "email", "country", "employees", "projects"]) {
    if (!String(f[k] || "").trim()) err[k] = e.err_required;
  }
  if (f.name && f.name.trim().length < 2) err.name = e.err_required;
  if (f.email && !EMAIL.test(f.email.trim())) err.email = e.err_email;
  if (f.phone && !PHONE.test(f.phone.trim())) err.phone = e.err_phone;
  if (!f.consent) err.consent = e.err_consent;
  return err;
}

export default function EnterpriseLeadForm({ lang }) {
  const e = copyFor(lang).ent;
  const startedAt = useRef(Date.now());
  const submissionId = useMemo(newSubmissionId, []);
  const [f, setF] = useState({ name: "", company: "", email: "", phone: "", country: e.countries[0],
    employees: "", projects: "", features: [], message: "", consent: false, website: "" });
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState("idle"); // idle | sending | done | error
  const [serverMsg, setServerMsg] = useState("");

  const set = (k) => (ev) => setF((s) => ({ ...s, [k]: ev?.target ? (ev.target.type === "checkbox" ? ev.target.checked : ev.target.value) : ev }));
  const toggle = (k) => setF((s) => ({ ...s, features: s.features.includes(k) ? s.features.filter((x) => x !== k) : [...s.features, k] }));

  const submit = async (ev) => {
    ev.preventDefault();
    if (status === "sending" || status === "done") return; // anti double-envoi
    const err = validateLead(f, e);
    setErrors(err);
    if (Object.keys(err).length) {
      document.getElementById(`ent-${Object.keys(err)[0]}`)?.focus();
      return;
    }
    setStatus("sending");
    try {
      const { data } = await api.post("/commercial/enterprise-lead", {
        ...f, lang, submission_id: submissionId, elapsed_ms: Date.now() - startedAt.current,
      });
      setServerMsg(data.message);
      setStatus("done");
    } catch (er) {
      setServerMsg(er?.response?.status === 429 ? e.err_rate : e.err_generic);
      setStatus("error");
    }
  };

  if (status === "done") {
    return (
      <div role="status" className="mx-auto max-w-xl rounded-2xl border border-primary/40 bg-card p-10 text-center" data-testid="enterprise-success">
        <CheckCircle2 className="mx-auto h-12 w-12 text-primary" aria-hidden />
        <p className="mt-4 font-display text-2xl font-bold">{e.success_title}</p>
        <p className="mt-2 text-sm text-muted-foreground">{serverMsg}</p>
      </div>
    );
  }

  const field = (k, label, input, hint) => (
    <div className="grid gap-1.5">
      <Label htmlFor={`ent-${k}`}>{label}</Label>
      {input}
      {errors[k] ? <p id={`ent-${k}-err`} className="text-xs text-destructive" role="alert">{errors[k]}</p>
        : hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
  const aria = (k) => ({ id: `ent-${k}`, "aria-invalid": !!errors[k], "aria-describedby": errors[k] ? `ent-${k}-err` : undefined });
  const selectCls = "h-10 w-full rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

  return (
    <div className="grid gap-8 rounded-2xl border border-border bg-card p-6 md:grid-cols-[1fr_1.6fr] md:p-10" data-testid="enterprise-form">
      <div>
        <p className="overline text-primary">ENTERPRISE</p>
        <h2 id="enterprise-title" className="mt-2 font-display text-3xl font-bold tracking-tight">{e.title}</h2>
        <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{e.intro}</p>
      </div>
      <form onSubmit={submit} noValidate className="grid gap-4" aria-describedby="enterprise-title">
        <div className="grid gap-4 sm:grid-cols-2">
          {field("name", e.name, <Input {...aria("name")} autoComplete="name" value={f.name} onChange={set("name")} maxLength={120} required />)}
          {field("company", e.company, <Input {...aria("company")} autoComplete="organization" value={f.company} onChange={set("company")} maxLength={160} required />)}
          {field("email", e.email, <Input {...aria("email")} type="email" autoComplete="email" value={f.email} onChange={set("email")} maxLength={200} required />,
            FREE.test(f.email) ? e.freemail : null)}
          {field("phone", e.phone, <Input {...aria("phone")} type="tel" autoComplete="tel" value={f.phone} onChange={set("phone")} maxLength={40} />)}
          {field("country", e.country, (
            <select {...aria("country")} className={selectCls} value={f.country} onChange={set("country")}>
              {e.countries.map((x) => <option key={x}>{x}</option>)}
            </select>))}
          {field("employees", e.employees, (
            <select {...aria("employees")} className={selectCls} value={f.employees} onChange={set("employees")} required>
              <option value="">{e.select}</option>{EMPLOYEES.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>))}
          {field("projects", e.projects, (
            <select {...aria("projects")} className={selectCls} value={f.projects} onChange={set("projects")} required>
              <option value="">{e.select}</option>{PROJECTS.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>))}
        </div>
        <fieldset className="grid gap-2">
          <legend className="text-sm font-medium mb-1">{e.features}</legend>
          <div className="flex flex-wrap gap-2">
            {INTERESTS.map((k) => {
              const on = f.features.includes(k);
              return (
                <button key={k} type="button" aria-pressed={on} onClick={() => toggle(k)} data-testid={`ent-interest-${k}`}
                  className={`rounded-full border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    on ? "border-primary bg-primary/10 text-primary" : "border-border hover:border-primary/50"}`}>
                  {e.interests[k]}
                </button>
              );
            })}
          </div>
        </fieldset>
        {field("message", e.message, <Textarea {...aria("message")} rows={4} value={f.message} onChange={set("message")} maxLength={4000} placeholder={e.message_ph} />)}
        {/* Honeypot : invisible pour les humains, rempli par les robots. */}
        <div aria-hidden="true" className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
          <label>Website<input tabIndex={-1} autoComplete="off" value={f.website} onChange={set("website")} name="website" /></label>
        </div>
        <div className="grid gap-1.5">
          <label className="flex items-start gap-2 text-xs leading-relaxed">
            <input {...aria("consent")} type="checkbox" checked={f.consent} onChange={set("consent")} className="mt-0.5 h-4 w-4 accent-[hsl(var(--primary))]" />
            <span>{e.consent} <a href={e.privacy_href} target="_blank" rel="noreferrer" className="underline underline-offset-2">{e.privacy}</a>.</span>
          </label>
          {errors.consent && <p id="ent-consent-err" className="text-xs text-destructive" role="alert">{errors.consent}</p>}
        </div>
        {status === "error" && <p role="alert" className="text-sm text-destructive" data-testid="enterprise-error">{serverMsg}</p>}
        <Button type="submit" disabled={status === "sending"} className="h-11 gap-2 rounded-lg sm:w-fit" data-testid="enterprise-submit">
          {status === "sending" ? <><Loader2 className="h-4 w-4 animate-spin" aria-hidden />{e.sending}</> : <><Send className="h-4 w-4" aria-hidden />{e.submit}</>}
        </Button>
      </form>
    </div>
  );
}
