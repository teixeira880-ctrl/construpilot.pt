import { Link } from "react-router-dom";
import {
  Calculator, Sparkles, Camera, FileText, Search, MessageSquare, ShieldCheck,
  Ruler, Home as HomeIcon, HardHat, Layers, Building2, Droplets, Waves,
  Truck, PenTool, FileSignature, CreditCard, CalendarRange, Users, Boxes,
  Cuboid, ArrowRight, CheckCircle2, Smartphone, Download, PlayCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import HelpChatbot from "@/components/HelpChatbot";

const PARTICULIER = [
  { icon: Calculator, title: "Estimateur de travaux", desc: "Chiffrage instantané matériaux + main d'œuvre, par type de projet." },
  { icon: Sparkles, title: "Smart Project", desc: "Décrivez « rénover salle de bain 8 m² » → lots, matériaux et budget générés par l'IA." },
  { icon: Camera, title: "Analyse de photo", desc: "Envoyez une photo d'une pièce ou d'un défaut, l'IA propose des pistes." },
  { icon: FileText, title: "Scanner de devis", desc: "Importez un devis PDF : l'IA l'explique et vérifie les montants." },
  { icon: Ruler, title: "Calculateurs", desc: "Surfaces, volumes, quantités (peinture, carrelage, béton…)." },
  { icon: Search, title: "Recherche de prix", desc: "Ordres de grandeur de prix matériaux et prestations." },
  { icon: MessageSquare, title: "Coach IA travaux", desc: "Un assistant qui répond à vos questions chantier, en français." },
  { icon: CalendarRange, title: "Planning des phases", desc: "Visualisez l'ordre des étapes de votre chantier." },
  { icon: ShieldCheck, title: "Sécurité d'abord", desc: "Gaz, électricité, murs porteurs : l'app oriente toujours vers un pro." },
];

const PRO = [
  { icon: Cuboid, title: "Analyse de plans DWG/DXF/PDF", desc: "Rendu fidèle (cotes, textes) et métré exact : murs, planchers, escaliers, poutres, poteaux." },
  { icon: Building2, title: "Métré béton & structure", desc: "Quantités béton et devis détaillé par corps d'état, marges et acompte." },
  { icon: HardHat, title: "Ferraillage / Acier", desc: "Extraction des barres HA et treillis → bordereau et quantités commandables." },
  { icon: Droplets, title: "Étanchéité", desc: "Toiture-terrasse : bordereau par couche → rouleaux, bidons, panneaux." },
  { icon: Layers, title: "Toiture", desc: "Tuiles/ardoises/bac acier, écran, liteaux, faîtage, noues, gouttières." },
  { icon: Waves, title: "VRD / Réseaux", desc: "EP, EU, AEP, télécom, gaz + métré des tranchées (déblai, sable, remblai, réfection)." },
  { icon: Boxes, title: "Bibliothèque de prix DPGF", desc: "Importez votre Excel/BPU pour surcharger les prix de l'IA." },
  { icon: Truck, title: "Approvisionnement & fournisseurs", desc: "Chiffrage, surlignage sur le plan, export CSV et bon de commande par e-mail." },
  { icon: FileSignature, title: "Devis signables en ligne", desc: "Vos clients acceptent et signent le devis à distance." },
  { icon: CreditCard, title: "Acompte Stripe", desc: "Encaissez 30 % d'acompte à la signature du devis." },
  { icon: Users, title: "Équipe & portail Pro", desc: "Collaborateurs, rôles, portail dédié et gestion de projets." },
  { icon: Smartphone, title: "Application mobile (PWA)", desc: "Installez ConstruPilot sur mobile pour le chantier." },
];

const Card = ({ icon: Icon, title, desc, tid }) => (
  <div className="surface p-5 rounded-lg hover:border-primary/50 transition-colors" data-testid={tid}>
    <div className="h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center mb-3">
      <Icon className="h-5 w-5 text-primary" />
    </div>
    <h3 className="font-bold text-base mb-1">{title}</h3>
    <p className="text-sm text-muted-foreground">{desc}</p>
  </div>
);

export default function Features() {
  return (
    <div className="min-h-screen bg-background">
      <SEO title="Fonctionnalités" description="Toutes les fonctionnalités ConstruPilot pour particuliers et professionnels du bâtiment : estimation IA, analyse de plans DWG, métré, devis, approvisionnement." canonical="/fonctionnalites" />
      <Nav />

      <section className="max-w-6xl mx-auto px-4 pt-16 pb-10 text-center">
        <span className="overline text-primary">Fonctionnalités</span>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
          Tout ConstruPilot, <span className="text-primary">en un coup d'œil</span>
        </h1>
        <p className="mt-5 text-base text-muted-foreground max-w-2xl mx-auto">
          Des outils simples pour les particuliers, une suite technique puissante pour les pros du bâtiment. Estimation, plans, métré, devis et approvisionnement — propulsés par l'IA.
        </p>
        <div className="mt-8 flex flex-wrap gap-3 justify-center">
          <Link to="/login"><Button className="rounded-sm gap-2 h-11" data-testid="features-cta-start">Commencer gratuitement <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link to="/tarifs"><Button variant="outline" className="rounded-sm h-11" data-testid="features-cta-pricing">Voir les tarifs</Button></Link>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-6">
          <HomeIcon className="h-6 w-6 text-primary" />
          <h2 className="font-display text-2xl font-bold">Pour les particuliers</h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="features-particulier">
          {PARTICULIER.map((f, i) => <Card key={i} {...f} tid={`feature-part-${i}`} />)}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-2">
          <HardHat className="h-6 w-6 text-primary" />
          <h2 className="font-display text-2xl font-bold">Pour les professionnels</h2>
          <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Offre Pro</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">Métré exact depuis vos plans, approvisionnement chantier et devis professionnels.</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="features-pro">
          {PRO.map((f, i) => <Card key={i} {...f} tid={`feature-pro-${i}`} />)}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 py-10" data-testid="features-downloads">
        <div className="surface p-6 rounded-xl">
          <h2 className="font-display text-xl font-bold flex items-center gap-2"><Download className="h-5 w-5 text-primary" /> Toutes les fonctionnalités en PDF et PowerPoint</h2>
          <p className="mt-2 text-sm text-muted-foreground">Brochure commerciale (1 offre par page) et catalogue exhaustif — Particuliers, Premium, Pro, Pro Business, Blog & SEO, Radar Chantiers, API. En français.</p>
          <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ["Brochure (PDF)", "/docs/ConstruPilot_Brochure_Fonctionnalites.pdf", "features-dl-brochure-pdf"],
              ["Brochure (PowerPoint)", "/docs/ConstruPilot_Brochure_Fonctionnalites.pptx", "features-dl-brochure-pptx"],
              ["Catalogue complet (PDF)", "/docs/ConstruPilot_Catalogue_Complet.pdf", "features-dl-catalogue-pdf"],
              ["Catalogue complet (PowerPoint)", "/docs/ConstruPilot_Catalogue_Complet.pptx", "features-dl-catalogue-pptx"],
            ].map(([label, href, tid]) => (
              <a key={tid} href={href} download data-testid={tid}
                 className="flex items-center gap-2 rounded-sm border border-border px-3 py-2.5 text-sm hover:bg-primary/5 transition-colors">
                <FileText className="h-4 w-4 text-primary shrink-0" />{label}
              </a>
            ))}
          </div>
          <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="features-videos">
            {[
              ["Vidéo démo courte 16:9 (2 min 30)", "/docs/ConstruPilot_Demo_Courte_16x9.mp4", "features-video-short-169"],
              ["Vidéo démo courte 9:16 (réels)", "/docs/ConstruPilot_Demo_Courte_9x16.mp4", "features-video-short-916"],
              ["Vidéo démo complète 16:9 (4 min 40)", "/docs/ConstruPilot_Demo_Complete_16x9.mp4", "features-video-full-169"],
              ["Vidéo démo complète 9:16", "/docs/ConstruPilot_Demo_Complete_9x16.mp4", "features-video-full-916"],
            ].map(([label, href, tid]) => (
              <a key={tid} href={href} target="_blank" rel="noreferrer" data-testid={tid}
                 className="flex items-center gap-2 rounded-sm border border-border px-3 py-2.5 text-sm hover:bg-primary/5 transition-colors">
                <PlayCircle className="h-4 w-4 text-primary shrink-0" />{label}
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 py-14 text-center">
        <div className="surface p-8 rounded-xl">
          <PenTool className="h-8 w-8 text-primary mx-auto" />
          <h2 className="mt-4 font-display text-2xl font-bold">Prêt à estimer votre premier chantier ?</h2>
          <p className="mt-3 text-sm text-muted-foreground max-w-xl mx-auto">Créez un compte en 30 secondes, ou testez avec un compte démo. Aucune carte bancaire requise pour commencer.</p>
          <div className="mt-6 flex flex-wrap gap-3 justify-center">
            <Link to="/login"><Button className="rounded-sm gap-2 h-11" data-testid="features-cta-bottom">Créer mon compte <ArrowRight className="h-4 w-4" /></Button></Link>
          </div>
          <div className="mt-6 flex flex-wrap gap-4 justify-center text-xs text-muted-foreground">
            {["Sans engagement", "Comptes démo disponibles", "Support en français"].map((t, i) => (
              <span key={i} className="flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-primary" />{t}</span>
            ))}
          </div>
        </div>
      </section>

      <Footer />
      <HelpChatbot />
    </div>
  );
}
