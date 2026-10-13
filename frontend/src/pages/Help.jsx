import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { LifeBuoy, Bot, KeyRound, Mail, MessageCircle, ChevronDown, Send, FileText, Smartphone, Mic, ShieldCheck, Euro, Ruler } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SEO } from "@/components/SEO";

const FAQ = [
  { icon: FileText, q: "Comment créer un devis rapidement ?", a: "Depuis « Créer un devis » ou l'Assistant BTP : décrivez les travaux (ou dictez-les), l'IA propose des lignes chiffrées que vous validez. Chaque prix indique sa provenance (bibliothèque, votre catalogue, saisie). Le devis se convertit en facture en un clic ; un devis signé est figé et toute modification crée une révision." },
  { icon: Euro, q: "Mes factures sont-elles conformes à la facturation électronique ?", a: "Oui : les factures sont émises au format Factur-X (EN 16931) avec validation automatique. Renseignez SIRET, TVA et adresse dans Mon compte → Identité pro pour que le contrôle passe." },
  { icon: Ruler, q: "Puis-je importer un plan DWG, Revit ou PDF ?", a: "Oui, dans « Éditeur de plans » (PDF/images, métré traçable) et « Analyse de plan Pro » (DWG, RVT, IFC via Autodesk : quantités par ouvrage, export Excel). Chaque quantité conserve sa source ; en cas de désaccord entre lectures IA, le résultat est marqué « à vérifier », jamais inventé." },
  { icon: KeyRound, q: "Comment mon client ou mon sous-traitant accède-t-il à son espace ?", a: "Depuis la fiche chantier → Partage & invités → Inviter. L'invité reçoit un lien (14 jours) puis se connecte sur /espace avec l'identifiant chantier (CP-XXXX-XXXX) et un code reçu par e-mail. Il ne voit que ce chantier et uniquement ce que vous publiez : avancement, photos, messages, signalement de problème." },
  { icon: Mic, q: "La dictée vocale ne fonctionne pas", a: "Autorisez le micro dans votre navigateur (icône cadenas → Microphone). La dictée est disponible sur les notes de devis, les comptes rendus, les réserves et les messages du portail. Sur iPhone, utilisez Safari ou l'application ConstruPilot." },
  { icon: Smartphone, q: "Existe-t-il des applications mobiles ?", a: "Oui : ConstruPilot Chantier (pros), ConstruPilot Collaborateur (équipes : pointage, comptes rendus) et ConstruPilot Particuliers, sur Android et iPhone. Le site web s'installe aussi sur l'écran d'accueil avec notifications." },
  { icon: Euro, q: "Quels sont les tarifs et comment résilier ?", a: "Particuliers : gratuit. Pros : Premium 19 €, Pro 149 €, Pro Business 249 € HT/mois, sans engagement. Gestion et résiliation en un clic depuis Tarifs & abonnement → portail de facturation." },
  { icon: ShieldCheck, q: "Où sont mes données et comment les exporter ?", a: "Données hébergées en Europe, documents figés horodatés (hash SHA-256), photos et fichiers sur stockage objet chiffré. Export de vos documents en PDF/Excel depuis chaque module ; demande d'export complet ou de suppression via le formulaire ci-dessous." },
  { icon: KeyRound, q: "Mot de passe oublié ou code non reçu", a: "Utilisez « Mot de passe oublié » sur la page de connexion. Pour les codes (2FA, espace invité), vérifiez les indésirables : l'expéditeur est construpilot.fr. Le code est valable 10 minutes." },
];

function FaqItem({ item, open, onToggle, i }) {
  const I = item.icon;
  return (
    <div className="border-b border-border last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="w-full flex items-center gap-3 py-4 text-left" data-testid={`faq-q-${i}`}>
        <span className="h-8 w-8 rounded-sm bg-primary/10 text-primary grid place-items-center shrink-0"><I className="h-4 w-4" /></span>
        <span className="font-semibold text-sm flex-1">{item.q}</span>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <p className="text-sm text-muted-foreground pb-4 ps-11 leading-relaxed" data-testid={`faq-a-${i}`}>{item.a}</p>}
    </div>
  );
}

function ContactForm() {
  const { user } = useAuth();
  const [form, setForm] = useState({ name: user?.name || "", email: user?.email || "", subject: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/help/contact", form); setDone(data); }
    catch (err) { toast.error(err?.response?.status === 429 ? "Trop de demandes : réessayez dans une heure." : err?.response?.data?.detail?.[0]?.msg || err?.response?.data?.detail || "Envoi impossible"); }
    finally { setBusy(false); }
  };
  if (done) return (
    <div className="surface p-6 grid gap-2" data-testid="help-contact-done">
      <p className="font-display font-bold">Demande enregistrée — référence <span className="font-mono text-primary" data-testid="help-ticket-id">{done.ticket_id}</span></p>
      <p className="text-sm text-muted-foreground">{done.email_status === "sent" ? "Un accusé de réception vous a été envoyé par e-mail. Réponse sous 1 jour ouvré." : "Votre demande est bien enregistrée, mais l'e-mail de confirmation n'a pas pu partir : nous vous répondrons directement à l'adresse indiquée."}</p>
    </div>
  );
  return (
    <form onSubmit={submit} className="surface p-6 grid gap-3" data-testid="help-contact-form">
      <div className="grid sm:grid-cols-2 gap-3">
        <Input required minLength={2} value={form.name} onChange={set("name")} placeholder="Votre nom *" data-testid="help-name" />
        <Input required type="email" value={form.email} onChange={set("email")} placeholder="Votre e-mail *" data-testid="help-email" />
      </div>
      <Input required minLength={3} value={form.subject} onChange={set("subject")} placeholder="Sujet * (ex. Facture Factur-X refusée)" data-testid="help-subject" />
      <Textarea required minLength={10} rows={5} value={form.message} onChange={set("message")} placeholder="Décrivez votre question ou le problème rencontré (page, message d'erreur, ce que vous attendiez)…" className="resize-none" data-testid="help-message" />
      <input type="text" value={form.website} onChange={set("website")} className="hidden" tabIndex={-1} autoComplete="off" aria-hidden="true" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">Réponse par e-mail sous 1 jour ouvré · <a href="mailto:info@construpilot.fr" className="text-primary hover:underline">info@construpilot.fr</a></p>
        <Button type="submit" disabled={busy} className="gap-2" data-testid="help-submit"><Send className="h-4 w-4" /> {busy ? "Envoi…" : "Envoyer ma demande"}</Button>
      </div>
    </form>
  );
}

export default function Help() {
  const { user } = useAuth();
  const [open, setOpen] = useState(0);
  const openChat = () => window.dispatchEvent(new CustomEvent("cp:open-help"));
  const links = [
    { icon: MessageCircle, title: "Assistant en ligne", desc: "Réponse immédiate aux questions sur l'utilisation de ConstruPilot.", action: <Button size="sm" onClick={openChat} data-testid="help-open-chat">Ouvrir le chat</Button> },
    { icon: Bot, title: "Assistant BTP (IA métier)", desc: "Devis, réglementation, lecture de plans, dossier chantier — pour les pros connectés.", action: <Button size="sm" variant="outline" asChild data-testid="help-open-assistant"><Link to={user ? "/assistant" : "/login?next=/assistant"}>/assistant</Link></Button> },
    { icon: KeyRound, title: "Espace client & sous-traitant", desc: "Vous êtes invité sur un chantier ? Connectez-vous avec l'identifiant reçu.", action: <Button size="sm" variant="outline" asChild data-testid="help-open-portal"><Link to="/espace">/espace</Link></Button> },
    { icon: Mail, title: "E-mail", desc: "Pour toute question commerciale, facturation ou données personnelles.", action: <Button size="sm" variant="outline" asChild data-testid="help-mailto"><a href="mailto:info@construpilot.fr">info@construpilot.fr</a></Button> },
  ];
  return (
    <div className="grid gap-10 max-w-5xl" data-testid="help-page">
      <SEO title="Aide & assistance ConstruPilot" description="Centre d'aide ConstruPilot : questions fréquentes, assistant en ligne, espace client et formulaire de contact avec réponse sous 1 jour ouvré." path="/aide" />
      <header className="grid gap-3">
        <p className="text-xs uppercase tracking-[0.2em] text-primary font-semibold flex items-center gap-2"><LifeBuoy className="h-4 w-4" /> Assistance</p>
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">Comment pouvons-nous vous aider ?</h1>
        <p className="text-base text-muted-foreground max-w-2xl">Un assistant en ligne pour les questions immédiates, une FAQ pour l'essentiel, et une équipe qui répond par e-mail sous 1 jour ouvré.</p>
      </header>

      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="help-links">
        {links.map((l) => <div key={l.title} className="surface p-5 grid gap-3 content-start"><span className="h-10 w-10 rounded-sm bg-primary/10 text-primary grid place-items-center"><l.icon className="h-5 w-5" /></span><p className="font-display font-bold">{l.title}</p><p className="text-sm text-muted-foreground flex-1">{l.desc}</p>{l.action}</div>)}
      </section>

      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-8 items-start">
        <section className="surface px-6 py-2" data-testid="help-faq">
          <h2 className="font-display text-lg font-bold pt-4 pb-1">Questions fréquentes</h2>
          {FAQ.map((it, i) => <FaqItem key={it.q} item={it} i={i} open={open === i} onToggle={() => setOpen(open === i ? null : i)} />)}
        </section>
        <section className="grid gap-3" data-testid="help-contact">
          <h2 className="font-display text-lg font-bold">Écrire à l'assistance</h2>
          <ContactForm />
        </section>
      </div>
    </div>
  );
}
