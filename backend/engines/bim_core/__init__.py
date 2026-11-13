"""Núcleo BIM do ConstruPilot: planta lida → modelo métrico → IFC 4.3 (IfcOpenShell, LGPL-3.0)."""
from .ifc_builder import SCHEMA, build_ifc, stable_guid, summarize, validate
from .model import DEFAULTS, BuildingModel, ModelError, from_takeoff

__all__ = ["SCHEMA", "DEFAULTS", "BuildingModel", "ModelError", "build_ifc", "from_takeoff",
           "stable_guid", "summarize", "validate"]
