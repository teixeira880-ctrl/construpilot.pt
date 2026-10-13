import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, Sparkles, Camera, FileSearch, Wrench, Calculator, MessageSquare, Check, Play, ChevronDown } from "lucide-react";
import { SEO } from "@/components/SEO";
import { FeatureClips } from "@/components/FeatureClips";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { LandingLayout, LandingHeading, LandingPricing, scrollToLanding } from "@/components/landing/LandingLayout";

const EXAMPLE = "Rénover une salle de bain de 8 m² avec une douche à l’italienne, de la faïence et un meuble vasque.";
const CHIPS = ["Rénovation salle de bain 8 m²", "Isolation combles 60 m²", "Peinture T3 70 m²", "Cuisine équipée"];
const TOOLS = [
  { icon: Sparkles, tag: "Préparer", title: "Un projet, étape par étape", desc: "Organisez les travaux, les matériaux et les étapes de votre rénovation.", to: "/smart-project" },
  { icon: FileSearch, tag: "Comprendre", title: "Un regard sur vos devis", desc: "Comparez les postes et repérez les points à clarifier avec votre artisan.", to: "/scanner-devis" },
  { icon: Camera, tag: "Explorer", title: "Votre pièce en images", desc: "Utilisez une photo pour apporter du contexte et préparer vos questions.", to: "/photo" },
  { icon: Wrench, tag: "Choisir", title: "Faire soi-même ou déléguer", desc: "Comparez les options selon votre budget, vos compétences et le chantier.", to: "/diy" },
  { icon: Calculator, tag: "Calculer", title: "Les bonnes quantités", desc: "Estimez les besoins en peinture, carrelage ou isolant à partir de vos mesures.", to: "/calculateurs" },
  { icon: MessageSquare, tag: "Être accompagné", title: "Vos questions travaux", desc: "Préparez vos échanges et trouvez des explications au fil du projet.", to: "/coach" },
];
const PLANS = [
  { name: "Gratuit", price: "0 €", period: "à vie", popular: false, tid: "plan-particulier-free-cta",
    desc: "Pour explorer et faire une première estimation.",
    features: ["3 estimations express / mois", "Calculateurs de surfaces & volumes", "Guide des prix moyens par région"] },
  { name: "Pass Sérénité", price: "19 €", period: "/mois sans engagement", popular: true, tid: "plan-particulier-pass-cta",
    desc: "Accompagnement complet pendant tous vos travaux.",
    features: ["Estimations & Smart Projects illimités", "Scanner de devis illimité", "Analyse photo & détection des risques", "Coach IA travaux 24/7", "Mise en relation prioritaire artisans"] },
];

export default function LandingParticuliers() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const [name,setName]=useState("");const [email,setEmail]=useState("");const [description,setDescription]=useState("");
  const [error,setError]=useState("");const [videosOpen,setVideosOpen]=useState(false);
  useEffect(()=>{try{const sp=new URLSearchParams(window.location.search);["utm_source","utm_medium","utm_campaign"].forEach(k=>{const v=sp.get(k);if(v)sessionStorage.setItem(`construpilot_${k}`,v);});}catch{}},[]);
  const launch = e => {
    e.preventDefault();if(loading)return;setError("");
    const text=description.trim()||EXAMPLE,mail=email.trim();let leadPayload;
    try {
      sessionStorage.setItem("estimator_prefill",JSON.stringify({description:text,_raw:text}));
      if(mail)sessionStorage.setItem("construpilot_lead_email",mail);
      if(name.trim())sessionStorage.setItem("construpilot_lead_name",name.trim());
      leadPayload={name:name.trim(),email:mail,description:text,source:sessionStorage.getItem("construpilot_utm_source")||"landing-particuliers",utm_source:sessionStorage.getItem("construpilot_utm_source")||"",utm_medium:sessionStorage.getItem("construpilot_utm_medium")||"",utm_campaign:sessionStorage.getItem("construpilot_utm_campaign")||""};
      if(!user)sessionStorage.setItem("construpilot_pending_lead",JSON.stringify(leadPayload));
    } catch { setError("Votre navigateur n’a pas pu conserver le projet. Autorisez le stockage pour ce site, puis réessayez.");return; }
    if(user){if(mail)api.post("/leads",leadPayload).catch(()=>{});navigate("/estimation");}
    else navigate(`/inscription?email=${encodeURIComponent(mail)}&signup=1`);
  };
  return <LandingLayout audience="particulier">
    <SEO title="ConstruPilot — Préparez votre projet de rénovation" description="Estimez votre budget travaux, comprenez vos devis et préparez les étapes de votre rénovation avec ConstruPilot pour les particuliers." canonical="/particuliers" keywords="estimation travaux, budget rénovation, comparer devis artisan"
      jsonLd={{"@context":"https://schema.org","@type":"WebApplication",name:"ConstruPilot pour les particuliers",applicationCategory:"UtilitiesApplication",operatingSystem:"Web",offers:[{"@type":"Offer",name:"Gratuit",price:"0",priceCurrency:"EUR"},{"@type":"Offer",name:"Pass Sérénité",price:"19",priceCurrency:"EUR"}]}} />
    <section className="landing-hero landing-section" data-testid="particuliers-hero">
      <div className="landing-hero-copy"><p className="landing-eyebrow"><span />POUR VOTRE MAISON, VOTRE APPARTEMENT</p><h1>Vos envies prennent forme.<br /><em>Votre projet aussi.</em></h1>
        <p className="landing-hero-description">Un budget à préparer, un devis à comprendre, des travaux à organiser. Avancez avec des repères clairs, du premier souhait aux prochaines étapes.</p>
        <div className="landing-hero-actions"><button type="button" className="landing-button" onClick={()=>scrollToLanding("landing-estimator",true)}>Préparer mon projet <ArrowRight size={18} /></button><Link to="/scanner-devis" className="landing-text-link" data-testid="particuliers-hero-secondary-cta">J’ai déjà un devis <ArrowRight size={17} /></Link></div>
        <div className="landing-hero-proof"><span><Check size={15} />Gratuit pour démarrer</span><span><Check size={15} />Sans carte bancaire</span></div>
        <p className="landing-hero-note">Une estimation donne un ordre de grandeur. Votre artisan confirme les travaux et le prix final.</p>
      </div>
      <form className="landing-estimator" id="landing-estimator" data-testid="particuliers-form" onSubmit={launch}>
        <div className="landing-form-heading"><span className="landing-feature-icon"><Sparkles size={23} /></span><span><small>VOTRE POINT DE DÉPART</small><h2>Et si on parlait de vos travaux ?</h2></span></div>
        <label htmlFor="landing-description">Décrivez votre projet</label><textarea id="landing-description" rows={4} value={description} onChange={e=>setDescription(e.target.value)} placeholder={EXAMPLE} data-testid="particuliers-description" />
        <div className="landing-project-chips" aria-label="Exemples de projets">{CHIPS.map((c,i)=><button type="button" key={c} onClick={()=>setDescription(c)} aria-pressed={description===c} data-testid={`part-chip-${c.slice(0,6)}`}>{["Salle de bain","Isolation","Peinture","Cuisine"][i]}</button>)}</div>
        <div className="landing-contact-fields"><div><label htmlFor="landing-name">Prénom <span>(facultatif)</span></label><input id="landing-name" autoComplete="given-name" value={name} onChange={e=>setName(e.target.value)} placeholder="Votre prénom" data-testid="particuliers-name" /></div><div><label htmlFor="landing-email">E-mail <span>(facultatif)</span></label><input id="landing-email" autoComplete="email" type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="vous@exemple.fr" data-testid="particuliers-email" /></div></div>
        {error&&<p role="alert" className="landing-form-error">{error}</p>}
        <button type="submit" className="landing-button" disabled={loading} data-testid="particuliers-hero-primary-cta">{loading?"Chargement…":"Estimer mon projet"}<ArrowRight size={18} /></button><p className="landing-form-note">{user?"Votre projet vous attend dans l’estimateur.":"Créez ensuite votre compte pour retrouver votre projet."}</p>
      </form>
    </section>
    <div className="landing-ribbon"><span>Votre idée.</span><strong>Des repères pour avancer.</strong><span>Un projet qui vous ressemble.</span></div>
    <section className="landing-section" id="landing-how" data-testid="particuliers-steps"><LandingHeading eyebrow="Simple, dès le début" title="Une question à la fois. Un projet plus clair." />
      <div className="landing-steps">{[{title:"Racontez votre projet",desc:"La pièce, la surface et ce que vous souhaitez changer.",icon:MessageSquare},{title:"Explorez votre budget",desc:"Une estimation pour comparer les postes et vos priorités.",icon:Calculator},{title:"Préparez la suite",desc:"Vos questions à l’artisan, vos devis et les prochaines étapes.",icon:FileSearch}].map((s,i)=><article key={s.title}><div><span>0{i+1}</span><s.icon size={23} /></div><h3>{s.title}</h3><p>{s.desc}</p></article>)}</div>
    </section>
    <section className="landing-section" id="landing-tools" data-testid="particuliers-tools"><LandingHeading eyebrow="À chaque étape, le bon outil" title="Moins de questions en suspens.">Comprendre, comparer, calculer : retrouvez les outils utiles au même endroit.</LandingHeading><div className="landing-feature-grid landing-feature-grid-home">{TOOLS.map(t=><Link key={t.to} to={t.to} className="landing-feature-card" data-testid={`particulier-tool-${t.to.slice(1)}`}><span className="landing-feature-icon"><t.icon size={23} /></span><small>{t.tag}</small><h3>{t.title}</h3><p>{t.desc}</p><span className="landing-card-link">Découvrir <ArrowRight size={17} /></span></Link>)}</div></section>
    <section className="landing-section landing-video-section" id="landing-demo"><details open={videosOpen} onToggle={e=>setVideosOpen(e.currentTarget.open)} data-testid="landing-videos"><summary><span><small>EN QUELQUES IMAGES</small><strong>Découvrez ce que vous pouvez faire.</strong></span><span className="landing-video-play"><Play size={21} /></span></summary>{videosOpen&&<FeatureClips title="Vos outils, en vidéo" subtitle="Découvrez l’estimation et les calculateurs en situation." keys={["estimation","calculateurs"]} />}</details></section>
    <LandingPricing plans={PLANS} />
    <section className="landing-section landing-faq"><LandingHeading eyebrow="Bon à savoir" title="Des repères, dès le départ." />{[{q:"L’estimation remplace-t-elle un devis d’artisan ?",a:"Non. Elle permet de préparer un budget à partir des informations données. L’état réel du logement, les matériaux choisis et la visite d’un professionnel peuvent faire évoluer le montant."},{q:"Puis-je commencer sans connaître toutes les dimensions ?",a:"Décrivez ce que vous connaissez et précisez les informations manquantes. Vous pourrez compléter le projet au fur et à mesure."},{q:"Puis-je utiliser ConstruPilot sur mon téléphone ?",a:"Oui, depuis votre navigateur : préparez votre projet, consultez les outils et retrouvez vos informations."}].map(f=><details key={f.q}><summary>{f.q}<ChevronDown size={18} /></summary><p>{f.a}</p></details>)}</section>
    <section className="landing-section"><div className="landing-final"><p className="landing-eyebrow">UN PROJET QUI VOUS RESSEMBLE</p><h2>La prochaine étape ?<br />Parlons de la vôtre.</h2><button type="button" className="landing-button landing-button-ivory" onClick={()=>scrollToLanding("landing-estimator",true)} data-testid="particuliers-cta-final">Préparer mes travaux <ArrowRight size={18} /></button><Link to="/" className="landing-audience-link" onClick={()=>{try{localStorage.setItem("construpilot_audience","pro");}catch{}}}>Vous êtes professionnel du bâtiment ? Découvrez l’espace Pro.</Link></div></section>
  </LandingLayout>;
}
