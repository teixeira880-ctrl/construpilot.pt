"""Seuils normatifs (DTU 36.3 France).

Structure configurable, préparée pour un support multi-pays en Phase 1+.
Toutes valeurs en millimètres, sauf pentes en degrés.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class StairNorms:
    """Seuils normatifs pour la conception d'escalier."""

    country_code: str
    standard: str

    # Hauteur de marche (h)
    riser_height_optimal_min_mm: float
    riser_height_optimal_max_mm: float
    riser_height_acceptable_min_mm: float
    riser_height_acceptable_max_mm: float
    riser_height_max_mm: float   # rouge au-delà

    # Giron (g)
    tread_depth_optimal_min_mm: float
    tread_depth_optimal_max_mm: float
    tread_depth_acceptable_min_mm: float
    tread_depth_max_mm: float  # au-delà = disproportionné mais pas dangereux
    tread_depth_hard_min_mm: float  # rouge en-deçà

    # Blondel (2h + g)
    blondel_optimal_min_mm: float
    blondel_optimal_max_mm: float
    blondel_acceptable_min_mm: float
    blondel_acceptable_max_mm: float

    # Pente (degrés)
    slope_optimal_min_deg: float
    slope_optimal_max_deg: float
    slope_acceptable_max_deg: float  # orange au-delà
    slope_hard_max_deg: float        # rouge au-delà

    # Échappée (headroom)
    headroom_min_mm: float
    headroom_optimal_mm: float

    # Largeur d'escalier
    stair_width_min_mm: float

    # Marches balancées (QT)
    winder_walkline_min_mm: float   # giron minimum sur ligne de foulée
    winder_inner_min_mm: float      # giron intérieur minimum
    winder_walkline_default_offset_mm: float

    def as_dict(self) -> Dict[str, float | str]:
        return {
            "country_code": self.country_code,
            "standard": self.standard,
            "riser_height_optimal_min_mm": self.riser_height_optimal_min_mm,
            "riser_height_optimal_max_mm": self.riser_height_optimal_max_mm,
            "riser_height_acceptable_min_mm": self.riser_height_acceptable_min_mm,
            "riser_height_acceptable_max_mm": self.riser_height_acceptable_max_mm,
            "riser_height_max_mm": self.riser_height_max_mm,
            "tread_depth_optimal_min_mm": self.tread_depth_optimal_min_mm,
            "tread_depth_optimal_max_mm": self.tread_depth_optimal_max_mm,
            "tread_depth_acceptable_min_mm": self.tread_depth_acceptable_min_mm,
            "tread_depth_max_mm": self.tread_depth_max_mm,
            "tread_depth_hard_min_mm": self.tread_depth_hard_min_mm,
            "blondel_optimal_min_mm": self.blondel_optimal_min_mm,
            "blondel_optimal_max_mm": self.blondel_optimal_max_mm,
            "blondel_acceptable_min_mm": self.blondel_acceptable_min_mm,
            "blondel_acceptable_max_mm": self.blondel_acceptable_max_mm,
            "slope_optimal_min_deg": self.slope_optimal_min_deg,
            "slope_optimal_max_deg": self.slope_optimal_max_deg,
            "slope_acceptable_max_deg": self.slope_acceptable_max_deg,
            "slope_hard_max_deg": self.slope_hard_max_deg,
            "headroom_min_mm": self.headroom_min_mm,
            "headroom_optimal_mm": self.headroom_optimal_mm,
            "stair_width_min_mm": self.stair_width_min_mm,
            "winder_walkline_min_mm": self.winder_walkline_min_mm,
            "winder_inner_min_mm": self.winder_inner_min_mm,
            "winder_walkline_default_offset_mm": self.winder_walkline_default_offset_mm,
        }


# DTU 36.3 France (valeurs usuelles)
DTU_36_3_FR = StairNorms(
    country_code="FR",
    standard="DTU 36.3",
    # h : optimal 160-180, acceptable 155-195, max 200
    riser_height_optimal_min_mm=160,
    riser_height_optimal_max_mm=180,
    riser_height_acceptable_min_mm=155,
    riser_height_acceptable_max_mm=195,
    riser_height_max_mm=200,
    # g : optimal 250-320, acceptable >= 220
    tread_depth_optimal_min_mm=250,
    tread_depth_optimal_max_mm=320,
    tread_depth_acceptable_min_mm=220,
    tread_depth_max_mm=400,
    tread_depth_hard_min_mm=220,
    # Blondel : optimal 600-640, acceptable 580-660
    blondel_optimal_min_mm=600,
    blondel_optimal_max_mm=640,
    blondel_acceptable_min_mm=580,
    blondel_acceptable_max_mm=660,
    # Pente
    slope_optimal_min_deg=28,
    slope_optimal_max_deg=33,
    slope_acceptable_max_deg=35,
    slope_hard_max_deg=40,
    # Échappée
    headroom_min_mm=1900,
    headroom_optimal_mm=2100,
    # Largeur
    stair_width_min_mm=700,
    # Winders
    winder_walkline_min_mm=240,
    winder_inner_min_mm=100,
    winder_walkline_default_offset_mm=500,
)
