import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Check, Sparkles, Zap, Building2, Users, Rocket, ShieldCheck, ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";

const ICON = {
  FREE: Sparkles, PROJECT_PASS: Zap,
  PREMIUM_MONTHLY: Rocket, PREMIUM_YEARLY: Rocket,
  PRO_MONTHLY: Building2, PRO_YEARLY: Building2,
  PRO_BUSINESS_MONTHLY: Users, PRO_BUSINESS_YEARLY: Users,
};

const priceLabel = (p, t) => {
  if (p.kind === "free") return { big: "0 €", small: t("pricing.free") };
  const eur = (p.amount_cents / 100).toFixed(p.amount_cents % 100 ? 2 : 0);
  if (p.interval === "month") return { big: `${eur} €`, small: t("pricing.per_month") };
  if (p.interval === "year") return { big: `${eur} €`, small: t("pricing.per_year") };
  return { big: `${eur} €`, small: t("pricing.one_time") };
};

const PlanCard = ({ plan, flags, busy, onSubscribe }) => {
  const { t } = useI18n();
  const Icon = ICON[plan.code] || Sparkles;
  const price = priceLabel(plan, t);
  const hi = plan.highlight;
  return (
    <div
      data-testid={`plan-card-${plan.plan_id}`}
      className={`surface p-6 grid gap-4 relative transition-transform hover:-translate-y-1 ${
        hi ? "border-primary/60 shadow-[0_10px_40px_-15px_rgba(255,90,0,0.4)]" : ""
      }`}
    >
      {plan.badge && (
        <Badge className="absolute -top-3 left-6 rounded-sm bg-primary text-primary-foreground uppercase tracking-wider text-[10px]">
          {plan.badge}
        </Badge>
      )}
      <div className="flex items-center gap-3">
        <span className={`h-10 w-10 grid place-items-center rounded-sm ${hi ? "bg-primary/15 text-primary" : "bg-secondary text-foreground"}`}>
          <Icon className="h-5 w-5" />
        </span>
        <div>
          <p className="font-display font-bold text-lg">{plan.name}</p>
          {plan.tagline && <p className="text-xs text-muted-foreground">{plan.tagline}</p>}
        </div>
      </div>
      <div>
        <p className="num font-display text-4xl font-extrabold tracking-tighter">{price.big}</p>
        <p className="text-xs text-muted-foreground mt-1">{price.small}</p>
      </div>
      {plan.description && <p className="text-sm text-muted-foreground">{plan.description}</p>}
      <ul className="grid gap-2 mt-2">
        {(plan.features || []).map((f, i) => (
          <li key={i} className="flex items-start gap-2 text-sm">
            <Check className="h-4 w-4 text-primary shrink-0 mt-0.5" />
            <span>{f}</span>
          </li>
        ))}
      </ul>
      <div className="mt-auto pt-4">
        {plan.kind === "free" ? (
          <Button variant="outline" className="w-full rounded-sm" data-testid={`plan-cta-${plan.plan_id}`} disabled>
            {t("pricing.current")}
          </Button>
        ) : (
          <Button
            onClick={() => onSubscribe(plan)}
            disabled={busy === plan.plan_id}
            data-testid={`plan-cta-${plan.plan_id}`}
            className={`w-full rounded-sm gap-2 ${hi ? "hover:bg-orange-600" : ""}`}
            variant={hi ? "default" : "outline"}
          >
            {busy === plan.plan_id ? t("pricing.redirecting") : (
              <>
                {plan.kind === "one_time" ? t("pricing.unlock_project") : t("pricing.choose")}
                <ArrowRight className="h-4 w-4" />
              </>
            )}
          </Button>
        )}
        {plan.kind === "subscription" && flags?.trial_enabled && plan.trial_days > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground text-center">
            {plan.trial_days} {t("pricing.trial_suffix")}
          </p>
        )}
      </div>
    </div>
  );
};

export default function Pricing() {
  const { user } = useAuth();
  const { t, lang } = useI18n();
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [flags, setFlags] = useState({});
  const [audience, setAudience] = useState("particulier");
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api.get(`/plans?lang=${lang}`).then(({ data }) => {
      setPlans(data.plans || []);
      setFlags(data.flags || {});
    }).catch(() => toast.error(t("pricing.load_fail")));
  }, [lang]);

  const filtered = useMemo(() => plans.filter((p) => p.audience === audience), [plans, audience]);

  const subscribe = async (plan) => {
    if (!user) {
      toast.info(t("pricing.login_to_subscribe"));
      navigate("/login");
      return;
    }
    setBusy(plan.plan_id);
    try {
      const { data } = await api.post("/billing/checkout", {
        plan_id: plan.plan_id,
        origin_url: window.location.origin,
      });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("pricing.checkout_fail"));
      setBusy(null);
    }
  };

  return (
    <div className="grid gap-10">
      <SEO
        title="Tarifs — Gratuit pour les particuliers, Premium dès 19 €/mois"
        description="Estimation, calculateurs, comparateur de prix et coach IA pour les particuliers. Devis PDF illimités, TVA 10 % auto, rendu 3D, signature client, CRM et facturation pour les pros. Premium dès 19 €/mois, sans engagement."
        keywords="prix logiciel devis, tarif construpilot, abonnement artisan, logiciel BTP gratuit, prix outil estimation travaux"
        canonical="/tarifs"
      />
      <SectionTitle as="h1" over={t("pricing.over")} title={t("pricing.title")}>
        {t("pricing.subtitle")}
      </SectionTitle>

      <Tabs value={audience} onValueChange={setAudience}>
        <TabsList className="rounded-sm mx-auto">
          <TabsTrigger value="particulier" data-testid="pricing-tab-particulier" className="rounded-sm">
            {t("pricing.tab_particulier")}
          </TabsTrigger>
          <TabsTrigger value="pro" data-testid="pricing-tab-pro" className="rounded-sm">
            {t("pricing.tab_pro")}
          </TabsTrigger>
        </TabsList>

        <TabsContent value={audience} className="mt-10">
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 items-start" data-testid="pricing-grid">
            {filtered.map((p) => (
              <PlanCard key={p.plan_id} plan={p} flags={flags} busy={busy} onSubscribe={subscribe} />
            ))}
          </div>
        </TabsContent>
      </Tabs>

      <div className="surface p-8 grid md:grid-cols-3 gap-6">
        <div className="flex gap-3">
          <ShieldCheck className="h-6 w-6 text-primary shrink-0" />
          <div>
            <p className="font-display font-semibold">{t("pricing.secure_title")}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t("pricing.secure_desc")}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <Sparkles className="h-6 w-6 text-primary shrink-0" />
          <div>
            <p className="font-display font-semibold">{t("pricing.trial_title")}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t("pricing.trial_desc")}
            </p>
          </div>
        </div>
        <div className="flex gap-3">
          <Zap className="h-6 w-6 text-primary shrink-0" />
          <div>
            <p className="font-display font-semibold">{t("pricing.pass_title")}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t("pricing.pass_desc")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
