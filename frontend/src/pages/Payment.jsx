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
  project_pass: "Project Pass", invoicing_addon_monthly: "Opção Faturação",
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

  const planName = PLAN_LABELS[rec?.plan_id] || (rec?.mode === "subscription" ? "A sua subscrição" : "A sua compra");

  return (
    <div className="max-w-lg mx-auto surface p-8 mt-16 grid gap-6 text-center" data-testid="payment-success-page">
      {status === "checking" && (
        <>
          <Loader2 className="h-10 w-10 mx-auto text-primary animate-spin" />
          <p className="font-display text-2xl font-bold">Confirmação do pagamento…</p>
          <p className="text-sm text-muted-foreground">Não feche esta janela.</p>
        </>
      )}
      {status === "ok" && (
        <>
          <CheckCircle2 className="h-14 w-14 mx-auto text-emerald-500" />
          <div>
            <p className="font-display text-2xl font-bold" data-testid="ps-plan-activated">🎉 {planName} ativado</p>
            <p className="mt-2 text-sm text-muted-foreground">
              O seu {rec?.mode === "subscription" ? "abonnement" : "achat"} está confirmado. Todas as funcionalidades da sua fórmula estão agora desbloqueadas na sua conta.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 justify-center">
            <Button onClick={() => navigate("/dashboard")} data-testid="ps-cta-dashboard" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              Ir para o painel de controlo <ArrowRight className="h-4 w-4" />
            </Button>
            <Link to="/estimateur"><Button variant="outline" className="rounded-sm">Criar um projeto</Button></Link>
          </div>
        </>
      )}
      {status === "pending" && (
        <>
          <Loader2 className="h-10 w-10 mx-auto text-amber-500" />
          <p className="font-display text-xl font-bold">Pagamento em processamento</p>
          <p className="text-sm text-muted-foreground">
            O seu banco processa o pagamento. Receberá um email assim que for confirmado.
          </p>
        </>
      )}
      {status === "error" && (
        <>
          <XCircle className="h-14 w-14 mx-auto text-red-500" />
          <p className="font-display text-xl font-bold">Sessão não encontrada</p>
          <Link to="/planos"><Button variant="outline" className="rounded-sm">Voltar aos preços</Button></Link>
        </>
      )}
    </div>
  );
}

export function PaymentCancel() {
  return (
    <div className="max-w-lg mx-auto surface p-8 mt-16 grid gap-4 text-center" data-testid="payment-cancel-page">
      <XCircle className="h-14 w-14 mx-auto text-muted-foreground" />
      <p className="font-display text-2xl font-bold">Pagamento cancelado</p>
      <p className="text-sm text-muted-foreground">Nenhum montante foi debitado. Pode retomar a qualquer momento.</p>
      <div className="flex justify-center gap-3">
        <Link to="/planos"><Button className="rounded-sm hover:bg-orange-600 hover:text-white">Rever as fórmulas</Button></Link>
        <Link to="/"><Button variant="outline" className="rounded-sm">Voltar ao início</Button></Link>
      </div>
    </div>
  );
}
