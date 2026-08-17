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

const EXAMPLE = "Je veux rénover mon appartement de 60 m² : refaire les peintures, changer le sol, rénover la salle de bain et la cuisine.";

const STEPS = [
  { icon: Camera, title: "Décrivez votre projet", text: "En une phrase ou une photo de votre plan — c'est tout." },
  { icon: Sparkles, title: "L'IA chiffre tout", text: "Estimation détaillée poste par poste en 30 secondes." },
  { icon: Wallet, title: "Comparez et budgétez", text: "Prix des matériaux, fourchettes réalistes, aucune surprise." },
];

const PERKS = [
  { icon: Clock, title: "30 secondes", text: "Une estimation instantanée, sans rendez-vous ni attente." },
  { icon: Wallet, title: "100 % gratuit", text: "Estimez votre budget rénovation sans engagement." },
  { icon: ShieldCheck, title: "Prix réels du marché", text: "Basé sur les tarifs matériaux et main d'œuvre actuels." },
  { icon: HomeIcon, title: "Pensé pour vous", text: "Pas de jargon : des chiffres clairs pour votre projet." },
];

const TESTIS = [
  { name: "Camille · Lyon", text: "J'ai eu mon budget rénovation en 2 minutes, avant même de contacter un artisan. Bluffant." },
  { name: "Karim · Nantes", text: "Super pratique pour savoir si mon projet de cuisine tenait dans mon budget." },
  { name: "Sophie · Bordeaux", text: "Enfin des chiffres clairs sans avoir à faire venir 3 entreprises." },
];

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
    if (mail && mail.includes("@")) {
      sessionStorage.setItem("construpilot_lead_email", mail);
      if (name.trim()) sessionStorage.setItem("construpilot_lead_name", name.trim());
      api.post("/leads", {
        name: name.trim(), email: mail, description: text,
        source: sessionStorage.getItem("construpilot_utm_source") || "landing-particuliers",
        utm_source: sessionStorage.getItem("construpilot_utm_source") || "",
        utm_medium: sessionStorage.getItem("construpilot_utm_medium") || "",
        utm_campaign: sessionStorage.getItem("construpilot_utm_campaign") || "",
      }).catch(() => {});
    }
    navigate("/estimation");
  };

  return (
    <>
      <SEO
        title="Estimez votre budget rénovation en 30 secondes — ConstruPilot"
        description="Vous rénovez votre maison ou appartement ? Obtenez une estimation de budget travaux gratuite et instantanée grâce à l'IA. Prix réels, poste par poste, sans engagement."
        keywords="estimation travaux gratuite, budget rénovation maison, prix rénovation appartement, calcul coût travaux, devis rénovation particulier"
        canonical="/particuliers"
      />
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border" data-testid="particuliers-hero">
        <div className="absolute inset-0">
          <img src={IMG.hero} alt="Intérieur rénové lumineux" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/92 to-background/40" />
        </div>
        <div className="relative mx-auto max-w-6xl px-5 py-20 lg:py-28 grid lg:grid-cols-2 gap-10 items-center">
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-3 py-1 text-xs font-bold text-primary mb-5" data-testid="particuliers-badge">
              <Sparkles className="h-3.5 w-3.5" /> Spécial particuliers · 100 % gratuit
            </span>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] tracking-tight">
              Votre budget rénovation,<br />
              <span className="text-primary">estimé en 30 secondes.</span>
            </h1>
            <p className="mt-5 text-base md:text-lg text-muted-foreground max-w-lg">
              Maison, appartement, cuisine, salle de bain… Décrivez votre projet, notre IA vous donne une estimation chiffrée poste par poste. Sans rendez-vous, sans engagement.
            </p>

            <div className="mt-7 surface p-4 rounded-xl max-w-lg space-y-3" data-testid="particuliers-form">
              <div className="grid sm:grid-cols-2 gap-3">
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Votre prénom"
                         className="pl-9 rounded-sm" data-testid="particuliers-name" />
                </div>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Votre e-mail"
                         className="pl-9 rounded-sm" data-testid="particuliers-email" />
                </div>
              </div>
              <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
                        placeholder={EXAMPLE} className="rounded-sm text-sm" data-testid="particuliers-description" />
              <Button onClick={launch} size="lg" className="w-full rounded-sm gap-2 text-base font-bold" data-testid="particuliers-cta">
                Estimer mon projet gratuitement <ArrowRight className="h-5 w-5" />
              </Button>
              <p className="text-[11px] text-muted-foreground text-center flex items-center justify-center gap-1">
                <CheckCircle2 className="h-3 w-3 text-primary" /> Gratuit · Aucune carte bancaire · Résultat immédiat
              </p>
            </div>
            <div className="mt-4"><SignupCounter /></div>
          </motion.div>
        </div>
      </section>

      {/* AVANT / APRÈS */}
      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20 grid lg:grid-cols-2 gap-10 items-center">
        <motion.div initial={{ opacity: 0, x: -20 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.5 }}>
          <img src={IMG.avantApres} alt="Avant et après rénovation" className="rounded-xl w-full shadow-lg" data-testid="particuliers-avant-apres" />
        </motion.div>
        <div>
          <p className="overline text-primary">Du rêve au chiffrage</p>
          <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">Savez-vous vraiment combien va coûter votre projet ?</h2>
          <p className="mt-4 text-base text-muted-foreground">
            Avant de vous lancer, obtenez une vision claire et réaliste de votre budget. ConstruPilot analyse votre description et vous donne une estimation détaillée — comme le ferait un professionnel, mais en quelques secondes.
          </p>
          <ul className="mt-6 space-y-3">
            {["Estimation poste par poste (peinture, sol, plomberie…)", "Fourchette de prix basse / moyenne / haute", "Prix des matériaux à jour", "Exportable pour comparer les devis d'artisans"].map((t) => (
              <li key={t} className="flex items-start gap-2 text-sm">
                <CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" /> {t}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* COMMENT ÇA MARCHE */}
      <section className="bg-muted/40 border-y border-border py-16 lg:py-20" data-testid="particuliers-steps">
        <div className="mx-auto max-w-6xl px-5">
          <div className="text-center max-w-2xl mx-auto">
            <p className="overline text-primary">Simple comme bonjour</p>
            <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">3 étapes, zéro prise de tête</h2>
          </div>
          <div className="mt-10 grid md:grid-cols-3 gap-6">
            {STEPS.map((s, i) => (
              <motion.div key={s.title} initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
                          viewport={{ once: true }} transition={{ delay: i * 0.1 }}
                          className="surface p-6 rounded-xl">
                <div className="h-12 w-12 rounded-xl bg-primary/10 grid place-items-center mb-4">
                  <s.icon className="h-6 w-6 text-primary" />
                </div>
                <div className="text-xs font-bold text-primary mb-1">Étape {i + 1}</div>
                <h3 className="font-display text-lg font-bold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground">{s.text}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* POURQUOI */}
      <section className="mx-auto max-w-6xl px-5 py-16 lg:py-20">
        <div className="grid lg:grid-cols-2 gap-10 items-center">
          <img src={IMG.couple} alt="Couple préparant sa rénovation" className="rounded-xl w-full shadow-lg order-2 lg:order-1" />
          <div className="order-1 lg:order-2">
            <p className="overline text-primary">Pourquoi ConstruPilot</p>
            <h2 className="font-display text-3xl lg:text-4xl font-extrabold mt-2">Reprenez le contrôle de votre budget travaux</h2>
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

      {/* TÉMOIGNAGES */}
      <section className="bg-muted/40 border-y border-border py-16">
        <div className="mx-auto max-w-6xl px-5">
          <div className="grid md:grid-cols-3 gap-6">
            {TESTIS.map((t) => (
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
        <h2 className="font-display text-3xl lg:text-5xl font-extrabold">Prêt à connaître votre budget ?</h2>
        <p className="mt-4 text-base md:text-lg text-muted-foreground">C'est gratuit, immédiat et sans engagement.</p>
        <Button onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })} size="lg"
                className="mt-7 rounded-sm gap-2 text-base font-bold px-8" data-testid="particuliers-cta-final">
          Estimer mon projet <ArrowRight className="h-5 w-5" />
        </Button>
        <p className="mt-6 text-sm text-muted-foreground">
          Vous êtes un professionnel du bâtiment ? <Link to="/" className="text-primary font-semibold underline">Découvrir l'offre Pro</Link>
        </p>
      </section>

      <Footer />
    </>
  );
}
