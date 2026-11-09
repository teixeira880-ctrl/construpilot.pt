"""Polices des PDF commerciaux : Helvetica par défaut, DejaVu (cyrillique) pour l'ukrainien.

Helvetica (police PDF standard) n'a pas les caractères cyrilliques. Pour un PDF en ukrainien,
le builder ouvre `cyrillic_fonts()` : tout appel `F("Helvetica-Bold")` renvoie alors la
police DejaVu équivalente. Hors de ce contexte, `F()` renvoie le nom tel quel (aucun
changement visuel pour les PDF FR / PT / EN).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_active: ContextVar[bool] = ContextVar("pdf_cyrillic", default=False)
_registered = False

CYR, CYR_BOLD = "CPCyr", "CPCyr-Bold"
_MAP = {"Helvetica": CYR, "Helvetica-Oblique": CYR, "Times-Roman": CYR,
        "Helvetica-Bold": CYR_BOLD, "Helvetica-BoldOblique": CYR_BOLD, "Times-Bold": CYR_BOLD}

CYRILLIC_LANGS = ("uk", "ru", "bg", "sr")


def _register() -> None:
    global _registered
    if _registered:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont(CYR, str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(CYR_BOLD, str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(CYR, normal=CYR, bold=CYR_BOLD, italic=CYR, boldItalic=CYR_BOLD)
    _registered = True


def F(name: str) -> str:
    """Nom de police effectif pour le PDF en cours."""
    return _MAP.get(name, name) if _active.get() else name


def needs_cyrillic(lang: str | None) -> bool:
    return (lang or "").lower()[:2] in CYRILLIC_LANGS


@contextmanager
def cyrillic_fonts(enabled: bool = True):
    if not enabled:
        yield
        return
    _register()
    tok = _active.set(True)
    try:
        yield
    finally:
        _active.reset(tok)


def remap_styles(styles: dict) -> dict:
    """Applique F() à tous les styles (y compris ceux hérités de getSampleStyleSheet)."""
    if _active.get():
        for st in styles.values():
            if hasattr(st, "fontName"):
                st.fontName = F(st.fontName)
    return styles
