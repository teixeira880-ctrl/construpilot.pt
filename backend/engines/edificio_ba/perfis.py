"""Perfis por país : língua, normas, ações, sismo, preços indicativos e IVA/TVA.

O motor de cálculo é único (Eurocódigos) ; o perfil fixa os Anexos Nacionais, as referências regulamentares, a língua dos
livrables e os preços. Valores indicativos assinalados nas hipóteses ; os preços são de referência e substituíveis pelo utilizador.
"""
from __future__ import annotations

# ------------------------------------------------------------------ ações (kN/m²) — EN 1991-1-1 + AN
LOADS_PT = {
    "residential": {"g2": 2.5, "q": 2.0, "psi2": 0.3},     # cat. A : revestimentos 1,5 + divisórias 1,0
    "balcony": {"g2": 1.5, "q": 4.0, "psi2": 0.3},
    "roof": {"g2": 3.0, "q": 1.0, "psi2": 0.0},            # terraço não acessível + equipamentos
    "garden": {"g2": 6.5, "q": 4.0, "psi2": 0.6},          # laje sobre a cave fora do edifício (terras / pavimento, espaços comuns)
    "stair": {"g2": 1.5, "q": 3.0, "psi2": 0.3},
}
LOADS_FR = {
    "residential": {"g2": 2.5, "q": 1.5, "psi2": 0.3},     # cat. A (AN FR : 1,5 kN/m²)
    "balcony": {"g2": 1.5, "q": 3.5, "psi2": 0.3},
    "roof": {"g2": 3.0, "q": 1.0, "psi2": 0.0},
    "garden": {"g2": 6.5, "q": 5.0, "psi2": 0.6},
    "stair": {"g2": 1.5, "q": 2.5, "psi2": 0.3},
}

# ------------------------------------------------------------------ sismo
# Portugal : NP EN 1998-1 + AN (Quadros NA.I, NA-3.2 e NA-3.3)
AGR_PT = {"1.1": 2.5, "1.2": 2.0, "1.3": 1.5, "1.4": 1.0, "1.5": 0.6, "1.6": 0.35,
          "2.1": 2.5, "2.2": 2.0, "2.3": 1.7, "2.4": 1.1, "2.5": 0.8}
SOIL_PT = {1: {"A": (1.0, 0.1, 0.6, 2.0), "B": (1.35, 0.1, 0.6, 2.0), "C": (1.6, 0.1, 0.6, 2.0), "D": (2.0, 0.1, 0.8, 2.0), "E": (1.8, 0.1, 0.6, 2.0)},
           2: {"A": (1.0, 0.1, 0.25, 2.0), "B": (1.35, 0.1, 0.25, 2.0), "C": (1.6, 0.1, 0.25, 2.0), "D": (2.0, 0.1, 0.3, 2.0), "E": (1.8, 0.1, 0.25, 2.0)}}
GAMMA_I_PT = {1: {"I": 0.65, "II": 1.0, "III": 1.45, "IV": 1.95}, 2: {"I": 0.75, "II": 1.0, "III": 1.25, "IV": 1.50}}
# France : NF EN 1998-1 + AN, arrêté du 22/10/2010 modifié (zones 1 à 5)
AGR_FR = {"1": 0.4, "2": 0.7, "3": 1.1, "4": 1.6, "5": 3.0}
SOIL_FR = {"1-4": {"A": (1.0, 0.03, 0.20, 2.5), "B": (1.35, 0.05, 0.25, 2.5), "C": (1.5, 0.06, 0.40, 2.0), "D": (1.6, 0.10, 0.60, 1.5),
                   "E": (1.8, 0.08, 0.45, 1.25)},
           "5": {"A": (1.0, 0.15, 0.40, 2.0), "B": (1.2, 0.15, 0.50, 2.0), "C": (1.15, 0.20, 0.60, 2.0), "D": (1.35, 0.20, 0.80, 2.0),
                 "E": (1.4, 0.15, 0.50, 2.0)}}
GAMMA_I_FR = {"I": 0.8, "II": 1.0, "III": 1.2, "IV": 1.4}

# ------------------------------------------------------------------ preços (€ sem IVA / HT, fornecido e aplicado)
PRICES_PT = {"concrete": 105.0, "steel": 1.20, "formwork": 22.0, "excavation": 12.0, "transport": 6.0, "excavation_fnd": 14.0,
             "blinding": 9.0, "waterproof_wall": 45.0, "drain": 25.0, "waterproof_slab": 28.0, "ground_slab": 160.0}
PRICES_FR = {"concrete": 150.0, "steel": 1.75, "formwork": 38.0, "excavation": 18.0, "transport": 12.0, "excavation_fnd": 22.0,
             "blinding": 15.0, "waterproof_wall": 65.0, "drain": 38.0, "waterproof_slab": 45.0, "ground_slab": 210.0}
# restantes trabalhos (estimativa paramétrica) : (código, designação PT, designação FR, preço PT, preço FR, base)
# base : a = área bruta acima do solo ; roof = cobertura ; u = valor global ; cave = área da cave
PARAM = [
    ("7", "Alvenarias, isolamento térmico (ETICS) e acústico", "Maçonneries, isolation thermique par l'extérieur et acoustique", 95.0, 120.0, "a"),
    ("8", "Cobertura (forma, isolamento XPS, impermeabilização, proteção)", "Toiture-terrasse (forme de pente, isolant, étanchéité, protection)", 95.0, 150.0, "roof"),
    ("9", "Caixilharias em alumínio com rotura térmica, vidro duplo, estores e guardas", "Menuiseries extérieures alu RPT, double vitrage, volets et garde-corps", 115.0, 165.0, "a"),
    ("10", "Revestimentos de pavimentos, paredes e tetos (incl. tetos falsos e pinturas)", "Revêtements de sols, murs et plafonds (faux plafonds et peintures compris)", 125.0, 150.0, "a"),
    ("11", "Carpintarias (portas interiores, roupeiros) e mobiliário de cozinha", "Menuiseries intérieures (portes, placards) et cuisines", 85.0, 95.0, "a"),
    ("12", "Instalações de águas, esgotos e águas pluviais", "Plomberie, évacuations et eaux pluviales", 45.0, 65.0, "a"),
    ("13", "Instalações elétricas, ITED e segurança contra incêndio", "Électricité, courants faibles et sécurité incendie", 60.0, 75.0, "a"),
    ("14", "AVAC e AQS (bombas de calor, ventilação mecânica)", "CVC et ECS (pompes à chaleur, VMC)", 55.0, 80.0, "a"),
    ("15", "Elevador", "Ascenseur", 48000.0, 60000.0, "lift"),
    ("16", "Cave : pavimento, pinturas, portão, ventilação e desenfumagem", "Sous-sol : sol, peintures, porte, ventilation et désenfumage", 35.0, 45.0, "cave"),
    ("17", "Arranjos exteriores, muros de vedação e ligações às redes", "Aménagements extérieurs, clôtures et branchements", 45000.0, 60000.0, "u"),
]

# ------------------------------------------------------------------ perfis
PT = {
    "country": "PT", "lang": "pt", "loads": LOADS_PT, "prices": PRICES_PT, "vat": 0.23,
    "vat_note": "IVA 23 % (taxa normal ; verificar a aplicabilidade da taxa reduzida em empreitadas de habitação)",
    "price_ref": "preços de referência Norte de Portugal 2026, sem IVA",
    "steel": "A500 NR", "concrete": "C30/37",
    "norms": "NP EN 1990, NP EN 1991-1-1, NP EN 1992-1-1, NP EN 1997-1, NP EN 1998-1 (+ Anexos Nacionais), NP EN 206 / LNEC E 464",
    "seismic_ref": "NP EN 1998-1 + Anexo Nacional (ações tipo 1 e tipo 2)",
    "engineer": "engenheiro civil inscrito na Ordem dos Engenheiros (Lei 31/2009 e Portaria 113/2015)",
}
FR = {
    "country": "FR", "lang": "fr", "loads": LOADS_FR, "prices": PRICES_FR, "vat": 0.20,
    "vat_note": "TVA 20 % (taux normal ; vérifier l'éligibilité aux taux réduits de 10 % / 5,5 % selon l'opération)",
    "price_ref": "prix de référence Île-de-France 2026, HT",
    "steel": "B500B", "concrete": "C30/37",
    "norms": "NF EN 1990, NF EN 1991-1-1, NF EN 1992-1-1, NF EN 1997-1, NF EN 1998-1 (+ Annexes nationales), NF EN 206/CN",
    "seismic_ref": "NF EN 1998-1 + AN, arrêté du 22 octobre 2010 modifié (zonage sismique)",
    "engineer": "ingénieur structure (bureau d'études) — visa du contrôleur technique",
}
PROFILES = {"PT": PT, "FR": FR}


def profile(country: str | None) -> dict:
    return PROFILES.get((country or "PT").upper(), PT)


def fck_of(cls: str | None, default: float = 30.0) -> float:
    """« C30/37 » → 30."""
    try:
        return float(str(cls).upper().replace("C", "").split("/")[0])
    except (ValueError, AttributeError):
        return default
