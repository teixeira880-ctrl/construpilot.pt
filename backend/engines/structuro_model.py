"""StructuroPilot — modèle porteur déterministe (Lot A backbone).

AUCUN calcul structurel chiffré ici : ce module structure les données, trace leur
provenance, calcule la COUVERTURE des vérifications (ce qui est documenté vs manquant)
et gère la péremption des résultats dépendants. Le moteur de vérification Eurocodes
est volontairement VERROUILLÉ (normes non licenciées) — voir CALC_ENGINE_AVAILABLE.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

CALC_ENGINE_AVAILABLE = False  # verrouillé : normes/catalogues/cas de référence non fournis
RULEPACK = {"id": "none", "version": "0", "status": "non_qualifie",
            "note": "Moteur de vérification non disponible : textes normatifs (Eurocodes/NF/EN) "
                    "non licenciés, catalogues de profilés et cas de référence ingénieur absents."}

# Provenance d'une donnée (jamais déduite de l'âge ou d'une photo).
SOURCES = ["declaration", "mesure", "observation", "document", "essai", "ia_proposition",
           "hypothese", "inconnu"]
# Une donnée est « documentée » (utilisable pour une vérif) seulement si sa source est fiable.
DOCUMENTED_SOURCES = {"mesure", "document", "essai", "observation"}

ELEMENT_TYPES = ["mur_porteur", "poutre", "poteau", "plancher", "appui", "fondation_semelle",
                 "linteau", "chevetre", "ouverture", "etai"]

# Statuts de vérification. JAMAIS "satisfaisante"/"defavorable" tant que le moteur est verrouillé.
VERIF_STATUS = ["non_calculee", "bloquee", "hors_domaine", "en_attente_moteur", "perimee"]

OUTPUT_LEVELS = ["exploration", "preliminaire", "calculee"]

# Catalogue des vérifications requises selon l'objectif, avec données d'entrée critiques.
# required = clés de données (datum keys) devant être DOCUMENTÉES pour lever le blocage.
VERIFICATIONS = {
    "descente_charges": {
        "label": "Descente de charges jusqu'au sol",
        "required": ["geometrie.niveaux", "plancher.sens_porteur", "plancher.portee",
                     "charges.permanentes", "charges.exploitation"],
        "domain": "generique"},
    "poutre_acier": {
        "label": "Poutre acier (flexion / flèche / déversement / appuis)",
        "required": ["ouverture.portee", "ouverture.charges_reprises", "poutre.appuis",
                     "poutre.maintien_lateral"],
        "domain": "acier_en1993"},
    "mur_ouverture": {
        "label": "Mur porteur & reprise d'ouverture (trumeaux, linteau, appuis)",
        "required": ["mur.epaisseur", "mur.materiau_resistance", "ouverture.position",
                     "charges.sur_appuis"],
        "domain": "maconnerie_en1996"},
    "semelle": {
        "label": "Semelle / fondation sous nouvel appui",
        "required": ["fondation.geometrie", "fondation.niveau_assise", "sol.portance",
                     "charges.sur_appuis"],
        "domain": "geotech_en1997_nfp94"},
    "plancher": {
        "label": "Plancher (portance, flèche, vibrations)",
        "required": ["plancher.section", "plancher.entraxe", "plancher.portee",
                     "plancher.etat_abouts", "charges.exploitation"],
        "domain": "generique"},
    "etaiement": {
        "label": "Étaiement / ouvrages provisoires par phase",
        "required": ["etai.materiel", "etai.hauteur", "etai.charges_reprises",
                     "niveau_inferieur.capacite"],
        "domain": "provisoire_en12812"},
}

# Données critiques du scénario « ouverture dans mur porteur ».
OPENING_CRITICAL_DATA = [
    {"key": "ouverture.position", "label": "Position et niveau de l'ouverture",
     "blocks": ["mur_ouverture", "descente_charges"]},
    {"key": "ouverture.portee", "label": "Portée (largeur) de l'ouverture",
     "blocks": ["poutre_acier", "mur_ouverture"]},
    {"key": "ouverture.charges_reprises", "label": "Charges reprises au-dessus de l'ouverture",
     "blocks": ["poutre_acier"]},
    {"key": "plancher.sens_porteur", "label": "Sens porteur des planchers",
     "blocks": ["descente_charges", "plancher"]},
    {"key": "plancher.portee", "label": "Portée des planchers", "blocks": ["descente_charges", "plancher"]},
    {"key": "mur.epaisseur", "label": "Épaisseur du mur porteur", "blocks": ["mur_ouverture"]},
    {"key": "mur.materiau_resistance", "label": "Résistance reconnue de la maçonnerie (essai requis)",
     "blocks": ["mur_ouverture"], "requires_essai": True},
    {"key": "poutre.appuis", "label": "Appuis de la poutre (trumeaux, longueur d'appui)",
     "blocks": ["poutre_acier"]},
    {"key": "fondation.geometrie", "label": "Géométrie des fondations existantes",
     "blocks": ["semelle"]},
    {"key": "sol.portance", "label": "Portance du sol (rapport géotechnique)",
     "blocks": ["semelle"], "requires_essai": True},
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def datum(value=None, unit=None, source="inconnu", note=None) -> dict:
    """Une donnée tracée. value=None + source='inconnu' = INCONNU (≠ valeur nulle)."""
    if source not in SOURCES:
        source = "inconnu"
    return {"value": value, "unit": unit, "source": source, "note": note, "updated_at": now()}

def is_documented(d: dict | None, requires_essai: bool = False) -> bool:
    if not d or d.get("value") in (None, ""):
        return False
    src = d.get("source")
    if src not in DOCUMENTED_SOURCES:
        return False
    if requires_essai and src != "essai":
        return False
    return True


def new_study(user_id: str, title: str, country: str, description: str) -> dict:
    return {
        "study_id": new_id("struct"),
        "user_id": user_id,
        "title": (title or "Étude structurelle").strip()[:160],
        "country": (country or "FR").upper()[:4],
        "description": (description or "").strip()[:8000],
        "revision": 1,
        "lifecycle": "brouillon",       # brouillon→donnees_a_confirmer→calcule→a_revoir→approuve
        "output_level": "exploration",
        "facts": [],                    # faits déclarés extraits (source tracée)
        "goal": {"type": "ouverture_mur_porteur", "label": "Créer une ouverture dans un mur porteur"},
        "levels": [],                   # niveaux (esquisse)
        "elements": [],                 # éléments porteurs à ID stable
        "data": {},                     # datum keys -> datum()
        "questionnaire": [],            # questions adaptatives
        "verifications": [],            # couverture (statuts, jamais fabriqués)
        "approvals": [],
        "calc_engine": {"available": CALC_ENGINE_AVAILABLE, "rulepack": RULEPACK},
        "created_at": now(),
        "updated_at": now(),
    }


def build_questionnaire(study: dict) -> list[dict]:
    """Construit les questions adaptatives : chaque donnée critique manquante → une question,
    avec la/les vérifications qu'elle débloque et comment la documenter."""
    data = study.get("data") or {}
    questions = []
    for crit in OPENING_CRITICAL_DATA:
        d = data.get(crit["key"])
        requires_essai = crit.get("requires_essai", False)
        if is_documented(d, requires_essai):
            continue
        how = ("Essai / sondage par un intervenant compétent (l'âge du bâtiment ne fournit "
               "aucune résistance).") if requires_essai else \
              ("Relevé coté sur site, plan vérifié ou mesure. Une description ou une photo ne "
               "suffit pas comme mesure fiable.")
        questions.append({
            "id": new_id("q"),
            "datum_key": crit["key"],
            "question": crit["label"],
            "blocks": crit["blocks"],
            "requires_essai": requires_essai,
            "how_to_document": how,
            "answer": None,
            "answer_source": None,       # declaration|mesure|document|essai|observation|inconnu
            "status": "a_documenter",
        })
    return questions


def recompute(study: dict) -> dict:
    """Recalcule couverture des vérifications + niveau de sortie + cycle de vie.
    Déterministe. N'invente aucun résultat ; le moteur de calcul reste verrouillé."""
    data = study.get("data") or {}
    goal_verifs = ["descente_charges", "poutre_acier", "mur_ouverture", "semelle"]

    # Certaines entrées sont satisfaites par l'ÉTAT DU MODÈLE, pas par une donnée saisie.
    model_satisfied = set()
    if study.get("levels"):
        model_satisfied.add("geometrie.niveaux")

    def _req_ok(req: str) -> bool:
        if req in model_satisfied:
            return True
        crit = next((c for c in OPENING_CRITICAL_DATA if c["key"] == req), None)
        requires_essai = bool(crit and crit.get("requires_essai"))
        return is_documented(data.get(req), requires_essai)

    verifs = []
    for vkey in goal_verifs:
        spec = VERIFICATIONS[vkey]
        missing = [req for req in spec["required"] if not _req_ok(req)]
        if missing:
            status = "bloquee"
        elif not CALC_ENGINE_AVAILABLE:
            # Données suffisantes MAIS moteur non qualifié → honnête, jamais "satisfaisante".
            status = "en_attente_moteur"
        else:
            status = "non_calculee"
        verifs.append({
            "key": vkey, "label": spec["label"], "domain": spec["domain"],
            "status": status, "missing_inputs": missing,
            "note": (RULEPACK["note"] if status == "en_attente_moteur" else None),
        })
    study["verifications"] = verifs

    # Niveau de sortie
    geom_ok = bool(study.get("levels")) and is_documented(data.get("ouverture.position")) \
        and is_documented(data.get("plancher.sens_porteur"))
    if geom_ok:
        study["output_level"] = "preliminaire"
    else:
        study["output_level"] = "exploration"
    # Le niveau "calculee" est inaccessible tant que CALC_ENGINE_AVAILABLE est faux.

    # Cycle de vie
    any_documented = any(is_documented(v) for v in data.values())
    all_unblocked = all(v["status"] != "bloquee" for v in verifs) if verifs else False
    if study.get("approvals"):
        study["lifecycle"] = "approuve"
    elif all_unblocked and any_documented:
        study["lifecycle"] = "a_revoir"
    elif any_documented:
        study["lifecycle"] = "donnees_a_confirmer"
    else:
        study["lifecycle"] = "brouillon"

    study["questionnaire"] = build_questionnaire(study)
    study["updated_at"] = now()
    return study


def invalidate_dependents(study: dict, datum_key: str) -> dict:
    """Le retrait/l'inconnu d'une donnée critique périme approbations + résultats dépendants."""
    # Toute approbation existante devient périmée (donnée influente modifiée).
    for ap in study.get("approvals", []):
        ap["status"] = "perimee"
    study["approvals"] = [ap for ap in study.get("approvals", []) if ap.get("status") != "perimee"]
    study["revision"] = int(study.get("revision", 1)) + 1
    return recompute(study)


DEMO_DESCRIPTION = ("Maison vers 1850, deux niveaux sur cave, murs en pierre d'environ 50 cm, "
                    "planchers bois. Ouverture souhaitée d'environ 2,40 m entre le séjour et la "
                    "cuisine au rez-de-chaussée.")


def build_demo(study: dict) -> dict:
    """Jeu de démo « Maison 1850 » : faits déclarés + esquisse de niveaux, MAIS aucune
    résistance/fondation affectée (restent inconnues → vérifications bloquées)."""
    study["title"] = "DÉMO — Maison 1850, ouverture séjour/cuisine"
    study["description"] = DEMO_DESCRIPTION
    study["facts"] = [
        {"id": new_id("f"), "text": "Construction vers 1850", "source": "declaration"},
        {"id": new_id("f"), "text": "Deux niveaux sur cave", "source": "declaration"},
        {"id": new_id("f"), "text": "Murs en pierre ~50 cm", "source": "declaration"},
        {"id": new_id("f"), "text": "Planchers bois", "source": "declaration"},
        {"id": new_id("f"), "text": "Ouverture ~2,40 m séjour/cuisine au RDC", "source": "declaration"},
    ]
    study["levels"] = [
        {"id": new_id("lvl"), "name": "Cave", "elevation_m": datum(-2.4, "m", "declaration")},
        {"id": new_id("lvl"), "name": "Rez-de-chaussée", "elevation_m": datum(0.0, "m", "declaration")},
        {"id": new_id("lvl"), "name": "Étage", "elevation_m": datum(2.7, "m", "declaration")},
    ]
    study["elements"] = [
        {"id": new_id("el"), "type": "mur_porteur", "ref": "M1",
         "label": "Mur porteur séjour/cuisine (pierre)", "level": "Rez-de-chaussée"},
        {"id": new_id("el"), "type": "ouverture", "ref": "O1",
         "label": "Ouverture projetée ~2,40 m", "level": "Rez-de-chaussée"},
        {"id": new_id("el"), "type": "plancher", "ref": "P1",
         "label": "Plancher bois sur RDC", "level": "Étage"},
    ]
    # Données : seulement ce qui est réellement déclaré/mesurable ; le reste reste INCONNU.
    study["data"] = {
        "ouverture.position": datum("Mur M1, RDC, entre séjour et cuisine", None, "declaration"),
        "ouverture.portee": datum(2.40, "m", "declaration",
                                  "Déclaré, à confirmer par relevé coté."),
        "mur.epaisseur": datum(0.50, "m", "declaration", "Déclaré ~50 cm, à mesurer."),
        # Volontairement INCONNUS (le cahier des charges l'exige) :
        "mur.materiau_resistance": datum(None, "MPa", "inconnu",
                                         "La pierre ancienne n'a pas de résistance type ; essai requis."),
        "plancher.sens_porteur": datum(None, None, "inconnu"),
        "plancher.portee": datum(None, "m", "inconnu"),
        "ouverture.charges_reprises": datum(None, "kN/m", "inconnu"),
        "poutre.appuis": datum(None, None, "inconnu"),
        "fondation.geometrie": datum(None, None, "inconnu"),
        "sol.portance": datum(None, "kPa", "inconnu"),
        "charges.permanentes": datum(None, "kN/m²", "inconnu"),
        "charges.exploitation": datum(None, "kN/m²", "inconnu"),
    }
    return recompute(study)
