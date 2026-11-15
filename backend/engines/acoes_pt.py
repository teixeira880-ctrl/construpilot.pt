"""Ações em edifícios em Portugal (Eurocódigos com o Anexo Nacional português), sem dependência de nenhum motor.

Usado pelos motores estruturais gerais (LSF, …). O motor CLT tem as suas próprias normas (engines/bet_clt/norms.py):
o CLT é uma aplicação à parte e não deve servir de base aos outros motores.

  - sobrecargas de utilização: NP EN 1991-1-1, Quadro 6.2 (valores do AN PT)
  - neve: NP EN 1991-1-3, zonas Z1–Z3, sk = Cz·[1 + (H/500)²] para H ≥ 200 m (abaixo de 200 m sk = 0)
  - vento: NP EN 1991-1-4, zonas A/B (vb,0 = 27 / 30 m/s), categoria de terreno III (z0 = 0,3 m), co = 1

Mesma interface que engines.bet_clt.norms (snow / wind / q_use com o argumento país), restrita a «PT»:
os valores coincidem com os desse módulo para Portugal (verificado em tests/test_acoes_pt.py).
"""
from __future__ import annotations

import math

# NP EN 1991-1-1 (AN PT), q_k em kN/m²
Q_USE = {"habitation": 2.0, "bureaux": 3.0, "commerce": 4.0, "scolaire": 3.0, "public": 4.0, "stationnement": 2.5,
         "technique": 5.0, "toiture": 0.4, "terrasse": 2.0}
# NP EN 1991-1-3: coeficiente de zona Cz (kN/m²)
SNOW_CZ = {"Z1": 0.30, "Z2": 0.20, "Z3": 0.10}
# NP EN 1991-1-4: valor básico da velocidade de referência vb,0 (m/s)
VB0 = {"A": 27.0, "B": 30.0}


def _pt(country: str) -> None:
    if (country or "PT").upper() != "PT":
        raise ValueError("engines.acoes_pt só tem os valores do Anexo Nacional português")


def q_use(country: str, use: str) -> float:
    _pt(country)
    return Q_USE.get(use, Q_USE["habitation"])


def snow(raw: dict, country: str, warns: list) -> dict:
    """Neve sobre cobertura plana: s = μ1·sk com μ1 = 0,8 (Ce = Ct = 1)."""
    _pt(country)
    pr = raw.get("project") or {}
    alt = float(pr.get("altitude_m") or 0)
    z = str(pr.get("snow_zone") or "Z2")
    if "snow_zone" not in pr:
        warns.append(("SNOW", "Zona de neve não indicada: Z2 admitida."))
    sk = SNOW_CZ.get(z, 0.20) * (1 + (alt / 500) ** 2) if alt >= 200 else 0.0
    mu = 0.8
    return {"sk": round(sk, 3), "mu": mu, "s": round(mu * sk, 3), "source": f"NP EN 1991-1-3 {z}, alt. {alt:.0f} m"}


def wind(raw: dict, country: str, H: float, warns: list) -> dict:
    """Pressão dinâmica de pico qp(H), categoria de terreno III (z0 = 0,3 m, zmin = 5 m)."""
    _pt(country)
    pr = raw.get("project") or {}
    zona = str(pr.get("wind_zone") or "A")
    vb = VB0.get(zona, 27.0)
    z0, zmin = 0.3, 5.0
    z = max(H, zmin)
    kr = 0.19 * (z0 / 0.05) ** 0.07
    cr = kr * math.log(z / z0)
    iv = 1 / math.log(z / z0)
    qb = 0.5 * 1.25 * vb ** 2 / 1000
    qp = (1 + 7 * iv) * cr ** 2 * qb
    return {"vb": round(vb, 1), "qb": round(qb, 3), "qp": round(qp, 3), "source": f"NP EN 1991-1-4 zona {zona}"}
