"""Motor de construção tradicional (betão armado + alvenarias) do ConstruPilot — determinístico, sem IA.
Mesma leitura de planta, mesma rastreabilidade e mesmos livrables que os motores LSF e CLT."""
from __future__ import annotations

from .engine import calcular

VERSAO = "1.0"


def estudo(projeto: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    from .quantities import linhas
    from engines.lsf.quantities import precificar
    res = calcular(projeto)
    lin = linhas(res, lang)
    tot = precificar(lin, biblioteca, projeto.get("precos"))
    return {"versao": VERSAO, "resultado": res, "linhas": lin, "totais": tot}


__all__ = ["calcular", "estudo", "VERSAO"]
