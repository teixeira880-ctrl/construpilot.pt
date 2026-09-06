"""Base de referência dos preços (lotes de obra). Administrável pelo back-office."""

DIFFICULTY = {
    "easy": {"label": "Fácil", "color": "green", "icon": "🟢"},
    "intermediate": {"label": "Intermédio", "color": "yellow", "icon": "🟡"},
    "hard": {"label": "Difícil", "color": "orange", "icon": "🟠"},
    "pro": {"label": "Profissional recomendado", "color": "red", "icon": "🔴"},
}

# unit_material_* = €/unidade de materiais, unit_labour = €/unidade de mão de obra
LOTS = [
    {"key": "demolition", "name": "Demolição", "unit": "m²", "mat_eco": 4, "mat_std": 7, "mat_premium": 10,
     "labour": 24, "hours": 0.4, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Marreta", "Martelo demolidor", "Big bag", "EPI completo"]},
    {"key": "maconnerie", "name": "Alvenaria", "unit": "m²", "mat_eco": 28, "mat_std": 42, "mat_premium": 65,
     "labour": 58, "hours": 1.1, "difficulty": "pro", "diy_possible": False,
     "tools": ["Betoneira", "Colher de pedreiro", "Nível laser", "Régua de pedreiro"]},
    {"key": "fondations", "name": "Fundações", "unit": "m³", "mat_eco": 130, "mat_std": 165, "mat_premium": 210,
     "labour": 140, "hours": 2.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Miniescavadora", "Cofragem", "Agulha vibradora"]},
    {"key": "terrassement", "name": "Movimentos de terras", "unit": "m²", "mat_eco": 15, "mat_std": 25, "mat_premium": 40,
     "labour": 30, "hours": 0.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Retroescavadora", "Laser de obra", "Compactador", "Camião basculante"]},
    {"key": "vrd", "name": "Infraestruturas exteriores / Redes", "unit": "ml", "mat_eco": 45, "mat_std": 65, "mat_premium": 95,
     "labour": 55, "hours": 1.0, "difficulty": "pro", "diy_possible": False,
     "tools": ["Miniescavadora", "Rede sinalizadora", "Tubagens TPC", "Caixas de visita"]},
    {"key": "charpente", "name": "Estrutura de cobertura (asnas)", "unit": "m²", "mat_eco": 55, "mat_std": 85, "mat_premium": 140,
     "labour": 45, "hours": 0.8, "difficulty": "pro", "diy_possible": False,
     "tools": ["Grua / manipulador telescópico", "Pistola de pregos", "Arnês", "Nível laser"]},
    {"key": "ventilation", "name": "Ventilação / VMC", "unit": "m²", "mat_eco": 12, "mat_std": 18, "mat_premium": 32,
     "labour": 14, "hours": 0.25, "difficulty": "hard", "diy_possible": True,
     "tools": ["Serra copo", "Condutas isoladas", "Anemómetro", "Perfurador"]},
    {"key": "placo", "name": "Estucaria / Pladur", "unit": "m²", "mat_eco": 12, "mat_std": 17, "mat_premium": 24,
     "labour": 26, "hours": 0.55, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Aparafusadora pladur", "Elevador de placas", "Espátula", "Nível laser"]},
    {"key": "isolation", "name": "Isolamento", "unit": "m²", "mat_eco": 14, "mat_std": 22, "mat_premium": 38,
     "labour": 22, "hours": 0.4, "difficulty": "easy", "diy_possible": True,
     "tools": ["Faca para lã", "Agrafador", "Máscara FFP2", "Luvas"]},
    {"key": "electricite", "name": "Electricidade", "unit": "m²", "mat_eco": 22, "mat_std": 34, "mat_premium": 52,
     "labour": 48, "hours": 0.8, "difficulty": "pro", "diy_possible": False,
     "tools": ["Alicate descarnador", "Multímetro", "Perfurador", "Detector de tensão"]},
    {"key": "plomberie", "name": "Canalização", "unit": "m²", "mat_eco": 20, "mat_std": 32, "mat_premium": 55,
     "labour": 52, "hours": 0.75, "difficulty": "hard", "diy_possible": True,
     "tools": ["Alicate de prensar", "Corta-tubos", "Chave inglesa", "Maçarico"]},
    {"key": "chauffage", "name": "Aquecimento", "unit": "m²", "mat_eco": 45, "mat_std": 75, "mat_premium": 130,
     "labour": 42, "hours": 0.6, "difficulty": "pro", "diy_possible": False,
     "tools": ["Alicate de prensar", "Manómetro", "Bomba de purga"]},
    {"key": "climatisation", "name": "Ar condicionado", "unit": "m²", "mat_eco": 40, "mat_std": 65, "mat_premium": 110,
     "labour": 38, "hours": 0.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Bomba de vácuo", "Manifold", "Alargador de tubo"]},
    {"key": "carrelage", "name": "Azulejos", "unit": "m²", "mat_eco": 25, "mat_std": 42, "mat_premium": 75,
     "labour": 38, "hours": 0.55, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Cortadora de azulejos", "Espátula dentada", "Cruzetas", "Nível"]},
    {"key": "parquet", "name": "Soalho / Pavimento flutuante", "unit": "m²", "mat_eco": 22, "mat_std": 38, "mat_premium": 70,
     "labour": 26, "hours": 0.35, "difficulty": "easy", "diy_possible": True,
     "tools": ["Serrote de esquadria", "Alavanca", "Cunhas", "Martelo de borracha"]},
    {"key": "peinture", "name": "Pintura", "unit": "m²", "mat_eco": 8, "mat_std": 14, "mat_premium": 24,
     "labour": 18, "hours": 0.25, "difficulty": "easy", "diy_possible": True,
     "tools": ["Rolo", "Pincéis", "Fita de pintor", "Lona de protecção"]},
    {"key": "menuiseries", "name": "Caixilharia", "unit": "u", "mat_eco": 320, "mat_std": 520, "mat_premium": 950,
     "labour": 180, "hours": 3.0, "difficulty": "hard", "diy_possible": False,
     "tools": ["Espuma expansiva", "Pé-de-cabra", "Nível", "Berbequim de percussão"]},
    {"key": "cuisine", "name": "Cozinha", "unit": "ml", "mat_eco": 850, "mat_std": 1600, "mat_premium": 3200,
     "labour": 280, "hours": 4.0, "difficulty": "hard", "diy_possible": True,
     "tools": ["Berbequim", "Serra circular", "Nível", "Broca de furar chapa"]},
    {"key": "salle_de_bain", "name": "Casa de banho", "unit": "m²", "mat_eco": 450, "mat_std": 850, "mat_premium": 1700,
     "labour": 280, "hours": 4.5, "difficulty": "pro", "diy_possible": False,
     "tools": ["Chave sextavada", "Silicone sanitário", "Nível", "Rebarbadora"]},
    {"key": "facade", "name": "Fachada", "unit": "m²", "mat_eco": 35, "mat_std": 58, "mat_premium": 95,
     "labour": 42, "hours": 0.7, "difficulty": "pro", "diy_possible": False,
     "tools": ["Andaimes", "Pistola de reboco", "Talocha", "Arnês"]},
    {"key": "toiture", "name": "Cobertura", "unit": "m²", "mat_eco": 65, "mat_std": 105, "mat_premium": 180,
     "labour": 52, "hours": 0.9, "difficulty": "pro", "diy_possible": False,
     "tools": ["Escadote de telhadista", "Arnês", "Compressor", "Pistola de pregos"]},
    {"key": "terrasse", "name": "Terraço / Deck", "unit": "m²", "mat_eco": 45, "mat_std": 85, "mat_premium": 165,
     "labour": 38, "hours": 0.65, "difficulty": "intermediate", "diy_possible": True,
     "tools": ["Serra circular", "Berbequim", "Nível laser", "Espaçadores"]},
    {"key": "extension", "name": "Ampliação", "unit": "m²", "mat_eco": 950, "mat_std": 1550, "mat_premium": 2400,
     "labour": 420, "hours": 8.0, "difficulty": "pro", "diy_possible": False,
     "tools": ["Grua", "Betoneira", "Andaimes", "Nível laser"]},
    {"key": "renovation_energetique", "name": "Reabilitação energética", "unit": "m²", "mat_eco": 85, "mat_std": 145, "mat_premium": 240,
     "labour": 62, "hours": 1.1, "difficulty": "pro", "diy_possible": False,
     "tools": ["Câmara termográfica", "Análise energética", "Ventilador porta soprante"]},
    {"key": "dechets", "name": "Gestão de resíduos", "unit": "m²", "mat_eco": 6, "mat_std": 10, "mat_premium": 16,
     "labour": 8, "hours": 0.1, "difficulty": "easy", "diy_possible": True,
     "tools": ["Big bag", "Contentor de obra", "EPI"]},
]
LOTS_BY_KEY = {l["key"]: l for l in LOTS}

# Factores por defeito (superfície × factor = quantidade realista) — usados quando
# um lote é adicionado à estimativa fora do modelo de projecto inicial.
# Baseado numa habitação-tipo de 100 m² SHAB com pé-direito de 2,5 m.
DEFAULT_LOT_FACTORS = {
    "demolition": 0.90,     # m² : ~90% da superfície é demolida
    "fondations": 0.30,     # m³ : 0,30 m³ de betão / m² SHAB
    "terrassement": 1.00,   # m² : implantação ≈ superfície
    "vrd": 0.40,            # ml : ~40 ml de valas para 100 m²
    "charpente": 1.10,      # m² : beirado incluído
    "maconnerie": 0.20,     # m² : 20% de paredes-mestras/reforços
    "toiture": 1.10,        # m² : ligeiro beirado
    "facade": 0.90,         # m² : perímetro × altura / superfície
    "menuiseries": 0.08,    # u : ~12 janelas+portas para 150 m²
    "electricite": 1.00,    # m² : cada m² equipado
    "plomberie": 1.00,      # m² (percursos interiores)
    "chauffage": 1.00,      # m²
    "climatisation": 0.03,  # u : ~5 splits para 150 m²
    "isolation": 1.40,      # m² : paredes + tectos inclinados + pavimentos térreos
    "placo": 1.80,          # m² : tabiques + revestimentos + tectos
    "carrelage": 0.35,      # m² : zonas húmidas + cozinha
    "parquet": 0.50,        # m² : pavimentos secos
    "peinture": 2.90,       # m² : 2 faces de paredes + tecto
    "cuisine": 0.03,        # ml : ~5 ml para 150 m²
    "salle_de_bain": 0.06,  # m² : ~9 m² para 150 m²
    "terrasse": 0.20,       # m² : ~20% da superfície
    "extension": 0.20,      # m²
    "renovation_energetique": 1.00,
    "dechets": 1.00,        # m² : evacuação ≈ superfície
    "ventilation": 1.00,
}

# Modelos de projecto : lote -> factor de quantidade por m² de superfície do projecto
PROJECT_TYPES = [
    # ---- Construção de habitação nova (todos os lotes detalhados) ----
    {"key": "construction_maison_neuve", "name": "Construção de moradia nova (chave na mão)",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.5}},
    {"key": "construction_maison_hors_eau_hors_air",
     "name": "Construção de moradia nova — tosco (fora de água / fora de ar)",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "dechets": 0.4}},
    {"key": "construction_maison_gros_oeuvre",
     "name": "Construção de moradia — só estrutura",
     "image": "project_card_exterior",
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "dechets": 0.3}},
    {"key": "construction_maison_second_oeuvre",
     "name": "Construção de moradia — acabamentos e especialidades",
     "image": "project_card_interior",
     "lots": {"electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.3}},
    {"key": "construction_maison_main_oeuvre",
     "name": "Construção de moradia nova — só mão de obra",
     "image": "project_card_exterior", "labour_only": True,
     "lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,
              "charpente": 1.10, "toiture": 1.10, "facade": 1.0, "menuiseries": 0.08,
              "electricite": 1.0, "plomberie": 1.0, "chauffage": 1.0, "ventilation": 1.0,
              "isolation": 1.4, "placo": 1.8, "carrelage": 0.35, "parquet": 0.5,
              "peinture": 2.9, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 0.5}},
    # ---- Remodelação / Reabilitação ----
    {"key": "renovation_complete", "name": "Remodelação integral de moradia", "image": "project_card_exterior",
     "lots": {"demolition": 0.9, "maconnerie": 0.15, "placo": 1.8, "isolation": 1.4, "electricite": 1.0,
              "plomberie": 1.0, "chauffage": 1.0, "carrelage": 0.35, "parquet": 0.5, "peinture": 2.9,
              "menuiseries": 0.08, "cuisine": 0.03, "salle_de_bain": 0.06, "dechets": 1.0}},
    {"key": "renovation_appartement", "name": "Remodelação de apartamento", "image": "project_card_interior",
     "lots": {"demolition": 0.7, "placo": 1.4, "isolation": 0.9, "electricite": 1.0, "plomberie": 0.8,
              "carrelage": 0.3, "parquet": 0.55, "peinture": 2.8, "cuisine": 0.04, "salle_de_bain": 0.06,
              "dechets": 1.0}},
    {"key": "salle_de_bain", "name": "Casa de banho", "image": "project_card_bathroom",
     "lots": {"demolition": 1.0, "plomberie": 1.0, "electricite": 1.0, "placo": 2.2, "carrelage": 3.2,
              "salle_de_bain": 1.0, "peinture": 1.2, "dechets": 1.0}},
    {"key": "cuisine", "name": "Cozinha", "image": "project_card_interior",
     "lots": {"demolition": 0.8, "plomberie": 1.0, "electricite": 1.0, "carrelage": 1.6, "peinture": 2.0,
              "cuisine": 0.45, "dechets": 1.0}},
    {"key": "peinture", "name": "Pintura", "image": "project_card_interior",
     "lots": {"peinture": 2.9, "dechets": 0.2}},
    {"key": "placo", "name": "Pladur / Estucaria", "image": "project_card_interior",
     "lots": {"placo": 1.0, "isolation": 0.8, "dechets": 0.3}},
    {"key": "isolation", "name": "Isolamento", "image": "project_card_exterior",
     "lots": {"isolation": 1.0, "placo": 1.0, "dechets": 0.2}},
    {"key": "electricite", "name": "Electricidade", "image": "project_card_interior",
     "lots": {"electricite": 1.0, "dechets": 0.2}},
    {"key": "plomberie", "name": "Canalização", "image": "project_card_bathroom",
     "lots": {"plomberie": 1.0, "dechets": 0.2}},
    {"key": "chauffage", "name": "Aquecimento", "image": "project_card_interior",
     "lots": {"chauffage": 1.0, "plomberie": 0.3}},
    {"key": "climatisation", "name": "Ar condicionado", "image": "project_card_interior",
     "lots": {"climatisation": 1.0, "electricite": 0.2}},
    {"key": "carrelage", "name": "Azulejos", "image": "project_card_bathroom",
     "lots": {"carrelage": 1.0, "dechets": 0.2}},
    {"key": "parquet", "name": "Soalho", "image": "project_card_interior",
     "lots": {"parquet": 1.0, "dechets": 0.1}},
    {"key": "toiture", "name": "Cobertura", "image": "project_card_exterior",
     "lots": {"toiture": 1.0, "isolation": 0.9, "dechets": 0.5}},
    {"key": "facade", "name": "Fachada", "image": "project_card_exterior",
     "lots": {"facade": 1.0, "dechets": 0.3}},
    {"key": "terrasse", "name": "Terraço", "image": "project_card_exterior",
     "lots": {"terrasse": 1.0, "maconnerie": 0.2, "dechets": 0.3}},
    {"key": "maconnerie", "name": "Alvenaria", "image": "project_card_exterior",
     "lots": {"maconnerie": 1.0, "dechets": 0.4}},
    {"key": "fondations", "name": "Fundações", "image": "project_card_exterior",
     "lots": {"fondations": 0.35, "maconnerie": 0.3, "dechets": 0.4}},
    {"key": "fenetres", "name": "Janelas", "image": "project_card_exterior",
     "lots": {"menuiseries": 1.0, "peinture": 0.3, "dechets": 0.1}},
    {"key": "portes", "name": "Portas", "image": "project_card_interior",
     "lots": {"menuiseries": 1.0, "peinture": 0.2}},
    {"key": "extension", "name": "Ampliação", "image": "project_card_exterior",
     "lots": {"extension": 1.0, "fondations": 0.3, "toiture": 1.0, "dechets": 0.6}},
    {"key": "renovation_energetique", "name": "Reabilitação energética", "image": "project_card_exterior",
     "lots": {"renovation_energetique": 1.0, "isolation": 1.6, "menuiseries": 0.08, "chauffage": 1.0}},
]

PROJECT_TYPES_BY_KEY = {p["key"]: p for p in PROJECT_TYPES}

FINISH_LEVELS = [
    {"key": "eco", "name": "Económico", "coef": 0.85},
    {"key": "standard", "name": "Padrão", "coef": 1.0},
    {"key": "premium", "name": "Premium", "coef": 1.28},
    {"key": "luxe", "name": "Alta gama", "coef": 1.65},
]
FINISH_BY_KEY = {f["key"]: f for f in FINISH_LEVELS}

REGIONS = [
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

# Palavras-chave de risco — chaves FR mantidas por retrocompatibilidade (matching
# em descrições antigas), chaves PT-PT adicionadas para o mercado português.
RISK_KEYWORDS = {
    # --- Chaves FR (legado, matching em descrições antigas) ---
    "gaz": "Toute intervention sur une installation gaz doit être réalisée par un professionnel certifié (PGN/PGP).",
    "amiante": "Présence possible d'amiante : diagnostic obligatoire avant travaux, retrait par entreprise certifiée.",
    "mur porteur": "L'ouverture d'un mur porteur exige une étude de structure et un renfort dimensionné par un bureau d'études.",
    "structure": "Modification de structure : étude technique obligatoire.",
    "tableau électrique": "Le remplacement d'un tableau électrique relève d'un électricien qualifié (NF C 15-100).",
    "toiture": "Travaux en hauteur : risque de chute grave, échafaudage et harnais obligatoires.",
    "fondations": "Les fondations engagent la stabilité du bâtiment : étude de sol et bureau d'études requis.",
    "étanchéité": "Étanchéité structurelle : une malfaçon entraîne des dégâts majeurs, garantie décennale recommandée.",
    "plomb": "Peintures au plomb : diagnostic et protocole de retrait spécifique.",
    # --- Chaves PT-PT (adicionadas, mercado português) ---
    "gás": "Qualquer intervenção numa instalação de gás deve ser executada por técnico certificado (categoria I/II).",
    "amianto": "Suspeita de amianto: diagnóstico obrigatório antes da obra, remoção por empresa licenciada pela APA.",
    "fibrocimento": "Fibrocimento pode conter amianto: análise e remoção por empresa certificada.",
    "parede-mestra": "A abertura de uma parede-mestra exige projecto de estabilidade assinado por engenheiro.",
    "parede mestra": "A abertura de uma parede-mestra exige projecto de estabilidade assinado por engenheiro.",
    "estrutura": "Alteração de estrutura: projecto de engenharia obrigatório.",
    "quadro elétrico": "Substituição do quadro eléctrico obriga a certificação por técnico responsável (RTIEBT).",
    "quadro eléctrico": "Substituição do quadro eléctrico obriga a certificação por técnico responsável (RTIEBT).",
    "cobertura": "Trabalhos em altura: risco grave de queda, andaimes e arnês obrigatórios.",
    "telhado": "Trabalhos em altura: risco grave de queda, andaimes e arnês obrigatórios.",
    "fundações": "As fundações comprometem a estabilidade do edifício: estudo geotécnico e projecto obrigatórios.",
    "impermeabilização": "Impermeabilização estrutural: uma falha causa danos graves, garantia decenal recomendada.",
    "chumbo": "Tintas com chumbo: diagnóstico e protocolo de remoção específico.",
    "canalização antiga": "Canalizações antigas em chumbo: substituir e testar a água.",
}

HIGH_RISK_LOTS = {"electricite", "chauffage", "climatisation", "toiture", "facade", "fondations",
                  "extension", "maconnerie", "renovation_energetique", "terrassement", "charpente",
                  "vrd"}

# Ordem de execução para o planeamento
EXECUTION_ORDER = ["demolition", "terrassement", "fondations", "vrd", "maconnerie", "extension",
                   "charpente", "toiture", "menuiseries",
                   "electricite", "plomberie", "chauffage", "climatisation", "ventilation",
                   "isolation", "placo",
                   "carrelage", "parquet", "peinture", "cuisine", "salle_de_bain", "facade",
                   "terrasse", "renovation_energetique", "dechets"]
