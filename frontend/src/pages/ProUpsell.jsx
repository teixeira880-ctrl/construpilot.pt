import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { BadgeCheck, Check, ArrowRight, Lock, Loader2, Sparkles } from "lucide-react";
import { api, eur } from "@/lib/api";
import { toast } from "sonner";

const PlanCard = ({ plan, highlight, busy, onSelect }) => {
  const price = (plan.amount_cents || 0) / 100;
  const per = plan.interval === "year" ? "ano" : plan.interval === "month" ? "mês" : null;
  return (
    <Card className={`p-6 flex flex-col text-left relative ${highlight ? "border-primary ring-1 ring-primary/30" : ""}`} data-testid={`upsell-plan-${plan.plan_id}`}>
      {highlight && (
        <span className="absolute -top-3 left-6 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-primary text-primary-foreground">Recomendado</span>
      )}
      <p className="text-xs uppercase tracking-wide text-muted-foreground">{plan.tagline}</p>
      <h3 className="font-display text-xl font-bold mt-1">{plan.name}</h3>
      <p className="mt-2">
        <span className="num text-3xl font-extrabold">{eur(price)}</span>
        {per && <span className="text-sm text-muted-foreground"> /{per}</span>}
      </p>
      <ul className="mt-4 space-y-2 flex-1">
        {(plan.features || []).slice(0, 6).map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" /> <span>{f}</span>
          </li>
        ))}
      </ul>
      <Button className="rounded-sm gap-2 mt-6 w-full" disabled={busy}
        onClick={() => onSelect(plan)} data-testid={`upsell-checkout-${plan.plan_id}`}>
        {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <BadgeCheck className="h-4 w-4" />}
        Escolher {plan.name}
      </Button>
    </Card>
  );
};

export default function ProUpsell() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const analyse = sp.get("feature") === "analyse";
  const [proPlans, setProPlans] = useState([]);
  const [partPlans, setPartPlans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");

  useEffect(() => {
    const reqs = [api.get("/plans?audience=pro")];
    if (analyse) reqs.push(api.get("/plans?audience=particulier"));
    Promise.all(reqs).then((res) => {
      const pro = (res[0].data.plans || []).filter((p) => p.kind === "subscription" && p.interval === "month");
      setProPlans(pro);
      if (analyse && res[1]) {
        const part = (res[1].data.plans || []).filter((p) => p.plan_id.startsWith("premium") && p.interval === "month");
        setPartPlans(part);
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, [analyse]);

  const checkout = async (plan) => {
    setBusyId(plan.plan_id);
    try {
      const { data } = await api.post("/billing/checkout", {
        plan_id: plan.plan_id, origin_url: window.location.origin,
      });
      if (data?.url) { window.location.href = data.url; return; }
      toast.error("Impossível iniciar o pagamento");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pagamento indisponível");
    } finally { setBusyId(""); }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-12" data-testid="pro-upsell-page">
      <div className="text-center max-w-2xl mx-auto">
        <div className="mx-auto h-16 w-16 rounded-full bg-primary/10 grid place-items-center mb-5">
          <Lock className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold">
          {analyse ? "Desbloqueie a análise de orçamentos" : "Mude para conta Pro"}
        </h1>
        <p className="text-muted-foreground mt-3">
          {analyse
            ? "A análise de orçamentos (comparação de preços linha por linha) está incluída nas nossas subscrições. Escolha um plano para desbloquear esta função e muito mais."
            : "Orçamentos, faturas, obras, empresa & RH… Subscreva um plano Pro para desbloquear tudo. Acesso imediato após pagamento."}
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : (
        <>
          {analyse && partPlans.length > 0 && (
            <div className="mt-10">
              <div className="flex items-center gap-2 mb-4">
                <Sparkles className="h-4 w-4 text-primary" />
                <h2 className="text-lg font-bold">Para particulares</h2>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                {partPlans.map((p) => (
                  <PlanCard key={p.plan_id} plan={p} busy={busyId === p.plan_id} onSelect={checkout} />
                ))}
              </div>
            </div>
          )}

          <div className="mt-10">
            {analyse && (
              <div className="flex items-center gap-2 mb-4">
                <BadgeCheck className="h-4 w-4 text-primary" />
                <h2 className="text-lg font-bold">Para profissionais</h2>
              </div>
            )}
            <div className="grid sm:grid-cols-2 gap-4">
              {proPlans.map((p) => (
                <PlanCard key={p.plan_id} plan={p} highlight={p.plan_id === "pro_monthly"} busy={busyId === p.plan_id} onSelect={checkout} />
              ))}
            </div>
          </div>
        </>
      )}

      <div className="flex flex-col sm:flex-row gap-3 justify-center mt-10">
        <Button variant="ghost" onClick={() => nav("/planos")} data-testid="pro-upsell-see-all" className="gap-2">
          Ver todas as tarifas <ArrowRight className="h-4 w-4" />
        </Button>
        <Button variant="outline" onClick={() => nav("/dashboard")} data-testid="pro-upsell-back">
          Voltar ao painel de controlo
        </Button>
      </div>
    </div>
  );
}
