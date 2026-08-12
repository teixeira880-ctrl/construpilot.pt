import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  ArrowRight, Sparkles, Calculator, Search, Wrench, ShieldCheck, FileText,
  MessageSquare, Camera, TrendingDown, Hammer, ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Nav, Footer } from "@/components/Nav";
import { api, IMAGES, eur } from "@/lib/api";

const EXAMPLE =
  "Je veux rénover une maison de 150 m², refaire les murs, plafonds, électricité, plomberie, deux salles de bain et remplacer les fenêtres.";

const STEPS = [
  { icon: MessageSquare, title: "Je décris mon projet", text: "En une phrase, comme à un artisan." },
  { icon: Sparkles, title: "CMRENOV AI comprend", text: "Lots, surfaces, niveau de finition, risques." },
  { icon: Calculator, title: "Le moteur calcule", text: "Quantités et prix déterministes, vérifiables." },
  { icon: Search, title: "Je trouve les meilleurs prix", text: "Comparaison multi-fournisseurs et panier optimisé." },
  { icon: Wrench, title: "Je sais quoi faire moi-même", text: "Guides pas à pas et niveaux de difficulté." },
  { icon: Hammer, title: "J'appelle CMRENOV si besoin", text: "Proposition professionnelle en 48 h." },
];

const FEATURES = [
  { icon: Calculator, title: "Calculateurs pros", text: "Peinture, carrelage, placo, béton, isolation : quantités exactes avec marges.", to: "/calculateurs" },
  { icon: Search, title: "Comparateur de prix", text: "10 fournisseurs, livraison, stock, historique et alertes prix.", to: "/prix" },
  { icon: Wrench, title: "Mode « je le fais moi-même »", text: "Matériaux calculés + guide professionnel étape par étape.", to: "/diy" },
  { icon: Camera, title: "Estimation par photo", text: "L'IA identifie la pièce, son état et les travaux probables.", to: "/photo" },
  { icon: FileText, title: "Scanner de devis", text: "Prix bas, correct, élevé : l'IA analyse et compare vos devis.", to: "/devis" },
  { icon: MessageSquare, title: "Coach IA CMRENOV", text: "Toutes vos questions travaux, réponses de professionnel.", to: "/coach" },
];

export default function Landing() {
  const [description, setDescription] = useState("");
  const [types, setTypes] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/estimation/catalog").then(({ data }) => setTypes(data.project_types)).catch(() => {});
  }, []);

  const launch = () => {
    const text = description.trim() || EXAMPLE;
    sessionStorage.setItem("cmrenov_description", text);
    navigate("/smart-project");
  };

  return (
    <>
      <Nav />

      <section className="relative overflow-hidden border-b border-border grain">
        <img
          src={IMAGES.hero} alt="Architecture contemporaine"
          className="absolute inset-0 h-full w-full object-cover opacity-25 dark:opacity-20"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="relative mx-auto max-w-[1500px] px-5 lg:px-8 py-20 lg:py-28">
          <div className="max-w-3xl">
            <p className="overline animate-rise">CMRENOV Smart Project</p>
            <h1 className="mt-5 font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tighter animate-rise">
              Votre expert travaux,<br />
              <span className="text-primary">de l'idée au chantier.</span>
            </h1>
            <p className="mt-6 text-base md:text-lg text-muted-foreground max-w-2xl animate-rise">
              Des prix réels. Des conseils de pros. Un chantier mieux maîtrisé. Décrivez votre projet :
              CMRENOV AI le décompose, l'estime, calcule les matériaux et trouve les meilleurs prix.
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
          <p className="overline">Le parcours CMRENOV</p>
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
                CMRENOV AI compare le coût professionnel et le coût en autonomie, le temps nécessaire,
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

      <Footer />
    </>
  );
}
