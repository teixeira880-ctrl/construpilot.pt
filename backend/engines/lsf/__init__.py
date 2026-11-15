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
from .verificacao import verificar

VERSAO = "1.0"


def estudo(projeto: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    """Cálculo completo + mapa de quantidades com preços (biblioteca da empresa / projeto)."""
    res = calcular(projeto)
    res["barraComercial"] = projeto.get("barraComercial", 6000)
    res["verificacao"] = verificacao_segura(projeto, res)
    lin = linhas(res, lang)
    tot = precificar(lin, biblioteca, projeto.get("precos"))
    return {"versao": VERSAO, "resultado": res, "linhas": lin, "totais": tot}


def verificacao_segura(projeto: dict, res: dict) -> dict:
    """Verificação estrutural EN 1993-1-3 (engines.lsf.verificacao); um projeto que ela não sabe ler não impede as quantidades."""
    try:
        return verificar(projeto, res)
    except Exception as exc:  # noqa: BLE001
        return {"erro": f"Verificação estrutural não calculada: {exc}", "verificacoes": [], "resumo": None, "avisos": []}


__all__ = ["calcular", "estudo", "linhas", "precificar", "verificar", "verificacao_segura", "VERSAO"]
