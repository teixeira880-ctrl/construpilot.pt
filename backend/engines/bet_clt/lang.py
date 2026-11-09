"""Langue des livrables CLT : chaque texte est rédigé directement en FR, PT, EN et UK (pas de traduction automatique)."""
from __future__ import annotations

LANGS = ("fr", "pt", "en", "uk")
LANG = ["fr"]


def t(fr: str, pt: str, en: str, uk: str) -> str:
    return {"fr": fr, "pt": pt, "en": en, "uk": uk}[LANG[0]]


def cur() -> str:
    return LANG[0]


def num(v: float, n: int = 2) -> str:
    """Nombre au format du livrable (virgule décimale sauf en anglais)."""
    s = f"{v:,.{n}f}" if abs(v) >= 10000 else f"{v:.{n}f}"
    if LANG[0] == "en":
        return s
    return s.replace(",", " ").replace(".", ",")


class use_lang:
    def __init__(self, lang: str):
        self.lang, self.prev = (lang if lang in LANGS else "fr"), None

    def __enter__(self):
        self.prev = LANG[0]
        LANG[0] = self.lang
        return self

    def __exit__(self, *a):
        LANG[0] = self.prev


def pick_lang(country: str, wanted: str | None = None) -> str:
    """Langue par défaut : PT → pt, UA → uk, FR → fr ; une langue demandée explicitement (fr/pt/en/uk) prime."""
    if wanted in LANGS:
        return wanted
    return {"PT": "pt", "UA": "uk", "FR": "fr"}.get((country or "FR").upper(), "en")
