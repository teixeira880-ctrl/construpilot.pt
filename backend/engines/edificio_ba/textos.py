"""Textos bilingues (PT-PT / FR) e formatação numérica dos livrables.

Cada texto é escrito diretamente nas duas línguas (sem tradução automática) : t(S, "português", "français").
"""
from __future__ import annotations


def t(S, pt: str, fr: str) -> str:
    """Texto na língua do estudo (S.lang = "pt" ou "fr")."""
    return fr if getattr(S, "lang", "pt") == "fr" else pt


def fmt(v, n: int = 2) -> str:
    """1234.5 → « 1 234,50 » (espaço fino como separador de milhares, vírgula decimal — PT e FR)."""
    if v is None:
        return "—"
    s = f"{float(v):,.{n}f}"
    return s.replace(",", " ").replace(".", ",")


def fint(v) -> str:
    return fmt(v, 0)


def level_name(S, k: int, n_floors: int, basement: bool) -> str:
    """Nome do nível k (−1 = cave, 0 … n−1 = pisos, n = cobertura)."""
    if k == -1:
        return t(S, "Piso -1", "Sous-sol")
    if k == n_floors:
        return t(S, "Cobertura", "Toiture-terrasse")
    if S.lang == "fr":
        return "RDC" if k == 0 else f"R+{k}"
    return f"Piso {k}"
