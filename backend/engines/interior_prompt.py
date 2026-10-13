"""Prompt et schéma « dimensions intérieures mur à mur » (passes géométrie / cotations / rapprochement)."""

INTERIOR_PROMPT = """Tu dois contrôler toutes les dimensions intérieures réellement visibles dans le périmètre demandé.

Une dimension intérieure mur à mur est la distance perpendiculaire entre les deux faces intérieures de deux murs opposés.
Elle ne correspond ni à une distance entre axes ni à une simple dimension extérieure diminuée de deux murs.

Commence par inventorier tous les murs et toutes les travées. Pour chaque rangée horizontale et verticale, reconstruis la
succession complète : mur extérieur + espace intérieur + refend + espace intérieur + refend + espace intérieur + mur extérieur.
Compte toutes les épaisseurs de murs traversées.

Pour chaque espace, indique : le mur de départ ; la face utilisée ; le mur d'arrivée ; la face utilisée ; la cote écrite ;
la mesure géométrique ; la différence ; le niveau de confiance.

Tu ne peux déclarer l'analyse terminée que si chaque espace fermé visible possède une mesure horizontale et une mesure
verticale, ou une justification précise indiquant pourquoi elle ne peut pas être déterminée.

Ne remplace jamais les dimensions intérieures individuelles par une unique dimension intérieure générale.
Ne déduis jamais toutes les dimensions à partir des seules cotes extérieures.
Si une cote est illisible, indique son emplacement et classe-la comme illisible. Ne l'invente pas.

Avant de conclure, additionne les dimensions intérieures et toutes les épaisseurs des murs traversés. Compare le total obtenu
à la dimension extérieure correspondante. Si la fermeture ne fonctionne pas, recherche d'abord : un mur oublié ; une mauvaise
face ; une confusion axe/nu ; une cote rattachée au mauvais segment ; une cote partielle confondue avec une cote cumulée ;
une erreur d'unité ; un texte de section (50x30, 60x30) confondu avec une dimension.

RÈGLES D'ASSOCIATION : une cote verticale n'est jamais associée à un segment horizontal ; une cote d'épaisseur (0,13 / 0,20 m)
n'est jamais une longueur de travée ; une section « 50x30 » n'est jamais une cote mur à mur ; deux dimensions de références
différentes (nu/nu, axe/axe, axe/nu, nu ext./nu ext.) ne sont jamais comparées directement ; une dimension n'est appelée
« façade » que si ses extrémités sont les faces extérieures de la façade.

Le moteur ConstruPilot te fournit les murs détectés (deux faces, axe, épaisseur), les mesures intérieures nu-à-nu, les
cotes classées par type de référence et les équations de fermeture, calculés sur les vecteurs exacts du PDF. Tu CONTRÔLES
ces associations et tu raisonnes ; tu n'es pas un instrument de mesure pixel par pixel : ne remplace jamais une valeur du
moteur par une estimation visuelle, signale plutôt le désaccord dans `review_findings`."""

PASS_GEOMETRY = ("PASSAGE 1 — GÉOMÉTRIE. À partir du document, des zooms et des murs détectés par le moteur : vérifie l'inventaire "
                 "des murs (deux faces, axe, épaisseur, extrémités, intersections, continuité, ouvertures). Signale tout mur oublié, "
                 "toute paire de traits qui n'est pas un mur (ligne de cote, semelle, hachure, trait de coupe), toute face mal identifiée. "
                 "Classe chaque ouvrage avec le RÉFÉRENTIEL SYMBOLES fourni (mur porteur, cloison, voile béton, poteau, poutre, longrine, "
                 "semelle filante/isolée, ligne de cote, axe de trame…) : classe candidate, source (légende > cartouche > repère > géométrie > "
                 "convention), alternatives, confiance. Lis d'abord la légende et le cartouche du plan : ils priment sur la convention générale. "
                 "N'analyse PAS encore les cotes écrites.")
PASS_DIMENSIONS = ("PASSAGE 2 — COTATIONS. Pour chaque texte numérique : texte brut, position, orientation, ligne de cote, traits "
                   "d'attache, points réellement cotés, unité, distance géométrique, compatibilité valeur/segment. Rejette les "
                   "associations incompatibles (orientation, attaches, extrémités, position dans la chaîne, voisines). Classe chaque "
                   "cote : nu int./nu int., nu ext./nu ext., axe/axe, axe/nu, ouverture, épaisseur, cumulée, partielle, estimée.")
PASS_RECONCILE = ("PASSAGE 3 — RAPPROCHEMENT. Compare géométrie et cotations : pour chaque espace, cote écrite vs mesure ; "
                  "reconstitue chaque chaîne complète ; ferme chaque rangée ; localise chaque mesure ; décide de la complétude.")

_S = {"type": "string"}
_NN = {"type": ["number", "null"]}
_SN = {"type": ["string", "null"]}

INTERIOR_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "walls": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "wall_id": _S, "orientation": {"type": "string", "enum": ["horizontal", "vertical", "inclined"]},
            "thickness_m": _NN, "role": {"type": "string", "enum": ["exterior", "interior", "unknown"]},
            "ouvrage_class": _S, "class_source": {"type": "string", "enum": ["legende", "cartouche", "repere", "geometrie", "convention"]},
            "class_alternatives": {"type": "array", "items": _S}, "associated_text": _S,
            "engine_agreement": {"type": "string", "enum": ["confirmed", "corrected", "rejected", "added"]},
            "comment": _S, "confidence": {"type": "number"}},
            "required": ["wall_id", "orientation", "thickness_m", "role", "ouvrage_class", "class_source", "class_alternatives", "associated_text",
                         "engine_agreement", "comment", "confidence"]}},
        "interior_measurements": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "measurement_id": _S, "direction": {"type": "string", "enum": ["horizontal", "vertical"]},
            "from_wall": _S, "from_face": _S, "to_wall": _S, "to_face": _S,
            "reference_type": {"type": "string", "enum": ["inside_face_to_inside_face", "outside_face_to_outside_face", "axis_to_axis",
                                                          "axis_to_face", "opening", "wall_thickness", "cumulative", "partial", "estimated"]},
            "written_dimension_m": _NN, "geometric_dimension_m": _NN, "difference_m": _NN, "page": {"type": "integer"},
            "status": {"type": "string", "enum": ["confirmed", "probable", "to_confirm", "unreadable"]},
            "justification": _S, "confidence": {"type": "number"}},
            "required": ["measurement_id", "direction", "from_wall", "from_face", "to_wall", "to_face", "reference_type",
                         "written_dimension_m", "geometric_dimension_m", "difference_m", "page", "status", "justification", "confidence"]}},
        "closure_equations": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "row_id": _S, "direction": {"type": "string", "enum": ["horizontal", "vertical"]}, "formula": _S,
            "sum_m": _NN, "exterior_dimension_m": _NN, "difference_m": _NN,
            "status": {"type": "string", "enum": ["closed", "open", "not_compared"]}, "explanation": _S},
            "required": ["row_id", "direction", "formula", "sum_m", "exterior_dimension_m", "difference_m", "status", "explanation"]}},
        "dimension_associations_rejected": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "raw_text": _S, "reason": _S, "location": _S}, "required": ["raw_text", "reason", "location"]}},
        "unreadable_dimensions": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "location": _S, "comment": _S}, "required": ["location", "comment"]}},
        "review_findings": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "target": _S, "finding": _S, "severity": {"type": "string", "enum": ["bloquant", "mineur"]}},
            "required": ["target", "finding", "severity"]}},
        "analysis_complete": {"type": "boolean"},
        "incompleteness_reasons": {"type": "array", "items": _S},
        "summary": _S,
    },
    "required": ["walls", "interior_measurements", "closure_equations", "dimension_associations_rejected", "unreadable_dimensions",
                 "review_findings", "analysis_complete", "incompleteness_reasons", "summary"],
}
