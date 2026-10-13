import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Play, Ruler, FileText, ReceiptText, Cuboid, FileSpreadsheet, Truck, Layers, Users, Check, ChevronDown } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DemoShowcase } from "@/components/DemoShowcase";
import { FeatureClips } from "@/components/FeatureClips";
import { LandingLayout, LandingHeading, LandingPricing, scrollToLanding } from "@/components/landing/LandingLayout";
import { ProductPreview } from "@/components/landing/ProductPreview";

const FEATURES = [
  { id: "metre", icon: Ruler, clip: "metre", tag: "Lire & mesurer", title: "Plans & métrés", desc: "Importez vos plans PDF, DWG ou DXF, calibrez l’échelle et contrôlez vos surfaces, longueurs et volumes.", to: "/plan" },
  { id: "devis", icon: FileText, clip: "devis_editeur", tag: "Chiffrer & présenter", title: "Des devis à votre image", desc: "Structurez vos postes, ajustez vos prix et gardez les remises, la TVA et les totaux à portée de main.", to: "/devis-editeur" },
  { id: "factures", icon: ReceiptText, clip: "factures", tag: "Facturer & suivre", title: "Factures & situations", desc: "Retrouvez vos documents, préparez vos situations à l’avancement et vos exports de facturation.", to: "/factures" },
  { id: "dpgf", icon: FileSpreadsheet, clip: "dpgf", tag: "Organiser les pièces", title: "DPGF & CCTP", desc: "Rassemblez les informations du dossier pour préparer un chiffrage que vous pouvez vérifier et compléter.", to: "/dpgf" },
  { id: "escaliers", icon: Cuboid, clip: "escaliers", tag: "Étudier une solution", title: "Escaliers 3D", desc: "Explorez la géométrie de votre escalier et consultez ses dimensions dans une vue interactive.", to: "/escaliers" },
  { id: "appro", icon: Truck, clip: null, tag: "Préparer le chantier", title: "Approvisionnement", desc: "Organisez les matériaux, les commandes et les coûts dans le dossier du chantier.", to: "/appro" },
  { id: "multiniveaux", icon: Layers, clip: "multiniveaux", tag: "Garder une vue globale", title: "Projets multi-niveaux", desc: "Retrouvez les plans de chaque niveau et rassemblez les quantités de votre projet.", to: "/plan" },
  { id: "equipe", icon: Users, clip: null, tag: "Travailler ensemble", title: "Votre équipe, réunie", desc: "Partagez les informations utiles et organisez les accès de vos collaborateurs.", to: "/equipe" },
];

const PLANS = [
  { name: "Pro Artisan", price: "149 €", period: "/mois HT", popular: false, tid: "plan-pro-artisan-cta",
    desc: "Artisans indépendants et petites équipes.",
    features: ["Métré sur plan illimité", "Devis & factures Factur-X", "Calcul d'escaliers 3D DTU", "Export PDF à votre logo", "Support BTP prioritaire"] },
  { name: "Pro Business / TCE", price: "249 €", period: "/mois HT", popular: true, tid: "plan-pro-business-cta",
    desc: "PME BTP, entreprises générales, conducteurs de travaux.",
    features: ["Tout Pro Artisan +", "Analyse CCTP & import DPGF", "Projets multi-niveaux & équipe", "Portail sous-traitants & appro", "Accompagnement à la prise en main"] },
];

const FAQ = [
  { q: "Comment vérifier les quantités issues d’un plan ?", a: "Calibrez l’échelle, contrôlez les éléments repérés et complétez les informations manquantes. La lecture du plan peut nécessiter des corrections : les quantités doivent être vérifiées avant d’être utilisées dans un devis." },
  { q: "Puis-je utiliser mes propres prix ?", a: "Vous pouvez préparer vos devis avec vos prix et votre catalogue, puis ajuster les postes, remises et taux de TVA dans l’éditeur." },
  { q: "Est-ce utilisable sur téléphone ?", a: "La plateforme s’ouvre dans votre navigateur. Vous pouvez consulter vos dossiers et utiliser les fonctions adaptées au mobile ; un grand écran reste plus confortable pour travailler sur des plans détaillés." },
];

export default function LandingPro() {
  const navigate = useNavigate();
  const [preview, setPreview] = useState(null);
  const [videosOpen, setVideosOpen] = useState(false);
  useEffect(() => { try { if (localStorage.getItem("construpilot_audience") === "particulier") navigate("/particuliers", { replace: true }); } catch {} }, [navigate]);
  const showDemo = () => { setVideosOpen(true); scrollToLanding("landing-demo"); };
  return <LandingLayout audience="pro">
    <SEO title="ConstruPilot Pro — Métrés, devis et suivi de chantier" description="Réunissez vos plans, métrés, devis et factures dans un espace de travail BTP pensé pour les artisans et les entreprises. Découvrez ConstruPilot Pro."
      canonical="/" keywords="logiciel devis BTP, métré sur plan, chiffrage bâtiment, gestion chantier"
      jsonLd={{"@context":"https://schema.org","@type":"SoftwareApplication",name:"ConstruPilot Pro",applicationCategory:"BusinessApplication",operatingSystem:"Web",offers:[{"@type":"Offer",name:"Pro Artisan",price:"149",priceCurrency:"EUR"},{"@type":"Offer",name:"Pro Business",price:"249",priceCurrency:"EUR"}]}} />
    <section className="landing-hero landing-section" data-testid="pro-hero">
      <div className="landing-hero-copy"><p className="landing-eyebrow"><span />POUR LES PROFESSIONNELS DU BÂTIMENT</p>
        <h1>Votre savoir-faire.<br /><em>Le reste, simplifié.</em></h1>
        <p className="landing-hero-description">Du premier plan au suivi du chantier, retrouvez vos métrés, devis et documents dans un espace de travail pensé pour le terrain.</p>
        <div className="landing-hero-actions"><Link to="/inscription" className="landing-button" data-testid="pro-hero-primary-cta">Essayer ConstruPilot <ArrowRight size={18} /></Link><button type="button" className="landing-button landing-button-outline" onClick={showDemo} data-testid="pro-hero-secondary-cta"><Play size={16} />Voir la démonstration</button></div>
        <p className="landing-hero-note">Essai 7 jours · Carte requise · Sans engagement après l’essai</p>
        <div className="landing-hero-proof"><span><Check size={15} />Plans & métrés</span><span><Check size={15} />Devis & factures</span><span><Check size={15} />Dossiers chantier</span></div>
      </div>
      <ProductPreview />
    </section>
    <div className="landing-ribbon"><span>Moins de dispersion.</span><strong>Plus de place pour votre métier.</strong><span>Au bureau comme sur le chantier.</span></div>
    <section className="landing-section" id="landing-how"><LandingHeading eyebrow="Une continuité, du début à la fin" title="Votre chantier avance. Vos informations aussi." />
      <div className="landing-steps">{[{title:"Rassemblez",desc:"Les plans, les pièces du dossier et les demandes du client.",icon:Ruler},{title:"Préparez",desc:"Des quantités contrôlées et un devis construit poste par poste.",icon:FileText},{title:"Pilotez",desc:"Les documents, les prochaines actions et les échanges de l’équipe.",icon:Users}].map((s,i)=><article key={s.title}><div><span>0{i+1}</span><s.icon size={23} /></div><h3>{s.title}</h3><p>{s.desc}</p></article>)}</div>
    </section>
    <section className="landing-section" id="landing-tools" data-testid="pro-features"><LandingHeading eyebrow="Votre boîte à outils" title="Tout se retrouve. Tout se suit.">Les fonctions essentielles restent proches ; les outils spécialisés sont là quand vous en avez besoin.</LandingHeading>
      <div className="landing-feature-grid">{FEATURES.map(f=><button type="button" key={f.id} className="landing-feature-card" onClick={()=>setPreview(f)} data-testid={`pro-feature-${f.id}`}><span className="landing-feature-icon"><f.icon size={23} /></span><small>{f.tag}</small><h3>{f.title}</h3><p>{f.desc}</p><span className="landing-card-link">Découvrir <ArrowRight size={17} /></span></button>)}</div>
      <Link to="/comparatif" className="landing-text-link" data-testid="pro-hero-comparatif-cta">Comparer les solutions BTP <ArrowRight size={16} /></Link>
    </section>
    <section className="landing-section landing-video-section" id="landing-demo"><details open={videosOpen} onToggle={e=>setVideosOpen(e.currentTarget.open)} data-testid="landing-videos"><summary><span><small>VOIR CONCRÈTEMENT</small><strong>Découvrez les outils en action.</strong></span><span className="landing-video-play"><Play size={21} /></span></summary>{videosOpen&&<div><DemoShowcase /><FeatureClips title="Les fonctions Pro, en vidéo" subtitle="Parcourez les démonstrations des outils qui vous intéressent." keys={["metre","devis_editeur","escaliers","factures","dpgf","multiniveaux"]} /></div>}</details></section>
    <LandingPricing plans={PLANS} pro />
    <section className="landing-section landing-faq"><LandingHeading eyebrow="Vos questions" title="Quelques repères avant de commencer." />{FAQ.map(f=><details key={f.q}><summary>{f.q}<ChevronDown size={18} /></summary><p>{f.a}</p></details>)}</section>
    <section className="landing-section"><div className="landing-final"><p className="landing-eyebrow">CONSTRUPILOT PRO</p><h2>Un chantier bien préparé<br />commence ici.</h2><Link to="/inscription" className="landing-button landing-button-ivory" data-testid="pro-bottom-cta">Découvrir mon espace Pro <ArrowRight size={18} /></Link><Link to="/particuliers" className="landing-audience-link" onClick={()=>{try{localStorage.setItem("construpilot_audience","particulier");}catch{}}}>Vous rénovez votre logement ? Découvrez l’espace Particuliers.</Link></div></section>
    <Dialog open={!!preview} onOpenChange={open=>!open&&setPreview(null)}><DialogContent className="landing-feature-dialog" data-testid="pro-feature-preview">{preview&&<><DialogHeader><DialogTitle>{preview.title}</DialogTitle><DialogDescription>{preview.desc}</DialogDescription></DialogHeader>{preview.clip?<video src={`/demo/clips/${preview.clip}.mp4`} poster={`/demo/clips/${preview.clip}.jpg`} controls muted playsInline preload="metadata" data-testid="pro-feature-preview-video" />:<p>Retrouvez les détails des fonctions et des niveaux d’accès dans nos offres.</p>}<div className="landing-dialog-actions"><Link to="/inscription" className="landing-button" data-testid="pro-feature-preview-cta">Essayer ConstruPilot <ArrowRight size={17} /></Link><Link to={preview.to} className="landing-button landing-button-outline" data-testid="pro-feature-preview-open">Ouvrir l’outil</Link></div></>}</DialogContent></Dialog>
  </LandingLayout>;
}
