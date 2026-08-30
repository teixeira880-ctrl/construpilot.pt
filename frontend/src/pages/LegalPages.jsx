import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const CONTACT_EMAIL = "contact@construpilot.fr";
const EDITOR = "ConstruPilot";

const LegalLayout = ({ title, updated, testid, children }) => (
  <div className="max-w-3xl mx-auto px-6 py-14" data-testid={testid}>
    <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6">
      <ArrowLeft className="h-4 w-4" /> Retour à l'accueil
    </Link>
    <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground">{title}</h1>
    <p className="text-xs text-muted-foreground mt-2">Dernière mise à jour : {updated}</p>
    <div className="prose prose-sm dark:prose-invert max-w-none mt-8 space-y-6 text-[15px] leading-relaxed text-foreground/90 [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mt-8 [&_h2]:mb-2 [&_a]:text-primary">
      {children}
    </div>
  </div>
);

export const MentionsLegales = () => (
  <LegalLayout title="Mentions légales" updated="Juin 2026" testid="page-mentions-legales">
    <h2>1. Éditeur du site</h2>
    <p>
      Le site et l'application <strong>{EDITOR}</strong> sont édités par {EDITOR}.<br />
      Forme juridique : [À COMPLÉTER — ex. SAS/EI]<br />
      Siège social : [À COMPLÉTER — adresse]<br />
      SIRET : [À COMPLÉTER] · TVA intracommunautaire : [À COMPLÉTER]<br />
      Directeur de la publication : [À COMPLÉTER — nom]<br />
      Contact : <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
    </p>

    <h2>2. Hébergement</h2>
    <p>
      L'application est hébergée par Emergent (infrastructure cloud). Les données sont stockées
      sur des serveurs situés dans l'Union européenne. Pour toute question relative à
      l'hébergement, contactez-nous à <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>3. Propriété intellectuelle</h2>
    <p>
      L'ensemble des contenus, marques, logos, textes, interfaces et technologies présents sur
      {" "}{EDITOR} sont protégés par le droit de la propriété intellectuelle. Technologie protégée
      par le brevet n° FR261104. Toute reproduction ou représentation, totale ou partielle, sans
      autorisation écrite est interdite.
    </p>

    <h2>4. Responsabilité</h2>
    <p>
      Les estimations, chiffrages et analyses fournis par {EDITOR} sont donnés à titre indicatif et
      ne constituent pas un engagement contractuel. L'utilisateur reste seul responsable de
      l'usage qu'il fait des résultats produits.
    </p>

    <h2>5. Liens et contact</h2>
    <p>
      Voir aussi notre <Link to="/confidentialite">Politique de confidentialité</Link> et nos{" "}
      <Link to="/cgv">Conditions générales</Link>. Pour toute réclamation :{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>
  </LegalLayout>
);

export const Confidentialite = () => (
  <LegalLayout title="Politique de confidentialité" updated="Juin 2026" testid="page-confidentialite">
    <p>
      {EDITOR} accorde une grande importance à la protection de vos données personnelles,
      conformément au Règlement Général sur la Protection des Données (RGPD) et à la loi
      « Informatique et Libertés ».
    </p>

    <h2>1. Responsable du traitement</h2>
    <p>{EDITOR} — contact : <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p>

    <h2>2. Données collectées</h2>
    <p>
      Nous collectons : identité et coordonnées (nom, e-mail), données de compte et
      d'authentification, contenus que vous créez (devis, chantiers, photos, documents),
      informations d'entreprise (SIRET, TVA, logo) et données techniques (logs, appareil).
    </p>

    <h2>3. Finalités</h2>
    <p>
      Fourniture du service (estimation, devis, factures, chantiers), gestion du compte et de
      l'abonnement, facturation, support, amélioration du service et sécurité. Les paiements sont
      traités par Stripe ; les e-mails par notre prestataire d'envoi.
    </p>

    <h2>4. Base légale et durée</h2>
    <p>
      Exécution du contrat, obligations légales (facturation), et intérêt légitime. Les données
      sont conservées le temps de la relation contractuelle puis archivées selon les durées
      légales applicables.
    </p>

    <h2>5. Partage</h2>
    <p>
      Vos données ne sont jamais vendues. Elles peuvent être transmises à nos sous-traitants
      techniques (hébergement, paiement Stripe, envoi d'e-mails) strictement pour le
      fonctionnement du service.
    </p>

    <h2>6. Vos droits</h2>
    <p>
      Vous disposez d'un droit d'accès, de rectification, d'effacement, de portabilité, de
      limitation et d'opposition. Exercez-les à{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Vous pouvez saisir la CNIL en cas de
      litige (www.cnil.fr).
    </p>

    <h2>7. Cookies</h2>
    <p>
      Nous utilisons des cookies strictement nécessaires au fonctionnement (session,
      authentification) et, le cas échéant, des cookies de mesure d'audience. Vous pouvez gérer vos
      préférences depuis votre navigateur.
    </p>
  </LegalLayout>
);

export const CGV = () => (
  <LegalLayout title="Conditions générales d'utilisation et de vente" updated="Juin 2026" testid="page-cgv">
    <h2>1. Objet</h2>
    <p>
      Les présentes conditions régissent l'accès et l'utilisation de l'application {EDITOR}, ainsi
      que les abonnements payants proposés.
    </p>

    <h2>2. Compte</h2>
    <p>
      L'utilisateur s'engage à fournir des informations exactes et à préserver la confidentialité
      de ses identifiants. Chaque compte est personnel.
    </p>

    <h2>3. Abonnements et prix</h2>
    <p>
      {EDITOR} propose des fonctionnalités gratuites et des abonnements payants (Particulier et
      Professionnel). Les prix sont indiqués en euros, TTC le cas échéant. Le paiement s'effectue
      par carte via Stripe. L'abonnement est renouvelé automatiquement et résiliable à tout moment ;
      la résiliation prend effet à la fin de la période en cours.
    </p>

    <h2>4. Droit de rétractation</h2>
    <p>
      Pour les consommateurs, le droit de rétractation de 14 jours s'applique sauf renoncement
      exprès en cas d'accès immédiat au service numérique. Contact :{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>5. Disponibilité et limitation de responsabilité</h2>
    <p>
      {EDITOR} met tout en œuvre pour assurer la disponibilité du service sans pouvoir la garantir
      de façon ininterrompue. Les estimations et chiffrages sont fournis à titre indicatif.
    </p>

    <h2>6. Données personnelles</h2>
    <p>
      Le traitement des données est décrit dans notre{" "}
      <Link to="/confidentialite">Politique de confidentialité</Link>.
    </p>

    <h2>7. Droit applicable</h2>
    <p>
      Les présentes conditions sont soumises au droit français. En cas de litige, une solution
      amiable sera recherchée avant toute action judiciaire.
    </p>
  </LegalLayout>
);
