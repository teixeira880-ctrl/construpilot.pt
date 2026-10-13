"""Aides à la rénovation — API officielle « Mes Aides Réno » (France Rénov' / ANAH).

Source : https://mesaides.france-renov.gouv.fr/api/v1/ (gratuite, sans quota).
Moteur Publicodes officiel → calcul **déterministe** (aucune IA, aucun chiffre inventé).

⚠️ L'ANAH signale que, suite à des évolutions réglementaires, certains barèmes
peuvent ne plus être à jour. Les montants sont donc exposés comme **INDICATIFS**
(cohérent avec l'esprit « non opposable » de ConstruPilot). Tout montant provient
tel quel de l'API ; on ne recalcule ni n'extrapole les aides.
"""
from __future__ import annotations

import os
import urllib.parse

import httpx

API_BASE = "https://mesaides.france-renov.gouv.fr/api/v1"
GEO_BASE = "https://geo.api.gouv.fr/communes"
# Token facultatif (l'API fonctionne sans ; l'ANAH le fournit sur simple demande e-mail).
API_TOKEN = os.environ.get("MESAIDES_API_TOKEN") or ""
TIMEOUT = 20.0

# RenoPilot → paramètres Publicodes de l'API
TYPE_MAP = {"maison": "maison", "appartement": "appartement", "immeuble": "appartement"}
# L'API ne connaît que 4 tranches ; tout bâti ancien = « au moins 15 ans ».
PERIODE_MAP = {
    "avant 1948": "pelo menos 15 anos", "1948-1974": "pelo menos 15 anos",
    "1975-1988": "pelo menos 15 anos", "1989-2000": "pelo menos 15 anos",
    "2001-2012": "pelo menos 15 anos", "après 2012": "de 10 a 15 anos",
}
DPE_LETTER_TO_NUM = {"A": "1", "B": "2", "C": "3", "D": "4", "E": "5", "F": "6", "G": "7"}

_CP_CACHE: dict[str, list[dict]] = {}


async def insee_from_cp(code_postal: str) -> list[dict]:
    """Code postal → liste {code INSEE, nom} (API geo.api.gouv.fr, gratuite)."""
    cp = (code_postal or "").strip()
    if not cp:
        return []
    if cp in _CP_CACHE:
        return _CP_CACHE[cp]
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(GEO_BASE, params={"codePostal": cp, "fields": "nom,code", "format": "json"})
            r.raise_for_status()
            out = [{"code": c["code"], "nom": c["nom"]} for c in r.json()]
    except Exception:
        out = []
    _CP_CACHE[cp] = out
    return out


async def simulate(situation: dict, fields: list[str]) -> dict:
    """Interroge l'API officielle. `fields` joints par virgule = un seul appel.
    Renvoie {field: {label, rawValue, formattedValue, extra, missingVariables}}."""
    params = [(k, str(v)) for k, v in situation.items() if v not in (None, "")]
    params.append(("fields", ",".join(fields)))
    headers = {"User-Agent": "ConstruPilot/1.0"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        r = await client.get(API_BASE + "?" + qs, headers=headers)
        r.raise_for_status()
        data = r.json()
    return data


def _entry(data: dict, field: str) -> dict | None:
    e = data.get(field)
    if not isinstance(e, dict):
        return None
    extra = {k: v for k, v in e.items()
             if k not in ("label", "rawValue", "formattedValue", "missingVariables")}
    return {"label": e.get("label"), "rawValue": e.get("rawValue"),
            "formattedValue": e.get("formattedValue"),
            "missing": e.get("missingVariables") or [], "extra": extra}


GESTE_CATALOGUE = [
    {"code": "pac_air_eau", "label": "Bomba de calor ar/água",
     "base": "gestes.chauffage.PAC.air-eau", "input": None, "unit": None},
    {"code": "vmc_double_flux", "label": "VMC double flux",
     "base": "gestes.ventilation.double flux", "input": None, "unit": None},
    {"code": "iso_rampants", "label": "Isolamento de vertentes / sob a cobertura",
     "base": "gestes.isolation.rampants",
     "input": "gestes.isolation.rampants.MPR.surface", "unit": "m²"},
    {"code": "iso_toiture_terrasse", "label": "Isolamento de cobertura em terraço",
     "base": "gestes.isolation.toitures terrasses",
     "input": "gestes.isolation.toitures terrasses.MPR.surface", "unit": "m²"},
    {"code": "fenetres", "label": "Substituição de janelas (vidro simples)",
     "base": "gestes.isolation.vitres",
     "input": "gestes.isolation.vitres.MPR.quantité", "unit": "équipements"},
    # Murs / plancher bas : l'API ADEME renvoie fréquemment un 500 sur ces postes.
    # → calcul de repli déterministe à partir du forfait officiel MPR par classe de revenu.
    {"code": "iso_murs_ext", "label": "Isolamento das paredes pelo exterior (ETICS)",
     "base": "gestes.isolation.murs extérieurs",
     "input": "gestes.isolation.murs extérieurs.MPR.surface", "unit": "m²", "repli": "iso_murs_ext"},
    {"code": "iso_murs_int", "label": "Isolamento das paredes pelo interior",
     "base": "gestes.isolation.murs intérieurs",
     "input": "gestes.isolation.murs intérieurs.MPR.surface", "unit": "m²", "repli": "iso_murs_int"},
    {"code": "iso_plancher_bas", "label": "Isolamento do pavimento térreo",
     "base": "gestes.isolation.planchers bas",
     "input": "gestes.isolation.planchers bas.MPR.surface", "unit": "m²", "repli": "iso_plancher_bas"},
]
_GESTE_BY_CODE = {g["code"]: g for g in GESTE_CATALOGUE}

# Forfaits officiels MaPrimeRénov' par geste (€/m²), par classe de revenu
# (Bleu = très modestes, Jaune = modestes, Violet = intermédiaires, Rose = supérieurs).
# Utilisés UNIQUEMENT en repli quand l'API officielle est indisponible (500) — marqués « indicatif ».
FORFAIT_MPR_REPLI = {
    "iso_murs_ext": {"bleu": 75, "jaune": 60, "violet": 40, "rose": 15},
    "iso_murs_int": {"bleu": 25, "jaune": 20, "violet": 15, "rose": 7},
    "iso_plancher_bas": {"bleu": 25, "jaune": 20, "violet": 15, "rose": 7},
}

# CEE — fiches d'opérations standardisées BAR-EN (opérations engagées à partir du
# 01/01/2025), volume en kWh cumac/m² d'isolant posé, par zone climatique.
# Officiel (arrêté) et déterministe : BAR-EN-101 combles/rampants, BAR-EN-102 murs
# (ITI/ITE identiques), BAR-EN-103 plancher bas.
CEE_BAR_EN_KWHC = {
    "iso_rampants": {"H1": 1700, "H2": 1400, "H3": 920},
    "iso_murs_ext": {"H1": 1600, "H2": 1300, "H3": 880},
    "iso_murs_int": {"H1": 1600, "H2": 1300, "H3": 880},
    "iso_plancher_bas": {"H1": 1100, "H2": 890, "H3": 590},
}
# Prix de rachat du kWh cumac : NON réglementé (marché ~7,5–9,5 €/MWh cumac).
# Valeur médiane indicative, surchargeable par env. Sert UNIQUEMENT à convertir le
# volume officiel de CEE en euros « indicatifs » — jamais présenté comme opposable.
try:
    CEE_PRIX_KWHC = float(os.environ.get("CEE_PRIX_RACHAT_KWHC") or 0.0085)
except (TypeError, ValueError):
    CEE_PRIX_KWHC = 0.0085

# Zones climatiques (découpage réglementaire RT2012/CEE), par n° de département.
ZONE_H1 = {"01", "02", "03", "05", "08", "10", "14", "15", "19", "21", "23", "25", "27", "28",
           "38", "39", "42", "43", "45", "51", "52", "54", "55", "57", "58", "59", "60", "61",
           "62", "63", "67", "68", "69", "70", "71", "73", "74", "75", "76", "77", "78", "80",
           "87", "88", "89", "90", "91", "92", "93", "94", "95", "975"}
ZONE_H2 = {"04", "07", "09", "12", "16", "17", "18", "22", "24", "26", "29", "31", "32", "33",
           "35", "36", "37", "40", "41", "44", "46", "47", "48", "49", "50", "53", "56", "64",
           "65", "72", "79", "81", "82", "84", "85", "86"}
ZONE_H3 = {"06", "11", "13", "20", "30", "34", "66", "83", "971", "972", "973", "974", "976"}


def _dept_from_code(code: str | None) -> str | None:
    code = (code or "").strip().upper()
    if not code:
        return None
    if code.startswith("97") or code.startswith("98"):
        return code[:3]
    if code[:2] in ("2A", "2B"):
        return "20"
    return code[:2]


def _zone_climatique(code: str | None) -> str | None:
    dept = _dept_from_code(code)
    if not dept:
        return None
    if dept in ZONE_H3:
        return "H3"
    if dept in ZONE_H2:
        return "H2"
    if dept in ZONE_H1:
        return "H1"
    return None


def _normalise_classe(raw) -> str | None:
    """Normalise la classe de revenu Publicodes en bleu/jaune/violet/rose."""
    s = str(raw or "").strip().lower()
    if not s:
        return None
    if "bleu" in s or "très" in s or "tres" in s:
        return "bleu"
    if "jaune" in s or "modeste" in s:
        return "jaune"
    if "violet" in s or "intermédiaire" in s or "intermediaire" in s:
        return "violet"
    if "rose" in s or "supérieur" in s or "superieur" in s or "élevé" in s or "eleve" in s:
        return "rose"
    return None


async def _revenu_classe(situation: dict) -> str | None:
    """Récupère la classe de revenu du ménage via l'API (appel isolé, tolérant au 500)."""
    try:
        d = await simulate(situation, ["ménage.revenu.classe"])
        e = d.get("ménage.revenu.classe") or {}
        return _normalise_classe(e.get("rawValue") or e.get("formattedValue"))
    except Exception:
        return None


async def _geste_amounts(situation: dict, base: str) -> tuple:
    """Lit MPR.montant et CEE.montant d'un geste (appels séparés si l'API 500 sur la combinaison)."""
    mpr = cee = None
    try:
        d = await simulate(situation, [base + ".MPR.montant", base + ".CEE.montant"])
        mpr = (d.get(base + ".MPR.montant") or {}).get("rawValue")
        cee = (d.get(base + ".CEE.montant") or {}).get("rawValue")
    except Exception:
        for suffix, is_mpr in ((".MPR.montant", True), (".CEE.montant", False)):
            try:
                d = await simulate(situation, [base + suffix])
                v = (d.get(base + suffix) or {}).get("rawValue")
                if is_mpr:
                    mpr = v
                else:
                    cee = v
            except Exception:
                pass
    return mpr, cee


async def estimate_gestes(situation: dict, items: list[dict]) -> dict:
    """Simulation « par geste » : pour chaque geste sélectionné, MPR + CEE (API officielle).
    items = [{code, value}]. Montants officiels, non recalculés.

    Repli murs/plancher bas quand l'API renvoie 500 :
      • MPR = forfait officiel MaPrimeRénov' par classe de revenu × surface (marqué « repli »).
      • CEE = volume officiel BAR-EN (kWh cumac/m², par zone climatique) × surface
        × prix de rachat INDICATIF du kWh cumac (non réglementé).
    Sans classe / surface / zone, aucun chiffre n'est inventé (« à confirmer »)."""
    results = []
    total_mpr = total_cee = 0.0
    used_repli = False
    classe_norm: str | None = None  # récupérée paresseusement (une seule fois)
    classe_fetched = False
    zone = _zone_climatique(situation.get("logement.commune") or situation.get("ménage.commune"))
    for it in items:
        g = _GESTE_BY_CODE.get(it.get("code"))
        if not g:
            continue
        sit = dict(situation)
        value = it.get("value")
        if g["input"] and value not in (None, ""):
            sit[g["input"]] = value
        try:
            val_num = float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            val_num = None
        mpr, cee = await _geste_amounts(sit, g["base"])
        source = "api"
        notes: list[str] = []
        cee_kwhc = None

        # --- Repli MPR (forfait officiel MaPrimeRénov' par classe de revenu) ---
        if mpr is None and g.get("repli"):
            if not classe_fetched:
                classe_norm = await _revenu_classe(situation)
                classe_fetched = True
            forfait = FORFAIT_MPR_REPLI.get(g["repli"], {}).get(classe_norm or "")
            source = "repli"
            if forfait and val_num:
                mpr = round(forfait * val_num, 2)
                used_repli = True
                notes.append(f'Apoio indicativo — valor fixo oficial {forfait} €/m² (classe {classe_norm}) × área, indicativo')
            else:
                notes.append("Apoio: rubrica elegível — montante a confirmar (API indisponível)")

        # --- Repli CEE (volume officiel BAR-EN × prix de rachat indicatif) ---
        if cee is None and g["code"] in CEE_BAR_EN_KWHC:
            forfait_kwhc = CEE_BAR_EN_KWHC[g["code"]].get(zone or "")
            if forfait_kwhc and val_num:
                cee_kwhc = round(forfait_kwhc * val_num, 1)
                cee = round(cee_kwhc * CEE_PRIX_KWHC, 2)
                source = "repli"
                used_repli = True
                notes.append(f'Certificados de poupança — zona {zone} {forfait_kwhc} kWhc/m² × {val_num:g} m² × {CEE_PRIX_KWHC} €/kWhc (prix de rachat indicatif)')
            elif g.get("repli"):
                notes.append("Certificados de poupança: a confirmar (zona/área em falta ou API indisponível)")

        if isinstance(mpr, (int, float)):
            total_mpr += mpr
        if isinstance(cee, (int, float)):
            total_cee += cee
        results.append({"code": g["code"], "label": g["label"], "unit": g["unit"],
                        "value": value, "mpr": mpr, "cee": cee, "cee_kwhc": cee_kwhc,
                        "source": source, "note": " · ".join(notes) or None})
    disclaimer = ("Montantes INDICATIVOS por intervenção. Não vinculativos.")
    if used_repli:
        disclaimer = (f'Montantes INDICATIVOS por intervenção, calculados com a referência francesa (API ADEME) e não aplicáveis diretamente em Portugal: apoio = valor fixo por classe de rendimento; certificados = volume oficial (kWh cumac) × preço indicativo ({CEE_PRIX_KWHC} €/kWhc, não regulamentado). Em Portugal, confirme junto do Fundo Ambiental / ADENE. Não vinculativo.')
    return {
        "source": "Simulador de apoios (referência francesa) — percurso por intervenção",
        "disclaimer": disclaimer,
        "gestes": results,
        "used_repli": used_repli,
        "cee_prix_kwhc": CEE_PRIX_KWHC,
        "total_mpr_indicatif": round(total_mpr, 2),
        "total_cee_indicatif": round(total_cee, 2),
        "total_aides_indicatif": round(total_mpr + total_cee, 2),
    }


async def estimate_aides(situation: dict, travaux_ht: float | None = None) -> dict:
    """Simulation complète d'un projet/scénario. Renvoie un récapitulatif normalisé.
    `travaux_ht` (optionnel) sert au reste à charge indicatif."""
    sit = dict(situation)
    if travaux_ht is not None:
        sit["projet.travaux"] = int(round(travaux_ht))

    # Deux appels : l'API refuse (500) de mélanger 'eligibilite' (liste) et des
    # champs scalaires. On les requête donc séparément.
    scalar_fields = [
        "ménage.revenu.classe",
        "MPR.accompagnée.montant",
        "PTZ.montant",
        "PAR.montant",
    ]
    data = await simulate(sit, scalar_fields)
    if not isinstance(data, dict):
        data = {}

    elig_raw = []
    try:
        elig_raw = await simulate(sit, ["eligibilite"])
    except Exception:
        elig_raw = []

    classe = _entry(data, "ménage.revenu.classe")
    mpr = _entry(data, "MPR.accompagnée.montant")
    ptz = _entry(data, "PTZ.montant")
    par = _entry(data, "PAR.montant")

    # eligibilite : liste d'aides applicables, renvoyée telle quelle par l'API.
    aides = []
    if isinstance(elig_raw, list):
        for a in elig_raw:
            if not isinstance(a, dict):
                continue
            aides.append({
                "label": a.get("label"), "fields": a.get("fields"),
                "type": a.get("type"), "status": a.get("status"),
                "value": a.get("value"), "rawValue": a.get("rawValue"),
                "missing": a.get("missingVariables") or [],
            })

    # Subventions chiffrées (rawValue numérique et status != faux) → somme indicative.
    subventions = [a for a in aides
                   if a.get("status") and isinstance(a.get("rawValue"), (int, float))
                   and a.get("type") != "prêt"]
    total_subventions = round(sum(a["rawValue"] for a in subventions), 2) if subventions else None

    reste_a_charge = None
    if travaux_ht is not None and total_subventions is not None:
        reste_a_charge = round(max(travaux_ht - total_subventions, 0), 2)

    return {
        "source": "Simulador de apoios (referência francesa)",
        "disclaimer": ("Montantes INDICATIVOS de uma API oficial francesa. Em Portugal, consulte os programas do Fundo Ambiental e o portal da ADENE. Não vinculativo."),
        "revenu_classe": (classe or {}).get("rawValue"),
        "mpr_accompagnee": mpr,
        "eco_ptz": ptz,
        "pret_avance_renovation": par,
        "aides": aides,
        "total_subventions_indicatif": total_subventions,
        "travaux_ht": travaux_ht,
        "reste_a_charge_indicatif": reste_a_charge,
    }
