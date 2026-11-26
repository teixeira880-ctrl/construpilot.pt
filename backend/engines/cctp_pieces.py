"""Programme par pièce → articles « équipement par pièce » des lots Électricité et Plomberie.

Comme dans les CCTP d'architecte (« Prises (par pièce) » : Entrée, Cuisine, Chambre 1…), chaque pièce du
programme devient un article listant ses équipements, et chaque équipement une ligne quantifiée du DPGF.

Les quantités sont calculées par règle déterministe (jamais par l'IA) :
- Électricité : socle minimal NF C 15-100 (logements, amendement A5) — vérifié sur Legrand / IZI by EDF :
    séjour 5 PC (< 28 m²) ou 7 PC (≥ 28 m²) + 2 PC près des prises de communication, 2 RJ45 juxtaposées ;
    cuisine > 4 m² : 6 PC dont 4 au-dessus du plan de travail (3 si ≤ 4 m²), circuit 32 A cuisson,
    circuits spécialisés four et lave-vaisselle ; chambre : 3 PC ; salle d'eau : 1 PC hors volumes ;
    autres pièces > 4 m² (hors WC) : 1 PC ; chaque pièce : 1 point d'éclairage commandé depuis l'entrée.
  Le CCTP le présente comme une base minimale à compléter suivant les plans électricité.
- Plomberie : appareils et attentes usuels par type de pièce.
"""
from __future__ import annotations

import unicodedata

TYPES = {
    "sejour": "Séjour", "cuisine": "Cuisine", "chambre": "Chambre", "bureau": "Bureau", "sdb": "Salle de bain / salle d'eau",
    "wc": "WC", "entree": "Entrée", "circulation": "Circulation / dégagement", "buanderie": "Buanderie / cellier",
    "garage": "Garage", "exterieur": "Extérieur", "autre": "Autre pièce",
}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def type_piece(p: dict) -> str:
    t = p.get("type")
    if t in TYPES:
        return t
    n = _fold(p.get("nom", ""))
    for key, mots in (("sejour", ("sejour", "salon", "living", "salle a manger", "bibliotheque")), ("cuisine", ("cuisine",)),
                      ("sdb", ("salle de bain", "salle d'eau", "sdb", "sde", "douche")), ("wc", ("wc", "toilette")),
                      ("chambre", ("chambre", "suite")), ("bureau", ("bureau",)), ("entree", ("entree", "hall")),
                      ("circulation", ("degagement", "couloir", "circulation", "palier", "passerelle", "escalier")),
                      ("buanderie", ("buanderie", "cellier", "lingerie")), ("garage", ("garage",)),
                      ("exterieur", ("terrasse", "jardin", "exterieur", "balcon", "porche"))):
        if any(m in n for m in mots):
            return key
    return "autre"


def _surface(p: dict) -> float | None:
    try:
        s = float(str(p.get("surface")).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return s if s > 0 else None


def _titre(p: dict) -> str:
    nom = (p.get("nom") or TYPES[type_piece(p)]).strip()
    niv = (p.get("niveau") or "").strip()
    return (f"{nom} ({niv})" if niv else nom).upper()[:120]


def equipements_electricite(p: dict) -> list[tuple[int, str]]:
    t, s = type_piece(p), _surface(p)
    pl = (1, "Point d'éclairage en plafond équipé DCL, commandé depuis l'entrée de la pièce")
    if t == "sejour":
        return [pl, (5 if (s or 0) < 28 else 7, "PC 16 A+T"), (2, "PC 16 A+T à proximité des prises de communication"),
                (2, "Prises RJ45 juxtaposées")]
    if t == "cuisine":
        lst = [pl]
        if s is not None and s <= 4:
            lst.append((3, "PC 16 A+T au-dessus du plan de travail"))
        else:
            lst += [(4, "PC 16 A+T au-dessus du plan de travail"), (2, "PC 16 A+T")]
        return lst + [(1, "Sortie de câble 32 A+T pour appareil de cuisson"), (1, "PC 16 A+T sur circuit spécialisé four"),
                      (1, "PC 16 A+T sur circuit spécialisé lave-vaisselle"), (1, "PC 16 A+T pour hotte, à 1,80 m minimum du sol")]
    if t in ("chambre", "bureau"):
        return [pl, (3, "PC 16 A+T"), (1, "Prise RJ45")]
    if t == "sdb":
        return [pl, (1, "PC 16 A+T hors volumes (à plus de 60 cm de la douche ou de la baignoire)"),
                (1, "Liaison équipotentielle locale")]
    if t == "wc":
        return [pl]
    if t == "buanderie":
        return [pl, (1, "PC 16 A+T"), (1, "PC 16 A+T sur circuit spécialisé lave-linge")]
    if t == "garage":
        return [pl, (1, "PC 16 A+T")]
    if t == "exterieur":
        return [(1, "Point d'éclairage extérieur étanche, commandé depuis l'intérieur")]
    lst = [pl]                                                   # entrée, circulation, autre
    if s is None or s > 4:
        lst.append((1, "PC 16 A+T"))
    return lst


def equipements_plomberie(p: dict) -> list[tuple[int, str]]:
    t = type_piece(p)
    if t == "sdb":
        return [(1, "Lavabo ou meuble vasque avec mitigeur, siphon et vidage — alimentations EF/EC, évacuation"),
                (1, "Douche (receveur extra-plat ou douche à l'italienne) avec mitigeur thermostatique — alimentations EF/EC, évacuation")]
    if t == "wc":
        return [(1, "WC suspendu sur bâti-support ou WC au sol, réservoir double débit — alimentation EF, évacuation Ø 100")]
    if t == "cuisine":
        return [(1, "Attentes évier : alimentations EF/EC avec robinets d'arrêt, évacuation siphonnée"),
                (1, "Attentes lave-vaisselle : alimentation EF avec robinet d'arrêt, vidange siphonnée")]
    if t == "buanderie":
        return [(1, "Attentes lave-linge : alimentation EF avec robinet d'arrêt, vidange siphonnée")]
    if t == "exterieur":
        return [(1, "Robinet de puisage extérieur antigel")]
    return []


def articles_par_piece(code_lot: str, pieces: list[dict]) -> list[dict]:
    """Articles « par pièce » pour 'electricite' ou 'plomberie' (liste vide pour les autres lots)."""
    fn = {"electricite": equipements_electricite, "plomberie": equipements_plomberie}.get(code_lot)
    if not fn:
        return []
    out = []
    for p in pieces or []:
        eq = fn(p)
        extras = [str(x).strip()[:200] for x in (p.get("extras") or []) if str(x).strip()] if code_lot == "electricite" else []
        if not eq and not extras:
            continue
        lignes = [f"{q} {lib}" for q, lib in eq] + extras
        intro = ("Fourniture, pose et raccordement des équipements listés ci-dessous, socle minimal conforme à la "
                 "NF C 15-100 à compléter suivant les plans électricité de l'architecte :"
                 if code_lot == "electricite" else
                 "Fourniture, pose et raccordement des appareils et attentes ci-dessous ; modèles à valider par le maître "
                 "d'ouvrage et l'architecte avant commande :")
        out.append({"chapitre": "Équipements par pièce", "titre": _titre(p), "description": intro + "\n" + "\n".join(f"- {l}" for l in lignes),
                    "localisation": "Se référer aux plans de l'architecte.", "code": None, "source": "pieces",
                    "variantes": [{"libelle": lib, "unite": "u", "quantite": float(q)} for q, lib in eq]
                    + [{"libelle": x, "unite": "u", "quantite": None} for x in extras]})
    if code_lot == "electricite" and out:
        types = {type_piece(p) for p in pieces}
        communs = [(1, "Tableau de répartition avec dispositifs différentiels 30 mA, réserve de 20 % minimum"),
                   (1, "Tableau de communication (coffret VDI) avec dispositif de terminaison intérieur optique"),
                   (1, "Circuit d'alimentation de la production d'eau chaude sanitaire"),
                   (1, "Circuit d'alimentation de la ventilation mécanique"),
                   (1, "Détecteur autonome avertisseur de fumée (DAAF) conforme au Code de la construction et de l'habitation")]
        if "buanderie" not in types:
            communs.append((1, "PC 16 A+T sur circuit spécialisé lave-linge (emplacement suivant plans)"))
        out.append({"chapitre": "Équipements par pièce", "titre": "ÉQUIPEMENTS COMMUNS DU LOGEMENT",
                    "description": "Fourniture, pose et raccordement :\n" + "\n".join(f"- {q} {l}" for q, l in communs),
                    "localisation": "Se référer aux plans de l'architecte.", "code": None, "source": "pieces",
                    "variantes": [{"libelle": l, "unite": "u", "quantite": float(q)} for q, l in communs]})
    return out
