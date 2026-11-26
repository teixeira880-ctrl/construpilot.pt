"""Prompt en langage courant → programme architectural (déterministe).

Le même texte donne toujours le même programme (règle ConstruPilot : un même pedido donne le même résultat).
Ce qui n'est pas dit est pris dans des valeurs types, écrites dans `hypotheses` pour que l'architecte les voie.

Typologie : en France T4 = 4 pièces principales (séjour + 3 chambres) ; au Portugal T3 / V3 = 3 quartos.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

from engines.estudio_projeto import sitio

PAIS = sitio.PAIS

# clé → (FR, PT, EN, zone, surface type m²)
PIECES: Dict[str, tuple] = {
    "sejour": ("Séjour", "Sala", "Living room", "jour", 30.0),
    "sejour_cuisine": ("Séjour / cuisine", "Sala / cozinha", "Living / kitchen", "jour", 40.0),
    "cuisine": ("Cuisine", "Cozinha", "Kitchen", "jour", 11.0),
    "entree": ("Entrée", "Hall de entrada", "Entrance", "jour", 5.0),
    "wc": ("WC", "WC", "WC", "jour", 1.8),
    "bureau": ("Bureau", "Escritório", "Office", "jour", 9.0),
    "buanderie": ("Buanderie", "Lavandaria", "Laundry", "jour", 5.0),
    "chambre": ("Chambre", "Quarto", "Bedroom", "nuit", 11.0),
    "suite": ("Chambre parentale", "Suite", "Master bedroom", "nuit", 14.0),
    "sdb": ("Salle de bain", "Casa de banho", "Bathroom", "nuit", 6.0),
    "sde": ("Salle d'eau", "Casa de banho da suite", "Shower room", "nuit", 4.0),
    "dressing": ("Dressing", "Closet", "Walk-in closet", "nuit", 4.0),
    "garage": ("Garage", "Garagem", "Garage", "garage", 18.0),
}
HUMIDES = {"wc", "sdb", "sde", "buanderie"}

_NOMBRES = {"un": 1, "une": 1, "um": 1, "uma": 1, "one": 1, "a": 1, "deux": 2, "dois": 2, "duas": 2, "two": 2,
            "trois": 3, "tres": 3, "three": 3, "quatre": 4, "quatro": 4, "four": 4, "cinq": 5, "cinco": 5, "five": 5,
            "six": 6, "seis": 6}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def nom(cle: str, lang: Optional[str] = None, n: Optional[int] = None) -> str:
    lang = (lang or ("pt" if PAIS == "PT" else "fr")).lower()
    i = {"fr": 0, "pt": 1, "en": 2}.get(lang, 0)
    base = PIECES[cle][i]
    return f"{base} {n}" if n else base


def _compte(txt: str, mots: str) -> Optional[int]:
    m = re.search(rf"\b(\d{{1,2}}|{'|'.join(_NOMBRES)})\s+(?:grandes?\s+|petites?\s+)?(?:{mots})\b", txt)
    if not m:
        return None
    v = m.group(1)
    return int(v) if v.isdigit() else _NOMBRES.get(v)


def lire(prompt: str) -> Dict[str, Any]:
    """Analyse le prompt. Renvoie {"reconnu": bool, "chambres", "surface", "niveaux", "garage", ...}."""
    t = _fold(prompt)
    out: Dict[str, Any] = {"reconnu": False}
    typo = re.search(r"\b([tv])\s?([1-9])\b", t)
    if typo:
        n = int(typo.group(2))
        # France : T4 = séjour + 3 chambres ; Portugal : T3 / V3 = 3 quartos.
        out["chambres"] = n if (PAIS == "PT" or typo.group(1) == "v") else max(0, n - 1)
        out["typologie"] = typo.group(0).upper().replace(" ", "")
        out["reconnu"] = True
    ch = _compte(t, r"chambres?|quartos?|bedrooms?")
    if ch is not None:
        out["chambres"] = ch
        out["reconnu"] = True
    surf = [float(x.replace(",", ".")) for x in re.findall(r"(\d{2,4}(?:[.,]\d+)?)\s*(?:m2|m²|m\s?carr|metres? carr|metros? quadrados|sqm)", t)]
    if surf:
        out["surface"] = max(surf)
        out["reconnu"] = True
    if re.search(r"plain[- ]?pied|rez[- ]de[- ]chaussee seul|terrea|piso unico|um piso|single[- ]stor|bungalow", t):
        out["niveaux"] = 1
    if re.search(r"\br\s?\+\s?1\b|etage|deux niveaux|2 niveaux|duplex|dois pisos|2 pisos|andar|piso superior|r/c\s?\+\s?1|two[- ]stor|2[- ]stor", t):
        out["niveaux"] = 2
    if re.search(r"garage|garagem", t) and not re.search(r"sans garage|sem garagem|no garage", t):
        out["garage"] = True
    if re.search(r"double garage|garage double|garagem dupla|2 voitures|duas viaturas|two[- ]car", t):
        out["garage"] = True
        out["garage_double"] = True
    if re.search(r"bureau|escritorio|office", t):
        out["bureau"] = True
    if re.search(r"buanderie|cellier|lavandaria|laundry", t):
        out["buanderie"] = True
    if re.search(r"suite parentale|suite|master", t):
        out["suite"] = True
    if re.search(r"cuisine ouverte|cuisine americaine|cozinha aberta|open[- ]plan|open kitchen|kitchenette", t):
        out["cuisine_ouverte"] = True
    if re.search(r"cuisine fermee|cuisine separee|cozinha fechada|cozinha separada|separate kitchen", t):
        out["cuisine_ouverte"] = False
    nb_sdb = _compte(t, r"salles? de bains?|salles? d'eau|casas? de banho|wc'?s|bathrooms?")
    if nb_sdb:
        out["sdb"] = nb_sdb
    if re.search(r"toit[- ]terrasse|toit plat|toiture plate|cobertura plana|terraco|flat roof", t):
        out["toiture"] = "plana"
    elif re.search(r"4 pans|quatre pans|quatro aguas|hip roof", t):
        out["toiture"] = "quatro_aguas"
    elif re.search(r"1 pan|un pan|monopente|uma agua|mono[- ]?pitch|shed roof", t):
        out["toiture"] = "uma_agua"
    elif re.search(r"2 pans|deux pans|duas aguas|gable", t):
        out["toiture"] = "duas_aguas"
    if any(k in out for k in ("niveaux", "garage", "toiture", "bureau", "suite")):
        out["reconnu"] = out["reconnu"] or bool(re.search(r"maison|moradia|casa|house|villa|pavillon|habitation", t))
    return out


def programme(prompt: str, lang: Optional[str] = None) -> Dict[str, Any]:
    """Programme complet : liste des pièces par niveau, surfaces, toiture ; hypothèses écrites."""
    lu = lire(prompt)
    hyp: List[str] = []
    fr = (lang or ("pt" if PAIS == "PT" else "fr")) == "fr"

    def H(f: str, p: str) -> None:
        hyp.append(f if fr else p)

    chambres = lu.get("chambres")
    if chambres is None:
        chambres = 3
        H("Nombre de chambres non précisé : 3 chambres retenues.", "Número de quartos não indicado: 3 quartos considerados.")
    chambres = max(0, min(int(chambres), 6))
    niveaux = lu.get("niveaux") or (2 if chambres >= 5 else 1)
    if "niveaux" not in lu:
        H(f"Niveaux non précisés : {'plain-pied' if niveaux == 1 else 'R+1'} retenu.",
          f"Pisos não indicados: {'piso único' if niveaux == 1 else 'R/C + 1'} considerado.")
    ouverte = lu.get("cuisine_ouverte", True)
    if "cuisine_ouverte" not in lu:
        H("Cuisine ouverte sur le séjour retenue (non précisé).", "Cozinha aberta para a sala considerada (não indicado).")
    nb_sdb = lu.get("sdb") or (2 if chambres >= 4 else 1)

    pieces: List[Dict[str, Any]] = []

    def add(cle: str, niveau: int, n: Optional[int] = None) -> None:
        pieces.append({"cle": cle, "nom": nom(cle, lang, n), "zone": PIECES[cle][3], "surface": PIECES[cle][4], "niveau": niveau})

    nuit = 1 if niveaux == 2 else 0
    add("entree", 0)
    if ouverte:
        add("sejour_cuisine", 0)
    else:
        add("sejour", 0)
        add("cuisine", 0)
    add("wc", 0)
    if niveaux == 2:
        add("wc", 1)
    if lu.get("bureau"):
        add("bureau", 0)
    if lu.get("buanderie"):
        add("buanderie", 0)
    suite = bool(lu.get("suite")) and chambres >= 1
    k0 = 1
    if suite:
        add("suite", nuit)
        add("sde", nuit)
        k0 = 2
        nb_sdb = max(1, nb_sdb - 1)
    for k in range(k0, chambres + 1):
        add("chambre", nuit, k - (1 if suite else 0) if chambres - (1 if suite else 0) > 1 else None)
    for k in range(nb_sdb):
        add("sdb", nuit, (k + 1) if nb_sdb > 1 else None)
    garage = None
    if lu.get("garage"):
        garage = {"nom": nom("garage", lang), "surface": 36.0 if lu.get("garage_double") else 18.0,
                  "largeur": 6.0 if lu.get("garage_double") else 3.0}

    # Surface habitable demandée : les surfaces types sont mises à l'échelle (circulations ≈ 8 %).
    cible = lu.get("surface")
    somme = sum(p["surface"] for p in pieces)
    if cible:
        circ = (0.16 if niveaux == 2 else 0.08) * cible     # deux niveaux : hall + dégagement + escalier
        f = max(0.6, min(1.8, (cible - circ) / somme))
        for p in pieces:
            if p["cle"] not in ("wc",):
                p["surface"] = round(p["surface"] * f, 1)
        if abs(f - 1) > 0.25:
            H(f"Surfaces types ajustées (×{f:.2f}) pour viser {cible:.0f} m² habitables.",
              f"Áreas tipo ajustadas (×{f:.2f}) para {cible:.0f} m² de área útil.")
    else:
        H("Surface non précisée : surfaces types par pièce (modifiables dans le Studio).",
          "Área não indicada: áreas tipo por divisão (editáveis no Estúdio).")
    toiture = lu.get("toiture") or "duas_aguas"
    if "toiture" not in lu:
        H("Toiture deux pans retenue (non précisé).", "Cobertura de duas águas considerada (não indicado).")
    return {"pieces": pieces, "niveaux": niveaux, "garage": garage, "toiture": toiture, "surface_visee": cible,
            "chambres": chambres, "reconnu": lu["reconnu"], "lu": lu, "hypotheses": hyp}


def programme_depuis_ia(data: Any, lang: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Programme renvoyé par l'IA (repli si le prompt n'est pas reconnu) → même structure, valeurs bornées."""
    if not isinstance(data, dict):
        return None
    texte = []
    if data.get("chambres") is not None:
        texte.append(f"{int(data['chambres'])} chambres")
    if data.get("surface"):
        texte.append(f"{float(data['surface']):.0f} m2")
    if data.get("niveaux") == 2:
        texte.append("r+1")
    elif data.get("niveaux") == 1:
        texte.append("plain-pied")
    for k, mot in (("garage", "garage"), ("bureau", "bureau"), ("buanderie", "buanderie"), ("suite", "suite parentale")):
        if data.get(k):
            texte.append(mot)
    if data.get("cuisine_ouverte") is False:
        texte.append("cuisine fermée")
    if data.get("toiture") in ("plana", "quatro_aguas", "uma_agua", "duas_aguas"):
        texte.append({"plana": "toit plat", "quatro_aguas": "4 pans", "uma_agua": "monopente", "duas_aguas": "2 pans"}[data["toiture"]])
    if not texte:
        return None
    p = programme("maison " + " ".join(texte), lang)
    p["source"] = "ia"
    return p
