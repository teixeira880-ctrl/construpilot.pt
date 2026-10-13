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
  { icon: FileText, title: "Orçamento para o cliente num instante", text: "Gere estimativa, quantidades, preços de fornecedores e orçamento em PDF pronto a enviar." },
  { icon: Ruler, title: "Medição em planta 2D / DXF", text: "Desenhe, calibre, deduza os vãos e exporte a medição líquida para o orçamento." },
  { icon: Boxes, title: "Orçamentação por especialidade", text: "Pladur, pintura, mosaico… composições e rácios personalizáveis, preços memorizados." },
  { icon: Footprints, title: "Cálculo de escadas em betão", text: "Otimizador, alertas RGEU / DL 163/2006, análise de betão armado e processo PDF cotado." },
  { icon: Layers, title: "Projetos multinível", text: "Agrupe Fundações, R/C, 1.º andar… com medição e orçamentação consolidadas." },
  { icon: ShieldCheck, title: "Cálculos determinísticos", text: "Nenhuma aproximação IA na matemática: proveniência e rastreabilidade garantidas." },
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
    if (!user) { toast.info("Crie a sua conta para iniciar a experiência Pro"); navigate("/register?intent=pro"); return; }
    setBusy(plan.plan_id);
    try {
      const { data } = await api.post("/billing/checkout", { plan_id: plan.plan_id, origin_url: window.location.origin });
      window.location.href = data.url;
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossível abrir o pagamento");
      setBusy(null);
    }
  };

  return (
    <div className="grid gap-16 pb-20" data-testid="pro-offer-page">
      <SEO
        title="Oferta Pro ConstruPilot — software de orçamentos e medições para profissionais da construção"
        description="Passe ao Pro: orçamentos para clientes, medição em planta, orçamentação por especialidade, cálculo de escadas e projetos multinível. Experiência gratuita de 7 dias, depois 149 €/mês. Sem fidelização."
        keywords="software orçamentos profissional, medições construção, orçamentação por especialidade, subscrição pro construpilot, experiência gratuita orçamentos"
        canonical="/pro"
      />

      {/* HERO */}
      <header className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(60%_80%_at_15%_0%,rgba(255,90,0,0.12),transparent)]" />
        <div className="max-w-5xl mx-auto px-5 pt-16 pb-6 grid gap-6">
          <Badge className="w-fit rounded-full bg-primary/10 text-primary border-0 px-3 py-1" data-testid="pro-hero-badge">
            Para os profissionais da construção
          </Badge>
          <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter leading-[1.05]">
            Orçamente, meça e emita os seus orçamentos<br className="hidden sm:block" /> <span className="text-primary">ao preço justo, sem erros.</span>
          </h1>
          <p className="text-base sm:text-lg text-muted-foreground max-w-2xl">
            O ConstruPilot Pro reúne medição em planta, orçamentação por especialidade, cálculo de escadas em betão e projetos multinível — com cálculos 100 % determinísticos.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" className="rounded-sm gap-2" data-testid="pro-hero-cta"
                    onClick={() => proPlans[0] ? subscribe(proPlans[0]) : navigate("/register?intent=pro")}>
              Iniciar a experiência gratuita ({trialDays} jours) <ArrowRight className="h-5 w-5" />
            </Button>
            <a href="#offre-pro" className="text-sm font-medium underline underline-offset-4" data-testid="pro-see-plans">Ver as ofertas</a>
          </div>
          <p className="text-xs text-muted-foreground flex items-center gap-2">
            <CreditCard className="h-3.5 w-3.5" /> Cartão obrigatório na inscrição · nenhum débito antes do fim da experiência · cancelável a qualquer momento
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
          <p className="text-xs uppercase tracking-widest text-primary font-semibold">Oferta Pro</p>
          <h2 className="font-display text-3xl font-extrabold tracking-tight">Experiência {trialDays} dias, depois uma subscrição clara</h2>
          <p className="text-sm text-muted-foreground max-w-xl mx-auto">
            Teste todas as funções Pro durante {trialDays} dias. O cartão é registado na inscrição: no fim da experiência, a subscrição começa automaticamente ao preço abaixo. Sem fidelização, cancelável num clique.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 gap-5">
          {proPlans.length === 0 ? (
            <p className="col-span-2 text-center text-sm text-muted-foreground">A carregar as ofertas…</p>
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
                  <p className="text-[11px] text-muted-foreground mt-1">Experiência {trialDays} dias oferecidos · sem fidelização</p></div>
                {plan.description && <p className="text-sm text-muted-foreground">{plan.description}</p>}
                <ul className="grid gap-2">
                  {(plan.features || []).map((f, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm"><Check className="h-4 w-4 text-primary shrink-0 mt-0.5" /><span>{f}</span></li>
                  ))}
                </ul>
                <Button onClick={() => subscribe(plan)} disabled={busy === plan.plan_id}
                        data-testid={`pro-subscribe-${plan.plan_id}`}
                        className="w-full rounded-sm gap-2 mt-2" variant={hi ? "default" : "outline"}>
                  {busy === plan.plan_id ? "A redirecionar…" : <>Iniciar a experiência {trialDays} jours <ArrowRight className="h-4 w-4" /></>}
                </Button>
              </div>
            );
          })}
        </div>
      </section>

      <FeatureClips title="Descubra cada função Pro em vídeo" subtitle="Demonstrações curtas e reais, narradas, com uma explicação detalhada de cada ferramenta Pro." />

      {/* CONDITIONS / FAQ facturation */}
      <section className="max-w-3xl mx-auto px-5 w-full grid gap-4">
        <h2 className="font-display text-2xl font-extrabold tracking-tight text-center">Condições e faturação</h2>
        <div className="grid gap-3">
          {[
            { icon: CalendarClock, q: `Como funciona a experiência de ${trialDays} jours ?`, a: `Acede a todas as funções Pro durante ${trialDays} dias. Não há qualquer débito durante a experiência.` },
            { icon: CreditCard, q: "Porque é pedido um cartão na inscrição?", a: "O cartão é registado para permitir o início automático da subscrição no fim da experiência. Só é debitado depois do período de experiência." },
            { icon: ShieldCheck, q: "Posso cancelar antes de ser faturado?", a: `Sim. Cancele a qualquer momento durante a experiência a partir do seu espaço de faturação: nenhum montante será cobrado.` },
            { icon: Building2, q: "Qual a diferença entre Pro e Pro Business?", a: "O Pro cobre um profissional e as suas obras. O Pro Business acrescenta a gestão de equipa (artigos partilhados), a faturação eletrónica e volumes superiores." },
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
            <Sparkles className="h-5 w-5" /> Começar agora
          </Button>
          <p className="mt-2 text-xs text-muted-foreground">Está com dúvidas? <a href="/planos" className="underline underline-offset-4">Comparar todos os planos</a></p>
        </div>
      </section>
    </div>
  );
}
