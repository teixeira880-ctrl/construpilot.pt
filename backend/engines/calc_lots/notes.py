"""Blocos comuns das notas de cálculo (versão PT)."""
from __future__ import annotations

from reportlab.lib.units import mm

from . import rendu

W = mm


def _f(x, n=0):
    return f"{x:,.{n}f}".replace(",", " ").replace(".", ",") if n else f"{x:,.0f}".replace(",", " ")


def pdf(titre, sous_titre, blocs, hypotheses) -> tuple[bytes, bytes]:
    b = list(blocs) + [("h2", "Hipóteses / a validar"), ("hyp", hypotheses or ["nenhuma"])]
    data = rendu.build_pdf(titre, sous_titre, b)
    return data, rendu.first_page_png(data)
