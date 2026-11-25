"""Motor CLT (madeira lamelada-colada cruzada) do ConstruPilot — determinístico, sem IA nos cálculos.

    from engines.clt import estudo
    st = estudo(projeto)        # projeto CLT (defaults.exemplo()) ou adapter.from_takeoff(plan) / from_mep_input(data)

Mesma leitura de planta, mesma rastreabilidade e mesmos livrables que o motor LSF (engines.lsf).
"""
from __future__ import annotations

from .engine import calcular

VERSAO = "1.0"


def estudo(projeto: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    from .quantities import linhas, precificar
    res = calcular(projeto)
    lin = linhas(res, lang)
    tot = precificar(lin, biblioteca, projeto.get("precos"))
    return {"versao": VERSAO, "resultado": res, "linhas": lin, "totais": tot}


__all__ = ["calcular", "estudo", "VERSAO"]
