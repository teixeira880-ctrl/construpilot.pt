"""Photo d'un croquis papier (ou d'un plan esquissé) → traits → même nettoyage que le dessin à main levée.

L'IA ne fait que lire le dessin : murs, ouvertures, noms des pièces et cotes écrites. L'échelle, le redressement, les
raccords, les murs extérieurs et la maquette sont faits par `croquis.nettoyer` (déterministe). Ce qui n'a pas pu être
lu est renvoyé dans les avertissements ; rien n'est inventé pour « compléter » le dessin.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from engines.atelier_archi import croquis as C

log = logging.getLogger(__name__)

SYSTEME = ("Tu lis des croquis d'architecture dessinés à la main (plans de maison, d'appartement, d'extension). "
           "Tu relèves fidèlement ce qui est dessiné et écrit, sans rien ajouter. Tu réponds UNIQUEMENT en JSON valide.")

CONSIGNE = """Relève le plan dessiné sur l'image.
Repère : origine au coin bas-gauche du bâtiment, x vers la droite, y vers le HAUT de l'image, en MÈTRES.
Utilise les cotes écrites sur le croquis pour l'échelle ; s'il n'y en a pas, estime au mieux et mets "echelle_sure": false.
Réponds avec ce JSON :
{
 "murs": [{"a": [x, y], "b": [x, y], "exterieur": true|false}],
 "ouvertures": [{"type": "porte"|"fenetre"|"baie"|"portail", "a": [x, y], "b": [x, y]}],
 "pieces": [{"nom": "texte écrit dans la pièce", "x": x, "y": y}],
 "cotes": [{"a": [x, y], "b": [x, y], "m": longueur écrite en mètres}],
 "echelle_sure": true|false,
 "illisible": ["ce que tu n'as pas pu lire"]
}
Règles : un mur = un segment droit (découpe les murs aux angles) ; une ouverture = le segment qu'elle occupe sur son mur ;
les noms de pièces sont recopiés tels qu'écrits ; aucun mobilier ; aucun mur qui n'est pas dessiné."""


def _float_pt(p: Any) -> List[float] | None:
    try:
        return [float(p[0]), float(p[1])]
    except (TypeError, ValueError, IndexError):
        return None


def traits_depuis_lecture(data: Dict[str, Any]) -> Dict[str, Any]:
    traits: List[Dict[str, Any]] = []
    for m in (data.get("murs") or [])[:600]:
        a, b = _float_pt(m.get("a")), _float_pt(m.get("b"))
        if a and b:
            traits.append({"type": "mur_ext" if m.get("exterieur") else "cloison", "points": [a, b]})
    for o in (data.get("ouvertures") or [])[:300]:
        a, b = _float_pt(o.get("a")), _float_pt(o.get("b"))
        if a and b and o.get("type") in C.OUVERTURES:
            traits.append({"type": o["type"], "points": [a, b]})
    textes = []
    for p in (data.get("pieces") or [])[:120]:
        try:
            textes.append({"x": float(p["x"]), "y": float(p["y"]), "nom": str(p["nom"])[:40]})
        except (KeyError, TypeError, ValueError):
            continue
    return {"traits": traits, "textes": textes}


async def lire_photo(image_b64: str) -> Dict[str, Any]:
    from engines import ai
    brut = await ai._complete(SYSTEME, CONSIGNE, images=[image_b64], feature="atelier_croquis_photo")
    data = ai._json(brut, {})
    if not isinstance(data, dict) or not data.get("murs"):
        raise C.ErreurCroquis(C._txt("Aucun mur n'a pu être lu sur la photo : photographiez le croquis bien à plat, en entier, avec un bon éclairage.",
                                     "Não foi possível ler paredes na fotografia: fotografe o esboço bem plano, inteiro e com boa luz."))
    t = traits_depuis_lecture(data)
    cotes = [c for c in (data.get("cotes") or [])[:40] if isinstance(c, dict)]
    r = C.nettoyer(t["traits"], t["textes"], cotes=cotes, y_bas=False)     # les cotes écrites recalent l'échelle relevée
    r["avisos"].insert(0, C._txt("Plan relu sur la photo par l'IA puis redressé : contrôlez chaque cote avant de continuer.",
                                 "Planta lida na fotografia pela IA e depois endireitada: confirme cada cota antes de continuar."))
    if data.get("echelle_sure") is False:
        r["avisos"].insert(1, C._txt("Aucune cote lisible sur le croquis : l'échelle est estimée. Saisissez une cote connue dans le Studio.",
                                     "Nenhuma cota legível no esboço: a escala é estimada. Introduza uma cota conhecida no Estúdio."))
    for x in (data.get("illisible") or [])[:8]:
        r["avisos"].append(C._txt("Non lu : ", "Não lido: ") + str(x)[:160])
    r["lecture"] = {"murs": len(data.get("murs") or []), "cotes": data.get("cotes") or []}
    return r

