import { useEffect, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { FileText, CheckCircle2, Clock, Mail, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

/**
 * Client portal — lists every quote a client received across all Pros,
 * accessible via a signed HMAC token embedded in each outgoing devis email.
 *
 * URL : `/mes-devis?token=<base64email>.<sig>`
 */
export default function ClientPortal() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [state, setState] = useState({ loading: true, error: null, data: null });

  useEffect(() => {
    if (!token) {
      setState({ loading: false, error: "Nenhum token fornecido.", data: null });
      return;
    }
    api
      .get(`/quotes/client-portal/${token}`)
      .then(({ data }) => setState({ loading: false, error: null, data }))
      .catch((e) => setState({
        loading: false,
        error: e?.response?.data?.detail || "Lien invalide ou expiré.",
        data: null,
      }));
  }, [token]);

  if (state.loading) {
    return (
      <div className="mx-auto max-w-[900px] px-5 py-20 text-center text-sm text-muted-foreground">
        Chargement de vos devis…
      </div>
    );
  }

  if (state.error) {
    return (
      <div className="mx-auto max-w-[700px] px-5 py-20" data-testid="client-portal-error">
        <div className="surface p-10 text-center">
          <h1 className="font-display text-2xl font-bold">Lien invalide</h1>
          <p className="mt-3 text-sm text-muted-foreground">{state.error}</p>
          <p className="mt-6 text-xs text-muted-foreground">
            Demandez un nouveau lien à l'artisan qui vous a envoyé le devis.
          </p>
        </div>
      </div>
    );
  }

  const { email, quotes = [], count } = state.data || {};
  const signed = quotes.filter((q) => q.signed).length;
  const pending = count - signed;

  return (
    <div className="mx-auto max-w-[1100px] px-5 py-10" data-testid="client-portal">
      <div className="mb-8">
        <p className="overline text-primary">Mon espace client</p>
        <h1 className="mt-2 font-display text-3xl lg:text-4xl font-bold tracking-tight">
          Vos devis reçus
        </h1>
        <p className="mt-2 text-sm text-muted-foreground flex items-center gap-2">
          <Mail className="h-4 w-4" /> {email}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
        <Kpi label="Orçamentos recebidos" value={count} />
        <Kpi label="Signés" value={signed} accent />
        <Kpi label="En attente" value={pending} />
        <Kpi label="Total montant" value={
          `${quotes.reduce((s, q) => s + (q.total_ttc || 0), 0).toLocaleString("pt-PT")} €`
        } small />
      </div>

      {quotes.length === 0 && (
        <div className="surface p-16 text-center text-sm text-muted-foreground">
          Aucun devis reçu pour le moment.
        </div>
      )}

      <div className="grid gap-3">
        {quotes.map((q) => (
          <QuoteCard key={q.log_id} q={q} />
        ))}
      </div>

      <p className="mt-10 text-[11px] text-muted-foreground text-center">
        Ce portail est sécurisé — ce lien est unique et personnel à votre adresse email.
        <br />
        Envoyé par <b>ConstruPilot</b> pour le compte de vos artisans.
      </p>
    </div>
  );
}

function Kpi({ label, value, accent, small }) {
  return (
    <div className={`surface p-4 ${accent ? "border-primary/40 bg-primary/5" : ""}`}
         data-testid={`portal-kpi-${label}`}>
      <p className="text-[10px] text-muted-foreground uppercase tracking-widest">{label}</p>
      <p className={`num font-display font-extrabold mt-1 ${small ? "text-xl" : "text-2xl"} ${accent ? "text-primary" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function QuoteCard({ q }) {
  const dl = async () => {
    try {
      const base = process.env.REACT_APP_BACKEND_URL;
      const res = await fetch(`${base}/api/quotes/public/sign/${q.signature_token}/pdf`);
      if (!res.ok) throw new Error("PDF error");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `orcamento-${q.log_id}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { toast.error("Transferência impossível"); }
  };
  const status = q.signed ? "signed" : q.opened_at ? "opened" : "sent";
  const STATUS_MAP = {
    signed: { icon: CheckCircle2, label: "Signé", tone: "bg-green-500/15 text-green-600 border-green-500/40" },
    opened: { icon: Clock, label: "En attente signature", tone: "bg-amber-500/15 text-amber-600 border-amber-500/40" },
    sent: { icon: Clock, label: "Non ouvert", tone: "bg-muted text-muted-foreground border-border" },
  };
  const S = STATUS_MAP[status];
  return (
    <div className="surface p-4 flex flex-wrap items-center gap-4" data-testid={`portal-quote-${q.log_id}`}>
      <div className="h-12 w-12 grid place-items-center rounded-sm bg-primary/15 shrink-0">
        <FileText className="h-6 w-6 text-primary" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-semibold truncate">Devis de <span className="text-primary">{q.pro_name}</span></p>
        <p className="text-xs text-muted-foreground">
          Envoyé le {q.sent_at?.slice(0, 10).split("-").reverse().join("/")}
          {q.finish ? ` · finition ${q.finish}` : ""}
          {q.floor_material ? ` · ${q.floor_material}` : ""}
        </p>
      </div>
      <div className="text-right">
        <p className="num font-display text-xl font-extrabold">
          {(q.total_ttc || 0).toLocaleString("pt-PT")} €
        </p>
        <p className="text-[10px] text-muted-foreground">TTC</p>
      </div>
      <Badge variant="outline" className={`rounded-sm ${S.tone}`}>
        <S.icon className="h-3 w-3 mr-1" /> {S.label}
      </Badge>
      <div className="flex gap-2">
        <Button
          size="sm" variant="outline" onClick={dl}
          data-testid={`portal-quote-pdf-${q.log_id}`}
          className="rounded-sm"
        >
          PDF
        </Button>
        {!q.signed && q.signature_token && (
          <Link to={`/devis/signer/${q.signature_token}`} data-testid={`portal-quote-sign-${q.log_id}`}>
            <Button size="sm" className="rounded-sm gap-1">
              Signer <ExternalLink className="h-3 w-3" />
            </Button>
          </Link>
        )}
      </div>
    </div>
  );
}
