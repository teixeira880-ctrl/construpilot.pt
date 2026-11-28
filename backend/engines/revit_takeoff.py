"""Métré Revit (.rvt) à partir de la traduction Autodesk Model Derivative.

Entrées : l'arbre d'objets (metadata/{guid}) et la collection COMPLÈTE de propriétés de la vue 3D.
Sortie : quantités par niveau → ouvrage → type, + traçabilité élément par élément (id Revit),
pour que l'entreprise puisse contrôler chaque mur, dalle, porte…

Règles :
  - on ne lit que ce que Revit a calculé (Surface, Volume, Longueur…) : rien n'est estimé ;
  - une valeur sans unité reconnue est EXCLUE des totaux et signalée (jamais d'unité devinée) ;
  - les éléments démolis (phase de démolition renseignée) sont sortis des totaux et listés à part ;
  - un sous-composant (panneau de mur-rideau imbriqué, limon d'escalier…) n'est pas recompté
    dans le total de son élément parent ;
  - fonctionne avec un Revit en anglais, français, portugais ou espagnol, en métrique ou impérial.
"""
from __future__ import annotations

import re
import unicodedata
from collections import OrderedDict

MAX_TRACE = 8000

# ── Catégories Revit (EN / FR / PT / ES) → ouvrage ConstruPilot + unité principale du métré ──────────
_CATEGORIES: list[tuple[tuple[str, ...], str, str]] = [
    (("walls", "murs", "paredes", "muros"), "Murs", "m2"),
    (("curtain panels", "panneaux de murs-rideaux", "painéis de cortina", "paneles de muro cortina"), "Murs-rideaux (panneaux)", "m2"),
    (("curtain wall mullions", "meneaux de murs-rideaux", "montantes de cortina", "montantes de muro cortina"), "Murs-rideaux (meneaux)", "ml"),
    (("floors", "sols", "pisos", "suelos", "lajes"), "Dalles / planchers", "m2"),
    (("structural foundations", "fondations", "fondations de structure", "fundações estruturais", "fundaciones estructurales"), "Fondations", "m3"),
    (("structural columns", "poteaux porteurs", "pilares estruturais", "pilares estructurales"), "Poteaux", "m3"),
    (("columns", "poteaux", "pilares"), "Poteaux (architecturaux)", "u"),
    (("structural framing", "ossature", "estrutura", "armazón estructural", "vigas"), "Poutres / ossature", "m3"),
    (("roofs", "toits", "coberturas", "cubiertas"), "Toitures", "m2"),
    (("ceilings", "plafonds", "forros", "techos"), "Plafonds", "m2"),
    (("doors", "portes", "portas", "puertas"), "Portes", "u"),
    (("windows", "fenêtres", "fenetres", "janelas", "ventanas"), "Fenêtres", "u"),
    (("stairs", "escaliers", "escadas", "escaleras"), "Escaliers", "u"),
    (("railings", "garde-corps", "guarda-corpos", "barandillas"), "Garde-corps", "ml"),
    (("ramps", "rampes", "rampas"), "Rampes", "u"),
    (("rooms", "pièces", "pieces", "ambientes", "habitaciones"), "Pièces (surfaces)", "m2"),
    (("plumbing fixtures", "installations de plomberie", "aparelhos sanitários", "aparatos sanitarios"), "Plomberie (appareils)", "u"),
    (("pipes", "canalisations", "tubulações", "tuberías"), "Plomberie (canalisations)", "ml"),
    (("ducts", "gaines", "dutos", "conductos"), "CVC (gaines)", "ml"),
    (("mechanical equipment", "équipement mécanique", "equipamento mecânico", "equipos mecánicos"), "CVC (équipements)", "u"),
    (("electrical fixtures", "installations électriques", "dispositivos elétricos", "aparatos eléctricos"), "Électricité (appareillage)", "u"),
    (("lighting fixtures", "luminaires", "luminárias", "luminarias"), "Électricité (luminaires)", "u"),
    (("cable trays", "chemins de câbles", "eletrocalhas", "bandejas de cables"), "Électricité (chemins de câbles)", "ml"),
    (("casework", "meubles de rangement", "marcenaria", "mobiliario de obra"), "Agencement", "u"),
    (("furniture", "mobilier", "mobiliário", "mobiliario"), "Mobilier", "u"),
    (("generic models", "modèles génériques", "modelos genéricos"), "Modèles génériques", "u"),
    (("structural rebar", "armatures", "armaduras", "armadura estructural"), "Armatures", "kg"),
    (("toposolid", "topography", "topographie", "topografia", "topografía"), "Terrain", "m2"),
]
_PT_LABELS = {
    "Murs": "Paredes", "Murs-rideaux (panneaux)": "Fachadas-cortina (painéis)", "Murs-rideaux (meneaux)": "Fachadas-cortina (montantes)",
    "Dalles / planchers": "Lajes / pavimentos", "Fondations": "Fundações", "Poteaux": "Pilares", "Poteaux (architecturaux)": "Pilares (arquitetura)",
    "Poutres / ossature": "Vigas / estrutura", "Toitures": "Coberturas", "Plafonds": "Tetos", "Portes": "Portas", "Fenêtres": "Janelas",
    "Escaliers": "Escadas", "Garde-corps": "Guarda-corpos", "Rampes": "Rampas", "Pièces (surfaces)": "Compartimentos (áreas)",
    "Plomberie (appareils)": "Canalização (aparelhos sanitários)", "Plomberie (canalisations)": "Canalização (tubagens)",
    "CVC (gaines)": "AVAC (condutas)", "CVC (équipements)": "AVAC (equipamentos)", "Électricité (appareillage)": "Eletricidade (aparelhagem)",
    "Électricité (luminaires)": "Eletricidade (luminárias)", "Électricité (chemins de câbles)": "Eletricidade (caminhos de cabos)",
    "Agencement": "Carpintarias / mobiliário fixo", "Mobilier": "Mobiliário", "Modèles génériques": "Modelos genéricos",
    "Armatures": "Armaduras", "Terrain": "Terreno",
}
_TEXT = {
    "fr": {"no_level": "Sans niveau", "unit_note": "{u} non fourni par Revit pour ce type : comptage à l'unité",
           "w_units": "{n} élément(s) avec une valeur dont l'unité n'est pas reconnue : exclue(s) des totaux (voir colonne « non lu »).",
           "w_demo": "{n} élément(s) en phase « démoli » : hors totaux, listés à part.",
           "w_level": "{n} élément(s) sans niveau Revit : regroupés sous « Sans niveau ».",
           "w_sub": "{n} sous-composant(s) (ex. panneaux imbriqués, limons) non recomptés : inclus dans leur élément parent.",
           "w_empty": "Aucun élément constructif trouvé dans la vue 3D : vérifiez que le modèle Revit contient une vue 3D avec les éléments visibles.",
           "method": "Quantités lues dans les paramètres calculés par Revit (Surface, Volume, Longueur — nettes des ouvertures pour les murs), "
                     "aucune estimation par ratio. Chaque ligne renvoie aux identifiants Revit pour contrôle."},
    "pt": {"no_level": "Sem nível", "unit_note": "{u} não fornecido pelo Revit para este tipo: contagem à unidade",
           "w_units": "{n} elemento(s) com um valor cuja unidade não é reconhecida: excluído(s) dos totais (ver coluna « não lido »).",
           "w_demo": "{n} elemento(s) na fase « demolido »: fora dos totais, listados à parte.",
           "w_level": "{n} elemento(s) sem nível Revit: agrupados em « Sem nível ».",
           "w_sub": "{n} subcomponente(s) (ex. painéis encaixados, pernas de escada) não recontados: incluídos no elemento principal.",
           "w_empty": "Nenhum elemento construtivo encontrado na vista 3D: verifique se o modelo Revit tem uma vista 3D com os elementos visíveis.",
           "method": "Quantidades lidas nos parâmetros calculados pelo Revit (Área, Volume, Comprimento — áreas de paredes já sem os vãos), "
                     "sem qualquer estimativa por rácio. Cada linha remete para os identificadores Revit para controlo."},
}


def label(ouvrage: str, lang: str) -> str:
    return _PT_LABELS.get(ouvrage, ouvrage) if lang == "pt" else ouvrage


# Catégories sans quantité de chantier : on ne les compte pas comme ouvrages.
_IGNORED = {"levels", "niveaux", "níveis", "niveles", "grids", "quadrillages", "grades", "rejillas", "cameras", "caméras",
            "views", "vues", "lines", "lignes", "linhas", "líneas", "room separation", "séparation de pièces",
            "project information", "informations sur le projet", "sheets", "feuilles", "<sketch>", "<esquisse>",
            "reference planes", "plans de référence", "scope boxes", "zones de définition", "rvt links", "liens rvt",
            "analytical nodes", "nœuds analytiques", "center line", "ligne d'axe", "property lines", "limites de propriété"}

# ── Paramètres Revit lus (EN / FR / PT / ES) ─────────────────────────────────────────────────────────
_KEYS = {
    "area": ("area", "surface", "área", "area"),
    "volume": ("volume", "volumen"),
    "length": ("length", "longueur", "comprimento", "longitud"),
    "width": ("width", "largeur", "largura", "anchura", "thickness", "épaisseur", "epaisseur", "espessura", "espesor",
              "default thickness", "épaisseur par défaut", "espessura padrão", "grosor por defecto"),
    "height": ("unconnected height", "hauteur non connectée", "altura desconectada", "altura desconectada", "height", "hauteur", "altura"),
    "level": ("base constraint", "contrainte inférieure", "contrainte de base", "restrição da base", "restricción de base",
              "level", "niveau", "nível", "nivel", "base level", "niveau de base", "nível base", "nivel base",
              "reference level", "niveau de référence", "nível de referência", "nivel de referencia",
              "schedule level", "niveau de nomenclature"),
    "material": ("structural material", "matériau structurel", "material estrutural", "material estructural", "material", "matériau", "materiau"),
    "type_name": ("type name", "nom du type", "nome do tipo", "nombre de tipo"),
    "demolished": ("phase demolished", "phase de démolition", "fase demolida", "fase de demolición"),
    "rebar_weight": ("total bar length", "longueur totale de barre"),
}
_NONE_VALUES = {"", "none", "aucun", "aucune", "nenhum", "nenhuma", "ninguno", "ninguna", "-"}


def _norm(text) -> str:
    text = unicodedata.normalize("NFKC", str(text or "")).strip().lower()
    return re.sub(r"\s+", " ", text.replace("revit ", "", 1) if text.startswith("revit ") else text)


def category_info(name: str) -> tuple[str, str] | None:
    """(ouvrage, unité principale) ou None si catégorie sans quantité de chantier."""
    n = _norm(name)
    if n in _IGNORED or n.startswith("<"):
        return None
    for words, label, unit in _CATEGORIES:
        if n in words:
            return label, unit
    return (str(name).strip() or "Autres", "u")


# ── Unités ───────────────────────────────────────────────────────────────────────────────────────────
_NUM = r"[-+]?\d{1,3}(?:[   .,]\d{3})*(?:[.,]\d+)?|[-+]?\d+(?:[.,]\d+)?"
_UNIT_FACTORS = {
    "length": {"m": 1.0, "mm": 0.001, "cm": 0.01, "dm": 0.1, "ft": 0.3048, "'": 0.3048, "in": 0.0254, '"': 0.0254},
    "area": {"m^2": 1.0, "m²": 1.0, "m2": 1.0, "cm^2": 1e-4, "cm²": 1e-4, "mm^2": 1e-6, "mm²": 1e-6,
             "ft^2": 0.09290304, "ft²": 0.09290304, "sf": 0.09290304, "sq ft": 0.09290304},
    "volume": {"m^3": 1.0, "m³": 1.0, "m3": 1.0, "cm^3": 1e-6, "cm³": 1e-6, "mm^3": 1e-9, "mm³": 1e-9, "l": 0.001,
               "ft^3": 0.028316846592, "ft³": 0.028316846592, "cf": 0.028316846592, "cu ft": 0.028316846592,
               "yd^3": 0.764554857984, "yd³": 0.764554857984, "cy": 0.764554857984},
}


def _to_float(token: str) -> float:
    t = token.replace(" ", "").replace(" ", "").replace(" ", "")
    if "," in t and "." in t:  # séparateur de milliers + décimal
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:  # Revit en français / portugais : virgule décimale (« 12,500 m² » = 12,5 m²)
        t = t.replace(",", ".")
    return float(t)


def parse_quantity(value, kind: str) -> float | None:
    """Convertit une valeur Revit affichée (« 12,50 m² », « 10' - 6" », « 150 SF ») en m / m² / m³.

    Renvoie None si l'unité n'est pas reconnue : la valeur n'entre alors dans aucun total.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None  # nombre sans unité : on ne devine pas
    s = str(value).strip()
    if not s:
        return None
    if kind == "length":
        m = re.fullmatch(r"\s*([-+]?\d+(?:[.,]\d+)?)\s*'\s*-?\s*(?:(\d+(?:[.,]\d+)?)(?:\s+(\d+)/(\d+))?\s*\")?\s*", s)
        if m:  # pieds-pouces Revit : 10' - 6 1/2"
            inches = float((m.group(2) or "0").replace(",", ".")) + (int(m.group(3)) / int(m.group(4)) if m.group(3) else 0)
            return float(m.group(1).replace(",", ".")) * 0.3048 + inches * 0.0254
    m = re.fullmatch(rf"\s*({_NUM})\s*([a-zA-Z²³^'\"0-9 ]*?)\s*", s)
    if not m:
        return None
    unit = re.sub(r"\s+", " ", m.group(2).strip().lower())
    factors = _UNIT_FACTORS[kind]
    if unit not in factors:
        return None
    try:
        return _to_float(m.group(1)) * factors[unit]
    except ValueError:
        return None


# ── Propriétés ──────────────────────────────────────────────────────────────────────────────────────
def _flat(props: dict) -> dict[str, object]:
    """Toutes les propriétés, groupes aplatis, clés normalisées (le premier groupe gagne)."""
    out: dict[str, object] = {}
    for group, values in (props or {}).items():
        if isinstance(values, dict):
            for k, v in values.items():
                out.setdefault(_norm(k), v)
        else:
            out.setdefault(_norm(group), values)
    return out


def _pick(flat: dict, field: str):
    for key in _KEYS[field]:
        v = flat.get(key)
        if v not in (None, "") and _norm(v) not in _NONE_VALUES:
            return v
    return None


def _element_id(name: str) -> str | None:
    m = re.search(r"\[(\d+)\]\s*$", name or "")
    return m.group(1) if m else None


# ── Arbre d'objets ──────────────────────────────────────────────────────────────────────────────────
def index_tree(tree: dict | list) -> dict[int, dict]:
    """objectid → {category, family, type, type_id, depth, top_instance}.

    Revit traduit : racine (modèle) → catégorie → famille → type → instance → sous-composants.
    """
    roots = tree.get("data", {}).get("objects", []) if isinstance(tree, dict) else (tree or [])
    index: dict[int, dict] = {}

    def walk(node, path, top):
        oid = node.get("objectid")
        depth = len(path)
        is_instance = depth == 4
        info = {"depth": depth, "name": node.get("name"),
                "category": path[1]["name"] if depth > 1 else node.get("name") if depth == 1 else None,
                "family": path[2]["name"] if depth > 2 else None,
                "type": path[3]["name"] if depth > 3 else None,
                "type_id": path[3]["objectid"] if depth > 3 else None,
                "top_instance": oid if is_instance else top}
        if oid is not None:
            index[oid] = info
        for child in node.get("objects") or []:
            walk(child, path + [{"name": node.get("name"), "objectid": oid}], info["top_instance"])

    for root in roots:
        walk(root, [], None)
    return index


# ── Métré ───────────────────────────────────────────────────────────────────────────────────────────
def _r(x, nd=3):
    return round(x, nd) if x is not None else None


def takeoff(collection: list[dict], tree: dict | list, *, filename: str = "", lang: str = "fr") -> dict:
    """Métré complet d'un modèle Revit traduit. Pur, déterministe (même fichier → mêmes chiffres)."""
    tx = _TEXT.get(lang, _TEXT["fr"])
    index = index_tree(tree)
    props_by_id = {o.get("objectid"): o for o in collection or [] if o.get("objectid") is not None}
    flat_cache: dict[int, dict] = {}

    def flat(oid):
        if oid not in flat_cache:
            flat_cache[oid] = _flat((props_by_id.get(oid) or {}).get("properties") or {})
        return flat_cache[oid]

    rows: "OrderedDict[tuple, dict]" = OrderedDict()
    elements, demolished, warnings = [], [], []
    unknown_units, sub_components, no_level = 0, 0, 0

    for oid, info in sorted(index.items()):
        if info["depth"] < 4:
            continue
        if info["depth"] > 4:
            sub_components += 1
            continue
        cat = category_info(info["category"] or "")
        if cat is None:
            continue
        ouvrage, unit = cat
        ouvrage = label(ouvrage, lang)
        own, typ = flat(oid), flat(info["type_id"]) if info["type_id"] is not None else {}

        def val(field, kind):
            raw = _pick(own, field)
            if raw is None and field in ("width", "height", "material"):
                raw = _pick(typ, field)  # paramètres de type (largeur de porte, épaisseur de mur…)
            if raw is None:
                return None, None
            parsed = parse_quantity(raw, kind) if kind else raw
            return parsed, raw

        area, area_raw = val("area", "area")
        volume, vol_raw = val("volume", "volume")
        length, len_raw = val("length", "length")
        width, _ = val("width", "length")
        height, _ = val("height", "length")
        material, _ = val("material", None)
        level = _pick(own, "level")
        bad = [r for p, r in ((area, area_raw), (volume, vol_raw), (length, len_raw)) if r is not None and p is None]
        if bad:
            unknown_units += 1
        type_name = info["type"] or _pick(own, "type_name") or "—"
        element = {"objectid": oid, "revit_id": _element_id(info["name"]), "external_id": (props_by_id.get(oid) or {}).get("externalId"),
                   "ouvrage": ouvrage, "category": info["category"], "family": info["family"], "type": type_name,
                   "level": str(level) if level is not None else tx["no_level"], "material": str(material) if material else None,
                   "area_m2": _r(area), "volume_m3": _r(volume), "length_m": _r(length), "width_m": _r(width), "height_m": _r(height),
                   "unparsed": [str(b) for b in bad] or None}
        if _pick(own, "demolished") is not None:
            demolished.append(element)
            continue
        if level is None:
            no_level += 1
        elements.append(element)
        key = (element["level"], ouvrage, info["family"] or "", type_name)
        row = rows.setdefault(key, {"level": element["level"], "ouvrage": ouvrage, "family": info["family"], "type": type_name,
                                    "unit": unit, "count": 0, "area_m2": 0.0, "volume_m3": 0.0, "length_m": 0.0,
                                    "materials": set(), "revit_ids": []})
        row["count"] += 1
        row["area_m2"] += area or 0
        row["volume_m3"] += volume or 0
        row["length_m"] += length or 0
        if material:
            row["materials"].add(str(material))
        if element["revit_id"] and len(row["revit_ids"]) < 400:
            row["revit_ids"].append(element["revit_id"])

    out_rows = []
    for row in rows.values():
        row["materials"] = sorted(row["materials"])
        for k in ("area_m2", "volume_m3", "length_m"):
            row[k] = _r(row[k]) or None
        row["quantity"] = {"m2": row["area_m2"], "m3": row["volume_m3"], "ml": row["length_m"], "u": row["count"]}.get(row["unit"])
        if row["quantity"] is None:  # unité principale absente du modèle → repli sur le comptage, signalé
            row["quantity_note"] = tx["unit_note"].format(u=row["unit"])
            row["unit"], row["quantity"] = "u", row["count"]
        out_rows.append(row)

    by_ouvrage: "OrderedDict[str, dict]" = OrderedDict()
    for row in out_rows:
        b = by_ouvrage.setdefault(row["ouvrage"], {"count": 0, "total_area_m2": 0.0, "total_volume_m3": 0.0, "total_length_m": 0.0, "source": "revit_properties"})
        b["count"] += row["count"]
        b["total_area_m2"] += row["area_m2"] or 0
        b["total_volume_m3"] += row["volume_m3"] or 0
        b["total_length_m"] += row["length_m"] or 0
    for b in by_ouvrage.values():
        for k in ("total_area_m2", "total_volume_m3", "total_length_m"):
            b[k] = round(b[k], 2) or None

    levels = list(OrderedDict.fromkeys(r["level"] for r in out_rows))
    if unknown_units:
        warnings.append(tx["w_units"].format(n=unknown_units))
    if demolished:
        warnings.append(tx["w_demo"].format(n=len(demolished)))
    if no_level:
        warnings.append(tx["w_level"].format(n=no_level))
    if sub_components:
        warnings.append(tx["w_sub"].format(n=sub_components))
    if not elements:
        warnings.append(tx["w_empty"])
    return {"source": "revit", "filename": filename, "elements_count": len(elements), "levels": levels,
            "rows": out_rows, "by_ouvrage": dict(by_ouvrage), "elements": elements[:MAX_TRACE],
            "elements_truncated": len(elements) > MAX_TRACE, "demolished": demolished[:2000], "warnings": warnings,
            "method": tx["method"], "lang": lang}
