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
            {"label": "Surface murs brute", "value": round(geom["wall_area"], 2), "unit": "m²"},
            {"label": "Surface ouvertures déduite", "value": round(geom["openings"], 2), "unit": "m²"},
            {"label": "Surface plafond", "value": round(geom["ceiling"], 2), "unit": "m²"},
            {"label": "Surface à peindre", "value": round(geom["net"], 2), "unit": "m²"},
            {"label": f"Peinture ({p.coats} couches, +7% marge)",
             "value": round(litres_margin, 1), "unit": "L"},
            {"label": "Sous-couche", "value": round(primer * 1.07, 1), "unit": "L"},
        ],
        "materials": [
            {"name": "Peinture murale (pot 10 L)", "quantity": _ceil(litres_margin / 10),
             "unit": "pot 10L", "search": "peinture murale mate blanche 10L"},
            {"name": "Sous-couche universelle (pot 10 L)",
             "quantity": _ceil(primer * 1.07 / 10),
             "unit": "pot 10L", "search": "sous couche universelle 10L"},
            {"name": "Rouleau + manchon", "quantity": 2, "unit": "u",
             "search": "rouleau peinture manchon"},
            {"name": "Adhésif de masquage", "quantity": 2, "unit": "u",
             "search": "ruban masquage peinture"},
            {"name": "Bâche de protection", "quantity": 1, "unit": "u",
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
            {"label": "Surface avec pertes", "value": round(net_area, 2), "unit": "m²"},
            {"label": "Nombre de carreaux", "value": tiles, "unit": "u"},
            {"label": "Nombre de cartons", "value": boxes, "unit": "carton"},
            {"label": "Colle à carrelage", "value": glue_bags, "unit": "sac 25 kg"},
            {"label": "Joint", "value": joint_bags, "unit": "sac 5 kg"},
        ],
        "materials": [
            {"name": f"Carrelage {int(p.tile_length)}x{int(p.tile_width)}",
             "quantity": round(net_area, 2), "unit": "m²",
             "search": f"carrelage {int(p.tile_length)}x{int(p.tile_width)}"},
            {"name": "Colle à carrelage 25 kg", "quantity": glue_bags, "unit": "sac",
             "search": "colle carrelage 25 kg"},
            {"name": "Joint carrelage 5 kg", "quantity": joint_bags, "unit": "sac",
             "search": "joint carrelage 5kg"},
            {"name": "Croisillons", "quantity": _ceil(tiles / 100), "unit": "boîte",
             "search": f"croisillon carrelage {int(p.joint)}mm"},
            {"name": "Primaire d'accrochage", "quantity": _ceil(p.area / 30),
             "unit": "bidon", "search": "primaire accrochage carrelage"},
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
         "unit": "plaque", "search": f"plaque platre {plate_type} {int(plate_length)}x{int(plate_width)}"},
        {"name": "Rail R48 (barre 3 m)", "quantity": _ceil(rails / 3), "unit": "barre",
         "search": "rail placo R48 3m"},
        {"name": "Montant M48 (barre 3 m)", "quantity": _ceil(studs / 3), "unit": "barre",
         "search": "montant placo M48 3m"},
        {"name": "Vis TTPC 25mm", "quantity": screw_boxes, "unit": "boîte 500", "search": "vis placo TTPC 25"},
        {"name": "Bande à joint 150 m", "quantity": _ceil(bands / 150), "unit": "rouleau",
         "search": "bande a joint placo 150m"},
        {"name": "Enduit à joint 25 kg", "quantity": coating_bags, "unit": "sac", "search": "enduit joint placo 25kg"},
    ]
    results = [
        {"label": "Surface avec 10% de marge", "value": round(net, 2), "unit": "m²"},
        {"label": "Plaques nécessaires", "value": plates, "unit": "plaque"},
        {"label": "Rails", "value": rails, "unit": "ml"},
        {"label": "Montants", "value": studs, "unit": "ml"},
        {"label": "Vis", "value": screws, "unit": "u"},
        {"label": "Bande à joint", "value": bands, "unit": "ml"},
        {"label": "Enduit", "value": coating_bags, "unit": "sac 25 kg"},
    ]
    if structure == "plafond":
        mats.insert(3, {"name": "Suspente (lot 100)", "quantity": _ceil(suspentes / 100), "unit": "lot",
                        "search": "suspente placo lot 100"})
        mats.insert(4, {"name": "Fourrure F530 (barre 3 m)", "quantity": _ceil(fourrures / 3), "unit": "barre",
                        "search": "fourrure F530 3m"})
        results.insert(3, {"label": "Suspentes", "value": suspentes, "unit": "u"})
        results.insert(4, {"label": "Fourrures", "value": fourrures, "unit": "ml"})
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
        mats.append({"name": "Béton prêt à l'emploi 35 kg", "quantity": bags_35, "unit": "sac",
                     "search": "beton pret a l'emploi 35 kg"})
    elif mode == "toupie":
        mats.append({"name": "Béton livré (toupie)", "quantity": round(vol_margin, 2), "unit": "m³",
                     "search": "beton livre toupie m3"})
    else:
        mats += [
            {"name": "Ciment CEM II 35 kg", "quantity": _ceil(cement_kg / 35), "unit": "sac",
             "search": "ciment 35 kg CEM II"},
            {"name": "Sable 0/4", "quantity": _ceil(sand_kg / 35), "unit": "sac 35 kg",
             "search": "sable 0/4 sac"},
            {"name": "Gravier 4/20", "quantity": _ceil(gravel_kg / 35), "unit": "sac 35 kg",
             "search": "gravier 4/20 sac"},
        ]
    mats.append({"name": "Treillis soudé ST25", "quantity": _ceil(length * width / 6),
                 "unit": "panneau", "search": "treillis soude ST25"})
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
            {"label": "Volume théorique", "value": round(volume, 3), "unit": "m³"},
            {"label": "Volume avec 7% de marge", "value": round(vol_margin, 3), "unit": "m³"},
            {"label": "Sacs de béton 35 kg", "value": bags_35, "unit": "sac"},
            {"label": "Ciment", "value": round(cement_kg), "unit": "kg"},
            {"label": "Sable", "value": round(sand_kg), "unit": "kg"},
            {"label": "Gravier", "value": round(gravel_kg), "unit": "kg"},
            {"label": "Eau", "value": round(water_l), "unit": "L"},
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
            {"label": "Lambda du matériau", "value": lam, "unit": "W/m.K"},
            {"label": "Épaisseur retenue", "value": thickness_mm, "unit": "mm"},
            {"label": "Résistance thermique R obtenue", "value": r_value, "unit": "m².K/W"},
            {"label": "Surface avec 6% de marge", "value": round(net, 2), "unit": "m²"},
            {"label": "Rouleaux / paquets (6 m²)", "value": rolls, "unit": "u"},
            {"label": "Rouleaux pare-vapeur (75 m² / rouleau)", "value": vapor_rolls, "unit": "u"},
        ],
        "materials": [
            {"name": f"{material.replace('_', ' ').title()} {thickness_mm} mm", "quantity": round(net, 2),
             "unit": "m²", "search": f"{material.replace('_', ' ')} {thickness_mm} mm"},
            {"name": "Membrane pare-vapeur (rouleau 75 m²)", "quantity": vapor_rolls, "unit": "rouleau",
             "search": "membrane pare vapeur 75m2 rouleau"},
            {"name": "Adhésif pare-vapeur", "quantity": _ceil(net / 40), "unit": "rouleau",
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
        warnings.append("Pente > 60° — vérifier le rendu de la surface calculée")
    if not p.pitch_deg and not p.rampant_m:
        warnings.append("Ni pente ni rampant fournis — surface réelle = surface projetée")
    return warnings


def _roof_facade_materials(real_area: float, facade_net: float, projected: float,
                            ite_mm: int) -> list[dict]:
    return [
        # Toiture
        {"name": "Tuile / ardoise (couverture)",
         "quantity": round(real_area * 1.05, 2), "unit": "m²",
         "search": "tuile terre cuite couverture"},
        {"name": "Écran sous-toiture (rouleau 75 m²)",
         "quantity": _ceil(real_area / 75), "unit": "rouleau",
         "search": "ecran sous toiture HPV 75m2"},
        {"name": "Liteaux 25×50 (barre 4 m)",
         "quantity": _ceil(real_area * 3 / 4), "unit": "barre",
         "search": "liteau bois 25x50 4m"},
        {"name": "Isolation combles (laine roche 240 mm)",
         "quantity": round(projected * 1.05, 2), "unit": "m²",
         "search": "laine de roche 240 mm combles"},
        # Façade ITE
        {"name": f"Panneau ITE {ite_mm} mm (paquet 3 m²)",
         "quantity": _ceil(facade_net / 3), "unit": "paquet",
         "search": f"panneau ite polystyrene {ite_mm}mm"},
        {"name": "Colle ITE (sac 25 kg)",
         "quantity": _ceil(facade_net / 4.5), "unit": "sac",
         "search": "colle enduit ite sac 25 kg"},
        {"name": "Enduit de finition (sac 25 kg)",
         "quantity": _ceil(facade_net / 3.5), "unit": "sac",
         "search": "enduit de finition sac 25 kg"},
        {"name": "Treillis fibre (rouleau 50 m²)",
         "quantity": _ceil(facade_net / 50), "unit": "rouleau",
         "search": "treillis armature ite rouleau 50m2"},
        {"name": "Peinture façade (pot 10 L)",
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
            {"label": "Surface toiture projetée", "value": max(0.0, p.projected_m2), "unit": "m²"},
            {"label": "Surface toiture RÉELLE (rampant)", "value": real_area, "unit": "m²"},
            {"label": "Ratio pente", "value": round(slope_ratio, 3), "unit": ""},
            {"label": "Façade brute", "value": facade_gross, "unit": "m²"},
            {"label": "Façade nette (- ouvertures)", "value": facade_net, "unit": "m²"},
        ],
        "materials": _roof_facade_materials(real_area, facade_net,
                                             max(0.0, p.projected_m2), p.ite_thickness_mm),
        "warnings": _roof_facade_warnings(p),
    }


CALCULATORS = {
    "paint": {"key": "paint", "name": "Peinture", "fn": paint, "icon": "PaintRoller",
              "fields": [
                  {"name": "length", "label": "Longueur (m)", "type": "number", "default": 4},
                  {"name": "width", "label": "Largeur (m)", "type": "number", "default": 3},
                  {"name": "height", "label": "Hauteur (m)", "type": "number", "default": 2.5},
                  {"name": "doors", "label": "Nombre de portes", "type": "number", "default": 1},
                  {"name": "windows", "label": "Nombre de fenêtres", "type": "number", "default": 1},
                  {"name": "coats", "label": "Nombre de couches", "type": "number", "default": 2},
                  {"name": "include_ceiling", "label": "Peindre le plafond", "type": "boolean", "default": True},
              ]},
    "tile": {"key": "tile", "name": "Carrelage", "fn": tile, "icon": "GridFour",
             "fields": [
                 {"name": "area", "label": "Surface (m²)", "type": "number", "default": 12},
                 {"name": "tile_length", "label": "Longueur carreau (cm)", "type": "number", "default": 60},
                 {"name": "tile_width", "label": "Largeur carreau (cm)", "type": "number", "default": 60},
                 {"name": "joint", "label": "Largeur joint (mm)", "type": "number", "default": 3},
                 {"name": "pose", "label": "Type de pose", "type": "select",
                  "options": ["droite", "diagonale", "chevron"], "default": "droite"},
                 {"name": "tiles_per_box", "label": "Carreaux par carton", "type": "number", "default": 6},
             ]},
    "drywall": {"key": "drywall", "name": "Placo", "fn": drywall, "icon": "Wall",
                "fields": [
                    {"name": "area", "label": "Surface (m²)", "type": "number", "default": 35},
                    {"name": "structure", "label": "Ouvrage", "type": "select",
                     "options": ["cloison", "doublage", "plafond"], "default": "plafond"},
                    {"name": "plate_type", "label": "Type de plaque", "type": "select",
                     "options": ["BA13 standard", "BA13 hydrofuge", "BA13 phonique", "BA18 haute dureté"],
                     "default": "BA13 standard"},
                    {"name": "plate_length", "label": "Longueur plaque (cm)", "type": "number", "default": 250},
                    {"name": "plate_width", "label": "Largeur plaque (cm)", "type": "number", "default": 120},
                ]},
    "concrete": {"key": "concrete", "name": "Béton", "fn": concrete, "icon": "Cube",
                 "fields": [
                     {"name": "length", "label": "Longueur (m)", "type": "number", "default": 5},
                     {"name": "width", "label": "Largeur (m)", "type": "number", "default": 4},
                     {"name": "thickness_cm", "label": "Épaisseur (cm)", "type": "number", "default": 12},
                     {"name": "mode", "label": "Approvisionnement", "type": "select",
                      "options": ["sacs", "toupie", "melange"], "default": "sacs"},
                 ]},
    "insulation": {"key": "insulation", "name": "Isolation", "fn": insulation, "icon": "ThermometerSimple",
                   "fields": [
                       {"name": "area", "label": "Surface (m²)", "type": "number", "default": 60},
                       {"name": "material", "label": "Matériau", "type": "select",
                        "options": list(LAMBDA.keys()), "default": "laine_de_verre"},
                       {"name": "thickness_mm", "label": "Épaisseur (mm)", "type": "number", "default": 200},
                       {"name": "target_r", "label": "R visé (optionnel)", "type": "number", "default": None},
                   ]},
    "roof_facade": {"key": "roof_facade", "name": "Toiture & Façade ITE", "fn": roof_facade, "icon": "Home",
                    "fields": [
                        {"name": "projected_m2", "label": "Surface toiture projetée (m²)", "type": "number", "default": 100},
                        {"name": "pitch_deg", "label": "Pente (°)", "type": "number", "default": 30},
                        {"name": "rampant_m", "label": "Longueur rampant (m, optionnel)", "type": "number", "default": None},
                        {"name": "wall_perimeter_m", "label": "Périmètre façade (m)", "type": "number", "default": 40},
                        {"name": "wall_height_m", "label": "Hauteur façade (m)", "type": "number", "default": 5.5},
                        {"name": "openings_m2", "label": "Ouvertures totales (m²)", "type": "number", "default": 15},
                        {"name": "ite_thickness_mm", "label": "Épaisseur ITE (mm)", "type": "number", "default": 140},
                    ]},
}
