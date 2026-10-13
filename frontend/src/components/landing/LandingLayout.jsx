import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Menu, X, LogIn, Waves } from "lucide-react";
import { AudienceSwitch } from "@/components/AudienceSwitch";
import { Footer } from "@/components/Nav";
import { WorkspaceBackdrop, useWorkspaceMotion } from "@/components/workspace/WorkspaceBackdrop";
import "@/styles/workspace-ambient.css";
import "@/styles/landing-premium.css";

export function scrollToLanding(id, focus = false) {
  const target = document.getElementById(id);
  if (!target) return;
  target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  if (focus) target.querySelector("textarea")?.focus({ preventScroll: true });
}

export function LandingLayout({ audience, children }) {
  const pro = audience === "pro";
  const prefix = pro ? "pro" : "part";
  const motion = useWorkspaceMotion();
  const [menu, setMenu] = useState(false);
  const { pathname } = useLocation();
  useEffect(() => { setMenu(false); window.scrollTo(0, 0); }, [pathname]);
  const sections = [{ id: "landing-tools", label: "Les outils" }, { id: "landing-how", label: "Comment ça marche" }, { id: "landing-pricing", label: "Les offres" }];
  return <div className={`landing-premium landing-${audience}`}>
    <WorkspaceBackdrop paused={motion.paused || motion.reduced} />
    <a className="landing-skip" href="#landing-main">Aller au contenu</a>
    <header className="landing-header" onKeyDown={e => { if (e.key === "Escape") { setMenu(false); document.getElementById("landing-menu-button")?.focus(); } }}>
      <div className="landing-header-inner">
        <Link to={pro ? "/" : "/particuliers"} className="landing-brand" aria-label="ConstruPilot, accueil" data-testid={`${prefix}-logo`}><img src="/construpilot-icon.png" alt="" width="34" height="34" /><span>Constru<span>Pilot</span></span></Link>
        <div className="landing-audience"><AudienceSwitch active={audience} tone="light" /></div>
        <nav className="landing-desktop-links" aria-label="Présentation">{sections.map(s => <a key={s.id} href={`#${s.id}`}>{s.label}</a>)}</nav>
        <Link to="/login" className="landing-login" data-testid={`${prefix}-nav-login`} aria-label="Se connecter"><LogIn size={18} aria-hidden="true" /><span>Connexion</span></Link>
        {pro ? <Link to="/inscription" className="landing-button landing-header-cta" data-testid="pro-nav-cta">Essayer <ArrowRight size={15} /></Link> : <button type="button" className="landing-button landing-header-cta" data-testid="part-nav-cta" onClick={() => scrollToLanding("landing-estimator", true)}>Estimer <ArrowRight size={15} /></button>}
        <button type="button" id="landing-menu-button" className="landing-menu-button" aria-expanded={menu} aria-controls="landing-mobile-menu" aria-label={menu ? "Fermer le menu" : "Ouvrir le menu"} onClick={() => setMenu(!menu)} data-testid="landing-menu-toggle">{menu ? <X size={21} /> : <Menu size={21} />}</button>
      </div>
      {menu && <nav className="landing-mobile-menu" id="landing-mobile-menu" aria-label="Présentation sur mobile">{sections.map(s => <a key={s.id} href={`#${s.id}`} onClick={() => setMenu(false)}>{s.label}<ArrowRight size={16} /></a>)}<Link to="/inscription" onClick={() => setMenu(false)}>Créer mon compte<ArrowRight size={16} /></Link></nav>}
    </header>
    <main id="landing-main" tabIndex={-1}>{children}</main>
    <div className="landing-motion-row"><button type="button" disabled={motion.reduced} aria-pressed={!motion.paused && !motion.reduced} onClick={motion.toggle} data-testid="landing-motion-toggle"><Waves size={17} />Fond animé<span>{motion.reduced ? "Réduit sur l’appareil" : motion.paused ? "En pause" : "Activé"}</span></button></div>
    <Footer />
  </div>;
}

export function LandingHeading({ eyebrow, title, children }) {
  return <div className="landing-section-heading"><p className="landing-eyebrow">{eyebrow}</p><h2>{title}</h2>{children && <p>{children}</p>}</div>;
}

export function LandingPricing({ plans, pro = false }) {
  return <section className="landing-section landing-pricing" id="landing-pricing" data-testid={pro ? "pro-pricing" : "particuliers-pricing"}>
    <LandingHeading eyebrow="À votre rythme" title={pro ? "Une offre pour votre façon de travailler." : "Commencez simplement. Allez plus loin."}>{pro ? "Essai de 7 jours, puis abonnement sans engagement. Carte requise ; aucun débit avant la fin de l’essai." : "Découvrez les premiers outils gratuitement, puis choisissez l’accompagnement qui vous convient."}</LandingHeading>
    <div className="landing-price-grid">{plans.map(p => <article key={p.name} className={`landing-price-card${p.popular ? " is-featured" : ""}`}>
      <div className="landing-price-name"><h3>{p.name}</h3>{p.popular && <span>{pro ? "Pour les équipes" : "Pour votre projet"}</span>}</div><p>{p.desc}</p>
      <div className="landing-price"><strong>{p.price}</strong><span>{p.period}</span></div>
      <ul>{p.features.map(f => <li key={f}><span aria-hidden="true">✓</span>{f}</li>)}</ul>
      <Link to="/inscription" className={`landing-button${p.popular ? "" : " landing-button-outline"}`} data-testid={p.tid}>{pro ? "Essayer pendant 7 jours" : p.popular ? "Découvrir le Pass" : "Commencer gratuitement"}<ArrowRight size={17} /></Link>
    </article>)}</div>
    <Link to="/tarifs" className="landing-text-link">Consulter le détail des offres <ArrowRight size={16} /></Link>
  </section>;
}
