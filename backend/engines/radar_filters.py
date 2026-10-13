"""Evidence-based, server-side facets. Unknown is not a private individual."""
import re
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator

FILTER_SCHEMA_VERSION = 1
WorkType = Literal["neuf", "extension", "renovation", "inconnu"]
BuildingType = Literal["maison", "collectif", "autre", "inconnu"]
ClientType = Literal["particulier", "promoteur", "entreprise", "syndic", "banque", "architecte", "autre", "inconnu"]
OPTIONS = {
    "work_types": [("neuf", "Construction neuve"), ("extension", "Extension / agrandissement"), ("renovation", "Rénovation / existant"), ("inconnu", "Non identifié")],
    "building_types": [("maison", "Maison individuelle"), ("collectif", "Immeuble collectif"), ("autre", "Autre bâtiment"), ("inconnu", "Non identifié")],
    "client_types": [("particulier", "Particulier"), ("promoteur", "Promoteur"), ("entreprise", "Entreprise / professionnel"), ("syndic", "Copropriété / syndic"), ("banque", "Banque"), ("architecte", "Architecte"), ("autre", "Autre organisme"), ("inconnu", "Non identifié")],
}


class RadarFilters(BaseModel):
    work_types: list[WorkType] = Field(default_factory=list, max_length=10)
    building_types: list[BuildingType] = Field(default_factory=list, max_length=10)
    client_types: list[ClientType] = Field(default_factory=list, max_length=10)

    @field_validator("work_types", "building_types", "client_types")
    @classmethod
    def distinct(cls, values):
        return sorted(set(values))


def filter_options():
    return {group: [{"value": key, "label": label} for key, label in options] for group, options in OPTIONS.items()}


def query_filters(saved, **params):
    values = dict(saved)
    for key, value in params.items():
        if value is not None:
            values[key] = [part.strip() for part in value.split(",") if part.strip()]
    try:
        return RadarFilters.model_validate(values).model_dump()
    except ValidationError as exc:
        raise HTTPException(422, "Catégorie de filtre Radar invalide.") from exc


def observed_categories(row, kind):
    """Keep SDES fields needed by filters, without interpreting names/APE as roles."""
    evidence = {key: row.get(key) for key in ("NATURE_PROJET_DECLAREE", "I_EXTENSION", "I_SURELEVATION", "TYPE_PRINCIP_LOGTS_CREES", "NB_LGT_IND_CREES", "NB_LGT_COL_CREES", "CJ_DEM", "APE_DEM")}
    work = []
    nature = row.get("NATURE_PROJET_DECLAREE")
    if type(nature) is int and nature == 1:
        work.append("neuf")
    if type(nature) is int and nature == 2:
        work.append("renovation")
    if row.get("I_EXTENSION") is True or row.get("I_SURELEVATION") is True:
        work.append("extension")
    building = []
    if kind == "locaux":
        building.append("autre")
    else:
        for key, category in (("NB_LGT_IND_CREES", "maison"), ("NB_LGT_COL_CREES", "collectif")):
            value = row.get(key)
            if type(value) in (int, float) and value > 0:
                building.append(category)
        principal = row.get("TYPE_PRINCIP_LOGTS_CREES")
        if not building and type(principal) is int:
            building = {1: ["maison"], 2: ["maison"], 3: ["collectif"], 4: ["autre"]}.get(principal, [])
    return {"work_types": sorted(work) or ["inconnu"], "building_types": sorted(building) or ["inconnu"],
            "filter_evidence": evidence, "filter_schema_version": FILTER_SCHEMA_VERSION}


def classification(permit):
    work = permit.get("work_types")
    if not work:
        work = [permit["nature"]] if permit.get("nature") in ("neuf", "renovation") else []
        if str(permit.get("batiment", "")).endswith(" · extension"):
            work.append("extension")
    building = permit.get("building_types") or (["autre"] if str(permit.get("batiment", "")).startswith("Locaux non résidentiels") else ["inconnu"])
    cj = str((permit.get("filter_evidence") or {}).get("CJ_DEM") or (permit.get("promoteur") or {}).get("categorie_juridique") or "")
    client = ("autre" if cj.startswith("7") else "entreprise") if re.fullmatch(r"[2-9]\d{3}", cj) else "inconnu"
    return {"work_types": sorted(set(work)) or ["inconnu"], "building_types": building, "client_type": client, "client_source": "sitadel" if client != "inconnu" else "unknown"}


def matches(item, selected, exclude=None):
    categories = item["classification"]
    for group, choices in selected.items():
        if group == exclude or not choices:
            continue
        values = [categories["client_type"]] if group == "client_types" else categories[group]
        if not set(choices).intersection(values):
            return False
    return True


def apply_filters(items, selected):
    facets = filter_options()
    for group, options in facets.items():
        candidates = [item for item in items if matches(item, selected, exclude=group)]
        for option in options:
            option["count"] = sum(matches(item, {group: [option["value"]]}) for item in candidates)
    return [item for item in items if matches(item, selected)], facets