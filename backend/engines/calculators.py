"""Calculateurs de matériaux déterministes.

Refactor iter53 :
- Extraction de dataclasses (`PaintParams`, `TileParams`, `RoofFacadeParams`)
  pour ramener le nombre de paramètres < 6 par fonction et clarifier
  les contrats sans casser les appelants existants (compat kwargs).
"""
from dataclasses import dataclass
import math


def _ceil(x):
    return int(math.ceil(x - 1e-9))


# =============== PAINT ===============

@dataclass
class PaintParams:
    length: float
    width: float
    height: float
    doors: int = 1
    windows: int = 1
    coats: int = 2
    include_ceiling: bool = True
    coverage: float = 10.0
    price_per_litre: float = 6.5


def _paint_geometry(p: PaintParams) -> dict:
    perimeter = 2 * (p.length + p.width)
    wall_area = perimeter * p.height
    openings = p.doors * 2.0 + p.windows * 1.5
    ceiling = p.length * p.width if p.include_ceiling else 0
    net = max(0.0, wall_area - openings) + ceiling
    return {"wall_area": wall_area, "openings": openings,
            "ceiling": ceiling, "net": net}


def paint(*args, **kwargs) -> dict:
    """Calc peinture. Accepte `PaintParams(...)` OU les kwargs legacy."""
    p = args[0] if args and isinstance(args[0], PaintParams) else PaintParams(*args, **kwargs)
    geom = _paint_geometry(p)
    litres = geom["net"] * p.coats / p.coverage
    litres_margin = litres * 1.07
    primer = geom["net"] / (p.coverage * 1.15)
    return {
        "inputs": {"length": p.length, "width": p.width, "height": p.height,
                   "doors": p.doors, "windows": p.windows, "coats": p.coats,
                   "include_ceiling": p.include_ceiling},
        "results": [
            {"label": "Superfície bruta de paredes", "value": round(geom["wall_area"], 2), "unit": "m²"},
            {"label": "Vãos deduzidos", "value": round(geom["openings"], 2), "unit": "m²"},
            {"label": "Superfície de tecto", "value": round(geom["ceiling"], 2), "unit": "m²"},
            {"label": "Superfície a pintar", "value": round(geom["net"], 2), "unit": "m²"},
            {"label": f"Tinta ({p.coats} demãos, +7% margem)",
             "value": round(litres_margin, 1), "unit": "L"},
            {"label": "Primário", "value": round(primer * 1.07, 1), "unit": "L"},
        ],
        "materials": [
            {"name": "Tinta parede (lata 10 L)", "quantity": _ceil(litres_margin / 10),
             "unit": "pot 10L", "search": "peinture murale mate blanche 10L"},
            {"name": "Primário universal (lata 10 L)",
             "quantity": _ceil(primer * 1.07 / 10),
             "unit": "pot 10L", "search": "sous couche universelle 10L"},
            {"name": "Rolo + manga", "quantity": 2, "unit": "u",
             "search": "rouleau peinture manchon"},
            {"name": "Fita de pintor", "quantity": 2, "unit": "u",
             "search": "ruban masquage peinture"},
            {"name": "Lona de protecção", "quantity": 1, "unit": "u",
             "search": "bache protection chantier"},
        ],
        "estimated_budget": round(litres_margin * p.price_per_litre + primer * 4.5, 2),
    }


# =============== TILE ===============

@dataclass
class TileParams:
    area: float
    tile_length: float = 60
    tile_width: float = 60
    joint: float = 3
    pose: str = "droite"
    loss_pct: float | None = None
    tiles_per_box: int = 6
    price_per_sqm: float = 28.0


def _tile_default_loss(pose: str) -> float:
    return 12 if pose == "diagonale" else 8


def tile(*args, **kwargs) -> dict:
    p = args[0] if args and isinstance(args[0], TileParams) else TileParams(*args, **kwargs)
    loss = p.loss_pct if p.loss_pct is not None else _tile_default_loss(p.pose)
    tile_area = (p.tile_length / 100 + p.joint / 1000) * (p.tile_width / 100 + p.joint / 1000)
    net_area = p.area * (1 + loss / 100)
    tiles = _ceil(net_area / tile_area)
    boxes = _ceil(tiles / max(1, p.tiles_per_box))
    glue_bags = _ceil((p.area * 5.0) / 25)
    joint_bags = _ceil((p.area * (1.4 if p.tile_length <= 40 else 0.9)) / 5)
    return {
        "inputs": {"area": p.area, "tile_length": p.tile_length,
                   "tile_width": p.tile_width, "joint": p.joint,
                   "pose": p.pose, "loss_pct": loss},
        "results": [
            {"label": "Superfície com perdas", "value": round(net_area, 2), "unit": "m²"},
            {"label": "Número de azulejos", "value": tiles, "unit": "u"},
            {"label": "Número de caixas", "value": boxes, "unit": "caixa"},
            {"label": "Cola para azulejos", "value": glue_bags, "unit": "saco 25 kg"},
            {"label": "Junta", "value": joint_bags, "unit": "saco 5 kg"},
        ],
        "materials": [
            {"name": f"Azulejos {int(p.tile_length)}x{int(p.tile_width)}",
             "quantity": round(net_area, 2), "unit": "m²",
             "search": f"carrelage {int(p.tile_length)}x{int(p.tile_width)}"},
            {"name": "Cola para azulejos 25 kg", "quantity": glue_bags, "unit": "saco",
             "search": "colle carrelage 25 kg"},
            {"name": "Betumação juntas 5 kg", "quantity": joint_bags, "unit": "saco",
             "search": "joint carrelage 5kg"},
            {"name": "Cruzetas", "quantity": _ceil(tiles / 100), "unit": "caixa",
             "search": f"croisillon carrelage {int(p.joint)}mm"},
            {"name": "Primário de aderência", "quantity": _ceil(p.area / 30),
             "unit": "bidão", "search": "primaire accrochage carrelage"},
        ],
        "estimated_budget": round(net_area * p.price_per_sqm + glue_bags * 14
                                   + joint_bags * 12, 2),
    }


# =============== DRYWALL ===============

def drywall(area: float, plate_type: str = "BA13 standard", plate_length: float = 250,
            plate_width: float = 120, structure: str = "cloison", price_per_plate: float = 7.5) -> dict:
    plate_area = (plate_length / 100) * (plate_width / 100)
    layers = 2 if structure == "cloison" else 1
    net = area * 1.10 * layers
    plates = _ceil(net / plate_area)
    rails = _ceil(area * 0.9)         # ml rails R/U
    studs = _ceil(area * 1.7)         # ml montants
    suspentes = _ceil(area * 1.6) if structure == "plafond" else 0
    fourrures = _ceil(area * 1.4) if structure == "plafond" else 0
    screws = _ceil(plates * 30 * 1.08)
    screw_boxes = _ceil(screws / 500)
    bands = _ceil(area * 1.6)
    coating_kg = area * 1.2
    coating_bags = _ceil(coating_kg / 25)
    mats = [
        {"name": f"Plaque {plate_type} {int(plate_length)}x{int(plate_width)}", "quantity": plates,
         "unit": "placa", "search": f"plaque platre {plate_type} {int(plate_length)}x{int(plate_width)}"},
        {"name": "Perfil R48 (barra 3 m)", "quantity": _ceil(rails / 3), "unit": "barra",
         "search": "rail placo R48 3m"},
        {"name": "Prumo M48 (barra 3 m)", "quantity": _ceil(studs / 3), "unit": "barra",
         "search": "montant placo M48 3m"},
        {"name": "Parafusos TTPC 25mm", "quantity": screw_boxes, "unit": "caixa 500", "search": "vis placo TTPC 25"},
        {"name": "Fita de junta 150 m", "quantity": _ceil(bands / 150), "unit": "rolo",
         "search": "bande a joint placo 150m"},
        {"name": "Massa de junta 25 kg", "quantity": coating_bags, "unit": "saco", "search": "enduit joint placo 25kg"},
    ]
    results = [
        {"label": "Superfície com 10% de margem", "value": round(net, 2), "unit": "m²"},
        {"label": "Placas necessárias", "value": plates, "unit": "placa"},
        {"label": "Perfis", "value": rails, "unit": "ml"},
        {"label": "Prumos", "value": studs, "unit": "ml"},
        {"label": "Parafusos", "value": screws, "unit": "u"},
        {"label": "Fita de junta", "value": bands, "unit": "ml"},
        {"label": "Massa de junta", "value": coating_bags, "unit": "saco 25 kg"},
    ]
    if structure == "plafond":
        mats.insert(3, {"name": "Suspensor (pack 100)", "quantity": _ceil(suspentes / 100), "unit": "lote",
                        "search": "suspente placo lot 100"})
        mats.insert(4, {"name": "Ómega F530 (barra 3 m)", "quantity": _ceil(fourrures / 3), "unit": "barra",
                        "search": "fourrure F530 3m"})
        results.insert(3, {"label": "Suspensores", "value": suspentes, "unit": "u"})
        results.insert(4, {"label": "Ómegas", "value": fourrures, "unit": "ml"})
    return {
        "inputs": {"area": area, "plate_type": plate_type, "plate_length": plate_length,
                   "plate_width": plate_width, "structure": structure},
        "results": results, "materials": mats,
        "estimated_budget": round(plates * price_per_plate + rails * 2.2 + studs * 2.6 +
                                  suspentes * 0.9 + fourrures * 1.8 + screw_boxes * 12 +
                                  coating_bags * 18 + _ceil(bands / 150) * 6, 2),
    }


# =============== CONCRETE ===============

def _concrete_materials_for_mode(mode: str, *, vol_margin: float, cement_kg: float,
                                  sand_kg: float, gravel_kg: float,
                                  bags_35: int, length: float, width: float) -> list[dict]:
    mats: list[dict] = []
    if mode == "sacs":
        mats.append({"name": "Betão pronto 35 kg", "quantity": bags_35, "unit": "saco",
                     "search": "beton pret a l'emploi 35 kg"})
    elif mode == "toupie":
        mats.append({"name": "Betão entregue (autobetoneira)", "quantity": round(vol_margin, 2), "unit": "m³",
                     "search": "beton livre toupie m3"})
    else:
        mats += [
            {"name": "Cimento CEM II 35 kg", "quantity": _ceil(cement_kg / 35), "unit": "saco",
             "search": "ciment 35 kg CEM II"},
            {"name": "Areia 0/4", "quantity": _ceil(sand_kg / 35), "unit": "saco 35 kg",
             "search": "sable 0/4 sac"},
            {"name": "Godo 4/20", "quantity": _ceil(gravel_kg / 35), "unit": "saco 35 kg",
             "search": "gravier 4/20 sac"},
        ]
    mats.append({"name": "Malha electrossoldada ST25", "quantity": _ceil(length * width / 6),
                 "unit": "painel", "search": "treillis soude ST25"})
    return mats


def concrete(length: float, width: float, thickness_cm: float, mode: str = "sacs",
             price_per_m3: float = 135.0) -> dict:
    volume = length * width * (thickness_cm / 100)
    vol_margin = volume * 1.07
    bags_35 = _ceil(vol_margin / 0.0175)  # 1 sac 35kg ≈ 17,5 L de béton
    cement_kg = vol_margin * 350
    sand_kg = vol_margin * 700
    gravel_kg = vol_margin * 1100
    water_l = vol_margin * 175
    return {
        "inputs": {"length": length, "width": width, "thickness_cm": thickness_cm, "mode": mode},
        "results": [
            {"label": "Volume teórico", "value": round(volume, 3), "unit": "m³"},
            {"label": "Volume com 7% de margem", "value": round(vol_margin, 3), "unit": "m³"},
            {"label": "Sacos de betão 35 kg", "value": bags_35, "unit": "saco"},
            {"label": "Cimento", "value": round(cement_kg), "unit": "kg"},
            {"label": "Areia", "value": round(sand_kg), "unit": "kg"},
            {"label": "Godo", "value": round(gravel_kg), "unit": "kg"},
            {"label": "Água", "value": round(water_l), "unit": "L"},
        ],
        "materials": _concrete_materials_for_mode(
            mode, vol_margin=vol_margin, cement_kg=cement_kg, sand_kg=sand_kg,
            gravel_kg=gravel_kg, bags_35=bags_35, length=length, width=width),
        "estimated_budget": round(vol_margin * price_per_m3, 2),
    }


# =============== INSULATION ===============

LAMBDA = {"laine_de_verre": 0.032, "laine_de_roche": 0.035, "polystyrene": 0.031,
          "polyurethane": 0.022, "ouate_cellulose": 0.039, "fibre_de_bois": 0.038, "liege": 0.040}


def insulation(area: float, material: str = "laine_de_verre", thickness_mm: float | None = None,
               target_r: float | None = None, price_per_sqm: float = 12.0) -> dict:
    lam = LAMBDA.get(material, 0.035)
    if target_r and not thickness_mm:
        thickness_mm = round(target_r * lam * 1000)
    thickness_mm = thickness_mm or 200
    r_value = round((thickness_mm / 1000) / lam, 2)
    net = area * 1.06
    rolls = _ceil(net / 6.0)
    # Membrane pare-vapeur : vendue en rouleaux ~75 m² → convertir la surface
    ROLL_COVERAGE_M2 = 75.0
    vapor_rolls = _ceil(net / ROLL_COVERAGE_M2)
    return {
        "inputs": {"area": area, "material": material, "thickness_mm": thickness_mm,
                   "target_r": target_r},
        "results": [
            {"label": "Lambda do material", "value": lam, "unit": "W/m.K"},
            {"label": "Espessura escolhida", "value": thickness_mm, "unit": "mm"},
            {"label": "Resistência térmica R obtida", "value": r_value, "unit": "m².K/W"},
            {"label": "Superfície com 6% de margem", "value": round(net, 2), "unit": "m²"},
            {"label": "Rolos / pacotes (6 m²)", "value": rolls, "unit": "u"},
            {"label": "Rolos pára-vapor (75 m² / rolo)", "value": vapor_rolls, "unit": "u"},
        ],
        "materials": [
            {"name": f"{material.replace('_', ' ').title()} {thickness_mm} mm", "quantity": round(net, 2),
             "unit": "m²", "search": f"{material.replace('_', ' ')} {thickness_mm} mm"},
            {"name": "Membrana pára-vapor (rolo 75 m²)", "quantity": vapor_rolls, "unit": "rolo",
             "search": "membrane pare vapeur 75m2 rouleau"},
            {"name": "Adesivo pára-vapor", "quantity": _ceil(net / 40), "unit": "rolo",
             "search": "adhesif pare vapeur"},
        ],
        "estimated_budget": round(net * price_per_sqm * (thickness_mm / 200), 2),
    }


# =============== ROOF & FACADE ===============

@dataclass
class RoofFacadeParams:
    projected_m2: float = 100.0
    pitch_deg: float | None = 30
    rampant_m: float | None = None
    wall_perimeter_m: float = 0.0
    wall_height_m: float = 2.5
    openings_m2: float = 0.0
    ite_thickness_mm: int = 140


def _roof_slope(projected_m2: float, pitch_deg: float | None) -> tuple[float, float]:
    """Return (real_area, slope_ratio) for the projected surface at `pitch_deg`."""
    projected = max(0.0, projected_m2)
    pitch = pitch_deg if pitch_deg is not None else 0
    angle = math.radians(min(75, max(0, pitch)))
    real_area = round(projected / math.cos(angle) if angle < math.pi / 2 else projected, 2)
    slope_ratio = real_area / projected if projected else 1.0
    return real_area, slope_ratio


def _roof_facade_warnings(p: RoofFacadeParams) -> list[str]:
    warnings: list[str] = []
    if p.pitch_deg and p.pitch_deg > 60:
        warnings.append("Inclinação > 60° — verificar o resultado da superfície calculada")
    if not p.pitch_deg and not p.rampant_m:
        warnings.append("Sem inclinação nem rampante fornecidos — superfície real = superfície projectada")
    return warnings


def _roof_facade_materials(real_area: float, facade_net: float, projected: float,
                            ite_mm: int) -> list[dict]:
    return [
        # Toiture
        {"name": "Telha / ardósia (cobertura)",
         "quantity": round(real_area * 1.05, 2), "unit": "m²",
         "search": "tuile terre cuite couverture"},
        {"name": "Subtelha (rolo 75 m²)",
         "quantity": _ceil(real_area / 75), "unit": "rolo",
         "search": "ecran sous toiture HPV 75m2"},
        {"name": "Ripas 25×50 (barra 4 m)",
         "quantity": _ceil(real_area * 3 / 4), "unit": "barra",
         "search": "liteau bois 25x50 4m"},
        {"name": "Isolamento de sótão (lã rocha 240 mm)",
         "quantity": round(projected * 1.05, 2), "unit": "m²",
         "search": "laine de roche 240 mm combles"},
        # Façade ITE
        {"name": f"Painel ETIC {ite_mm} mm (pack 3 m²)",
         "quantity": _ceil(facade_net / 3), "unit": "paquet",
         "search": f"panneau ite polystyrene {ite_mm}mm"},
        {"name": "Cola ETIC (saco 25 kg)",
         "quantity": _ceil(facade_net / 4.5), "unit": "saco",
         "search": "colle enduit ite sac 25 kg"},
        {"name": "Reboco de acabamento (saco 25 kg)",
         "quantity": _ceil(facade_net / 3.5), "unit": "saco",
         "search": "enduit de finition sac 25 kg"},
        {"name": "Rede de fibra (rolo 50 m²)",
         "quantity": _ceil(facade_net / 50), "unit": "rolo",
         "search": "treillis armature ite rouleau 50m2"},
        {"name": "Tinta de fachada (lata 10 L)",
         "quantity": _ceil(facade_net * 0.15 / 10), "unit": "pot 10L",
         "search": "peinture facade acrylique 10L"},
    ]


def roof_facade(*args, **kwargs) -> dict:
    """Toitures inclinées + ITE façades.

    Accepte `RoofFacadeParams(...)` OU les kwargs legacy (compat).
    - Si `pitch_deg` est fourni : real_area = projected / cos(angle).
    - Sinon si `rampant_m` : conservé à titre indicatif (ratio moyen).
    """
    p = args[0] if args and isinstance(args[0], RoofFacadeParams) else RoofFacadeParams(*args, **kwargs)
    real_area, slope_ratio = _roof_slope(p.projected_m2, p.pitch_deg)
    facade_gross = round(p.wall_perimeter_m * p.wall_height_m, 2)
    facade_net = round(max(0.0, facade_gross - p.openings_m2), 2)

    return {
        "inputs": {
            "projected_m2": p.projected_m2, "pitch_deg": p.pitch_deg,
            "rampant_m": p.rampant_m, "wall_perimeter_m": p.wall_perimeter_m,
            "wall_height_m": p.wall_height_m, "openings_m2": p.openings_m2,
            "ite_thickness_mm": p.ite_thickness_mm,
        },
        "results": [
            {"label": "Superfície de cobertura projectada", "value": max(0.0, p.projected_m2), "unit": "m²"},
            {"label": "Superfície REAL (inclinada)", "value": real_area, "unit": "m²"},
            {"label": "Rácio de inclinação", "value": round(slope_ratio, 3), "unit": ""},
            {"label": "Fachada bruta", "value": facade_gross, "unit": "m²"},
            {"label": "Fachada líquida (- vãos)", "value": facade_net, "unit": "m²"},
        ],
        "materials": _roof_facade_materials(real_area, facade_net,
                                             max(0.0, p.projected_m2), p.ite_thickness_mm),
        "warnings": _roof_facade_warnings(p),
    }


CALCULATORS = {
    "paint": {"key": "paint", "name": "Pintura", "fn": paint, "icon": "PaintRoller",
              "fields": [
                  {"name": "length", "label": "Comprimento (m)", "type": "number", "default": 4},
                  {"name": "width", "label": "Largura (m)", "type": "number", "default": 3},
                  {"name": "height", "label": "Altura (m)", "type": "number", "default": 2.5},
                  {"name": "doors", "label": "Número de portas", "type": "number", "default": 1},
                  {"name": "windows", "label": "Número de janelas", "type": "number", "default": 1},
                  {"name": "coats", "label": "Número de demãos", "type": "number", "default": 2},
                  {"name": "include_ceiling", "label": "Pintar o tecto", "type": "boolean", "default": True},
              ]},
    "tile": {"key": "tile", "name": "Azulejos", "fn": tile, "icon": "GridFour",
             "fields": [
                 {"name": "area", "label": "Superfície (m²)", "type": "number", "default": 12},
                 {"name": "tile_length", "label": "Comprimento azulejo (cm)", "type": "number", "default": 60},
                 {"name": "tile_width", "label": "Largura azulejo (cm)", "type": "number", "default": 60},
                 {"name": "joint", "label": "Largura junta (mm)", "type": "number", "default": 3},
                 {"name": "pose", "label": "Tipo de assentamento", "type": "select",
                  "options": ["droite", "diagonale", "chevron"], "default": "droite",
                  "option_labels": {"droite": "Direita", "diagonale": "Diagonal", "chevron": "Espinha"}},
                 {"name": "tiles_per_box", "label": "Azulejos por caixa", "type": "number", "default": 6},
             ]},
    "drywall": {"key": "drywall", "name": "Pladur", "fn": drywall, "icon": "Wall",
                "fields": [
                    {"name": "area", "label": "Superfície (m²)", "type": "number", "default": 35},
                    {"name": "structure", "label": "Trabalho", "type": "select",
                     "options": ["cloison", "doublage", "plafond"], "default": "plafond",
                     "option_labels": {"cloison": "Divisória", "doublage": "Contra-mureta", "plafond": "Teto falso"}},
                    {"name": "plate_type", "label": "Tipo de placa", "type": "select",
                     "options": ["BA13 standard", "BA13 hydrofuge", "BA13 phonique", "BA18 haute dureté"],
                     "default": "BA13 standard",
                     "option_labels": {"BA13 standard": "BA13 standard",
                                        "BA13 hydrofuge": "BA13 hidrófugo",
                                        "BA13 phonique": "BA13 acústico",
                                        "BA18 haute dureté": "BA18 alta dureza"}},
                    {"name": "plate_length", "label": "Comprimento placa (cm)", "type": "number", "default": 250},
                    {"name": "plate_width", "label": "Largura placa (cm)", "type": "number", "default": 120},
                ]},
    "concrete": {"key": "concrete", "name": "Betão", "fn": concrete, "icon": "Cube",
                 "fields": [
                     {"name": "length", "label": "Comprimento (m)", "type": "number", "default": 5},
                     {"name": "width", "label": "Largura (m)", "type": "number", "default": 4},
                     {"name": "thickness_cm", "label": "Espessura (cm)", "type": "number", "default": 12},
                     {"name": "mode", "label": "Fornecimento", "type": "select",
                      "options": ["sacs", "toupie", "melange"], "default": "sacs",
                      "option_labels": {"sacs": "Sacos", "toupie": "Autobetoneira", "melange": "Mistura no local"}},
                 ]},
    "insulation": {"key": "insulation", "name": "Isolamento", "fn": insulation, "icon": "ThermometerSimple",
                   "fields": [
                       {"name": "area", "label": "Superfície (m²)", "type": "number", "default": 60},
                       {"name": "material", "label": "Material", "type": "select",
                        "options": list(LAMBDA.keys()), "default": "laine_de_verre",
                        "option_labels": {"laine_de_verre": "Lã de vidro",
                                           "laine_de_roche": "Lã de rocha",
                                           "polystyrene": "Poliestireno",
                                           "polyurethane": "Poliuretano",
                                           "ouate_cellulose": "Celulose insuflada",
                                           "fibre_de_bois": "Fibra de madeira",
                                           "liege": "Cortiça"}},
                       {"name": "thickness_mm", "label": "Espessura (mm)", "type": "number", "default": 200},
                       {"name": "target_r", "label": "R pretendido (opcional)", "type": "number", "default": None},
                   ]},
    "roof_facade": {"key": "roof_facade", "name": "Cobertura & Fachada ETIC", "fn": roof_facade, "icon": "Home",
                    "fields": [
                        {"name": "projected_m2", "label": "Superfície projectada (m²)", "type": "number", "default": 100},
                        {"name": "pitch_deg", "label": "Inclinação (°)", "type": "number", "default": 30},
                        {"name": "rampant_m", "label": "Comprimento inclinado (m, opcional)", "type": "number", "default": None},
                        {"name": "wall_perimeter_m", "label": "Perímetro fachada (m)", "type": "number", "default": 40},
                        {"name": "wall_height_m", "label": "Altura fachada (m)", "type": "number", "default": 5.5},
                        {"name": "openings_m2", "label": "Vãos totais (m²)", "type": "number", "default": 15},
                        {"name": "ite_thickness_mm", "label": "Espessura ETIC (mm)", "type": "number", "default": 140},
                    ]},
}
