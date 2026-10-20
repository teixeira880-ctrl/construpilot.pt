"""Module béton armé — pré-dimensionnement + métré + ferraillage indicatif.

⚠️ Toutes les valeurs retournées sont indicatives (pré-dimensionnement).
La validation par un ingénieur structure est OBLIGATOIRE avant exécution.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .concrete_abaques import (
    CONCRETE_CLASSES, COVER_MM_BY_EXPOSURE, EXPOSURE_CLASSES,
    STEEL_GRADES, lookup_paillasse_thickness,
)
from .models import Alert, StairResult


DENSITY_HA_KG_PER_M_PER_MM2 = 0.617e-3  # 0.617 kg/m pour Ø=1mm → coef 0.617 × d² × 10⁻³
CONCRETE_DENSITY_KN_M3 = 25.0


class ConcreteAnalysisInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stair_result: StairResult
    stair_type: str = "straight"
    concrete_class: str = Field(default="C25/30")
    steel_grade: str = Field(default="B500B")
    exposure_class: str = Field(default="XC1")
    live_load_kN_m2: float = Field(default=2.5, ge=0, le=20)
    dead_load_extra_kN_m2: float = Field(default=1.5, ge=0, le=20)
    slab_span_mm: Optional[float] = None
    support_type: Literal["simple", "encastree_haut", "encastree_bas", "bi_encastree"] = "simple"
    is_flying: bool = False


class NomenclatureRow(BaseModel):
    repere: str
    designation: str
    diameter: str
    length_m: float
    count: int
    total_length_m: float
    weight_kg: float


class ConcreteAnalysisResult(BaseModel):
    stair_type: str
    quantities: Dict[str, float]
    load_breakdown_kN_m2: Dict[str, float]
    paillasse: Dict[str, Any]
    reinforcement: Dict[str, Any]
    nomenclature: List[NomenclatureRow]
    alerts: List[Alert]
    disclaimer: Dict[str, str]
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _steel_weight_per_m(diameter_mm: float) -> float:
    """Retourne le poids linéique acier HA en kg/m.
    Formule : (π/4) × d² × 7850 kg/m³ × 10⁻⁶ ≈ 0.006165 × d².
    Ex : Ø12 → 0.888 kg/m ; Ø8 → 0.395 kg/m.
    """
    return 0.006165 * diameter_mm * diameter_mm


def compute_concrete_analysis(inp: ConcreteAnalysisInput) -> ConcreteAnalysisResult:
    alerts: List[Alert] = []

    if inp.concrete_class not in CONCRETE_CLASSES:
        alerts.append(Alert(level="orange", code="CONCRETE_CLASS_UNUSUAL",
                            message_fr=f"Classe béton non standard '{inp.concrete_class}'."))
    if inp.steel_grade not in STEEL_GRADES:
        alerts.append(Alert(level="orange", code="STEEL_GRADE_UNUSUAL",
                            message_fr=f"Nuance acier non standard '{inp.steel_grade}'."))
    if inp.exposure_class not in EXPOSURE_CLASSES:
        inp.exposure_class = "XC1"
    if inp.exposure_class in ("XC3", "XC4"):
        alerts.append(Alert(level="orange", code="HIGH_EXPOSURE_REQUIRES_VALIDATION",
                            message_fr=f"Classe d'exposition {inp.exposure_class} : validation BE requise pour enrobage/durabilité."))

    r = inp.stair_result

    # ---------- Géométrie / métré ----------
    stair_run_mm = r.stair_run_mm or (r.num_treads * r.tread_depth_mm)
    stair_length_mm = r.stair_length_mm or math.sqrt((r.num_steps * r.riser_height_mm) ** 2 + stair_run_mm ** 2)
    # Largeur utile : depuis required_stairwell_mm.min_width_mm ou stair_width
    width_mm = r.required_stairwell_mm.get("min_width_mm", 900) or 900

    span_mm = inp.slab_span_mm or stair_length_mm

    # Épaisseur paillasse minimum L/25 (DTU 21 simple appui)
    thickness_min_L25 = span_mm / 25

    # Charge poids propre estimée (dépendante de l'épaisseur : itératif possible ; on prend 150mm par défaut)
    self_weight_kN_m2 = 0.15 * CONCRETE_DENSITY_KN_M3  # 3.75 kN/m²
    load_total = inp.live_load_kN_m2 + inp.dead_load_extra_kN_m2 + self_weight_kN_m2

    thickness_reco, abaque_line, out_of_abaque = lookup_paillasse_thickness(span_mm, load_total)
    if out_of_abaque:
        alerts.append(Alert(level="red", code="PAILLASSE_OUT_OF_ABAQUE",
                            message_fr=f"Portée {span_mm:.0f} mm ou charge {load_total:.1f} kN/m² hors abaque simplifié. Calcul EC2 requis."))
    if span_mm > 5000:
        alerts.append(Alert(level="red", code="SPAN_EXCEEDS_SIMPLE_ANALYSIS",
                            message_fr=f"Portée {span_mm:.0f} mm > 5000 mm : calcul Eurocode 2 rigoureux nécessaire."))

    # Recalcul poids propre avec épaisseur retenue
    thickness_final = max(thickness_reco, thickness_min_L25) if thickness_reco > 0 else thickness_min_L25
    self_weight_final = (thickness_final / 1000) * CONCRETE_DENSITY_KN_M3
    load_total_final = inp.live_load_kN_m2 + inp.dead_load_extra_kN_m2 + self_weight_final

    if thickness_final < thickness_min_L25:
        alerts.append(Alert(level="red", code="PAILLASSE_THICKNESS_INSUFFICIENT",
                            message_fr=f"Épaisseur paillasse {thickness_final:.0f} mm < L/25 = {thickness_min_L25:.0f} mm."))

    # Volume béton (paillasse rampante + marches)
    paillasse_area_m2 = (stair_length_mm / 1000) * (width_mm / 1000)
    paillasse_volume_m3 = paillasse_area_m2 * (thickness_final / 1000)
    # Marches (triangles) : (giron × h × largeur) / 2 × nb marches
    tread_volume_m3 = (r.tread_depth_mm / 1000) * (r.riser_height_mm / 1000) * (width_mm / 1000) / 2 * r.num_treads
    total_volume_m3 = paillasse_volume_m3 + tread_volume_m3

    # Coffrage : sous-face paillasse + 2 joues + front des marches
    formwork_paillasse = paillasse_area_m2
    formwork_joues = 2 * (stair_length_mm / 1000) * (thickness_final / 1000)
    formwork_marches = r.num_treads * (r.riser_height_mm / 1000) * (width_mm / 1000)
    formwork_area_m2 = formwork_paillasse + formwork_joues + formwork_marches

    # ---------- Pré-dim aciers ----------
    cover_mm = COVER_MM_BY_EXPOSURE.get(inp.exposure_class, 25)
    main_diam = 12  # HA12 par défaut
    d = thickness_final - cover_mm - main_diam / 2  # hauteur utile
    fyd = 435.0  # MPa (B500B / 1.15)

    # Moment de calcul par mètre de largeur (ELU simplifié) : M = 1.35g + 1.5q, L²/8
    # ELU load
    load_ELU = 1.35 * (inp.dead_load_extra_kN_m2 + self_weight_final) + 1.5 * inp.live_load_kN_m2
    M_ELU_kNm_per_m = load_ELU * (span_mm / 1000) ** 2 / 8  # kNm/m
    # Section acier par m : As = M / (0.9 × d × fyd) — d en m, fyd en MPa → As en m²
    As_m2_per_m = M_ELU_kNm_per_m * 1e-3 / (0.9 * (d / 1000) * fyd * 1000) if d > 0 else 0
    As_mm2_per_m = As_m2_per_m * 1e6
    # Espacement : As_par_barre = π × (Ø/2)². Nb barres/m = As_mm2_per_m / (π × (Ø/2)²)
    A_bar_mm2 = math.pi * (main_diam / 2) ** 2
    bars_per_m = max(6, math.ceil(As_mm2_per_m / A_bar_mm2))
    main_spacing_mm = min(200, int(1000 / bars_per_m) // 10 * 10) or 150
    # Nombre total barres principales = largeur / espacement + 1
    main_count = max(4, int(width_mm / main_spacing_mm) + 1)

    # Longueur d'ancrage
    lb_mm = 40 * main_diam

    main_length_mm = stair_length_mm + 2 * lb_mm
    main_length_m = main_length_mm / 1000
    main_weight = _steel_weight_per_m(main_diam) * main_length_m * main_count

    # Répartition
    dist_diam = 8
    dist_spacing_mm = 200
    dist_count = int(stair_length_mm / dist_spacing_mm) + 1
    dist_length_m = width_mm / 1000
    dist_weight = _steel_weight_per_m(dist_diam) * dist_length_m * dist_count

    # Chapeaux (aciers de continuité sur appuis)
    upper_diam = 10
    upper_spacing_mm = 200
    upper_count = max(4, int(width_mm / upper_spacing_mm) + 1)
    upper_length_m = (span_mm / 4) / 1000 + lb_mm / 1000
    upper_weight = _steel_weight_per_m(upper_diam) * upper_length_m * upper_count * 2  # 2 appuis

    # Aciers contremarches
    tread_diam = 6
    tread_length_m = width_mm / 1000
    tread_count_per_riser = 2
    tread_count = tread_count_per_riser * r.num_treads
    tread_weight = _steel_weight_per_m(tread_diam) * tread_length_m * tread_count

    # Attentes en pied
    starter_diam = main_diam
    starter_count = max(4, main_count // 2)
    starter_length_m = (40 * starter_diam + 200) / 1000
    starter_weight = _steel_weight_per_m(starter_diam) * starter_length_m * starter_count

    total_steel_kg = main_weight + dist_weight + upper_weight + tread_weight + starter_weight

    reinforcement = {
        "main_bars": {"diameter_mm": main_diam, "spacing_mm": main_spacing_mm,
                      "count": main_count, "length_mm": round(main_length_mm, 0)},
        "distribution_bars": {"diameter_mm": dist_diam, "spacing_mm": dist_spacing_mm,
                              "count": dist_count, "length_mm": round(dist_length_m * 1000, 0)},
        "upper_bars": {"diameter_mm": upper_diam, "spacing_mm": upper_spacing_mm,
                       "count": upper_count * 2, "length_mm": round(upper_length_m * 1000, 0)},
        "tread_bars": {"diameter_mm": tread_diam, "count_per_riser": tread_count_per_riser,
                       "length_mm": round(tread_length_m * 1000, 0)},
        "starter_bars": {"diameter_mm": starter_diam, "count": starter_count,
                         "length_mm": round(starter_length_m * 1000, 0)},
        "anchor_length_mm": lb_mm,
        "cover_mm": cover_mm,
        "total_steel_kg": round(total_steel_kg, 2),
        "As_computed_mm2_per_m": round(As_mm2_per_m, 1),
        "utile_height_d_mm": round(d, 1),
        "M_ELU_kNm_per_m": round(M_ELU_kNm_per_m, 2),
    }

    nomenclature: List[NomenclatureRow] = [
        NomenclatureRow(repere="1", designation="Armature principale inférieure",
                        diameter=f"HA{main_diam}", length_m=round(main_length_m, 2),
                        count=main_count, total_length_m=round(main_length_m * main_count, 2),
                        weight_kg=round(main_weight, 2)),
        NomenclatureRow(repere="2", designation="Armature de répartition",
                        diameter=f"HA{dist_diam}", length_m=round(dist_length_m, 2),
                        count=dist_count, total_length_m=round(dist_length_m * dist_count, 2),
                        weight_kg=round(dist_weight, 2)),
        NomenclatureRow(repere="3", designation="Chapeaux sur appuis",
                        diameter=f"HA{upper_diam}", length_m=round(upper_length_m, 2),
                        count=upper_count * 2,
                        total_length_m=round(upper_length_m * upper_count * 2, 2),
                        weight_kg=round(upper_weight, 2)),
        NomenclatureRow(repere="4", designation="Aciers de contremarche",
                        diameter=f"HA{tread_diam}", length_m=round(tread_length_m, 2),
                        count=tread_count, total_length_m=round(tread_length_m * tread_count, 2),
                        weight_kg=round(tread_weight, 2)),
        NomenclatureRow(repere="5", designation="Attentes en pied",
                        diameter=f"HA{starter_diam}", length_m=round(starter_length_m, 2),
                        count=starter_count,
                        total_length_m=round(starter_length_m * starter_count, 2),
                        weight_kg=round(starter_weight, 2)),
    ]

    # Disclaimer systématique (orange informatif)
    alerts.append(Alert(level="orange", code="CONCRETE_ANALYSIS_INDICATIVE",
                        message_fr="Analyse indicative — validation BE requise avant exécution."))

    if inp.is_flying:
        alerts.append(Alert(level="red", code="FLYING_STAIRS_OUT_OF_SCOPE",
                            message_fr="Les escaliers suspendus (marches flottantes) ne sont pas dans le périmètre Phase 3."))

    return ConcreteAnalysisResult(
        stair_type=inp.stair_type,
        quantities={
            "concrete_volume_m3": round(total_volume_m3, 3),
            "paillasse_volume_m3": round(paillasse_volume_m3, 3),
            "tread_volume_m3": round(tread_volume_m3, 3),
            "formwork_area_m2": round(formwork_area_m2, 2),
            "paillasse_area_m2": round(paillasse_area_m2, 2),
            "tread_count": float(r.num_treads),
            "riser_count": float(r.num_steps),
            "landing_count": 0.0,
            "landing_area_m2": 0.0,
            "paillasse_length_mm": round(stair_length_mm, 1),
            "paillasse_thickness_mm": round(thickness_final, 0),
            "width_mm": round(width_mm, 0),
        },
        load_breakdown_kN_m2={
            "live_load": inp.live_load_kN_m2,
            "dead_load_extra": inp.dead_load_extra_kN_m2,
            "self_weight": round(self_weight_final, 2),
            "total_ELS": round(load_total_final, 2),
            "total_ELU": round(load_ELU, 2),
        },
        paillasse={
            "thickness_recommended_mm": round(thickness_final, 0),
            "thickness_min_L25_mm": round(thickness_min_L25, 0),
            "span_mm": round(span_mm, 0),
            "abaque_used": abaque_line,
            "concrete_class": inp.concrete_class,
            "steel_grade": inp.steel_grade,
            "exposure_class": inp.exposure_class,
            "support_type": inp.support_type,
        },
        reinforcement=reinforcement,
        nomenclature=nomenclature,
        alerts=alerts,
        disclaimer={
            "level": "warning",
            "message_fr": (
                "Les calculs de pré-dimensionnement et le schéma de ferraillage sont indicatifs. "
                "Ils reposent sur des abaques simplifiés DTU 21 et ne remplacent pas une étude "
                "structurelle complète conforme à l'Eurocode 2. Toute exécution doit être validée "
                "par un ingénieur structure titulaire des qualifications requises."
            ),
        },
    )
