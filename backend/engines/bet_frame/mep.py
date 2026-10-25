"""Réseaux collectifs : colonnes montantes eau froide / eau chaude, chutes d'eaux usées, colonne électrique.

- Eau : débits de base par appareil, débit de pointe par la courbe de simultanéité des bâtiments d'habitation
  Q = a·(ΣQR)^b − c (a = 1,48 ; b = 0,19 ; c = 0,94 — EN 806-3 / DIN 1988-300) ; diamètre pour v ≤ 1,5 m/s
  (colonnes) et 2,0 m/s (branchements). À confirmer : DTU 60.11 (FR) / DR 23/95 (PT).
- Eaux usées : unités de décharge DU (EN 12056-2, système I), Qww = K·√ΣDU (K = 0,5 habitation) ;
  capacité des chutes à ventilation primaire (tableau 11) ; WC → Ø100 mini.
- Électricité : puissance par logement selon la typologie, coefficients de simultanéité de la colonne
  (NF C 14-100 / RTIEBT 803), intensité triphasée 400 V, section cuivre.
"""
from __future__ import annotations

import math

from .lang import _
from .model import Frame

# appareil → (QR l/s EF, QR l/s ECS, DU l/s)
FIXTURES = {
    "wc": (0.13, 0.0, 2.0), "lavatorio": (0.07, 0.07, 0.5), "duche": (0.15, 0.15, 0.6), "banheira": (0.15, 0.15, 0.8),
    "bide": (0.07, 0.07, 0.5), "pia": (0.07, 0.07, 0.8), "mlr": (0.15, 0.0, 0.8), "mll": (0.07, 0.0, 0.8),
    "torneira": (0.15, 0.0, 0.0), "urinol": (0.15, 0.0, 0.5),
}
FIX_ALIASES = {"lavabo": "lavatorio", "vasque": "lavatorio", "douche": "duche", "baignoire": "banheira", "bidet": "bide",
               "evier": "pia", "évier": "pia", "lave_linge": "mlr", "lave_vaisselle": "mll", "robinet": "torneira", "urinoir": "urinol",
               "sanita": "wc", "maquina_roupa": "mlr", "maquina_louca": "mll"}
FIX_LABEL = {"wc": ("WC", "Sanita"), "lavatorio": ("Lavabo", "Lavatório"), "duche": ("Douche", "Base de duche"),
             "banheira": ("Baignoire", "Banheira"), "bide": ("Bidet", "Bidé"), "pia": ("Évier", "Lava-loiça"),
             "mlr": ("Lave-linge", "Máq. roupa"), "mll": ("Lave-vaisselle", "Máq. loiça"), "torneira": ("Robinet de service", "Torneira de serviço"),
             "urinol": ("Urinoir", "Urinol")}
DEFAULT_FIX = {"T0": {"wc": 1, "lavatorio": 1, "duche": 1, "pia": 1, "mlr": 1},
               "T1": {"wc": 1, "lavatorio": 1, "duche": 1, "pia": 1, "mlr": 1, "mll": 1},
               "T2": {"wc": 1, "lavatorio": 1, "banheira": 1, "bide": 1, "pia": 1, "mlr": 1, "mll": 1},
               "T3": {"wc": 2, "lavatorio": 2, "banheira": 1, "duche": 1, "bide": 1, "pia": 1, "mlr": 1, "mll": 1},
               "T4": {"wc": 2, "lavatorio": 3, "banheira": 1, "duche": 1, "bide": 1, "pia": 1, "mlr": 1, "mll": 1}}
PIPES = [(16, 12.0), (20, 15.5), (25, 20.4), (32, 26.2), (40, 32.6), (50, 40.8), (63, 51.4), (75, 61.4), (90, 73.6), (110, 90.0)]  # PEX/PPR ext, int (mm)
STACKS = [(90, 2.7, 3.5), (100, 4.0, 5.2), (125, 5.8, 7.6), (150, 9.5, 12.4), (200, 16.0, 21.0)]   # DN, Qmax, Qmax entrées à 45°
SIMULT_FR = [(1, 1.0), (5, 0.78), (10, 0.63), (15, 0.53), (20, 0.49), (25, 0.46), (30, 0.44), (35, 0.42), (40, 0.41), (50, 0.40)]
SIMULT_PT = [(1, 1.0), (5, 0.75), (10, 0.56), (15, 0.48), (20, 0.43), (25, 0.40), (30, 0.38), (35, 0.37), (40, 0.36), (50, 0.34)]
CABLES = [(10, 57), (16, 76), (25, 101), (35, 125), (50, 151), (70, 192), (95, 232), (120, 269), (150, 309), (185, 353), (240, 415)]


def fixtures_of(u) -> dict:
    fx = {}
    src = u.fixtures or DEFAULT_FIX.get((u.typology or "T2").upper()[:2], DEFAULT_FIX["T2"])
    for k, v in src.items():
        k2 = FIX_ALIASES.get(str(k).lower(), str(k).lower())
        if k2 in FIXTURES and int(v or 0) > 0:
            fx[k2] = fx.get(k2, 0) + int(v)
    return fx


def peak_flow(sum_qr: float, single_max: float) -> float:
    if sum_qr <= 0:
        return 0.0
    q = 1.48 * sum_qr ** 0.19 - 0.94
    return max(min(q, sum_qr), single_max)


def pipe_for(q_ls: float, vmax: float) -> tuple[int, float]:
    for ext, di in PIPES:
        a = math.pi * (di / 1000) ** 2 / 4
        if q_ls / 1000 / a <= vmax:
            return ext, q_ls / 1000 / a
    ext, di = PIPES[-1]
    return ext, q_ls / 1000 / (math.pi * (di / 1000) ** 2 / 4)


def stack_for(q: float, has_wc: bool) -> int:
    for dn, qmax, _qs in STACKS:
        if dn < 100 and has_wc:
            continue
        if q <= qmax:
            return dn
    return 200


def power_kva(typ: str, country: str) -> float:
    t = (typ or "T2").upper()
    n = int(t[1]) if len(t) > 1 and t[1].isdigit() else 2
    if country == "PT":
        return 6.90 if n <= 1 else (10.35 if n <= 3 else 13.80)
    return 9.0 if n <= 2 else 12.0


def simult(n: int, country: str) -> float:
    tab = SIMULT_PT if country == "PT" else SIMULT_FR
    c = 1.0
    for k, v in tab:
        if n >= k:
            c = v
    return c


def nearest(m: Frame, u, kind: str) -> dict | None:
    cand = [r for r in m.risers if str(r.get("kind", "")).upper() == kind]
    if not cand:
        return None
    cx, cy = u.center
    return min(cand, key=lambda r: (float(r["x"]) - cx) ** 2 + (float(r["y"]) - cy) ** 2)


def compute(m: Frame) -> dict:
    hot = str((m.raw.get("mep") or {}).get("hot_water", "individual")).lower()
    units = []
    for u in m.units:
        fx = fixtures_of(u)
        qr_ef = sum(FIXTURES[k][0] * n for k, n in fx.items())
        qr_ecs = sum(FIXTURES[k][1] * n for k, n in fx.items())
        du = sum(FIXTURES[k][2] * n for k, n in fx.items())
        q_ef = peak_flow(qr_ef, max([FIXTURES[k][0] for k in fx] or [0]))
        q_ecs = peak_flow(qr_ecs, max([FIXTURES[k][1] for k in fx] or [0]))
        d_ef, v_ef = pipe_for(q_ef, 2.0)
        d_ecs, v_ecs = pipe_for(q_ecs, 2.0)
        units.append({"id": u.id, "name": u.name, "level": u.level, "typology": u.typology, "area": u.area, "fixtures": fx,
                      "qr_ef": qr_ef, "qr_ecs": qr_ecs, "q_ef": q_ef, "q_ecs": q_ecs, "d_ef": d_ef, "d_ecs": d_ecs, "du": du,
                      "kva": power_kva(u.typology, m.country),
                      "af": (nearest(m, u, "AF") or {}).get("id"), "ecs": (nearest(m, u, "ECS") or {}).get("id"),
                      "eu": (nearest(m, u, "EU") or {}).get("id"), "elec": (nearest(m, u, "ELEC") or {}).get("id"),
                      "x": u.center[0], "y": u.center[1]})
    lv_order = [l.id for l in m.levels]
    risers = []
    for r in m.risers:
        kind = str(r.get("kind", "")).upper()
        served = [x for x in units if x.get({"AF": "af", "ECS": "ecs", "EU": "eu", "ELEC": "elec"}.get(kind, "_")) == r["id"]]
        sections = []
        for k, lid in enumerate(lv_order):
            # tronçon au niveau lid : alimente les fractions de ce niveau et au-dessus (eau, élec) / reçoit celles de ce niveau et au-dessus (EU)
            up = [x for x in served if lv_order.index(x["level"]) >= k]
            if not up:
                continue
            if kind in ("AF", "ECS"):
                key = "qr_ef" if kind == "AF" else "qr_ecs"
                sq = sum(x[key] for x in up)
                q = peak_flow(sq, 0.15)
                d, v = pipe_for(q, 1.5)
                sections.append({"level": lid, "n": len(up), "sum_qr": sq, "q": q, "d": d, "v": v})
            elif kind == "EU":
                sdu = sum(x["du"] for x in up)
                q = 0.5 * math.sqrt(sdu)
                has_wc = any(x["fixtures"].get("wc") for x in up)
                sections.append({"level": lid, "n": len(up), "sum_du": sdu, "q": q, "d": stack_for(q, has_wc)})
            elif kind == "ELEC":
                kva = sum(x["kva"] for x in up)
                ks = simult(len(up), m.country)
                s_kva = kva * ks
                i = s_kva * 1000 / (math.sqrt(3) * 400)
                sec = next((s for s, a in CABLES if a >= i * 1.0), CABLES[-1][0])
                sections.append({"level": lid, "n": len(up), "kva": kva, "ks": ks, "s_kva": s_kva, "I": i, "sec": sec})
        risers.append({"id": r["id"], "kind": kind, "x": float(r["x"]), "y": float(r["y"]), "label": r.get("label") or r["id"],
                       "served": [x["id"] for x in served], "sections": sections})
    notes = []
    if hot == "individual":
        notes.append(_("Eau chaude produite dans chaque logement (ballon / pompe à chaleur) : pas de colonne ECS collective.",
                       "Água quente produzida em cada fração (termoacumulador / bomba de calor): sem coluna coletiva de AQS."))
    for kind, fr, pt in (("AF", "Aucune colonne d'eau froide relevée", "Nenhuma coluna de água fria relevada"),
                         ("EU", "Aucune chute d'eaux usées relevée", "Nenhum tubo de queda relevado"),
                         ("ELEC", "Aucune colonne électrique relevée", "Nenhuma coluna montante elétrica relevada")):
        if units and not any(r["kind"] == kind for r in risers):
            notes.append(_(fr + " : position à définir avec l'architecte.", pt + ": posição a definir com o arquiteto."))
    return {"units": units, "risers": risers, "hot_water": hot, "notes": notes}
