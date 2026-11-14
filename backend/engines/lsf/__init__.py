"""Motor LSF (Light Steel Framing) do ConstruPilot — determinístico, sem IA nos cálculos.

    from engines.lsf import estudo
    st = estudo(projeto)                         # projeto LSF (defaults.exemplo()) ou adapter.from_takeoff(plan) / from_mep_input(data)
    st["resultado"], st["linhas"], st["totais"]

    from engines.lsf.pdf import dossier ; from engines.lsf.xlsx import xlsx ; from engines.lsf.viewer import html_viewer
    from engines.lsf.render import render        # render fotorrealista (Mitsuba)

Ver README.md.
"""
from __future__ import annotations

from .engine import calcular
from .quantities import linhas, precificar

VERSAO = "1.0"


def estudo(projeto: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    """Cálculo completo + mapa de quantidades com preços (biblioteca da empresa / projeto)."""
    res = calcular(projeto)
    res["barraComercial"] = projeto.get("barraComercial", 6000)
    lin = linhas(res, lang)
    tot = precificar(lin, biblioteca, projeto.get("precos"))
    return {"versao": VERSAO, "resultado": res, "linhas": lin, "totais": tot}


__all__ = ["calcular", "estudo", "linhas", "precificar", "VERSAO"]
