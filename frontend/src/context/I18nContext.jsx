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
  es: {
    "nav.dashboard": "Panel",
    "nav.team": "Equipo",
    "nav.tracking": "Seguimiento presupuestos",
    "nav.referral": "Recomendar",
    "nav.login": "Iniciar sesión",
    "nav.logout": "Cerrar sesión",
    "nav.pro": "Espacio pro",
    "common.loading": "Cargando…",
    "common.cancel": "Cancelar",
    "common.save": "Guardar",
    "common.delete": "Eliminar",
    "common.close": "Cerrar",
    "common.refresh": "Actualizar",
    "common.confirm": "Confirmar",
    "common.download": "Descargar",
    "common.language": "Idioma",
    "quote.dashboard.title": "¿En qué punto están sus presupuestos enviados?",
    "quote.dashboard.subtitle": "Todas las propuestas enviadas a sus clientes, organizadas por estado. Haga seguimiento en el momento adecuado gracias al rastreo de apertura y firma.",
    "quote.kpi.sent": "Enviados",
    "quote.kpi.opened": "Abiertos",
    "quote.kpi.signed": "Firmados",
    "quote.kpi.pipeline": "Cartera",
    "quote.col.notopened": "No abiertos",
    "quote.col.opened": "Abiertos (recordar)",
    "quote.col.signed": "Firmados",
    "team.title": "Su equipo",
    "team.create": "Crear una organización",
    "team.join": "Unirse a un equipo",
    "team.invite": "Invitar",
    "team.leave": "Salir",
    "team.transfer": "Transferir",
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
  const LANGS = [
    { code: "fr", label: "FR", full: "Français" },
    { code: "en", label: "EN", full: "English" },
    { code: "es", label: "ES", full: "Español" },
  ];
  return (
    <div className="relative inline-block" data-testid="lang-toggle-wrapper">
      <select
        value={lang}
        onChange={(e) => setLang(e.target.value)}
        data-testid="lang-toggle"
        aria-label="Language"
        className="rounded-sm border border-border bg-transparent px-2 py-1 text-[10px] font-extrabold uppercase tracking-widest hover:bg-primary hover:text-white hover:border-primary transition cursor-pointer appearance-none pr-6"
        style={{ backgroundImage: "url(\"data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' width='8' height='6' viewBox='0 0 8 6' fill='none'%3e%3cpath d='M1 1l3 3 3-3' stroke='currentColor' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3e%3c/svg%3e\")",
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "right 6px center" }}
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code} className="bg-background text-foreground">
            {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}
