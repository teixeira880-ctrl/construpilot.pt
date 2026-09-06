import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, Plus, Download, CreditCard, FileMinus, Receipt, FileText, ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";

const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const STATUS_KEY = {
  draft: "crm.st_e_draft", sent: "crm.st_e_sent", signed: "crm.st_e_signed", refused: "crm.st_e_refused",
  partial: "crm.st_partial", paid: "crm.st_paid", issued: "crm.st_issued",
};
const STATUS_COLOR = {
  signed: "text-primary border-primary/50", paid: "text-primary border-primary/50",
  refused: "text-destructive border-destructive/40", partial: "text-amber-500 border-amber-500/40",
};

export default function ClientDetail() {
  const { clientId } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const { t } = useI18n();
  const [client, setClient] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const [convert, setConvert] = useState(null);
  const [mode, setMode] = useState("total");
  const [pct, setPct] = useState(50);
  const [payFor, setPayFor] = useState(null);
  const [payAmount, setPayAmount] = useState("");
  const [payMethod, setPayMethod] = useState("virement");

  const load = async () => {
    setLoading(true);
    try {
      const [{ data: c }, { data: s }] = await Promise.all([
        api.get(`/clients/${clientId}`),
        api.get(`/documents/client-summary/${clientId}`),
      ]);
      setClient(c); setData(s);
    } catch { toast.error(t("crm.not_found")); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (user) load(); /* eslint-disable-next-line */ }, [user, clientId]);

  const pdf = async (docId) => {
    try {
      const res = await api.get(`/documents/${docId}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a"); a.href = url; a.download = `${docId}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error(t("crm.pdf_fail")); }
  };
  const doConvert = async () => {
    try {
      const { data: inv } = await api.post(`/documents/${convert.doc_id}/to-invoice`,
        { mode, pct: Number(pct) });
      toast.success(t("crm.invoice_num_created").replace("{n}", inv.number));
      setConvert(null);
      nav(`/devis-editeur/${inv.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.conv_fail")); }
  };
  const doPay = async () => {
    if (!Number(payAmount)) return toast.error(t("crm.amount_invalid"));
    try {
      await api.post(`/documents/${payFor.doc_id}/payments`,
        { amount: Number(payAmount), method: payMethod });
      toast.success(t("crm.payment_saved"));
      setPayFor(null); setPayAmount(""); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.err")); }
  };
  const doAvoir = async (inv) => {
    if (!window.confirm(t("crm.confirm_avoir").replace("{n}", inv.number || ""))) return;
    try {
      const { data: av } = await api.post(`/documents/${inv.doc_id}/to-credit-note`);
      toast.success(t("crm.avoir_created").replace("{n}", av.number)); load();
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.err")); }
  };

  if (!user) return <div className="surface p-10 text-center">{t("crm.login")}</div>;
  if (loading || !client || !data) return <div className="surface p-10 text-center animate-pulse">{t("crm.loading")}</div>;

  const name = [client.first_name, client.last_name].filter(Boolean).join(" ") || client.company || client.email;
  const k = data.kpis;
  const signed = data.quotes.filter((q) => q.status === "signed");
  const refused = data.quotes.filter((q) => q.status === "refused");
  const otherQ = data.quotes.filter((q) => !["signed", "refused"].includes(q.status));

  const St = ({ s }) => (
    <Badge variant="outline" className={`rounded-sm text-[10px] ${STATUS_COLOR[s] || ""}`}>
      {t(STATUS_KEY[s] || "") || s}
    </Badge>
  );

  const Row = ({ d, extra }) => (
    <div className="flex items-center gap-2 px-3 py-2.5" data-testid={`doc-row-${d.doc_id}`}>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium truncate">{d.title || d.number || "—"}</p>
        <p className="text-[11px] text-muted-foreground num">
          {d.number || "brouillon"} · {(d.created_at || "").slice(0, 10)}
          {d.doc_type === "invoice" && d.paid > 0 && ` · payé ${eur(d.paid)}`}
        </p>
      </div>
      <St s={d.status} />
      <span className="num font-bold text-sm w-24 text-right">{eur(d.totals?.ttc)}</span>
      <div className="flex gap-1 shrink-0">
        <Button size="icon" variant="ghost" className="h-7 w-7" title="Abrir"
                onClick={() => nav(`/devis-editeur/${d.doc_id}`)} data-testid={`doc-open-${d.doc_id}`}>
          <ExternalLink className="h-3.5 w-3.5" />
        </Button>
        <Button size="icon" variant="ghost" className="h-7 w-7" title="PDF"
                onClick={() => pdf(d.doc_id)} data-testid={`doc-pdf-${d.doc_id}`}>
          <Download className="h-3.5 w-3.5" />
        </Button>
        {extra}
      </div>
    </div>
  );

  const Section = ({ icon: Icon, title, count, children }) => (
    <div className="surface">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
        <Icon className="h-4 w-4 text-primary" />
        <p className="font-display font-bold text-sm">{title}</p>
        <Badge variant="outline" className="ml-auto rounded-sm">{count}</Badge>
      </div>
      <div className="divide-y divide-border">{children}</div>
    </div>
  );

  return (
    <div className="grid gap-6">
      <button onClick={() => nav("/clients")} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 w-fit" data-testid="clientdetail-back">
        <ArrowLeft className="h-3 w-3" /> {t("crm.cd_back")}
      </button>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-sm bg-primary/10 text-primary grid place-items-center font-display text-xl font-extrabold">
            {(name || "?").slice(0, 1).toUpperCase()}
          </div>
          <div>
            <h1 className="font-display text-2xl font-bold tracking-tight" data-testid="clientdetail-name">{name}</h1>
            <p className="text-sm text-muted-foreground">
              {[client.company, client.email, client.phone,
                [client.address, client.postal_code, client.city].filter(Boolean).join(" ")]
                .filter(Boolean).join(" · ")}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button className="rounded-sm gap-2" onClick={() => nav(`/devis-editeur?client=${clientId}`)} data-testid="clientdetail-new-quote">
            <Plus className="h-4 w-4" /> {t("crm.new_quote")}
          </Button>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3" data-testid="clientdetail-kpis">
        {[
          [t("crm.kpi_ca_signed"), k.ca_signed], [t("crm.kpi_invoiced"), k.invoiced], [t("crm.kpi_collected"), k.paid],
          [t("crm.kpi_to_invoice"), k.to_invoice], [t("crm.kpi_to_collect"), k.to_collect],
        ].map(([lbl, val], i) => (
          <div key={i} className="surface p-4">
            <p className="overline">{lbl}</p>
            <p className={`num font-display text-2xl font-extrabold mt-1 ${i >= 3 ? "text-primary" : ""}`}>{eur(val)}</p>
          </div>
        ))}
      </div>

      {/* Devis signés */}
      <Section icon={FileText} title={t("crm.sec_signed")} count={signed.length}>
        {signed.length === 0 && <p className="text-sm text-muted-foreground px-4 py-4">{t("crm.none_signed")}</p>}
        {signed.map((d) => (
          <Row key={d.doc_id} d={d} extra={
            <Button size="sm" variant="outline" className="rounded-sm gap-1 h-7 text-[11px] border-primary/40 text-primary hover:bg-primary hover:text-primary-foreground"
                    onClick={() => { setConvert(d); setMode(d.deposit_pct > 0 ? "acompte" : "total"); setPct(d.deposit_pct > 0 ? d.deposit_pct : 30); }}
                    data-testid={`convert-invoice-${d.doc_id}`}>
              <Receipt className="h-3.5 w-3.5" /> {t("crm.bill_btn")}
            </Button>
          } />
        ))}
      </Section>

      {/* Factures */}
      <Section icon={Receipt} title={t("crm.sec_invoices")} count={data.invoices.length}>
        {data.invoices.length === 0 && <p className="text-sm text-muted-foreground px-4 py-4">{t("crm.none_invoices")}</p>}
        {data.invoices.map((d) => (
          <Row key={d.doc_id} d={d} extra={<>
            {d.status !== "paid" && (
              <Button size="sm" variant="outline" className="rounded-sm gap-1 h-7 text-[11px]"
                      onClick={() => { setPayFor(d); setPayAmount(String(d.remaining_due ?? d.totals?.ttc ?? "")); }}
                      data-testid={`pay-${d.doc_id}`}>
                <CreditCard className="h-3.5 w-3.5" /> {t("crm.payment_btn")}
              </Button>
            )}
            <Button size="icon" variant="ghost" className="h-7 w-7 text-amber-500" title={t("crm.sec_credit")}
                    onClick={() => doAvoir(d)} data-testid={`avoir-${d.doc_id}`}>
              <FileMinus className="h-3.5 w-3.5" />
            </Button>
          </>} />
        ))}
      </Section>

      {/* Avoirs */}
      {data.credit_notes.length > 0 && (
        <Section icon={FileMinus} title={t("crm.sec_credit")} count={data.credit_notes.length}>
          {data.credit_notes.map((d) => <Row key={d.doc_id} d={d} />)}
        </Section>
      )}

      {/* Devis refusés / brouillons */}
      {(refused.length > 0 || otherQ.length > 0) && (
        <Section icon={FileText} title={t("crm.sec_other")} count={refused.length + otherQ.length}>
          {[...refused, ...otherQ].map((d) => <Row key={d.doc_id} d={d} />)}
        </Section>
      )}

      {/* Dialog conversion facture */}
      <Dialog open={!!convert} onOpenChange={(o) => !o && setConvert(null)}>
        <DialogContent className="max-w-md" data-testid="convert-dialog">
          <DialogHeader><DialogTitle>{t("crm.convert_title")}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div>
              <Label>{t("crm.billing_type")}</Label>
              <select value={mode} onChange={(e) => setMode(e.target.value)} data-testid="convert-mode"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                <option value="total">{t("crm.mode_total")}</option>
                <option value="acompte">{t("crm.mode_acompte")}</option>
                <option value="prorata">{t("crm.mode_prorata")}</option>
                <option value="detailed">{t("crm.mode_detailed")}</option>
              </select>
            </div>
            {(mode === "prorata" || mode === "acompte") && (
              <div>
                <Label>{mode === "acompte" ? t("crm.pct_acompte") : t("crm.pct_prorata")}</Label>
                <Input type="number" min="1" max="100" value={pct} onChange={(e) => setPct(e.target.value)}
                       className="rounded-sm num mt-1 max-w-[120px]" data-testid="convert-pct" />
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              {mode === "detailed"
                ? t("crm.hint_detailed")
                : mode === "acompte"
                  ? t("crm.hint_acompte")
                  : mode === "prorata"
                    ? t("crm.hint_prorata")
                    : t("crm.hint_total")}
            </p>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConvert(null)} className="rounded-sm">{t("crm.cancel")}</Button>
            <Button onClick={doConvert} className="rounded-sm" data-testid="convert-confirm">{t("crm.create_invoice")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog paiement */}
      <Dialog open={!!payFor} onOpenChange={(o) => !o && setPayFor(null)}>
        <DialogContent className="max-w-md" data-testid="payment-dialog">
          <DialogHeader><DialogTitle>{t("crm.payment_title")}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <p className="text-sm text-muted-foreground">
              {t("crm.sec_invoices")} {payFor?.number} · {t("crm.remaining")} <b>{eur(payFor?.remaining_due ?? payFor?.totals?.ttc)}</b>
            </p>
            <div>
              <Label>{t("crm.amount")}</Label>
              <Input type="number" step="0.01" value={payAmount} onChange={(e) => setPayAmount(e.target.value)}
                     className="rounded-sm num mt-1" data-testid="payment-amount" />
            </div>
            <div>
              <Label>{t("crm.method")}</Label>
              <select value={payMethod} onChange={(e) => setPayMethod(e.target.value)} data-testid="payment-method"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {[["virement", "crm.m_virement"], ["chèque", "crm.m_cheque"], ["espèces", "crm.m_especes"], ["carte", "crm.m_carte"], ["autre", "crm.m_autre"]].map(([m, key]) => <option key={m} value={m}>{t(key)}</option>)}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setPayFor(null)} className="rounded-sm">{t("crm.cancel")}</Button>
            <Button onClick={doPay} className="rounded-sm" data-testid="payment-confirm">{t("crm.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
