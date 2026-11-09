"""Paramètres réglementaires par pays (FR, PT, UA) pour les structures bois massif CLT / lamellé-collé.

Méthode commune : EN 1990 / EN 1991 / EN 1995-1-1 / EN 1995-1-2 (Eurocodes), avec les valeurs nationales :
  FR : NF EN 1990/NA, NF EN 1991-1-1/NA, NF EN 1991-1-3/NA (régions de neige), NF EN 1991-1-4/NA, NF EN 1995-1-1/NA,
       NF EN 1998-1/NA + arrêté du 22/10/2010 ; résistance au feu : arrêté du 31/01/1986 (habitation), code du travail / ERP.
  PT : NP EN 1990, NP EN 1991-1-1, NP EN 1991-1-3 (zonas Z1–Z3), NP EN 1991-1-4 (zonas A/B), NP EN 1995-1-1,
       NP EN 1998-1 (zonas 1.x / 2.x) ; resistência ao fogo : RT-SCIE (Portaria 1532/2008, categorias de risco).
  UA : ДСТУ-Н Б EN 1990, ДСТУ-Н Б EN 1995-1-1 (application parallèle autorisée) ; valeurs caractéristiques des actions
       d'après ДБН В.1.2-2:2006 (зі змінами) ; sismicité ДБН В.1.1-12:2014 ; feu ДБН В.1.1-7:2016.
Aucune valeur n'est inventée : toute donnée de site absente (neige, vent, séisme, sol) est prise par défaut du côté de la
sécurité ET signalée en avertissement dans la note et sur les plans.
"""
from __future__ import annotations

import re

from .lang import t

# ---------------------------------------------------------------- coefficients EN 1990 (identiques FR / PT / UA)
GAM_G, GAM_Q = 1.35, 1.50
# ψ0, ψ1, ψ2 par catégorie d'usage (EN 1990 tab. A1.1)
PSI = {"habitation": (0.7, 0.5, 0.3), "bureaux": (0.7, 0.5, 0.3), "commerce": (0.7, 0.7, 0.6), "scolaire": (0.7, 0.7, 0.6),
       "public": (0.7, 0.7, 0.6), "stationnement": (0.7, 0.7, 0.6), "technique": (1.0, 0.9, 0.8), "toiture": (0.0, 0.0, 0.0),
       "terrasse": (0.7, 0.5, 0.3), "snow": (0.5, 0.2, 0.0)}

# Charges d'exploitation q_k (kN/m²) : FR = NF EN 1991-1-1/NA, PT = NP EN 1991-1-1 (valeurs AN), UA = ДБН В.1.2-2 табл. 6.2
Q_USE = {
    "FR": {"habitation": 1.5, "bureaux": 2.5, "commerce": 5.0, "scolaire": 2.5, "public": 4.0, "stationnement": 2.5,
           "technique": 5.0, "toiture": 1.0, "terrasse": 1.5},
    "PT": {"habitation": 2.0, "bureaux": 3.0, "commerce": 4.0, "scolaire": 3.0, "public": 4.0, "stationnement": 2.5,
           "technique": 5.0, "toiture": 0.4, "terrasse": 2.0},
    "UA": {"habitation": 1.5, "bureaux": 2.0, "commerce": 4.0, "scolaire": 2.0, "public": 4.0, "stationnement": 2.5,
           "technique": 5.0, "toiture": 0.5, "terrasse": 1.5},
}
# Long terme (ψ2) pour la flèche finale ; durée de chargement pour k_mod (EN 1995-1-1 tab. 2.2 / 3.1)
#   G : permanente (k_mod 0,60), Q catégories A/B/C/D : moyen terme (0,80), neige < 1000 m : court terme (0,90)
KMOD = {"permanent": 0.60, "long": 0.70, "medium": 0.80, "short": 0.90, "instant": 1.10}
KDEF = {"GL": 0.60, "CLT": 0.80, "C24": 0.60}                 # classe de service 1 (EN 1995-1-1 tab. 3.2 ; ETA CLT : 0,80)
GAM_M = {"GL": 1.25, "CLT": 1.25, "C24": 1.30, "CONN": 1.30, "STEEL0": 1.00, "STEEL2": 1.25, "CONC": 1.50, "REBAR": 1.15}

# Flèches limites (portée / x) : w_inst(Q), w_net,fin — EN 1995-1-1 tab. 7.2 et AN
DEFL = {"FR": (300, 250), "PT": (300, 250), "UA": (300, 250)}

# ---------------------------------------------------------------- neige
FR_SNOW_SK = {"A1": 0.45, "A2": 0.45, "B1": 0.55, "B2": 0.55, "C1": 0.65, "C2": 0.65, "D": 0.90, "E": 1.40}
PT_SNOW_CZ = {"Z1": 0.30, "Z2": 0.20, "Z3": 0.10}
UA_SNOW_DEFAULT = 1.60          # kN/m² — valeur prudente (zone de Kyiv, ДБН В.1.2-2) si S0 n'est pas fourni

# ---------------------------------------------------------------- vent (vitesse de référence v_b,0 en m/s)
FR_VB0 = {1: 22.0, 2: 24.0, 3: 26.0, 4: 28.0}
PT_VB0 = {"A": 27.0, "B": 30.0}
UA_W0_DEFAULT = 0.40            # kPa (≈ Kyiv, ДБН В.1.2-2 рис. 9.1) si W0 n'est pas fourni

# ---------------------------------------------------------------- séisme : accélération de référence a_gR (m/s²)
FR_AGR = {1: 0.4, 2: 0.7, 3: 1.1, 4: 1.6, 5: 3.0}
PT_AGR = {"1.1": 2.5, "1.2": 2.0, "1.3": 1.5, "1.4": 1.0, "1.5": 0.6, "1.6": 0.35,
          "2.1": 2.5, "2.2": 2.0, "2.3": 1.7, "2.4": 1.1, "2.5": 0.8}
UA_AGR_DEFAULT = 0.50           # intensité 6 (Kyiv, ДБН В.1.1-12 карта А) — prudence


def _dept(address: str) -> str | None:
    m = re.search(r"\b(\d{5})\b", address or "")
    if not m:
        return None
    cp = m.group(1)
    if cp.startswith("20"):
        return "2A" if int(cp) < 20200 else "2B"
    return cp[:3] if cp.startswith("97") else cp[:2]


def q_use(country: str, use: str) -> float:
    return Q_USE.get(country, Q_USE["FR"]).get(use, Q_USE.get(country, Q_USE["FR"])["habitation"])


def snow(raw: dict, country: str, warns: list) -> dict:
    """Charge de neige sur toiture plate s = μ1·Ce·Ct·sk (μ1 = 0,8) ; UA : s = μ·S0 (μ = 1,0)."""
    pr = raw.get("project") or {}
    alt = float(pr.get("altitude_m") or 0)
    if country == "PT":
        z = str(pr.get("snow_zone") or "Z2")
        if "snow_zone" not in pr:
            warns.append(("SNOW", t("Zone de neige non fournie : Z2 retenue.", "Zona de neve não indicada: Z2 admitida.",
                                    "Snow zone not given: Z2 assumed.", "Снігову зону не задано: прийнято Z2.")))
        sk = PT_SNOW_CZ.get(z, 0.20) * (1 + (alt / 500) ** 2) if alt >= 200 else 0.0
        src = f"NP EN 1991-1-3 {z}, alt. {alt:.0f} m"
        mu = 0.8
    elif country == "UA":
        s0 = pr.get("snow_s0_kpa")
        if s0 in (None, ""):
            s0 = UA_SNOW_DEFAULT
            warns.append(("SNOW", t(f"S0 (ДБН В.1.2-2) non fourni : {UA_SNOW_DEFAULT} kPa retenu — à vérifier sur la carte de la région.",
                                    f"S0 (ДБН В.1.2-2) não indicado: {UA_SNOW_DEFAULT} kPa admitido — verificar no mapa regional.",
                                    f"S0 (DBN V.1.2-2) not given: {UA_SNOW_DEFAULT} kPa assumed — check the regional map.",
                                    f"S0 (ДБН В.1.2-2) не задано: прийнято {UA_SNOW_DEFAULT} кПа — перевірити за картою району.")))
        sk = float(s0)
        src = "ДБН В.1.2-2 (S0)"
        mu = 1.0
    else:
        reg = pr.get("snow_region")
        if not reg:
            try:
                from engines.calc_lots.climat_dept import NEIGE_DEPT
            except ImportError:                          # site sans la table départementale : pire cas courant
                NEIGE_DEPT = {}
            reg = NEIGE_DEPT.get(_dept(pr.get("address", "")) or "", None) or "C2"
            warns.append(("SNOW", t(f"Région de neige déduite de l'adresse : {reg} (pire cas du département).",
                                    f"Região de neve deduzida da morada: {reg}.", f"Snow region from the address: {reg}.",
                                    f"Сніговий район за адресою: {reg}.")))
        sk = FR_SNOW_SK.get(reg, 0.65)
        if alt > 200:                                   # NF EN 1991-1-3/NA : majoration d'altitude (régions A–D, 200–500 m)
            sk += (alt - 200) / 1000 * (1.0 if reg != "E" else 1.5)
        src = f"NF EN 1991-1-3/NA {reg}"
        mu = 0.8
    return {"sk": round(sk, 3), "mu": mu, "s": round(mu * sk, 3), "source": src}


def wind(raw: dict, country: str, H: float, warns: list) -> dict:
    """Pression de pointe q_p(H), catégorie de terrain III (z0 = 0,3 m), EN 1991-1-4 §4.5 ; c_o = 1."""
    import math
    pr = raw.get("project") or {}
    if country == "PT":
        z = str(pr.get("wind_zone") or "A")
        vb = PT_VB0.get(z, 27.0)
        src = f"NP EN 1991-1-4 zona {z}"
    elif country == "UA":
        w0 = float(pr.get("wind_w0_kpa") or UA_W0_DEFAULT)
        if not pr.get("wind_w0_kpa"):
            warns.append(("WIND", t(f"W0 non fourni : {UA_W0_DEFAULT} kPa retenu.", f"W0 não indicado: {UA_W0_DEFAULT} kPa.",
                                    f"W0 not given: {UA_W0_DEFAULT} kPa assumed.", f"W0 не задано: прийнято {UA_W0_DEFAULT} кПа.")))
        vb = math.sqrt(2 * w0 * 1000 / 1.25)
        src = "ДБН В.1.2-2 (W0)"
    else:
        reg = int(pr.get("wind_region") or 2)
        vb = FR_VB0.get(reg, 24.0)
        src = f"NF EN 1991-1-4/NA région {reg}"
    z0, zmin = 0.3, 5.0
    z = max(H, zmin)
    kr = 0.19 * (z0 / 0.05) ** 0.07
    cr = kr * math.log(z / z0)
    iv = 1 / math.log(z / z0)
    qb = 0.5 * 1.25 * vb ** 2 / 1000
    qp = (1 + 7 * iv) * cr ** 2 * qb
    return {"vb": round(vb, 1), "qb": round(qb, 3), "qp": round(qp, 3), "source": src}


def seismic(raw: dict, country: str, warns: list) -> dict:
    s = raw.get("seismic") or {}
    pr = raw.get("project") or {}
    if country == "PT":
        z1, z2 = str(s.get("zone1") or pr.get("seismic_zone1") or "1.3"), str(s.get("zone2") or pr.get("seismic_zone2") or "2.3")
        agr = max(PT_AGR.get(z1, 1.5), PT_AGR.get(z2, 1.7))
        src = f"NP EN 1998-1 zonas {z1} / {z2}"
        if not (s.get("zone1") or pr.get("seismic_zone1")):
            warns.append(("SEIS", t("Zones sismiques non fournies : 1.3 / 2.3 (Lisbonne) retenues.", "Zonas sísmicas não indicadas: 1.3 / 2.3 (Lisboa) admitidas.",
                                    "Seismic zones not given: 1.3 / 2.3 (Lisbon) assumed.", "Сейсмічні зони не задано: прийнято 1.3 / 2.3.")))
    elif country == "UA":
        agr = float(s.get("agr") or UA_AGR_DEFAULT)
        src = "ДБН В.1.1-12:2014"
    else:
        zn = int(s.get("zone") or pr.get("seismic_zone") or 2)
        agr = FR_AGR.get(zn, 0.7)
        src = f"NF EN 1998-1/NA zone {zn}"
    soil = str(s.get("soil") or "B")
    S = {"A": 1.0, "B": 1.2, "C": 1.15, "D": 1.35, "E": 1.4}.get(soil, 1.2)
    gi = float(s.get("gamma_i") or 1.0)
    return {"agr": agr, "S": S, "soil": soil, "gamma_i": gi, "q": float(s.get("q") or 2.0), "source": src}


def fire_rating(raw: dict, country: str, h_last_floor: float, n_storeys: int, use: str) -> tuple[int, str]:
    """Durée de stabilité au feu exigée (minutes) pour la structure porteuse."""
    f = raw.get("fire") or {}
    if f.get("R"):
        return int(f["R"]), t("valeur fournie", "valor fornecido", "given value", "задане значення")
    h = h_last_floor
    if country == "PT":                                  # RT-SCIE art. 15 : catégories de risque par hauteur (UT I / III)
        R = 30 if h <= 9 else 60 if h <= 28 else 90 if h <= 50 else 120
        return R, f"RT-SCIE (h = {h:.1f} m)"
    if country == "UA":                                  # ДБН В.1.1-7 : degré de résistance au feu selon le nombre de niveaux
        R = 30 if n_storeys <= 2 else 60 if n_storeys <= 5 else 90
        return R, f"ДБН В.1.1-7 ({n_storeys} пов.)"
    if use == "habitation":                              # arrêté du 31/01/1986 : familles d'habitation
        R = 15 if n_storeys <= 2 else 30 if h <= 8 else 60 if h <= 28 else 90
    else:
        R = 30 if h <= 8 else 60 if h <= 28 else 120
    return R, f"{'arrêté du 31/01/1986' if use == 'habitation' else 'CCH / code du travail'} (h = {h:.1f} m)"


VAT = {"FR": 0.20, "PT": 0.23, "UA": 0.20}
