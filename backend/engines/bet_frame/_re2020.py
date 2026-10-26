# Copie embarquée de engines/calc_lots/re2020.py (site .fr) pour que le moteur ossature soit identique sur .fr et .pt.
"""Pré-étude RE2020 INDICATIVE (logements neufs : maison individuelle, logement collectif).

Ce moteur ne remplace pas l'étude réglementaire : l'attestation RE2020 exige le moteur Th-BCE 2020 du CSTB dans un logiciel évalué.
Il sert à orienter la conception (enveloppe, systèmes, structure) et à repérer tôt les indicateurs en risque.

Ce qui est réglementaire (annexe à l'article R.172-4 du CCH, version révisée 2024 ; arrêté du 4 août 2021) :
  - seuils Bbio_maxmoyen, Cep_maxmoyen, Cep,nr_maxmoyen, DH_max, Ic_énergie_maxmoyen, Ic_construction_maxmoyen et leurs échéances 2025 / 2028 / 2031 ;
  - modulations Mbgéo, Mbcombles, Mbsurf_moy, Mbsurf_tot, Mbbruit, Mcgéo, Mccombles, Mcsurf_moy, Mcsurf_tot, Mccat, Mi… ;
  - coefficients d'énergie primaire (électricité 2,3) et facteurs d'émission par usage (arrêté, art. 9 et 10) ;
  - exigences de moyens : Q4Pa-surf, surface de baies ≥ 1/6 Sref, ratio ψ ≤ 0,33, ψ9 ≤ 0,6.
Ce qui est simplifié (et signalé comme tel dans la note) :
  - besoins Bch / Bfr par méthode MENSUELLE (bilan NF EN ISO 13790 / 52016-1 mensuel, facteur d'utilisation des apports),
    au lieu du calcul horaire Th-BCE ; climat = normales mensuelles approchées d'une station par zone (les fichiers horaires
    du CSTB ne sont pas publics) ;
  - Béclairage forfaitaire selon le ratio de vitrage ; DH = indicateur de tendance (canicule de référence simplifiée) ;
  - Ic_construction : valeur fournie (ACV avec FDES INIES) sinon ordre de grandeur par mode constructif ;
  - Ic_énergie : consommations × facteurs d'émission × somme des coefficients de pondération dynamique approchée.
"""
from __future__ import annotations

import math

from . import _climat as climat

# --------------------------------------------------------------------------------------------------------------------------------
# Zones climatiques RE2020 (découpage repris de la RT2012) et climat mensuel approché
SOUS_ZONES = {
    "H1a": "02 14 27 28 59 60 61 62 75 76 77 78 80 91 92 93 94 95",
    "H1b": "08 10 45 51 52 54 55 57 58 67 68 70 88 89 90",
    "H1c": "01 03 05 15 19 21 23 25 38 39 42 43 63 69 71 73 74 87",
    "H2a": "22 29 35 50 56",
    "H2b": "16 17 18 36 37 41 44 49 53 72 79 85 86",
    "H2c": "07 09 12 24 31 32 33 40 46 47 64 65 81 82",
    "H2d": "04 26 48 84",
    "H3": "06 11 13 20 30 34 66 83",
}
DEPT_ZONE = {d: z for z, s in SOUS_ZONES.items() for d in s.split()}
ZONES = list(SOUS_ZONES)

# Températures extérieures moyennes mensuelles (°C), station représentative (normales approchées) — janvier → décembre
T_MOIS = {
    "H1a": [4.2, 4.8, 7.8, 10.4, 14.0, 17.2, 19.4, 19.2, 15.8, 12.2, 7.6, 4.8],      # bassin parisien
    "H1b": [2.0, 2.8, 6.6, 9.8, 13.8, 17.2, 19.3, 19.0, 15.1, 11.0, 6.1, 2.9],       # Lorraine
    "H1c": [3.4, 4.6, 8.6, 11.6, 15.6, 19.5, 22.0, 21.6, 17.4, 13.2, 7.6, 4.2],      # Lyonnais
    "H2a": [6.0, 6.4, 8.8, 10.8, 14.2, 17.2, 19.2, 19.1, 16.4, 13.0, 9.0, 6.4],      # Bretagne
    "H2b": [5.6, 6.2, 9.0, 11.4, 15.0, 18.4, 20.4, 20.3, 17.4, 13.8, 9.2, 6.2],      # Centre-Ouest / Val de Loire
    "H2c": [5.6, 6.6, 9.8, 12.2, 15.9, 19.8, 22.2, 22.2, 18.6, 14.8, 9.4, 6.4],      # Sud-Ouest
    "H2d": [5.4, 6.6, 10.0, 12.8, 16.8, 20.9, 23.6, 23.1, 19.0, 14.8, 9.4, 6.0],     # Provence intérieure
    "H3": [9.6, 9.9, 11.9, 14.2, 17.6, 21.2, 23.9, 24.2, 21.1, 17.6, 13.2, 10.4],    # littoral méditerranéen
}
# Irradiation globale horizontale annuelle (kWh/m².an) et profil mensuel normalisé (somme = 1)
G_AN = {"H1a": 1120, "H1b": 1150, "H1c": 1290, "H2a": 1200, "H2b": 1330, "H2c": 1400, "H2d": 1560, "H3": 1620}
PROFIL_G = [0.027, 0.043, 0.078, 0.107, 0.130, 0.140, 0.146, 0.126, 0.090, 0.058, 0.032, 0.023]
# rapport irradiation verticale / horizontale par orientation (moyennes mensuelles, latitude 43–50° N)
F_ORIENT = {
    "S": [1.75, 1.45, 1.05, 0.75, 0.58, 0.52, 0.55, 0.68, 0.95, 1.30, 1.65, 1.85],
    "E": [0.55, 0.58, 0.60, 0.62, 0.62, 0.62, 0.62, 0.62, 0.60, 0.58, 0.55, 0.55],
    "O": [0.55, 0.58, 0.60, 0.62, 0.62, 0.62, 0.62, 0.62, 0.60, 0.58, 0.55, 0.55],
    "N": [0.30, 0.30, 0.28, 0.30, 0.33, 0.36, 0.35, 0.31, 0.28, 0.30, 0.30, 0.32],
    "H": [1.0] * 12,
}
F_ORIENT["SE"] = F_ORIENT["SO"] = [round((a + b) / 2, 3) for a, b in zip(F_ORIENT["S"], F_ORIENT["E"])]
F_ORIENT["NE"] = F_ORIENT["NO"] = [round((a + b) / 2, 3) for a, b in zip(F_ORIENT["N"], F_ORIENT["E"])]
T_CONSIGNE_EQ = 18.0     # 19 °C en occupation / 16 °C en réduit (scénario conventionnel logement) ≈ 18 °C en moyenne
JOURS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
PV_KWH_KWC = {"H1a": 1000, "H1b": 1020, "H1c": 1120, "H2a": 1060, "H2b": 1150, "H2c": 1200, "H2d": 1320, "H3": 1350}

# --------------------------------------------------------------------------------------------------------------------------------
# Seuils réglementaires (annexe R.172-4 CCH, révision 2024)
BBIO_MOY = {"maison": 63, "collectif": 65}
CEPNR_MOY = {"maison": 55, "collectif": 70}
CEP_MOY = {"maison": 75, "collectif": 85}
DH_BAS = 350
IC_CONS = {"maison": [(2024, 640), (2027, 530), (2030, 475), (9999, 415)], "collectif": [(2024, 740), (2027, 650), (2030, 580), (9999, 490)]}

# modulations géographiques : ordre H1a H1b H1c H2a H2b H2c H2d H3 ; tranches d'altitude < 400 / 400–800 / > 800 m
MBGEO = {"maison": [[0.15, 0.2, 0.2, -0.05, 0, -0.1, 0.05, -0.1], [0.4, 0.5, 0.45, 0.15, 0.3, 0.05, 0.1, -0.05], [0.75, 0.85, 0.75, 0.55, 0.65, 0.35, 0.25, 0.1]],
         "collectif": [[0.1, 0.2, 0.15, -0.1, 0, -0.1, 0, -0.1], [0.4, 0.5, 0.45, 0.2, 0.3, 0.1, 0.2, -0.05], [0.8, 0.85, 0.75, 0.6, 0.65, 0.4, 0.4, 0.15]]}
MCGEO = {"maison": [[0.1, 0.15, 0.1, -0.05, 0, -0.1, -0.1, -0.15], [0.4, 0.5, 0.4, 0.15, 0.3, 0.05, 0, -0.1], [0.75, 0.85, 0.75, 0.55, 0.6, 0.35, 0.25, 0.15]],
         "collectif": [[0.05, 0.05, 0.05, -0.1, 0, -0.15, -0.1, -0.15], [0.35, 0.4, 0.35, 0.2, 0.2, 0.05, 0.05, -0.1], [0.55, 0.65, 0.55, 0.45, 0.5, 0.3, 0.3, 0.15]]}

# coefficients d'énergie primaire (arrêté du 4 août 2021, art. 9) : (Cep, Cep,nr)
CEP_COEF = {"elec": (2.3, 2.3), "gaz": (1.0, 1.0), "fioul": (1.0, 1.0), "bois": (1.0, 0.0), "reseau": (1.0, None)}
# facteurs d'émission kg éq. CO2 / kWh d'énergie finale (art. 10)
FE_ELEC = {"chauffage": 0.079, "ecs": 0.065, "refroidissement": 0.064, "eclairage": 0.069, "auxiliaires": 0.064}
FE = {"gaz": 0.227, "propane": 0.272, "fioul": 0.324, "bois": 0.030, "granules": 0.030}
SOMME_PONDERATION_50 = sum(0.992 - (0.992 - 0.578) * (t - 1) / 48 for t in range(1, 50)) + 0.578   # années 1 → 50, ≈ 39,0 (approximation linéaire de la table art. 11)

# --------------------------------------------------------------------------------------------------------------------------------
# Systèmes (valeurs conventionnelles indicatives, remplacées par les données produit quand elles sont fournies)
CHAUFFAGE = {
    "pac_air_eau": {"energie": "elec", "rendement": 3.4, "nom": "PAC air/eau"},
    "pac_air_air": {"energie": "elec", "rendement": 3.8, "nom": "PAC air/air"},
    "pac_geothermique": {"energie": "elec", "rendement": 4.3, "nom": "PAC géothermique"},
    "effet_joule": {"energie": "elec", "rendement": 1.0, "nom": "Convecteurs / panneaux rayonnants"},
    "chaudiere_gaz": {"energie": "gaz", "rendement": 0.95, "nom": "Chaudière gaz à condensation"},
    "chaudiere_granules": {"energie": "granules", "rendement": 0.88, "nom": "Chaudière à granulés"},
    "poele_granules": {"energie": "granules", "rendement": 0.85, "nom": "Poêle à granulés (+ appoint électrique 15 %)", "appoint_elec": 0.15},
    "reseau_chaleur": {"energie": "reseau", "rendement": 0.95, "nom": "Réseau de chaleur urbain"},
    "pac_hybride_gaz": {"energie": "mixte", "rendement": 3.0, "part_gaz": 0.25, "nom": "PAC hybride (gaz 25 % des besoins)"},
}
ECS = {
    "cet": {"energie": "elec", "rendement": 2.6, "nom": "Chauffe-eau thermodynamique"},
    "pac_double_service": {"energie": "elec", "rendement": 2.4, "nom": "PAC double service"},
    "ballon_joule": {"energie": "elec", "rendement": 0.85, "nom": "Ballon électrique à effet Joule"},
    "chaudiere_gaz": {"energie": "gaz", "rendement": 0.85, "nom": "Chaudière gaz (production ECS)"},
    "cesi": {"energie": "elec", "rendement": 0.85, "solaire": 0.5, "nom": "Chauffe-eau solaire individuel (50 % solaire)"},
    "reseau_chaleur": {"energie": "reseau", "rendement": 0.85, "nom": "Réseau de chaleur urbain"},
}
VENTIL = {   # débit moyen conventionnel (m³/h par m² Sref), puissance spécifique (W par m³/h), efficacité de récupération
    "vmc_sf_autoreglable": {"q_m2": 0.9, "sfp": 0.25, "eta": 0.0, "nom": "VMC simple flux autoréglable"},
    "vmc_sf_hygro_a": {"q_m2": 0.7, "sfp": 0.20, "eta": 0.0, "nom": "VMC simple flux hygroréglable A"},
    "vmc_sf_hygro_b": {"q_m2": 0.6, "sfp": 0.18, "eta": 0.0, "nom": "VMC simple flux hygroréglable B"},
    "vmc_df": {"q_m2": 0.9, "sfp": 0.40, "eta": 0.75, "nom": "VMC double flux (η 75 % utile)"},
}
INERTIE_CM = {"legere": 110, "moyenne": 165, "lourde": 260, "tres_lourde": 370}            # kJ/(m².K) par m² Sref (NF EN ISO 13790)
AMORT_INERTIE = {"legere": 0.55, "moyenne": 0.38, "lourde": 0.25, "tres_lourde": 0.18}   # amortissement de l'amplitude intérieure (DH)
# Ic construction : ordre de grandeur kg éq. CO2/m² Sref (ACV dynamique, mix de FDES et données par défaut, lots 1 à 13), ± 20 %
IC_CONS_ESTIME = {
    "maison": {"parpaing": 640, "brique": 610, "beton_cellulaire": 600, "beton_banche": 690, "ossature_bois": 500, "bois_massif": 470, "mixte_bois_beton": 560},
    "collectif": {"parpaing": 760, "brique": 730, "beton_cellulaire": 720, "beton_banche": 800, "ossature_bois": 600, "bois_massif": 570, "mixte_bois_beton": 660},
}
U_NEUF = {"mur": 0.20, "toiture": 0.13, "plafond": 0.13, "plancher_bas": 0.18, "fenetre": 1.2, "porte": 1.3}
B_COTE = {"exterieur": 1.0, "terre_plein": 0.45, "vide_sanitaire": 0.8, "garage": 0.8, "comble_perdu": 0.9, "local_non_chauffe": 0.5}


def _v(x, defaut):
    """Valeur fournie (même 0) sinon défaut — évite que 0 soit pris pour « non renseigné »."""
    return defaut if x is None else x


def sous_zone(code_postal: str | None, zone_imposee: str | None = None) -> str:
    if zone_imposee:
        if zone_imposee not in SOUS_ZONES:
            raise ValueError(f"zone climatique inconnue {zone_imposee!r} (H1a … H3)")
        return zone_imposee
    d = climat.departement(code_postal)
    if d and d.startswith(("97", "98")):
        raise ValueError("Outre-mer : la RE2020 ne s'applique pas (réglementation RTAA DOM / RTG / RE Réunion)")
    if not d or d not in DEPT_ZONE:
        raise ValueError("code postal manquant ou inconnu : fournissez code_postal ou zone (H1a … H3)")
    return DEPT_ZONE[d]


def _tranche(alt: float) -> int:
    return 0 if alt < 400 else 1 if alt <= 800 else 2


def periode_ic(annee: int, typ: str) -> int:
    return next(v for a, v in IC_CONS[typ] if annee <= a)


# --------------------------------------------------------------------------------------------------------------------------------
def seuils(typ: str, zone: str, altitude: float, sref: float, nb_logements: int = 1, scombles: float = 0.0, bruit: str = "BR1",
           categorie: int = 1, annee: int = 2026, reseau_chaleur: bool = False, climatise: bool = False, ic_lots: dict | None = None,
           ic_ded: float | None = None) -> dict:
    """Seuils modulés RE2020. ic_lots : {1: kg/m², 2: …, 13: …} pour Mivrd / Miinfra / Mipv (contributions des lots, kg éq. CO2/m² Sref) ;
    ic_ded : part de l'Ic construction issue des données environnementales par défaut (terme Mided)."""
    if categorie not in (1, 2):
        raise ValueError("categorie : 1 ou 2")
    zi, ti = ZONES.index(zone), _tranche(altitude)
    smoy = sref / max(1, nb_logements)
    m = typ == "maison"
    det: dict[str, float] = {}
    # ---- Bbio
    mb_geo = MBGEO[typ][ti][zi]
    mb_comb = 0.4 * scombles / sref if m and sref else 0.0
    if m:
        mb_smoy = (49 - 0.49 * smoy if smoy <= 100 else 18 - 0.18 * smoy if smoy <= 150 else -9) / 63
        mb_stot = 0.0
    else:
        mb_smoy = (-6 + 0.1 * smoy if smoy <= 80 else -2 + 0.05 * smoy if smoy <= 120 else 4) / 65
        mb_stot = (19.5 - 0.015 * sref) / 65 if sref <= 1300 else 0.0
    bruyant = bruit in ("BR2", "BR3")
    if m:
        mb_bruit = 0.1 if bruyant and zone in ("H2d", "H3") else 0.0
    else:
        mb_bruit = (0.1 if zone in ("H1c", "H2c") else 0.2 if zone in ("H2d", "H3") else 0.0) if bruyant else 0.0
    det.update(Mbgeo=mb_geo, Mbcombles=mb_comb, Mbsurf_moy=mb_smoy, Mbsurf_tot=mb_stot, Mbbruit=mb_bruit)
    bbio_max = BBIO_MOY[typ] * (1 + mb_geo + mb_comb + mb_smoy + mb_stot + mb_bruit)
    # ---- Cep, Cep,nr, Ic énergie
    mc_geo = MCGEO[typ][ti][zi]
    mc_comb = 0.4 * scombles / sref if m and sref else 0.0
    if m:
        mc_smoy = (49.5 - 0.55 * smoy if smoy <= 100 else 14.5 - 0.2 * smoy if smoy <= 150 else -15.5) / 55
        mc_stot = 0.0
    else:
        mc_smoy = (45 - smoy if smoy <= 40 else 15 - 0.25 * smoy if smoy <= 80 else 3 - 0.1 * smoy if smoy <= 120 else -9) / 70
        mc_stot = (13 - 0.01 * sref) / 70 if sref <= 1300 else 0.0
    mc_cat = 0.1 if categorie == 2 and zone in ("H2d", "H3") else 0.0
    mc = 1 + mc_geo + mc_comb + mc_smoy + mc_stot + mc_cat
    det.update(Mcgeo=mc_geo, Mccombles=mc_comb, Mcsurf_moy=mc_smoy, Mcsurf_tot=mc_stot, Mccat=mc_cat)
    if m:
        ice_moy = 200 if (reseau_chaleur and annee <= 2027) else 160
    else:
        ice_moy = 560 if annee <= 2024 else (320 if reseau_chaleur and annee <= 2027 else 260)
    # ---- Ic construction
    icc_moy = periode_ic(annee, typ)
    mi_comb = 0.4 * scombles / sref if m and sref else 0.0
    if m:
        mi_smoy = 0.36 - 0.0036 * smoy if smoy <= 120 else -0.072
        mi_stot = 0.0
    else:
        mi_smoy = (100 - 2.5 * smoy) / icc_moy if smoy <= 40 else 0.0
        mi_stot = -0.104 + 0.00008 * sref if sref <= 1300 else 0.0455 - 0.000035 * sref if sref < 4000 else -0.0945
    lots = {int(k): float(v) for k, v in (ic_lots or {}).items()}
    mi_geo = 30.0 if zone in ("H2d", "H3") and altitude < 400 else 0.0
    mi_infra = max(0.0, lots.get(2, 0.0) - 40)
    mi_vrd = max(0.0, lots.get(1, 0.0) - (20 if m else 10))
    mi_pv = max(0.0, lots.get(13, 0.0) - 20)
    mi_ded = 0.0
    if ic_ded is not None:
        ecart = float(ic_ded) - (370 if m else 250)
        mi_ded = 0.3 * ecart if annee <= 2024 else (-0.3 * ecart if annee >= 2028 else 0.0)
    det.update(Micombles=mi_comb, Misurf_moy=mi_smoy, Misurf_tot=mi_stot, Migeo=mi_geo, Miinfra=mi_infra, Mivrd=mi_vrd, Mipv=mi_pv, Mided=mi_ded)
    icc_max = icc_moy * (1 + mi_comb + mi_smoy + mi_stot) + mi_geo + mi_infra + mi_vrd + mi_pv + mi_ded
    # ---- DH
    if m:
        dh_max = 1250 if categorie == 1 else 1850
    else:
        if categorie == 2:
            dh_max = 2600 if smoy <= 20 else 2850 - 12.5 * smoy if smoy <= 60 else 2100
        elif climatise and zone in ("H2d", "H3"):
            dh_max = 1600 if smoy <= 20 else 1700 - 5 * smoy if smoy <= 60 else 1400
        else:
            dh_max = 1250
    return {"Bbio_max": bbio_max, "Cep_max": CEP_MOY[typ] * mc, "Cep_nr_max": CEPNR_MOY[typ] * mc, "Ic_energie_max": ice_moy * mc,
            "Ic_construction_max": icc_max, "DH_max": dh_max, "DH_bas": DH_BAS, "maxmoyen": {"Bbio": BBIO_MOY[typ], "Cep": CEP_MOY[typ],
            "Cep_nr": CEPNR_MOY[typ], "Ic_energie": ice_moy, "Ic_construction": icc_moy}, "modulations": det, "smoy": smoy}


# --------------------------------------------------------------------------------------------------------------------------------
def _enveloppe_defaut(sref: float, niveaux: int, hsp: float, typ: str) -> tuple[list[dict], list[str]]:
    """Enveloppe-type quand la géométrie n'est pas fournie : plan carré, baies 1/6 de Sref réparties S 40 % / E 20 % / O 20 % / N 20 %."""
    emprise = sref / max(1, niveaux)
    cote = math.sqrt(emprise)
    perim = 4 * cote
    a_baies = sref / 6
    mur = max(0.0, perim * hsp * niveaux - a_baies - 2.0)
    parois = [{"type": "mur", "surface_m2": mur, "cote": "exterieur"}, {"type": "porte", "surface_m2": 2.0, "cote": "exterieur"},
              {"type": "plafond" if typ == "maison" else "toiture", "surface_m2": emprise, "cote": "comble_perdu" if typ == "maison" else "exterieur"},
              {"type": "plancher_bas", "surface_m2": emprise, "cote": "terre_plein"}]
    for o, f in (("S", 0.4), ("E", 0.2), ("O", 0.2), ("N", 0.2)):
        parois.append({"type": "fenetre", "surface_m2": a_baies * f, "orientation": o, "cote": "exterieur"})
    return parois, [f"géométrie non fournie : enveloppe-type (plan carré de {emprise:.0f} m² d'emprise × {niveaux} niveau(x), hauteur {hsp:g} m, "
                    f"baies = 1/6 de Sref réparties S 40 % / E 20 % / O 20 % / N 20 %, U neufs usuels)"]


def _eta_util(gamma: float, a: float) -> float:
    if gamma <= 0:
        return 1.0
    if abs(gamma - 1) < 1e-6:
        return a / (a + 1)
    return (1 - gamma ** a) / (1 - gamma ** (a + 1))


def besoins_mensuels(env: dict, zone: str, altitude: float) -> dict:
    """Bilan mensuel NF EN ISO 13790 : chauffage (19 °C en occupation, 16 °C en inoccupation → consigne équivalente 18 °C) et refroidissement conventionnel (26 °C), kWh."""
    dalt = -0.6 * altitude / 100     # gradient d'altitude ≈ −0,6 K / 100 m
    sref, H_tr, H_ve, H_ve_ete = env["sref"], env["H_tr"], env["H_ve"], env["H_ve_ete"]
    cm = INERTIE_CM[env["inertie"]] * 1000 * sref          # J/K
    rows = []
    for k in range(12):
        te = T_MOIS[zone][k] + dalt
        h = JOURS[k] * 24
        g_h = G_AN[zone] * PROFIL_G[k]                       # kWh/m² horizontal du mois
        q_sol_hiver = sum(w["A"] * w["g_eff"] * w["f_hiver"] * g_h * F_ORIENT[w["orient"]][k] for w in env["baies"])
        q_sol_ete = sum(w["A"] * w["g_eff"] * w["f_ete"] * g_h * F_ORIENT[w["orient"]][k] for w in env["baies"])
        q_int = env["apports_w_m2"] * sref * h / 1000
        # chauffage
        H = H_tr + H_ve
        q_ht = H * (T_CONSIGNE_EQ - te) * h / 1000
        q_gn = q_int + q_sol_hiver
        tau = cm / 3600 / H
        a = 1 + tau / 15
        gam = q_gn / q_ht if q_ht > 0 else 99.0
        bch = max(0.0, q_ht - _eta_util(gam, a) * q_gn) if q_ht > 0 else 0.0
        # refroidissement conventionnel (protections solaires gérées, surventilation estivale)
        Hc = H_tr + H_ve_ete
        q_ht_c = Hc * (26 - te) * h / 1000
        q_gn_c = q_int + q_sol_ete
        tau_c = cm / 3600 / Hc
        a_c = 1 + tau_c / 15
        if q_ht_c <= 0:
            bfr = q_gn_c - q_ht_c
        else:
            gc = q_gn_c / q_ht_c
            eta_c = (1 - gc ** (-a_c)) / (1 - gc ** (-(a_c + 1))) if abs(gc - 1) > 1e-6 else a_c / (a_c + 1)
            bfr = max(0.0, q_gn_c - eta_c * q_ht_c)
        rows.append({"mois": MOIS[k], "te": te, "q_ht": q_ht, "q_int": q_int, "q_sol": q_sol_hiver, "bch": bch, "bfr": bfr})
    return {"mois": rows, "Bch_kwh": sum(r["bch"] for r in rows), "Bfr_kwh": sum(r["bfr"] for r in rows)}


def dh_indicatif(env: dict, zone: str, altitude: float, jours_canicule: int = 12) -> dict:
    """Degrés-heures d'inconfort (indicateur de TENDANCE, pas le DH réglementaire Th-BCE).

    Été juin → septembre : journée type par mois (normales, amplitude ± 5 K) + séquence caniculaire de type 2003 (θe moyenne = juillet + 3,5 K,
    amplitude ± 7 K) de `jours_canicule` jours. Température intérieure moyenne = θe + apports / (H_tr + H_ve_été), amplitude amortie selon
    l'inertie ; confort 26 °C la nuit (22 h → 6 h), 27 °C le jour (milieu de la plage adaptative 26–28 °C)."""
    dalt = -0.6 * altitude / 100
    sref = env["sref"]
    damp = AMORT_INERTIE[env["inertie"]]
    Hc = env["H_tr"] + env["H_ve_ete"]
    total = 0.0
    detail = []
    seq = [(k, JOURS[k] - (jours_canicule if k == 6 else 0), 0.0, 5.0) for k in (5, 6, 7, 8)] + [(6, jours_canicule, 3.5, 7.0)]
    for k, nj, surplus, ampl in seq:
        if nj <= 0:
            continue
        te_m = T_MOIS[zone][k] + dalt + surplus
        g_jour = G_AN[zone] * PROFIL_G[k] / JOURS[k] * (1.15 if surplus else 1.0)      # kWh/m².j horizontal (canicule plus ensoleillée)
        q_sol = sum(w["A"] * w["g_eff"] * w["f_ete"] * g_jour * F_ORIENT[w["orient"]][k] for w in env["baies"]) * 1000 / 24    # W moyens
        q_int = env["apports_w_m2"] * sref
        # la surventilation nocturne se fait avec l'air frais de la nuit (θe nuit ≈ θe moyenne − 0,6 × amplitude)
        ti_m = te_m + (q_sol + q_int - env["H_nuit"] * 0.6 * ampl) / Hc
        a_i = ampl * damp + 0.6 * (q_sol / Hc) * damp
        dh = 0.0
        for hr in range(24):
            ti = ti_m + a_i * math.cos(2 * math.pi * (hr - 17) / 24)
            conf = 26.0 if (hr >= 22 or hr < 6) else 27.0
            dh += max(0.0, ti - conf)
        total += dh * nj
        detail.append({"periode": ("canicule" if surplus else MOIS[k]), "jours": nj, "te": te_m, "ti_moy": ti_m, "dh": dh * nj})
    return {"DH": total, "detail": detail}


# --------------------------------------------------------------------------------------------------------------------------------
def calculer(params: dict) -> dict:
    p = dict(params or {})
    hyp: list[str] = ["pré-étude indicative : méthode mensuelle simplifiée, ne remplace pas l'étude RE2020 réglementaire (moteur Th-BCE 2020 du CSTB, logiciel évalué)"]
    if (p.get("travaux") or "neuf") != "neuf":
        raise ValueError("la RE2020 s'applique aux constructions neuves (et extensions concernées) ; en rénovation, utiliser la RT existant "
                         "(élément par élément : calcul_isolation / calcul_lots_techniques)")
    typ = p.get("type_batiment") or "maison"
    if typ not in BBIO_MOY:
        raise ValueError("type_batiment : 'maison' ou 'collectif'")
    sref = float(p.get("sref_m2") or 0)
    if sref <= 0:
        raise ValueError("sref_m2 (surface habitable) obligatoire")
    if typ == "collectif":
        if p.get("nb_logements"):
            nlog = int(p["nb_logements"])
        else:
            nlog = max(2, round(sref / 65))
            hyp.append(f"nombre de logements non fourni : {nlog} estimé (Sref / 65 m²) — il conditionne Smoy, les modulations et le DH_max : à préciser")
    else:
        nlog = 1
    zone = sous_zone(p.get("code_postal"), p.get("zone"))
    alt = float(p.get("altitude_m") or 0)
    if p.get("altitude_m") is None:
        hyp.append("altitude non fournie : < 400 m retenue (modulations Mbgéo / Mcgéo de la première tranche)")
    annee = int(p.get("annee_permis") or 2026)
    if annee < 2022:
        raise ValueError("annee_permis : la RE2020 s'applique aux permis déposés à partir de 2022")
    niveaux = int(p.get("niveaux") or (1 if typ == "maison" else 4))
    hsp = float(p.get("hauteur_m") or 2.5)
    inertie = p.get("inertie") or ("moyenne" if p.get("structure") in (None, "parpaing", "brique", "beton_cellulaire") else
                                   "lourde" if p.get("structure") == "beton_banche" else "legere")
    if not p.get("inertie"):
        hyp.append(f"inertie {inertie} déduite du mode constructif")
    vent = p.get("ventilation") or "vmc_sf_hygro_b"
    if vent not in VENTIL:
        raise ValueError(f"ventilation inconnue {vent!r}")
    # ---- enveloppe
    parois = p.get("parois")
    if not parois:
        parois, h = _enveloppe_defaut(sref, niveaux, hsp, typ)
        hyp += h
    H_tr, a_dep, a_dep_hors_pb, baies, defauts = 0.0, 0.0, 0.0, [], set()
    lignes = []
    volets_def = p.get("protections_solaires")
    g_def = float(p.get("g_vitrage") or 0.55)
    for w in parois:
        t = w.get("type") or "mur"
        A = float(w["surface_m2"])
        if A <= 0:
            raise ValueError(f"surface de paroi nulle ou négative ({t})")
        U = w.get("U")
        if U is None:
            U = U_NEUF.get(t, 0.25)
            defauts.add(t)
        U = float(U)
        b = B_COTE.get(w.get("cote") or ("terre_plein" if t == "plancher_bas" else "exterieur"), 1.0)
        H_tr += A * U * b
        a_dep += A
        if t != "plancher_bas":
            a_dep_hors_pb += A
        lignes.append({"type": t, "A": A, "U": U, "b": b, "HA": A * U * b, "orientation": w.get("orientation")})
        if t == "fenetre":
            o = (w.get("orientation") or "S").upper().replace("W", "O")
            if o not in F_ORIENT:
                raise ValueError(f"orientation de baie inconnue {o!r} (N, NE, E, SE, S, SO, O, NO, H)")
            prot = w.get("protection") if w.get("protection") is not None else volets_def
            prot = prot if prot is not None else "volets"
            f_ete = {"volets": 0.30, "bso": 0.20, "store_exterieur": 0.25, "store_interieur": 0.65, "aucune": 0.90}.get(prot, 0.30)
            g = float(w.get("g") or g_def)
            baies.append({"A": A, "orient": o, "g_eff": g * 0.7, "f_hiver": 0.85, "f_ete": f_ete * (0.85 if not w.get("debord") else 0.6)})
    if defauts:
        hyp.append("U par défaut (neuf) pour : " + ", ".join(f"{t} {U_NEUF.get(t, 0.25):g}" for t in sorted(defauts)) + " W/(m².K)")
    # ponts thermiques
    psi_l = p.get("psi_total_w_k")
    if psi_l is None:
        ratio_psi = float(p.get("ratio_psi") if p.get("ratio_psi") is not None else 0.22)
        if p.get("ratio_psi") is None:
            hyp.append("ponts thermiques non décrits : ratio ψ = 0,22 W/(m²Sref.K) retenu (conception RE2020 courante ; exigence ≤ 0,33)")
        psi_l = ratio_psi * sref
    else:
        ratio_psi = float(psi_l) / sref
    H_tr += float(psi_l)
    # ventilation + infiltrations
    V = VENTIL[vent]
    vol = sref * hsp
    q_vent = V["q_m2"] * sref
    q4 = float(_v(p.get("q4pa_surf"), 0.6 if typ == "maison" else 1.0))
    if p.get("q4pa_surf") is None:
        hyp.append(f"perméabilité à l'air Q4Pa-surf = {q4:g} m³/(h.m²) (valeur de l'exigence, à mesurer en fin de chantier)")
    q_inf = q4 * a_dep_hors_pb * (0.20 if vent == "vmc_df" else 0.15)
    H_ve = 0.34 * (q_vent * (1 - V["eta"]) + q_inf)
    ouv = p.get("ouverture_nocturne")
    n_nuit = 1.0 if ouv in (None, "traversant") else 0.5 if ouv == "mono_orientee" else 0.0
    H_ve_ete = 0.34 * (q_vent + q_inf + n_nuit * vol)
    if ouv is None:
        hyp.append("été : ouverture nocturne des fenêtres possible (logement traversant, surventilation ≈ 1 vol/h en moyenne)")
    env = {"sref": sref, "H_tr": H_tr, "H_ve": H_ve, "H_ve_ete": H_ve_ete, "H_nuit": 0.34 * n_nuit * vol, "inertie": inertie, "baies": baies, "apports_w_m2": 3.5}
    hyp.append("apports internes conventionnels 3,5 W/m² Sref ; chauffage 19 °C en occupation / 16 °C en réduit (consigne équivalente 18 °C) ; refroidissement conventionnel 26 °C")
    bes = besoins_mensuels(env, zone, alt)
    bch, bfr = bes["Bch_kwh"] / sref, bes["Bfr_kwh"] / sref
    a_baies = sum(w["A"] for w in baies)
    ratio_baies = a_baies / sref
    becl = max(0.8, min(3.0, 1.6 * math.sqrt((1 / 6) / ratio_baies))) if ratio_baies > 0 else 3.0
    hyp.append("Béclairage forfaitaire selon le ratio surface de baies / Sref (1,6 kWh/m² à 1/6)")
    bbio = 2 * (bch + bfr) + 5 * becl
    # ---- DH
    dh = dh_indicatif(env, zone, alt)
    # ---- seuils
    s = seuils(typ, zone, alt, sref, nlog, float(p.get("scombles_m2") or 0), p.get("zone_bruit") or "BR1", int(p.get("categorie") or 1), annee,
               "reseau_chaleur" in (p.get("chauffage"), p.get("ecs")), bool(p.get("refroidissement") not in (None, "aucun")), p.get("ic_lots"),
               p.get("ic_ded"))
    if p.get("ic_ded") is None:
        hyp.append("terme Mided (données environnementales par défaut) non appliqué faute de valeur Icded")
    # ---- consommations d'énergie finale (kWh/an)
    ch = CHAUFFAGE.get(p.get("chauffage") or "pac_air_eau")
    if not ch:
        raise ValueError(f"chauffage inconnu {p.get('chauffage')!r}")
    ec = ECS.get(p.get("ecs") or "cet")
    if not ec:
        raise ValueError(f"ECS inconnue {p.get('ecs')!r}")
    eta_dist = 0.92 if (p.get("chauffage") or "pac_air_eau") in ("pac_air_eau", "pac_geothermique", "chaudiere_gaz", "chaudiere_granules", "reseau_chaleur", "pac_hybride_gaz") else 0.97
    r_ch = float(p.get("rendement_chauffage") or ch["rendement"])
    if not p.get("rendement_chauffage"):
        hyp.append(f"chauffage {ch['nom']} : rendement / SCOP saisonnier conventionnel {r_ch:g} (à remplacer par la donnée produit)")
    b_ch_reel = bes["Bch_kwh"] / eta_dist
    conso = []   # (usage, energie, kWh)
    if ch["energie"] == "mixte":
        conso += [("chauffage", "gaz", b_ch_reel * ch["part_gaz"] / 0.95), ("chauffage", "elec", b_ch_reel * (1 - ch["part_gaz"]) / r_ch)]
    elif ch.get("appoint_elec"):
        conso += [("chauffage", ch["energie"], b_ch_reel * (1 - ch["appoint_elec"]) / r_ch), ("chauffage", "elec", b_ch_reel * ch["appoint_elec"])]
    else:
        conso.append(("chauffage", ch["energie"], b_ch_reel / r_ch))
    smoy = s["smoy"]
    b_ecs = nlog * (600 + 13 * min(smoy, 150))        # kWh utiles / an (besoin conventionnel approché)
    hyp.append(f"besoin d'ECS approché : {b_ecs:.0f} kWh/an ({nlog} logement(s), Smoy {smoy:.0f} m²)")
    r_ec = float(p.get("rendement_ecs") or ec["rendement"])
    b_ecs_appoint = b_ecs * (1 - ec.get("solaire", 0.0))
    conso.append(("ecs", ec["energie"], b_ecs_appoint * 1.10 / r_ec))     # +10 % pertes de stockage et distribution
    refr = p.get("refroidissement") or "aucun"
    if refr != "aucun":
        conso.append(("refroidissement", "elec", bes["Bfr_kwh"] / float(p.get("eer") or 3.5)))
    conso.append(("eclairage", "elec", becl * sref))
    aux = V["sfp"] * q_vent * 1.25 * 8760 / 1000 + (1.0 * sref if eta_dist < 0.95 else 0.0)
    conso.append(("auxiliaires", "elec", aux))
    # photovoltaïque autoconsommé (l'export n'est pas valorisé dans cette pré-étude)
    pv_auto = 0.0
    if p.get("pv_kwc"):
        prod = float(p["pv_kwc"]) * PV_KWH_KWC[zone]
        elec_tot = sum(k for _, e, k in conso if e == "elec")
        pv_auto = min(prod * float(_v(p.get("taux_autoconsommation"), 0.35)), 0.30 * elec_tot)   # production estivale ≠ besoin hivernal : plafond 30 %
        hyp.append(f"PV {float(p['pv_kwc']):g} kWc : {prod:.0f} kWh/an produits, {pv_auto:.0f} kWh autoconsommés déduits (export non valorisé)")
    # forfait de refroidissement (bâtiment non climatisé, 350 ≤ DH ≤ DH_max) — loi linéaire approchée (≈ 12 kWhep/m² à 1250 °C.h)
    forfait_fr = 0.0
    if refr == "aucun" and dh["DH"] > DH_BAS:
        forfait_fr = 12.0 * (min(dh["DH"], s["DH_max"]) - DH_BAS) / (1250 - DH_BAS)
        hyp.append("forfait de refroidissement ajouté au Cep : loi linéaire approchée (formule exacte de l'annexe non retenue ici)")
    cep, cepnr, ice_an, ef = 0.0, 0.0, 0.0, {}
    reseau_enr = float(_v(p.get("reseau_part_enr"), 0.5))
    if not 0 <= reseau_enr <= 1:
        raise ValueError("reseau_part_enr doit être entre 0 et 1")
    reseau_fe = float(_v(p.get("reseau_fe"), 0.10))
    elec_tot = sum(k for _, e, k in conso if e == "elec")
    for usage, e, kwh in conso:
        if e == "elec" and pv_auto and elec_tot:
            kwh *= (1 - pv_auto / elec_tot)
        ef[(usage, e)] = ef.get((usage, e), 0.0) + kwh
        ce, cnr = CEP_COEF["bois" if e == "granules" else "gaz" if e == "propane" else e]
        if e == "reseau":
            cnr = 1 - reseau_enr
        cep += ce * kwh
        cepnr += cnr * kwh
        fe = FE_ELEC[usage] if e == "elec" else reseau_fe if e == "reseau" else FE[e]
        ice_an += fe * kwh
    ice_an += forfait_fr * sref / 2.3 * FE_ELEC["refroidissement"]     # forfait = électricité de refroidissement conventionnelle
    cep = cep / sref + forfait_fr
    cepnr = cepnr / sref + forfait_fr
    if "reseau" in {e for _, e, _ in conso}:
        hyp.append(f"réseau de chaleur : part EnR&R {reseau_enr * 100:.0f} %, contenu CO2 {reseau_fe:g} kg/kWh (valeurs de l'arrêté du réseau à saisir)")
    ic_energie = ice_an * SOMME_PONDERATION_50 / sref
    # ---- Ic construction
    if p.get("ic_construction") is not None:
        icc, icc_src = float(p["ic_construction"]), "valeur fournie (ACV)"
    else:
        struct = p.get("structure") or "parpaing"
        if struct not in IC_CONS_ESTIME[typ]:
            raise ValueError(f"structure inconnue {struct!r}")
        icc = IC_CONS_ESTIME[typ][struct]
        icc_src = f"ordre de grandeur pour une structure {struct} (± 20 %, à remplacer par l'ACV avec FDES INIES)"
        hyp.append(f"Ic construction estimé à {icc:g} kg éq. CO2/m² ({struct}) : ordre de grandeur, ± 20 %")
    # ---- contrôles
    def ctl(ref, exig, val, ok, note=None):
        return {"ref": ref, "exigence": exig, "valeur": val, "ok": ok, "note": note}
    controles = [
        ctl("Bbio (besoin bioclimatique)", f"≤ Bbio_max = {s['Bbio_max']:.1f} pts", f"{bbio:.1f} pts", bbio <= s["Bbio_max"],
            "agir sur l'isolation, les ponts thermiques, l'orientation des baies et les protections solaires" if bbio > s["Bbio_max"] else None),
        ctl("Cep,nr (énergie primaire non renouvelable)", f"≤ {s['Cep_nr_max']:.1f} kWhep/m².an", f"{cepnr:.1f}", cepnr <= s["Cep_nr_max"]),
        ctl("Cep (énergie primaire totale)", f"≤ {s['Cep_max']:.1f} kWhep/m².an", f"{cep:.1f}", cep <= s["Cep_max"]),
        ctl("DH (degrés-heures d'inconfort, TENDANCE)", f"≤ {s['DH_max']:.0f} °C.h (sans forfait si < 350)", ("> 5000 °C.h" if dh["DH"] > 5000 else f"≈ {dh['DH']:.0f} °C.h"),
            True if dh["DH"] <= 0.8 * s["DH_max"] else (False if dh["DH"] > 1.3 * s["DH_max"] else None),
            "indicateur simplifié : vérifier en étude Th-BCE" + (" ; ajouter protections solaires extérieures / inertie / ouverture nocturne" if dh["DH"] > 0.8 * s["DH_max"] else "")),
        ctl(f"Ic énergie ({annee})", f"≤ {s['Ic_energie_max']:.0f} kg éq. CO2/m²", f"{ic_energie:.0f}", ic_energie <= s["Ic_energie_max"]),
        ctl(f"Ic construction ({annee})", f"≤ {s['Ic_construction_max']:.0f} kg éq. CO2/m²", f"{icc:.0f} ({icc_src})",
            (icc <= s["Ic_construction_max"]) if p.get("ic_construction") is not None else (None if abs(icc - s["Ic_construction_max"]) <= 0.2 * icc else icc <= s["Ic_construction_max"]),
            None if p.get("ic_construction") is not None else "estimation : conclure avec l'ACV (FDES / PEP / données par défaut)"),
        ctl("Exigence de moyens — perméabilité à l'air", f"Q4Pa-surf ≤ {0.6 if typ == 'maison' else 1.0:g} m³/(h.m²)", f"{q4:g}",
            q4 <= (0.6 if typ == "maison" else 1.0) + 1e-9, "mesure obligatoire en fin de chantier"),
        ctl("Exigence de moyens — surface de baies", "≥ 1/6 de Sref (alternative à l'éclairement naturel)", f"{a_baies:.1f} m² / {sref / 6:.1f} m²",
            a_baies >= sref / 6 - 1e-6),
        ctl("Exigence de moyens — ponts thermiques", "ratio ψ ≤ 0,33 W/(m²Sref.K) ; ψ9 ≤ 0,6 W/(m.K)",
            f"ratio {ratio_psi:.2f}" + (f" ; ψ9 {float(p['psi9']):.2f}" if p.get("psi9") is not None else ""),
            ratio_psi <= 0.33 and (p.get("psi9") is None or float(p["psi9"]) <= 0.6)),
    ]
    conforme = all(c["ok"] is not False for c in controles)
    cls = classement([{"usage": u, "energie": e, "kwh": k} for (u, e), k in ef.items()], sref, zone, alt, p.get("date_dpe"))
    return {"classement": cls, "type_batiment": typ, "zone": zone, "altitude_m": alt, "sref": sref, "nb_logements": nlog, "annee_permis": annee, "inertie": inertie,
            "ventilation": V["nom"], "chauffage": ch["nom"], "ecs": ec["nom"], "H_tr": H_tr, "H_ve": H_ve, "Ubat_approx": H_tr / a_dep if a_dep else 0.0,
            "ratio_psi": ratio_psi, "parois": lignes, "a_baies": a_baies, "Bch": bch, "Bfr": bfr, "Becl": becl, "Bbio": bbio, "besoins": bes,
            "DH": dh["DH"], "dh_detail": dh["detail"], "forfait_refroidissement": forfait_fr, "Cep": cep, "Cep_nr": cepnr,
            "conso_finale": [{"usage": u, "energie": e, "kwh": k} for (u, e), k in ef.items()], "pv_autoconsomme_kwh": pv_auto,
            "Ic_energie": ic_energie, "Ic_construction": icc, "seuils": s, "controles": controles, "conforme": conforme, "hypotheses": hyp}



class _DpeMin:
    """Seuils DPE standard (arrêté du 31/03/2021 modifié) pour les sites sans le moteur DPE complet."""
    FE = {"gaz": 0.227, "fioul": 0.324, "gpl": 0.272, "bois": 0.030, "granules": 0.030, "reseau": 0.385}
    FE_ELEC = {"chauffage": 0.079, "ecs": 0.065, "refroidissement": 0.064, "eclairage": 0.069, "auxiliaires": 0.064}

    @staticmethod
    def coef_elec(d):
        import datetime as _dt
        return 2.3 if d < _dt.date(2026, 1, 1) else 1.9 if d < _dt.date(2027, 1, 1) else 1.7

    @staticmethod
    def classe(cep, ges, sh, zone, alt_classe):
        sc, sg = [70, 110, 180, 250, 330, 420], [6, 11, 30, 50, 70, 100]
        if alt_classe == 2 and zone in ("H1B", "H1C", "H2D"):
            sc[4], sc[5], sg[4], sg[5] = 390, 500, 80, 110
        ce = next(("ABCDEFG"[i] for i, s in enumerate(sc) if cep < s), "G")
        cg = next(("ABCDEFG"[i] for i, s in enumerate(sg) if ges < s), "G")
        return {"energie": ce, "climat": cg, "dpe": max(ce, cg), "seuils_cep": sc, "seuils_ges": sg}

def classement(conso: list, sref: float, zone: str, altitude: float, date_dpe=None) -> dict:
    """Classement énergétique du logement neuf (étiquettes énergie et climat du DPE, arrêté du 31/03/2021 modifié) à partir des
    consommations conventionnelles 5 usages de l'étude : Cep DPE (coefficient de l'électricité en vigueur à la date du DPE)
    et émissions GES (facteurs par usage), double seuil — classe finale = la plus défavorable des deux."""
    import datetime as _dt
    try:
        from engines.calc_lots import dpe as _dpe          # site .fr : barème DPE complet
    except ImportError:                                     # site .pt : seuils standard (surfaces > 40 m²)
        _dpe = _DpeMin
    d = date_dpe if isinstance(date_dpe, _dt.date) else _dt.date.today()
    k_el = _dpe.coef_elec(d)
    ep = ges = 0.0
    for c in conso:
        kwh, en = float(c["kwh"]), c["energie"]
        if en == "elec":
            ep += kwh * k_el
            ges += kwh * _dpe.FE_ELEC.get(c["usage"], 0.064)
        else:
            ep += kwh * 1.0
            ges += kwh * _dpe.FE.get(en, 0.227)
    sref = max(sref, 1.0)
    cep, g = ep / sref, ges / sref
    z = (zone or "H1A").upper()
    cl = _dpe.classe(cep, g, sref, z, 2 if altitude > 800 else 1)
    return {"cep": round(cep, 1), "ges": round(g, 1), "energie": cl["energie"], "climat": cl["climat"], "dpe": cl["dpe"],
            "seuils_cep": cl["seuils_cep"], "seuils_ges": cl["seuils_ges"], "coef_elec": k_el, "date": d.strftime("%d/%m/%Y")}


# --------------------------------------------------------------------------------------------------------------------------------
def note(params: dict) -> dict:
    from reportlab.lib.units import mm

    from engines.calc_lots import graficos as G
    from engines.calc_lots import notes
    r = calculer(params)
    s = r["seuils"]
    W = mm
    f = notes._f
    ind = [["Bbio", f"{r['Bbio']:.1f}", f"{s['Bbio_max']:.1f}", "pts"], ["Cep,nr", f"{r['Cep_nr']:.1f}", f"{s['Cep_nr_max']:.1f}", "kWhep/m².an"],
           ["Cep", f"{r['Cep']:.1f}", f"{s['Cep_max']:.1f}", "kWhep/m².an"], ["DH (tendance)", f"{r['DH']:.0f}", f"{s['DH_max']:.0f}", "°C.h"],
           ["Ic énergie", f"{r['Ic_energie']:.0f}", f"{s['Ic_energie_max']:.0f}", "kg éq. CO2/m²"],
           ["Ic construction", f"{r['Ic_construction']:.0f}", f"{s['Ic_construction_max']:.0f}", "kg éq. CO2/m²"]]
    mod = [[k, f"{v:+.3f}" if abs(v) < 5 else f"{v:+.0f}"] for k, v in s["modulations"].items() if v]
    mois = [[m["mois"], f"{m['te']:.1f}", f(max(0.0, m["q_ht"])), f(m["q_int"]), f(m["q_sol"]), f(m["bch"]), f(m["bfr"])] for m in r["besoins"]["mois"]]
    par = [[l["type"] + (f" {l['orientation']}" if l.get("orientation") else ""), f(l["A"], 1), f"{l['U']:.2f}", f"{l['b']:g}", f(l["HA"], 1)] for l in r["parois"]]
    ef = [[c["usage"], c["energie"], f(c["kwh"]), f(c["kwh"] / r["sref"], 1)] for c in r["conso_finale"]]
    blocs = [
        ("p", "PRÉ-ÉTUDE INDICATIVE — ne remplace pas l'étude thermique et environnementale RE2020 réglementaire (moteur Th-BCE 2020 du CSTB, "
              "logiciel évalué, ACV avec FDES). Seuils et modulations : annexe à l'article R.172-4 du CCH (révision 2024) ; coefficients : arrêté du 4 août 2021."),
        ("h2", "1. Indicateurs RE2020 et seuils modulés"),
        ("table", ["Indicateur", "Projet", "Seuil max", "Unité"], ind, [45 * W, 30 * W, 30 * W, 45 * W]),
        ("chart", G.jauges([(k, (v / m) if m else None, f"{v:.0f} / {m:.0f}") for k, v, m in (
            ("Bbio", r["Bbio"], s["Bbio_max"]), ("Cep,nr", r["Cep_nr"], s["Cep_nr_max"]), ("Cep", r["Cep"], s["Cep_max"]), ("DH (tendance)", r["DH"], s["DH_max"]),
            ("Ic énergie", r["Ic_energie"], s["Ic_energie_max"]), ("Ic construction", r["Ic_construction"], s["Ic_construction_max"]))],
            "Indicateurs du projet rapportés au seuil modulé"), "Vert ≤ 90 % du seuil, ambre entre 90 et 100 %, rouge au-delà."),
        ("controls", r["controles"]),
        ("h2", "2. Modulations appliquées"),
        ("p", f"Zone {r['zone']} · altitude {r['altitude_m']:g} m · Sref {f(r['sref'])} m² · Smoy {s['smoy']:.0f} m² · permis {r['annee_permis']} · "
              f"maxmoyens : Bbio {s['maxmoyen']['Bbio']}, Cep,nr {s['maxmoyen']['Cep_nr']}, Cep {s['maxmoyen']['Cep']}, Ic énergie {s['maxmoyen']['Ic_energie']}, "
              f"Ic construction {s['maxmoyen']['Ic_construction']}"),
        ("table", ["Coefficient", "Valeur"], mod or [["aucune", "0"]], [60 * W, 40 * W]),
        ("h2", "3. Enveloppe"),
        ("p", f"H_T = {r['H_tr']:.1f} W/K (dont ponts thermiques, ratio ψ {r['ratio_psi']:.2f} W/(m²Sref.K)) · H_V = {r['H_ve']:.1f} W/K ({r['ventilation']}) · "
              f"U moyen ≈ {r['Ubat_approx']:.2f} W/(m².K) · inertie {r['inertie']} · baies {r['a_baies']:.1f} m²"),
        ("table", ["Paroi", "A m²", "U", "b", "H W/K"], par, [45 * W, 22 * W, 18 * W, 14 * W, 22 * W]),
        ("h2", "4. Besoins mensuels (méthode NF EN ISO 13790 simplifiée)"),
        ("chart", G.colonnes([m["mois"][:3] for m in r["besoins"]["mois"]],
                             [("Besoin de chauffage", [m["bch"] for m in r["besoins"]["mois"]]), ("Besoin de refroidissement", [m["bfr"] for m in r["besoins"]["mois"]])],
                             "Besoins mensuels", "kWh", couleurs=[G.SERIES[1], G.SERIES[0]])),
        ("table", ["Mois", "θe °C", "Déperd. kWh", "Int. kWh", "Sol. kWh", "Bch kWh", "Bfr kWh"], mois, [18 * W, 16 * W, 26 * W, 22 * W, 22 * W, 22 * W, 22 * W]),
        ("p", f"Bch = {r['Bch']:.1f} kWh/m² · Bfr = {r['Bfr']:.1f} kWh/m² · Béclairage = {r['Becl']:.1f} kWh/m² → Bbio = 2 × (Bch + Bfr) + 5 × Bécl = {r['Bbio']:.1f} pts"),
        ("h2", "5. Consommations et émissions"),
        ("p", f"Chauffage : {r['chauffage']} · ECS : {r['ecs']}" + (f" · PV autoconsommé {f(r['pv_autoconsomme_kwh'])} kWh/an" if r["pv_autoconsomme_kwh"] else "")
              + (f" · forfait refroidissement {r['forfait_refroidissement']:.1f} kWhep/m²" if r["forfait_refroidissement"] else "")),
        ("table", ["Usage", "Énergie", "kWh EF/an", "kWh EF/m²"], ef, [40 * W, 25 * W, 30 * W, 30 * W]),
        ("chart", G.cote_a_cote(G.donut([(G.usage(c["usage"]), c["kwh"]) for c in r["conso_finale"]], "Consommation d'énergie finale par usage",
                                        f"{f(sum(c['kwh'] for c in r['conso_finale']))}", "kWh EF/an"),
                                G.barres_h([("Parois opaques et baies", sum(l["HA"] for l in r["parois"])), ("Renouvellement d'air", r["H_ve"]),
                                            ("Ponts thermiques", max(0.0, r["H_tr"] - sum(l["HA"] for l in r["parois"])))],
                                           "Répartition des déperditions", "W/K", w=86 * G.mm))),
        ("p", f"Ic énergie = Σ(consommation × facteur d'émission de l'usage) × {SOMME_PONDERATION_50:.1f} (somme approchée des pondérations dynamiques sur 50 ans) / Sref."),
    ]
    titre = "Pré-étude RE2020 (indicative)"
    a_verifier = any(c["ok"] is None for c in r["controles"])
    verdict = ("au moins un indicateur en dépassement" if not r["conforme"] else
               "indicateurs estimés conformes, Ic construction à confirmer par l'ACV" if a_verifier else "conforme sur tous les indicateurs estimés")
    sous = f"{'Maison individuelle' if r['type_batiment'] == 'maison' else 'Logement collectif'} · {r['zone']} · Sref {r['sref']:.0f} m² · {verdict}"
    cl = r["classement"]

    def _plages(seuils):
        out, lo = [], 0
        for i, c_ in enumerate("ABCDEFG"):
            out.append((c_, f"≤ {seuils[0]:g}" if i == 0 else (f"> {seuils[-1]:g}" if i == 6 else f"{lo + 1:g} à {seuils[i]:g}")))
            lo = seuils[i] if i < 6 else lo
        return out
    blocs += [
        ("h2", "6. Classement énergétique — étiquettes énergie et climat (DPE du logement neuf)"),
        ("chart", G.cote_a_cote(G.etiquette(_plages(cl["seuils_cep"]), {cl["energie"]: f"{cl['cep']:.0f} kWhEP"}, "Énergie — kWhEP/m².an"),
                                G.etiquette(_plages(cl["seuils_ges"]), {cl["climat"]: f"{cl['ges']:.1f} kgCO2"}, "Climat — kgCO2/m².an", couleurs=G.GES_COULEURS)),
         f"Classe DPE {cl['dpe']} = la plus défavorable des deux échelles (double seuil)."),
        ("table", ["Indicateur", "Valeur", "Classe"], [["Consommation d'énergie primaire (5 usages)", f"{cl['cep']:.1f} kWhEP/m².an", cl["energie"]],
                                                        ["Émissions de gaz à effet de serre", f"{cl['ges']:.1f} kg éq. CO2/m².an", cl["climat"]],
                                                        ["Étiquette DPE du logement", "double seuil", cl["dpe"]]], [80 * W, 50 * W, 25 * W]),
        ("p", f"Méthode : consommations conventionnelles 5 usages de la présente étude (chauffage, ECS, refroidissement, éclairage, auxiliaires) ; "
              f"électricité convertie en énergie primaire avec le coefficient {str(cl['coef_elec']).replace('.', ',')} en vigueur au {cl['date']} "
              f"(2,3 dans le calcul RE2020) ; facteurs d'émission par usage de l'arrêté DPE ; seuils de l'arrêté du 31/03/2021 modifié. "
              "Le DPE définitif du logement neuf est établi à la livraison par un diagnostiqueur certifié, à partir de l'étude thermique réglementaire."),
    ]
    blocs = [("kpis", [{"label": "Classe énergie (DPE)", "value": f"{cl['dpe']} · {cl['cep']:.0f} kWhEP", "ok": cl["dpe"] <= "C"},
                       {"label": "Bbio / Bbio,max", "value": f"{r['Bbio']:.0f} / {s['Bbio_max']:.0f}", "ok": r["Bbio"] <= s["Bbio_max"]},
                       {"label": "Cep,nr (kWhep/m².an)", "value": f"{r['Cep_nr']:.0f} / {s['Cep_nr_max']:.0f}", "ok": r["Cep_nr"] <= s["Cep_nr_max"]},
                       {"label": "Ic énergie (kg éq. CO2/m²)", "value": f"{r['Ic_energie']:.0f} / {s['Ic_energie_max']:.0f}", "ok": r["Ic_energie"] <= s["Ic_energie_max"]}])] + blocs
    if params.get("_blocs_only"):                       # note intégrée à l'étude thermique du bâtiment (bet_frame)
        return {**r, "titre": titre, "sous_titre": sous, "blocs": blocs}
    pdf, png = notes.pdf(titre, sous, blocs, r["hypotheses"])
    return {**r, "titre": titre, "sous_titre": sous, "pdf": pdf, "png": png}
