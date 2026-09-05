import { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { CheckCircle2, XCircle, Loader2, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useBilling } from "@/context/BillingContext";
import { useAuth } from "@/context/AuthContext";

const PLAN_LABELS = {
  pro_business_monthly: "Pro Business", pro_business_yearly: "Pro Business",
  pro_monthly: "Pro", pro_yearly: "Pro", premium_monthly: "Premium", premium_yearly: "Premium",
  project_pass: "Project Pass", invoicing_addon_monthly: "Option Facturation",
};

export function PaymentSuccess() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { refresh } = useBilling();
  const { checkAuth } = useAuth();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("checking");
  const [rec, setRec] = useState(null);

  useEffect(() => {
    if (!sessionId) { setStatus("error"); return; }
    let cancelled = false;
    let tries = 0;
    const poll = async () => {
      try {
        const { data } = await api.get(`/billing/status/${sessionId}`);
        if (cancelled) return;
        setRec(data);
        if (data.payment_status === "paid") {
          setStatus("ok");
          refresh?.();  // met à jour le tier dans toute l'app (débloque les options)
          checkAuth?.();  // rafraîchit account_type (particulier -> pro) après upgrade
          return;
        }
        if (tries++ < 15) setTimeout(poll, 2000);
        else setStatus("pending");
      } catch { setStatus("error"); }
    };
    poll();
    return () => { cancelled = true; };
  }, [sessionId, refresh, checkAuth]);

  const planName = PLAN_LABELS[rec?.plan_id] || (rec?.mode === "subscription" ? "Votre abonnement" : "Votre achat");

  return (
    <div className="max-w-lg mx-auto surface p-8 mt-16 grid gap-6 text-center" data-testid="payment-success-page">
      {status === "checking" && (
        <>
          <Loader2 className="h-10 w-10 mx-auto text-primary animate-spin" />
          <p className="font-display text-2xl font-bold">Confirmation du paiement…</p>
          <p className="text-sm text-muted-foreground">Ne fermez pas cette fenêtre.</p>
        </>
      )}
      {status === "ok" && (
        <>
          <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-500" />
          <div>
            <p className="font-display text-2xl font-bold" data-testid="ps-plan-activated">🎉 {planName} activé</p>
            <p className="mt-2 text-sm text-muted-foreground">
              Votre {rec?.mode === "subscription" ? "abonnement" : "achat"} est confirmé.
              Toutes les fonctionnalités de votre formule sont désormais débloquées sur votre compte.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 justify-center">
            <Button onClick={() => navigate("/dashboard")} data-testid="ps-cta-dashboard" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              Aller au tableau de bord <ArrowRight className="h-4 w-4" />
            </Button>
            <Link to="/estimateur"><Button variant="outline" className="rounded-sm">Créer un projet</Button></Link>
          </div>
        </>
      )}
      {status === "pending" && (
        <>
          <Loader2 className="h-10 w-10 mx-auto text-amber-500" />
          <p className="font-display text-xl font-bold">Paiement en cours de traitement</p>
          <p className="text-sm text-muted-foreground">
            Votre banque traite le paiement. Vous recevrez un email dès qu'il est confirmé.
          </p>
        </>
      )}
      {status === "error" && (
        <>
          <XCircle className="h-14 w-14 mx-auto text-red-500" />
          <p className="font-display text-xl font-bold">Session introuvable</p>
          <Link to="/tarifs"><Button variant="outline" className="rounded-sm">Retour aux tarifs</Button></Link>
        </>
      )}
    </div>
  );
}

export function PaymentCancel() {
  return (
    <div className="max-w-lg mx-auto surface p-8 mt-16 grid gap-4 text-center" data-testid="payment-cancel-page">
      <XCircle className="h-14 w-14 mx-auto text-muted-foreground" />
      <p className="font-display text-2xl font-bold">Paiement annulé</p>
      <p className="text-sm text-muted-foreground">Aucun montant n'a été prélevé. Vous pouvez reprendre à tout moment.</p>
      <div className="flex justify-center gap-3">
        <Link to="/tarifs"><Button className="rounded-sm hover:bg-orange-600 hover:text-white">Revoir les formules</Button></Link>
        <Link to="/"><Button variant="outline" className="rounded-sm">Retour à l'accueil</Button></Link>
      </div>
    </div>
  );
}
