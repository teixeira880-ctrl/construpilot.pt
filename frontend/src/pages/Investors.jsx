import { Link } from "react-router-dom";
import { useState } from "react";
import {
  ArrowRight, ScanLine, Cuboid, FileText, Bot, Globe2, ShieldCheck,
  TrendingUp, Target, Rocket, PieChart, Mail, CheckCircle2, Building2, Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CONTACT = "info@construpilot.fr";
const DECK_PDF = `${process.env.REACT_APP_BACKEND_URL}/api/investors/pitch-deck.pdf`;

const DeckDownloadDialog = ({ open, onOpenChange }) => {
  const [form, setForm] = useState({ name: "", email: "", fund: "", note: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email) return;
    setBusy(true);
    try {
      await api.post("/investors/deck-request", form);
      window.open(DECK_PDF, "_blank", "noopener,noreferrer");
      toast.success("Merci ! Le pitch deck s'ouvre dans un nouvel onglet.");
      onOpenChange(false);
      setForm({ name: "", email: "", fund: "", note: "" });
    } catch {
      // On ne bloque pas l'accès au deck si le log échoue
      window.open(DECK_PDF, "_blank", "noopener,noreferrer");
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="deck-download-dialog">
        <DialogHeader>
          <DialogTitle>Recevoir le pitch deck</DialogTitle>
          <DialogDescription>
            Laissez-nous vos coordonnées — le PDF s'ouvre juste après.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="deck-name">Nom</Label>
            <Input id="deck-name" value={form.name} onChange={set("name")}
                   placeholder="Votre nom" data-testid="deck-form-name" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deck-email">E-mail *</Label>
            <Input id="deck-email" type="email" required value={form.email} onChange={set("email")}
                   placeholder="vous@fonds.com" data-testid="deck-form-email" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deck-fund">Fonds / société</Label>
            <Input id="deck-fund" value={form.fund} onChange={set("fund")}
                   placeholder="Ex : Urban Ventures" data-testid="deck-form-fund" />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={busy} className="rounded-full gap-2" data-testid="deck-form-submit">
              <Download className="h-4 w-4" /> {busy ? "…" : "Télécharger le PDF"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const Slide = ({ n, kicker, title, children, dark }) => (
  <section data-testid={`deck-slide-${n}`}
           className={`relative border-b border-border ${dark ? "bg-secondary/30" : "bg-background"}`}>
    <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-20 lg:py-28">
      <div className="flex items-center gap-3 mb-5">
        <span className="num text-xs font-bold text-primary/70">{String(n).padStart(2, "0")}</span>
        <span className="overline">{kicker}</span>
      </div>
      <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight max-w-4xl">{title}</h2>
      <div className="mt-8">{children}</div>
    </div>
  </section>
);

const Card = ({ icon: Icon, title, text }) => (
  <div className="rounded-2xl border border-border bg-card p-6">
    <span className="h-11 w-11 rounded-xl bg-primary/10 border border-primary/20 grid place-items-center mb-4">
      <Icon className="h-5 w-5 text-primary" />
    </span>
    <h3 className="font-semibold text-lg">{title}</h3>
    <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{text}</p>
  </div>
);

const Stat = ({ v, l }) => (
  <div className="rounded-2xl border border-border bg-card p-6 text-center">
    <p className="num text-4xl font-extrabold text-primary">{v}</p>
    <p className="mt-2 text-xs text-muted-foreground">{l}</p>
  </div>
);

export default function Investors() {
  const [deckOpen, setDeckOpen] = useState(false);
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="investors-page">
      <DeckDownloadDialog open={deckOpen} onOpenChange={setDeckOpen} />
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 h-16 flex items-center justify-between">
          <Link to="/" className="font-display font-bold text-lg">Constru<span className="text-primary">Pilot</span></Link>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-full gap-2" data-testid="deck-download-top"
                    onClick={() => setDeckOpen(true)}>
              <Download className="h-4 w-4" /> Pitch deck PDF
            </Button>
            <Button asChild size="sm" className="rounded-full gap-2" data-testid="deck-contact-top">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot`}><Mail className="h-4 w-4" /> Contacter</a>
            </Button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 h-72 w-[70%] bg-primary/20 blur-3xl rounded-full pointer-events-none" />
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 lg:py-32 text-center relative">
          <span className="overline">Dossier investisseurs · 2026</span>
          <h1 className="mt-5 font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            L'IA qui transforme un plan<br className="hidden sm:block" /> en devis chiffré, en secondes.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            ConstruPilot digitalise tout le cycle du BTP : analyse IA des plans, métré béton & aciers,
            maquette 3D et devis automatique — dans une seule plateforme.
          </p>
          <div className="mt-9 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-contact">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot`}><Mail className="h-5 w-5" /> Parler à l'équipe</a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-demo">
              <Link to="/">Voir la démo <ArrowRight className="h-5 w-5" /></Link>
            </Button>
            <Button size="lg" variant="ghost" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-download"
                    onClick={() => setDeckOpen(true)}>
              <Download className="h-5 w-5" /> Télécharger le pitch deck (PDF)
            </Button>
          </div>
        </div>
      </section>

      {/* 01 PROBLÈME */}
      <Slide n={1} kicker="Le problème" dark
             title="Chiffrer un chantier reste lent, manuel et source d'erreurs.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={FileText} title="Des heures perdues" text="Un métré manuel depuis un plan prend des heures et retarde l'envoi des devis." />
          <Card icon={Target} title="Marges qui fuient" text="Erreurs de quantités, oublis de postes, prix non à jour : la rentabilité s'érode." />
          <Card icon={Building2} title="Outils cloisonnés" text="Métré, devis, 3D, facturation et chantier vivent dans des logiciels séparés." />
        </div>
      </Slide>

      {/* 02 SOLUTION */}
      <Slide n={2} kicker="La solution"
             title="Une plateforme unique, du plan au devis signé — propulsée par l'IA.">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <Card icon={ScanLine} title="Analyse IA du plan" text="Détection murs, poteaux, poutres, semelles + métré béton & aciers automatiques." />
          <Card icon={FileText} title="Devis instantané" text="Depuis un plan, une description ou une vidéo. Chiffrage auto via la bibliothèque de prix." />
          <Card icon={Cuboid} title="Maquette 3D" text="Visualisation des volumes détectés, export PNG joint au devis client." />
          <Card icon={Bot} title="Assistant IA" text="Correction du plan en langage naturel, marge & prix de vente estimés." />
        </div>
      </Slide>

      {/* 03 MARCHÉ */}
      <Slide n={3} kicker="Le marché" dark
             title="Un secteur immense, encore peu digitalisé.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Stat v="+500 Md€" l="marché du BTP en France (par an)" />
          <Stat v="~600 000" l="entreprises du bâtiment en France" />
          <Stat v="< 30%" l="équipées d'un vrai outil de chiffrage" />
        </div>
        <p className="mt-6 text-sm text-muted-foreground max-w-3xl">
          Tendances porteuses 2026 : obligation de facture électronique, pénurie de main-d'œuvre
          (besoin de productivité) et adoption rapide de l'IA. Cible : artisans, PME du BTP et bureaux d'études.
        </p>
      </Slide>

      {/* 04 DIFFÉRENCIATION */}
      <Slide n={4} kicker="Notre avantage"
             title="Le seul outil qui relie IA de plan, métré béton, 3D et devis.">
        <ul className="grid sm:grid-cols-2 gap-4 max-w-3xl">
          {[
            "IA de plan → métré béton + aciers (unique bout-en-bout)",
            "Devis depuis une vidéo (voix + photos) — inédit sur le marché",
            "Maquette 3D générée automatiquement depuis le métré",
            "ERP intégré : factures, situations, RH, suivi de chantier",
            "Multilingue (7 langues) + Landing B2C particuliers",
            "Conformité facture électronique (Factur-X) déjà en place",
          ].map((t) => (
            <li key={t} className="flex items-start gap-3 text-sm">
              <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" /><span>{t}</span>
            </li>
          ))}
        </ul>
      </Slide>

      {/* 05 MODÈLE ÉCONOMIQUE */}
      <Slide n={5} kicker="Modèle économique" dark
             title="SaaS par abonnement, revenus récurrents et scalables.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={TrendingUp} title="Abonnement SaaS" text="Formules mensuelles par utilisateur (artisan → PME), montée en gamme par modules." />
          <Card icon={PieChart} title="Options à la valeur" text="Crédits IA, module Entreprise (RBAC/RH/chantier), génération de documents." />
          <Card icon={Globe2} title="Expansion" text="Marché francophone puis Europe du Sud (déjà multilingue), et B2C particuliers." />
        </div>
      </Slide>

      {/* 06 POURQUOI MAINTENANT */}
      <Slide n={6} kicker="Pourquoi maintenant"
             title="Le bon produit, au bon moment.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={Rocket} title="IA mature" text="Les modèles de vision permettent enfin de lire des plans de façon fiable." />
          <Card icon={ShieldCheck} title="Réglementation" text="La facture électronique pousse tout le secteur à s'équiper en 2026-2027." />
          <Card icon={TrendingUp} title="Produit déjà avancé" text="Plateforme complète et fonctionnelle, prête à passer à l'échelle." />
        </div>
      </Slide>

      {/* 07 L'ASK */}
      <section className="border-b border-border bg-gradient-to-br from-primary/15 via-card to-secondary">
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 text-center">
          <span className="overline">L'opportunité</span>
          <h2 className="mt-5 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
            Nous levons pour accélérer.
          </h2>
          <div className="mt-10 grid sm:grid-cols-3 gap-5 max-w-3xl mx-auto text-left">
            <Card icon={Rocket} title="Produit & IA" text="Renforcer la détection (IFC/BIM), la 3D et l'automatisation du chiffrage." />
            <Card icon={TrendingUp} title="Go-to-market" text="Acquisition artisans/PME, partenariats fournisseurs & fédérations BTP." />
            <Card icon={Building2} title="Équipe" text="Recrutements produit, IA et commercial pour passer à l'échelle." />
          </div>
          <div className="mt-10 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-final">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot&body=Bonjour, je souhaite en savoir plus sur l'opportunité d'investissement dans ConstruPilot.`}>
                <Mail className="h-5 w-5" /> Demander le dossier complet
              </a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2">
              <Link to="/">Explorer le produit <ArrowRight className="h-5 w-5" /></Link>
            </Button>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">Contact : {CONTACT}</p>
        </div>
      </section>

      <footer className="mx-auto max-w-[1200px] px-6 lg:px-10 py-10 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} ConstruPilot — Document confidentiel destiné aux investisseurs.
      </footer>
    </div>
  );
}
