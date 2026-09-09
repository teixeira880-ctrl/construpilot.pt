import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, FileText, Mic, Ruler, Receipt, CheckCircle2, Quote, ShieldCheck, Sparkles,
  Clock, TrendingUp, Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";

const ROOMS = [
  ["Salon", 24], ["Cuisine", 11], ["Ch. 1", 14], ["Ch. 2", 12], ["Ch. 3", 11], ["SDB", 5], ["Entrée", 8], ["WC", 2],
];
const LOTS = [
  ["Démolition et dépose", 3640, 34], ["Plâtrerie et isolation", 9860, 31], ["Électricité", 7420, 28],
  ["Plomberie", 6980, 27], ["Carrelage et faïence", 5760, 33], ["Menuiserie intérieure", 8340, 30],
  ["Peinture", 9120, 36], ["Sols", 7480, 29], ["Finitions et nettoyage", 3880, 22],
];
const TOTAL = LOTS.reduce((a, l) => a + l[1], 0);
const MARGE = Math.round(LOTS.reduce((a, l) => a + l[1] * l[2] / 100, 0));
const eur = (n) => n.toLocaleString("fr-FR") + " €";

const FAQ = [
  ["ConstruPilot est-il adapté aux entreprises générales de rénovation ?",
    "Oui. Un chantier complet est structuré en lots (démolition, plâtrerie, électricité, plomberie, carrelage, menuiserie, peinture, sols, finitions…) avec ses ouvrages, quantités et sous-totaux. Un devis de 70 lignes sur 9 lots est un cas normal."],
  ["Puis-je utiliser mes propres ouvrages et mes propres prix ?",
    "Oui. Vous démarrez avec notre catalogue (ouvrages avec prix ajustés par niveau), puis ConstruPilot chiffre avec les vôtres : chaque ligne validée est enregistrée dans votre bibliothèque privée et c'est ce prix qui est repris au devis suivant."],
  ["ConstruPilot peut-il reprendre mes anciens devis ?",
    "Oui. Déposez vos anciens devis en PDF (Tolteck, Obat, Batappli, Excel, Word…) : l'IA en extrait les ouvrages, unités et prix pour reconstruire votre bibliothèque. Vous ne repartez pas de zéro."],
  ["Lit-il mes plans, mes photos et le dossier de l'architecte ?",
    "Oui. Un plan PDF, scanné ou photographié, des photos de visite, une note vocale et la DPGF : ConstruPilot en tire les pièces, les surfaces (murs développés, ouvertures déduites, plinthes) et les ouvrages. Vous vérifiez chaque quantité avant qu'elle entre dans le devis."],
  ["Calcule-t-il ma marge ?",
    "Oui, avant la signature. Chaque ligne porte son coût de revient (main-d'œuvre + fournitures). ConstruPilot affiche la marge prévisionnelle lot par lot pendant que vous chiffrez et signale les ouvrages chiffrés à perte."],
  ["Remplace-t-il mon logiciel de facturation ?",
    "Oui. Le devis signé devient facture d'acompte, factures de situation et facture de solde sans ressaisie, avec avoir si besoin. Factur-X conforme à la facturation électronique, export PDF/CSV pour votre expert-comptable."],
  ["Décide-t-il du prix à ma place ?",
    "Non. Vous gardez la maîtrise des quantités, des ouvrages, des prix et du devis final. Rien n'est envoyé au client sans votre validation."],
];

const fade = (d = 0) => ({ initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.55, delay: d } });

function Step({ n, icon: Icon, title, text, children, delay }) {
  return (
    <motion.div {...fade(delay)} className="grid lg:grid-cols-[1fr_1.15fr] gap-8 items-center" data-testid={`metre-step-${n}`}>
      <div>
        <span className="num text-primary text-sm font-bold">0{n}</span>
        <h3 className="font-display text-2xl md:text-3xl font-bold mt-1 flex items-center gap-3"><Icon className="h-6 w-6 text-primary" /> {title}</h3>
        <p className="text-muted-foreground mt-3 text-base leading-relaxed">{text}</p>
      </div>
      <div className="surface rounded-xl p-5 shadow-2xl border border-border/60">{children}</div>
    </motion.div>
  );
}

function Counter({ to, suffix = "" }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf; const t0 = performance.now();
    const tick = (t) => { const p = Math.min(1, (t - t0) / 1100); setV(Math.round(to * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <span className="num">{v.toLocaleString("fr-FR")}{suffix}</span>;
}

export default function LandingMetre() {
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="landing-metre">
      <SEO title="Métré IA — du plan au devis chiffré à vos prix | ConstruPilot"
           description="Déposez plan, photos, note vocale ou DPGF : ConstruPilot mètre chaque pièce, chiffre par lots à vos prix et affiche votre marge avant signature. Essai gratuit, sans engagement."
           canonical="/metre" />
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top_left,hsl(var(--primary)/0.18),transparent_55%)]" />
        <div className="mx-auto max-w-6xl px-5 lg:px-8 pt-16 pb-14 grid lg:grid-cols-[1.1fr_1fr] gap-10 items-center">
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6 }}>
            <p className="overline text-primary">Métré IA · Entreprises de rénovation</p>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] mt-3">
              Laissez l'IA gérer votre <span className="text-primary">métré</span>, gardez vos prix.
            </h1>
            <p className="text-base md:text-lg text-muted-foreground mt-5 max-w-xl">
              Un plan, quelques photos, une note vocale ou la DPGF de l'architecte : ConstruPilot relève chaque pièce,
              chiffre par lots à vos prix et vous montre la marge <b>avant</b> d'envoyer le devis.
            </p>
            <div className="flex flex-wrap gap-3 mt-7">
              <Button asChild size="lg" className="rounded-full gap-2 h-12 px-6" data-testid="metre-cta-start">
                <Link to="/inscription?signup=1&plan=pro">Démarrer l'essai gratuit <ArrowRight className="h-4 w-4" /></Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-full h-12 px-6" data-testid="metre-cta-demo">
                <Link to="/plan">Voir en action</Link>
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-3 flex items-center gap-2"><ShieldCheck className="h-3.5 w-3.5" /> Essai gratuit · Sans engagement · Hébergé en France</p>
          </motion.div>

          <motion.figure initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, delay: 0.15 }}
                         className="relative" data-testid="metre-hero-video">
            <div className="absolute -inset-4 bg-primary/15 blur-3xl rounded-[2.5rem]" aria-hidden="true" />
            <div className="relative rounded-2xl border border-border bg-black shadow-2xl overflow-hidden aspect-video">
              <video className="h-full w-full object-cover" src="/docs/ConstruPilot_Demo_Courte_16x9.mp4"
                     autoPlay muted loop controls playsInline preload="metadata" data-testid="metre-video-player" />
            </div>
            <figcaption className="mt-3 text-xs text-muted-foreground text-center">Démonstration en 2 min 30 : estimation, plan → métré, devis, signature, approvisionnement, Radar, rentabilité.</figcaption>
          </motion.figure>
        </div>
      </section>

      <section className="bg-secondary/30 border-y border-border/60">
        <div className="mx-auto max-w-6xl px-5 lg:px-8 py-12">
          <figure className="surface rounded-2xl p-6 border border-border/60 shadow-2xl relative max-w-2xl mx-auto" data-testid="metre-testimonial">
            <Quote className="h-8 w-8 text-primary/40 absolute -top-3 -left-3 rotate-180" />
            <h2 className="font-display text-base md:text-lg font-bold">Comment Fabrice a retrouvé <span className="text-primary">jusqu'à 5 heures par semaine</span>.</h2>
            <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
              « Un dossier de consultation, le métré nous prenait deux jours. Aujourd'hui on dépose le dossier, les quantités
              sortent seules, nos prix se posent dessus, et il me reste la vérification. On répond à tout. »
            </p>
            <div className="flex items-center gap-3 mt-5">
              <span className="h-10 w-10 rounded-full bg-primary/15 grid place-items-center font-display font-bold text-primary">FB</span>
              <div><p className="text-sm font-bold">Fabrice B.</p><p className="text-xs text-muted-foreground">Entreprise générale · Rénovation intérieure · 11 salariés</p></div>
            </div>
            <p className="text-[10px] text-muted-foreground mt-3">Témoignage illustratif</p>
          </figure>
        </div>
      </section>

      {/* 3 ÉTAPES */}
      <section className="mx-auto max-w-6xl px-5 lg:px-8 py-16 space-y-20" data-testid="metre-steps">
        <motion.div {...fade()} className="max-w-2xl">
          <p className="overline text-primary">Comment ça marche</p>
          <h2 className="font-display text-3xl md:text-4xl font-bold mt-2">Automatiser le chiffrage de tout un chantier avec l'IA</h2>
        </motion.div>

        <Step n={1} icon={Upload} title="Vous déposez le chantier" delay={0}
              text="Le plan, les photos de la visite, le descriptif, une note vocale dictée depuis le chantier, la DPGF. Aucun formulaire à remplir.">
          <div className="text-xs space-y-2">
            <div className="flex items-center justify-between"><span className="font-bold">Chantier · Appartement T4 · Lyon 6ᵉ</span><span className="text-primary flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> Reçu</span></div>
            {[["Plan-T4-architecte.pdf · 1/50", FileText], ["Note vocale · 1:12 · « T4 à refaire entièrement… »", Mic], ["DPGF architecte · 9 lots · 61 postes", Receipt]].map(([l, I], i) => (
              <motion.div key={l} initial={{ opacity: 0, x: -10 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 + i * 0.15 }}
                          className="flex items-center gap-2 rounded-md bg-secondary/40 px-3 py-2"><I className="h-4 w-4 text-primary" /> {l}</motion.div>
            ))}
            <div className="flex gap-1.5 pt-1">{["Salon", "Cuisine", "SDB"].map((p) => <span key={p} className="h-12 flex-1 rounded-md bg-primary/10 grid place-items-center text-[10px] text-muted-foreground">{p}</span>)}</div>
          </div>
        </Step>

        <Step n={2} icon={Ruler} title="ConstruPilot mètre le chantier" delay={0.05}
              text="Chaque pièce relevée sur le plan, murs développés, ouvertures déduites, plinthes comptées. Sortie : 8 pièces, 87 m² au sol.">
          <div className="text-xs">
            <div className="flex items-center justify-between mb-2"><span className="font-bold">Métré · 8 pièces relevées</span><span className="text-primary">Calculé</span></div>
            <div className="grid grid-cols-4 gap-1.5">
              {ROOMS.map(([n, s], i) => (
                <motion.div key={n} initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.06 }}
                            className="rounded-md border border-primary/30 bg-primary/5 p-2 text-center"><p className="text-[10px] uppercase text-muted-foreground">{n}</p><p className="num font-bold">{s} m²</p></motion.div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-2 mt-3">
              {[["Sol", 87, " m²"], ["Murs développés", 237, " m²"], ["Plafonds", 87, " m²"], ["Plinthes", 63, " ml"]].map(([l, v, u]) => (
                <div key={l} className="rounded-md bg-secondary/40 p-2"><p className="text-[10px] text-muted-foreground">{l}</p><p className="font-bold text-sm"><Counter to={v} suffix={u} /></p></div>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground mt-2">HSP 2,50 m · ouvertures déduites · reporté sur chaque ouvrage</p>
          </div>
        </Step>

        <Step n={3} icon={Receipt} title="Vous relisez, vous envoyez" delay={0.05}
              text="Le devis vous attend en brouillon, chiffré à vos prix, avec la marge lot par lot et les ouvrages à perte signalés. Le client signe en ligne.">
          <div className="text-xs">
            <div className="flex items-center justify-between mb-2"><span className="font-bold">Devis D-2026-0112 · brouillon</span><span className="text-primary">Vos prix</span></div>
            <ul className="divide-y divide-border/50">
              {LOTS.map(([l, v, m], i) => (
                <motion.li key={l} initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.05 }} className="flex items-center justify-between py-1.5">
                  <span><span className="num text-muted-foreground mr-2">{i + 1}</span>{l}</span>
                  <span className="flex items-center gap-2"><span className={`num text-[10px] px-1.5 rounded-sm ${m < 25 ? "bg-amber-500/10 text-amber-600" : "bg-emerald-500/10 text-emerald-600"}`}>{m} %</span><b className="num">{eur(v)}</b></span>
                </motion.li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-border mt-2 pt-2"><span className="text-muted-foreground">Total HT · 9 lots · 74 lignes</span><b className="num text-base text-primary">{eur(TOTAL)}</b></div>
            <div className="flex items-center justify-between text-emerald-600"><span className="flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> Marge prévisionnelle</span><b className="num">{Math.round(MARGE / TOTAL * 100)} % · {eur(MARGE)}</b></div>
          </div>
        </Step>

        <motion.div {...fade()} className="text-center">
          <p className="font-display text-2xl md:text-3xl font-bold">Laissez <span className="text-primary">l'IA gérer votre métré</span>, et concentrez-vous sur vos clients.</p>
          <Button asChild size="lg" className="rounded-full gap-2 h-12 px-7 mt-5" data-testid="metre-cta-mid"><Link to="/inscription?signup=1&plan=pro">Voir en action <ArrowRight className="h-4 w-4" /></Link></Button>
          <p className="text-xs text-muted-foreground mt-2">Essai gratuit · Sans engagement</p>
        </motion.div>
      </section>

      {/* PREUVE + PRICING */}
      <section className="bg-secondary/30 border-y border-border/60">
        <div className="mx-auto max-w-6xl px-5 lg:px-8 py-16 grid lg:grid-cols-2 gap-10 items-start">
          <motion.div {...fade()}>
            <p className="overline text-primary">Ce qu'en disent les entreprises</p>
            <blockquote className="font-display text-xl md:text-2xl font-bold mt-3 leading-snug" data-testid="metre-quote">
              « Le métré nous prenait deux jours. Alors on choisissait les dossiers. Aujourd'hui on répond à tout, et ça fait <span className="text-primary">cinq heures de bureau en moins par semaine</span>. »
            </blockquote>
            <p className="text-sm text-muted-foreground mt-3">Pascal M. · Entreprise générale du bâtiment · Villeurbanne · témoignage illustratif</p>
            <div className="grid grid-cols-3 gap-3 mt-8">
              {[[Clock, "5 h", "gagnées / semaine"], [Sparkles, "30 s", "pour un devis brouillon"], [TrendingUp, "lot par lot", "marge visible avant signature"]].map(([I, b, s]) => (
                <div key={s} className="surface rounded-xl p-4"><I className="h-4 w-4 text-primary" /><p className="font-display font-bold text-lg mt-2">{b}</p><p className="text-[11px] text-muted-foreground">{s}</p></div>
              ))}
            </div>
          </motion.div>

          <motion.div {...fade(0.1)} className="surface rounded-2xl p-7 border border-primary/30 shadow-2xl relative overflow-hidden" data-testid="metre-pricing">
            <div className="absolute -top-16 -right-16 h-40 w-40 rounded-full bg-primary/15 blur-2xl" />
            <p className="overline text-primary">Le métré IA, avec Pro</p>
            <h3 className="font-display text-2xl font-bold mt-1">Pour chiffrer aussi ce qu'on vous envoie : un plan, une DPGF, une note vocale.</h3>
            <p className="mt-4"><span className="num text-4xl font-extrabold">149 €</span> <span className="text-sm text-muted-foreground">HT / mois · sans engagement · 7 jours d'essai</span></p>
            <p className="text-xs text-muted-foreground">Pro Business (équipes, multi-utilisateurs) : 249 € HT / mois</p>
            <ul className="text-sm space-y-2 mt-5">
              {["Devis et factures illimités (acompte, situations, solde, Factur-X)", "Métré IA : le plan devient des surfaces et des ouvrages", "Photos, vidéos, notes vocales et cotes de vos plans lus par l'IA", "DPGF reçue lue et chiffrée à vos prix", "Marge prévisionnelle lot par lot + alerte « à perte »", "Reprise de votre bibliothèque depuis vos anciens devis PDF", "Chantiers, clients, relances, signature en ligne"].map((f) => (
                <li key={f} className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" /> {f}</li>
              ))}
            </ul>
            <Button asChild size="lg" className="rounded-full w-full mt-6 h-12" data-testid="metre-cta-pricing"><Link to="/inscription?signup=1&plan=pro">Démarrer l'essai gratuit</Link></Button>
            <p className="text-center text-xs text-muted-foreground mt-2"><Link to="/tarifs" className="underline underline-offset-2">Voir tous les tarifs</Link></p>
          </motion.div>
        </div>
      </section>

      {/* FAQ */}
      <section className="mx-auto max-w-3xl px-5 lg:px-8 py-16" data-testid="metre-faq">
        <motion.div {...fade()}>
          <p className="overline text-primary">Questions fréquentes</p>
          <h2 className="font-display text-3xl md:text-4xl font-bold mt-2 mb-6">Tout ce que vous voulez savoir avant de tester.</h2>
        </motion.div>
        <Accordion type="single" collapsible className="w-full">
          {FAQ.map(([q, a], i) => (
            <AccordionItem key={q} value={`q${i}`} data-testid={`metre-faq-${i}`}>
              <AccordionTrigger className="text-left font-display font-bold">{q}</AccordionTrigger>
              <AccordionContent className="text-muted-foreground leading-relaxed">{a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>

      <Footer />
    </div>
  );
}
