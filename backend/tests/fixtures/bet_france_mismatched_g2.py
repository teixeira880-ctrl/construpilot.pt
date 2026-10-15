"""Caso 1 — PC em Saint-Denis vs G2 em La Courneuve (moradas diferentes)."""

PC_DATA = {
    "project_address": "21 rue Georges Bizet, 93200 Saint-Denis, France",
    "project_parcel": "L 166",
    "country_code": None,
    "implantation": {"length_m": 15.0, "width_m": 8.0},
    "levels": {
        "cave_m": -1.50, "rdc_m": 0.90, "r_plus_1_m": 4.00,
        "comble_m": 7.50, "cumeeira_m": 11.00,
    },
    "walls_interior_resistant": [],
    "openings_facades": [],
    "stairs": [
        {"from": "cave", "to": "rdc", "height_m": 2.40},
        {"from": "rdc", "to": "r_plus_1", "height_m": 3.10},
        {"from": "r_plus_1", "to": "comble", "height_m": 3.18, "slope_deg": 33},
    ],
}

G2_DATA = {
    "project_address": "3 rue Beaufils, 93120 La Courneuve, France",
    "project_parcel": "AG/0087",
    "bc_sol_assentamento_m": 2.50,
    "q_ELS_MPa": 0.25, "q_ELU_MPa": 0.42,
    "sismicidade_zona": "1",
    "ka": 0.333, "k0": 0.500, "phi_deg": 30.0, "gamma_kN_m3": 19.0,
    "water_level_m": None,
}
