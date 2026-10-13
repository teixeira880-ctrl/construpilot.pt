import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Send, Eye, CheckCircle2, FileText, Copy, ExternalLink, RefreshCw, Mail,
  Download, FileDown, Star, Receipt, Trash2, Sparkles, PenLine, GraduationCap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { SectionTitle } from "@/components/Bits";
import { ImportDocumentsDialog } from "@/components/ImportDocumentsDialog";
import { useConfirm } from "@/components/ConfirmProvider";
import { RevenueChart } from "@/components/RevenueChart";
import { api, eur } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuoteCopy } from "@/components/assistant/quoteCopy";

const MONTHS_FR = ["janvier", "fevereiro", "mars", "avril", "mai", "juin",
  "juillet", "agosto", "septembre", "octobre", "novembre", "dezembro"];

export default function QuoteTracking() {
  const { user } = useAuth();
  const quoteText = useQuoteCopy();
  const [searchParams] = useSearchParams();
  const highlighted = searchParams.get("highlight");
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [sends, setSends] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(new Set());
  const [drafts, setDrafts] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [quotesError, setQuotesError] = useState(false);
  const [quotesLoading, setQuotesLoading] = useState(true);
  const [exampleDocs, setExampleDocs] = useState(new Set());
  const [exBusy, setExBusy] = useState(null);
  const isAdmin = user?.role === "admin";
  useEffect(() => {
    if (highlighted && quotes.length) document.getElementById(`quote-${highlighted}`)?.scrollIntoView({ block: "center" });
  }, [highlighted, quotes]);
  const [retrying, setRetrying] = useState(null);
  const [autoRemind, setAutoRemind] = useState(true);
  const [remindDelay, setRemindDelay] = useState(7);
  const [remindMax, setRemindMax] = useState(2);

  useEffect(() => {
    api.get("/quotes/reminders/settings").then(({ data }) => {
      setAutoRemind(data.enabled !== false);
      setRemindDelay(data.delay_days || 7);
      setRemindMax(data.max_reminders || 2);
    }).catch(() => {});
  }, []);
  const saveRemind = async (patch) => {
    const next = { enabled: autoRemind, delay_days: remindDelay, max_reminders: remindMax, ...patch };
    setAutoRemind(next.enabled); setRemindDelay(next.delay_days); setRemindMax(next.max_reminders);
    try {
      await api.post("/quotes/reminders/settings", next);
      toast.success("Reenvios atualizados");
    } catch { toast.error("Impossível modificar a configuração"); }
  };
  const toggleAutoRemind = (val) => saveRemind({ enabled: val });

  const QUOTE_STATUS = {
    draft: { label: "Brouillon", cls: "border-border text-muted-foreground" },
    sent: { label: "Enviado", cls: "border-sky-500/60 text-sky-600" },
    signed: { label: "Assinado", cls: "border-primary/60 text-primary bg-primary/5" },
    refused: { label: "Recusado", cls: "border-red-500/60 text-red-600" },
  };
  const [autoDeposit, setAutoDeposit] = useState(false);
  const [depositPct, setDepositPct] = useState(30);
  useEffect(() => {
    api.get("/documents/settings/auto-deposit")
      .then(({ data }) => { setAutoDeposit(!!data.enabled); setDepositPct(data.pct || 30); })
      .catch(() => {});
  }, []);
  const saveDeposit = async (patch) => {
    const next = { enabled: autoDeposit, pct: depositPct, ...patch };
    try {
      const { data } = await api.put("/documents/settings/auto-deposit", next);
      setAutoDeposit(data.enabled); setDepositPct(data.pct);
      toast.success(data.enabled
        ? `Acompte ${data.pct}% criado automaticamente em cada assinatura`
        : "Adiantamento automático desativado");
    } catch { toast.error("Definição impossível"); }
  };
  const toggleAutoDeposit = (v) => saveDeposit({ enabled: v });

  const signOnSite = async (doc) => {
    try {
      const { data } = await api.get(`/documents/${doc.doc_id}/sign-link`);
      if (data.already_signed) { toast.message("Este orçamento já está assinado"); return; }
      window.open(data.path, "_blank", "noopener");
      toast.success("Página de assinatura aberta — passe o ecrã ao cliente");
    } catch { toast.error("Impossível abrir a assinatura"); }
  };

  const changeStatus = async (doc, status) => {
    try {
      await api.patch(`/documents/${doc.doc_id}/status`, { status });
      setQuotes((qs) => qs.map((x) => x.doc_id === doc.doc_id ? { ...x, status } : x));
      toast.success(`Statut : ${QUOTE_STATUS[status]?.label || status}`);
    } catch { toast.error("Alteração de estado impossível"); }
  };
  const deleteQuote = async (doc) => {
    const signed = doc.status === "signed";
    if (signed) {
      const typed = window.prompt(`Este orçamento está ASSINADO (${doc.number || doc.doc_id}). A sua eliminação tem alcance contratual.\nPara confirmar, escreva exatamente: ELIMINAR`);
      if (typed !== "ELIMINAR") { toast.message("Eliminação anulada — o orçamento assinado é conservado"); return; }
    } else if (!(await confirm({
      title: "Mover este orçamento para o lixo?",
      description: `O orçamento${doc.number || ""}será recuperável durante 30 dias a partir do Lixo.`,
      confirmLabel: "Mover para o lixo",
    }))) return;
    try {
      await api.delete(`/documents/${doc.doc_id}${signed ? "?confirm_signed=true" : ""}`);
      setQuotes((qs) => qs.filter((x) => x.doc_id !== doc.doc_id));
      toast.success("Orçamento movido para o lixo — recuperável durante 30 dias", { action: { label: "Corbeille", onClick: () => navigate("/corbeille") } });
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };
  const facturer = async (doc) => {
    if (doc.status !== "signed") { toast.error("O orçamento deve ser assinado antes de ser faturado"); return; }
    try {
      const { data } = await api.post(`/documents/${doc.doc_id}/to-invoice`, { mode: "total", pct: 100 });
      toast.success("Fatura criada ✅");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Faturação impossível"); }
  };

  const facturerAcompte = async (doc) => {
    if (doc.status !== "signed") { toast.error("O orçamento deve ser assinado antes de faturar um sinal"); return; }
    try {
      const { data } = await api.post(`/documents/${doc.doc_id}/deposit-invoice`, { pct: 30 });
      toast.success("Fatura de sinal 30% criada — verifique e envie ✅");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Faturação do adiantamento impossível"); }
  };

  const [billQuote, setBillQuote] = useState(null);
  const [recap, setRecap] = useState(null);
  const [sitPct, setSitPct] = useState(50);
  const [sitDepMode, setSitDepMode] = useState("prorata");
  const [sitDepManual, setSitDepManual] = useState(0);
  const openBilling = async (doc) => {
    if (doc.status !== "signed") { toast.error("O orçamento deve ser assinado"); return; }
    setBillQuote(doc); setRecap(null); setSitPct(50); setSitDepMode("prorata"); setSitDepManual(0);
    try { const { data } = await api.get(`/documents/${doc.doc_id}/billing-recap`); setRecap(data); } catch { /* */ }
  };
  const makeSituation = async () => {
    try {
      const { data } = await api.post(`/documents/${billQuote.doc_id}/situation-invoice`, {
        pct: Number(sitPct), deposit_mode: sitDepMode, deposit_amount_ht: Number(sitDepManual) || 0,
      });
      toast.success("Fatura de auto de medição criada — verifique e envie ✅");
      setBillQuote(null); navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Auto de medição impossível"); }
  };
  const makeBalance = async () => {
    try {
      const { data } = await api.post(`/documents/${billQuote.doc_id}/balance-invoice`);
      toast.success("Fatura de saldo criada — verifique e envie ✅");
      setBillQuote(null); navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Fatura final impossível"); }
  };

  const retrySend = async (send) => {
    if (!send.doc_id) { toast.error("Orçamento não encontrado para a reativação"); return; }
    setRetrying(send.log_id);
    try {
      await api.post(`/documents/${send.doc_id}/send`, {
        client_email: send.client_email, client_name: send.client_name || "",
      });
      toast.success("Novo envio lançado ✅");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envio impossível");
    } finally { setRetrying(null); }
  };
  const now = new Date();
  const [recapY, setRecapY] = useState(now.getFullYear());
  const [recapM, setRecapM] = useState(now.getMonth() + 1);

  const load = async () => {
    setLoading(true);
    setQuotesLoading(true); setQuotesError(false);
    try {
      const { data } = await api.get("/quotes/sends/all");
      setSends(data.sends || []);
      setStats(data.stats || {});
      const done = new Set(
        (data.sends || []).filter((s) => s.worksite_status === "completed" || s.review_requested)
          .map((s) => s.log_id));
      setCompleted(done);
    } catch { toast.error("Impossível carregar os orçamentos"); }
    finally { setLoading(false); }
    try {
      const { data } = await api.get("/documents?doc_type=quote");
      setQuotes(data.documents || []);
      setDrafts((data.documents || []).filter((d) => d.status === "draft"));
    } catch { setQuotesError(true); }
    finally { setQuotesLoading(false); }
    if (user?.role === "admin") {
      try {
        const { data } = await api.get("/admin/learning/example-doc-ids");
        setExampleDocs(new Set(data.doc_ids || []));
      } catch { /* ignore */ }
    }
  };
  useEffect(() => { if (user) load(); }, [user]);

  const makeExample = async (send) => {
    if (!send.doc_id) { toast.error("Orçamento não encontrado"); return; }
    setExBusy(send.log_id);
    try {
      const { data } = await api.post(`/admin/learning/from-document/${send.doc_id}`);
      setExampleDocs((s) => new Set(s).add(send.doc_id));
      toast.success(data.already ? "Este orçamento já é um exemplo IA." : "Orçamento ganho adicionado aos exemplos IA — o assistente vai inspirar-se nele.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível adicionar");
    } finally { setExBusy(null); }
  };

  const exportCsv = async () => {
    try {
      const res = await api.get("/quotes/export.csv", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "construpilot-clients-devis.csv";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Export CSV transferido");
    } catch {
      toast.error("Impossível exportar");
    }
  };

  const exportRecapPdf = async () => {
    try {
      const res = await api.get(`/quotes/recap-pdf?year=${recapY}&month=${recapM}`,
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `recap-comptable-${recapY}-${String(recapM).padStart(2, "0")}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Relatório PDF descarregado");
    } catch {
      toast.error("Impossível gerar");
    }
  };

  const copySignLink = async (send) => {
    const raw = window.prompt(
      "Sinal pedido à assinatura (% do c/ IVA) — deixe 30 por defeito, ou 0 para desativar:",
      "30");
    if (raw === null) return; // annulé
    const pct = Math.max(0, Math.min(100, parseFloat(raw) || 0));
    try {
      const { data } = await api.post(
        `/takeoffs/${send.plan_id}/quote-sends/${send.log_id}/signature-link`,
        { deposit_pct: pct }
      );
      const fullUrl = data.url.startsWith("http") ? data.url
        : `${window.location.origin}${data.url}`;
      await navigator.clipboard.writeText(fullUrl);
      toast.success(pct > 0
        ? `Ligação copiada — sinal${pct}% na assinatura`
        : "Link de assinatura copiado (sem sinal)");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível gerar");
    }
  };

  const markCompleted = async (send) => {
    try {
      await api.post(`/reviews/request/${send.log_id}`);
      setCompleted((prev) => new Set(prev).add(send.log_id));
      toast.success("Obra terminada — pedido de avaliação enviado ao cliente 🎉");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Ação impossível");
    }
  };

  const [invoicing, setInvoicing] = useState(null);
  const [invoiceSend, setInvoiceSend] = useState(null);
  const [invoiceVat, setInvoiceVat] = useState("10");
  const convertToInvoice = async () => {
    if (!invoiceSend) return;
    const send = invoiceSend;
    setInvoicing(send.log_id);
    try {
      const { data } = await api.post(`/quotes/sends/${send.log_id}/to-invoice`,
        { vat_rate: Number(invoiceVat) });
      toast.success(data.already
        ? "Fatura já criada — abertura do editor"
        : `Fatura${data.number || ""}criada a partir do orçamento 🎉`);
      setInvoiceSend(null);
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Conversão impossível");
    } finally { setInvoicing(null); }
  };

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;
  if (loading) return <div className="surface p-10 text-center">A carregar…</div>;

  const notOpened = sends.filter(s => !s.opened && !s.signed);
  const opened = sends.filter(s => s.opened && !s.signed);
  const signed = sends.filter(s => s.signed);

  const fmtEur = (n) => (n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 0 }) + " €";
  const daysSince = (iso) => {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "aujourd'hui";
    if (d === 1) return "hier";
    return `há${d} j`;
  };

  const Card = ({ send, colour, showComplete }) => {
    const isDone = completed.has(send.log_id);
    return (
      <div className={`border rounded-sm p-3 space-y-1 ${colour}`}
           data-testid={`quote-card-${send.log_id}`}>
        <p className="font-bold text-sm truncate">
          {send.client_name || send.client_email}
        </p>
        <p className="text-[10px] text-muted-foreground truncate">
          {send.client_email !== (send.client_name || send.client_email) && send.client_email}
        </p>
        <p className="text-[10px] text-muted-foreground truncate">
          {send.plan_filename || send.plan_id}
        </p>
        <p className="num font-extrabold text-primary text-lg">{fmtEur(send.total_ttc)}</p>
        {send.email_status === "failed" && (
          <div className="flex items-center gap-2 pt-1" data-testid={`send-failed-${send.log_id}`}>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-red-500/15 text-red-600">Falha de envio</span>
            <button onClick={() => retrySend(send)} disabled={retrying === send.log_id}
                    data-testid={`retry-send-${send.log_id}`}
                    className="text-[10px] px-2 py-0.5 rounded-sm border border-red-500/40 text-red-600 font-semibold">
              {retrying === send.log_id ? "Envoi…" : "Tentar novamente"}
            </button>
          </div>
        )}
        {send.email_status === "queued" && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-amber-500/15 text-amber-600" data-testid={`send-queued-${send.log_id}`}>Envoi en cours…</span>
        )}
        <p className="text-[10px] num text-muted-foreground">
          Enviado {daysSince(send.created_at)}
          {send.opened && send.opened_at && ` · ouvert ${daysSince(send.opened_at)}`}
          {send.signed && send.signed_at && `· assinado${daysSince(send.signed_at)}`}
          {send.open_count > 1 && ` (${send.open_count} ouvertures)`}
        </p>
        <div className="flex gap-1 pt-1 flex-wrap">
          {!send.signed && (
            <button onClick={() => copySignLink(send)}
                    data-testid={`copy-sign-${send.log_id}`}
                    className="text-[10px] text-primary hover:underline inline-flex items-center gap-1">
              <Copy className="h-3 w-3" /> Lien signature
            </button>
          )}
          {send.signature_token && (
            <a href={`/sign/${send.signature_token}`} target="_blank" rel="noopener noreferrer"
               data-testid={`open-sign-${send.log_id}`}
               className="text-[10px] text-muted-foreground hover:text-primary inline-flex items-center gap-1">
              <ExternalLink className="h-3 w-3" /> Ouvrir
            </a>
          )}
        </div>
        {send.invoice_doc_id ? (
          <button onClick={() => navigate(`/devis-editeur/${send.invoice_doc_id}`)}
                  data-testid={`open-invoice-${send.log_id}`}
                  className="w-full inline-flex items-center justify-center gap-1 rounded-sm border border-primary/40 text-primary text-[11px] h-7 mt-1 hover:bg-primary hover:text-primary-foreground transition-colors">
            <Receipt className="h-3 w-3" /> Ver a fatura
          </button>
        ) : (
          <Button size="sm" variant="outline"
                  disabled={invoicing === send.log_id}
                  className="w-full rounded-sm gap-1 text-[11px] h-7 mt-1"
                  onClick={() => { setInvoiceVat("10"); setInvoiceSend(send); }}
                  data-testid={`convert-invoice-${send.log_id}`}>
            <Receipt className="h-3 w-3" />
            {invoicing === send.log_id ? "Conversion…" : "Converter em fatura"}
          </Button>
        )}
        {isAdmin && send.signed && send.doc_id && (
          exampleDocs.has(send.doc_id) ? (
            <div className="w-full inline-flex items-center justify-center gap-1 rounded-sm bg-primary/10 text-primary text-[11px] h-7 mt-1 font-semibold"
                 data-testid={`ai-example-done-${send.log_id}`}>
              <GraduationCap className="h-3 w-3" /> Exemplo IA guardado
            </div>
          ) : (
            <Button size="sm" variant="outline"
                    disabled={exBusy === send.log_id}
                    className="w-full rounded-sm gap-1 text-[11px] h-7 mt-1 border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                    onClick={() => makeExample(send)}
                    title="Transformar este orçamento ganho num exemplo de aprendizagem para a IA"
                    data-testid={`ai-example-${send.log_id}`}>
              <GraduationCap className="h-3 w-3" />
              {exBusy === send.log_id ? "Ajout…" : "Fazer dele um exemplo IA"}
            </Button>
          )
        )}
        {showComplete && (
          isDone ? (
            <Badge variant="outline"
                   className="rounded-sm border-primary/50 text-primary text-[10px] gap-1 mt-1"
                   data-testid={`worksite-done-${send.log_id}`}>
              <Star className="h-3 w-3" /> Avaliação solicitada
            </Badge>
          ) : (
            <Button size="sm" variant="outline"
                    className="w-full rounded-sm gap-1 text-[11px] h-7 mt-1 border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                    onClick={() => markCompleted(send)}
                    data-testid={`worksite-complete-${send.log_id}`}>
              <CheckCircle2 className="h-3 w-3" /> Obra terminada → pedir uma avaliação
            </Button>
          )
        )}
      </div>
    );
  };

  return (
    <div className="grid grid-cols-1 gap-8 min-w-0" data-testid="quote-tracking-page">
      <div className="flex flex-wrap items-start justify-between gap-3 min-w-0">
        <SectionTitle over={quoteText("tracking")} title={quoteText("title")} />
        <Link to="/devis-editeur" data-testid="create-quote-link">
          <Button className="rounded-sm gap-2" data-testid="create-quote-btn">
            <FileText className="h-4 w-4" /> Criar um orçamento
          </Button>
        </Link>
        <Button asChild variant="outline" className="gap-2"><Link to="/assistant?intent=quote" data-testid="tracking-create-with-assistant"><Sparkles size={16} />{quoteText("create")}</Link></Button>
        <ImportDocumentsDialog triggerLabel="Importar PDFs" onImported={load} />
        <label className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground border border-border rounded-sm px-3 py-2 max-w-full min-w-0"
               data-testid="auto-remind-toggle" title="Relançamento automático por e-mail dos orçamentos enviados não assinados">
          <Switch checked={autoRemind} onCheckedChange={toggleAutoRemind} data-testid="auto-remind-switch" />
          Relances auto
          {autoRemind && (
            <span className="flex flex-wrap items-center gap-1 ml-1 min-w-0">
              <select value={remindDelay} onChange={(e) => saveRemind({ delay_days: Number(e.target.value) })}
                      className="rounded-sm border border-border bg-background px-1.5 py-0.5 text-xs" data-testid="remind-delay-select">
                <option value={3}>a cada 3 d</option>
                <option value={5}>a cada 5 d</option>
                <option value={7}>a cada 7 d</option>
              </select>
              <select value={remindMax} onChange={(e) => saveRemind({ max_reminders: Number(e.target.value) })}
                      className="rounded-sm border border-border bg-background px-1.5 py-0.5 text-xs" data-testid="remind-max-select">
                <option value={1}>1 relance</option>
                <option value={2}>2 relances</option>
                <option value={3}>3 relances</option>
              </select>
            </span>
          )}
        </label>
        <label className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground border border-border rounded-sm px-3 py-2 max-w-full min-w-0"
               data-testid="auto-deposit-toggle"
               title="Cria a fatura de adiantamento em rascunho assim que o cliente assina">
          <Switch checked={autoDeposit} onCheckedChange={toggleAutoDeposit} data-testid="auto-deposit-switch" />
          Adiantamento automático na assinatura
          {autoDeposit && (
            <select value={depositPct} onChange={(e) => saveDeposit({ pct: Number(e.target.value) })}
                    className="rounded-sm border border-border bg-background px-1.5 py-0.5 text-xs"
                    data-testid="auto-deposit-pct-select">
              {[10, 20, 30, 40, 50].map((v) => <option key={v} value={v}>{v} %</option>)}
            </select>
          )}
        </label>
      </div>

      {/* Chiffre d'affaires mensuel */}
      <RevenueChart />

      {/* Devis enregistrés (brouillons, non encore envoyés) */}
      <div className="surface p-5" data-testid="saved-drafts-section">
        <div className="flex items-center justify-between mb-3">
          <p className="overline" data-testid="saved-quotes-title">{quoteText("drafts")}</p>
          <span className="text-xs text-muted-foreground num" data-testid="saved-quotes-count">{quotes.length}</span>
        </div>
        {quotesError && <p role="alert" data-testid="saved-quotes-error" className="text-sm text-red-600 mb-4">{quoteText("loadError")} <button onClick={load} className="underline" data-testid="saved-quotes-retry">{quoteText("retry")}</button></p>}
        {quotesLoading && <RefreshCw className="animate-spin h-4 w-4 my-3" aria-label="A carregar" data-testid="saved-quotes-loading" />}
        {!quotesLoading && !quotesError && quotes.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Nenhum orçamento registado. Os seus orçamentos aparecerão aqui após « Guardar ».
          </p>
        ) : (
          <div className="grid gap-2">
            {quotes.map((d) => {
              const st = QUOTE_STATUS[d.status] || QUOTE_STATUS.draft;
              return (
                <div key={d.doc_id} id={`quote-${d.doc_id}`} data-testid={`quote-row-${d.doc_id}`}
                     className={`w-full min-w-0 flex flex-col gap-3 border rounded-sm px-3 py-3 hover:border-primary/60 transition-colors ${highlighted === d.doc_id ? "border-primary bg-primary/5" : "border-border"}`}>
                  <div className="flex items-start gap-3 min-w-0">
                    {d.plan_id && (
                      <img src={`${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${d.plan_id}/thumb`} alt="" loading="lazy"
                           onError={(e) => { e.currentTarget.style.display = "none"; }}
                           className="w-12 h-12 object-cover rounded-sm border border-border shrink-0 bg-muted/40"
                           data-testid={`quote-thumb-${d.doc_id}`} />
                    )}
                    <button onClick={() => navigate(`/devis-editeur/${d.doc_id}`)}
                            className="min-w-0 text-left flex-1" data-testid={`quote-open-${d.doc_id}`}>
                      <p className="text-sm font-semibold break-words line-clamp-2" data-testid={`quote-title-${d.doc_id}`}>
                        {d.title || d.number || "Brouillon"}
                      </p>
                      <p className="text-xs text-muted-foreground break-words line-clamp-1" data-testid={`quote-client-${d.doc_id}`}>{d.client_name || d.client?.company || [d.client?.first_name, d.client?.last_name].filter(Boolean).join(" ") || quoteText("emptyClient")}</p>
                      {d.source === "assistant" && <p className="text-xs text-primary" data-testid={`quote-assistant-origin-${d.doc_id}`}>{quoteText("source")}</p>}
                      <p className="text-[11px] text-muted-foreground">{(d.created_at || "").slice(0, 10)}</p>
                    </button>
                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className="num text-sm font-bold text-primary whitespace-nowrap" data-testid={`quote-total-${d.doc_id}`}>
                        {Number(d.totals?.ttc ?? d.total_ttc ?? 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
                      </span>
                      <Badge variant="outline" className={`rounded-sm ${st.cls}`}
                             data-testid={`quote-status-badge-${d.doc_id}`}>{st.label}</Badge>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select value={d.status || "draft"} onChange={(e) => changeStatus(d, e.target.value)}
                            data-testid={`quote-status-select-${d.doc_id}`}
                            className="rounded-sm border border-border bg-background px-2 py-1.5 text-xs outline-none focus:border-primary h-9 flex-1 sm:flex-none min-w-[6.5rem]">
                      <option value="draft">Brouillon</option>
                      <option value="sent">Enviado</option>
                      <option value="signed">Assinado</option>
                      <option value="refused">Recusado</option>
                    </select>
                    <Button size="sm" className="rounded-sm gap-1 h-9 flex-1 sm:flex-none min-w-[8rem] justify-center"
                            disabled={d.status === "signed"} onClick={() => signOnSite(d)}
                            title={d.status === "signed" ? "Orçamento já assinado" : "Fazer o cliente assinar neste dispositivo"}
                            data-testid={`quote-sign-onsite-${d.doc_id}`}>
                      <PenLine className="h-3.5 w-3.5" /> Mandar assinar
                    </Button>
                    <Button size="sm" variant="outline" className="rounded-sm gap-1 h-9 flex-1 sm:flex-none min-w-[7rem] justify-center"
                            disabled={d.status !== "signed"} onClick={() => facturer(d)}
                            title={d.status !== "signed" ? "O orçamento deve ser assinado" : "Transformar em fatura"}
                            data-testid={`quote-invoice-${d.doc_id}`}>
                      <Receipt className="h-3.5 w-3.5" /> Facturer
                    </Button>
                    <Button size="sm" variant="outline" className="rounded-sm gap-1 h-9 flex-1 sm:flex-none min-w-[7rem] justify-center"
                            disabled={d.status !== "signed"} onClick={() => facturerAcompte(d)}
                            title={d.status !== "signed" ? "O orçamento deve ser assinado" : "Fatura de sinal 30%"}
                            data-testid={`quote-deposit-${d.doc_id}`}>
                      <Receipt className="h-3.5 w-3.5" /> Acompte 30%
                    </Button>
                    <Button size="sm" variant="outline" className="rounded-sm gap-1 h-9 flex-1 sm:flex-none min-w-[9rem] justify-center"
                            disabled={d.status !== "signed"} onClick={() => openBilling(d)}
                            title={d.status !== "signed" ? "O orçamento deve ser assinado" : "Descontos, auto de medição, saldo"}
                            data-testid={`quote-billing-${d.doc_id}`}>
                      <Receipt className="h-3.5 w-3.5" /> Auto / Situação
                    </Button>
                    <Button size="sm" variant="ghost" className="rounded-sm h-9 w-9 p-0 text-muted-foreground hover:text-red-600 shrink-0 ml-auto"
                            onClick={() => deleteQuote(d)} data-testid={`quote-delete-${d.doc_id}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="surface p-4" data-testid="kpi-sent">
          <div className="flex items-center gap-2 mb-1">
            <Send className="h-4 w-4 text-muted-foreground" />
            <p className="overline">Enviados</p>
          </div>
          <p className="num font-display text-3xl font-extrabold">{stats.sent || 0}</p>
        </div>
        <div className="surface p-4" data-testid="kpi-opened">
          <div className="flex items-center gap-2 mb-1">
            <Eye className="h-4 w-4 text-emerald-500" />
            <p className="overline">Ouverts</p>
          </div>
          <p className="num font-display text-3xl font-extrabold">{stats.opened || 0}</p>
          <p className="text-[10px] text-muted-foreground num">
            {stats.sent ? Math.round((stats.opened || 0) / stats.sent * 100) : 0} % taux d'ouverture
          </p>
        </div>
        <div className="surface p-4" data-testid="kpi-signed">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="h-4 w-4 text-primary" />
            <p className="overline">Assinados</p>
          </div>
          <p className="num font-display text-3xl font-extrabold text-primary">{stats.signed || 0}</p>
          <p className="text-[10px] text-muted-foreground num">
            {fmtEur(stats.total_ttc_signed)} conclus
          </p>
        </div>
        <div className="surface p-4" data-testid="kpi-pipeline">
          <div className="flex items-center gap-2 mb-1">
            <FileText className="h-4 w-4 text-primary" />
            <p className="overline">Pipeline</p>
          </div>
          <p className="num font-display text-3xl font-extrabold">{fmtEur(stats.total_ttc_pipeline)}</p>
          <p className="text-[10px] text-muted-foreground">a concluir</p>
        </div>
      </div>

      {/* Export comptabilité */}
      <div className="surface p-4 flex flex-wrap items-end gap-3" data-testid="accounting-export">
        <div>
          <p className="overline">Export comptable</p>
          <p className="text-xs text-muted-foreground mt-1">
            Relatório mensal PDF pronto a enviar ao seu contabilista, ou exportação CSV bruta.
          </p>
        </div>
        <div className="flex items-end gap-2 ml-auto flex-wrap">
          <div className="flex flex-col">
            <label className="text-[10px] text-muted-foreground mb-1">Mois</label>
            <select value={recapM} onChange={(e) => setRecapM(Number(e.target.value))}
                    data-testid="recap-month-select"
                    className="rounded-sm border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary">
              {MONTHS_FR.map((m, i) => (
                <option key={i} value={i + 1}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col">
            <label className="text-[10px] text-muted-foreground mb-1">Ano</label>
            <select value={recapY} onChange={(e) => setRecapY(Number(e.target.value))}
                    data-testid="recap-year-select"
                    className="rounded-sm border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary">
              {[now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2].map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>
          <Button onClick={exportRecapPdf} className="rounded-sm gap-2"
                  data-testid="export-recap-pdf-btn">
            <FileDown className="h-4 w-4" /> Rapport PDF comptable
          </Button>
          <Button variant="outline" onClick={exportCsv} className="rounded-sm gap-2"
                  data-testid="export-csv-btn">
            <Download className="h-4 w-4" /> Exporter CSV
          </Button>
        </div>
      </div>

      <div className="flex justify-between items-center">
        <p className="text-xs text-muted-foreground">
          {sends.length} orçamento · última atualização {new Date().toLocaleTimeString("fr-FR")}
        </p>
        <Button size="sm" variant="outline" onClick={load} data-testid="quote-tracking-refresh"
                className="rounded-sm gap-1">
          <RefreshCw className="h-3 w-3" /> Actualiser
        </Button>
      </div>

      {/* 3-column board */}
      {sends.length === 0 ? (
        <div className="surface p-10 text-center space-y-3">
          <Mail className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">Nenhum orçamento enviado por agora</p>
          <p className="text-sm text-muted-foreground">
            Abra um plano de medições, clique em <b>Orçamento PDF → Enviar ao cliente</b>, e acompanhe tudo aqui em tempo real.
          </p>
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {/* Col 1 : Non ouverts */}
          <div className="space-y-3" data-testid="col-not-opened">
            <div className="flex items-center gap-2 border-b-2 border-muted-foreground/40 pb-2">
              <Send className="h-4 w-4 text-muted-foreground" />
              <p className="font-display font-bold text-sm">Não abertos</p>
              <Badge variant="outline" className="ml-auto rounded-sm">{notOpened.length}</Badge>
            </div>
            {notOpened.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Todos os seus orçamentos foram abertos 🎉
              </p>
            )}
            {notOpened.map(s => <Card key={s.log_id} send={s}
                                       colour="border-muted-foreground/20 bg-secondary/20" />)}
          </div>

          {/* Col 2 : Ouverts */}
          <div className="space-y-3" data-testid="col-opened">
            <div className="flex items-center gap-2 border-b-2 border-emerald-500/60 pb-2">
              <Eye className="h-4 w-4 text-emerald-500" />
              <p className="font-display font-bold text-sm">Abertos (a relembrar)</p>
              <Badge variant="outline" className="ml-auto rounded-sm border-emerald-500/60 text-emerald-500">
                {opened.length}
              </Badge>
            </div>
            {opened.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Nenhum orçamento lido sem assinatura.
              </p>
            )}
            {opened.map(s => <Card key={s.log_id} send={s}
                                    colour="border-emerald-500/30 bg-emerald-500/5" />)}
          </div>

          {/* Col 3 : Signés */}
          <div className="space-y-3" data-testid="col-signed">
            <div className="flex items-center gap-2 border-b-2 border-primary pb-2">
              <CheckCircle2 className="h-4 w-4 text-primary" />
              <p className="font-display font-bold text-sm">Assinados</p>
              <Badge className="ml-auto rounded-sm bg-primary text-primary-foreground">
                {signed.length}
              </Badge>
            </div>
            {signed.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Nenhuma assinatura por enquanto.
              </p>
            )}
            {signed.map(s => <Card key={s.log_id} send={s} showComplete
                                    colour="border-primary/40 bg-primary/5" />)}
          </div>
        </div>
      )}

      <Dialog open={!!invoiceSend} onOpenChange={(o) => !o && setInvoiceSend(null)}>
        <DialogContent className="max-w-sm" data-testid="invoice-vat-dialog">
          <DialogHeader>
            <DialogTitle>Converter em fatura</DialogTitle>
            <DialogDescription>
              Escolha a taxa de IVA a aplicar. O montante c/ IVA do orçamento é mantido ({fmtEur(invoiceSend?.total_ttc)}).
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <label className="text-xs text-muted-foreground">Taxa de IVA</label>
            <div className="grid grid-cols-3 gap-2">
              {[["5.5", "5,5 % — 1.ª necessidade"], ["10", "10 % — Renovação"], ["20", "20 % — Neuf"]].map(([v, lbl]) => (
                <button key={v} onClick={() => setInvoiceVat(v)}
                  data-testid={`vat-opt-${v}`}
                  className={`rounded-sm border px-2 py-3 text-center transition-colors ${
                    invoiceVat === v ? "border-primary bg-primary/10 text-primary" : "border-border hover:border-primary/40"
                  }`}>
                  <span className="num font-bold text-base block">{v.replace(".", ",")} %</span>
                  <span className="text-[10px] text-muted-foreground">{lbl.split("—")[1]}</span>
                </button>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" className="rounded-sm" onClick={() => setInvoiceSend(null)}
                    data-testid="invoice-vat-cancel">Cancelar</Button>
            <Button className="rounded-sm gap-2" onClick={convertToInvoice}
                    disabled={!!invoicing} data-testid="invoice-vat-confirm">
              <Receipt className="h-4 w-4" /> Criar a fatura
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!billQuote} onOpenChange={(o) => !o && setBillQuote(null)}>
        <DialogContent className="max-w-lg" data-testid="billing-modal">
          <DialogHeader>
            <DialogTitle>Resumo geral — {billQuote?.number || billQuote?.title}</DialogTitle>
            <DialogDescription>Fature proporcionalmente (auto de medição) ou o saldo. Os sinais já faturados são tidos em conta.</DialogDescription>
          </DialogHeader>
          {recap ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="surface p-2 rounded-sm"><p className="num font-bold">{eur(recap.quote.ttc)}</p><p className="text-[11px] text-muted-foreground">Orçamento c/ IVA</p></div>
                <div className="surface p-2 rounded-sm"><p className="num font-bold text-emerald-500">{eur(recap.billed_ttc)}</p><p className="text-[11px] text-muted-foreground">Já faturado</p></div>
                <div className="surface p-2 rounded-sm"><p className="num font-bold text-primary">{eur(recap.remaining_ttc)}</p><p className="text-[11px] text-muted-foreground">Por faturar</p></div>
              </div>
              <div className="text-xs text-muted-foreground">Progresso faturado: {recap.progress_pct}%</div>
              {recap.invoices.length > 0 && (
                <div className="border border-border rounded-sm divide-y divide-border max-h-32 overflow-auto" data-testid="billing-recap-list">
                  {recap.invoices.map((i) => (
                    <div key={i.doc_id} className="flex justify-between px-3 py-1.5 text-xs">
                      <span>{i.number || "—"} · {{ deposit: "Acompte", situation: "Situation", balance: "Solde" }[i.source] || "Fatura"}</span>
                      <span className="num">{eur(i.ttc)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="rounded-sm border border-border p-3 space-y-2">
                <p className="font-semibold text-xs uppercase tracking-wide">Novo auto de medição</p>
                <div className="flex items-end gap-3">
                  <label className="w-24 text-xs">Avancement %
                    <input type="number" min="1" max="100" value={sitPct} onChange={(e) => setSitPct(e.target.value)}
                           className="mt-1 w-full h-9 rounded-sm border border-border bg-background px-2" data-testid="billing-sit-pct" />
                  </label>
                  <label className="flex-1 text-xs">Adiantamento já pago
                    <select value={sitDepMode} onChange={(e) => setSitDepMode(e.target.value)}
                            className="mt-1 w-full h-9 rounded-sm border border-border bg-background px-2" data-testid="billing-sit-deposit-mode">
                      <option value="prorata">Deduzir proporcionalmente</option>
                      <option value="full">Deduzir na totalidade</option>
                      <option value="manual">Montante manual</option>
                      <option value="none">Não deduzir</option>
                    </select>
                  </label>
                  {sitDepMode === "manual" && (
                    <label className="w-24 text-xs">Montante s/ IVA
                      <input type="number" min="0" value={sitDepManual} onChange={(e) => setSitDepManual(e.target.value)}
                             className="mt-1 w-full h-9 rounded-sm border border-border bg-background px-2" data-testid="billing-sit-deposit-manual" />
                    </label>
                  )}
                  <Button size="sm" className="h-9" onClick={makeSituation} data-testid="billing-make-situation">Criar auto de medição</Button>
                </div>
                <p className="text-[11px] text-muted-foreground" data-testid="billing-deposit-info">
                  {recap.deposit?.available_ht > 0
                    ? `Adiantamento recebido${eur(recap.deposit.paid_ttc)}c/ IVA · disponível para deduzir${eur(recap.deposit.available_ht)} HT`
                    : "Nenhum adiantamento recebido a deduzir (só o adiantamento efetivamente pago é dedutível)."}
                </p>
              </div>
            </div>
          ) : <p className="text-sm text-muted-foreground py-6 text-center">Carregamento da contabilização…</p>}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setBillQuote(null)}>Fechar</Button>
            <Button onClick={makeBalance} data-testid="billing-make-balance">Faturar o saldo</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
