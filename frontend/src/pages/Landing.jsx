import { useEffect, useState, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import { SignupCounter } from "@/components/SignupCounter";
import { motion } from "framer-motion";
import {
  ArrowRight, Sparkles, Calculator, Search, Wrench, ShieldCheck, FileText,
  MessageSquare, Camera, TrendingDown, Hammer, ChevronRight, Building2,
  HardHat, Home as HomeIcon, Store, GraduationCap, Factory, ChevronDown,
  Globe2, PenTool, CheckCircle2, Cuboid, User, Mail, Volume2, VolumeX
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import { TrustSection } from "@/components/TrustSection";
import { MarketingTeaser } from "@/components/MarketingTeaser";
import { FeatureShowcase } from "@/components/FeatureShowcase";
import { Interactive3D } from "@/components/Interactive3D";
import { ParamLibraryPromo } from "@/components/ParamLibraryPromo";
import { DemoShowcase } from "@/components/DemoShowcase";
import { SoroBlog } from "@/components/SoroBlog";
import { LandingInstallBanner } from "@/components/pwa/LandingInstallBanner";
import { api, IMAGES, eur } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { OfferNotice, useOffer, offerSentence } from "@/components/OfferNotice";

const EXAMPLE =
  "Quero renovar uma casa de 150 m², refazer as paredes, tetos, eletricidade, canalizações, duas casas de banho e substituir as janelas.";

// Data for Interactive3D hero demo — plan de maison réaliste (5 pièces + ouvertures)
const HERO_ROOMS = [
  { name: "Cozinha", polygon_px: [[0,0],[320,0],[320,260],[0,260]], centroid_px: [160,130],
    openings: [{ kind: "fenetre", width_m: 1.2 }, { kind: "porte", width_m: 0.8 }] },
  { name: "Sala de estar", polygon_px: [[0,260],[480,260],[480,600],[0,600]], centroid_px: [240,430],
    openings: [{ kind: "baie", width_m: 2.4 }, { kind: "fenetre", width_m: 1.4 }, { kind: "porte", width_m: 0.9 }] },
  { name: "Entrada", polygon_px: [[320,0],[480,0],[480,260],[320,260]], centroid_px: [400,130],
    openings: [{ kind: "porte", width_m: 1.0 }, { kind: "porte", width_m: 0.8 }] },
  { name: "Quarto 1", polygon_px: [[480,0],[800,0],[800,300],[480,300]], centroid_px: [640,150],
    openings: [{ kind: "fenetre", width_m: 1.4 }, { kind: "porte", width_m: 0.8 }] },
  { name: "Quarto 2", polygon_px: [[480,300],[800,300],[800,600],[480,600]], centroid_px: [640,450],
    openings: [{ kind: "fenetre", width_m: 1.4 }, { kind: "porte", width_m: 0.8 }] },
];
const HERO_WALLS = [
  // Murs porteurs (périmètre + refend central)
  { x1: 0, y1: 0, x2: 800, y2: 0, wall_type: "porteur", thickness_px: 18 },
  { x1: 800, y1: 0, x2: 800, y2: 600, wall_type: "porteur", thickness_px: 18 },
  { x1: 800, y1: 600, x2: 0, y2: 600, wall_type: "porteur", thickness_px: 18 },
  { x1: 0, y1: 600, x2: 0, y2: 0, wall_type: "porteur", thickness_px: 18 },
  { x1: 480, y1: 0, x2: 480, y2: 600, wall_type: "porteur", thickness_px: 18 },
  // Cloisons intérieures
  { x1: 0, y1: 260, x2: 480, y2: 260, wall_type: "cloison", thickness_px: 10 },
  { x1: 320, y1: 0, x2: 320, y2: 260, wall_type: "cloison", thickness_px: 10 },
  { x1: 480, y1: 300, x2: 800, y2: 300, wall_type: "cloison", thickness_px: 10 },
];

const STEPS = [
  { icon: MessageSquare, title: "Descrevo o meu projeto", text: "Numa frase, como a um profissional." },
  { icon: Sparkles, title: "ConstruPilot compreende", text: "Especialidades, superfícies, nível de acabamento, riscos." },
  { icon: Calculator, title: "O motor calcula", text: "Quantidades e preços determinísticos, verificáveis." },
  { icon: Search, title: "Encontro os melhores preços", text: "Comparação multi-fornecedores e cesto otimizado." },
  { icon: Wrench, title: "Sei o que fazer eu próprio", text: "Guias passo a passo e níveis de dificuldade." },
  { icon: Hammer, title: "Chamo um profissional se necessário", text: "Contacto com um profissional verificado." },
];

const FEATURES = [
  { icon: Calculator, tKey: "landing.feat.calc_t", title: "Calculadoras profissionais", dKey: "landing.feat.calc_d", text: "Pintura, azulejos, pladur, betão, isolamento: quantidades exatas com margens.", to: "/calculadoras", span: "md:col-span-4" },
  { icon: Search, tKey: "landing.feat.price_t", title: "Comparador de preços", dKey: "landing.feat.price_d", text: "Preços recolhidos nas lojas de materiais de construção, com data da recolha, histórico das suas pesquisas e alertas.", to: "/precos", span: "md:col-span-4" },
  { icon: Cuboid, tKey: "landing.feat.threed_t", title: "Geração 3D", dKey: "landing.feat.threed_d", text: "Visualize o seu projeto em três dimensões a partir de uma simples planta 2D.", to: "/plan", span: "md:col-span-8 lg:col-span-4" },
  { icon: Wrench, tKey: "landing.feat.diy_t", title: "Modo «faço eu mesmo»", dKey: "landing.feat.diy_d", text: "Materiais calculados + guia profissional passo a passo.", to: "/diy", span: "md:col-span-4 lg:col-span-4" },
  { icon: Camera, tKey: "landing.feat.photo_t", title: "Estimativa por foto", dKey: "landing.feat.photo_d", text: "A IA identifica a divisão, o seu estado e as obras prováveis.", to: "/photo", span: "md:col-span-4 lg:col-span-4" },
  { icon: FileText, tKey: "landing.feat.scan_t", title: "Scanner de orçamentos", dKey: "landing.feat.scan_d", text: "Preço baixo, correto, alto: a IA analisa e compara os seus orçamentos.", to: "/scanner-devis", span: "md:col-span-4 lg:col-span-4" },
];

const AUDIENCES = [
  { icon: HardHat, key: "landing.for_pro", title: "Artesãos construção", textKey: "landing.for_pro_text", text: "Gere os seus orçamentos para clientes com declaração para IVA a 6 %, assinatura eletrónica e acompanhamento de abertura." },
  { icon: HomeIcon, key: "landing.for_particulier", title: "Particulares", textKey: "landing.for_particulier_text", text: "Estime a sua renovação antes de contactar um profissional. Compare os orçamentos recebidos." },
  { icon: Building2, key: "landing.aud.arch_t", title: "Arquitetos", textKey: "landing.aud.arch_d", text: "Medição 2D automática a partir das suas plantas PDF/DXF, orçamento instantâneo por lote, render 3D para os seus clientes." },
  { icon: Store, key: "landing.aud.merch_t", title: "Comerciantes", textKey: "landing.aud.merch_d", text: "Os seus preços, comparados em tempo real. Gere a lista de compras a partir de uma planta." },
  { icon: GraduationCap, key: "landing.aud.school_t", title: "Escolas de construção", textKey: "landing.aud.school_d", text: "Um campo de treino pedagógico: IA, calculadoras e guias de ofício gratuitos." },
  { icon: Factory, key: "landing.aud.dev_t", title: "Promotores", textKey: "landing.aud.dev_d", text: "Orçamento rápido para as suas propostas. Orçamento multiplanta consolidado, tour de vídeo 3D para anexar." },
];

const FAQ = [
  { qKey: "landing.faq.q1", q: "Quanto custa uma renovação completa por m² em 2026?", aKey: "landing.faq.a1", a: "Numa remodelação profunda em Portugal, conte com 700 a 1 500 €/m² consoante a região e a gama. Estes intervalos são indicativos: o ConstruPilot calcula uma estimativa detalhada a partir das suas áreas e do seu nível de acabamento." },
  { qKey: "landing.faq.q2", q: "O ConstruPilot é gratuito?", aKey: "landing.faq.a2", a: "Existe uma oferta gratuita (2 projetos, 3 estimativas por mês). Para particulares, o Premium custa 19 €/mês. Para profissionais, a oferta Pro começa em 149 €/mês e a Pro Business em 249 €/mês, com 7 dias de experiência." },
  { qKey: "landing.faq.q3", q: "Como funciona a medição 2D automática?", aKey: "landing.faq.a3", a: "Carregue a sua planta (PDF, PNG, DXF). O nosso motor deteta automaticamente as paredes, as portas e calcula as áreas." },
  { qKey: "landing.faq.q4", q: "Posso gerar um orçamento com certificado de IVA a 10%?", aKey: "landing.faq.a4", a: "Sim. O ConstruPilot gera o certificado exigido para a renovação de habitações com mais de 2 anos. O cliente assina-o online." },
  { qKey: "landing.faq.q5", q: "Os vossos preços de materiais estão atualizados?", aKey: "landing.faq.a5", a: "Os preços são recolhidos em direto nos sites públicos das lojas no momento da sua pesquisa, com a data da recolha apresentada. Se não for encontrado nenhum preço público, é apresentado um intervalo indicativo, assinalado como tal." },
  { qKey: "landing.faq.q6", q: "A IA substitui um profissional?", aKey: "landing.faq.a6", a: "Não. Fornece uma estimativa instantânea. Para uma obra complexa, um profissional continua indispensável." },
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
    badgeKey: "landing.hero.badge_part", badge: "Para particulares",
    h1aKey: "landing.hero.h1a_part", h1a: "Estime o custo da",
    h1bKey: "landing.hero.h1b_part", h1b: "sua obra, lote por lote.",
    subKey: "landing.hero.sub_part",
    sub: "Descreva o seu projeto de remodelação. O ConstruPilot calcula uma estimativa detalhada, artigo a artigo — antes mesmo de contactar um profissional.",
    ctaKey: "landing.hero.cta_part", cta: "Estimar a minha obra",
    dest: "/smart-project",
  },
  pro: {
    badgeKey: "landing.hero.badge_pro", badge: "Para profissionais da construção",
    h1aKey: "landing.hero.h1a_pro", h1a: "Orce e edite",
    h1bKey: "landing.hero.h1b_pro", h1b: "os seus orçamentos num instante.",
    subKey: "landing.hero.sub_pro",
    sub: "Descreva a obra. O ConstruPilot gera a estimativa, as quantidades, os preços exatos de fornecedores e o orçamento PDF com planta 3D interativa.",
    ctaKey: "landing.hero.cta_pro", cta: "Gerar o meu orçamento",
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
  const videoRef = useRef(null);
  const [videoMuted, setVideoMuted] = useState(true);
  const masterVideoRef = useRef(null);
  const [masterMuted, setMasterMuted] = useState(true);
  const toggleMasterSound = () => {
    const v = masterVideoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setMasterMuted(v.muted);
    if (!v.muted) v.play().catch(() => {});
  };
  const toggleVideoSound = () => {
    const v = videoRef.current;
    if (!v) return;
    v.muted = !v.muted;
    setVideoMuted(v.muted);
    if (!v.muted) v.play().catch(() => {});
  };
  const navigate = useNavigate();
  const { t, lang } = useI18n();
  const offer = useOffer();

  useEffect(() => {
    api.get("/estimation/catalog").then(({ data }) => setTypes(data.project_types)).catch(() => {});
    const sp = new URLSearchParams(window.location.search);
    const ref = sp.get("ref");
    if (ref) sessionStorage.setItem("construpilot_ref", ref.toUpperCase());
    ["utm_source", "utm_medium", "utm_campaign"].forEach((k) => {
      const v = sp.get(k);
      if (v) sessionStorage.setItem(`construpilot_${k}`, v);
    });
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
    const utm_source = sessionStorage.getItem("construpilot_utm_source") || "";
    const utm_medium = sessionStorage.getItem("construpilot_utm_medium") || "";
    const utm_campaign = sessionStorage.getItem("construpilot_utm_campaign") || "";
    const source = utm_source || `landing-hero-${audience}`;
    const leadPayload = { email: mail, description: text, source, utm_source, utm_medium, utm_campaign };
    const isLoggedIn = localStorage.getItem("construpilot_session") === "1";
    if (isLoggedIn) {
      if (mail && mail.includes("@")) api.post("/leads", leadPayload).catch(() => {});
      navigate(hero.dest);
      return;
    }
    // Compte requis avant d'envoyer la demande : on garde la demande et on redirige vers l'inscription
    sessionStorage.setItem("construpilot_pending_lead", JSON.stringify(leadPayload));
    navigate(`/inscription?email=${encodeURIComponent(mail)}&signup=1`);
  };

  return (
    <>
      <SEO
        title={null}
        description="ConstruPilot: o assistente IA da construção. Orçamente, compare preços de materiais, calcule as suas quantidades e emita orçamentos em PDF com planta 3D interativa."
        keywords="orçamento obras, estimativa remodelação, calculadora materiais, comparador preços construção, software orçamentos profissional, planta 2D 3D, preço remodelação casa"
        canonical="/"
        jsonLd={{
          "@context": "https://schema.org",
          "@type": "FAQPage",
          "mainEntity": FAQ.map(({ q, a, qKey }) => ({
            "@type": "Question",
            "name": q,
            "acceptedAnswer": {
              "@type": "Answer",
              "text": qKey === "landing.faq.q2" && offer ? offerSentence(offer, "fr") : a,
            },
          }))
        }}
      />
      <Nav />

      {offer?.free_promo && (
        <div className="bg-primary text-primary-foreground text-center text-sm font-semibold px-4 py-2.5 flex flex-wrap items-center justify-center gap-2" data-testid="promo-banner">
          <Sparkles className="h-4 w-4" />
          {t("landing.promo")}
          <Link to="/planos" className="underline underline-offset-2 hover:opacity-80 font-normal">
            {t("landing.promo_terms", "Ver os planos aplicáveis depois")}
          </Link>
          <Link to="/inscription" className="underline underline-offset-2 hover:opacity-80">{t("landing.promo_cta")}</Link>
        </div>
      )}
      <SignupCounter />
      <LandingInstallBanner />

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
                  <User className="h-4 w-4" /> {t("landing.hero.seg_part", "Sou um particular")}
                </button>
                <button
                  role="tab"
                  aria-selected={audience === "pro"}
                  data-testid="hero-audience-pro"
                  onClick={() => setAudience("pro")}
                  className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold transition-colors ${audience === "pro" ? "bg-primary text-white shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >
                  <HardHat className="h-4 w-4" /> {t("landing.hero.seg_pro", "Sou um profissional")}
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
                    placeholder={t("landing.hero.placeholder", `Descreva o seu projeto — ex.: « ${EXAMPLE} »`)}
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
                      placeholder={t("landing.hero.email_ph", "O seu email (para receber o orçamento)")}
                      className="ps-9 border-0 bg-background/60 rounded-lg h-11 focus-visible:ring-1 focus-visible:ring-primary/40"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 p-2 pt-2">
                    <button
                      onClick={() => setDescription(EXAMPLE)} data-testid="hero-example-btn"
                      className="text-xs font-medium text-muted-foreground hover:text-primary transition-colors"
                    >
                      {t("landing.hero.example_btn", "Usar o exemplo")}
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
                  {t("landing.hero.reassurance", "Gratuito e sem compromisso — resultado em 30 segundos.")}
                </p>
                {audience === "pro" && (
                  <button
                    onClick={() => navigate("/pro")}
                    data-testid="hero-pro-offer-link"
                    className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline underline-offset-4"
                  >
                    Descobrir a oferta Pro (experiência de 7 dias) <ArrowRight className="h-4 w-4" />
                  </button>
                )}
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
                  <span className="font-bold text-foreground">{t("landing.hero.trust_title", "Concebido para os profissionais da construção")}</span>
                  <span className="text-xs">{t("landing.hero.trust_subtitle", "Artesãos, PME e arquitetos")}</span>
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
                  <div className="absolute bottom-6 left-6 z-20 flex flex-col gap-1 pointer-events-none">
                     <span className="text-[10px] uppercase font-bold tracking-widest text-primary">{t("landing.hero.live_view", "Vista em direto")}</span>
                     <span className="text-sm font-semibold">{t("landing.hero.plan3d", "Geração de planta 3D")}</span>
                  </div>
                  {/* Reuse the existing Interactive3D component with mock data */}
                  <div className="h-full w-full overflow-hidden rounded-xl bg-background/50">
                     <Interactive3D 
                        rooms={HERO_ROOMS} 
                        walls={HERO_WALLS} 
                        scaleMperPx={0.012} 
                        imageHeight={600} 
                     />
                  </div>
               </div>
            </motion.div>

          </div>
        </div>
      </section>

      <DemoShowcase />


      {/* ── VIDÉO EXPLICATIVE : lecture des plans ─────────────── */}
      <section className="border-b border-border bg-secondary/20" data-testid="intro-video-section">
        <div className="mx-auto max-w-[1500px] px-6 lg:px-10 py-20 lg:py-28">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-16 items-center">
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ duration: 0.6 }}
            >
              <p className="overline">{t("landing.video.overline", "Em 1 minuto")}</p>
              <h2 className="mt-4 font-display text-4xl lg:text-5xl font-bold tracking-tight text-foreground">
                {t("landing.video.title_a", "Veja como o ConstruPilot")}<br className="hidden md:block" />
                <span className="text-primary italic">{t("landing.video.title_b", "lê os seus projetos")}</span>
              </h2>
              <p className="mt-6 text-base sm:text-lg text-muted-foreground leading-relaxed max-w-xl">
                {t("landing.video.subtitle", "Importe uma planta (PDF ou DWG), calibre a escala em 2 cliques, depois deixe a IA detetar as divisões, paredes, pilares, vigas e calcular as medições e a estimativa — automaticamente.")}
              </p>
              <ul className="mt-8 space-y-3">
                {[
                  t("landing.video.step1", "Importação da planta PDF / DWG — tudo é preservado (cotas, legenda)"),
                  t("landing.video.step2", "Calibragem da escala em 2 cliques"),
                  t("landing.video.step3", "Análise automática: divisões, paredes, pilares, vigas, escadas"),
                  t("landing.video.step4", "Medições quantificadas (betão, cofragem, aços) e orçamento em 1 clique"),
                ].map((s, i) => (
                  <li key={i} className="flex items-start gap-3 text-sm text-foreground" data-testid={`video-step-${i}`}>
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-bold">{i + 1}</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-10">
                <Link to="/inscription">
                  <Button size="lg" className="rounded-lg gap-2 shadow-md" data-testid="video-cta-btn">
                    <Sparkles className="h-4 w-4" /> {t("landing.video.cta", "Experimentar gratuitamente")}
                  </Button>
                </Link>
              </div>
            </motion.div>
          </div>
        </div>
      </section>


      {/* ── MARKETING TEASER (mobile mockup) ─────────────── */}
      <MarketingTeaser />

      {/* ── TRUST & LOGOS ───────────────────────────────── */}
      <TrustSection />

      {/* ── PUB : Bibliothèque paramétrique ────────────────── */}
      <ParamLibraryPromo />

      {/* ── BENTO FEATURES GRID ────────────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
        <div className="max-w-2xl">
          <p className="overline">{t("landing.feat.overline", "O arsenal completo")}</p>
          <h2 className="mt-4 font-display text-4xl lg:text-5xl font-bold tracking-tight text-foreground">
            {t("landing.feat.title_a", "Ferramentas de profissional,")} <br className="hidden md:block" />
            <span className="text-muted-foreground">{t("landing.feat.title_b", "repensadas para a eficiência.")}</span>
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
                  <h3 className="font-display text-xl font-bold text-foreground">{t(f.tKey, f.title)}</h3>
                  <p className="mt-3 text-sm text-muted-foreground leading-relaxed">{t(f.dKey, f.text)}</p>
                </div>
              </div>
              {/* Subtle hover gradient */}
              <div className="absolute inset-0 bg-gradient-to-tr from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── FEATURE SHOWCASE (interactif / publicité) ────────── */}
      <FeatureShowcase />

      {/* ── CATALOGUE / PROJECT TYPES ─────────────────────── */}
      <section className="border-y border-border bg-secondary/30 relative">
        <div className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-8 mb-16">
            <div className="max-w-xl">
              <p className="overline">{t("landing.cat.overline", "Catálogo de trabalhos")}</p>
              <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
                {t("landing.cat.title", "Comece com o pé direito")}
              </h2>
            </div>
            <Button variant="outline" onClick={() => navigate('/smart-project')} className="rounded-full">
              {t("landing.cat.all_btn", "Ver todos os modelos")} <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </div>

          <motion.div 
            className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6"
            variants={containerVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
          >
            {types.length > 0 ? types.map((pt, i) => (
              <motion.button
                variants={itemVariants}
                key={pt.key}
                data-testid={`category-card-${pt.key}`}
                onClick={() => navigate(`/estimation?type=${pt.key}`)}
                className="group relative h-64 w-full overflow-hidden rounded-2xl text-left border border-white/10"
              >
                <img
                  src={IMAGES[pt.image] || IMAGES.project_card_interior} alt={pt.name}
                  className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-110"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent" />
                <div className="relative h-full p-6 flex flex-col justify-between">
                  <div className="self-end px-3 py-1 rounded-full bg-black/40 backdrop-blur-md border border-white/20">
                    <p className="num text-xs text-white/90 font-medium">{String(i + 1).padStart(2, "0")}</p>
                  </div>
                  <div>
                    <h3 className="font-display text-2xl font-semibold text-white leading-tight">{pt.name}</h3>
                    <div className="mt-3 flex items-center gap-2 text-sm text-primary font-medium opacity-0 translate-y-2 group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-300">
                      {t("landing.cat.estimate_now", "Estimar agora")} <ArrowRight className="h-4 w-4" />
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
                <span className="text-xs font-semibold uppercase tracking-widest text-foreground">{t("landing.cmp.badge", "Tomada de decisão")}</span>
              </div>
              <h2 className="font-display text-3xl lg:text-4xl font-bold tracking-tight">
                {t("landing.cmp.title_a", "Fazer você mesmo ou")} <br className="hidden sm:block" />{t("landing.cmp.title_b", "contratar um profissional?")}
              </h2>
              <p className="mt-6 text-base text-muted-foreground leading-relaxed">
                {t("landing.cmp.desc_1", "O ConstruPilot compara em tempo real o custo de material puro e o custo com mão de obra. Avalie o tempo necessário, a complexidade e os riscos. ")}
                <strong className="text-foreground">{t("landing.cmp.desc_strong", "O sistema avisa-o automaticamente")}</strong>{t("landing.cmp.desc_2", " quando um profissional qualificado é indispensável (estrutura, eletricidade, amianto).")}
              </p>
              <div className="mt-10 flex flex-wrap gap-4">
                <Link to="/diy">
                  <Button className="rounded-full px-8 shadow-md">
                    <Wrench className="mr-2 h-4 w-4" /> {t("landing.cmp.diy_btn", "Modo Autonomia")}
                  </Button>
                </Link>
                <Link to="/estimation">
                  <Button variant="secondary" className="rounded-full px-8">
                    <PenTool className="mr-2 h-4 w-4" /> {t("landing.cmp.pro_btn", "Orçamento profissional")}
                  </Button>
                </Link>
              </div>
            </div>
            
            {/* Visual Data Comparison */}
            <div className="grid sm:grid-cols-2 gap-4">
              <div className="p-6 border border-border rounded-2xl bg-background/50 backdrop-blur-sm flex flex-col justify-center">
                <p className="text-xs uppercase font-bold tracking-wider text-muted-foreground mb-4">{t("landing.cmp.artisan_cost", "Custo profissional")}</p>
                <p className="num text-3xl font-extrabold text-foreground">{eur(10500)}</p>
                <p className="text-sm text-muted-foreground mt-2">{t("landing.cmp.artisan_sub", "Mão de obra incluída, com garantia da obra.")}</p>
              </div>
              
              <div className="p-6 border border-primary/30 rounded-2xl bg-primary/5 backdrop-blur-sm flex flex-col justify-center shadow-inner relative overflow-hidden">
                <div className="absolute top-0 right-0 w-24 h-24 bg-primary/10 rounded-full blur-2xl" />
                <p className="text-xs uppercase font-bold tracking-wider text-primary mb-4">{t("landing.cmp.diy_cost", "Custo DIY (só materiais)")}</p>
                <p className="num text-3xl font-extrabold text-primary">{eur(5800)}</p>
                <div className="mt-4 inline-flex items-center text-xs font-semibold text-emerald-600 bg-emerald-500/10 px-2 py-1 rounded-md w-fit">
                  <TrendingDown className="h-3 w-3 mr-1" /> {t("landing.cmp.savings", "Poupança")} {eur(4700)}
                </div>
              </div>
              
              <div className="sm:col-span-2 p-5 border border-border rounded-2xl bg-background/50 flex items-start gap-4">
                <ShieldCheck className="h-6 w-6 text-primary shrink-0 mt-0.5" />
                <p className="text-sm text-muted-foreground leading-relaxed">
                  <strong className="text-foreground">{t("landing.cmp.ai_label", "Análise IA (WC 8 m²):")}</strong> {t("landing.cmp.ai_text", "Pintura e acabamentos possíveis por um iniciante. Canalização e quadro elétrico a confiar a um profissional certificado.")}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── AUDIENCES / POUR QUI ───────────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-6 lg:px-10 pb-24 lg:pb-32">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <p className="overline">{t("landing.aud.overline", "Para quem?")}</p>
          <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            {t("landing.aud.title", "Um ecossistema conectado para todos os agentes da construção")}
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
                <h3 className="font-display text-xl font-semibold">{t(a.key, a.title)}</h3>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed">{t(a.textKey, a.text)}</p>
            </motion.div>
          ))}
        </motion.div>
      </section>

      {/* ── FAQ ────────────────────────────────────────────── */}
      <section className="border-t border-border bg-background" id="faq">
        <div className="mx-auto max-w-[1000px] px-6 lg:px-10 py-24 lg:py-32">
          <div className="text-center mb-16">
            <p className="overline">{t("landing.faq.overline", "Perguntas frequentes")}</p>
            <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
              {t("landing.faq.title", "Tudo o que precisa de saber")}
            </h2>
          </div>
          
          <OfferNotice lang={lang} className="mb-8" />

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
                    <span className="font-display font-semibold text-lg pr-8 text-foreground">{t(item.qKey, item.q)}</span>
                    <div className={`h-8 w-8 rounded-full border flex items-center justify-center shrink-0 transition-colors ${open ? 'border-primary bg-primary text-white' : 'border-border text-muted-foreground'}`}>
                      <ChevronDown className={`h-4 w-4 transition-transform duration-300 ${open ? "rotate-180" : ""}`} />
                    </div>
                  </button>
                  
                  {/* Framer motion animate presence would be better here, but CSS is fine for MVP */}
                  <div 
                    className={`overflow-hidden transition-all duration-300 ease-in-out ${open ? 'max-h-[500px] opacity-100' : 'max-h-0 opacity-0'}`}
                  >
                    <div className="px-6 pb-6 pt-2 text-base text-muted-foreground leading-relaxed border-t border-border/50">
                      {item.qKey === "landing.faq.q2" && offer
                        ? offerSentence(offer, lang)
                        : t(item.aKey, item.a)}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── BLOG (Soro embed) ──────────────────────────────── */}
      <SoroBlog />

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
            <Sparkles className="h-4 w-4" /> {t("landing.sticky.cta", "Estimar o meu projeto")}
          </Button>
        </div>
      </div>

      <Footer />
    </>
  );
}
