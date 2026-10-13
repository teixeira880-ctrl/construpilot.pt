import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, Link, useSearchParams } from "react-router-dom";
import axios from "axios";
import { ListenButton } from "@/components/voice/VoiceButtons";
import { PortalMessages, PortalIssues } from "@/components/portal/PortalTabs";
import { PortalDocuments } from "@/components/portal/PortalDocuments";
import { PortalReceptions } from "@/components/portal/PortalReceptions";
import { PortalPlanning } from "@/components/portal/PortalPlanning";
import { HardHat, KeyRound, Mail, ArrowRight, LogOut, Phone, CheckCircle2, Clock, AlertTriangle, Circle, Camera, ChevronDown, MessageSquare, TrendingUp, FileText, ClipboardCheck } from "lucide-react";

const BASE = process.env.REACT_APP_BACKEND_URL;
export const portalApi = axios.create({ baseURL: `${BASE}/api/portal`, withCredentials: true });
const detail = (e, fallback) => { const d = e?.response?.data?.detail; return typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join(" ") : fallback; };
const field = "w-full rounded-lg border border-[#d9cbbb] bg-[#fffaf3] px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-[#ad714b]";

function Frame({ children, company }) {
  return (
    <div className="min-h-screen bg-[#f5efe6] text-[#302b26]">
      <header className="border-b bg-[#fffaf3]"><div className="max-w-4xl mx-auto px-4 py-3 flex items-center gap-3">
        {company?.logo ? <img src={company.logo} alt="" className="h-9 w-9 rounded object-contain" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : <HardHat className="h-6 w-6 text-emerald-700" />}
        <div className="min-w-0"><p className="font-semibold truncate" data-testid="portal-company">{company?.name || "Espaço da obra"}</p><p className="text-[11px] text-slate-500">Espaço da obra seguro · ConstruPilot</p></div>
        {children[0]}
      </div></header>
      <main className="max-w-4xl mx-auto px-4 py-6 grid gap-6">{children[1]}</main>
    </div>
  );
}

export function PortalLogin() {
  const nav = useNavigate();
  const [step, setStep] = useState("login");
  const [form, setForm] = useState({ ref: "", email: "", code: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  useEffect(() => { portalApi.get("/me").then(({ data }) => nav(`/espace/${data.participant.chantier_ref}`, { replace: true })).catch(() => {}); }, [nav]);
  const submit = async (e) => {
    e.preventDefault(); setError(""); setBusy(true);
    try {
      if (step === "login") { await portalApi.post("/login", { ref: form.ref, email: form.email }); setStep("code"); }
      else { const { data } = await portalApi.post("/verify", form); nav(`/espace/${data.participant.chantier_ref}`, { replace: true }); }
    } catch (err) { setError(err?.response?.status === 429 ? "Demasiadas tentativas: aguarde alguns minutos." : detail(err, "Ligação impossível")); }
    finally { setBusy(false); }
  };
  return (
    <Frame company={null}>
      {null}
      <form onSubmit={submit} className="max-w-md mx-auto w-full rounded-2xl border bg-[#fffaf3] p-6 grid gap-4 mt-8" data-testid="portal-login-form">
        <div><h1 className="text-xl font-semibold flex items-center gap-2"><KeyRound className="h-5 w-5 text-emerald-700" /> Aceder à minha obra</h1>
          <p className="text-sm text-slate-600 mt-1">{step === "login" ? "Introduza o identificador da obra (recebido por e-mail) e o seu endereço de e-mail: ser-lhe-á enviado um código." : `Foi enviado um código de 6 dígitos para${form.email} (valable 10 min).`}</p></div>
        {step === "login" ? <>
          <label className="text-sm grid gap-1">Identificador da obra<input className={`${field} font-mono uppercase`} value={form.ref} onChange={set("ref")} placeholder="CP-XXXX-XXXX" required data-testid="portal-ref" /></label>
          <label className="text-sm grid gap-1">O seu e-mail<input type="email" className={field} value={form.email} onChange={set("email")} required data-testid="portal-email" /></label>
        </> : <label className="text-sm grid gap-1">Código recebido por e-mail<input inputMode="numeric" pattern="[0-9]{6}" maxLength={6} className={`${field} text-center text-2xl tracking-[0.5em] font-mono`} value={form.code} onChange={set("code")} required autoFocus data-testid="portal-code" /></label>}
        {error && <p className="text-sm text-red-600" role="alert" data-testid="portal-error">{error}</p>}
        <button type="submit" disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-lg bg-[#855334] text-white py-2.5 font-medium disabled:opacity-60" data-testid="portal-submit">
          {step === "login" ? <Mail className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />} {busy ? "…" : step === "login" ? "Receber o meu código" : "Entrer"}
        </button>
        {step === "code" && <button type="button" onClick={() => { setStep("login"); setError(""); }} className="text-xs text-slate-500 underline" data-testid="portal-back">Alterar o identificador ou o e-mail</button>}
      </form>
    </Frame>
  );
}

export function PortalAccept() {
  const { token } = useParams();
  const nav = useNavigate();
  const [error, setError] = useState("");
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    portalApi.post(`/accept/${token}`).then(({ data }) => nav(`/espace/${data.participant.chantier_ref}`, { replace: true }))
      .catch((e) => setError(detail(e, "Lien invalide")));
  }, [token, nav]);
  return (
    <Frame company={null}>{null}
      <div className="max-w-md mx-auto w-full rounded-2xl border bg-[#fffaf3] p-6 mt-8 text-center" data-testid="portal-accept">
        {error ? <><AlertTriangle className="h-8 w-8 mx-auto text-amber-600" /><p className="mt-3 text-sm" data-testid="portal-accept-error">{error}</p><Link to="/espace" className="inline-block mt-4 text-emerald-700 underline text-sm">Iniciar sessão com o identificador da obra</Link></>
          : <p className="text-sm text-slate-600">A abrir o seu espaço da obra…</p>}
      </div>
    </Frame>
  );
}

const MS = { planned: [Circle, "text-slate-400", "Previsto"], in_progress: [Clock, "text-amber-600", "En cours"], done: [CheckCircle2, "text-emerald-600", "Terminado"], late: [AlertTriangle, "text-red-600", "En retard"] };

export function PortalChantier() {
  const { ref } = useParams();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const requestedTab = ["progress", "documents", "receptions", "messages", "issues"].includes(params.get("tab")) ? params.get("tab") : "progress";
  const setTab = (t) => setParams(t === "progress" ? {} : { tab: t }, { replace: true });
  const [data, setData] = useState(null);
  const [me, setMe] = useState(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(null);
  useEffect(() => {
    let alive = true; setData(null); setMe(null); setError("");
    portalApi.get(`/${ref}/overview`).then(({ data }) => { if (alive) setData(data); }).catch((e) => { if (!alive) return; if (e?.response?.status === 401) nav("/espace", { replace: true }); else setError(detail(e, "Obra inacessível")); });
    portalApi.get("/me").then(({ data }) => { if (alive) setMe(data); }).catch(() => {});
    return () => { alive = false; };
  }, [ref, nav]);
  const logout = async () => { await portalApi.post("/logout").catch(() => {}); nav("/espace", { replace: true }); };
  const switchTo = async (pid) => { const { data: r } = await portalApi.post("/switch", { participant_id: pid }); nav(`/espace/${r.participant.chantier_ref}`); };
  if (error) return <Frame company={null}>{null}<p className="text-sm text-red-600" data-testid="portal-error">{error}</p></Frame>;
  if (!data) return <Frame company={null}>{null}<p className="text-sm text-slate-500">A carregar…</p></Frame>;
  const { chantier, company, participant, milestones, reports, photos, progress_pct } = data;
  const accent = company.accent || "#855334";
  const photoUrl = (p) => `${BASE}/api/portal/${ref}/photo?path=${encodeURIComponent(p)}`;
  const others = (me?.chantiers || []).filter((c) => c.available);
  const canDocs = participant.role === "client" && (participant.permissions?.quotes || participant.permissions?.invoices);
  const canRecept = participant.role === "client";
  const tabs = [["progress", "Avancement", TrendingUp, true], ["documents", "Orçamentos e faturas", FileText, !!canDocs], ["receptions", "Receção", ClipboardCheck, !!canRecept], ["messages", "Messages", MessageSquare, !!participant.permissions?.chat], ["issues", "Problemas", AlertTriangle, !!participant.permissions?.report_issue]].filter((t) => t[3]);
  const tab = tabs.some(t => t[0] === requestedTab) ? requestedTab : "progress";
  return (
    <Frame company={company}>
      <div className="ms-auto flex flex-wrap justify-end items-center gap-2 min-w-0">
        {others.length > 1 && <div className="relative"><select value={me.participant.participant_id} onChange={(e) => switchTo(e.target.value)} className="text-xs rounded-md border px-2 py-1.5 pr-6 max-w-[160px] bg-[#fffaf3]" data-testid="portal-switch">{others.map((c) => <option key={c.participant_id} value={c.participant_id}>{`${c.name} · ${c.ref}`}</option>)}</select><ChevronDown className="h-3 w-3 absolute right-2 top-2.5 pointer-events-none" /></div>}
        <button type="button" onClick={logout} className="text-xs inline-flex items-center gap-1 text-slate-500 hover:text-slate-900" data-testid="portal-logout"><LogOut className="h-3.5 w-3.5" /> Quitter</button>
      </div>
      <>
        <section className="rounded-2xl border bg-[#fffaf3] p-5" data-testid="portal-overview">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">{participant.role === "client" ? "A sua obra" : `Obra · o seu capítulo:${participant.lot || "—"}`} · {chantier.ref}</p>
          <h1 className="text-2xl font-semibold mt-1" data-testid="portal-chantier-name">{chantier.name}</h1>
          {chantier.address && <p className="text-sm text-slate-600">{chantier.address}</p>}
          {progress_pct != null && <div className="mt-4"><div className="flex justify-between text-xs text-slate-600"><span>Avancement global</span><span className="font-semibold" data-testid="portal-progress">{progress_pct}%</span></div>
            <div className="mt-1 h-2.5 rounded-full bg-slate-200 overflow-hidden"><div className="h-full transition-all" style={{ width: `${progress_pct}%`, background: accent }} /></div></div>}
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            {company.phone && <a href={`tel:${company.phone}`} className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5" data-testid="portal-call"><Phone className="h-4 w-4" /> {company.phone}</a>}
            {company.email && <a href={`mailto:${company.email}`} className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5" data-testid="portal-mail"><Mail className="h-4 w-4" /> Escrever a {company.name}</a>}
          </div>
        </section>

        {tabs.length > 1 && (
          <nav className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-1 rounded-2xl border border-[#dfd0be] bg-[#fffaf3] p-2" aria-label="O seu espaço da obra" data-testid="portal-tabs">
            {tabs.map(([k, l, I]) => <button key={k} type="button" onClick={() => setTab(k)} aria-pressed={tab === k} data-testid={`portal-tab-${k}`}
              className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl px-2 py-3 min-h-12 text-sm font-medium transition-colors ${tab === k ? "text-white" : "text-slate-600 hover:bg-slate-100"}`} style={tab === k ? { background: accent } : undefined}><I className="h-4 w-4 shrink-0" /> {l}</button>)}
          </nav>
        )}

        {tab === "messages" && <PortalMessages portalApi={portalApi} chantierRef={ref} participantId={me?.participant?.participant_id} />}
        {tab === "issues" && <PortalIssues portalApi={portalApi} chantierRef={ref} canReport={!!participant.permissions?.report_issue} />}
        {tab === "documents" && canDocs && <PortalDocuments portalApi={portalApi} chantierRef={ref} accent={accent} />}
        {tab === "receptions" && canRecept && <PortalReceptions portalApi={portalApi} chantierRef={ref} accent={accent} />}

        {tab === "progress" && participant.permissions?.progress && <PortalPlanning portalApi={portalApi} chantierRef={ref} accent={accent} />}

        {tab === "progress" && participant.permissions?.progress && (
          <section className="rounded-2xl border bg-[#fffaf3] p-5" data-testid="portal-milestones">
            <h2 className="font-semibold">Etapas da obra</h2>
            {milestones.length === 0 ? <p className="text-sm text-slate-500 mt-2">As etapas serão apresentadas assim que a empresa as tiver planeado.</p> : (
              <ol className="mt-3 grid gap-3">
                {milestones.map((m) => { const [I, cls, label] = MS[m.status] || MS.planned; return (
                  <li key={m.milestone_id} className="flex gap-3" data-testid={`portal-milestone-${m.milestone_id}`}>
                    <I className={`h-5 w-5 mt-0.5 shrink-0 ${cls}`} />
                    <div className="min-w-0 flex-1"><p className="text-sm font-medium">{m.title}{m.lot ? <span className="text-slate-500"> · {m.lot}</span> : null}</p>
                      <p className="text-xs text-slate-500">{label} · {[m.planned_start, m.planned_end].filter(Boolean).join(" → ") || "datas a confirmar"}</p>
                      <div className="mt-1 h-1.5 rounded-full bg-slate-200 overflow-hidden"><div className="h-full" style={{ width: `${m.progress_pct}%`, background: accent }} /></div></div>
                    <span className="text-xs font-semibold w-10 text-right">{m.progress_pct}%</span>
                  </li>); })}
              </ol>)}
          </section>
        )}

        {tab === "progress" && participant.permissions?.progress && (
          <section className="rounded-2xl border bg-[#fffaf3] p-5" data-testid="portal-reports">
            <h2 className="font-semibold">Diário de obra</h2>
            {reports.length === 0 ? <p className="text-sm text-slate-500 mt-2">Nenhum relatório publicado por agora.</p> : (
              <div className="mt-3 divide-y">
                {reports.map((r) => (
                  <article key={r.report_id} className="py-3" data-testid={`portal-report-${r.report_id}`}>
                    <button type="button" onClick={() => setOpen(open === r.report_id ? null : r.report_id)} className="w-full text-left flex items-center gap-2">
                      <div className="min-w-0 flex-1"><p className="text-sm font-medium">{r.title || "Ata"}</p><p className="text-xs text-slate-500">{(r.created_at || "").slice(0, 10)}{r.photos?.length ? ` · ${r.photos.length} photo(s)` : ""}</p></div>
                      <ChevronDown className={`h-4 w-4 transition-transform ${open === r.report_id ? "rotate-180" : ""}`} />
                    </button>
                    {open === r.report_id && <div className="mt-2 grid gap-2">{r.notes && <p className="text-sm whitespace-pre-wrap">{r.notes}</p>}
                      {(r.notes || r.title) && <div><ListenButton text={`${r.title || "Ata"}. ${r.notes || ""}`} testId={`portal-listen-${r.report_id}`} request={(body) => axios.post(`${BASE}/api/speech/portal/tts`, body, { withCredentials: true, responseType: "blob" })} /></div>}
                      {r.photos?.length > 0 && <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">{r.photos.map((p) => <a key={p} href={photoUrl(p)} target="_blank" rel="noreferrer"><img src={photoUrl(p)} alt="" loading="lazy" className="h-24 w-full object-cover rounded-md border" /></a>)}</div>}</div>}
                  </article>))}
              </div>)}
          </section>
        )}

        {tab === "progress" && participant.permissions?.photos && photos.length > 0 && (
          <section className="rounded-2xl border bg-[#fffaf3] p-5" data-testid="portal-photos">
            <h2 className="font-semibold flex items-center gap-2"><Camera className="h-4 w-4" /> Photos ({photos.length})</h2>
            <div className="mt-3 grid grid-cols-3 sm:grid-cols-5 gap-2">{photos.slice(0, 40).map((p, i) => <a key={i} href={photoUrl(p.path)} target="_blank" rel="noreferrer" title={p.title || ""}><img src={photoUrl(p.path)} alt={p.title || "Fotografia de obra"} loading="lazy" className="h-24 w-full object-cover rounded-md border" /></a>)}</div>
          </section>
        )}
        <p className="text-[11px] text-slate-400 text-center">Vê apenas esta obra, com os elementos que {company.name || "l'entreprise"} escolheu partilhar.</p>
      </>
    </Frame>
  );
}
