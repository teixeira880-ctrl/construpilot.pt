import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, HardHat, User, MapPin, Pencil, Trash2, FileText, Ruler, Layers, Wrench, Camera, Plus, ExternalLink, Link2, AlertTriangle, Bot, GitCompareArrows, CalendarRange } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api, eur } from "@/lib/api";
import { useConfirm } from "@/components/ConfirmProvider";
import { ChantierFormDialog, CHANTIER_STATUS } from "@/components/chantiers/ChantierFormDialog";
import { ShareParticipantsPanel, MilestonesPanel, PublishToggle } from "@/components/chantiers/SharePanels";
import { ChantierMessagesPanel } from "@/components/portal/Messaging";
import { ChantierIssuesPanel } from "@/components/portal/Issues";
import { ReceptionPanel } from "@/components/chantiers/ReceptionPanel";
import { PhotoCompareDialog } from "@/components/chantiers/PhotoCompareDialog";
import { ChantierPilot } from "@/components/chantiers/ChantierPilot";
import { ChantierCostsPanel } from "@/components/chantiers/ChantierCostsPanel";

const FILE = process.env.REACT_APP_BACKEND_URL + "/api/site/file?path=";
const DOC_STATUS = { draft: "Brouillon", sent: "Enviado", signed: "Assinado", refused: "Recusado", paid: "Paga", overdue: "En retard", partial: "Partiel", cancelled: "Anulado" };
const JOB_STATUS = { done: "Concluída", needs_review: "A verificar", partial: "Partielle", failed: "Falha", running: "En cours", queued: "En attente" };
const date = (d) => (d || "").slice(0, 10);

const Section = ({ icon: Icon, title, count, action, children, testId }) => (
  <section className="surface" data-testid={testId}>
    <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
      <Icon className="h-4 w-4 text-primary" /><p className="font-display font-bold text-sm">{title}</p>
      <Badge variant="outline" className="rounded-sm">{count}</Badge>
      <div className="ms-auto flex gap-1">{action}</div>
    </div>
    <div className="divide-y divide-border">{children}</div>
  </section>
);
const Empty = ({ children }) => <p className="px-4 py-4 text-sm text-muted-foreground">{children}</p>;
const Row = ({ title, sub, right, onOpen, testId }) => (
  <div className="flex items-center gap-3 px-4 py-2.5" data-testid={testId}>
    <div className="min-w-0 flex-1"><p className="text-sm font-medium truncate">{title}</p><p className="text-[11px] text-muted-foreground truncate">{sub}</p></div>
    {right}
    {onOpen && <Button size="icon" variant="ghost" className="h-7 w-7" title="Ouvrir" onClick={onOpen}><ExternalLink className="h-3.5 w-3.5" /></Button>}
  </div>
);

function AttachDialog({ open, onOpenChange, chantierId, onDone }) {
  const [docs, setDocs] = useState([]);
  const [plans, setPlans] = useState([]);
  const [projects, setProjects] = useState([]);
  const [orders, setOrders] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    api.get("/documents").then(({ data }) => setDocs((data.documents || []).filter((d) => !d.chantier_id))).catch(() => {});
    api.get("/projects").then(({ data }) => setProjects((Array.isArray(data) ? data : []).filter(p => !p.chantier_id))).catch(() => setProjects([]));
    api.get("/pro/appro/orders").then(({ data }) => setOrders((data.items || []).filter(o => !o.chantier_id))).catch(() => setOrders([]));
    api.get("/takeoffs").then(({ data }) => setPlans((data.plans || []).filter((p) => !p.chantier_id))).catch(() => {});
  }, [open]);
  const attach = async (kind, ref_id) => {
    setBusy(true);
    try { await api.post(`/chantiers/${chantierId}/attach`, { kind, ref_id }); toast.success("Associado ao processo"); onDone(); onOpenChange(false); }
    catch (e) { toast.error(e?.response?.data?.detail || "Associação impossível"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="chantier-attach-dialog">
        <DialogHeader><DialogTitle>Associar um elemento existente</DialogTitle><DialogDescription>Plantas, documentos, encomendas e projetos de terreno já criados, ainda não ligados a um processo.</DialogDescription></DialogHeader>
        <div className="grid gap-4 max-h-[60vh] overflow-y-auto">
          <div><p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Orçamentos e faturas</p>
            {docs.length === 0 ? <p className="text-sm text-muted-foreground">Nenhum documento livre.</p> : docs.slice(0, 40).map((d) => (
              <button key={d.doc_id} type="button" disabled={busy} onClick={() => attach("document", d.doc_id)} className="w-full text-left text-sm px-3 py-2 rounded-md hover:bg-muted flex justify-between gap-2" data-testid={`attach-doc-${d.doc_id}`}>
                <span className="truncate">{d.title || d.number || d.doc_id}</span><span className="text-muted-foreground shrink-0">{date(d.created_at)}</span></button>))}
          </div>
          {[["hr_project", "Projets terrain / pointages", projects, "project_id"], ["purchase", "Commandes d’achat", orders, "order_id"]].map(([kind, label, items, key]) => <div key={kind}><p className="text-xs font-semibold uppercase text-muted-foreground mb-1">{label}</p>{!items.length ? <p className="text-sm text-muted-foreground">Nenhum elemento livre.</p> : items.slice(0, 100).map(item => <button key={item[key]} disabled={busy} type="button" className="w-full text-left text-sm px-3 py-2 rounded-md hover:bg-muted" onClick={() => attach(kind, item[key])}>{item.name || item.project || item[key]}</button>)}</div>)}
          <div><p className="text-xs font-semibold uppercase text-muted-foreground mb-1">Plans</p>
            {plans.length === 0 ? <p className="text-sm text-muted-foreground">Nenhuma planta livre.</p> : plans.slice(0, 40).map((p) => (
              <button key={p.plan_id} type="button" disabled={busy} onClick={() => attach("plan", p.plan_id)} className="w-full text-left text-sm px-3 py-2 rounded-md hover:bg-muted flex justify-between gap-2" data-testid={`attach-plan-${p.plan_id}`}>
                <span className="truncate">{p.filename || p.plan_id}</span><span className="text-muted-foreground shrink-0">{date(p.created_at)}</span></button>))}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function ChantierDetail() {
  const { chantierId } = useParams();
  return <ChantierDetailContent key={chantierId} />;
}

function ChantierDetailContent() {
  const { chantierId } = useParams();
  const nav = useNavigate();
  const confirm = useConfirm();
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [edit, setEdit] = useState(false);
  const [attach, setAttach] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [params, setParams] = useSearchParams();
  const requestedTab = params.get("tab");
  const tab = ["documents", "budget", "exchanges", "reception"].includes(requestedTab) ? requestedTab : ["messages", "issues"].includes(requestedTab) ? "exchanges" : "overview";
  const tabs = [["overview", "Vue d’ensemble"], ["documents", "Plans & documents"], ["budget", "Budget & achats"], ["exchanges", "Conversas"], ["reception", "Receção"]];
  const selectTab = key => { const next = new URLSearchParams(params); next.set("tab", key); setParams(next); };
  const [inbox, setInbox] = useState({ unread: {}, open_issues: 0, new_issues: 0 });

  const load = useCallback(() => api.get(`/chantiers/${chantierId}`).then(({ data }) => { setData(data); setError(false); }).catch(() => setError(true)), [chantierId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { const f = () => api.get(`/chantiers/${chantierId}/inbox`).then(({ data }) => setInbox(data)).catch(() => {}); f(); const id = setInterval(f, 15000); return () => clearInterval(id); }, [chantierId]);

  const remove = async () => {
    if (!(await confirm({ title: "Eliminar este processo de obra?", description: "Os orçamentos, plantas e análises não são eliminados: serão simplesmente desligados do processo." }))) return;
    try { await api.delete(`/chantiers/${chantierId}`); toast.success("Processo eliminado"); nav("/chantiers"); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  if (error) return <div className="surface p-8 text-center text-sm" data-testid="chantier-detail-error">Dossier introuvable. <Link to="/chantiers" className="text-primary underline">Voltar às obras</Link></div>;
  if (!data) return <div className="text-sm text-muted-foreground p-6">A carregar o processo…</div>;

  const c = data;
  const ctx = `?chantier=${chantierId}`;
  const quotes = c.documents.filter((d) => d.doc_type === "quote");
  const invoices = c.documents.filter((d) => d.doc_type !== "quote");
  const actions = [
    { to: `/devis-editeur${ctx}`, icon: FileText, label: "Novo orçamento", test: "quote" },
    { to: `/plan${ctx}`, icon: Ruler, label: "Importar uma planta", test: "plan" },
    { to: `/plans-pro${ctx}`, icon: Layers, label: "Análise de planta Pro", test: "plans-pro" },
    { to: `/btp-solver${ctx}`, icon: Wrench, label: "Diagnosticar uma patologia", test: "solver" },
    { to: `/suivi-chantier${ctx}`, icon: Camera, label: "Relatório / fotografias", test: "site" },
    { to: `/planning${ctx}`, icon: CalendarRange, label: "Planning (Gantt)", test: "planning" },
    { to: `/assistant${ctx}`, icon: Bot, label: "Perguntar ao assistente", test: "assistant" },
  ];

  return (
    <div className="grid grid-cols-1 min-w-0 gap-6" data-testid="chantier-detail-page">
      <Link to="/chantiers" className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 w-fit" data-testid="chantier-back"><ArrowLeft className="h-3 w-3" /> Todas as obras</Link>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 max-w-full">
          <div className="h-12 w-12 rounded-xl bg-primary/10 text-primary grid place-items-center shrink-0"><HardHat className="h-6 w-6" /></div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-2xl font-bold tracking-tight break-words" data-testid="chantier-detail-name">{c.name}</h1>
              <Badge variant="outline" className="rounded-sm" data-testid="chantier-detail-status">{CHANTIER_STATUS[c.status] || c.status}</Badge>
            </div>
            <p className="text-sm text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 mt-1">
              {c.client ? <Link to={`/clients/${c.client.client_id}`} className="inline-flex items-center gap-1 hover:text-primary" data-testid="chantier-detail-client"><User className="h-3.5 w-3.5" /> {c.client_name}{c.client.phone ? ` · ${c.client.phone}` : ""}</Link>
                : <button type="button" onClick={() => setEdit(true)} className="inline-flex items-center gap-1 text-amber-700" data-testid="chantier-detail-no-client"><AlertTriangle className="h-3.5 w-3.5" /> Nenhum cliente — associar</button>}
              {(c.address || c.city) && <span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {[c.address, c.postal_code, c.city].filter(Boolean).join(" ")}</span>}
            </p>
            {c.notes && <p className="text-sm mt-2 whitespace-pre-wrap" data-testid="chantier-detail-notes">{c.notes}</p>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2 max-w-full">
          <Button variant="outline" className="gap-2" onClick={() => setAttach(true)} data-testid="chantier-attach-btn"><Link2 className="h-4 w-4" /> Rattacher</Button>
          <Button variant="outline" className="gap-2" onClick={() => setEdit(true)} data-testid="chantier-edit-btn"><Pencil className="h-4 w-4" /> Editar</Button>
          <Button variant="ghost" size="icon" onClick={remove} title="Eliminar" data-testid="chantier-delete-btn"><Trash2 className="h-4 w-4" /></Button>
        </div>
      </header>

      <nav className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 rounded-2xl bg-secondary/40 p-2 border border-border/70" aria-label="Secções do processo" data-testid="chantier-tabs">
        {tabs.map(([key, label]) => <button key={key} type="button" aria-current={tab === key ? "page" : undefined} onClick={() => selectTab(key)} data-testid={`chantier-tab-${key}`} className={`min-h-11 rounded-xl px-3 py-2 text-sm font-medium transition-colors ${tab === key ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:bg-background"}`}>{label}{key === "exchanges" && inbox.new_issues > 0 ? ` (${inbox.new_issues})` : ""}</button>)}
      </nav>
      {tab === "overview" && <>
      <ChantierPilot chantierId={chantierId} />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="chantier-kpis">
        {[["Orçamento", c.kpis.quotes, false], ["Assinado c/ IVA", c.kpis.signed_ttc, true], ["Faturado c/ IVA", c.kpis.invoiced_ttc, true], ["Recebido", c.kpis.paid, true], ["Reservas em aberto", c.kpis.open_reserves, false]].map(([l, v, money]) => (
          <div key={l} className="surface p-4"><p className="text-[11px] uppercase tracking-wide text-muted-foreground">{l}</p><p className="font-display text-xl font-bold num">{money ? eur(v) : v}</p></div>))}
      </div>

      <MilestonesPanel chantierId={chantierId} milestones={c.milestones || []} onChanged={load} />
      <details className="surface p-4"><summary className="cursor-pointer text-sm font-semibold min-h-8">Criar ou adicionar ao processo</summary>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2" data-testid="chantier-actions">
        {actions.map((a) => <Link key={a.test} to={a.to} className="surface p-4 flex items-center gap-3 hover:border-primary/50 transition-colors" data-testid={`chantier-action-${a.test}`}><span className="h-9 w-9 rounded-xl bg-primary/10 text-primary grid place-items-center shrink-0"><a.icon className="h-4 w-4" /></span><span className="text-sm font-semibold leading-tight">{a.label}</span><Plus className="h-4 w-4 ms-auto text-muted-foreground" /></Link>)}
      </div>

      </details>
      </>}
      {tab === "exchanges" && <>
        <ShareParticipantsPanel chantierId={chantierId} />
        <div className="grid lg:grid-cols-2 gap-4" data-testid="chantier-exchanges">
          <ChantierMessagesPanel chantierId={chantierId} api={api} initialChannel={params.get("channel") || "client"} unread={inbox.unread} />
          <ChantierIssuesPanel chantierId={chantierId} api={api} />
        </div>
      </>}
      {tab === "documents" && <>
      <div className="grid lg:grid-cols-2 gap-4">
        <Section icon={FileText} title="Orçamento" count={quotes.length} testId="chantier-quotes" action={<Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => nav(`/devis-editeur${ctx}`)} data-testid="chantier-quotes-new"><Plus className="h-3.5 w-3.5" /> Orçamento</Button>}>
          {quotes.length === 0 ? <Empty>Nenhum orçamento. O cliente do processo será pré-preenchido.</Empty> : quotes.map((d) => <Row key={d.doc_id} testId={`chantier-doc-${d.doc_id}`} title={d.title || d.number || "Orçamento"} sub={`${d.number || "brouillon"} · ${date(d.created_at)}`} right={<><Badge variant="outline" className="rounded-sm text-[10px]">{DOC_STATUS[d.status] || d.status}</Badge><span className="num font-bold text-sm w-24 text-right">{eur(d.totals?.ttc)}</span></>} onOpen={() => nav(`/devis-editeur/${d.doc_id}`)} />)}
        </Section>
        <Section icon={FileText} title="Factures & avoirs" count={invoices.length} testId="chantier-invoices">
          {invoices.length === 0 ? <Empty>Nenhuma fatura para esta obra.</Empty> : invoices.map((d) => <Row key={d.doc_id} testId={`chantier-doc-${d.doc_id}`} title={d.title || d.number} sub={`${d.number || ""} · ${date(d.created_at)}${d.paid > 0 ? `· pago${eur(d.paid)}` : ""}`} right={<><Badge variant="outline" className="rounded-sm text-[10px]">{DOC_STATUS[d.status] || d.status}</Badge><span className="num font-bold text-sm w-24 text-right">{eur(d.totals?.ttc)}</span></>} onOpen={() => nav(`/devis-editeur/${d.doc_id}`)} />)}
        </Section>
        <Section icon={Ruler} title="Plantas e medições" count={c.plans.length} testId="chantier-plans" action={<Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => nav(`/plan${ctx}`)} data-testid="chantier-plans-new"><Plus className="h-3.5 w-3.5" /> Plan</Button>}>
          {c.plans.length === 0 ? <Empty>Nenhuma planta associada.</Empty> : c.plans.map((p) => <Row key={p.plan_id} testId={`chantier-plan-${p.plan_id}`} title={p.filename || p.plan_id} right={<Link className="text-xs text-primary underline min-h-10 flex items-center" to={`/analyse/${p.plan_id}`}>Fontes e revisões</Link>} sub={`${(p.kind || "").toUpperCase()} · ${p.page_count || 1} page(s) · ${date(p.created_at)}`} onOpen={() => nav(`/plan?open=${p.plan_id}`)} />)}
        </Section>
        <Section icon={Layers} title="Análises de plantas Pro" count={c.plans_pro.length} testId="chantier-plans-pro" action={<Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => nav(`/plans-pro${ctx}`)} data-testid="chantier-plans-pro-new"><Plus className="h-3.5 w-3.5" /> Analyse</Button>}>
          {c.plans_pro.length === 0 ? <Empty>Nenhuma análise Autodesk / visão IA.</Empty> : c.plans_pro.map((j) => <Row key={j.job_id} testId={`chantier-job-${j.job_id}`} title={j.filename} sub={date(j.created_at)} right={<Badge variant="outline" className="rounded-sm text-[10px]">{JOB_STATUS[j.status] || j.status}</Badge>} onOpen={() => nav(`/plans-pro?job=${j.job_id}`)} />)}
        </Section>
        <Section icon={Wrench} title="Diagnósticos (patologias)" count={c.diagnostics.length} testId="chantier-diagnostics" action={<Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => nav(`/btp-solver${ctx}`)} data-testid="chantier-diagnostics-new"><Plus className="h-3.5 w-3.5" /> Diagnostic</Button>}>
          {c.diagnostics.length === 0 ? <Empty>Nenhum diagnóstico.</Empty> : c.diagnostics.map((p) => <Row key={p.problem_id} testId={`chantier-problem-${p.problem_id}`} title={(p.description || "").slice(0, 90)} sub={[p.domain, p.urgency, date(p.created_at)].filter(Boolean).join(" · ")} right={<Badge variant="outline" className="rounded-sm text-[10px]">{p.status === "done" ? "Terminado" : p.status === "error" ? "Falha" : "En cours"}</Badge>} onOpen={() => nav(`/btp-solver?id=${p.problem_id}`)} />)}
        </Section>
        <Section icon={Camera} title="Relatórios e reservas" count={c.reports.length + c.reserves.length} testId="chantier-reports" action={<Button size="sm" variant="ghost" className="h-7 gap-1" onClick={() => nav(`/suivi-chantier${ctx}`)} data-testid="chantier-reports-new"><Plus className="h-3.5 w-3.5" /> Ata</Button>}>
          {c.reports.length + c.reserves.length === 0 ? <Empty>Nenhum relatório. Os relatórios cujo nome de obra corresponda são retomados automaticamente.</Empty> : <>
            {c.reports.map((r) => <Row key={r.report_id} testId={`chantier-report-${r.report_id}`} title={r.title || "Ata"} sub={`${date(r.created_at)} · ${(r.photos || []).length} photo(s)`} right={<PublishToggle chantierId={chantierId} report={r} onChanged={load} />} />)}
            {c.reserves.map((r) => <Row key={r.reserve_id} testId={`chantier-reserve-${r.reserve_id}`} title={`Reserva —${r.lot || "lot"} : ${r.description}`} sub={`${r.company || ""} ${date(r.created_at)}`} right={<Badge variant="outline" className="rounded-sm text-[10px]">{r.status || "ouverte"}</Badge>} />)}
          </>}
        </Section>
      </div>

      </>}
      {tab === "budget" && <ChantierCostsPanel chantierId={chantierId} />}
      {tab === "reception" && <ReceptionPanel chantierId={chantierId} />}


      {tab === "overview" && c.photos.length > 0 && (
        <section className="surface p-4" data-testid="chantier-photos">
          <div className="flex items-center gap-2 mb-3 flex-wrap">
            <p className="font-display font-bold text-sm flex items-center gap-2"><Camera className="h-4 w-4 text-primary" /> Fotografias da obra ({c.photos.length})</p>
            {c.photos.length >= 2 && (
              <Button size="sm" variant="outline" className="h-7 gap-1.5 ms-auto rounded-sm" onClick={() => setCompareOpen(true)} data-testid="chantier-photo-compare-btn">
                <GitCompareArrows className="h-3.5 w-3.5" /> Comparar antes/depois
              </Button>
            )}
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {c.photos.slice(0, 36).map((p, i) => <a key={i} href={FILE + encodeURIComponent(p.path)} target="_blank" rel="noreferrer" title={p.title || ""}><img src={FILE + encodeURIComponent(p.path)} alt={p.title || "Fotografia de obra"} loading="lazy" className="h-24 w-full object-cover rounded-md border" /></a>)}
          </div>
        </section>
      )}

      <PhotoCompareDialog open={compareOpen} onOpenChange={setCompareOpen} photos={c.photos} />

      <ChantierFormDialog open={edit} onOpenChange={setEdit} chantier={c} onSaved={load} />
      <AttachDialog open={attach} onOpenChange={setAttach} chantierId={chantierId} onDone={load} />
    </div>
  );
}
