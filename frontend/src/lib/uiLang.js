// Língua da interface fora do React (pedidos à API, voz, datas).
// Fonte única: localStorage "construpilot_lang", escrita pelo I18nProvider.

export const UI_LANGS = ["pt", "en", "fr", "uk"];

// Locale BCP-47 de cada língua da interface (datas, voz, Intl).
export const UI_LOCALES = { pt: "pt-PT", en: "en-GB", fr: "fr-FR", uk: "uk-UA" };

export const UI_LANG_LABELS = { pt: "Português", en: "English", fr: "Français", uk: "Українська" };

/** Língua atual da interface ("pt" por defeito). */
export function currentUiLang() {
  try {
    const l = localStorage.getItem("construpilot_lang");
    if (l && UI_LANGS.includes(l)) return l;
  } catch { /* armazenamento indisponível */ }
  return "pt";
}

/** Locale BCP-47 da língua atual (ex.: reconhecimento e síntese de voz). */
export function currentUiLocale() {
  return UI_LOCALES[currentUiLang()] || "pt-PT";
}
