"""Langue des livrables : chaque texte est écrit directement en français ET en portugais (pas de traduction automatique)."""
from __future__ import annotations

LANG = ["fr"]


def _(fr: str, pt: str) -> str:
    return pt if LANG[0] == "pt" else fr


def num(v: float, n: int = 2) -> str:
    """Nombre au format du livrable (virgule décimale en FR comme en PT)."""
    return f"{v:.{n}f}".replace(".", ",")


class use_lang:
    """with use_lang("pt"): …"""

    def __init__(self, lang: str):
        self.lang, self.prev = ("pt" if lang == "pt" else "fr"), None

    def __enter__(self):
        self.prev = LANG[0]
        LANG[0] = self.lang
        return self

    def __exit__(self, *a):
        LANG[0] = self.prev
