import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { CheckCircle2, CreditCard, FileDown, HardHat, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, eur, num } from "@/lib/api";

export default function PcSignPage() {
  const { token } = useParams();
  const [searchParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const [busy, setBusy] = useState(false);
  const [depositBusy, setDepositBusy] = useState(false);

  useEffect(() => {
    api.get(`/pc/sign/${token}`)
      .then(({ data: d }) => setData(d))
      .catch((e) => setError(e?.response?.data?.detail || "Lien invalide ou expiré"));
  }, [token]);

  // Retour de Stripe : confirme le paiement de l'acompte (polling)
  useEffect(() => {
    const sid = searchParams.get("session_id");
    if (!sid) return;
    let tries = 0;
    const timer = setInterval(async () => {
      tries += 1;
      try {
        const { data: st } = await api.get(`/pc/deposit/status/${sid}`);
        if (st.payment_status === "paid") {
          clearInterval(timer);
          toast.success("Acompte reçu — merci !");
          setData((p) => p ? {
            ...p,
            deposit: { ...(p.deposit || {}), paid: true, paid_amount: st.amount },
          } : p);
        } else if (["expired", "failed"].includes(st.payment_status) || tries > 12) {
          clearInterval(timer);
          if (["expired", "failed"].includes(st.payment_status)) {
            toast.error("Le paiement n'a pas abouti — vous pouvez réessayer");
          }
        }
      } catch {
        if (tries > 12) clearInterval(timer);
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [searchParams]);

  const accept = async () => {
    if (name.trim().length < 2) return toast.error("Indiquez votre nom complet");
    if (!agree) return toast.error("Cochez la case d'acceptation");
    setBusy(true);
    try {
      const { data: r } = await api.post(`/pc/sign/${token}/accept`, { name: name.trim() });
      setData((p) => ({ ...p, accepted: true, accepted_at: r.accepted_at, accepted_by: name.trim() }));
      toast.success("Étude acceptée — merci !");
    } catch (e) { toast.error(e?.response?.data?.detail || "Acceptation impossible"); }
    finally { setBusy(false); }
  };

  const payDeposit = async () => {
    setDepositBusy(true);
    try {
      const { data: r } = await api.post(`/pc/sign/${token}/deposit/checkout`,
        { origin_url: window.location.origin });
      window.location.href = r.url;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Paiement indisponible — réessayez plus tard");
      setDepositBusy(false);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center bg-background p-6">
        <p className="text-muted-foreground" data-testid="pc-sign-error">{error}</p>
      </div>
    );
  }
  if (!data) {
    return <div className="min-h-screen grid place-items-center bg-background">
      <p className="text-muted-foreground animate-pulse">Chargement de l'étude…</p>
    </div>;
  }

  const t = data.totals || {};
  const dep = data.deposit || {};
  return (
    <div className="min-h-screen bg-background py-10 px-4" data-testid="pc-sign-page">
      <div className="max-w-2xl mx-auto space-y-6">
        <header className="space-y-1">
          <p className="overline flex items-center gap-2 text-primary">
            <HardHat className="h-4 w-4" /> {data.company || "ConstruPilot"}
          </p>
          <h1 className="font-display text-2xl sm:text-3xl font-extrabold">
            Étude gros œuvre — {data.filename || "votre projet"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Établie le {String(data.generated_at || "").slice(0, 10)}
            {data.planning?.total_days ? ` · chantier estimé ${data.planning.total_days} jours (${data.planning.total_weeks} semaines)` : ""}
          </p>
        </header>

        {data.demandes?.length > 0 && (
          <ul className="text-sm text-muted-foreground space-y-0.5">
            {data.demandes.slice(0, 4).map((d, i) => <li key={i}>• {d}</li>)}
          </ul>
        )}

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[["Béton", `${num(t.beton_m3, 1)} m³`], ["Aciers", `${num(t.acier_kg)} kg`],
            ["Briques isobrique", `${num(t.briques_u)} u`], ["Total TTC", eur(t.ttc)]].map(([k, v]) => (
            <div key={k} className="surface p-3">
              <p className="text-[10px] text-muted-foreground">{k}</p>
              <p className="font-display font-bold num">{v}</p>
            </div>
          ))}
        </div>

        <table className="w-full text-sm border border-border">
          <tbody>
            {(data.lots || []).map((l) => (
              <tr key={l.lot} className="border-t border-border first:border-t-0">
                <td className="p-2">{l.lot}</td>
                <td className="p-2 text-right num font-semibold">{eur(l.total)}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-primary/40 bg-muted/40">
              <td className="p-2 font-bold">Total HT / TVA 20 % / TTC</td>
              <td className="p-2 text-right num font-bold text-primary">
                {eur(t.ht)} / {eur(t.tva)} / {eur(t.ttc)}
              </td>
            </tr>
          </tbody>
        </table>

        {data.accepted ? (
          <div className="rounded-sm border-2 border-emerald-500/50 bg-emerald-500/10 p-5 text-center space-y-1"
               data-testid="pc-sign-accepted">
            <CheckCircle2 className="h-8 w-8 text-emerald-500 mx-auto" />
            <p className="font-display font-bold text-emerald-600">Étude acceptée</p>
            <p className="text-sm text-muted-foreground">
              le {String(data.accepted_at || "").slice(0, 10)} par <b>{data.accepted_by}</b>
            </p>
          </div>
        ) : (
          <div className="surface p-5 space-y-3" data-testid="pc-sign-form">
            <p className="font-semibold flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" /> Accepter cette étude en ligne
            </p>
            <Input placeholder="Votre nom complet" value={name}
                   onChange={(e) => setName(e.target.value)}
                   data-testid="pc-sign-name-input" className="rounded-sm" />
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)}
                     data-testid="pc-sign-agree-checkbox" className="mt-0.5 accent-primary" />
              J'ai pris connaissance de l'étude gros œuvre ci-dessus (quantités et montants
              indicatifs) et je l'accepte comme base de travail.
            </label>
            <Button onClick={accept} disabled={busy} className="rounded-sm w-full gap-2"
                    data-testid="pc-sign-accept-btn">
              <CheckCircle2 className="h-4 w-4" /> {busy ? "…" : "J'accepte cette étude"}
            </Button>
          </div>
        )}

        {data.accepted && dep.pct > 0 && (dep.paid ? (
          <div className="rounded-sm border-2 border-emerald-500/50 bg-emerald-500/10 p-4 text-center space-y-1"
               data-testid="pc-deposit-paid">
            <CreditCard className="h-6 w-6 text-emerald-500 mx-auto" />
            <p className="font-display font-bold text-emerald-600">
              Acompte de {eur(dep.paid_amount || dep.amount)} réglé
            </p>
            {dep.paid_at && (
              <p className="text-xs text-muted-foreground">le {String(dep.paid_at).slice(0, 10)}</p>
            )}
            <a href={`${api.defaults.baseURL}/pc/sign/${token}/deposit/invoice`}
               target="_blank" rel="noreferrer"
               className="inline-flex items-center gap-1.5 text-xs font-semibold text-primary underline underline-offset-2"
               data-testid="pc-deposit-invoice-link">
              <FileDown className="h-3.5 w-3.5" /> Télécharger la facture d'acompte
            </a>
          </div>
        ) : (
          <div className="surface p-5 space-y-3" data-testid="pc-deposit-block">
            <p className="font-semibold flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-primary" /> Verser l'acompte pour lancer le chantier
            </p>
            <p className="text-sm text-muted-foreground">
              Acompte de <b>{num(dep.pct)} %</b> — soit <b>{eur(dep.amount)}</b> sur un
              total de {eur(t.ttc)} TTC. Paiement sécurisé par carte bancaire (Stripe).
            </p>
            <Button onClick={payDeposit} disabled={depositBusy}
                    className="rounded-sm w-full gap-2" data-testid="pc-deposit-pay-btn">
              <CreditCard className="h-4 w-4" />
              {depositBusy ? "Redirection vers le paiement…" : `Payer l'acompte de ${eur(dep.amount)}`}
            </Button>
          </div>
        ))}

        <p className="text-[10px] text-muted-foreground text-center">
          Document indicatif généré par ConstruPilot — ne constitue pas un devis contractuel.
        </p>
      </div>
    </div>
  );
}
