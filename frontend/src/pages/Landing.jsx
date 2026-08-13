import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  ArrowRight, Sparkles, Calculator, Search, Wrench, ShieldCheck, FileText,
  MessageSquare, Camera, TrendingDown, Hammer, ChevronRight, Building2,
  HardHat, Home as HomeIcon, Store, GraduationCap, Factory, ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import { TrustSection } from "@/components/TrustSection";
import { api, IMAGES, eur } from "@/lib/api";

const EXAMPLE =
  "Je veux rénover une maison de 150 m², refaire les murs, plafonds, électricité, plomberie, deux salles de bain et remplacer les fenêtres.";

const STEPS = [
  { icon: MessageSquare, title: "Je décris mon projet", text: "En une phrase, comme à un artisan." },
  { icon: Sparkles, title: "ConstruPilot comprend", text: "Lots, surfaces, niveau de finition, risques." },
  { icon: Calculator, title: "Le moteur calcule", text: "Quantités et prix déterministes, vérifiables." },
  { icon: Search, title: "Je trouve les meilleurs prix", text: "Comparaison multi-fournisseurs et panier optimisé." },
  { icon: Wrench, title: "Je sais quoi faire moi-même", text: "Guides pas à pas et niveaux de difficulté." },
  { icon: Hammer, title: "J'appelle un pro ConstruPilot si besoin", text: "Proposition professionnelle en 48 h." },
];

const FEATURES = [
  { icon: Calculator, title: "Calculateurs pros", text: "Peinture, carrelage, placo, béton, isolation : quantités exactes avec marges.", to: "/calculateurs" },
  { icon: Search, title: "Comparateur de prix", text: "10 fournisseurs, livraison, stock, historique et alertes prix.", to: "/prix" },
  { icon: Wrench, title: "Mode « je le fais moi-même »", text: "Matériaux calculés + guide professionnel étape par étape.", to: "/diy" },
  { icon: Camera, title: "Estimation par photo", text: "L'IA identifie la pièce, son état et les travaux probables.", to: "/photo" },
  { icon: FileText, title: "Scanner de devis", text: "Prix bas, correct, élevé : l'IA analyse et compare vos devis.", to: "/scanner-devis" },
  { icon: MessageSquare, title: "Coach IA ConstruPilot", text: "Toutes vos questions travaux, réponses de professionnel.", to: "/coach" },
];

// SEO — publics visés (pour section "Pour qui ?")
const AUDIENCES = [
  { icon: HardHat, title: "Artisans BTP",       text: "Générez vos devis client en 30 s avec attestation TVA 10 %, signature électronique et suivi ouverture." },
  { icon: HomeIcon, title: "Particuliers",      text: "Estimez votre rénovation avant de contacter un pro. Comparez les devis reçus." },
  { icon: Building2, title: "Architectes",      text: "Métré 2D auto depuis vos plans PDF/DXF, chiffrage instantané par lot, rendu 3D pour vos clients." },
  { icon: Store, title: "Marchands de matériaux", text: "Vos prix, comparés en temps réel. Générez la liste de courses depuis un plan." },
  { icon: GraduationCap, title: "Écoles BTP",   text: "Un terrain de jeu pédagogique : IA, calculateurs et guides métier accessibles gratuitement." },
  { icon: Factory, title: "Promoteurs & CMI",   text: "Chiffrage rapide pour vos offres. Devis multi-plans consolidé, tour vidéo 3D à joindre." },
];

// SEO — Q&A extrait Google People-Also-Ask sur les mots-clés du BTP
const FAQ = [
  {
    q: "Combien coûte une rénovation complète au m² en 2026 ?",
    a: "En rénovation lourde en France, comptez 900 à 1 800 €/m² selon la région et la gamme (éco / standard / premium). ConstruPilot calcule votre estimation exacte en 30 secondes à partir d'une simple description de votre projet.",
  },
  {
    q: "ConstruPilot est-il gratuit ?",
    a: "Oui pour les particuliers : estimation, calculateurs matériaux, comparateur de prix, coach IA et guides DIY sont gratuits. Une offre Pro (devis PDF illimités, signature client, rendu 3D IA, tour vidéo) est disponible pour les artisans dès 39 €/mois.",
  },
  {
    q: "Comment fonctionne le métré 2D automatique ?",
    a: "Uploadez votre plan (PDF, PNG, DXF). Notre moteur OpenCV détecte automatiquement les murs, les portes et calcule les surfaces au m² pour chaque pièce. Vous pouvez ensuite étiqueter les pièces d'un clic et générer estimation + devis + rendu 3D en un seul flux.",
  },
  {
    q: "Puis-je générer un devis avec attestation TVA à 10 % ?",
    a: "Oui. ConstruPilot génère automatiquement l'attestation TVA à taux réduit (art. 279-0 bis CGI) requise pour bénéficier du taux 10 % en rénovation de logement de plus de 2 ans. Le client la signe en ligne, vous êtes couvert.",
  },
  {
    q: "Vos prix matériaux sont-ils à jour ?",
    a: "Nous croisons les catalogues des principales enseignes du BTP (Point.P, Leroy Merlin, Castorama, Brico Dépôt…) mis à jour hebdomadairement, avec l'historique 12 mois pour détecter les hausses.",
  },
  {
    q: "L'IA remplace-t-elle un métreur ou un architecte ?",
    a: "Non. ConstruPilot fournit une estimation instantanée avec ±20 % de précision, idéale pour un premier chiffrage ou une comparaison. Pour un chantier complexe (structure, mur porteur, gros œuvre), un professionnel reste indispensable — et notre coach IA vous dit quand le consulter.",
  },
];

const FAQ_JSON_LD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": FAQ.map(({ q, a }) => ({
    "@type": "Question",
    "name": q,
    "acceptedAnswer": { "@type": "Answer", "text": a },
  })),
};

export default function Landing() {
  const [description, setDescription] = useState("");
  const [types, setTypes] = useState([]);
  const [openFaq, setOpenFaq] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/estimation/catalog").then(({ data }) => setTypes(data.project_types)).catch(() => {});
    // Capture ?ref=CODE from landing URL — persists into signup flow
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) sessionStorage.setItem("construpilot_ref", ref.toUpperCase());
  }, []);

  const launch = () => {
    const text = description.trim() || EXAMPLE;
    sessionStorage.setItem("construpilot_description", text);
    navigate("/smart-project");
  };

  return (
    <>
      <SEO
        title={null}
        description="ConstruPilot : l'assistant IA du BTP. Générez un devis chiffré en 30 s, comparez les prix matériaux de 10 fournisseurs, calculez vos quantités exactes et éditez vos devis clients PDF avec tour vidéo 3D. Gratuit pour les particuliers."
        keywords="devis travaux, estimation rénovation, calculateur matériaux, comparateur prix BTP, logiciel devis artisan, plan 2D 3D, prix rénovation maison, IA construction, devis en ligne gratuit, métré automatique"
        canonical="/"
        jsonLd={FAQ_JSON_LD}
      />
      <Nav />

      <section className="relative overflow-hidden border-b border-border grain">
        <img
          src={IMAGES.hero} alt="Rénovation maison contemporaine : estimation IA travaux ConstruPilot"
          className="absolute inset-0 h-full w-full object-cover opacity-25 dark:opacity-20"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="relative mx-auto max-w-[1500px] px-5 lg:px-8 py-20 lg:py-28">
          <div className="max-w-3xl">
            <p className="overline animate-rise">Devis Travaux IA · Estimation Rénovation en 30 secondes</p>
            <h1 className="mt-5 font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter animate-rise">
              Estimez vos travaux.<br />
              Comparez les prix.<br />
              <span className="text-primary">Construisez sereinement.</span>
            </h1>
            <p className="mt-6 text-base md:text-lg text-muted-foreground max-w-2xl animate-rise">
              L'assistant IA du BTP pour <strong>artisans</strong>, <strong>particuliers</strong> et
              <strong> architectes</strong>. Décrivez votre projet : ConstruPilot le décompose en lots,
              chiffre chaque poste, calcule les matériaux et trouve les meilleurs prix France 2026.
            </p>

            <div className="mt-10 relative animate-rise">
              <div className="absolute -inset-1 bg-primary/25 blur-2xl rounded-md animate-glow" aria-hidden="true" />
              <div className="relative surface glow-ring p-2">
                <Textarea
                  data-testid="hero-ai-input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder={`Décrivez votre projet — ex : « ${EXAMPLE} »`}
                  rows={4}
                  className="resize-none border-0 bg-transparent text-base focus-visible:ring-0 rounded-sm"
                />
                <div className="flex flex-wrap items-center gap-3 p-2 pt-0">
                  <Button
                    onClick={launch} data-testid="hero-submit-btn"
                    className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
                  >
                    <Sparkles className="h-4 w-4" /> Créer mon estimation
                  </Button>
                  <button
                    onClick={() => setDescription(EXAMPLE)} data-testid="hero-example-btn"
                    className="text-xs text-muted-foreground hover:text-primary transition-colors"
                  >
                    Utiliser l'exemple
                  </button>
                  <span className="ml-auto text-xs text-muted-foreground hidden sm:block">
                    Estimez. Comparez. Construisez.
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-8 flex flex-wrap gap-6 text-sm text-muted-foreground">
              {[["Lots détaillés", "14+"], ["Fournisseurs comparés", "10"], ["Calculateurs pros", "5"]].map(([l, v]) => (
                <div key={l}>
                  <p className="num text-xl font-bold text-foreground">{v}</p>
                  <p className="text-xs uppercase tracking-wider">{l}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ── Trust Bar (logos + counter + testimonials) ────────────── */}
      <TrustSection />

      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-20">
        <p className="overline">Catalogue travaux</p>
        <h2 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
          Quel projet voulez-vous réaliser ?
        </h2>
        <div className="mt-10 grid sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger" data-testid="project-types-grid">
          {types.map((t, i) => (
            <button
              key={t.key}
              data-testid={`category-card-${t.key}`}
              onClick={() => navigate(`/estimation?type=${t.key}`)}
              className="group relative h-40 overflow-hidden rounded-md border border-border text-left transition-transform duration-200 hover:-translate-y-1"
            >
              <img
                src={IMAGES[t.image] || IMAGES.project_card_interior} alt={t.name}
                className="absolute inset-0 h-full w-full object-cover opacity-60 transition-transform duration-500 group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent" />
              <div className="relative h-full p-5 flex flex-col justify-end">
                <p className="num text-[10px] text-primary font-bold">{String(i + 1).padStart(2, "0")}</p>
                <p className="font-display text-lg font-semibold text-white leading-tight">{t.name}</p>
                <p className="mt-1 text-xs text-white/70 flex items-center gap-1">
                  Estimer <ChevronRight className="h-3 w-3 transition-transform group-hover:translate-x-1" />
                </p>
              </div>
            </button>
          ))}
        </div>
      </section>

      <section className="border-y border-border bg-secondary/30">
        <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-20">
          <p className="overline">Le parcours ConstruPilot</p>
          <h2 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Le copilote intelligent de vos travaux
          </h2>
          <div className="mt-12 grid md:grid-cols-2 lg:grid-cols-3 gap-x-10 gap-y-8 stagger">
            {STEPS.map((s, i) => (
              <div key={s.title} className="flex gap-4">
                <div className="shrink-0 h-11 w-11 grid place-items-center border border-primary/40 bg-primary/10 rounded-sm">
                  <s.icon className="h-5 w-5 text-primary" aria-hidden="true" />
                </div>
                <div>
                  <p className="num text-[10px] text-primary font-bold">ÉTAPE {i + 1}</p>
                  <h3 className="font-display font-semibold">{s.title}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">{s.text}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-20">
        <p className="overline">Tout l'outillage</p>
        <h2 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
          Des outils de professionnel, accessibles à tous
        </h2>
        <div className="mt-10 grid md:grid-cols-2 lg:grid-cols-3 gap-4 stagger">
          {FEATURES.map((f) => (
            <Link
              key={f.title} to={f.to} data-testid={`feature-card-${f.to.slice(1)}`}
              className="surface p-7 group transition-transform duration-200 hover:-translate-y-1 hover:border-primary/60"
            >
              <f.icon className="h-6 w-6 text-primary" aria-hidden="true" />
              <h3 className="mt-5 font-display text-lg font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{f.text}</p>
              <p className="mt-5 text-xs text-primary flex items-center gap-1">
                Ouvrir <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-1" />
              </p>
            </Link>
          ))}
        </div>
      </section>

      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 pb-20">
        <div className="surface p-8 lg:p-12 relative overflow-hidden grain">
          <div className="absolute -left-20 -bottom-20 h-72 w-72 bg-primary/20 blur-3xl rounded-full" />
          <div className="relative grid lg:grid-cols-2 gap-10 items-center">
            <div>
              <p className="overline">Faire moi-même ou artisan ?</p>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight">
                Voyez immédiatement ce que vous pouvez économiser
              </h2>
              <p className="mt-4 text-sm text-muted-foreground">
                ConstruPilot compare le coût professionnel et le coût en autonomie, le temps nécessaire,
                la difficulté et le risque. Et vous alerte quand un professionnel est indispensable
                (gaz, tableau électrique, mur porteur, structure, amiante).
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/diy">
                  <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white" data-testid="cta-diy-btn">
                    <Wrench className="h-4 w-4" /> Voir les guides DIY
                  </Button>
                </Link>
                <Link to="/estimation">
                  <Button variant="outline" className="rounded-sm gap-2" data-testid="cta-estimate-btn">
                    <Calculator className="h-4 w-4" /> Estimer mon chantier
                  </Button>
                </Link>
              </div>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              {[["Professionnel", eur(10500), ""], ["DIY", eur(5800), "text-primary"],
                ["Économie", eur(4700), "text-emerald-500"]].map(([l, v, c]) => (
                <div key={l} className="p-5 border border-border rounded-sm bg-background/60">
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">{l}</p>
                  <p className={`num mt-2 text-xl font-bold ${c}`}>{v}</p>
                </div>
              ))}
              <div className="sm:col-span-3 p-5 border border-border rounded-sm bg-background/60 flex items-start gap-3">
                <ShieldCheck className="h-5 w-5 text-primary shrink-0 mt-0.5" />
                <p className="text-xs text-muted-foreground">
                  Exemple salle de bain 8 m² : <TrendingDown className="inline h-3 w-3" /> peinture et
                  finitions réalisables soi-même, plomberie et électricité à confier à un professionnel.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Pour qui ? (SEO : audiences / secteurs) ────────────────────── */}
      <section className="border-y border-border bg-secondary/30" id="pour-qui">
        <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-20">
          <p className="overline">Pour qui ConstruPilot ?</p>
          <h2 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
            Un logiciel de devis travaux pour tout le BTP français
          </h2>
          <p className="mt-4 text-sm text-muted-foreground max-w-3xl">
            Que vous soyez artisan indépendant, particulier en rénovation, architecte, marchand de
            matériaux ou promoteur, ConstruPilot s'adapte à votre flux de travail. Un seul outil,
            de l'estimation au devis signé.
          </p>
          <div className="mt-10 grid md:grid-cols-2 lg:grid-cols-3 gap-4 stagger">
            {AUDIENCES.map((a) => (
              <div key={a.title} className="surface p-6" data-testid={`audience-card-${a.title.toLowerCase().replace(/[^a-z]+/g,"-")}`}>
                <a.icon className="h-6 w-6 text-primary" aria-hidden="true" />
                <h3 className="mt-4 font-display text-lg font-semibold">{a.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{a.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FAQ (SEO : rich snippet Google) ─────────────────────────────── */}
      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-20" id="faq">
        <p className="overline">Questions fréquentes</p>
        <h2 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight">
          Vos questions sur ConstruPilot & les devis travaux
        </h2>
        <div className="mt-10 grid gap-3 max-w-4xl">
          {FAQ.map((item, i) => {
            const open = openFaq === i;
            return (
              <div key={i} className="surface" data-testid={`faq-item-${i}`}>
                <button
                  onClick={() => setOpenFaq(open ? -1 : i)}
                  data-testid={`faq-toggle-${i}`}
                  aria-expanded={open}
                  className="w-full text-left flex items-center justify-between p-5 hover:text-primary transition-colors"
                >
                  <span className="font-display font-semibold text-base pr-8">{item.q}</span>
                  <ChevronDown className={`h-5 w-5 shrink-0 text-primary transition-transform ${open ? "rotate-180" : ""}`} />
                </button>
                {open && (
                  <div className="px-5 pb-5 text-sm text-muted-foreground leading-relaxed border-t border-border pt-4"
                       data-testid={`faq-answer-${i}`}>
                    {item.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      <Footer />
    </>
  );
}
