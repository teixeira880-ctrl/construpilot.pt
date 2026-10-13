import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { FileText, Plus, FileSignature, Download, Lock, ArrowRight, User, FileCheck2, ShieldCheck, ShieldAlert, Loader2, TrendingUp, Trash2, Network } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { useConfirm } from "@/components/ConfirmProvider";
import { ImportDocumentsDialog } from "@/components/ImportDocumentsDialog";
import { api, eur } from "@/lib/api";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { toast } from "sonner";

export const NoAccess = ({ title = "Acesso não autorizado" }) => (
  <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="no-access">
    <div className="h-14 w-14 rounded-xl bg-red-500/10 grid place-items-center mx-auto mb-5"><Lock className="h-7 w-7 text-red-500" /></div>
    <h1 className="font-display text-3xl font-bold">{title}</h1>
    <p className="text-muted-foreground mt-3">A sua função na empresa não dá acesso a este módulo. Contacte o responsável da sua empresa.</p>
  </div>
);

const STATUS = {
  draft: { key: "crm.st_draft", cls: "bg-secondary text-muted-foreground" },
  sent: { key: "crm.st_sent", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  issued: { key: "crm.st_sent", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  partial: { key: "crm.st_partial", cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  paid: { key: "crm.st_paid", cls: "bg-primary/15 text-primary" },
  overdue: { key: "crm.st_overdue", cls: "bg-red-500/15 text-red-600 dark:text-red-400" },
};

const StatusBadge = ({ s, t }) => {
  const cfg = STATUS[s] || STATUS.draft;
  return <span className={`px-2.5 py-1 rounded-sm text-[11px] font-semibold uppercase tracking-wide ${cfg.cls}`}>{t(cfg.key)}</span>;
};

export default function Invoices() {
  const nav = useNavigate();
  const { tier } = useBilling();
  const { can, in_org } = usePermissions();
  const { user } = useAuth();
  const { t } = useI18n();
  const confirm = useConfirm();
  const isProBusiness = tier === "pro_business" || user?.role === "admin" || !!user?.invoicing_addon;

  const activateAddon = async () => {
    try {
      const { data } = await api.post("/billing/checkout", {
        plan_id: "invoicing_addon_monthly", origin_url: window.location.origin,
      });
      if (data?.url) window.location.href = data.url;
    } catch { toast.error(t("crm.addon_fail")); }
  };
  const [invoices, setInvoices] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [convOpen, setConvOpen] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [fxBusyId, setFxBusyId] = useState("");
  const [fxReport, setFxReport] = useState(null);
  const [fxOpen, setFxOpen] = useState(false);
  const [selected, setSelected] = useState([]);
  const [batchBusy, setBatchBusy] = useState(false);

  const toggleSel = (id) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id]);
  const issueBatch = async () => {
    setBatchBusy(true);
    try {
      const { data } = await api.post("/documents/issue-batch", { doc_ids: selected });
      toast.success(`${data.issued}fatura(s) emitida(s) ·${data.conformes} conforme(s) EN16931`);
      setSelected([]); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Emissão em lote impossível"); }
    finally { setBatchBusy(false); }
  };

  const load = () => {
    Promise.all([
      api.get("/documents?doc_type=invoice"),
      api.get("/documents?doc_type=quote"),
    ]).then(([inv, q]) => {
      setInvoices(inv.data.documents || []);
      setQuotes(q.data.documents || []);
    }).catch(() => {}).finally(() => setLoading(false));
  };

  useEffect(() => { if (isProBusiness) load(); else setLoading(false); }, [isProBusiness]);

  const downloadPdf = async (doc) => {
    try {
      const res = await api.get(`/documents/${doc.doc_id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${doc.number || "facture"}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error(t("crm.pdf_fail")); }
  };

  const downloadFacturx = async (doc) => {
    try {
      const res = await api.get(`/documents/${doc.doc_id}/factur-x`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `${doc.number || "facture"}-facturx.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success(t("crm.facturx_ok"));
      // Rafraîchit le statut de conformité ; alerte si repli local (SIRET/TVA manquants…)
      try {
        const { data: fresh } = await api.get(`/documents/${doc.doc_id}`);
        const v = fresh?.facturx_validation;
        if (v?.source === "local" && v?.hint) {
          toast.warning(v.hint, { duration: 9000 });
        }
        load();
      } catch { /* non bloquant */ }
    } catch { toast.error(t("crm.facturx_fail")); }
  };

  const validateFacturx = async (doc) => {
    setFxBusyId(doc.doc_id);
    try {
      const { data } = await api.post(`/documents/${doc.doc_id}/factur-x/validate`);
      setFxReport({ ...data, number: doc.number });
      setFxOpen(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Validação da fatura eletrónica impossível");
    } finally {
      setFxBusyId("");
    }
  };

  const convertQuote = async (q) => {
    setBusyId(q.doc_id);
    try {
      const { data } = await api.post(`/documents/${q.doc_id}/to-invoice`, { mode: "total", pct: 100 });
      toast.success(t("crm.invoice_created").replace("{n}", q.number || ""));
      setConvOpen(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.conv_fail")); }
    finally { setBusyId(""); }
  };

  const removeInvoice = async (inv) => {
    if (!(await confirm({
      title: "Eliminar esta fatura?",
      description: `A fatura${inv.number || ""}será eliminada definitivamente.`,
      confirmLabel: "Eliminar",
    }))) return;
    try {
      await api.delete(`/documents/${inv.doc_id}`);
      toast.success("Fatura eliminada");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível eliminar"); }
  };

  if (!isProBusiness) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 mb-6">
          <Lock className="h-6 w-6 text-primary" />
        </div>
        <h1 className="font-display text-3xl font-extrabold tracking-tight">{t("crm.paywall_title")}</h1>
        <p className="mt-4 text-muted-foreground max-w-xl mx-auto">
          {t("crm.paywall_desc")}
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Button className="rounded-sm gap-2" data-testid="invoices-activate-addon-btn" onClick={activateAddon}>
            {t("crm.activate_addon")} <ArrowRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" className="rounded-sm gap-2" data-testid="invoices-upgrade-btn" onClick={() => nav("/tarifs")}>
            {t("crm.see_pb")}
          </Button>
        </div>
      </div>
    );
  }

  const totalDue = invoices.filter(i => i.status !== "paid").reduce((s, i) => s + (i.totals?.ttc || 0) - (i.paid || 0), 0);

  if (in_org && !can("factures")) return <NoAccess title="Faturas não autorizadas" />;

  return (
    <div className="max-w-6xl mx-auto px-4 py-10" data-testid="invoices-page">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <SectionTitle over={t("crm.inv_over")} title={t("crm.inv_title")} />
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" className="rounded-sm gap-2" data-testid="invoices-situations-link"
            onClick={() => nav("/situations")}>
            <TrendingUp className="h-4 w-4" /> Autos de medição
          </Button>
          <ImportDocumentsDialog triggerLabel="Importar PDFs" onImported={load} />
          <Dialog open={convOpen} onOpenChange={setConvOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="rounded-sm gap-2" data-testid="invoice-from-quote-btn">
                <FileSignature className="h-4 w-4" /> {t("crm.bill_quote")}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle>{t("crm.conv_dialog_title")}</DialogTitle></DialogHeader>
              <div className="max-h-[60vh] overflow-y-auto space-y-2 mt-2">
                {quotes.length === 0 && <p className="text-sm text-muted-foreground">{t("crm.no_quotes")}</p>}
                {quotes.map((q) => (
                  <button key={q.doc_id} disabled={busyId === q.doc_id}
                    onClick={() => convertQuote(q)} data-testid={`convert-quote-${q.doc_id}`}
                    className="w-full flex items-center justify-between gap-3 p-3 rounded-sm border border-border hover:border-primary/40 hover:bg-secondary/40 transition-colors text-left">
                    <div>
                      <p className="font-semibold text-sm">{q.number || t("crm.quote_btn")} · {q.title || t("crm.untitled")}</p>
                      <p className="text-xs text-muted-foreground">{q.client?.name || t("crm.client_undef")}</p>
                    </div>
                    <span className="num font-bold text-primary">{eur(q.totals?.ttc || 0)}</span>
                  </button>
                ))}
              </div>
            </DialogContent>
          </Dialog>
          <Button className="rounded-sm gap-2" data-testid="new-invoice-btn"
            onClick={() => nav("/devis-editeur?type=invoice")}>
            <Plus className="h-4 w-4" /> {t("crm.new_invoice")}
          </Button>
        </div>
      </div>

      <button
        onClick={() => nav("/factures-electroniques")}
        className="w-full text-left surface rounded-sm p-4 mb-8 flex flex-wrap items-center gap-4 border-primary/30 hover:border-primary/60 hover:bg-primary/[0.03] transition-colors"
        data-testid="einvoicing-banner">
        <div className="h-11 w-11 rounded-lg bg-primary/10 grid place-items-center shrink-0">
          <Network className="h-5 w-5 text-primary" />
        </div>
        <div className="min-w-0">
          <p className="font-display font-semibold flex items-center gap-2">
            Faturação eletrónica (rede PDP)
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400">demo</span>
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">Receba, aceite ou recuse as suas faturas fornecedores através de uma plataforma certificada.</p>
        </div>
        <span className="ml-auto inline-flex items-center gap-1.5 text-sm font-semibold text-primary">
          Ouvrir <ArrowRight className="h-4 w-4" />
        </span>
      </button>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-8">
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{invoices.length}</p><p className="text-xs text-muted-foreground mt-1">{t("crm.kpi_invoices")}</p></div>
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold text-primary">{invoices.filter(i => i.status === "paid").length}</p><p className="text-xs text-muted-foreground mt-1">{t("crm.kpi_paid")}</p></div>
        <div className="surface p-4 rounded-sm border-amber-500/30"><p className="num text-2xl font-extrabold text-amber-600 dark:text-amber-400">{eur(totalDue)}</p><p className="text-xs text-muted-foreground mt-1">{t("crm.kpi_due")}</p></div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">{t("crm.loading")}</p>
      ) : invoices.length === 0 ? (
        <div className="surface rounded-sm p-12 text-center">
          <FileText className="h-10 w-10 mx-auto text-muted-foreground/50" />
          <p className="mt-4 font-semibold">{t("crm.inv_empty_title")}</p>
          <p className="text-sm text-muted-foreground mt-1">{t("crm.inv_empty_sub")}</p>
        </div>
      ) : (
        <div className="grid gap-3" data-testid="invoices-list">
          {selected.length > 0 && (
            <div className="surface rounded-sm p-3 flex flex-wrap items-center gap-3 border-primary/40 sticky top-16 z-10" data-testid="batch-bar">
              <span className="text-sm font-semibold">{selected.length} selecionado(s)</span>
              <span className="text-xs text-muted-foreground">Emissão + controlo de conformidade Factur-X em lote</span>
              <div className="ml-auto flex gap-2">
                <Button size="sm" variant="ghost" className="rounded-sm" onClick={() => setSelected([])} data-testid="batch-clear">Cancelar</Button>
                <Button size="sm" className="rounded-sm gap-2" disabled={batchBusy} onClick={issueBatch} data-testid="batch-issue-btn">
                  {batchBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileSignature className="h-4 w-4" />} Emitir a seleção
                </Button>
              </div>
            </div>
          )}
          {invoices.map((inv, idx) => (
            <motion.div key={inv.doc_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              className="surface rounded-sm p-4 flex flex-wrap items-center gap-4" data-testid={`invoice-row-${inv.doc_id}`}>
              {(inv.status === "draft" || !inv.number) && (
                <input type="checkbox" checked={selected.includes(inv.doc_id)} onChange={() => toggleSel(inv.doc_id)}
                  className="h-4 w-4 accent-primary cursor-pointer" data-testid={`invoice-select-${inv.doc_id}`} title="Selecionar para emissão agrupada" />
              )}
              {inv.plan_id && (
                <img src={`${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${inv.plan_id}/thumb`} alt="" loading="lazy"
                     onError={(e) => { e.currentTarget.style.display = "none"; }}
                     className="w-12 h-12 object-cover rounded-sm border border-border shrink-0 bg-muted/40"
                     data-testid={`invoice-thumb-${inv.doc_id}`} />
              )}
              <div className="min-w-0">
                <p className="font-display font-semibold">{inv.number || t("crm.st_draft")} · {inv.title || t("crm.untitled")}</p>
                <button onClick={() => inv.client_id && nav(`/clients/${inv.client_id}`)}
                  className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-primary transition-colors"
                  data-testid={`invoice-client-${inv.doc_id}`}>
                  <User className="h-3 w-3" /> {inv.client?.name || t("crm.client_undef")}
                </button>
              </div>
              <StatusBadge s={inv.status} t={t} />
              {inv.facturx_validation && (
                inv.facturx_validation.valid ? (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] font-semibold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400" data-testid={`facturx-badge-ok-${inv.doc_id}`}>
                    <ShieldCheck className="h-3.5 w-3.5" /> Conforme EN16931
                  </span>
                ) : inv.facturx_validation.source === "local" ? (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400" data-testid={`facturx-badge-local-${inv.doc_id}`}>
                    <FileCheck2 className="h-3.5 w-3.5" /> Fatura eletrónica BASIC · não certificada
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-1 rounded-sm text-[11px] font-semibold bg-red-500/15 text-red-600 dark:text-red-400" data-testid={`facturx-badge-ko-${inv.doc_id}`}>
                    <ShieldAlert className="h-3.5 w-3.5" /> Não conforme
                  </span>
                )
              )}
              <span className="num ml-auto text-lg font-bold text-primary">{eur(inv.totals?.ttc || 0)}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="rounded-sm gap-1.5" data-testid={`invoice-open-${inv.doc_id}`}
                  onClick={() => nav(`/devis-editeur/${inv.doc_id}`)}>{t("crm.open")}</Button>
                <Button size="sm" variant="ghost" className="rounded-sm gap-1.5" data-testid={`invoice-pdf-${inv.doc_id}`}
                  onClick={() => downloadPdf(inv)}><Download className="h-4 w-4" /></Button>
                <Button size="sm" variant="outline" className="rounded-sm gap-1.5 text-primary border-primary/30" data-testid={`invoice-facturx-${inv.doc_id}`}
                  onClick={() => downloadFacturx(inv)}><FileCheck2 className="h-4 w-4" /> Factur-X</Button>
                <Button size="sm" variant="ghost" className="rounded-sm gap-1.5" disabled={fxBusyId === inv.doc_id} data-testid={`invoice-facturx-validate-${inv.doc_id}`}
                  onClick={() => validateFacturx(inv)}>
                  {fxBusyId === inv.doc_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                  {inv.facturx_validation && (
                    <span className={`h-2 w-2 rounded-full ${inv.facturx_validation.valid ? "bg-emerald-500" : inv.facturx_validation.source === "local" ? "bg-amber-500" : "bg-red-500"}`} />
                  )}
                  Valider
                </Button>
                <Button size="sm" variant="ghost" className="rounded-sm h-8 w-8 p-0 text-muted-foreground hover:text-red-600" data-testid={`invoice-delete-${inv.doc_id}`}
                  onClick={() => removeInvoice(inv)}><Trash2 className="h-4 w-4" /></Button>
              </div>
            </motion.div>
          ))}
        </div>
      )}

      <Dialog open={fxOpen} onOpenChange={setFxOpen}>
        <DialogContent className="max-w-lg" data-testid="facturx-report-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {fxReport?.valid ? (
                <><ShieldCheck className="h-5 w-5 text-emerald-500" /> Fatura conforme</>
              ) : (
                <><ShieldAlert className="h-5 w-5 text-red-500" /> Não conformidades detetadas</>
              )}
            </DialogTitle>
          </DialogHeader>
          {fxReport && (
            <div className="space-y-4 mt-1" data-testid="facturx-report-body">
              <div className={`rounded-sm p-4 border ${fxReport.valid ? "border-emerald-500/30 bg-emerald-500/5" : "border-red-500/30 bg-red-500/5"}`}>
                <p className="text-sm">
                  Fatura <b>{fxReport.number || "—"}</b> · perfil detetado{" "}
                  <b>{fxReport.profile || "inconnu"}</b>
                </p>
                <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
                  <span><b className="text-red-600 dark:text-red-400">{fxReport.error_count}</b> erro(s)</span>
                  <span><b className="text-amber-600 dark:text-amber-400">{fxReport.warning_count}</b> avertissement(s)</span>
                </div>
              </div>
              {fxReport.valid ? (
                <p className="text-sm text-muted-foreground">
                  O ficheiro Factur-X respeita a base XSD + Schematron EN16931. Diagnóstico técnico — não vale aceitação por uma Plataforma Aprovada.
                </p>
              ) : (
                <div className="max-h-[45vh] overflow-y-auto space-y-2" data-testid="facturx-issues">
                  {fxReport.issues?.map((it, i) => (
                    <div key={i} className="rounded-sm border border-border p-3 text-sm">
                      <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${it.severity === "error" ? "bg-red-500/15 text-red-600 dark:text-red-400" : "bg-amber-500/15 text-amber-600 dark:text-amber-400"}`}>{it.severity}</span>
                        {it.code && <span className="num text-xs text-muted-foreground">{it.code}</span>}
                        {it.stage && <span className="text-[10px] text-muted-foreground">· {it.stage}</span>}
                      </div>
                      <p className="mt-1.5 text-muted-foreground">{it.message}</p>
                    </div>
                  ))}
                  {(!fxReport.issues || fxReport.issues.length === 0) && (
                    <p className="text-sm text-muted-foreground">Nenhum detalhe de erro fornecido pelo validador.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
