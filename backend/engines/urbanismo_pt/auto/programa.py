"""Programa da habitação: compartimentos e áreas a partir de um pedido simples (tipologia, pisos, garagem).

As áreas de projeto são confortáveis (prática corrente de moradias unifamiliares) e verificadas contra os mínimos do RGEU.
Nada aqui é «inventado» sem rasto: cada valor tem origem (`regra`) e o quadro final é recalculado pelos motores do processo.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Mínimos do RGEU por compartimento (m²) — quarto casal / duplo / simples, sala e cozinha por tipologia.
RGEU_MIN = {
    "fonte": "RGEU (DL 38 382/51), art.º 66.º — áreas mínimas dos compartimentos e art.º 67.º — área bruta mínima do fogo",
    "status": "a_confirmar",
    "quarto": [10.5, 9.0, 9.0, 6.5, 6.5],
    "sala": {0: 10.0, 1: 10.0, 2: 12.0, 3: 12.0, 4: 12.0, 5: 16.0, 6: 16.0},
    "cozinha": 6.0,
    "area_bruta": {0: 35.0, 1: 52.0, 2: 72.0, 3: 91.0, 4: 105.0, 5: 122.0, 6: 134.0},
}

# Áreas úteis de projeto (m²): confortáveis, acima dos mínimos.
CONFORTO = {"sala": {1: 24.0, 2: 28.0, 3: 32.0, 4: 36.0, 5: 40.0, 6: 44.0},
            "cozinha": {1: 9.0, 2: 11.0, 3: 13.0, 4: 14.0, 5: 15.0, 6: 16.0},
            "suite": 15.0, "wc_suite": 4.5, "quarto": 12.0, "wc": 4.5, "wc_social": 2.6, "lavandaria": 4.0,
            "entrada": 6.0, "escada": 8.0, "escritorio": 9.0}
COEF_BRUTA = 1.20            # área bruta ≈ área útil × 1,20 (paredes exteriores e interiores)
CIRCULACAO = 0.12            # corredores e átrios (fração da área útil dos compartimentos)
GARAGEM_LUGAR = (3.2, 6.0)   # largura × profundidade por lugar coberto (m)


def _int(v, d, lo, hi):
    try:
        x = int(round(float(v)))
    except (TypeError, ValueError):
        x = d
    return max(lo, min(hi, x))


ESCALAVEIS = {"entrada", "sala", "cozinha", "quarto", "wc", "lavandaria", "escritorio"}   # escada e I.S. social ficam fixas


def tipologia_para_area(area_m2: float, n_pisos: int = 1) -> int:
    """Maior tipologia (T1…T5) cuja área de conforto cabe em 90 % da área pedida: os compartimentos ficam um pouco
    maiores que o conforto, nunca apertados (200 m² térrea → T4; 200 m² em 2 pisos → T3)."""
    cabe = [t for t in range(1, 6) if _programa(t, n_pisos, False, 0)["area_bruta_total_m2"] <= area_m2 * 0.9]
    return max(cabe) if cabe else 1


def programa(tipologia: Any = 3, pisos: Any = None, garagem: Any = True, lugares: Any = 2,
             escritorio: bool = False, area_alvo_m2: Optional[float] = None) -> Dict[str, Any]:
    """Lista de compartimentos por piso, com área útil de projeto e mínimo regulamentar.

    `area_alvo_m2` (área bruta da habitação pedida, sem garagem): as áreas de conforto dos compartimentos são escaladas
    pelo mesmo fator até a área bruta total bater com o pedido — nunca abaixo do mínimo do RGEU de cada compartimento."""
    base = _programa(tipologia, pisos, garagem, lugares, escritorio)
    if not area_alvo_m2 or area_alvo_m2 <= 0:
        return base
    alvo = float(area_alvo_m2)
    lo, hi = 0.3, 3.0
    out = base
    for _ in range(40):                       # bissecção no fator de escala (a área é monótona no fator)
        k = (lo + hi) / 2
        out = _programa(tipologia, pisos, garagem, lugares, escritorio, escala=k)
        if out["area_bruta_total_m2"] < alvo:
            lo = k
        else:
            hi = k
    out = _programa(tipologia, pisos, garagem, lugares, escritorio, escala=hi)
    out["area_alvo_m2"] = round(alvo, 1)
    out["escala_areas"] = round(hi, 3)
    out["limitado_pelo_rgeu"] = out["area_bruta_total_m2"] > alvo * 1.02
    return out


def _programa(tipologia: Any = 3, pisos: Any = None, garagem: Any = True, lugares: Any = 2,
              escritorio: bool = False, escala: float = 1.0) -> Dict[str, Any]:
    t = _int(str(tipologia).upper().lstrip("T") if tipologia is not None else 3, 3, 0, 6)
    n_pisos = _int(pisos, 2, 1, 2) if pisos not in (None, "") else 2
    quartos = max(t, 1) if t else 0
    rooms: List[Dict[str, Any]] = []

    def add(nome, tipo, area, piso, fila, minimo=None):
        if tipo in ESCALAVEIS and escala != 1.0:
            area = max(area * escala, minimo or 0.0, 2.0)
        rooms.append({"nome": nome, "tipo": tipo, "area_projeto_m2": round(area, 1), "piso": piso, "fila": fila,
                      "minimo_m2": minimo})

    dia, noite = 0, (1 if n_pisos == 2 else 0)
    add("Entrada / átrio", "entrada", CONFORTO["entrada"], dia, "servico")
    add("Sala de estar e jantar", "sala", CONFORTO["sala"].get(max(t, 1), 32.0), dia, "sol", RGEU_MIN["sala"].get(t, 12.0))
    add("Cozinha", "cozinha", CONFORTO["cozinha"].get(max(t, 1), 13.0), dia, "servico", RGEU_MIN["cozinha"])
    add("Lavandaria", "lavandaria", CONFORTO["lavandaria"], dia, "servico")
    if n_pisos == 2:
        add("I.S. social", "wc_social", CONFORTO["wc_social"], dia, "servico")
        add("Escada", "escada", CONFORTO["escada"], dia, "servico")
        add("Escada", "escada", CONFORTO["escada"], noite, "servico")
    if escritorio:
        add("Escritório", "escritorio", CONFORTO["escritorio"], dia, "sol")
    for i in range(quartos):
        minimo = RGEU_MIN["quarto"][min(i, len(RGEU_MIN["quarto"]) - 1)]
        if i == 0:
            add("Suite", "quarto", CONFORTO["suite"], noite, "sol", minimo)
            add("I.S. da suite", "wc", CONFORTO["wc_suite"], noite, "servico")
        else:
            add(f"Quarto {i + 1}", "quarto", CONFORTO["quarto"], noite, "sol" if i < 3 else "servico", minimo)
    if quartos >= 2:
        add("Instalação sanitária", "wc", CONFORTO["wc"], noite, "servico")

    por_piso = {}
    for p in range(n_pisos):
        util = sum(r["area_projeto_m2"] for r in rooms if r["piso"] == p)
        util_total = util * (1 + CIRCULACAO)
        por_piso[p] = {"area_util_m2": round(util_total, 1), "area_bruta_m2": round(util_total * COEF_BRUTA, 1)}
        rooms.append({"nome": "Circulação", "tipo": "circulacao", "area_projeto_m2": round(util * CIRCULACAO, 1), "piso": p,
                      "fila": "servico", "minimo_m2": None})
    # as plantas usam a mesma implantação em todos os pisos: a área bruta por piso é a do piso maior
    bruta_piso = max(v["area_bruta_m2"] for v in por_piso.values())
    nl = _int(lugares, 2, 0, 3)
    tem_garagem = bool(garagem) and nl > 0
    gar = None
    if tem_garagem:
        gar = {"lugares": nl, "l_m": round(GARAGEM_LUGAR[0] * nl + 0.3, 2), "w_m": GARAGEM_LUGAR[1] + 0.3, "h_m": 3.0}
    return {"tipologia": f"T{t}", "t": t, "n_pisos": n_pisos, "compartimentos": rooms, "por_piso": por_piso,
            "area_bruta_por_piso_m2": round(bruta_piso, 1), "area_bruta_total_m2": round(bruta_piso * n_pisos, 1),
            "minimo_area_bruta_m2": RGEU_MIN["area_bruta"].get(t), "garagem": gar, "lugares": nl,
            "fonte_minimos": RGEU_MIN["fonte"], "status_minimos": RGEU_MIN["status"]}
