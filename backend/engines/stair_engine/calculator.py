"""Orchestrator do Stair Engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from engines.stair_engine.blondel import (
    blondel_check, blondel_optimal, suggest_num_steps,
)
from engines.stair_engine.drawings import build_svgs
from engines.stair_engine.verifications import run_all, summarize


@dataclass
class StairInputs:
    altura_total_m: float   # ex 3.0
    pe_direito_m: float     # ex 2.70
    largura_m: float = 1.0
    num_degraus: Optional[int] = None  # auto
    uso: str = "habitacao"            # habitacao|comercio|evacuacao|publico
    material: str = "betao"            # betao|madeira|metal
    acessibilidade: bool = False
    capacidade: Optional[int] = None  # para evacuacao


def calculate_stair(inp: StairInputs) -> dict:
    altura_cm = float(inp.altura_total_m) * 100.0
    n = inp.num_degraus or suggest_num_steps(altura_cm)
    b = blondel_optimal(altura_cm, n)
    verifs = run_all(
        h_cm=b.h_cm, g_cm=b.g_cm, largura_m=inp.largura_m,
        pe_direito_m=inp.pe_direito_m,
        uso=inp.uso, material=inp.material,
        acessibilidade=inp.acessibilidade,
        capacidade=inp.capacidade,
    )
    svgs = build_svgs(n, b.h_cm, b.g_cm, inp.largura_m)
    sumr = summarize(verifs)

    # Alertas-chave
    alertas: list[str] = []
    if sumr["nao_conforme"]:
        for v in verifs:
            if v["estado"] == "nao_conforme":
                alertas.append(f"[{v['norma']}] {v['mensagem']}")
    if not b.blondel_ok:
        alertas.append(f"Blondel = {b.blondel} cm fora do intervalo 60–64 cm.")
    if b.inclination_deg > 36:
        alertas.append(f"Inclinação {b.inclination_deg}° demasiado íngreme (recomendado ≤ 32°).")

    # Patamares
    patamares = []
    if n > 20:
        patamares.append("Recomendado patamar intermédio (nº degraus > 20).")
    if altura_cm > 300:
        patamares.append("Altura total > 3 m: considerar patamar intermédio (ergonomia + segurança).")

    return {
        "inputs": {
            "altura_total_m": inp.altura_total_m,
            "pe_direito_m": inp.pe_direito_m,
            "largura_m": inp.largura_m,
            "num_degraus": n,
            "uso": inp.uso,
            "material": inp.material,
            "acessibilidade": inp.acessibilidade,
            "capacidade": inp.capacidade,
        },
        "dimensoes": {
            "num_degraus": n,
            "altura_degrau_cm": b.h_cm,
            "profundidade_cobertor_cm": b.g_cm,
            "altura_total_cm": round(altura_cm, 1),
            "largura_cm": round(inp.largura_m * 100, 1),
            "blondel": b.blondel,
            "inclinacao_graus": b.inclination_deg,
            "projecao_horizontal_m": round(n * b.g_cm / 100, 2),
            "comprimento_rampante_m": round(((n * b.h_cm) ** 2 + (n * b.g_cm) ** 2) ** 0.5 / 100, 2),
        },
        "conforto_score": b.comfort_score,
        "verificacoes": verifs,
        "resumo_verificacoes": sumr,
        "alertas": alertas,
        "patamares": patamares,
        "svgs": svgs,
    }


def check_user_dimensions(h_cm: float, g_cm: float) -> dict:
    r = blondel_check(h_cm, g_cm)
    return {
        "h_cm": r.h_cm, "g_cm": r.g_cm, "blondel": r.blondel,
        "inclination_deg": r.inclination_deg,
        "blondel_ok": r.blondel_ok, "comfort_score": r.comfort_score,
    }
