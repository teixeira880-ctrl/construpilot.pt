import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Send, Eye, CheckCircle2, FileText, Copy, ExternalLink, RefreshCw, Mail,
  Download, FileDown, Star,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SectionTitle } from "@/components/Bits";
import { RevenueChart } from "@/components/RevenueChart";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Link } from "react-router-dom";

const MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin",
  "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

export default function QuoteTracking() {
  const { user } = useAuth();
  const [sends, setSends] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [completed, setCompleted] = useState(new Set());
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
    try {
      const { data } = await api.post(
        `/takeoffs/${send.plan_id}/quote-sends/${send.log_id}/signature-link`
      );
      const fullUrl = data.url.startsWith("http") ? data.url
        : `${window.location.origin}${data.url}`;
      await navigator.clipboard.writeText(fullUrl);
      toast.success("Lien de signature copié");
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
      </div>

      {/* Chiffre d'affaires mensuel */}
      <RevenueChart />

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
    </div>
  );
}
