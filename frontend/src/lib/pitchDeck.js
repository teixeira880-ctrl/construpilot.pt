const DECK_BASE = `${process.env.REACT_APP_BACKEND_URL}/api/investors/pitch-deck`;

export const deckFileUrl = (format = "pdf") => `${DECK_BASE}.${format}`;
export const deckSlideUrl = (page, version) => `${DECK_BASE}/slides/${page}.webp?v=${version}`;