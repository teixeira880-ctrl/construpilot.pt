"""Function-calling contracts for the deterministic metré engine (validated server-side before execution)."""
from . import calibration, chains, dedupe, quantities

NUM_OR_NULL = {"type": ["number", "null"]}
STR_OR_NULL = {"type": ["string", "null"]}

READING = {"type": "object", "properties": {
    "label": {"type": "string"}, "value_m": NUM_OR_NULL,
    "candidates_m": {"type": "array", "items": {"type": "number"}, "description": "Lectures OCR concurrentes si la valeur n'est pas résolue"},
    "origin": {"type": "string", "enum": ["plan_reading", "native_text", "user_statement", "assumption"]},
    "plan_id": STR_OR_NULL, "page": {"type": ["integer", "null"]},
    "box": {"type": ["array", "null"], "items": {"type": "number"}, "description": "Zone source de la cote sur la page, normalisée [x0,y0,x1,y1] (0-1)"}},
    "required": ["label", "value_m", "candidates_m", "origin", "plan_id", "page", "box"], "additionalProperties": False}


def _fn(name, description, properties):
    return {"type": "function", "name": name, "description": description, "strict": True,
            "parameters": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}


METRE_TOOLS = [
    _fn("check_dimension_chain",
        "Somme déterministe d'une chaîne de cotes : portées intérieures + épaisseurs des murs réellement traversés, comparée au total déclaré. "
        "Ne ré-ajoute jamais les épaisseurs si la chaîne les inclut déjà. reference='axes' : demi-épaisseurs aux murs d'extrémité. "
        "Toute lecture non résolue rend le résultat indéterminé.",
        {"spans": {"type": "array", "items": READING}, "thicknesses": {"type": "array", "items": READING},
         "chain_includes_thickness": {"type": "boolean"}, "reference": {"type": "string", "enum": ["faces", "axes"]},
         "declared_total": {"anyOf": [READING, {"type": "null"}]}}),
    _fn("compare_dimension_values",
        "Différence arithmétique entre deux valeurs du même intervalle. Si intervalle ou référence diffèrent, l'écart est documenté sans être classé incohérence.",
        {"a": READING, "b": READING, "same_interval": {"type": "boolean"}, "same_reference": {"type": "boolean"}}),
    _fn("resolve_ambiguous_reading",
        "Tranche une lecture OCR ambiguë (ex. 13,27 / 13,72) UNIQUEMENT avec une preuve indépendante : texte natif PDF, zoom, déclaration utilisateur. "
        "La concordance arithmétique n'est jamais une preuve.",
        {"label": {"type": "string"}, "candidates_m": {"type": "array", "items": {"type": "number"}},
         "confirmations": {"type": "array", "items": {"type": "object", "properties": {
             "kind": {"type": "string", "enum": ["native_text", "zoom_crop", "user_statement", "arithmetic_fit"]}, "value_m": {"type": "number"}, "ref": STR_OR_NULL},
             "required": ["kind", "value_m", "ref"], "additionalProperties": False}},
         "arithmetic_fit_m": NUM_OR_NULL}),
    _fn("classify_strokes",
        "Classe des traits (calque, motif, flèches) en hachure / mobilier / axe / ligne de cote / caché / mur… Les traits non constructifs ou non classés n'entrent jamais dans un métré.",
        {"strokes": {"type": "array", "items": {"type": "object", "properties": {
            "stroke_id": {"type": "string"}, "kind": STR_OR_NULL, "layer": STR_OR_NULL, "pattern": STR_OR_NULL,
            "has_arrowheads": {"type": "boolean"}, "has_ticks": {"type": "boolean"}},
            "required": ["stroke_id", "kind", "layer", "pattern", "has_arrowheads", "has_ticks"], "additionalProperties": False}}}),
    _fn("dedupe_elements",
        "Unifie les observations d'un même élément vu en plan, élévation, nomenclature ou détail (repère F1/P02, ou position). Compte chaque élément une fois et conserve toutes les preuves.",
        {"observations": {"type": "array", "items": {"type": "object", "properties": {
            "obs_id": {"type": "string"}, "element_type": {"type": "string"}, "tag": STR_OR_NULL,
            "view": {"type": "string", "enum": ["plan", "section", "elevation", "schedule", "detail", "other"]},
            "dimensions": {"type": "object", "properties": {"width_m": NUM_OR_NULL, "height_m": NUM_OR_NULL, "length_m": NUM_OR_NULL},
                           "required": ["width_m", "height_m", "length_m"], "additionalProperties": False},
            "location": {"type": "object", "properties": {"level": STR_OR_NULL, "x_m": NUM_OR_NULL, "y_m": NUM_OR_NULL},
                         "required": ["level", "x_m", "y_m"], "additionalProperties": False}},
            "required": ["obs_id", "element_type", "tag", "view", "dimensions", "location"], "additionalProperties": False}}}),
    _fn("calculate_quantities",
        "Quantités par catégorie avec formule, déductions, net et état. wall_area : L × H − ouvertures selon deduction_rule EXPLICITE (full/none/threshold) ; "
        "hauteur absente → longueur seule. concrete_volume : emprise × hauteur, sans hauteur → emprise seule. roof_area : sans pente → surface projetée. "
        "packaged_units : quantité posée vs à commander. Aucune perte sans extra_pct/waste_pct explicite.",
        {"items": {"type": "array", "items": {"type": "object", "properties": {
            "category": {"type": "string", "enum": ["wall_area", "concrete_volume", "roof_area", "packaged_units"]},
            "element": {"type": "string"}, "location": STR_OR_NULL, "sources": {"type": "array", "items": {"type": "string"}},
            "length_m": NUM_OR_NULL, "height_m": NUM_OR_NULL, "width_m": NUM_OR_NULL, "area_m2": NUM_OR_NULL,
            "openings": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "width_m": NUM_OR_NULL, "height_m": NUM_OR_NULL},
                                                    "required": ["label", "width_m", "height_m"], "additionalProperties": False}},
            "deduction_rule": {"type": ["string", "null"], "enum": ["full", "none", "threshold", None]}, "deduction_threshold_m2": NUM_OR_NULL,
            "extra_pct": NUM_OR_NULL, "plan_area_m2": NUM_OR_NULL, "slope_deg": NUM_OR_NULL,
            "net_quantity": NUM_OR_NULL, "units_per_measure": NUM_OR_NULL, "pack_size": NUM_OR_NULL, "waste_pct": NUM_OR_NULL,
            "product": STR_OR_NULL, "unit": STR_OR_NULL},
            "required": ["category", "element", "location", "sources", "length_m", "height_m", "width_m", "area_m2", "openings", "deduction_rule",
                         "deduction_threshold_m2", "extra_pct", "plan_area_m2", "slope_deg", "net_quantity", "units_per_measure", "pack_size",
                         "waste_pct", "product", "unit"], "additionalProperties": False}}}),
]
METRE_TOOLS += [
    _fn("calibrate_view",
        "Calibre l'échelle d'UNE vue ou d'UN détail à partir de ses cotes explicites lisibles (longueur en pixels ↔ valeur). Détecte échelles multiples, "
        "déformation h/v d'un scan et écart avec l'échelle du cartouche (PDF redimensionné). Une calibration ne vaut que pour sa vue.",
        {"view_id": {"type": "string"}, "references": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "value_m": {"type": "number"}, "px_length": {"type": "number"}, "axis": {"type": ["string", "null"], "enum": ["h", "v", None]}},
            "required": ["label", "value_m", "px_length", "axis"], "additionalProperties": False}},
         "declared_scale": STR_OR_NULL, "dpi": NUM_OR_NULL}),
    _fn("measure_pixels",
        "Convertit une longueur mesurée en pixels avec la calibration d'une vue (résultat de calibrate_view). Refusé si la calibration est non fiable : "
        "aucune mesure en pixels n'est alors présentée comme confirmée.",
        {"calibration": {"type": "object", "properties": {"view_id": {"type": "string"}, "status": {"type": "string", "enum": ["reliable", "per_axis", "unreliable"]},
                                                          "px_per_m": NUM_OR_NULL, "px_per_m_by_axis": {"type": ["object", "null"], "properties": {"h": NUM_OR_NULL, "v": NUM_OR_NULL},
                                                                                                        "required": ["h", "v"], "additionalProperties": False},
                                                          "measurements_allowed": {"type": "boolean"}, "spread_pct": NUM_OR_NULL, "reasons": {"type": "array", "items": {"type": "string"}}},
                         "required": ["view_id", "status", "px_per_m", "px_per_m_by_axis", "measurements_allowed", "spread_pct", "reasons"], "additionalProperties": False},
         "label": {"type": "string"}, "px_length": {"type": "number"}, "axis": {"type": ["string", "null"], "enum": ["h", "v", None]}}),
]
METRE_TOOL_NAMES = {t["name"] for t in METRE_TOOLS}

METRE_INSTRUCTIONS = """Pour chaque lecture issue d'un plan attaché, renseigne plan_id, page et box (zone normalisée de la cote) afin que l'utilisateur
puisse ouvrir le recadrage et corriger la lecture. Métré et contrôle de cotes : tout calcul (somme de chaîne, écart entre cotes, surface, volume, déduction, comptage) passe par les outils
check_dimension_chain, compare_dimension_values, resolve_ambiguous_reading, classify_strokes, dedupe_elements et calculate_quantities ; ne calcule jamais
ces valeurs de tête. Présente leurs entrées, formules, résultats et états (confirmé / probable / indéterminé / non vérifiable) tels que renvoyés.
Toute mesure en pixels passe par calibrate_view (par vue / détail) puis measure_pixels ; sans calibration fiable, seules les cotes explicites sont utilisées.
Une différence entre cotes est un point de lecture ou de cohérence à éclaircir, jamais une accusation d'erreur de calcul du BET. Aucune tolérance
d'exécution, aucun pourcentage de perte et aucune règle de déduction ne sont appliqués sans être explicitement demandés ou référencés.
Plans de structure (ferraillage, poutres, dalles) : une étude d'ouvrage les prend en compte au même titre que l'architecture. Les nomenclatures d'aciers et
de treillis se lisent avec read_rebar_schedule (jamais de tête) ; les masses, totaux et écarts avec les récapitulatifs sont ceux renvoyés par l'outil. Une
nomenclature marquée « partielle » ne permet aucune extrapolation au niveau complet.
Volumes de béton d'un niveau (murs, poteaux, dalle, retombées) : uniquement avec compute_concrete_volumes, en lui passant le DXF/DWG du niveau, le plan de
coffrage PDF et le cahier de coupes s'ils sont joints. Règle des niveaux : l'arase supérieure des murs est l'arase inférieure du plancher haut (AS plancher −
épaisseur), sauf indication contraire imprimée ; la hauteur est prise par zone de coupe. Présente les volumes par élément avec la formule, la source de chaque
niveau et l'état renvoyés ; si une donnée manque (niveau de base, épaisseur, hauteur de poutre), demande-la à l'utilisateur au lieu de la supposer. La lecture
visuelle du cahier de coupes est facturée : ne passe allow_vision=true qu'avec l'accord de l'utilisateur (ou si les coupes ont déjà été lues)."""


def run_metre_tool(name: str, args: dict) -> dict:
    if name == "check_dimension_chain":
        clean = {k: v for k, v in args.items() if k != "declared_total"}
        return {"ok": True, **chains.check_dimension_chain(**clean, declared_total=args.get("declared_total"))}
    if name == "compare_dimension_values":
        return {"ok": True, **chains.compare_values(args["a"], args["b"], same_interval=args["same_interval"], same_reference=args["same_reference"])}
    if name == "resolve_ambiguous_reading":
        return {"ok": True, **chains.resolve_reading(label=args["label"], candidates_m=args["candidates_m"],
                                                     confirmations=args.get("confirmations"), arithmetic_fit_m=args.get("arithmetic_fit_m"))}
    if name == "classify_strokes":
        return {"ok": True, **dedupe.classify_strokes(args["strokes"])}
    if name == "dedupe_elements":
        return {"ok": True, **dedupe.dedupe_elements(args["observations"])}
    if name == "calculate_quantities":
        return {"ok": True, **quantities.calculate_quantities(args["items"])}
    if name == "calibrate_view":
        return {"ok": True, **calibration.calibrate_view(view_id=args["view_id"], references=args["references"],
                                                          declared_scale=args.get("declared_scale"), dpi=args.get("dpi"))}
    if name == "measure_pixels":
        return {"ok": True, **calibration.measure_pixels(calibration=args["calibration"], label=args["label"], px_length=args["px_length"], axis=args.get("axis"))}
    return {"ok": False, "error": "Outil métré inconnu"}
