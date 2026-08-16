import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, Sparkles, Calculator, Search, Wrench, ShieldCheck, FileText,
  MessageSquare, Camera, TrendingDown, Hammer, ChevronRight, Building2,
  HardHat, Home as HomeIcon, Store, GraduationCap, Factory, ChevronDown,
  Globe2, PenTool, CheckCircle2, Cuboid, User, Mail
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import { TrustSection } from "@/components/TrustSection";
import { MarketingTeaser } from "@/components/MarketingTeaser";
import { Interactive3D } from "@/components/Interactive3D";
import { api, IMAGES, eur } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";

const EXAMPLE =
  "Je veux rénover une maison de 150 m², refaire les murs, plafonds, électricité, plomberie, deux salles de bain et remplacer les fenêtres.";

// Data for Interactive3D hero demo
const HERO_ROOMS = [
  { name: "Séjour", polygon_px: [[0,0], [400,0], [400,300], [0,300]], centroid_px: [200, 150] },
  { name: "Chambre", polygon_px: [[400,0], [700,0], [700,200], [400,200]], centroid_px: [550, 100] },
  { name: "SDB", polygon_px: [[400,200], [700,200], [700,300], [400,300]], centroid_px: [550, 250] }
];
const HERO_WALLS = [
  { x1: 0, y1: 0, x2: 400, y2: 0, wall_type: "porteur", thickness_px: 15 },
  { x1: 400, y1: 0, x2: 700, y2: 0, wall_type: "porteur", thickness_px: 15 },
  { x1: 700, y1: 0, x2: 700, y2: 300, wall_type: "porteur", thickness_px: 15 },
  { x1: 700, y1: 300, x2: 0, y2: 300, wall_type: "porteur", thickness_px: 15 },
  { x1: 0, y1: 300, x2: 0, y2: 0, wall_type: "porteur", thickness_px: 15 },
  { x1: 400, y1: 0, x2: 400, y2: 300, wall_type: "cloison", thickness_px: 10 },
  { x1: 400, y1: 200, x2: 700, y2: 200, wall_type: "cloison", thickness_px: 10 }
];

const STEPS = [
  { icon: MessageSquare, title: "Je décris mon projet", text: "En une phrase, comme à un artisan." },
  { icon: Sparkles, title: "ConstruPilot comprend", text: "Lots, surfaces, niveau de finition, risques." },
  { icon: Calculator, title: "Le moteur calcule", text: "Quantités et prix déterministes, vérifiables." },
  { icon: Search, title: "Je trouve les meilleurs prix", text: "Comparaison multi-fournisseurs et panier optimisé." },
  { icon: Wrench, title: "Je sais quoi faire moi-même", text: "Guides pas à pas et niveaux de difficulté." },
  { icon: Hammer, title: "J'appelle un pro si besoin", text: "Proposition professionnelle en 48 h." },
];

const FEATURES = [
  { icon: Calculator, title: "Calculateurs pros", text: "Peinture, carrelage, placo, béton, isolation : quantités exactes avec marges.", to: "/calculateurs", span: "md:col-span-4" },
  { icon: Search, title: "Comparateur de prix", text: "10 fournisseurs, livraison, stock, historique et alertes prix.", to: "/prix", span: "md:col-span-4" },
  { icon: Cuboid, title: "Génération 3D", text: "Visualisez votre projet en trois dimensions à partir d'un simple plan 2D.", to: "/plan", span: "md:col-span-8 lg:col-span-4" },
  { icon: Wrench, title: "Mode « je le fais moi-même »", text: "Matériaux calculés + guide professionnel étape par étape.", to: "/diy", span: "md:col-span-4 lg:col-span-4" },
  { icon: Camera, title: "Estimation par photo", text: "L'IA identifie la pièce, son état et les travaux probables.", to: "/photo", span: "md:col-span-4 lg:col-span-4" },
  { icon: FileText, title: "Scanner de devis", text: "Prix bas, correct, élevé : l'IA analyse et compare vos devis.", to: "/scanner-devis", span: "md:col-span-4 lg:col-span-4" },
];

const AUDIENCES = [
  { icon: HardHat, key: "landing.for_pro", title: "Artisans BTP", textKey: "landing.for_pro_text", text: "Générez vos devis client en 30 s avec attestation TVA 10 %, signature électronique et suivi ouverture." },
  { icon: HomeIcon, key: "landing.for_particulier", title: "Particuliers", textKey: "landing.for_particulier_text", text: "Estimez votre rénovation avant de contacter un pro. Comparez les devis reçus." },
  { icon: Building2, title: "Architectes", text: "Métré 2D auto depuis vos plans PDF/DXF, chiffrage instantané par lot, rendu 3D pour vos clients." },
  { icon: Store, title: "Marchands", text: "Vos prix, comparés en temps réel. Générez la liste de courses depuis un plan." },
  { icon: GraduationCap, title: "Écoles BTP", text: "Un terrain de jeu pédagogique : IA, calculateurs et guides métier accessibles gratuitement." },
  { icon: Factory, title: "Promoteurs", text: "Chiffrage rapide pour vos offres. Devis multi-plans consolidé, tour vidéo 3D à joindre." },
];

const FAQ = [
  { q: "Combien coûte une rénovation complète au m² en 2026 ?", a: "En rénovation lourde en France, comptez 900 à 1 800 €/m² selon la région et la gamme. ConstruPilot calcule votre estimation exacte en 30 secondes." },
  { q: "ConstruPilot est-il gratuit ?", a: "Oui pour les particuliers. Une offre Pro (devis PDF illimités, signature client, rendu 3D IA, tour vidéo) est disponible pour les artisans dès 39 €/mois." },
  { q: "Comment fonctionne le métré 2D automatique ?", a: "Uploadez votre plan (PDF, PNG, DXF). Notre moteur détecte automatiquement les murs, les portes et calcule les surfaces." },
  { q: "Puis-je générer un devis avec attestation TVA à 10 % ?", a: "Oui. ConstruPilot génère l'attestation requise pour la rénovation de logement de plus de 2 ans. Le client la signe en ligne." },
  { q: "Vos prix matériaux sont-ils à jour ?", a: "Nous croisons les catalogues des principales enseignes du BTP mis à jour hebdomadairement, avec l'historique 12 mois." },
  { q: "L'IA remplace-t-elle un artisan ?", a: "Non. Elle fournit une estimation instantanée. Pour un chantier complexe, un professionnel reste indispensable." },
];

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } }
};

// Contenu dynamique du hero selon l'audience (particulier / pro)
const HERO_CONTENT = {
  particulier: {
    badgeKey: "landing.hero.badge_part", badge: "Pour les particuliers",
    h1aKey: "landing.hero.h1a_part", h1a: "Estimez le coût de",
    h1bKey: "landing.hero.h1b_part", h1b: "vos travaux en 30 s.",
    subKey: "landing.hero.sub_part",
    sub: "Décrivez votre projet de rénovation. ConstruPilot calcule instantanément une estimation détaillée, poste par poste — avant même de contacter un artisan.",
    ctaKey: "landing.hero.cta_part", cta: "Estimer mes travaux",
    dest: "/smart-project",
  },
  pro: {
    badgeKey: "landing.hero.badge_pro", badge: "Pour les pros du BTP",
    h1aKey: "landing.hero.h1a_pro", h1a: "Chiffrez et éditez",
    h1bKey: "landing.hero.h1b_pro", h1b: "vos devis en un éclair.",
    subKey: "landing.hero.sub_pro",
    sub: "Décrivez le chantier. ConstruPilot génère l'estimation, les quantités, les prix fournisseurs exacts et le devis client PDF avec plan 3D interactif.",
    ctaKey: "landing.hero.cta_pro", cta: "Générer mon devis",
    dest: "/estimation",
  },
};

export default function Landing() {
  const [description, setDescription] = useState("");
  const [email, setEmail] = useState("");
  const [audience, setAudience] = useState("particulier");
  const [showSticky, setShowSticky] = useState(false);
  const [types, setTypes] = useState([]);
  const [openFaq, setOpenFaq] = useState(0);
  const navigate = useNavigate();
  const { t } = useI18n();

  useEffect(() => {
    api.get("/estimation/catalog").then(({ data }) => setTypes(data.project_types)).catch(() => {});
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) sessionStorage.setItem("construpilot_ref", ref.toUpperCase());
  }, []);

  // Affiche le CTA collant sur mobile après avoir dépassé le hero
  useEffect(() => {
    const onScroll = () => setShowSticky(window.scrollY > 620);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const hero = HERO_CONTENT[audience];

  const launch = () => {
    const text = description.trim() || EXAMPLE;
    sessionStorage.setItem("construpilot_description", text);
    const mail = email.trim();
    if (mail && mail.includes("@")) {
      api.post("/leads", {
        email: mail, description: text, source: `landing-hero-${audience}`,
      }).catch(() => {});
    }
    navigate(hero.dest);
  };

  return (
    <>
      <SEO
        title={null}
        description="ConstruPilot : l'assistant IA du BTP. Générez un devis chiffré en 30 s, comparez les prix matériaux, calculez vos quantités exactes et éditez vos devis clients PDF avec tour vidéo 3D."
        keywords="devis travaux, estimation rénovation, calculateur matériaux, comparateur prix BTP, logiciel devis artisan, plan 2D 3D, prix rénovation maison"
        canonical="/"
        jsonLd={{
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": FAQ.map(({ q, a }) => ({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": { "@type": "Answer", "text": a },
          }))
        }}
      />
      <Nav />

      {/* ── HERO SECTION (SPLIT 3D) ───────────────────────── */}
      <section className="relative overflow-hidden pt-24 pb-32 lg:pt-32 lg:pb-40 border-b border-border bg-gradient-to-b from-background to-secondary/30">
        <div className="absolute inset-0 grain opacity-40 pointer-events-none" />
        
        <div className="mx-auto max-w-[1500px] px-6 lg:px-10 relative z-10">
          <div className="grid lg:grid-cols-12 gap-12 lg:gap-8 items-center">
            
            {/* Left Content */}
            <motion.div 
              className="lg:col-span-6 xl:col-span-5 flex flex-col items-start"
              initial={{ opacity: 0, x: -30 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, ease: "easeOut" }}
            >
              {/* Sélecteur d'audience : Particulier / Pro */}
              <div className="inline-flex p-1 rounded-full bg-secondary/70 border border-border mb-6" role="tablist" data-testid="hero-audience-toggle">
                <button
                  role="tab"
                  aria-selected={audience === "particulier"}
                  data-testid="hero-audience-particulier"
                  onClick={() => setAudience("particulier")}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-colors ${audience === "particulier" ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >
                  <User className="h-4 w-4" /> {t("landing.hero.seg_part", "Je suis un particulier")}
                </button>
                <button
                  role="tab"
                  aria-selected={audience === "pro"}
                  data-testid="hero-audience-pro"
                  onClick={() => setAudience("pro")}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-colors ${audience === "pro" ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >
                  <HardHat className="h-4 w-4" /> {t("landing.hero.seg_pro", "Je suis un pro")}
                </button>
              </div>

              <motion.h1
                key={`h1-${audience}`}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.35 }}
                className="font-display text-4xl sm:text-5xl lg:text-6xl xl:text-[4rem] font-extrabold tracking-tighter leading-[1.05]"
              >
                {t(hero.h1aKey, hero.h1a)} <br className="hidden sm:block" />
                <span className="text-primary italic">{t(hero.h1bKey, hero.h1b)}</span>
              </motion.h1>

              <motion.p
                key={`sub-${audience}`}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.4 }}
                className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed max-w-xl"
              >
                {t(hero.subKey, hero.sub)}
              </motion.p>

              <div className="mt-10 w-full max-w-xl relative">
                <div className="absolute -inset-1 bg-primary/20 blur-2xl rounded-xl" aria-hidden="true" />
                <div className="relative bg-card/60 backdrop-blur-xl border border-white/20 dark:border-white/10 shadow-xl rounded-xl p-2 transition-all focus-within:ring-2 focus-within:ring-primary/40">
                  <Textarea
                    data-testid="hero-ai-input"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder={t("landing.hero.placeholder", `Décrivez votre projet — ex : « ${EXAMPLE} »`)}
                    rows={3}
                    className="resize-none border-0 bg-transparent text-base focus-visible:ring-0 rounded-lg"
                  />
                  <div className="relative px-1">
                    <Mail className="absolute start-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <Input
                      data-testid="hero-email-input"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={t("landing.hero.email_ph", "Votre e-mail (pour recevoir votre estimation)")}
                      className="ps-9 border-0 bg-background/60 rounded-lg h-11 focus-visible:ring-1 focus-visible:ring-primary/40"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 p-2 pt-2">
                    <button
                      onClick={() => setDescription(EXAMPLE)} data-testid="hero-example-btn"
                      className="text-xs font-medium text-muted-foreground hover:text-primary transition-colors"
                    >
                      {t("landing.hero.example_btn", "Utiliser l'exemple")}
                    </button>
                    <Button
                      onClick={launch} data-testid="hero-submit-btn"
                      className="rounded-lg gap-2 shadow-md hover:shadow-primary/30 transition-all hover:-translate-y-0.5"
                    >
                      <Sparkles className="h-4 w-4" /> {t(hero.ctaKey, hero.cta)}
                    </Button>
                  </div>
                </div>
                <p className="mt-3 text-xs text-muted-foreground flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
                  {t("landing.hero.reassurance", "Gratuit et sans engagement — résultat en 30 secondes.")}
                </p>
              </div>

              <div className="mt-8 flex items-center gap-6 text-sm text-muted-foreground">
                <div className="flex -space-x-3">
                  {[1,2,3].map(i => (
                    <div key={i} className="h-10 w-10 rounded-full border-2 border-background bg-secondary flex items-center justify-center">
                      <HardHat className="h-4 w-4 text-primary/60" />
                    </div>
                  ))}
                </div>
                <div className="flex flex-col">
                  <span className="font-bold text-foreground num">{t("landing.hero.trust_title", "Rejoignez 10 000+ pros")}</span>
                  <span className="text-xs">{t("landing.hero.trust_subtitle", "Artisans & Architectes équipés")}</span>
                </div>
              </div>
            </motion.div>

            {/* Right Content - 3D Viewer */}
            <motion.div 
              className="lg:col-span-6 xl:col-span-7 h-[500px] lg:h-[600px] w-full rounded-2xl relative"
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            >
               <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 to-transparent rounded-2xl pointer-events-none" />
               <div className="relative h-full w-full rounded-2xl border border-white/20 dark:border-white/10 shadow-2xl overflow-hidden bg-card/50 backdrop-blur-sm p-4">
                  <div className="absolute top-6 left-6 z-20 flex flex-col gap-1 pointer-events-none">
                     <span className="text-[10px] uppercase font-bold tracking-widest text-primary">Vue en direct</span>
                     <span className="text-sm font-semibold">Génération Plan 3D</span>
                  </div>
                  {/* Reuse the existing Interactive3D component with mock data */}
                  <div className="h-full w-full overflow-hidden rounded-xl bg-background/50">
                     <Interactive3D 
                        rooms={HERO_ROOMS} 
                        walls={HERO_WALLS} 
                        scaleMperPx={0.012} 
                        imageHeight={550} 
                     />
                  </div>
               </div>
            </motion.div>

          </div>
        </div>
      </section>

      {/* ── MARKETING TEASER (mobile mockup) ─────────────── */}
      <MarketingTeaser />

      {/* ── TRUST & LOGOS ───────────────────────────────── */}
      <TrustSection />

      {/* ── BENTO FEATURES GRID ────────────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
        <div className="max-w-2xl">
          <p className="overline">L'arsenal Complet</p>
          <h2 className="mt-4 font-display text-4xl lg:text-5xl font-bold tracking-tight text-foreground">
            Des outils de professionnel, <br className="hidden md:block" />
            <span className="text-muted-foreground">repensés pour l'efficacité.</span>
          </h2>
        </div>

        <motion.div 
          className="mt-16 grid grid-cols-1 md:grid-cols-8 lg:grid-cols-12 gap-6"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
        >
          {FEATURES.map((f) => (
            <motion.div 
              key={f.title} 
              variants={itemVariants}
              className={`group relative overflow-hidden rounded-2xl border border-border bg-card p-8 hover:border-primary/40 transition-colors ${f.span}`}
            >
              <Link to={f.to} data-testid={`feature-card-${f.to.slice(1)}`} className="absolute inset-0 z-10" aria-label={f.title} />
              <div className="flex flex-col h-full justify-between gap-8 relative z-0">
                <div className="h-12 w-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center">
                  <f.icon className="h-6 w-6 text-primary group-hover:scale-110 transition-transform duration-300" aria-hidden="true" />
                </div>
                <div>
                  <h3 className="font-display text-xl font-bold text-foreground">{f.title}</h3>
                  <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{f.text}</p>
                </div>
              </div>
              {/* Subtle hover gradient */}
              <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── CATALOGUE / PROJECT TYPES ─────────────────────── */}
      <section className="border-y border-border bg-secondary/30 relative">
        <div className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8 mb-16">
            <div className="max-w-xl">
              <p className="overline">Catalogue travaux</p>
              <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
                Démarrez sur de bonnes bases
              </h2>
            </div>
            <Button variant="outline" onClick={() => navigate('/smart-project')} className="rounded-full">
              Voir tous les modèles <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>

          <motion.div 
            className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6"
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
          >
            {types.length > 0 ? types.map((t, i) => (
              <motion.button
                variants={itemVariants}
                key={t.key}
                data-testid={`category-card-${t.key}`}
                onClick={() => navigate(`/estimation?type=${t.key}`)}
                className="group relative h-64 w-full overflow-hidden rounded-2xl text-left border border-white/10"
              >
                <img
                  src={IMAGES[t.image] || IMAGES.project_card_interior} alt={t.name}
                  className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-110"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent" />
                <div className="relative h-full p-6 flex flex-col justify-between">
                  <div className="self-end px-3 py-1 rounded-full bg-black/40 backdrop-blur-md border border-white/20">
                    <p className="num text-xs text-white/90 font-medium">{String(i + 1).padStart(2, "0")}</p>
                  </div>
                  <div>
                    <h3 className="font-display text-2xl font-semibold text-white leading-tight">{t.name}</h3>
                    <div className="mt-3 flex items-center gap-2 text-sm text-primary font-medium opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-300">
                      Estimer maintenant <ArrowRight className="h-4 w-4" />
                    </div>
                  </div>
                </div>
              </motion.button>
            )) : (
              // Fallback loading state if api is slow
              [1,2,3,4].map(i => <div key={i} className="h-64 rounded-2xl bg-border/50 animate-pulse" />)
            )}
          </motion.div>
        </div>
      </section>

      {/* ── COMPARISON : DIY VS PRO ───────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
        <div className="bg-card border border-border rounded-[2rem] p-10 lg:p-16 relative overflow-hidden shadow-sm">
          <div className="absolute -right-40 -top-40 h-[500px] w-[500px] bg-primary/10 blur-[100px] rounded-full pointer-events-none" />
          
          <div className="grid lg:grid-cols-2 gap-16 lg:gap-24 items-center relative z-10">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-muted border border-border mb-6">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span className="text-xs font-semibold uppercase tracking-widest text-foreground">Prise de décision</span>
              </div>
              <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">
                Faire vous-même ou <br className="hidden sm:block" />engager un pro ?
              </h2>
              <p className="mt-6 text-base text-muted-foreground leading-relaxed">
                ConstruPilot compare en temps réel le coût matériel pur et le coût avec main-d'œuvre. Évaluez le temps nécessaire, la complexité et les risques. 
                <strong className="text-foreground"> Le système vous alerte automatiquement</strong> quand un professionnel qualifié est indispensable (structure, électricité, amiante).
              </p>
              <div className="mt-10 flex flex-wrap gap-4">
                <Link to="/diy">
                  <Button className="rounded-full px-8 shadow-md">
                    <Wrench className="mr-2 h-4 w-4" /> Mode Autonomie
                  </Button>
                </Link>
                <Link to="/estimation">
                  <Button variant="secondary" className="rounded-full px-8">
                    <PenTool className="mr-2 h-4 w-4" /> Devis Artisan
                  </Button>
                </Link>
              </div>
            </div>
            
            {/* Visual Data Comparison */}
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="p-6 border border-border rounded-2xl bg-background/50 backdrop-blur-sm flex flex-col justify-center">
                <p className="text-xs uppercase font-bold tracking-wider text-muted-foreground mb-4">Coût Artisan</p>
                <p className="num text-3xl font-extrabold text-foreground">{eur(10500)}</p>
                <p className="text-sm text-muted-foreground mt-2">Main d'œuvre incluse, garanti décennale.</p>
              </div>
              
              <div className="p-6 border border-primary/30 rounded-2xl bg-primary/5 backdrop-blur-sm flex flex-col justify-center shadow-inner relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-primary/10 rounded-full blur-2xl" />
                <p className="text-xs uppercase font-bold tracking-wider text-primary mb-4">Coût DIY (Matériaux purs)</p>
                <p className="num text-3xl font-extrabold text-primary">{eur(5800)}</p>
                <div className="mt-4 inline-flex items-center text-xs font-semibold text-emerald-600 bg-emerald-500/10 px-2 py-1 rounded-md w-fit">
                  <TrendingDown className="h-3 w-3 mr-1" /> Économie {eur(4700)}
                </div>
              </div>
              
              <div className="sm:col-span-2 p-5 border border-border rounded-2xl bg-background/50 flex items-start gap-4">
                <ShieldCheck className="h-6 w-6 text-primary shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground leading-relaxed">
                  <strong className="text-foreground">Analyse IA (SDB 8m²) :</strong> Peinture et finitions réalisables par un débutant. Plomberie et tableau électrique à confier à un professionnel RGE.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── AUDIENCES / POUR QUI ───────────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-6 lg:px-10 pb-24 lg:pb-32">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <p className="overline">Pour qui ?</p>
          <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Un écosystème connecté pour tous les acteurs du BTP
          </h2>
        </div>
        
        <motion.div 
          className="grid md:grid-cols-2 lg:grid-cols-3 gap-6"
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true }}
        >
          {AUDIENCES.map((a) => (
            <motion.div 
              variants={itemVariants}
              key={a.title} 
              className="p-8 rounded-2xl bg-secondary/40 border border-transparent hover:border-border transition-colors"
            >
              <div className="flex items-center gap-4 mb-6">
                <div className="h-10 w-10 rounded-full bg-background flex items-center justify-center shadow-sm">
                  <a.icon className="h-5 w-5 text-primary" aria-hidden="true" />
                </div>
                <h3 className="font-display text-xl font-semibold">{a.key ? t(a.key, a.title) : a.title}</h3>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">{a.textKey ? t(a.textKey, a.text) : a.text}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── FAQ ────────────────────────────────────────────── */}
      <section className="border-t border-border bg-background" id="faq">
        <div className="mx-auto max-w-[1000px] px-6 lg:px-10 py-24 lg:py-32">
          <div className="text-center mb-16">
            <p className="overline">Questions fréquentes</p>
            <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
              Tout ce que vous devez savoir
            </h2>
          </div>
          
          <div className="grid gap-4">
            {FAQ.map((item, i) => {
              const open = openFaq === i;
              return (
                <div key={i} className="bg-card border border-border rounded-xl overflow-hidden transition-all duration-300 hover:border-primary/30">
                  <button
                    onClick={() => setOpenFaq(open ? -1 : i)}
                    aria-expanded={open}
                    className="w-full text-left flex items-center justify-between p-6 focus:outline-none"
                  >
                    <span className="font-display font-semibold text-lg pr-8 text-foreground">{item.q}</span>
                    <div className={`h-8 w-8 rounded-full border flex items-center justify-center shrink-0 transition-colors ${open ? 'border-primary bg-primary text-white' : 'border-border text-muted-foreground'}`}>
                      <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  
                  {/* Framer motion animate presence would be better here, but CSS is fine for MVP */}
                  <div 
                    className={`overflow-hidden transition-all duration-300 ease-in-out ${open ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'}`}
                  >
                    <div className="px-6 pb-6 pt-2 text-base text-muted-foreground leading-relaxed border-t border-border/50">
                      {item.a}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── CTA COLLANT MOBILE ─────────────────────────────── */}
      <div
        className={`lg:hidden fixed inset-x-0 bottom-0 z-40 p-3 transition-transform duration-300 ${showSticky ? "translate-y-0" : "translate-y-full"}`}
        data-testid="mobile-sticky-cta"
      >
        <div className="mx-auto max-w-md rounded-2xl bg-card/90 backdrop-blur-xl border border-border shadow-2xl p-2 flex items-center gap-2">
          <Button
            onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
            className="flex-1 rounded-xl h-12 gap-2 text-base font-semibold"
            data-testid="mobile-sticky-cta-btn"
          >
            <Sparkles className="h-4 w-4" /> {t("landing.sticky.cta", "Estimer mon projet")}
          </Button>
        </div>
      </div>

      <Footer />
    </>
  );
}
