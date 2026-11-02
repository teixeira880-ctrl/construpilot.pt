const DECK_BASE = `${process.env.REACT_APP_BACKEND_URL}/api/investors/pitch-deck`;

export const DECK_LANGS = [
  { code: "pt", label: "PT" },
  { code: "fr", label: "FR" },
  { code: "en", label: "EN" },
];

export const deckFileUrl = (format = "pdf", lang = "pt") => `${DECK_BASE}.${format}?lang=${lang}`;
export const deckSlideUrl = (page, version, lang = "pt") => `${DECK_BASE}/slides/${page}.webp?lang=${lang}&v=${version}`;