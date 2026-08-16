import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { FileText, Plus, FileSignature, Download, Lock, ArrowRight, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import { api, eur } from "@/lib/api";
import { useBilling } from "@/context/BillingContext";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

const STATUS = {
  draft: { label: "Brouillon", cls: "bg-secondary text-muted-foreground" },
  sent: { label: "Émise", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  issued: { label: "Émise", cls: "bg-blue-500/15 text-blue-600 dark:text-blue-400" },
  partial: { label: "Partiel", cls: "bg-amber-500/15 text-amber-600 dark:text-amber-400" },
  paid: { label: "Payée", cls: "bg-primary/15 text-primary" },
  overdue: { label: "En retard", cls: "bg-red-500/15 text-red-600 dark:text-red-400" },
};

const StatusBadge = ({ s }) => {
  const cfg = STATUS[s] || STATUS.draft;
  return <span className={`px-2.5 py-1 rounded-sm text-[11px] font-semibold uppercase tracking-wide ${cfg.cls}`}>{cfg.label}</span>;
};

export default function Invoices() {
  const nav = useNavigate();
  const { tier } = useBilling();
  const { user } = useAuth();
  const isProBusiness = tier === "pro_business" || user?.role === "admin";
  const [invoices, setInvoices] = useState([]);
  const [quotes, setQuotes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [convOpen, setConvOpen] = useState(false);
  const [busyId, setBusyId] = useState("");

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
    } catch { toast.error("Génération PDF impossible"); }
  };

  const convertQuote = async (q) => {
    setBusyId(q.doc_id);
    try {
      const { data } = await api.post(`/documents/${q.doc_id}/to-invoice`, { mode: "total", pct: 100 });
      toast.success("Facture créée depuis le devis " + (q.number || ""));
      setConvOpen(false);
      nav(`/devis-editeur/${data.doc_id}`);
    } catch { toast.error("Conversion impossible"); }
    finally { setBusyId(""); }
  };

  if (!isProBusiness) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 mb-6">
          <Lock className="h-6 w-6 text-primary" />
        </div>
        <h1 className="font-display text-3xl font-extrabold tracking-tight">Facturation Pro Business</h1>
        <p className="mt-4 text-muted-foreground max-w-xl mx-auto">
          La gestion des factures (création, conversion de devis, suivi des paiements et
          facturation électronique) est réservée au plan <strong>Pro Business</strong>.
        </p>
        <Button className="mt-8 rounded-sm gap-2" data-testid="invoices-upgrade-btn" onClick={() => nav("/tarifs")}>
          Passer à Pro Business <ArrowRight className="h-4 w-4" />
        </Button>
      </div>
    );
  }

  const totalDue = invoices.filter(i => i.status !== "paid").reduce((s, i) => s + (i.totals?.ttc || 0) - (i.paid || 0), 0);

  return (
    <div className="max-w-6xl mx-auto px-4 py-10" data-testid="invoices-page">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <SectionTitle over="Facturation" title="Mes factures" />
        <div className="flex flex-wrap gap-2">
          <Dialog open={convOpen} onOpenChange={setConvOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="rounded-sm gap-2" data-testid="invoice-from-quote-btn">
                <FileSignature className="h-4 w-4" /> Facturer un devis
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader><DialogTitle>Créer une facture depuis un devis</DialogTitle></DialogHeader>
              <div className="max-h-[60vh] overflow-y-auto space-y-2 mt-2">
                {quotes.length === 0 && <p className="text-sm text-muted-foreground">Aucun devis disponible.</p>}
                {quotes.map((q) => (
                  <button key={q.doc_id} disabled={busyId === q.doc_id}
                    onClick={() => convertQuote(q)} data-testid={`convert-quote-${q.doc_id}`}
                    className="w-full flex items-center justify-between gap-3 p-3 rounded-sm border border-border hover:border-primary/40 hover:bg-secondary/40 transition-colors text-left">
                    <div>
                      <p className="font-semibold text-sm">{q.number || "Devis"} · {q.title || "Sans titre"}</p>
                      <p className="text-xs text-muted-foreground">{q.client?.name || "Client non défini"}</p>
                    </div>
                    <span className="num font-bold text-primary">{eur(q.totals?.ttc || 0)}</span>
                  </button>
                ))}
              </div>
            </DialogContent>
          </Dialog>
          <Button className="rounded-sm gap-2" data-testid="new-invoice-btn"
            onClick={() => nav("/devis-editeur?type=invoice")}>
            <Plus className="h-4 w-4" /> Nouvelle facture
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-8">
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold">{invoices.length}</p><p className="text-xs text-muted-foreground mt-1">Factures</p></div>
        <div className="surface p-4 rounded-sm"><p className="num text-2xl font-extrabold text-primary">{invoices.filter(i => i.status === "paid").length}</p><p className="text-xs text-muted-foreground mt-1">Payées</p></div>
        <div className="surface p-4 rounded-sm border-amber-500/30"><p className="num text-2xl font-extrabold text-amber-600 dark:text-amber-400">{eur(totalDue)}</p><p className="text-xs text-muted-foreground mt-1">Reste à encaisser</p></div>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Chargement…</p>
      ) : invoices.length === 0 ? (
        <div className="surface rounded-sm p-12 text-center">
          <FileText className="h-10 w-10 mx-auto text-muted-foreground/50" />
          <p className="mt-4 font-semibold">Aucune facture pour le moment</p>
          <p className="text-sm text-muted-foreground mt-1">Créez une facture ou transformez un devis existant.</p>
        </div>
      ) : (
        <div className="grid gap-3" data-testid="invoices-list">
          {invoices.map((inv, idx) => (
            <motion.div key={inv.doc_id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.03 }}
              className="surface rounded-sm p-4 flex flex-wrap items-center gap-4" data-testid={`invoice-row-${inv.doc_id}`}>
              <div className="min-w-0">
                <p className="font-display font-semibold">{inv.number || "Brouillon"} · {inv.title || "Sans titre"}</p>
                <button onClick={() => inv.client_id && nav(`/clients/${inv.client_id}`)}
                  className="text-xs text-muted-foreground inline-flex items-center gap-1 hover:text-primary transition-colors"
                  data-testid={`invoice-client-${inv.doc_id}`}>
                  <User className="h-3 w-3" /> {inv.client?.name || "Client non défini"}
                </button>
              </div>
              <StatusBadge s={inv.status} />
              <span className="num ml-auto text-lg font-bold text-primary">{eur(inv.totals?.ttc || 0)}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" className="rounded-sm gap-1.5" data-testid={`invoice-open-${inv.doc_id}`}
                  onClick={() => nav(`/devis-editeur/${inv.doc_id}`)}>Ouvrir</Button>
                <Button size="sm" variant="ghost" className="rounded-sm gap-1.5" data-testid={`invoice-pdf-${inv.doc_id}`}
                  onClick={() => downloadPdf(inv)}><Download className="h-4 w-4" /></Button>
              </div>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
