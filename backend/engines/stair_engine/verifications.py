"""Verificações normativas PT para escadas.

Devolve lista de `Verification(norma, estado, mensagem, referencia)` onde:
  - estado ∈ {"conforme", "atencao", "nao_conforme"}
  - referencia: nome do artigo ou cláusula
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Status = Literal["conforme", "atencao", "nao_conforme"]


@dataclass
class Verification:
    norma: str
    estado: Status
    mensagem: str
    referencia: str

    def dict(self) -> dict:
        return asdict(self)


def _check_rgeu(h: float, g: float, largura: float, pe_direito: float, uso: str) -> list[Verification]:
    out: list[Verification] = []
    # Art. 42º: altura máxima do espelho
    if uso in ("comercio", "evacuacao", "publico"):
        h_max = 17.5
    else:
        h_max = 19.0  # habitação (prática RGEU + REH)
    if h > h_max:
        out.append(Verification("RGEU", "nao_conforme",
            f"Altura do espelho {h:.1f} cm excede o máximo {h_max:.1f} cm para uso '{uso}'.",
            "Art. 42º"))
    elif h > h_max - 1:
        out.append(Verification("RGEU", "atencao",
            f"Altura do espelho {h:.1f} cm perto do limite ({h_max:.1f} cm).",
            "Art. 42º"))
    else:
        out.append(Verification("RGEU", "conforme",
            f"Altura do espelho {h:.1f} cm conforme (máx {h_max:.1f} cm).",
            "Art. 42º"))

    # Art. 43º: profundidade mínima do cobertor
    g_min = 25.0 if uso == "habitacao" else 28.0
    if g < g_min:
        out.append(Verification("RGEU", "nao_conforme",
            f"Profundidade do cobertor {g:.1f} cm abaixo do mínimo {g_min:.1f} cm.",
            "Art. 43º"))
    else:
        out.append(Verification("RGEU", "conforme",
            f"Profundidade do cobertor {g:.1f} cm conforme (mín {g_min:.1f} cm).",
            "Art. 43º"))

    # Art. 45º: pé-direito mínimo
    pd_min = 2.0  # m (sob escada em habitação)
    if pe_direito < pd_min:
        out.append(Verification("RGEU", "nao_conforme",
            f"Pé-direito {pe_direito:.2f} m abaixo do mínimo {pd_min:.2f} m sob a escada.",
            "Art. 45º"))
    else:
        out.append(Verification("RGEU", "conforme",
            f"Pé-direito {pe_direito:.2f} m conforme (mín {pd_min:.2f} m).",
            "Art. 45º"))
    return out


def _check_reh(largura: float, uso: str) -> list[Verification]:
    out: list[Verification] = []
    # REH + RGEU art. 44º: largura mínima
    if uso == "habitacao":
        lmin = 1.00
    elif uso in ("comercio", "publico"):
        lmin = 1.20
    else:  # evacuacao
        lmin = 1.20
    if largura < lmin:
        out.append(Verification("REH", "nao_conforme",
            f"Largura da escada {largura:.2f} m abaixo do mínimo {lmin:.2f} m para '{uso}'.",
            "REH + RGEU art. 44º"))
    elif largura < lmin + 0.1:
        out.append(Verification("REH", "atencao",
            f"Largura {largura:.2f} m próxima do mínimo. Recomendado {lmin + 0.2:.2f} m.",
            "REH"))
    else:
        out.append(Verification("REH", "conforme",
            f"Largura {largura:.2f} m conforme (mín {lmin:.2f} m).",
            "REH + RGEU art. 44º"))
    return out


def _check_rscie(largura: float, uso: str, capacidade: int | None) -> list[Verification]:
    out: list[Verification] = []
    if uso != "evacuacao":
        return out
    # Portaria 1532/2008 art. 51º: 1 UP = 0.60 m, mín 2 UP = 1.20 m
    # Capacidade: 100 pessoas / 1 UP
    cap = capacidade or 50
    up_necessarias = max(2, (cap + 99) // 100)
    largura_min = up_necessarias * 0.60
    if largura < largura_min:
        out.append(Verification("RSCIE", "nao_conforme",
            f"Via de evacuação {largura:.2f} m abaixo do mínimo {largura_min:.2f} m "
            f"({up_necessarias} UP para {cap} pessoas).",
            "Portaria 1532/2008 art. 51º"))
    else:
        out.append(Verification("RSCIE", "conforme",
            f"Via de evacuação {largura:.2f} m conforme ({up_necessarias} UP · {cap} pessoas).",
            "Portaria 1532/2008 art. 51º"))
    # Protecção escada (DL 220/2008) — recomendação
    out.append(Verification("RSCIE", "atencao",
        "Verifique protecção/compartimentação da escada (parede CF 60/90 min, portas E 30).",
        "DL 220/2008 + Portaria 1532/2008"))
    return out


def _check_en_1992(h: float, g: float, largura: float, material: str) -> list[Verification]:
    out: list[Verification] = []
    if material != "betao":
        return out
    # EN 1992-1-1 §9.10 — espessura mínima laje escada e armadura
    # Espessura mínima recomendada: L/25 onde L é vão livre (aqui ignoramos cálculo detalhado,
    # devolvemos indicação prática)
    out.append(Verification("EN 1992", "atencao",
        "Betão armado: espessura mínima da laje da escada ≥ L/25 "
        "(L = projeção horizontal). Armadura mín: As ≥ 0,13% × A_c (As_min, §9.3.1.1).",
        "EN 1992-1-1 §9.10 + §9.3.1.1"))
    # Betão recomendado
    out.append(Verification("EN 1992", "atencao",
        "Classe mínima recomendada C25/30. Recobrimento ≥ 20 mm (XC1 interior).",
        "EN 1992-1-1 §4.4.1"))
    return out


def _check_en_1991(largura: float, uso: str) -> list[Verification]:
    # EN 1991-1-1 Anexo A — ações
    if uso == "habitacao":
        q = 2.0
    elif uso in ("publico", "evacuacao"):
        q = 4.0
    else:
        q = 3.0
    return [Verification("EN 1991", "conforme",
        f"Sobrecarga de utilização q = {q:.1f} kN/m² (categoria '{uso}', Anexo A).",
        "EN 1991-1-1 Anexo A tabela 6.2")]


def _check_dl_163(h: float, g: float, largura: float, acessibilidade: bool) -> list[Verification]:
    if not acessibilidade:
        return []
    out: list[Verification] = []
    # DL 163/2006 anexo normas técnicas secção 2.4
    # Degrau: h ≤ 16 cm, g ≥ 28 cm
    if h > 16.0:
        out.append(Verification("DL 163/2006", "nao_conforme",
            f"Acessibilidade: altura {h:.1f} cm > 16 cm.",
            "DL 163/2006 secção 2.4.1"))
    else:
        out.append(Verification("DL 163/2006", "conforme",
            f"Acessibilidade: altura {h:.1f} cm ≤ 16 cm.",
            "DL 163/2006 secção 2.4.1"))
    if g < 28.0:
        out.append(Verification("DL 163/2006", "nao_conforme",
            f"Acessibilidade: cobertor {g:.1f} cm < 28 cm.",
            "DL 163/2006 secção 2.4.1"))
    else:
        out.append(Verification("DL 163/2006", "conforme",
            f"Acessibilidade: cobertor {g:.1f} cm ≥ 28 cm.",
            "DL 163/2006 secção 2.4.1"))
    if largura < 1.20:
        out.append(Verification("DL 163/2006", "nao_conforme",
            f"Acessibilidade: largura {largura:.2f} m < 1.20 m.",
            "DL 163/2006 secção 2.4.2"))
    # Corrimão duplo
    out.append(Verification("DL 163/2006", "atencao",
        "Corrimão duplo obrigatório (0.75 m + 0.90 m) com prolongamento 0.30 m nas extremidades.",
        "DL 163/2006 secção 2.4.3"))
    return out


def run_all(
    *,
    h_cm: float, g_cm: float, largura_m: float, pe_direito_m: float,
    uso: str, material: str, acessibilidade: bool = False,
    capacidade: int | None = None,
) -> list[dict]:
    verifs: list[Verification] = []
    verifs += _check_rgeu(h_cm, g_cm, largura_m, pe_direito_m, uso)
    verifs += _check_reh(largura_m, uso)
    verifs += _check_rscie(largura_m, uso, capacidade)
    verifs += _check_en_1992(h_cm, g_cm, largura_m, material)
    verifs += _check_en_1991(largura_m, uso)
    verifs += _check_dl_163(h_cm, g_cm, largura_m, acessibilidade)
    return [v.dict() for v in verifs]


def summarize(verifs: list[dict]) -> dict:
    conforme = sum(1 for v in verifs if v["estado"] == "conforme")
    atencao = sum(1 for v in verifs if v["estado"] == "atencao")
    nc = sum(1 for v in verifs if v["estado"] == "nao_conforme")
    overall: Status = "nao_conforme" if nc else ("atencao" if atencao else "conforme")
    return {"conforme": conforme, "atencao": atencao, "nao_conforme": nc,
            "total": len(verifs), "overall": overall}
