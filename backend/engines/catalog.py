"""Base de référence des prix (lots de travaux). Administrable via le back-office."""

DIFFICULTY = {
    "easy": {"label": "Facile", "color": "green", "icon": "🟢"},
    "intermediate": {"label": "Intermédiaire", "color": "yellow", "icon": "🟡"},
    "hard": {"label": "Difficile", "color": "orange", "icon": "🟠"},
    "pro": {"label": "Professionnel recommandé", "color": "red", "icon": "🔴"},
}

# unit_material_* = €/unité de matériaux, unit_labour = €/unité main d'oeuvre
LOTS = [
    {"key": "demolition", "name": "Démolition", "unit": "m²", "mat_eco": 4, "mat_std": 7, "mat_premium": 10,
     "labour": 24, "hours": 0.4, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Masse", "Marteau piqueur", "Big bag", "EPI complet"]},
    {"key": "maconnerie", "name": "Maçonnerie", "unit": "m²", "mat_eco": 28, "mat_std": 42, "mat_premium": 65,
     "labour": 58, "hours": 1.1, "difficulty": "pro", "diy_possible": False,
     "tools": ["Bétonnière", "Truelle", "Niveau laser", "Règle de maçon"]},
    {"key": "fondations", "name": "Fondations", "unit": "m³", "mat_eco": 130, "mat_std": 165, "mat_premium": 210,
     "labour": 140, "hours": 2.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Mini-pelle", "Coffrage", "Aiguille vibrante"]},
    {"key": "terrassement", "name": "Terrassement", "unit": "m²", "mat_eco": 15, "mat_std": 25, "mat_premium": 40,
     "labour": 30, "hours": 0.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Pelle mécanique", "Laser de chantier", "Compacteur", "Camion-benne"]},
    {"key": "vrd", "name": "VRD / Raccordements réseaux", "unit": "ml", "mat_eco": 45, "mat_std": 65, "mat_premium": 95,
     "labour": 55, "hours": 1.0, "difficulty": "pro", "diy_possible": False,
     "tools": ["Mini-pelle", "Grillage avertisseur", "Fourreaux TPC", "Regards"]},
    {"key": "charpente", "name": "Charpente", "unit": "m²", "mat_eco": 55, "mat_std": 85, "mat_premium": 140,
     "labour": 45, "hours": 0.8, "difficulty": "pro", "diy_possible": False,
     "tools": ["Grue / manuscopique", "Cloueur charpente", "Harnais", "Niveau laser"]},
    {"key": "ventilation", "name": "Ventilation / VMC", "unit": "m²", "mat_eco": 12, "mat_std": 18, "mat_premium": 32,
     "labour": 14, "hours": 0.25, "difficulty": "hard", "diy_possible": True,
     "tools": ["Scie cloche", "Gaines isolées", "Anémomètre", "Perforateur"]},
    {"key": "placo", "name": "Plâtrerie / Placo", "unit": "m²", "mat_eco": 12, "mat_std": 17, "mat_premium": 24,
     "labour": 26, "hours": 0.55, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Visseuse placo", "Lève-plaque", "Couteau à enduire", "Niveau laser"]},
    {"key": "isolation", "name": "Isolation", "unit": "m²", "mat_eco": 14, "mat_std": 22, "mat_premium": 38,
     "labour": 22, "hours": 0.4, "difficulty": "easy", "diy_possible": True,
     "tools": ["Couteau à laine", "Agrafeuse", "Masque FFP2", "Gants"]},
    {"key": "electricite", "name": "Électricité", "unit": "m²", "mat_eco": 22, "mat_std": 34, "mat_premium": 52,
     "labour": 48, "hours": 0.8, "difficulty": "pro", "diy_possible": False,
     "tools": ["Pince à dénuder", "Multimètre", "Perforateur", "VAT"]},
    {"key": "plomberie", "name": "Plomberie", "unit": "m²", "mat_eco": 20, "mat_std": 32, "mat_premium": 55,
     "labour": 52, "hours": 0.75, "difficulty": "hard", "diy_possible": True,
     "tools": ["Pince à sertir", "Coupe-tube", "Clé à molette", "Chalumeau"]},
    {"key": "chauffage", "name": "Chauffage", "unit": "m²", "mat_eco": 45, "mat_std": 75, "mat_premium": 130,
     "labour": 42, "hours": 0.6, "difficulty": "pro", "diy_possible": False,
     "tools": ["Pince à sertir", "Manomètre", "Pompe de désembouage"]},
    {"key": "climatisation", "name": "Climatisation", "unit": "m²", "mat_eco": 40, "mat_std": 65, "mat_premium": 110,
     "labour": 38, "hours": 0.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Pompe à vide", "Manifold", "Dudgeonnière"]},
    {"key": "carrelage", "name": "Carrelage", "unit": "m²", "mat_eco": 22, "mat_std": 38, "mat_premium": 75,
     "labour": 42, "hours": 0.85, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Carrelette", "Peigne à colle", "Croisillons", "Maillet caoutchouc"]},
    {"key": "parquet", "name": "Parquet / Sols souples", "unit": "m²", "mat_eco": 18, "mat_std": 35, "mat_premium": 85,
     "labour": 26, "hours": 0.45, "difficulty": "easy", "diy_possible": True,
     "tools": ["Scie sauteuse", "Cales", "Maillet", "Tire-lame"]},
    {"key": "peinture", "name": "Peinture", "unit": "m²", "mat_eco": 5, "mat_std": 8, "mat_premium": 14,
     "labour": 16, "hours": 0.3, "difficulty": "easy", "diy_possible": True,
     "tools": ["Rouleau", "Pinceau à rechampir", "Bâche", "Adhésif de masquage"]},
    {"key": "menuiseries", "name": "Menuiseries (fenêtres / portes)", "unit": "u", "mat_eco": 380, "mat_std": 650,
     "mat_premium": 1250, "labour": 220, "hours": 3.5, "difficulty": "hard", "diy_possible": True,
     "tools": ["Perforateur", "Niveau", "Mousse expansive", "Pistolet à mastic"]},
    {"key": "cuisine", "name": "Cuisine", "unit": "ml", "mat_eco": 600, "mat_std": 1150, "mat_premium": 2400,
     "labour": 320, "hours": 5, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Visseuse", "Scie circulaire", "Niveau", "Scie cloche"]},
    {"key": "salle_de_bain", "name": "Salle de bain", "unit": "m²", "mat_eco": 320, "mat_std": 520,
     "mat_premium": 950, "labour": 380, "hours": 6, "difficulty": "hard", "diy_possible": True,
     "tools": ["Pince à sertir", "Carrelette", "Niveau", "Perforateur"]},
    {"key": "facade", "name": "Façade", "unit": "m²", "mat_eco": 28, "mat_std": 48, "mat_premium": 85,
     "labour": 42, "hours": 0.7, "difficulty": "pro", "diy_possible": False,
     "tools": ["Échafaudage", "Machine à projeter", "Taloche"]},
    {"key": "toiture", "name": "Toiture", "unit": "m²", "mat_eco": 45, "mat_std": 75, "mat_premium": 135,
     "labour": 68, "hours": 0.9, "difficulty": "pro", "diy_possible": False,
     "tools": ["Échafaudage", "Harnais", "Cloueur", "Monte-matériaux"]},
    {"key": "terrasse", "name": "Terrasse", "unit": "m²", "mat_eco": 45, "mat_std": 85, "mat_premium": 160,
     "labour": 55, "hours": 0.9, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Scie circulaire", "Niveau", "Visseuse", "Plots réglables"]},
    {"key": "extension", "name": "Extension", "unit": "m²", "mat_eco": 900, "mat_std": 1400, "mat_premium": 2200,
     "labour": 700, "hours": 12, "difficulty": "pro", "diy_possible": False,
     "tools": ["Étude structure obligatoire"]},
    {"key": "renovation_energetique", "name": "Rénovation énergétique", "unit": "m²", "mat_eco": 85, "mat_std": 135,
     "mat_premium": 220, "labour": 75, "hours": 1.2, "difficulty": "pro", "diy_possible": False,
     "tools": ["Audit énergétique", "Caméra thermique"]},
    {"key": "dechets", "name": "Déchets / évacuation", "unit": "m²", "mat_eco": 4, "mat_std": 6, "mat_premium": 8,
     "labour": 4, "hours": 0.1, "difficulty": "easy", "diy_possible": True,
     "tools": ["Big bag", "Remorque", "Benne"]},
]

LOTS_BY_KEY = {l["key"]: l for l in LOTS}

# Facteurs par défaut (surface × factor = quantité réaliste) — utilisés quand
# un lot est ajouté à l'estimation hors du template projet initial.
# Basé sur une maison type de 100 m² SHAB avec hauteur 2.5 m.
DEFAULT_LOT_FACTORS = {
    "demolition": 0.90,     # m² : ~90% de la surface est démolie
    "fondations": 0.30,     # m³ : 0.30 m³ de béton / m² SHAB
    "terrassement": 1.00,   # m² : emprise au sol ≈ surface
    "vrd": 0.40,            # ml : ~40 ml de tranchées pour 100 m²
    "charpente": 1.10,      # m² : débord de toit inclus
    "maconnerie": 0.20,     # m² : 20% de refends/reprises
    "toiture": 1.10,        # m² : léger débord de toit
    "facade": 0.90,         # m² : périmètre × hauteur / surface
    "menuiseries": 0.08,    # u : ~12 fenêtres+portes pour 150 m²
    "electricite": 1.00,    # m² : chaque m² équipé
    "plomberie": 1.00,      # m² (routing intérieur)
    "chauffage": 1.00,      # m²
    "climatisation": 0.03,  # u : ~5 splits pour 150 m²
    "isolation": 1.40,      # m² : murs + rampants + planchers bas
    "placo": 1.80,          # m² : cloisons + doublages + plafonds
    "carrelage": 0.35,      # m² : pièces humides + cuisine
    "parquet": 0.50,        # m² : sols secs
    "peinture": 2.90,       # m² : 2 faces murs + plafond
    "cuisine": 0.03,        # ml : ~5 ml pour 150 m²
    "salle_de_bain": 0.06,  # m² : ~9 m² pour 150 m²
    "terrasse": 0.20,       # m² : ~20% de la surface
    "extension": 0.20,      # m²
    "renovation_energetique": 1.00,
    "dechets": 1.00,        # m² : évacuation ≈ surface
    "ventilation": 1.00,
}

# Modèles de projet : lot -> facteur de quantité par m² de surface du projet
PROJECT_TYPES = [
    # ---- Construction maison neuve (tous corps d'état détaillés) ----
    {"key": "construction_maison_neuve", "name": "Construction maison neuve (clé en main)",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.5}},
    {"key": "construction_maison_hors_eau_hors_air",
     "name": "Construction maison neuve — hors d'eau / hors d'air",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "dechets": 0.4}},
    {"key": "construction_maison_gros_oeuvre",
     "name": "Construction maison — gros œuvre seul",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "dechets": 0.3}},
    {"key": "construction_maison_second_oeuvre",
     "name": "Construction maison — second œuvre & finitions",
     "image": "project_card_interior",
     "lots": {"electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.3}},
    {"key": "construction_maison_main_oeuvre",
     "name": "Construction maison neuve — main d'œuvre seule",
     "image": "project_card_exterior", "labour_only": True,
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.5}},
    # ---- Rénovation ----
    {"key": "renovation_complete", "name": "Rénovation complète maison", "image": "project_card_exterior",
     "lots": {"demolition": 0.9, "maconnerie": 0.15, "placo": 1.8, "isolation": 1.4, "electricite": 1.0,
              "plomberie": 1.0, "chauffage": 1.0, "carrelage": 0.35, "parquet": 0.5, "peinture": 2.9,
              "menuiseries": 0.08, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 1.0}},
    {"key": "renovation_appartement", "name": "Rénovation appartement", "image": "project_card_interior",
     "lots": {"demolition": 0.7, "placo": 1.4, "isolation": 0.9, "electricite": 1.0, "plomberie": 0.8,
              "carrelage": 0.3, "parquet": 0.55, "peinture": 2.8, "cuisine": 0.04, "salle_de_bain": 0.06,
              "dechets": 1.0}},
    {"key": "salle_de_bain", "name": "Salle de bain", "image": "project_card_bathroom",
     "lots": {"demolition": 1.0, "plomberie": 1.0, "electricite": 1.0, "placo": 2.2, "carrelage": 3.2,
              "salle_de_bain": 1.0, "peinture": 1.2, "dechets": 1.0}},
    {"key": "cuisine", "name": "Cuisine", "image": "project_card_interior",
     "lots": {"demolition": 0.8, "plomberie": 1.0, "electricite": 1.0, "carrelage": 1.6, "peinture": 2.0,
              "cuisine": 0.45, "dechets": 1.0}},
    {"key": "peinture", "name": "Peinture", "image": "project_card_interior",
     "lots": {"peinture": 2.9, "dechets": 0.2}},
    {"key": "placo", "name": "Placo / Plâtrerie", "image": "project_card_interior",
     "lots": {"placo": 1.0, "isolation": 0.8, "dechets": 0.3}},
    {"key": "isolation", "name": "Isolation", "image": "project_card_exterior",
     "lots": {"isolation": 1.0, "placo": 1.0, "dechets": 0.2}},
    {"key": "electricite", "name": "Électricité", "image": "project_card_interior",
     "lots": {"electricite": 1.0, "dechets": 0.2}},
    {"key": "plomberie", "name": "Plomberie", "image": "project_card_bathroom",
     "lots": {"plomberie": 1.0, "dechets": 0.2}},
    {"key": "chauffage", "name": "Chauffage", "image": "project_card_interior",
     "lots": {"chauffage": 1.0, "plomberie": 0.3}},
    {"key": "climatisation", "name": "Climatisation", "image": "project_card_interior",
     "lots": {"climatisation": 1.0, "electricite": 0.2}},
    {"key": "carrelage", "name": "Carrelage", "image": "project_card_bathroom",
     "lots": {"carrelage": 1.0, "dechets": 0.2}},
    {"key": "parquet", "name": "Parquet", "image": "project_card_interior",
     "lots": {"parquet": 1.0, "dechets": 0.1}},
    {"key": "toiture", "name": "Toiture", "image": "project_card_exterior",
     "lots": {"toiture": 1.0, "isolation": 0.9, "dechets": 0.5}},
    {"key": "facade", "name": "Façade", "image": "project_card_exterior",
     "lots": {"facade": 1.0, "dechets": 0.3}},
    {"key": "terrasse", "name": "Terrasse", "image": "project_card_exterior",
     "lots": {"terrasse": 1.0, "maconnerie": 0.2, "dechets": 0.3}},
    {"key": "maconnerie", "name": "Maçonnerie", "image": "project_card_exterior",
     "lots": {"maconnerie": 1.0, "dechets": 0.4}},
    {"key": "fondations", "name": "Fondations", "image": "project_card_exterior",
     "lots": {"fondations": 0.35, "maconnerie": 0.3, "dechets": 0.4}},
    {"key": "fenetres", "name": "Fenêtres", "image": "project_card_exterior",
     "lots": {"menuiseries": 1.0, "peinture": 0.3, "dechets": 0.1}},
    {"key": "portes", "name": "Portes", "image": "project_card_interior",
     "lots": {"menuiseries": 1.0, "peinture": 0.2}},
    {"key": "extension", "name": "Extension", "image": "project_card_exterior",
     "lots": {"extension": 1.0, "fondations": 0.3, "toiture": 1.0, "dechets": 0.6}},
    {"key": "renovation_energetique", "name": "Rénovation énergétique", "image": "project_card_exterior",
     "lots": {"renovation_energetique": 1.0, "isolation": 1.6, "menuiseries": 0.08, "chauffage": 1.0}},
]

PROJECT_TYPES_BY_KEY = {p["key"]: p for p in PROJECT_TYPES}

FINISH_LEVELS = [
    {"key": "eco", "name": "Économique", "coef": 0.85},
    {"key": "standard", "name": "Standard", "coef": 1.0},
    {"key": "premium", "name": "Premium", "coef": 1.28},
    {"key": "luxe", "name": "Haut de gamme", "coef": 1.65},
]
FINISH_BY_KEY = {f["key"]: f for f in FINISH_LEVELS}

REGIONS = [
    {"country": "FR", "region": "Île-de-France", "coef": 1.22},
    {"country": "FR", "region": "Auvergne-Rhône-Alpes", "coef": 1.06},
    {"country": "FR", "region": "Provence-Alpes-Côte d'Azur", "coef": 1.10},
    {"country": "FR", "region": "Occitanie", "coef": 0.97},
    {"country": "FR", "region": "Nouvelle-Aquitaine", "coef": 0.98},
    {"country": "FR", "region": "Bretagne", "coef": 0.96},
    {"country": "FR", "region": "Pays de la Loire", "coef": 0.97},
    {"country": "FR", "region": "Grand Est", "coef": 0.95},
    {"country": "FR", "region": "Hauts-de-France", "coef": 0.93},
    {"country": "FR", "region": "Normandie", "coef": 0.95},
    {"country": "FR", "region": "Centre-Val de Loire", "coef": 0.94},
    {"country": "FR", "region": "Bourgogne-Franche-Comté", "coef": 0.92},
    {"country": "FR", "region": "Corse", "coef": 1.18},
    # Portugal — coeficientes de mercado 2026 por distrito/região (base preços de referência)
    {"country": "PT", "region": "Lisboa", "coef": 0.74},
    {"country": "PT", "region": "Porto", "coef": 0.67},
    {"country": "PT", "region": "Algarve (Faro)", "coef": 0.72},
    {"country": "PT", "region": "Setúbal", "coef": 0.66},
    {"country": "PT", "region": "Braga", "coef": 0.60},
    {"country": "PT", "region": "Aveiro", "coef": 0.61},
    {"country": "PT", "region": "Coimbra", "coef": 0.60},
    {"country": "PT", "region": "Leiria", "coef": 0.59},
    {"country": "PT", "region": "Santarém", "coef": 0.58},
    {"country": "PT", "region": "Viseu", "coef": 0.56},
    {"country": "PT", "region": "Évora / Alentejo", "coef": 0.57},
    {"country": "PT", "region": "Viana do Castelo", "coef": 0.57},
    {"country": "PT", "region": "Vila Real / Bragança", "coef": 0.55},
    {"country": "PT", "region": "Castelo Branco / Guarda", "coef": 0.55},
    {"country": "PT", "region": "Madeira", "coef": 0.70},
    {"country": "PT", "region": "Açores", "coef": 0.71},
]

CONDITION_COEF = {
    "neuf": 0.85, "bon": 1.0, "moyen": 1.12, "vetuste": 1.3, "a_renover_totalement": 1.45,
}

BUILDING_COEF = {"maison": 1.0, "appartement": 1.05, "commerce": 1.15}

# Travaux à risque -> professionnel fortement recommandé
RISK_KEYWORDS = {
    "gaz": "Toute intervention sur une installation gaz doit être réalisée par un professionnel certifié (PGN/PGP).",
    "amiante": "Présence possible d'amiante : diagnostic obligatoire avant travaux, retrait par entreprise certifiée.",
    "mur porteur": "L'ouverture d'un mur porteur exige une étude de structure et un renfort dimensionné par un bureau d'études.",
    "structure": "Modification de structure : étude technique obligatoire.",
    "tableau électrique": "Le remplacement d'un tableau électrique relève d'un électricien qualifié (NF C 15-100).",
    "toiture": "Travaux en hauteur : risque de chute grave, échafaudage et harnais obligatoires.",
    "fondations": "Les fondations engagent la stabilité du bâtiment : étude de sol et bureau d'études requis.",
    "étanchéité": "Étanchéité structurelle : une malfaçon entraîne des dégâts majeurs, garantie décennale recommandée.",
    "plomb": "Peintures au plomb : diagnostic et protocole de retrait spécifique.",
}

HIGH_RISK_LOTS = {"electricite", "chauffage", "climatisation", "toiture", "facade", "fondations",
                  "extension", "maconnerie", "renovation_energetique", "terrassement", "charpente",
                  "vrd"}

# Ordre d'exécution pour le planning
EXECUTION_ORDER = ["demolition", "terrassement", "fondations", "vrd", "maconnerie", "extension",
                   "charpente", "toiture", "menuiseries",
                   "electricite", "plomberie", "chauffage", "climatisation", "ventilation",
                   "isolation", "placo",
                   "carrelage", "parquet", "peinture", "cuisine", "salle_de_bain", "facade",
                   "terrasse", "renovation_energetique", "dechets"]
