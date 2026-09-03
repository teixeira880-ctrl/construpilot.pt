import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Send, Eye, CheckCircle2, FileText, Copy, ExternalLink, RefreshCw, Mail,
  Download, FileDown, Star, Receipt, Trash2,
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
import { Link, useNavigate } from "react-router-dom";

const MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

export default function QuoteTracking() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [sends, setSends] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(new Set());
  const [drafts, setDrafts] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [retrying, setRetrying] = useState(null);
  const [autoRemind, setAutoRemind] = useState(true);
  const [remindDelay, setRemindDelay] = useState(5);
  const [remindMax, setRemindMax] = useState(2);

  useEffect(() => {
    api.get("/quotes/reminders/settings").then(({ data }) => {
      setAutoRemind(data.enabled !== false);
      setRemindDelay(data.delay_days || 5);
      setRemindMax(data.max_reminders || 2);
    }).catch(() => {});
  }, []);
  const saveRemind = async (patch) => {
    const next = { enabled: autoRemind, delay_days: remindDelay, max_reminders: remindMax, ...patch };
    setAutoRemind(next.enabled); setRemindDelay(next.delay_days); setRemindMax(next.max_reminders);
    try {
      await api.post("/quotes/reminders/settings", next);
      toast.success("Relances mises à jour");
    } catch { toast.error("Impossible de modifier le réglage"); }
  };
  const toggleAutoRemind = (val) => saveRemind({ enabled: val });

  const QUOTE_STATUS = {
    draft: { label: "Brouillon", cls: "border-border text-muted-foreground" },
    sent: { label: "Envoyé", cls: "border-sky-500/60 text-sky-600" },
    signed: { label: "Signé", cls: "border-primary/60 text-primary bg-primary/5" },
    refused: { label: "Refusé", cls: "border-red-500/60 text-red-600" },
  };
  const changeStatus = async (doc, status) => {
    try {
      await api.patch(`/documents/${doc.doc_id}/status`, { status });
      setQuotes((qs) => qs.map((x) => x.doc_id === doc.doc_id ? { ...x, status } : x));
      toast.success(`Statut : ${QUOTE_STATUS[status]?.label || status}`);
    } catch { toast.error("Changement de statut impossible"); }
  };
  const deleteQuote = async (doc) => {
    if (!(await confirm({
      title: "Supprimer ce devis ?",
      description: `Le devis ${doc.number || ""} sera définitivement supprimé.`,
      confirmLabel: "Supprimer",
    }))) return;
    try {
      await api.delete(`/documents/${doc.doc_id}`);
      setQuotes((qs) => qs.filter((x) => x.doc_id !== doc.doc_id));
      toast.success("Devis supprimé");
    } catch { toast.error("Suppression impossible"); }
  };
  const facturer = async (doc) => {
    if (doc.status !== "signed") { toast.error("Le devis doit être signé avant d'être facturé"); return; }
    try {
      const { data } = await api.post(`/documents/${doc.doc_id}/to-invoice`, { mode: "total", pct: 100 });
      toast.success("Facture créée ✅");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Facturation impossible"); }
  };

  const facturerAcompte = async (doc) => {
    if (doc.status !== "signed") { toast.error("Le devis doit être signé avant de facturer un acompte"); return; }
    try {
      const { data } = await api.post(`/documents/${doc.doc_id}/deposit-invoice`, { pct: 30 });
      toast.success("Facture d'acompte 30% créée — vérifiez et envoyez ✅");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Facturation d'acompte impossible"); }
  };

  const [billQuote, setBillQuote] = useState(null);
  const [recap, setRecap] = useState(null);
  const [sitPct, setSitPct] = useState(50);
  const [sitDeduct, setSitDeduct] = useState(0);
  const openBilling = async (doc) => {
    if (doc.status !== "signed") { toast.error("Le devis doit être signé"); return; }
    setBillQuote(doc); setRecap(null); setSitPct(50); setSitDeduct(0);
    try { const { data } = await api.get(`/documents/${doc.doc_id}/billing-recap`); setRecap(data); } catch { /* */ }
  };
  const makeSituation = async () => {
    try {
      const { data } = await api.post(`/documents/${billQuote.doc_id}/situation-invoice`, { pct: Number(sitPct), deduct_deposit_pct: Number(sitDeduct) });
      toast.success("Facture de situation créée — vérifiez et envoyez ✅");
      setBillQuote(null); navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Situation impossible"); }
  };
  const makeBalance = async () => {
    try {
      const { data } = await api.post(`/documents/${billQuote.doc_id}/balance-invoice`);
      toast.success("Facture de solde créée — vérifiez et envoyez ✅");
      setBillQuote(null); navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Solde impossible"); }
  };

  const retrySend = async (send) => {
    if (!send.doc_id) { toast.error("Devis introuvable pour la relance"); return; }
    setRetrying(send.log_id);
    try {
      await api.post(`/documents/${send.doc_id}/send`, {
        client_email: send.client_email, client_name: send.client_name || "",
      });
      toast.success("Nouvel envoi lancé ✅");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi impossible");
    } finally { setRetrying(null); }
  };
  const now = new Date();
  const [recapY, setRecapY] = useState(now.getFullYear());
  const [recapM, setRecapM] = useState(now.getMonth() + 1);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/quotes/sends/all");
      setSends(data.sends || []);
      setStats(data.stats || {});
      const done = new Set(
        (data.sends || []).filter((s) => s.worksite_status === "completed" || s.review_requested)
          .map((s) => s.log_id));
      setCompleted(done);
    } catch { toast.error("Impossible de charger les devis"); }
    finally { setLoading(false); }
    try {
      const { data } = await api.get("/documents?doc_type=quote");
      setQuotes(data.documents || []);
      setDrafts((data.documents || []).filter((d) => d.status !== "sent"));
    } catch { /* noop */ }
  };
  useEffect(() => { if (user) load(); }, [user]);

  const exportCsv = async () => {
    try {
      const res = await api.get("/quotes/export.csv", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = "construpilot-clients-devis.csv";
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Export CSV téléchargé");
    } catch {
      toast.error("Export impossible");
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
      toast.success("Rapport PDF téléchargé");
    } catch {
      toast.error("Génération impossible");
    }
  };

  const copySignLink = async (send) => {
    const raw = window.prompt(
      "Acompte demandé à la signature (% du TTC) — laissez 30 par défaut, ou 0 pour désactiver :",
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
        ? `Lien copié — acompte ${pct}% à la signature`
        : "Lien de signature copié (sans acompte)");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Génération impossible");
    }
  };

  const markCompleted = async (send) => {
    try {
      await api.post(`/reviews/request/${send.log_id}`);
      setCompleted((prev) => new Set(prev).add(send.log_id));
      toast.success("Chantier terminé — demande d'avis envoyée au client 🎉");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Action impossible");
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
        ? "Facture déjà créée — ouverture de l'éditeur"
        : `Facture ${data.number || ""} créée depuis le devis 🎉`);
      setInvoiceSend(null);
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Conversion impossible");
    } finally { setInvoicing(null); }
  };

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;
  if (loading) return <div className="surface p-10 text-center">Chargement…</div>;

  const notOpened = sends.filter(s => !s.opened && !s.signed);
  const opened = sends.filter(s => s.opened && !s.signed);
  const signed = sends.filter(s => s.signed);

  const fmtEur = (n) => (n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 0 }) + " €";
  const daysSince = (iso) => {
    const d = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
    if (d === 0) return "aujourd'hui";
    if (d === 1) return "hier";
    return `il y a ${d} j`;
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
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-red-500/15 text-red-600">Échec d'envoi</span>
            <button onClick={() => retrySend(send)} disabled={retrying === send.log_id}
                    data-testid={`retry-send-${send.log_id}`}
                    className="text-[10px] px-2 py-0.5 rounded-sm border border-red-500/40 text-red-600 font-semibold">
              {retrying === send.log_id ? "Envoi…" : "Réessayer"}
            </button>
          </div>
        )}
        {send.email_status === "queued" && (
          <span className="text-[10px] font-bold px-2 py-0.5 rounded-sm bg-amber-500/15 text-amber-600" data-testid={`send-queued-${send.log_id}`}>Envoi en cours…</span>
        )}
        <p className="text-[10px] num text-muted-foreground">
          Envoyé {daysSince(send.created_at)}
          {send.opened && send.opened_at && ` · ouvert ${daysSince(send.opened_at)}`}
          {send.signed && send.signed_at && ` · signé ${daysSince(send.signed_at)}`}
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
            <Receipt className="h-3 w-3" /> Voir la facture
          </button>
        ) : (
          <Button size="sm" variant="outline"
                  disabled={invoicing === send.log_id}
                  className="w-full rounded-sm gap-1 text-[11px] h-7 mt-1"
                  onClick={() => { setInvoiceVat("10"); setInvoiceSend(send); }}
                  data-testid={`convert-invoice-${send.log_id}`}>
            <Receipt className="h-3 w-3" />
            {invoicing === send.log_id ? "Conversion…" : "Convertir en facture"}
          </Button>
        )}
        {showComplete && (
          isDone ? (
            <Badge variant="outline"
                   className="rounded-sm border-primary/50 text-primary text-[10px] gap-1 mt-1"
                   data-testid={`worksite-done-${send.log_id}`}>
              <Star className="h-3 w-3" /> Avis demandé
            </Badge>
          ) : (
            <Button size="sm" variant="outline"
                    className="w-full rounded-sm gap-1 text-[11px] h-7 mt-1 border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                    onClick={() => markCompleted(send)}
                    data-testid={`worksite-complete-${send.log_id}`}>
              <CheckCircle2 className="h-3 w-3" /> Chantier terminé → demander un avis
            </Button>
          )
        )}
      </div>
    );
  };

  return (
    <div className="grid gap-8">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Suivi Devis" title="Où en sont vos devis envoyés ?">
          Toutes les propositions envoyées à vos clients, organisées par état d'avancement.
          Relancez au bon moment grâce au suivi d'ouverture et de signature.
        </SectionTitle>
        <Link to="/devis-editeur">
          <Button className="rounded-sm gap-2" data-testid="create-quote-btn">
            <FileText className="h-4 w-4" /> Créer un devis
          </Button>
        </Link>
        <ImportDocumentsDialog triggerLabel="Importer des PDF" onImported={load} />
        <label className="flex items-center gap-2 text-xs text-muted-foreground border border-border rounded-sm px-3 py-2"
               data-testid="auto-remind-toggle" title="Relance automatique par e-mail des devis envoyés non signés">
          <Switch checked={autoRemind} onCheckedChange={toggleAutoRemind} data-testid="auto-remind-switch" />
          Relances auto
          {autoRemind && (
            <span className="flex items-center gap-1 ml-1">
              <select value={remindDelay} onChange={(e) => saveRemind({ delay_days: Number(e.target.value) })}
                      className="rounded-sm border border-border bg-background px-1.5 py-0.5 text-xs" data-testid="remind-delay-select">
                <option value={3}>tous les 3 j</option>
                <option value={5}>tous les 5 j</option>
                <option value={7}>tous les 7 j</option>
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
      </div>

      {/* Chiffre d'affaires mensuel */}
      <RevenueChart />

      {/* Devis enregistrés (brouillons, non encore envoyés) */}
      <div className="surface p-5" data-testid="saved-drafts-section">
        <div className="flex items-center justify-between mb-3">
          <p className="overline">Devis enregistrés</p>
          <span className="text-xs text-muted-foreground num">{quotes.length}</span>
        </div>
        {quotes.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            Aucun devis enregistré. Vos devis apparaîtront ici après « Enregistrer ».
          </p>
        ) : (
          <div className="grid gap-2">
            {quotes.map((d) => {
              const st = QUOTE_STATUS[d.status] || QUOTE_STATUS.draft;
              return (
                <div key={d.doc_id} data-testid={`quote-row-${d.doc_id}`}
                     className="w-full flex flex-wrap items-center justify-between gap-2 border border-border rounded-sm px-3 py-2 hover:border-primary/60 transition-colors">
                  <button onClick={() => navigate(`/devis-editeur/${d.doc_id}`)}
                          className="min-w-0 text-left flex-1" data-testid={`quote-open-${d.doc_id}`}>
                    <p className="text-sm font-semibold truncate">
                      {d.number || "Brouillon"}{d.client_name ? ` · ${d.client_name}` : ""}
                    </p>
                    <p className="text-[11px] text-muted-foreground">{(d.created_at || "").slice(0, 10)}</p>
                  </button>
                  <span className="num text-sm font-bold text-primary shrink-0">
                    {Math.round(d.total_ttc || (d.totals && d.totals.ttc) || 0).toLocaleString("fr-FR")} €
                  </span>
                  <Badge variant="outline" className={`rounded-sm shrink-0 ${st.cls}`}
                         data-testid={`quote-status-badge-${d.doc_id}`}>{st.label}</Badge>
                  <select value={d.status || "draft"} onChange={(e) => changeStatus(d, e.target.value)}
                          data-testid={`quote-status-select-${d.doc_id}`}
                          className="rounded-sm border border-border bg-background px-2 py-1 text-xs outline-none focus:border-primary shrink-0">
                    <option value="draft">Brouillon</option>
                    <option value="sent">Envoyé</option>
                    <option value="signed">Signé</option>
                    <option value="refused">Refusé</option>
                  </select>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8 shrink-0"
                          disabled={d.status !== "signed"} onClick={() => facturer(d)}
                          title={d.status !== "signed" ? "Le devis doit être signé" : "Transformer en facture"}
                          data-testid={`quote-invoice-${d.doc_id}`}>
                    <Receipt className="h-3.5 w-3.5" /> Facturer
                  </Button>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8 shrink-0"
                          disabled={d.status !== "signed"} onClick={() => facturerAcompte(d)}
                          title={d.status !== "signed" ? "Le devis doit être signé" : "Facture d'acompte 30%"}
                          data-testid={`quote-deposit-${d.doc_id}`}>
                    <Receipt className="h-3.5 w-3.5" /> Acompte 30%
                  </Button>
                  <Button size="sm" variant="outline" className="rounded-sm gap-1 h-8 shrink-0"
                          disabled={d.status !== "signed"} onClick={() => openBilling(d)}
                          title={d.status !== "signed" ? "Le devis doit être signé" : "Décompte, situation, solde"}
                          data-testid={`quote-billing-${d.doc_id}`}>
                    <Receipt className="h-3.5 w-3.5" /> Décompte / Situation
                  </Button>
                  <Button size="sm" variant="ghost" className="rounded-sm h-8 w-8 p-0 text-muted-foreground hover:text-red-600 shrink-0"
                          onClick={() => deleteQuote(d)} data-testid={`quote-delete-${d.doc_id}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
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
            <p className="overline">Envoyés</p>
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
            <p className="overline">Signés</p>
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
          <p className="text-[10px] text-muted-foreground">à conclure</p>
        </div>
      </div>

      {/* Export comptabilité */}
      <div className="surface p-4 flex flex-wrap items-end gap-3" data-testid="accounting-export">
        <div>
          <p className="overline">Export comptable</p>
          <p className="text-xs text-muted-foreground mt-1">
            Rapport mensuel PDF prêt à envoyer à votre comptable, ou export CSV brut.
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
            <label className="text-[10px] text-muted-foreground mb-1">Année</label>
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
          {sends.length} devis · dernière mise à jour {new Date().toLocaleTimeString("fr-FR")}
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
          <p className="font-display font-bold">Aucun devis envoyé pour l'instant</p>
          <p className="text-sm text-muted-foreground">
            Ouvrez un plan métré, cliquez sur <b>Devis PDF → Envoyer au client</b>,
            et suivez tout ici en temps réel.
          </p>
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          {/* Col 1 : Non ouverts */}
          <div className="space-y-3" data-testid="col-not-opened">
            <div className="flex items-center gap-2 border-b-2 border-muted-foreground/40 pb-2">
              <Send className="h-4 w-4 text-muted-foreground" />
              <p className="font-display font-bold text-sm">Non ouverts</p>
              <Badge variant="outline" className="ml-auto rounded-sm">{notOpened.length}</Badge>
            </div>
            {notOpened.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Tous vos devis ont été ouverts 🎉
              </p>
            )}
            {notOpened.map(s => <Card key={s.log_id} send={s}
                                       colour="border-muted-foreground/20 bg-secondary/20" />)}
          </div>

          {/* Col 2 : Ouverts */}
          <div className="space-y-3" data-testid="col-opened">
            <div className="flex items-center gap-2 border-b-2 border-emerald-500/60 pb-2">
              <Eye className="h-4 w-4 text-emerald-500" />
              <p className="font-display font-bold text-sm">Ouverts (à relancer)</p>
              <Badge variant="outline" className="ml-auto rounded-sm border-emerald-500/60 text-emerald-500">
                {opened.length}
              </Badge>
            </div>
            {opened.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Aucun devis lu sans signature.
              </p>
            )}
            {opened.map(s => <Card key={s.log_id} send={s}
                                    colour="border-emerald-500/30 bg-emerald-500/5" />)}
          </div>

          {/* Col 3 : Signés */}
          <div className="space-y-3" data-testid="col-signed">
            <div className="flex items-center gap-2 border-b-2 border-primary pb-2">
              <CheckCircle2 className="h-4 w-4 text-primary" />
              <p className="font-display font-bold text-sm">Signés</p>
              <Badge className="ml-auto rounded-sm bg-primary text-primary-foreground">
                {signed.length}
              </Badge>
            </div>
            {signed.length === 0 && (
              <p className="text-xs text-muted-foreground text-center py-6">
                Aucune signature pour l'instant.
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
            <DialogTitle>Convertir en facture</DialogTitle>
            <DialogDescription>
              Choisissez le taux de TVA à appliquer. Le montant TTC du devis est conservé
              ({fmtEur(invoiceSend?.total_ttc)}).
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <label className="text-xs text-muted-foreground">Taux de TVA</label>
            <div className="grid grid-cols-3 gap-2">
              {[["5.5", "5,5 % — 1ère nécessité"], ["10", "10 % — Rénovation"], ["20", "20 % — Neuf"]].map(([v, lbl]) => (
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
                    data-testid="invoice-vat-cancel">Annuler</Button>
            <Button className="rounded-sm gap-2" onClick={convertToInvoice}
                    disabled={!!invoicing} data-testid="invoice-vat-confirm">
              <Receipt className="h-4 w-4" /> Créer la facture
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!billQuote} onOpenChange={(o) => !o && setBillQuote(null)}>
        <DialogContent className="max-w-lg" data-testid="billing-modal">
          <DialogHeader>
            <DialogTitle>Décompte général — {billQuote?.number || billQuote?.title}</DialogTitle>
            <DialogDescription>Facturez au prorata (situation) ou le solde. Les acomptes déjà facturés sont pris en compte.</DialogDescription>
          </DialogHeader>
          {recap ? (
            <div className="space-y-3 text-sm">
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="surface p-2 rounded-sm"><p className="num font-bold">{eur(recap.quote.ttc)}</p><p className="text-[11px] text-muted-foreground">Devis TTC</p></div>
                <div className="surface p-2 rounded-sm"><p className="num font-bold text-emerald-500">{eur(recap.billed_ttc)}</p><p className="text-[11px] text-muted-foreground">Déjà facturé</p></div>
                <div className="surface p-2 rounded-sm"><p className="num font-bold text-primary">{eur(recap.remaining_ttc)}</p><p className="text-[11px] text-muted-foreground">Reste à facturer</p></div>
              </div>
              <div className="text-xs text-muted-foreground">Avancement facturé : {recap.progress_pct}%</div>
              {recap.invoices.length > 0 && (
                <div className="border border-border rounded-sm divide-y divide-border max-h-32 overflow-auto" data-testid="billing-recap-list">
                  {recap.invoices.map((i) => (
                    <div key={i.doc_id} className="flex justify-between px-3 py-1.5 text-xs">
                      <span>{i.number || "—"} · {{ deposit: "Acompte", situation: "Situation", balance: "Solde" }[i.source] || "Facture"}</span>
                      <span className="num">{eur(i.ttc)}</span>
                    </div>
                  ))}
                </div>
              )}
              <div className="rounded-sm border border-border p-3 space-y-2">
                <p className="font-semibold text-xs uppercase tracking-wide">Nouvelle facture de situation</p>
                <div className="flex items-end gap-3">
                  <label className="flex-1 text-xs">Avancement %
                    <input type="number" min="1" max="100" value={sitPct} onChange={(e) => setSitPct(e.target.value)}
                           className="mt-1 w-full h-9 rounded-sm border border-border bg-background px-2" data-testid="billing-sit-pct" />
                  </label>
                  <label className="flex-1 text-xs">Déduction acompte %
                    <input type="number" min="0" max="100" value={sitDeduct} onChange={(e) => setSitDeduct(e.target.value)}
                           className="mt-1 w-full h-9 rounded-sm border border-border bg-background px-2" data-testid="billing-sit-deduct" />
                  </label>
                  <Button size="sm" className="h-9" onClick={makeSituation} data-testid="billing-make-situation">Créer situation</Button>
                </div>
                <p className="text-[11px] text-muted-foreground">0% = facture normale sans déduction d'acompte.</p>
              </div>
            </div>
          ) : <p className="text-sm text-muted-foreground py-6 text-center">Chargement du décompte…</p>}
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setBillQuote(null)}>Fermer</Button>
            <Button onClick={makeBalance} data-testid="billing-make-balance">Facturer le solde</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
