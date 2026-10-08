import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, Sparkles, Clock, ShieldCheck, Wallet, Camera, CheckCircle2,
  Home as HomeIcon, Star, Mail, User,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import { SignupCounter } from "@/components/SignupCounter";
import { api } from "@/lib/api";

const IMG = {
  hero: "https://static.prod-images.emergentagent.com/jobs/24c1027c-3500-4369-9271-1f0502b94a6a/images/e26af67e137308e88ada544517a3765a5a64e9780e77f0271b542ce4c9a2b065.jpeg",
  avantApres: "https://static.prod-images.emergentagent.com/jobs/24c1027c-3500-4369-9271-1f0502b94a6a/images/da8d51f6072f524c806535c806f718ec00c2d6f9b749b447637eaf9feb126729.jpeg",
  couple: "https://static.prod-images.emergentagent.com/jobs/24c1027c-3500-4369-9271-1f0502b94a6a/images/67832e234a33611ab2d1f47a5438bff370514f9f4bf9ecb83cc337f96ba24644.jpeg",
};

const EXAMPLE = "Quero renovar o meu apartamento de 60 m²: refazer as pinturas, mudar o pavimento, renovar a casa de banho e a cozinha.";

const STEPS = [
  { icon: Camera, title: "Descreva o seu projecto", text: "Numa frase ou com uma foto da sua planta — é só isso." },
  { icon: Sparkles, title: "A IA orça tudo", text: "Estimativa detalhada rubrica a rubrica em 30 segundos." },
  { icon: Wallet, title: "Compare e defina o orçamento", text: "Preços dos materiais, intervalos realistas, nenhuma surpresa." },
];

const PERKS = [
  { icon: Clock, title: "30 segundos", text: "Uma estimativa instantânea, sem marcações nem esperas." },
  { icon: Wallet, title: "100 % gratuito", text: "Estime o seu orçamento de obra sem compromisso." },
  { icon: ShieldCheck, title: "Preços reais do mercado", text: "Baseado nas tarifas actuais de materiais e mão de obra." },
  { icon: HomeIcon, title: "Pensado para si", text: "Sem jargão: valores claros para o seu projecto." },
];

const TESTIS = [];

export default function LandingParticuliers() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [description, setDescription] = useState("");

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    ["utm_source", "utm_medium", "utm_campaign"].forEach((k) => {
      const v = sp.get(k);
      if (v) sessionStorage.setItem(`construpilot_${k}`, v);
    });
  }, []);

  const launch = () => {
    const text = description.trim() || EXAMPLE;
    sessionStorage.setItem("estimator_prefill", JSON.stringify({ description: text, _raw: text }));
    const mail = email.trim();
    if (mail) sessionStorage.setItem("construpilot_lead_email", mail);
    if (name.trim()) sessionStorage.setItem("construpilot_lead_name", name.trim());
    const leadPayload = {
      name: name.trim(), email: mail, description: text,
      source: sessionStorage.getItem("construpilot_utm_source") || "landing-particuliers",
      utm_source: sessionStorage.getItem("construpilot_utm_source") || "",
      utm_medium: sessionStorage.getItem("construpilot_utm_medium") || "",
      utm_campaign: sessionStorage.getItem("construpilot_utm_campaign") || "",
    };
    const isLoggedIn = !!localStorage.getItem("construpilot_token");
    if (isLoggedIn) {
      if (mail && mail.includes("@")) api.post("/leads", leadPayload).catch(() => {});
      navigate("/estimation");
      return;
    }
    sessionStorage.setItem("construpilot_pending_lead", JSON.stringify(leadPayload));
    navigate(`/inscription?email=${encodeURIComponent(mail)}&signup=1`);
  };

  return (
    <>
      <SEO
        title="Estime o seu orçamento de obra em 30 segundos — ConstruPilot"
        description="Vai renovar a sua casa ou apartamento? Obtenha uma estimativa de orçamento de obra gratuita e instantânea com IA. Preços reais, rubrica a rubrica, sem compromisso."
        keywords="estimativa de obra gratuita, orçamento renovação casa, preços renovação apartamento, cálculo custo obra, orçamento renovação particular"
        canonical="/particuliers"
      />
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border" data-testid="particuliers-hero">
        <div className="absolute inset-0">
          <img src={IMG.hero} alt="Interior renovado luminoso" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/92 to-background/40" />
        </div>
        <div className="relative mx-auto max-w-6xl px-5 py-20 lg:py-28 grid lg:grid-cols-2 gap-10 items-center">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-bold text-primary mb-5" data-testid="particuliers-badge">
              <Sparkles className="h-3.5 w-3.5" /> Especial particulares · 100 % gratuito
            </span>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] tracking-tight">
              O seu orçamento de obra,<br />
              <span className="text-primary">estimado em 30 segundos.</span>
            </h1>
            <p className="mt-5 text-base md:text-lg text-muted-foreground max-w-lg">
              Casa, apartamento, cozinha, casa de banho… Descreva o seu projecto e a nossa IA entrega uma estimativa detalhada rubrica a rubrica. Sem marcações, sem compromisso.
            </p>

            <div className="mt-7 surface p-4 rounded-xl max-w-lg space-y-3" data-testid="particuliers-form">
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="O seu nome próprio"
                         className="pl-9 rounded-sm" data-testid="particuliers-name" />
                </div>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="O seu e-mail"
                         className="pl-9 rounded-sm" data-testid="particuliers-email" />
                </div>
              </div>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
                        placeholder={EXAMPLE} className="rounded-sm text-sm" data-testid="particuliers-description" />
              <Button onClick={launch} size="lg" className="w-full rounded-sm gap-2 text-base font-bold" data-testid="particuliers-cta">
                Estimar o meu projecto gratuitamente <ArrowRight className="h-5 w-5" />
              </Button>
              <p className="text-[11px] text-muted-foreground text-center flex items-center justify-center gap-1">
                <CheckCircle2 className="h-3 w-3 text-primary" /> Gratuito · Sem cartão bancário · Resultado imediato
              </p>
            </div>
            <div className="mt-4"><SignupCounter /></div>
          </motion.div>
        </div>
      </section>

      {/* ANTES / DEPOIS */}
      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20 grid lg:grid-cols-2 gap-10 items-center">
        <motion.div initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
          <img src={IMG.avantApres} alt="Antes e depois de uma renovação" className="rounded-xl w-full shadow-lg" data-testid="particuliers-avant-apres" />
        </motion.div>
        <div>
          <p className="overline text-primary">Do sonho ao orçamento</p>
          <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">Sabe mesmo quanto vai custar o seu projecto?</h2>
          <p className="mt-4 text-base text-muted-foreground">
            Antes de avançar, tenha uma visão clara e realista do seu orçamento. O ConstruPilot analisa a sua descrição e entrega uma estimativa detalhada — como faria um profissional, mas em poucos segundos.
          </p>
          <ul className="mt-6 space-y-3">
            {["Estimativa rubrica a rubrica (pintura, pavimento, canalização…)", "Intervalo de preços baixo / médio / alto", "Preços dos materiais actualizados", "Exportável para comparar os orçamentos de profissionais"].map((t) => (
              <li key={t} className="flex items-start gap-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" /> {t}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* COMO FUNCIONA */}
      <section className="bg-muted/40 border-y border-border py-16 lg:py-20" data-testid="particuliers-steps">
        <div className="mx-auto max-w-6xl px-5">
          <div className="text-center max-w-2xl mx-auto">
            <p className="overline text-primary">Simples como bom dia</p>
            <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">3 passos, zero complicações</h2>
          </div>
          <div className="mt-10 grid md:grid-cols-3 gap-6">
            {STEPS.map((s, i) => (
              <motion.div key={s.title} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
                          viewport={{ once: true }} transition={{ delay: i * 0.1 }}
                          className="surface p-6 rounded-xl">
                <div className="h-12 w-12 rounded-xl bg-primary/10 grid place-items-center mb-4">
                  <s.icon className="h-6 w-6 text-primary" />
                </div>
                <div className="text-xs font-bold text-primary mb-1">Passo {i + 1}</div>
                <h3 className="font-display text-lg font-bold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* PORQUÊ */}
      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="grid lg:grid-cols-2 gap-10 items-center">
          <img src={IMG.couple} alt="Casal a preparar a sua renovação" className="rounded-xl w-full shadow-lg order-2 lg:order-1" />
          <div className="order-1 lg:order-2">
            <p className="overline text-primary">Porquê o ConstruPilot</p>
            <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">Retome o controlo do seu orçamento de obra</h2>
            <div className="mt-6 grid sm:grid-cols-2 gap-4">
              {PERKS.map((p) => (
                <div key={p.title} className="flex gap-3">
                  <div className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center shrink-0">
                    <p.icon className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-bold text-sm">{p.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{p.text}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* TESTEMUNHOS */}
      <section className="bg-muted/40 border-y border-border py-16">
        <div className="mx-auto max-w-6xl px-5">
          <div className="grid md:grid-cols-3 gap-6">
            {TESTIS.length === 0 ? (
              <div className="md:col-span-3 surface p-8 rounded-xl grid place-items-center text-center gap-2" data-testid="particuliers-testis-empty">
                <div className="flex gap-0.5 text-primary/40">
                  {[...Array(5)].map((_, i) => <Star key={i} className="h-4 w-4 fill-current" />)}
                </div>
                <p className="text-sm text-muted-foreground">Os comentários dos nossos utilizadores aparecerão aqui em breve.</p>
              </div>
            ) : TESTIS.map((t) => (
              <div key={t.name} className="surface p-6 rounded-xl">
                <div className="flex gap-0.5 mb-3">
                  {[...Array(5)].map((_, i) => <Star key={i} className="h-4 w-4 fill-primary text-primary" />)}
                </div>
                <p className="text-sm italic">« {t.text} »</p>
                <p className="mt-3 text-xs font-bold text-muted-foreground">{t.name}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA FINAL */}
      <section className="mx-auto max-w-4xl px-5 py-20 text-center">
        <h2 className="font-display text-3xl lg:text-5xl font-extrabold">Pronto para conhecer o seu orçamento?</h2>
        <p className="mt-4 text-base md:text-lg text-muted-foreground">É gratuito, imediato e sem compromisso.</p>
        <Button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} size="lg"
                className="mt-7 rounded-sm gap-2 text-base font-bold px-8" data-testid="particuliers-cta-final">
          Estimar o meu projecto <ArrowRight className="h-5 w-5" />
        </Button>
        <p className="mt-6 text-sm text-muted-foreground">
          É um profissional da construção? <Link to="/" className="text-primary font-semibold underline">Descobrir a oferta Pro</Link>
        </p>
      </section>

      <Footer />
    </>
  );
}
