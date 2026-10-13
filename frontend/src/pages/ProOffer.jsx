import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Check, ArrowRight, Building2, Users, ShieldCheck, CreditCard, CalendarClock,
  Ruler, FileText, Boxes, Footprints, Layers, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SEO } from "@/components/SEO";
import { FeatureClips } from "@/components/FeatureClips";

const PRO_VALUE = [
  { icon: FileText, title: "Devis client en un éclair", text: "Générez estimation, quantités, prix fournisseurs et devis PDF prêt à envoyer." },
  { icon: Ruler, title: "Métré sur plan 2D / DXF", text: "Dessinez, calibrez, déduisez les ouvertures et exportez le métré net vers le devis." },
  { icon: Boxes, title: "Chiffrage par corps d'état", text: "Placo, peinture, carrelage… compositions et ratios personnalisables, prix mémorisés." },
  { icon: Footprints, title: "Calcul d'escaliers béton", text: "Optimiseur, alertes DTU 36.3, analyse béton armé et dossier PDF coté." },
  { icon: Layers, title: "Projets multi-niveaux", text: "Regroupez Fondations, RDC, R+1… avec métré et chiffrage consolidés." },
  { icon: ShieldCheck, title: "Calculs déterministes", text: "Aucune approximation IA sur les maths : provenance et traçabilité garanties." },
];

const ICONS = { PRO_MONTHLY: Building2, PRO_YEARLY: Building2, PRO_BUSINESS_MONTHLY: Users, PRO_BUSINESS_YEARLY: Users };

export default function ProOffer() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [flags, setFlags] = useState({});
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api.get("/plans?lang=fr").then(({ data }) => { setPlans(data.plans || []); setFlags(data.flags || {}); }).catch(() => {});
  }, []);

  const proPlans = useMemo(
    () => plans.filter((p) => p.audience === "pro" && p.kind === "subscription" && p.interval === "month"),
    [plans]);
  const trialDays = flags?.trial_days || 7;

  const subscribe = async (plan) => {
    if (!user) { toast.info("Créez votre compte pour démarrer l'essai Pro"); navigate("/register?intent=pro"); return; }
    setBusy(plan.plan_id);
    try {
      const { data } = await api.post("/billing/checkout", { plan_id: plan.plan_id, origin_url: window.location.origin });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossible d'ouvrir le paiement");
      setBusy(null);
    }
  };

  return (
    <div className="grid gap-16 pb-20" data-testid="pro-offer-page">
      <SEO
        title="Offre Pro ConstruPilot — logiciel de devis et métré pour artisans du BTP"
        description="Passez au Pro : devis clients, métré sur plan, chiffrage par corps d'état, calcul d'escaliers et projets multi-niveaux. Essai gratuit de 7 jours, puis 149 €/mois. Sans engagement."
        keywords="logiciel devis artisan, métré BTP, chiffrage corps d'état, abonnement pro construpilot, essai gratuit devis"
        canonical="/pro"
      />

      {/* HERO */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(60%_80%_at_15%_0%,rgba(255,90,0,0.12),transparent)]" />
        <div className="max-w-5xl mx-auto px-5 pt-16 pb-6 grid gap-6">
          <Badge className="w-fit rounded-full bg-primary/10 text-primary border-0 px-3 py-1" data-testid="pro-hero-badge">
            Pour les professionnels du BTP
          </Badge>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter leading-[1.05]">
            Chiffrez, métrez et éditez vos devis<br className="hidden sm:block" /> <span className="text-primary">au tarif juste, sans erreurs.</span>
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl">
            ConstruPilot Pro réunit métré sur plan, chiffrage par corps d'état, calcul d'escaliers béton
            et projets multi-niveaux — avec des calculs 100 % déterministes.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" className="rounded-sm gap-2" data-testid="pro-hero-cta"
                    onClick={() => proPlans[0] ? subscribe(proPlans[0]) : navigate("/register?intent=pro")}>
              Démarrer l'essai gratuit ({trialDays} jours) <ArrowRight className="h-5 w-5" />
            </Button>
            <a href="#offre-pro" className="text-sm font-medium underline underline-offset-4" data-testid="pro-see-plans">Voir les offres</a>
          </div>
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            <CreditCard className="h-3.5 w-3.5" /> Carte requise à l'inscription · aucun débit avant la fin de l'essai · résiliable à tout moment
          </p>
        </div>
      </header>

      {/* VALUE GRID */}
      <section className="max-w-5xl mx-auto px-5 w-full">
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {PRO_VALUE.map((v) => (
            <div key={v.title} className="surface p-5 rounded-lg" data-testid={`pro-value-${v.title.slice(0, 6)}`}>
              <span className="h-10 w-10 grid place-items-center rounded-sm bg-primary/10 text-primary mb-3"><v.icon className="h-5 w-5" /></span>
              <p className="font-display font-bold">{v.title}</p>
              <p className="text-sm text-muted-foreground mt-1">{v.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* OFFER / PLANS */}
      <section id="offre-pro" className="max-w-4xl mx-auto px-5 w-full grid gap-6">
        <div className="text-center grid gap-2">
          <p className="text-xs uppercase tracking-widest text-primary font-semibold">Offre Pro</p>
          <h2 className="font-display text-3xl font-extrabold tracking-tight">Essai {trialDays} jours, puis un abonnement clair</h2>
          <p className="text-sm text-muted-foreground max-w-xl mx-auto">
            Testez toutes les fonctions Pro pendant {trialDays} jours. La carte est enregistrée dès l'inscription :
            à la fin de l'essai, l'abonnement démarre automatiquement au tarif ci-dessous. Sans engagement, résiliable en un clic.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-5">
          {proPlans.length === 0 ? (
            <p className="col-span-2 text-center text-sm text-muted-foreground">Chargement des offres…</p>
          ) : proPlans.map((plan) => {
            const Icon = ICONS[plan.code] || Building2;
            const eur = (plan.amount_cents / 100).toFixed(plan.amount_cents % 100 ? 2 : 0);
            const hi = plan.highlight;
            return (
              <div key={plan.plan_id} data-testid={`pro-plan-${plan.plan_id}`}
                   className={`surface p-6 rounded-lg grid gap-4 relative ${hi ? "border-primary/60 shadow-[0_10px_40px_-15px_rgba(255,90,0,0.4)]" : ""}`}>
                {plan.badge && <Badge className="absolute -top-3 left-6 rounded-sm bg-primary text-primary-foreground uppercase tracking-wider text-[10px]">{plan.badge}</Badge>}
                <div className="flex items-center gap-3">
                  <span className={`h-10 w-10 grid place-items-center rounded-sm ${hi ? "bg-primary/15 text-primary" : "bg-secondary"}`}><Icon className="h-5 w-5" /></span>
                  <div><p className="font-display font-bold text-lg">{plan.name}</p>{plan.tagline && <p className="text-xs text-muted-foreground">{plan.tagline}</p>}</div>
                </div>
                <div><p className="num font-display text-4xl font-extrabold tracking-tighter">{eur} €<span className="text-base font-normal text-muted-foreground">/mois</span></p>
                  <p className="text-[11px] text-muted-foreground mt-1">Essai {trialDays} jours offert · sans engagement</p></div>
                {plan.description && <p className="text-sm text-muted-foreground">{plan.description}</p>}
                <ul className="grid gap-2">
                  {(plan.features || []).map((f, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm"><Check className="h-4 w-4 text-primary shrink-0 mt-0.5" /><span>{f}</span></li>
                  ))}
                </ul>
                <Button onClick={() => subscribe(plan)} disabled={busy === plan.plan_id}
                        data-testid={`pro-subscribe-${plan.plan_id}`}
                        className="w-full rounded-sm gap-2 mt-2" variant={hi ? "default" : "outline"}>
                  {busy === plan.plan_id ? "Redirection…" : <>Démarrer l'essai {trialDays} jours <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      <FeatureClips title="Découvrez chaque fonction Pro en vidéo" subtitle="De courtes démonstrations réelles, narrées, avec une explication détaillée de chaque outil Pro." />

      {/* CONDITIONS / FAQ facturation */}
      <section className="max-w-3xl mx-auto px-5 w-full grid gap-4">
        <h2 className="font-display text-2xl font-extrabold tracking-tight text-center">Conditions & facturation</h2>
        <div className="grid gap-3">
          {[
            { icon: CalendarClock, q: `Comment marche l'essai de ${trialDays} jours ?`, a: `Vous accédez à toutes les fonctions Pro pendant ${trialDays} jours. Aucun débit n'a lieu pendant l'essai.` },
            { icon: CreditCard, q: "Pourquoi une carte est-elle demandée à l'inscription ?", a: "La carte est enregistrée pour permettre le démarrage automatique de l'abonnement à la fin de l'essai. Elle n'est débitée qu'après la période d'essai." },
            { icon: ShieldCheck, q: "Puis-je résilier avant d'être facturé ?", a: `Oui. Résiliez à tout moment pendant l'essai depuis votre espace facturation : aucun montant ne sera prélevé.` },
            { icon: Building2, q: "Quelle différence entre Pro et Pro Business ?", a: "Pro couvre un artisan et ses chantiers. Pro Business ajoute la gestion d'équipe (ouvrages partagés), la facturation électronique Factur-X et des volumes supérieurs." },
          ].map((f) => (
            <div key={f.q} className="surface rounded-md p-4 flex items-start gap-3" data-testid={`pro-faq-${f.q.slice(0, 8)}`}>
              <f.icon className="h-4 w-4 text-primary shrink-0 mt-0.5" />
              <div><p className="text-sm font-semibold">{f.q}</p><p className="text-sm text-muted-foreground mt-0.5">{f.a}</p></div>
            </div>
          ))}
        </div>
        <div className="text-center mt-2">
          <Button size="lg" className="rounded-sm gap-2" data-testid="pro-bottom-cta"
                  onClick={() => proPlans[0] ? subscribe(proPlans[0]) : navigate("/register?intent=pro")}>
            <Sparkles className="h-5 w-5" /> Démarrer maintenant
          </Button>
          <p className="mt-2 text-xs text-muted-foreground">Vous hésitez ? <a href="/tarifs" className="underline underline-offset-4">Comparer tous les plans</a></p>
        </div>
      </section>
    </div>
  );
}
