"""Schéma typé et versionné du relevé de plans — contrat unique lu ensuite par le métré, le BET et le devis.

Le relevé produit par l'IA doit être STRICTEMENT conforme à ce schéma. La validation (pydantic) et les
contrôles de cohérence (checks.py) sont faits AVANT tout calcul : aucun dossier n'est produit sur un relevé
invalide. Chaque valeur peut porter sa source (coté / mesuré à l'échelle / hypothèse / absent).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SCHEMA_VERSION = "1.0"

#: sources possibles d'une valeur relevée, de la plus fiable à la moins fiable
SOURCES = ("cote", "mesure", "hypothese", "absent")
SOURCE_LABEL = {"cote": "coté sur plan", "mesure": "mesuré à l'échelle", "hypothese": "hypothèse", "absent": "absent"}


class _Open(BaseModel):
    model_config = ConfigDict(extra="allow")


class Envelope(_Open):
    length_x: float
    width_y: float
    wall_total_thickness: float
    wall_structural_thickness: float


class Side(_Open):
    axis: Literal["x", "y"]
    pos: float
    type: str


class LevelS(_Open):
    id: str
    name: str
    floor_top: float
    slab_thickness: float
    ceiling_height: float
    use: str


class Roof(_Open):
    type: str
    eaves_level: float
    ridge_level: float


class OpeningS(_Open):
    model_config = ConfigDict(extra="allow", populate_by_name=True)
    id: str
    level: str
    side: str
    a: float = Field(alias="from")
    to: float
    sill: float
    height: float
    kind: str


class Stair(_Open):
    x0: float
    x1: float
    y0: float
    y1: float
    type: str
    flights: list[dict]


class RoomS(_Open):
    name: str
    type: str
    x0: float
    y0: float
    x1: float
    y1: float


class Geotech(_Open):
    q_els_kpa: float
    q_elu_kpa: float


class Hypothesis(_Open):
    field: str
    value: Any = None
    source: Literal["cote", "mesure", "hypothese", "absent"]


class BuildingModelSchema(_Open):
    """Relevé complet d'une maison. extra='allow' : les champs _source / _comment / on_boundary… restent tolérés."""
    schema_version: str = SCHEMA_VERSION
    project: dict
    envelope: Envelope
    sides: dict[str, Side]
    levels: list[LevelS]
    roof: Roof
    openings: list[OpeningS]
    stair: Stair
    interior_walls: dict[str, list[dict]]
    rooms: dict[str, list[RoomS]]
    geotech: Geotech
    user_hypotheses: Optional[dict] = None
    hypotheses: Optional[list[Hypothesis]] = None
    extraction_notes: Optional[list[str]] = None


def validate(raw: dict) -> list[str]:
    """Erreurs de schéma (vide = conforme). Messages courts « chemin : message » pour renvoyer à l'IA ou l'utilisateur."""
    try:
        BuildingModelSchema.model_validate(raw)
        return []
    except ValidationError as exc:
        return [f"{'.'.join(str(x) for x in e['loc'])} : {e['msg']}" for e in exc.errors()][:25]


_NUM = {"type": "number"}


def json_schema() -> dict:
    """Schéma JSON passé à Claude (sortie structurée). Guide le relevé ; la validation stricte reste côté backend
    (pydantic + cohérence), car les maps à clés dynamiques (sides / rooms / interior_walls) ne peuvent pas être strictes."""
    side = {"type": "object", "properties": {"axis": {"type": "string", "enum": ["x", "y"]}, "pos": _NUM, "type": {"type": "string"}},
            "required": ["axis", "pos", "type"]}
    level = {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "floor_top": _NUM,
             "slab_thickness": _NUM, "ceiling_height": _NUM, "use": {"type": "string"}},
             "required": ["id", "name", "floor_top", "slab_thickness", "ceiling_height", "use"]}
    opening = {"type": "object", "properties": {"id": {"type": "string"}, "level": {"type": "string"}, "side": {"type": "string"},
               "from": _NUM, "to": _NUM, "sill": _NUM, "height": _NUM, "kind": {"type": "string"}},
               "required": ["id", "level", "side", "from", "to", "sill", "height", "kind"]}
    room = {"type": "object", "properties": {"name": {"type": "string"}, "type": {"type": "string"}, "x0": _NUM, "y0": _NUM,
            "x1": _NUM, "y1": _NUM}, "required": ["name", "type", "x0", "y0", "x1", "y1"]}
    hyp = {"type": "object", "properties": {"field": {"type": "string"}, "value": {}, "source": {"type": "string", "enum": list(SOURCES)}},
           "required": ["field", "source"]}
    return {"type": "object", "required": ["project", "envelope", "sides", "levels", "roof", "openings", "stair",
                                           "interior_walls", "rooms", "geotech"],
            "properties": {
                "schema_version": {"type": "string"},
                "project": {"type": "object"},
                "envelope": {"type": "object", "properties": {"length_x": _NUM, "width_y": _NUM, "wall_total_thickness": _NUM,
                             "wall_structural_thickness": _NUM},
                             "required": ["length_x", "width_y", "wall_total_thickness", "wall_structural_thickness"]},
                "sides": {"type": "object", "additionalProperties": side},
                "levels": {"type": "array", "items": level},
                "roof": {"type": "object", "properties": {"type": {"type": "string"}, "eaves_level": _NUM, "ridge_level": _NUM},
                         "required": ["type", "eaves_level", "ridge_level"]},
                "openings": {"type": "array", "items": opening},
                "stair": {"type": "object"},
                "interior_walls": {"type": "object"},
                "rooms": {"type": "object", "additionalProperties": {"type": "array", "items": room}},
                "geotech": {"type": "object", "properties": {"q_els_kpa": _NUM, "q_elu_kpa": _NUM}},
                "user_hypotheses": {"type": "object"},
                "hypotheses": {"type": "array", "items": hyp},
                "extraction_notes": {"type": "array", "items": {"type": "string"}}}}


def hypotheses_rows(raw: dict) -> list[tuple[str, str, str]]:
    """Lignes (champ, valeur, source) pour l'encadré « Hypothèses et sources » du dossier."""
    rows = []
    for h in (raw or {}).get("hypotheses") or []:
        if not isinstance(h, dict):
            continue
        val = h.get("value")
        rows.append((str(h.get("field", "")), "—" if val in (None, "") else str(val),
                     SOURCE_LABEL.get(str(h.get("source")), str(h.get("source") or "—"))))
    return rows


def extraction_metrics(raw: dict) -> dict:
    """Télémétrie de qualité du relevé : part des valeurs « absentes » dans les hypothèses déclarées par l'IA.
    Un taux élevé signale un PC mal renseigné (beaucoup de champs non cotés / déduits)."""
    hyps = [h for h in (raw or {}).get("hypotheses") or [] if isinstance(h, dict)]
    absent = [str(h.get("field") or "?") for h in hyps
              if str(h.get("source") or "").lower() == "absent" or h.get("value") in (None, "")]
    total = len(hyps)
    return {"schema_version": (raw or {}).get("schema_version") or SCHEMA_VERSION,
            "hyp_total": total, "hyp_absent": len(absent),
            "absent_rate": round(len(absent) / total, 3) if total else 0.0,
            "absent_fields": absent[:20]}
