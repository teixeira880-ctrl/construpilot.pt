import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ShieldCheck, Smartphone } from "lucide-react";

const CONTACT_EMAIL = "contact@construpilot.fr";
const UPDATED_FR = "Juin 2026";
const UPDATED_EN = "June 2026";

const APPS = [
  "ConstruPilot Chantier",
  "ConstruPilot Collaborateur",
  "ConstruPilot Particuliers",
];

const PERMISSIONS = [
  {
    key: "camera",
    fr: ["Appareil photo", "Prendre des photos de chantier, scanner des devis et documents. Les photos sont envoyées à nos serveurs uniquement lorsque vous les rattachez à un chantier ou un document."],
    en: ["Camera", "Take site photos, scan quotes and documents. Photos are uploaded to our servers only when you attach them to a project or a document."],
  },
  {
    key: "microphone",
    fr: ["Microphone", "Dictée vocale (devis, réserves, messages). L'extrait audio est transmis à notre prestataire de transcription (OpenAI Whisper) puis supprimé ; seul le texte transcrit est conservé."],
    en: ["Microphone", "Voice dictation (quotes, punch-list items, messages). The audio clip is sent to our transcription provider (OpenAI Whisper) then deleted; only the transcribed text is stored."],
  },
  {
    key: "photos",
    fr: ["Photos / Fichiers", "Importer des plans, PDF et images depuis votre appareil. Aucun accès en arrière-plan à votre galerie."],
    en: ["Photos / Files", "Import plans, PDFs and images from your device. No background access to your gallery."],
  },
  {
    key: "location",
    fr: ["Localisation (optionnelle)", "Uniquement si vous activez le pointage géolocalisé ou la recherche de chantiers proches. Jamais de suivi en arrière-plan."],
    en: ["Location (optional)", "Only if you enable geo-stamped time tracking or nearby-project search. Never tracked in the background."],
  },
  {
    key: "notifications",
    fr: ["Notifications", "Alertes sur vos devis, messages client et rappels de chantier. Désactivables à tout moment."],
    en: ["Notifications", "Alerts about your quotes, client messages and project reminders. Can be disabled at any time."],
  },
];

const Section = ({ title, children }) => (
  <section className="mt-8">
    <h2 className="font-display text-xl font-bold text-foreground mb-2">{title}</h2>
    <div className="space-y-3 text-[15px] leading-relaxed text-foreground/90">{children}</div>
  </section>
);

const FrenchPolicy = () => (
  <div data-testid="app-privacy-fr">
    <p>
      La présente politique de confidentialité s'applique aux applications mobiles{" "}
      <strong>{APPS.join(", ")}</strong> (iOS et Android) ainsi qu'au service web ConstruPilot,
      édités par ConstruPilot. Elle est établie conformément au Règlement Général sur la
      Protection des Données (RGPD) et aux exigences de l'App Store d'Apple et de Google Play.
    </p>

    <Section title="1. Responsable du traitement">
      <p>
        ConstruPilot — contact :{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        Toute demande relative à vos données est traitée sous 30 jours.
      </p>
    </Section>

    <Section title="2. Données que nous collectons">
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Identité et contact</strong> : nom, e-mail, téléphone (facultatif).</li>
        <li><strong>Compte et authentification</strong> : mot de passe chiffré, jeton de session.</li>
        <li><strong>Données professionnelles</strong> : raison sociale, SIRET, TVA, logo, coordonnées bancaires de facturation si renseignées.</li>
        <li><strong>Contenus que vous créez</strong> : devis, factures, chantiers, photos, plans, notes vocales, messages échangés avec vos clients.</li>
        <li><strong>Données techniques</strong> : type d'appareil, version de l'app, journaux d'erreurs, adresse IP.</li>
        <li><strong>Paiement</strong> : traité exclusivement par Stripe. Nous ne stockons aucun numéro de carte.</li>
      </ul>
      <p>
        Nous ne collectons aucune donnée sensible (santé, origine, opinions) et n'utilisons
        aucun traceur publicitaire tiers. Aucune donnée n'est vendue.
      </p>
    </Section>

    <Section title="3. Autorisations demandées par l'application">
      <div className="space-y-3">
        {PERMISSIONS.map((p) => (
          <div key={p.key} className="rounded-lg border border-border p-3">
            <p className="font-semibold text-foreground">{p.fr[0]}</p>
            <p className="text-sm text-muted-foreground mt-0.5">{p.fr[1]}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Chaque autorisation est demandée au moment de l'usage et peut être refusée ou révoquée
        dans les réglages de votre téléphone, sans bloquer les autres fonctions de l'app.
      </p>
    </Section>

    <Section title="4. Finalités et bases légales">
      <p>
        Exécution du contrat (fourniture du service, gestion du compte et de l'abonnement),
        obligations légales (facturation, comptabilité), intérêt légitime (sécurité,
        prévention de la fraude, amélioration du service) et consentement pour les
        fonctionnalités optionnelles (localisation, notifications).
      </p>
    </Section>

    <Section title="5. Intelligence artificielle">
      <p>
        Certaines fonctions (Assistant BTP, estimation, transcription vocale, analyse de photos)
        envoient le contenu strictement nécessaire à nos prestataires d'IA (OpenAI, Anthropic,
        Google). Ces contenus ne sont pas utilisés pour entraîner leurs modèles. Les résultats
        produits par l'IA sont indicatifs et ne constituent pas un engagement contractuel.
      </p>
    </Section>

    <Section title="6. Sous-traitants">
      <ul className="list-disc pl-5 space-y-1">
        <li>Hébergement et stockage de fichiers : infrastructure cloud Emergent (UE).</li>
        <li>Paiement : Stripe.</li>
        <li>IA et transcription : OpenAI, Anthropic, Google.</li>
        <li>E-mails transactionnels : notre prestataire d'envoi.</li>
      </ul>
    </Section>

    <Section title="7. Durée de conservation">
      <p>
        Les données de compte sont conservées pendant toute la durée de la relation
        contractuelle. Après suppression du compte, elles sont effacées sous 30 jours, à
        l'exception des pièces comptables (factures) conservées 10 ans conformément à la loi.
      </p>
    </Section>

    <Section title="8. Suppression du compte et des données">
      <p>
        Vous pouvez supprimer votre compte directement dans l'application (Mon compte →
        Supprimer mon compte) ou en écrivant à{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}?subject=Suppression%20de%20compte`}>{CONTACT_EMAIL}</a>.
        La suppression entraîne l'effacement de vos chantiers, documents, photos et messages.
        Procédure détaillée :{" "}
        <Link className="text-primary underline" to="/suppression-compte" data-testid="privacy-delete-link">construpilot.fr/suppression-compte</Link>.
      </p>
    </Section>

    <Section title="9. Vos droits">
      <p>
        Accès, rectification, effacement, portabilité, limitation et opposition. Exercez-les à{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        Vous pouvez introduire une réclamation auprès de la CNIL (www.cnil.fr).
      </p>
    </Section>

    <Section title="10. Enfants">
      <p>
        Les applications ConstruPilot sont destinées aux adultes et aux professionnels. Elles ne
        s'adressent pas aux enfants de moins de 16 ans et nous ne collectons pas sciemment leurs
        données.
      </p>
    </Section>

    <Section title="11. Sécurité">
      <p>
        Chiffrement des échanges (HTTPS/TLS), mots de passe hachés, cookies de session HttpOnly,
        cloisonnement strict des données entre entreprises et accès invités limités aux seuls
        éléments explicitement partagés par le professionnel.
      </p>
    </Section>

    <Section title="12. Modifications">
      <p>
        Toute modification de cette politique sera publiée sur cette page avec une nouvelle date
        de mise à jour. Pour toute question :{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
        · Assistance : <Link className="text-primary underline" to="/aide">page d'aide</Link>.
      </p>
    </Section>
  </div>
);

const EnglishPolicy = () => (
  <div data-testid="app-privacy-en">
    <p>
      This privacy policy applies to the mobile applications{" "}
      <strong>{APPS.join(", ")}</strong> (iOS and Android) and to the ConstruPilot web service,
      published by ConstruPilot. It complies with the EU General Data Protection Regulation
      (GDPR) and with Apple App Store and Google Play requirements.
    </p>

    <Section title="1. Data controller">
      <p>
        ConstruPilot — contact:{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        Any request regarding your data is handled within 30 days.
      </p>
    </Section>

    <Section title="2. Data we collect">
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Identity and contact</strong>: name, email, phone (optional).</li>
        <li><strong>Account and authentication</strong>: hashed password, session token.</li>
        <li><strong>Business data</strong>: company name, registration and VAT numbers, logo, billing details if provided.</li>
        <li><strong>Content you create</strong>: quotes, invoices, projects, photos, plans, voice notes, messages exchanged with your clients.</li>
        <li><strong>Technical data</strong>: device type, app version, crash logs, IP address.</li>
        <li><strong>Payments</strong>: processed exclusively by Stripe. We never store card numbers.</li>
      </ul>
      <p>
        We collect no sensitive data (health, ethnicity, opinions) and use no third-party
        advertising trackers. Your data is never sold.
      </p>
    </Section>

    <Section title="3. Permissions requested by the app">
      <div className="space-y-3">
        {PERMISSIONS.map((p) => (
          <div key={p.key} className="rounded-lg border border-border p-3">
            <p className="font-semibold text-foreground">{p.en[0]}</p>
            <p className="text-sm text-muted-foreground mt-0.5">{p.en[1]}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Each permission is requested at the time of use and can be denied or revoked in your
        phone settings without blocking other app features.
      </p>
    </Section>

    <Section title="4. Purposes and legal bases">
      <p>
        Performance of the contract (service delivery, account and subscription management),
        legal obligations (invoicing, accounting), legitimate interest (security, fraud
        prevention, service improvement) and consent for optional features (location,
        notifications).
      </p>
    </Section>

    <Section title="5. Artificial intelligence">
      <p>
        Some features (construction assistant, cost estimation, voice transcription, photo
        analysis) send only the necessary content to our AI providers (OpenAI, Anthropic,
        Google). This content is not used to train their models. AI outputs are indicative and
        do not constitute a contractual commitment.
      </p>
    </Section>

    <Section title="6. Processors">
      <ul className="list-disc pl-5 space-y-1">
        <li>Hosting and file storage: Emergent cloud infrastructure (EU).</li>
        <li>Payments: Stripe.</li>
        <li>AI and transcription: OpenAI, Anthropic, Google.</li>
        <li>Transactional emails: our email delivery provider.</li>
      </ul>
    </Section>

    <Section title="7. Retention">
      <p>
        Account data is kept for the duration of the contractual relationship. After account
        deletion it is erased within 30 days, except accounting records (invoices) kept for 10
        years as required by law.
      </p>
    </Section>

    <Section title="8. Account and data deletion">
      <p>
        You can delete your account directly in the app (My account → Delete my account) or by
        writing to{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}?subject=Account%20deletion`}>{CONTACT_EMAIL}</a>.
        Deletion erases your projects, documents, photos and messages.
        Full procedure:{" "}
        <Link className="text-primary underline" to="/delete-account" data-testid="privacy-delete-link-en">construpilot.fr/delete-account</Link>.
      </p>
    </Section>

    <Section title="9. Your rights">
      <p>
        Access, rectification, erasure, portability, restriction and objection. Exercise them at{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        You may lodge a complaint with the French data protection authority (CNIL, www.cnil.fr).
      </p>
    </Section>

    <Section title="10. Children">
      <p>
        ConstruPilot apps are intended for adults and professionals. They are not directed at
        children under 16 and we do not knowingly collect their data.
      </p>
    </Section>

    <Section title="11. Security">
      <p>
        Encrypted transport (HTTPS/TLS), hashed passwords, HttpOnly session cookies, strict data
        isolation between companies, and guest access limited to what the professional
        explicitly shares.
      </p>
    </Section>

    <Section title="12. Changes">
      <p>
        Any change to this policy will be published on this page with a new update date.
        Questions:{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
        · Support: <Link className="text-primary underline" to="/aide">help page</Link>.
      </p>
    </Section>
  </div>
);

export default function AppPrivacy() {
  const [lang, setLang] = useState("fr");
  useEffect(() => { document.documentElement.lang = lang === "en" ? "en" : "fr"; }, [lang]);

  return (
    <div className="max-w-3xl mx-auto px-6 py-14" data-testid="page-app-privacy">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6"
        data-testid="app-privacy-back-link"
      >
        <ArrowLeft className="h-4 w-4" /> {lang === "fr" ? "Retour à l'accueil" : "Back to home"}
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Smartphone className="h-3.5 w-3.5" />
            {lang === "fr" ? "Applications mobiles & web" : "Mobile & web apps"}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground mt-2">
            {lang === "fr" ? "Politique de confidentialité" : "Privacy Policy"}
          </h1>
          <p className="text-xs text-muted-foreground mt-2">
            {lang === "fr"
              ? `Dernière mise à jour : ${UPDATED_FR}`
              : `Last updated: ${UPDATED_EN}`}
          </p>
        </div>

        <div className="flex rounded-full border border-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setLang("fr")}
            data-testid="app-privacy-lang-fr"
            className={`px-4 py-1.5 transition-colors ${lang === "fr" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            Français
          </button>
          <button
            type="button"
            onClick={() => setLang("en")}
            data-testid="app-privacy-lang-en"
            className={`px-4 py-1.5 transition-colors ${lang === "en" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            English
          </button>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4 text-primary shrink-0" />
        {lang === "fr"
          ? "Aucune donnée vendue · Aucun traceur publicitaire · Hébergement UE"
          : "No data sold · No ad trackers · EU hosting"}
      </div>

      {lang === "fr" ? <FrenchPolicy /> : <EnglishPolicy />}
    </div>
  );
}
