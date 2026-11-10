import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, CheckCircle2, Circle, Download, Filter, Mail, Plus, RefreshCw, Settings, ShieldAlert, Users, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { CAPS, DEMOS, PAINS, catalog } from "@/connect/engine";

/**
 * ConstruPilot Commercial Hub — /admin/connect (apenas admins).
 * Oportunidades do Discovery Engine: funis, prioridade justificada, tarefas, notas, e-mails
 * individuais, dashboard com dados reais, exportação e RGPD.
 */
const PROFILE_PT = { client: "Cliente", investor: "Investidor", partner: "Parceiro" };
const PRIORITY_PT = { high: "Alta", medium: "Média", low: "Baixa" };
const PRIORITY_CLS = { high: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200", medium: "bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-200", low: "bg-muted text-muted-foreground" };
const NEXT_PT = { meeting: "Reunião", individual_demo: "Demonstração individual", pilot: "Piloto", report: "Resumo do diagnóstico", none: "—" };
const STAGE_PT = {
  new: "Novo", qualification_pending: "Qualificação pendente", qualified: "Qualificado", demo_requested: "Demonstração solicitada",
  demo_done: "Demonstração realizada", pilot_proposed: "Piloto proposto", pilot_running: "Piloto em curso", proposal_sent: "Proposta enviada",
  negotiation: "Negociação", won: "Cliente ganho", lost: "Perdido / sem interesse", nurture: "Nutrição futura",
  identity_check: "Identidade por verificar", qualification: "Qualificação", meeting_requested: "Reunião solicitada", first_meeting: "Primeira reunião",
  interest_confirmed: "Interesse confirmado", docs_authorized: "Documentação autorizada", due_diligence: "Due diligence", invested: "Investimento concluído",
  no_interest: "Sem interesse / adiado", meeting: "Reunião", evaluation: "Avaliação de colaboração", pilot_negotiation: "Piloto / negociação",
  agreement: "Acordo", active: "Parceria ativa", no_follow_up: "Sem seguimento",
};
const EMAIL_PT = { follow_up: "Follow-up individual", pilot_invite: "Convite para piloto", meeting_confirmation: "Confirmação de reunião (data real)", partner_meeting_invite: "Convite para reunião de parceria" };
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" }) : "—");
const painPT = (p) => (PAINS[p] ? PAINS[p].label.pt : p);
const toLocalInput = (iso) => (iso ? new Date(iso).toISOString().slice(0, 16) : "");

export default function AdminConnect() {
  const [tab, setTab] = useState("leads");
  return (
    <div className="mx-auto max-w-7xl px-4 py-6" data-testid="admin-connect">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight">Commercial Hub</h1>
          <p className="text-sm text-muted-foreground">Oportunidades do Discovery Engine (/connect) — construpilot.pt</p>
        </div>
        <nav className="flex rounded-lg border border-border p-0.5" aria-label="Secções">
          {[["leads", Users, "Oportunidades"], ["dashboard", BarChart3, "Dashboard"], ["settings", Settings, "Definições"]].map(([id, Icon, label]) => (
            <button key={id} type="button" onClick={() => setTab(id)} aria-pressed={tab === id} data-testid={`hub-tab-${id}`}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm ${tab === id ? "bg-primary text-primary-foreground" : ""}`}><Icon className="h-4 w-4" aria-hidden />{label}</button>
          ))}
        </nav>
      </div>
      <div className="mt-6">
        {tab === "leads" && <Leads />}
        {tab === "dashboard" && <Dashboard />}
        {tab === "settings" && <SettingsPanel />}
      </div>
    </div>
  );
}

function Leads() {
  const [f, setF] = useState({ profile: "", stage: "", priority: "", owner: "", source: "", q: "", overdue: false });
  const [data, setData] = useState({ items: [], total: 0, stages: {} });
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(null);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v));
      const { data: d } = await api.get("/connect/admin/leads", { params: { ...params, limit: 200 } });
      setData(d);
    } catch (e) { toast.error(e?.response?.data?.detail || "Erro ao carregar"); }
    setLoading(false);
  }, [f]);
  useEffect(() => { const h = setTimeout(load, 200); return () => clearTimeout(h); }, [load]);
  const stageOptions = f.profile ? data.stages[f.profile] || [] : [...new Set(Object.values(data.stages || {}).flat())];
  const sel = "rounded-md border border-input bg-background px-2 py-1.5 text-sm";
  const exportCsv = () => {
    const base = `${process.env.REACT_APP_BACKEND_URL || ""}/api/connect/admin/export.csv${f.profile ? `?profile=${f.profile}` : ""}`;
    window.open(base, "_blank", "noopener");
  };
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3">
        <Filter className="h-4 w-4 text-muted-foreground" aria-hidden />
        <input placeholder="Pesquisar nome, empresa, e-mail" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} className={`${sel} w-56`} data-testid="hub-search" aria-label="Pesquisar" />
        <select className={sel} value={f.profile} onChange={(e) => setF({ ...f, profile: e.target.value, stage: "" })} aria-label="Perfil" data-testid="hub-filter-profile">
          <option value="">Todos os perfis</option>{Object.entries(PROFILE_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <select className={sel} value={f.stage} onChange={(e) => setF({ ...f, stage: e.target.value })} aria-label="Etapa">
          <option value="">Todas as etapas</option>{stageOptions.map((s) => <option key={s} value={s}>{STAGE_PT[s] || s}</option>)}
        </select>
        <select className={sel} value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })} aria-label="Prioridade">
          <option value="">Todas as prioridades</option>{Object.entries(PRIORITY_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input placeholder="Responsável" value={f.owner} onChange={(e) => setF({ ...f, owner: e.target.value })} className={`${sel} w-36`} aria-label="Responsável" />
        <input placeholder="Origem (ex.: websummit2026)" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} className={`${sel} w-48`} aria-label="Origem" />
        <label className="inline-flex items-center gap-1.5 text-sm"><input type="checkbox" checked={f.overdue} onChange={(e) => setF({ ...f, overdue: e.target.checked })} />Tarefas em atraso</label>
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={load} className="rounded-md border border-border p-1.5" aria-label="Atualizar"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /></button>
          <button type="button" onClick={exportCsv} className="inline-flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm" data-testid="hub-export"><Download className="h-4 w-4" aria-hidden />CSV</button>
        </div>
      </div>
      <p className="mt-3 text-sm text-muted-foreground">{data.total} oportunidade(s)</p>
      <div className="mt-2 overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm" data-testid="hub-table">
          <thead className="bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
            <tr><th className="p-2.5">Data</th><th className="p-2.5">Contacto</th><th className="p-2.5">Perfil</th><th className="p-2.5">Prioridade</th><th className="p-2.5">Etapa</th><th className="p-2.5">Pedido</th><th className="p-2.5">Responsável</th><th className="p-2.5">Próxima ação</th><th className="p-2.5">Origem</th></tr>
          </thead>
          <tbody>
            {data.items.map((l) => (
              <tr key={l.lead_id} onClick={() => setOpen(l.lead_id)} className="cursor-pointer border-t border-border hover:bg-accent/40" data-testid={`hub-row-${l.lead_id}`}>
                <td className="p-2.5 whitespace-nowrap">{fmtDate(l.created_at)}</td>
                <td className="p-2.5"><div className="font-medium">{l.name}</div><div className="text-xs text-muted-foreground">{l.company || l.email}</div></td>
                <td className="p-2.5">{PROFILE_PT[l.profile]}</td>
                <td className="p-2.5"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PRIORITY_CLS[l.priority]}`}>{PRIORITY_PT[l.priority]} · {l.score}</span></td>
                <td className="p-2.5">{STAGE_PT[l.stage] || l.stage}</td>
                <td className="p-2.5">{NEXT_PT[l.next_step] || "—"}</td>
                <td className="p-2.5">{l.owner || "—"}</td>
                <td className="p-2.5"><div className={l.overdue ? "text-destructive font-medium" : ""}>{l.next_action || "—"}</div><div className="text-xs text-muted-foreground">{fmtDate(l.next_contact_at)}</div></td>
                <td className="p-2.5 text-xs">{l.source}</td>
              </tr>
            ))}
            {!data.items.length && <tr><td colSpan={9} className="p-6 text-center text-muted-foreground">Ainda não há oportunidades com estes filtros.</td></tr>}
          </tbody>
        </table>
      </div>
      {open && <LeadDrawer leadId={open} onClose={() => { setOpen(null); load(); }} />}
    </div>
  );
}

function LeadDrawer({ leadId, onClose }) {
  const [lead, setLead] = useState(null);
  const [note, setNote] = useState({ text: "", type: "note" });
  const [task, setTask] = useState({ title: "", due_at: "" });
  const [mail, setMail] = useState({ template: "follow_up", note: "", when: "" });
  const load = useCallback(async () => {
    try { const { data } = await api.get(`/connect/admin/leads/${leadId}`); setLead(data); } catch (e) { toast.error("Erro ao abrir"); }
  }, [leadId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const k = (e) => e.key === "Escape" && onClose(); window.addEventListener("keydown", k); return () => window.removeEventListener("keydown", k); }, [onClose]);
  if (!lead) return null;
  const patch = async (body) => {
    try { const { data } = await api.patch(`/connect/admin/leads/${leadId}`, body); setLead({ ...data, stages: lead.stages }); toast.success("Guardado"); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erro"); }
  };
  const c = lead.contact || {};
  const rec = lead.recommendation || {};
  const a = lead.answers || {};
  const input = "w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm";
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" role="dialog" aria-modal="true" aria-label={`Oportunidade ${c.name}`} onClick={onClose}>
      <aside className="h-full w-full max-w-2xl overflow-y-auto bg-background p-5 shadow-xl" onClick={(e) => e.stopPropagation()} data-testid="hub-drawer">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{PROFILE_PT[lead.profile]} · {lead.lead_id}</p>
            <h2 className="font-display text-2xl font-semibold">{c.name}</h2>
            <p className="text-sm">{c.company} {c.company && "·"} <a className="underline" href={`mailto:${c.email}`}>{c.email}</a> {c.phone && `· ${c.phone}`}</p>
            <p className="text-xs text-muted-foreground">País: {c.country || "—"} · Idioma: {lead.lang} · Canal: {c.channel} · Origem: {lead.source}{lead.utm?.campaign ? ` / ${lead.utm.campaign}` : ""}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Fechar" className="rounded-md p-1.5 hover:bg-muted"><X className="h-5 w-5" /></button>
        </div>

        <section className="mt-4 rounded-xl border border-border p-4">
          <p className="text-sm"><span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${PRIORITY_CLS[lead.priority_override || lead.priority]}`}>Prioridade {PRIORITY_PT[lead.priority_override || lead.priority]} · {lead.score}/100</span></p>
          <p className="mt-2 text-sm" data-testid="hub-justification"><b>Justificação:</b> {lead.score_detail?.explanation || "—"}</p>
          <p className="mt-1 text-xs text-muted-foreground">Componentes: {Object.entries(lead.score_detail?.components || {}).map(([k, v]) => `${k} ${v}`).join(" · ")} — o score não é uma probabilidade de compra.</p>
          <p className="mt-2 text-sm"><b>Pedido:</b> {NEXT_PT[lead.next_step]} · <b>Marketing:</b> {lead.marketing_consent ? "consentido" : "não"}</p>
        </section>

        <section className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="text-sm">Etapa
            <select className={input} value={lead.stage} onChange={(e) => patch({ stage: e.target.value })} data-testid="hub-stage">
              {(lead.stages || []).map((s) => <option key={s} value={s}>{STAGE_PT[s] || s}</option>)}
            </select></label>
          <label className="text-sm">Responsável
            <input className={input} defaultValue={lead.owner} onBlur={(e) => e.target.value !== lead.owner && patch({ owner: e.target.value })} data-testid="hub-owner" /></label>
          <label className="text-sm">Próxima ação
            <input className={input} defaultValue={lead.next_action} onBlur={(e) => e.target.value !== lead.next_action && patch({ next_action: e.target.value })} /></label>
          <label className="text-sm">Próximo contacto
            <input type="datetime-local" className={input} defaultValue={toLocalInput(lead.next_contact_at)} onBlur={(e) => patch({ next_contact_at: e.target.value ? new Date(e.target.value).toISOString() : "" })} /></label>
          <label className="text-sm">Interesse comercial
            <input className={input} defaultValue={lead.interest} onBlur={(e) => e.target.value !== lead.interest && patch({ interest: e.target.value })} /></label>
          <label className="text-sm">Motivo de perda
            <input className={input} defaultValue={lead.loss_reason} onBlur={(e) => e.target.value !== lead.loss_reason && patch({ loss_reason: e.target.value })} /></label>
          <label className="text-sm">Prioridade manual
            <select className={input} value={lead.priority_override || ""} onChange={(e) => patch({ priority_override: e.target.value })}>
              <option value="">Automática ({PRIORITY_PT[lead.priority]})</option>{Object.entries(PRIORITY_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select></label>
        </section>

        <section className="mt-5">
          <h3 className="font-semibold">Diagnóstico</h3>
          {lead.profile === "client" ? (
            <ul className="mt-2 space-y-1 text-sm">
              <li><b>Atividade:</b> {catalog.activities.find((x) => x.id === a.activity)?.label.pt || "—"}</li>
              <li><b>Volume:</b> {Object.values(a.volume || {}).join(", ") || "—"} · <b>Urgência:</b> {a.urgency} · <b>Decisão:</b> {a.decision}</li>
              <li><b>Dores:</b> {(lead.pains || []).map(painPT).join(" · ")}</li>
              {a.other_text && <li><b>Texto livre (rever):</b> {a.other_text}</li>}
              <li><b>Respostas detalhadas:</b> {Object.entries(a.deep || {}).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join("/") : v}`).join(" · ") || "—"}</li>
              <li><b>Soluções sugeridas:</b> {(lead.solutions || []).map((s) => CAPS[s]?.name.pt || s).join(" · ")}</li>
              <li><b>Demonstração sugerida:</b> {DEMOS[rec.demo]?.title.pt || "—"} · <b>Vistas:</b> {(lead.demos_viewed || []).map((d) => DEMOS[d]?.title.pt || d).join(", ") || "nenhuma"}</li>
            </ul>
          ) : (
            <pre className="mt-2 whitespace-pre-wrap rounded-lg bg-muted/50 p-3 text-xs">{JSON.stringify(a, null, 2)}</pre>
          )}
        </section>

        <section className="mt-5">
          <h3 className="font-semibold">Tarefas</h3>
          <ul className="mt-2 space-y-1.5">
            {(lead.tasks || []).map((tk) => (
              <li key={tk.task_id} className="flex items-start gap-2 text-sm">
                <button type="button" aria-label={tk.done ? "Reabrir tarefa" : "Concluir tarefa"} onClick={async () => { await api.patch(`/connect/admin/leads/${leadId}/tasks/${tk.task_id}`, { done: !tk.done }); load(); }}>
                  {tk.done ? <CheckCircle2 className="h-4 w-4 text-primary" /> : <Circle className="h-4 w-4" />}
                </button>
                <span className={tk.done ? "line-through text-muted-foreground" : ""}>{tk.title}<span className="block text-xs text-muted-foreground">até {fmtDate(tk.due_at)}{tk.auto ? " · automática" : ""}</span></span>
              </li>
            ))}
          </ul>
          <form className="mt-2 flex flex-wrap gap-2" onSubmit={async (e) => { e.preventDefault(); if (!task.title.trim()) return; await api.post(`/connect/admin/leads/${leadId}/tasks`, { title: task.title, due_at: task.due_at ? new Date(task.due_at).toISOString() : null }); setTask({ title: "", due_at: "" }); load(); }}>
            <input className={`${input} flex-1 min-w-[180px]`} placeholder="Nova tarefa" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} />
            <input type="datetime-local" className={`${input} w-52`} value={task.due_at} onChange={(e) => setTask({ ...task, due_at: e.target.value })} aria-label="Prazo" />
            <button type="submit" className="inline-flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground"><Plus className="h-4 w-4" aria-hidden />Adicionar</button>
          </form>
        </section>

        <section className="mt-5">
          <h3 className="font-semibold">Registar interação</h3>
          <form className="mt-2 space-y-2" onSubmit={async (e) => { e.preventDefault(); if (!note.text.trim()) return; await api.post(`/connect/admin/leads/${leadId}/notes`, note); setNote({ text: "", type: "note" }); load(); }}>
            <select className={input} value={note.type} onChange={(e) => setNote({ ...note, type: e.target.value })} aria-label="Tipo">
              <option value="note">Nota</option><option value="call">Chamada</option><option value="email">E-mail (fora da plataforma)</option><option value="meeting">Reunião</option><option value="demo">Demonstração</option>
            </select>
            <textarea className={`${input} min-h-[70px]`} value={note.text} onChange={(e) => setNote({ ...note, text: e.target.value })} placeholder="O que aconteceu?" data-testid="hub-note" />
            <button type="submit" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground">Guardar</button>
          </form>
        </section>

        {!lead.anonymized && (
          <section className="mt-5 rounded-xl border border-border p-4">
            <h3 className="flex items-center gap-1.5 font-semibold"><Mail className="h-4 w-4" aria-hidden />Enviar e-mail individual ({(lead.lang || "pt").toUpperCase()})</h3>
            <p className="text-xs text-muted-foreground">Um envio de cada vez, para este contacto. Documentos confidenciais nunca são anexados.</p>
            <div className="mt-2 space-y-2">
              <select className={input} value={mail.template} onChange={(e) => setMail({ ...mail, template: e.target.value })} aria-label="Modelo">
                {Object.entries(EMAIL_PT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {mail.template === "meeting_confirmation" && <input className={input} placeholder="Data e hora reais combinadas (ex.: 12/11/2026 15:00, stand A-12)" value={mail.when} onChange={(e) => setMail({ ...mail, when: e.target.value })} />}
              <textarea className={`${input} min-h-[70px]`} placeholder="Mensagem personalizada" value={mail.note} onChange={(e) => setMail({ ...mail, note: e.target.value })} />
              <button type="button" className="rounded-md bg-primary px-3 py-1.5 text-sm text-primary-foreground" data-testid="hub-send-email"
                onClick={async () => {
                  if (!window.confirm(`Enviar «${EMAIL_PT[mail.template]}» para ${c.email}?`)) return;
                  try { const { data } = await api.post(`/connect/admin/leads/${leadId}/email`, mail); data.ok ? toast.success("E-mail enviado") : toast.error("Não enviado (duplicado ou falha)"); load(); }
                  catch (e) { toast.error(e?.response?.data?.detail || "Erro"); }
                }}>Enviar</button>
            </div>
          </section>
        )}

        <section className="mt-5">
          <h3 className="font-semibold">Histórico</h3>
          <ol className="mt-2 space-y-2 border-l border-border pl-4">
            {[...(lead.activities || [])].reverse().map((ac) => (
              <li key={ac.activity_id} className="text-sm"><span className="text-xs text-muted-foreground">{fmtDate(ac.at)} · {ac.type} · {ac.author}</span><br />{ac.text}</li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted-foreground">Consentimentos: {(lead.consents || []).map((x) => `${fmtDate(x.at)} (${x.origin}, marketing: ${x.marketing ? "sim" : "não"}, texto ${x.text_version})`).join(" · ")}</p>
        </section>

        <section className="mt-6 flex flex-wrap gap-2 border-t border-border pt-4">
          <a className="rounded-md border border-border px-3 py-1.5 text-sm" href={`${process.env.REACT_APP_BACKEND_URL || ""}/api/connect/admin/leads/${leadId}/personal-data`} target="_blank" rel="noreferrer">Exportar dados da pessoa (JSON)</a>
          {!lead.anonymized && (
            <button type="button" className="inline-flex items-center gap-1.5 rounded-md border border-destructive/50 px-3 py-1.5 text-sm text-destructive"
              onClick={async () => { if (!window.confirm("Eliminar os dados pessoais desta oportunidade? A ação é irreversível.")) return; await api.post(`/connect/admin/leads/${leadId}/anonymize`, { confirm: true }); load(); }}>
              <ShieldAlert className="h-4 w-4" aria-hidden />Apagar dados pessoais (RGPD)</button>
          )}
        </section>
      </aside>
    </div>
  );
}

function Bars({ data, label = (k) => k }) {
  const entries = Object.entries(data || {});
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) return <p className="text-sm text-muted-foreground">Sem dados ainda.</p>;
  return (
    <ul className="space-y-1.5">
      {entries.map(([k, v]) => (
        <li key={k} className="grid grid-cols-[minmax(0,12rem)_1fr_2.5rem] items-center gap-2 text-sm">
          <span className="truncate" title={label(k)}>{label(k)}</span>
          <span className="h-2.5 rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="text-right font-mono">{v}</span>
        </li>
      ))}
    </ul>
  );
}

function Card({ title, children }) {
  return <section className="rounded-xl border border-border bg-card p-4"><h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">{title}</h3>{children}</section>;
}

function Dashboard() {
  const [days, setDays] = useState(90);
  const [d, setD] = useState(null);
  useEffect(() => { api.get("/connect/admin/dashboard", { params: { days } }).then(({ data }) => setD(data)).catch(() => toast.error("Erro")); }, [days]);
  if (!d) return <p className="text-muted-foreground">A carregar…</p>;
  const kpis = [
    ["Diagnósticos iniciados", d.diagnosis.started], ["Concluídos", d.diagnosis.completed],
    ["Taxa de conclusão", d.diagnosis.completion_rate == null ? "—" : `${d.diagnosis.completion_rate} %`], ["Oportunidades", d.diagnosis.converted_to_lead],
    ["Demos iniciadas / concluídas", `${d.demos.started} / ${d.demos.completed}`], ["Pedidos de reunião/demo", d.requests.meeting + d.requests.individual_demo],
    ["1.ª resposta (mediana)", d.first_response_hours.median == null ? "—" : `${d.first_response_hours.median} h`], ["Sem seguimento", d.without_follow_up],
    ["Pilotos e propostas", d.pilots_and_proposals], ["Ganhos", d.won],
  ];
  return (
    <div data-testid="hub-dashboard">
      <div className="flex items-center gap-2 text-sm">Período:
        {[7, 30, 90, 365].map((n) => <button key={n} type="button" onClick={() => setDays(n)} className={`rounded-md px-2 py-1 ${days === n ? "bg-primary text-primary-foreground" : "border border-border"}`}>{n} d</button>)}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-5">
        {kpis.map(([k, v]) => <div key={k} className="rounded-xl border border-border bg-card p-3"><p className="text-xs text-muted-foreground">{k}</p><p className="mt-1 font-display text-2xl font-semibold">{v}</p></div>)}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card title="Oportunidades por origem"><Bars data={d.leads_by_source} /></Card>
        <Card title="Oportunidades por tipo"><Bars data={d.leads_by_profile} label={(k) => PROFILE_PT[k] || k} /></Card>
        <Card title="Dores mais frequentes"><Bars data={d.top_pains} label={painPT} /></Card>
        <Card title="Segmentos (atividade)"><Bars data={d.segments} label={(k) => catalog.activities.find((a) => a.id === k)?.label.pt || k} /></Card>
        <Card title="Funil de clientes"><Bars data={d.funnel.client} label={(k) => STAGE_PT[k] || k} /></Card>
        <Card title="Investidores por fase"><Bars data={d.investors_by_stage} label={(k) => STAGE_PT[k] || k} /></Card>
        <Card title="Funil de parceiros"><Bars data={d.funnel.partner} label={(k) => STAGE_PT[k] || k} /></Card>
        <Card title="Diagnósticos por origem"><Bars data={d.sessions_by_source} /></Card>
      </div>
      <p className="mt-4 text-xs text-muted-foreground">{d.note}</p>
    </div>
  );
}

function SettingsPanel() {
  const [s, setS] = useState(null);
  const [draft, setDraft] = useState(null);
  useEffect(() => { api.get("/connect/admin/settings").then(({ data }) => { setS(data); setDraft({ owners: data.owners, sla_hours: data.sla_hours, retention_days: data.retention_days, thresholds: data.scoring_effective.thresholds }); }); }, []);
  const save = async () => {
    try {
      const { data } = await api.put("/connect/admin/settings", { owners: draft.owners, sla_hours: draft.sla_hours, retention_days: Number(draft.retention_days), scoring: { ...(s.scoring || {}), thresholds: { high: Number(draft.thresholds.high), medium: Number(draft.thresholds.medium) } } });
      setS(data); toast.success("Definições guardadas");
    } catch (e) { toast.error(e?.response?.data?.detail || "Erro"); }
  };
  const weights = useMemo(() => (s ? s.scoring_effective : null), [s]);
  if (!draft) return <p className="text-muted-foreground">A carregar…</p>;
  const input = "w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm";
  return (
    <div className="grid gap-4 lg:grid-cols-2" data-testid="hub-settings">
      <Card title="Responsáveis por perfil">
        {Object.keys(PROFILE_PT).map((p) => (
          <div key={p} className="mb-3 grid grid-cols-2 gap-2">
            <label className="text-sm">{PROFILE_PT[p]} — nome<input className={input} value={draft.owners[p]?.name || ""} onChange={(e) => setDraft({ ...draft, owners: { ...draft.owners, [p]: { ...draft.owners[p], name: e.target.value } } })} /></label>
            <label className="text-sm">E-mail para alertas<input className={input} value={draft.owners[p]?.email || ""} onChange={(e) => setDraft({ ...draft, owners: { ...draft.owners, [p]: { ...draft.owners[p], email: e.target.value } } })} /></label>
          </div>
        ))}
      </Card>
      <Card title="Prazos de resposta (horas úteis, seg–sex 9h–18h)">
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(draft.sla_hours).map(([k, v]) => (
            <label key={k} className="text-sm">{{ high: "Prioridade alta", medium: "Prioridade média", low: "Prioridade baixa", investor: "Investidor", partner: "Parceiro" }[k] || k}
              <input type="number" min="1" className={input} value={v} onChange={(e) => setDraft({ ...draft, sla_hours: { ...draft.sla_hours, [k]: Number(e.target.value) } })} /></label>
          ))}
        </div>
      </Card>
      <Card title="Limiares de prioridade (score 0–100)">
        <div className="grid grid-cols-2 gap-2">
          <label className="text-sm">Alta a partir de<input type="number" className={input} value={draft.thresholds.high} onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, high: e.target.value } })} /></label>
          <label className="text-sm">Média a partir de<input type="number" className={input} value={draft.thresholds.medium} onChange={(e) => setDraft({ ...draft, thresholds: { ...draft.thresholds, medium: e.target.value } })} /></label>
        </div>
        <details className="mt-3 text-xs"><summary className="cursor-pointer">Pesos em vigor (regras transparentes)</summary><pre className="mt-2 max-h-64 overflow-auto rounded bg-muted/50 p-2">{JSON.stringify(weights, null, 2)}</pre></details>
        <p className="mt-2 text-xs text-muted-foreground">O score não usa país, idioma, nacionalidade nem atributos sensíveis, e nunca exclui oportunidades.</p>
      </Card>
      <Card title="Retenção de dados (RGPD)">
        <label className="text-sm">Anonimizar oportunidades fechadas sem interação há mais de (dias)
          <input type="number" min="30" max="3650" className={input} value={draft.retention_days} onChange={(e) => setDraft({ ...draft, retention_days: e.target.value })} /></label>
        <button type="button" className="mt-3 rounded-md border border-border px-3 py-1.5 text-sm" onClick={async () => {
          if (!window.confirm("Executar agora a anonimização das oportunidades fechadas fora do prazo?")) return;
          const { data } = await api.post("/connect/admin/retention/run"); toast.success(`${data.anonymized} anonimizada(s)`);
        }}>Aplicar retenção agora</button>
      </Card>
      <div className="lg:col-span-2"><button type="button" onClick={save} className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground" data-testid="hub-settings-save">Guardar definições</button></div>
    </div>
  );
}
