import { createContext, useContext, useEffect, useState } from "react";

const I18nContext = createContext(null);

const TRANSLATIONS = {
  fr: {
    "nav.dashboard": "Tableau de bord",
    "nav.team": "Équipe",
    "nav.tracking": "Suivi devis",
    "nav.referral": "Parrainer",
    "nav.login": "Connexion",
    "nav.logout": "Déconnexion",
    "nav.pro": "Espace pro",
    "common.loading": "Chargement…",
    "common.cancel": "Annuler",
    "common.save": "Enregistrer",
    "common.delete": "Supprimer",
    "common.close": "Fermer",
    "common.refresh": "Actualiser",
    "common.confirm": "Confirmer",
    "common.download": "Télécharger",
    "common.language": "Langue",
    "quote.dashboard.title": "Où en sont vos devis envoyés ?",
    "quote.dashboard.subtitle": "Toutes les propositions envoyées à vos clients, organisées par état d'avancement. Relancez au bon moment grâce au suivi d'ouverture et de signature.",
    "quote.kpi.sent": "Envoyés",
    "quote.kpi.opened": "Ouverts",
    "quote.kpi.signed": "Signés",
    "quote.kpi.pipeline": "Pipeline",
    "quote.col.notopened": "Non ouverts",
    "quote.col.opened": "Ouverts (à relancer)",
    "quote.col.signed": "Signés",
    "team.title": "Votre équipe",
    "team.create": "Créer une organisation",
    "team.join": "Rejoindre une équipe",
    "team.invite": "Inviter",
    "team.leave": "Quitter",
    "team.transfer": "Transférer",
  },
  en: {
    "nav.dashboard": "Dashboard",
    "nav.team": "Team",
    "nav.tracking": "Quote tracking",
    "nav.referral": "Refer",
    "nav.login": "Login",
    "nav.logout": "Logout",
    "nav.pro": "Pro space",
    "common.loading": "Loading…",
    "common.cancel": "Cancel",
    "common.save": "Save",
    "common.delete": "Delete",
    "common.close": "Close",
    "common.refresh": "Refresh",
    "common.confirm": "Confirm",
    "common.download": "Download",
    "common.language": "Language",
    "quote.dashboard.title": "Where do your sent quotes stand?",
    "quote.dashboard.subtitle": "All the proposals you sent to your clients, organised by stage. Follow up at the right time thanks to open and signature tracking.",
    "quote.kpi.sent": "Sent",
    "quote.kpi.opened": "Opened",
    "quote.kpi.signed": "Signed",
    "quote.kpi.pipeline": "Pipeline",
    "quote.col.notopened": "Not opened",
    "quote.col.opened": "Opened (follow up)",
    "quote.col.signed": "Signed",
    "team.title": "Your team",
    "team.create": "Create an organisation",
    "team.join": "Join a team",
    "team.invite": "Invite",
    "team.leave": "Leave",
    "team.transfer": "Transfer",
  },
};

const STORAGE_KEY = "construpilot_lang";

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(
    () => localStorage.getItem(STORAGE_KEY) || "fr"
  );

  const setLang = (l) => {
    setLangState(l);
    localStorage.setItem(STORAGE_KEY, l);
    document.documentElement.lang = l;
  };

  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const t = (key, fallback = "") =>
    TRANSLATIONS[lang]?.[key] ?? TRANSLATIONS.fr[key] ?? fallback ?? key;

  return (
    <I18nContext.Provider value={{ lang, setLang, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}

export function LangToggle() {
  const { lang, setLang } = useI18n();
  return (
    <button
      onClick={() => setLang(lang === "fr" ? "en" : "fr")}
      data-testid="lang-toggle"
      className="rounded-sm border border-border px-2 py-1 text-[10px] font-extrabold uppercase tracking-widest hover:bg-primary hover:text-white hover:border-primary transition"
      title={lang === "fr" ? "Switch to English" : "Passer en français"}
    >
      {lang}
    </button>
  );
}
