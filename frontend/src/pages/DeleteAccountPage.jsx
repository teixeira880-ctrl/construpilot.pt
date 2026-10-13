import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, Trash2, ShieldCheck, Mail, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "sonner";

const APPS = ["ConstruPilot Chantier", "ConstruPilot Collaborateur", "ConstruPilot Particuliers"];
const CONTACT_EMAIL = "contact@construpilot.fr";
const UPDATED = { fr: "Juin 2026", en: "June 2026" };

const T = {
  fr: {
    over: "Applications mobiles & web",
    title: "Supprimer mon compte ConstruPilot",
    updated: (d) => `Dernière mise à jour : ${d}`,
    banner: "Suppression définitive · Aucune donnée vendue · Hébergement UE",
    intro: `Cette page explique comment demander la suppression de votre compte et de vos données pour les applications ${APPS.join(", ")} et le service web ConstruPilot (éditeur : ConstruPilot).`,
    s1: "1. Supprimer votre compte depuis l'application",
    s1b: [
      "Connectez-vous à votre compte (application mobile ou site web).",
      "Ouvrez « Mon compte » (menu profil) → section « Supprimer mon compte ».",
      "Saisissez votre mot de passe puis tapez SUPPRIMER pour confirmer.",
      "La suppression est immédiate et définitive : aucune période d'attente, aucun rappel commercial.",
    ],
    s1link: "Ouvrir la page Mon compte",
    s2: "2. Vous n'avez plus accès à votre compte ?",
    s2p: "Envoyez-nous une demande avec l'adresse e-mail du compte concerné. Nous vérifions votre identité puis supprimons le compte sous 30 jours maximum (généralement sous 72 h ouvrées). Vous recevez une confirmation par e-mail.",
    s3: "3. Données supprimées",
    s3b: [
      "Compte et profil : nom, e-mail, téléphone, mot de passe, photo, préférences, sessions et appareils.",
      "Contenus professionnels : chantiers, devis, plans, métrés, photos de chantier, documents importés, messages et fils de discussion.",
      "Contacts : clients, sous-traitants, fournisseurs et collaborateurs invités par vous.",
      "Historique d'usage : notifications, recherches, journaux d'activité, crédits et statistiques liés au compte.",
    ],
    s4: "4. Données conservées (obligations légales)",
    s4b: [
      "Factures émises et pièces comptables : conservées 10 ans (article L.123-22 du Code de commerce) hors de votre espace, sans accès marketing.",
      "Preuves de facturation d'abonnement conservées par notre prestataire de paiement (Stripe) selon ses obligations légales.",
      "Journaux techniques de sécurité anonymisés : 12 mois maximum.",
      "Sauvegardes chiffrées : purgées par rotation sous 30 jours.",
    ],
    s5: "5. Conséquences de la suppression",
    s5p: "La suppression met fin à votre abonnement en cours et n'ouvre pas droit à remboursement des périodes déjà réglées. Vos collaborateurs et clients perdent l'accès aux espaces partagés que vous aviez créés. L'opération est irréversible : exportez vos devis, factures et documents avant de confirmer.",
    s6: "6. Nous contacter",
    s6p: "Pour toute question relative à vos données personnelles (accès, rectification, portabilité, suppression) :",
    form: "Demande de suppression de compte",
    fname: "Nom et prénom",
    femail: "E-mail du compte à supprimer",
    fmsg: "Précisions (facultatif)",
    fmsgph: "Ex. nom de l'entreprise, dernière connexion, application utilisée…",
    send: "Envoyer ma demande de suppression",
    sent: "Demande envoyée. Vous recevez un accusé de réception par e-mail ; la suppression est traitée sous 30 jours maximum.",
    err: "Envoi impossible. Écrivez-nous directement à " + CONTACT_EMAIL,
    required: "Indiquez votre nom et l'e-mail du compte.",
    dataTitle: "Demander la suppression de mes données",
    dataIntro: `Cette page permet à tout utilisateur des applications ${APPS.join(", ")} et du service web ConstruPilot de demander la suppression de ses données personnelles, avec ou sans suppression du compte.`,
    dataChoice: "Que souhaitez-vous supprimer ?",
    dataOptA: "Tout mon compte et toutes mes données",
    dataOptB: "Seulement certaines données (photos, chantier, contacts, historique…) en gardant mon compte",
    dataWhich: "Données à supprimer",
    dataWhichPh: "Ex. photos du chantier « Villa Dupont », mes contacts clients, l'historique de l'assistant IA…",
    dataForm: "Demande de suppression de données",
    dataSend: "Envoyer ma demande de suppression de données",
    dataDelay: "Nous répondons sous 30 jours maximum (généralement 72 h ouvrées), conformément au RGPD (article 17 — droit à l'effacement).",
    dataLink: "Vous voulez seulement supprimer certaines données, sans fermer votre compte ?",
    accountLink: "Vous voulez supprimer tout votre compte ?",
  },
  en: {
    over: "Mobile & web apps",
    title: "Delete my ConstruPilot account",
    updated: (d) => `Last updated: ${d}`,
    banner: "Permanent deletion · No data sold · EU hosting",
    intro: `This page explains how to request the deletion of your account and data for the ${APPS.join(", ")} apps and the ConstruPilot web service (publisher: ConstruPilot).`,
    s1: "1. Delete your account from the app",
    s1b: [
      "Sign in to your account (mobile app or website).",
      "Open “My account” (profile menu) → “Delete my account” section.",
      "Enter your password then type SUPPRIMER to confirm.",
      "Deletion is immediate and permanent: no waiting period, no marketing follow-up.",
    ],
    s1link: "Open My account",
    s2: "2. Can't access your account anymore?",
    s2p: "Send us a request using the e-mail address of the account. We verify your identity and delete the account within 30 days at most (usually within 72 business hours). You receive an e-mail confirmation.",
    s3: "3. Data that is deleted",
    s3b: [
      "Account and profile: name, e-mail, phone, password, picture, preferences, sessions and devices.",
      "Professional content: projects, quotes, plans, take-offs, site photos, uploaded documents, messages and threads.",
      "Contacts: clients, subcontractors, suppliers and team members you invited.",
      "Usage history: notifications, searches, activity logs, credits and account statistics.",
    ],
    s4: "4. Data we must keep (legal obligations)",
    s4b: [
      "Issued invoices and accounting records: kept for 10 years (French Commercial Code, art. L.123-22), outside your workspace and never used for marketing.",
      "Subscription billing records kept by our payment provider (Stripe) under its own legal obligations.",
      "Anonymised technical security logs: 12 months maximum.",
      "Encrypted backups: purged by rotation within 30 days.",
    ],
    s5: "5. Consequences of deletion",
    s5p: "Deletion ends your current subscription and does not entitle you to a refund for periods already paid. Your team members and clients lose access to the shared spaces you created. The operation is irreversible: export your quotes, invoices and documents before confirming.",
    s6: "6. Contact us",
    s6p: "For any question about your personal data (access, rectification, portability, deletion):",
    form: "Account deletion request",
    fname: "Full name",
    femail: "E-mail of the account to delete",
    fmsg: "Details (optional)",
    fmsgph: "E.g. company name, last sign-in, app used…",
    send: "Send my deletion request",
    sent: "Request sent. You will receive an acknowledgement by e-mail; deletion is processed within 30 days at most.",
    err: "Sending failed. Please e-mail us directly at " + CONTACT_EMAIL,
    required: "Please provide your name and the account e-mail.",
    dataTitle: "Request deletion of my data",
    dataIntro: `This page lets any user of the ${APPS.join(", ")} apps and the ConstruPilot web service request the deletion of their personal data, with or without deleting the account.`,
    dataChoice: "What do you want deleted?",
    dataOptA: "My whole account and all my data",
    dataOptB: "Only some data (photos, a project, contacts, history…) while keeping my account",
    dataWhich: "Data to delete",
    dataWhichPh: "E.g. photos of the “Villa Dupont” project, my client contacts, the AI assistant history…",
    dataForm: "Data deletion request",
    dataSend: "Send my data deletion request",
    dataDelay: "We answer within 30 days at most (usually 72 business hours), in line with the GDPR (article 17 — right to erasure).",
    dataLink: "Only want some data removed, without closing your account?",
    accountLink: "Want to delete your whole account?",
  },
};

const Section = ({ title, children }) => (
  <section className="mt-8">
    <h2 className="font-display text-xl font-bold text-foreground mb-2">{title}</h2>
    <div className="space-y-3 text-[15px] leading-relaxed text-foreground/90">{children}</div>
  </section>
);

const Bullets = ({ items }) => (
  <ul className="space-y-1.5 pl-1">
    {items.map((it, i) => (
      <li key={i} className="flex gap-2">
        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
        <span>{it}</span>
      </li>
    ))}
  </ul>
);

export default function DeleteAccountPage() {
  const { pathname } = useLocation();
  const dataMode = /donnees|data-deletion/.test(pathname);
  const [lang, setLang] = useState("fr");
  const [form, setForm] = useState({ name: "", email: "", message: "", which: "", website: "" });
  const [scope, setScope] = useState(dataMode ? "partial" : "account");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const t = T[lang];

  useEffect(() => {
    document.documentElement.lang = lang;
    const titles = {
      fr: dataMode ? "Supprimer mes données — ConstruPilot" : "Supprimer mon compte — ConstruPilot",
      en: dataMode ? "Delete my data — ConstruPilot" : "Delete my account — ConstruPilot",
    };
    document.title = titles[lang];
  }, [lang, dataMode]);

  const submit = async (e) => {
    e.preventDefault();
    if (form.name.trim().length < 2 || !form.email.includes("@")) { toast.error(t.required); return; }
    const partial = scope === "partial";
    setBusy(true);
    try {
      await api.post("/help/contact", {
        name: form.name.trim(),
        email: form.email.trim(),
        subject: partial ? "Demande de suppression de données (RGPD)"
                         : "Demande de suppression de compte (RGPD)",
        message: (partial
          ? `Demande de suppression de données pour le compte ${form.email.trim()} (compte conservé).\nDonnées visées : ${form.which.trim() || "non précisé"}.`
          : `Demande de suppression définitive du compte ${form.email.trim()}.`)
          + `\n\n${form.message.trim() || "Aucune précision."}`,
        website: form.website,
      });
      setDone(true);
      toast.success(t.sent);
    } catch {
      toast.error(t.err);
    } finally { setBusy(false); }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-14" data-testid="page-delete-account">
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6" data-testid="delete-account-back-link">
        <ArrowLeft className="h-4 w-4" /> {lang === "fr" ? "Retour à l'accueil" : "Back to home"}
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Trash2 className="h-3.5 w-3.5" /> {t.over}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground mt-2">{dataMode ? t.dataTitle : t.title}</h1>
          <p className="text-xs text-muted-foreground mt-2">{t.updated(UPDATED[lang])}</p>
        </div>
        <div className="flex rounded-full border border-border overflow-hidden text-sm">
          <button type="button" onClick={() => setLang("fr")} data-testid="delete-account-lang-fr"
            className={`px-4 py-1.5 transition-colors ${lang === "fr" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>Français</button>
          <button type="button" onClick={() => setLang("en")} data-testid="delete-account-lang-en"
            className={`px-4 py-1.5 transition-colors ${lang === "en" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>English</button>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4 text-primary shrink-0" /> {t.banner}
      </div>

      <p className="mt-6 text-[15px] leading-relaxed text-foreground/90" data-testid="delete-account-intro">{dataMode ? t.dataIntro : t.intro}</p>

      <Section title={t.s1}>
        <Bullets items={t.s1b} />
        <Button asChild variant="outline" className="rounded-sm gap-2 mt-1" data-testid="delete-account-app-link">
          <Link to="/compte">{t.s1link}</Link>
        </Button>
      </Section>

      <Section title={dataMode ? t.dataForm : t.s2}>
        <p id="demande">{dataMode ? t.dataDelay : t.s2p}</p>
        {done ? (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex gap-3 text-sm" data-testid="delete-account-form-done">
            <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
            <span>{t.sent}</span>
          </div>
        ) : (
          <form onSubmit={submit} className="surface rounded-md p-4 space-y-3" data-testid="delete-account-form">
            <p className="overline">{dataMode ? t.dataForm : t.form}</p>
            <input type="text" tabIndex={-1} autoComplete="off" className="hidden" value={form.website}
              onChange={(e) => setForm({ ...form, website: e.target.value })} />
            <fieldset className="grid gap-2 text-sm" data-testid="delete-account-scope">
              <legend className="text-xs text-muted-foreground mb-1">{t.dataChoice}</legend>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="scope" value="account" checked={scope === "account"}
                  onChange={() => setScope("account")} className="mt-1 accent-primary" data-testid="scope-account" />
                <span>{t.dataOptA}</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="scope" value="partial" checked={scope === "partial"}
                  onChange={() => setScope("partial")} className="mt-1 accent-primary" data-testid="scope-partial" />
                <span>{t.dataOptB}</span>
              </label>
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.fname}
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="rounded-sm h-10" required data-testid="delete-account-name" />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.femail}
                <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="rounded-sm h-10" required data-testid="delete-account-email" />
              </label>
            </div>
            {scope === "partial" && (
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.dataWhich}
                <Textarea value={form.which} onChange={(e) => setForm({ ...form, which: e.target.value })}
                  placeholder={t.dataWhichPh} rows={2} className="rounded-sm" data-testid="delete-account-which" />
              </label>
            )}
            <label className="grid gap-1.5 text-xs text-muted-foreground">{t.fmsg}
              <Textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder={t.fmsgph} rows={3} className="rounded-sm" data-testid="delete-account-message" />
            </label>
            <Button type="submit" className="rounded-sm gap-2" disabled={busy} data-testid="delete-account-submit">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              {scope === "partial" ? t.dataSend : t.send}
            </Button>
            <p className="text-[11px] text-muted-foreground">{dataMode ? "" : t.dataDelay}</p>
          </form>
        )}
        <p className="text-sm text-muted-foreground">
          {dataMode ? t.accountLink : t.dataLink}{" "}
          <Link className="text-primary underline"
            to={dataMode ? (lang === "fr" ? "/suppression-compte" : "/delete-account")
                         : (lang === "fr" ? "/suppression-donnees" : "/data-deletion")}
            data-testid="delete-account-cross-link">
            {dataMode
              ? (lang === "fr" ? "construpilot.fr/suppression-compte" : "construpilot.fr/delete-account")
              : (lang === "fr" ? "construpilot.fr/suppression-donnees" : "construpilot.fr/data-deletion")}
          </Link>
        </p>
      </Section>

      <Section title={t.s3}><Bullets items={t.s3b} /></Section>
      <Section title={t.s4}><Bullets items={t.s4b} /></Section>
      <Section title={t.s5}><p>{t.s5p}</p></Section>
      <Section title={t.s6}>
        <p>
          {t.s6p}{" "}
          <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`} data-testid="delete-account-mailto">{CONTACT_EMAIL}</a>
          {" · "}
          <Link className="text-primary underline" to="/privacy">{lang === "fr" ? "Politique de confidentialité" : "Privacy Policy"}</Link>
          {" · "}
          <Link className="text-primary underline" to="/aide">{lang === "fr" ? "Assistance" : "Support"}</Link>
        </p>
      </Section>
    </div>
  );
}
