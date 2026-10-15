"""Caso 2 — PC + G2 ambos em La Courneuve (mesma morada)."""

PC_DATA = {
    "project_address": "3 rue Beaufils, 93120 La Courneuve, France",
    "project_parcel": "AG/0087",
    "country_code": None,
    "building_type": "R+2+cave",
    "mass_plan_annotation": "R+1+C",  # discrepância a reportar
    "implantation": {"length_m": 11.14, "width_m": 7.35, "area_m2": 81.9},
    "levels": {
        "cave_floor_mNGF": 33.76,
        "cave_relative_to_rdc_m": -2.04,
        "terrain_natural_mNGF": 38.5,
    },
    "parking": {"location": "rdc", "type": "coberto"},
    "neighbors": [
        {"direction": "east", "building_type": "R+3",
         "attached": True, "cave_known": False},
        {"direction": "west", "building_type": "RDC",
         "attached": True, "cave_known": False},
    ],
}

G2_DATA = {
    "project_address": "3 rue Beaufils, 93120 La Courneuve, France",
    "project_parcel": "AG/0087",
    "soil_layers": [
        {"name": "aterros", "top_m": 0.0, "bottom_m": 1.8,
         "ka": 0.406, "k0": 0.577},
        {"name": "aluvioes", "top_m": 1.8, "bottom_m": 7.0,
         "ka": 0.333, "k0": 0.500},
        {"name": "margas_moles", "top_m": 7.0, "bottom_m": 14.5},
    ],
    "water_level_m": 7.0,
    "foundation_level_m": 2.5,
    "foundation_level_mNGF": 36.0,
    "q_ELS_MPa": 0.25, "q_ELU_MPa": 0.42,
    "settlement_mm": 12.7,
    "preferred_footing_type": "sapata_corrida",
    "sismicidade_zona": "1",
    "parasismic_rules_required": False,
    "phi_deg": None, "gamma_kN_m3": 19.0,
}
