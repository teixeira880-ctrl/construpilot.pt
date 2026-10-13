"""Source classification and faceting fixtures only; no upstream requests or mail."""
import pytest
from engines.radar_filters import (
    OPTIONS,
    RadarFilters,
    apply_filters,
    classification,
    observed_categories,
    query_filters,
)
from engines.sitadel_text import repair_cached_address, repair_source_row
from fastapi import HTTPException


@pytest.mark.parametrize("value", [None, "1", "true", "false", 1, 0, 2])
def test_extension_requires_actual_boolean(value):
    assert "extension" not in observed_categories({"I_EXTENSION": value}, "logements")["work_types"]


def test_new_individual_house_from_observed_counters():
    result = observed_categories({"NATURE_PROJET_DECLAREE": 1, "NB_LGT_IND_CREES": 2, "NB_LGT_COL_CREES": 0}, "logements")
    assert result["work_types"] == ["neuf"]
    assert result["building_types"] == ["maison"]


def test_collective_extension_matches_both_extension_and_existing():
    result = observed_categories({"NATURE_PROJET_DECLAREE": 2, "I_EXTENSION": True, "TYPE_PRINCIP_LOGTS_CREES": 3}, "logements")
    assert result["work_types"] == ["extension", "renovation"]
    assert result["building_types"] == ["collectif"]


def test_mixed_buildings_keep_both_observed_types():
    assert observed_categories({"NB_LGT_IND_CREES": 2, "NB_LGT_COL_CREES": 8}, "logements")["building_types"] == ["collectif", "maison"]


def test_missing_counts_not_guessed_from_one_total_dwelling():
    assert observed_categories({"NB_LGT_TOT_CREES": 1}, "logements")["building_types"] == ["inconnu"]
    assert observed_categories({}, "locaux")["building_types"] == ["autre"]


@pytest.mark.parametrize("name", ["Jean Dupont", "SCI PROMOTION", "BANQUE ARCHITECTES", "SYNDIC RESIDENCE"])
def test_names_never_determine_person_or_specialist(name):
    result = classification({"mo": "PARTICULIER", "promoteur": {"nom": name}, "logements": 1})
    assert result["client_type"] == "inconnu"
    assert result["building_types"] == ["inconnu"]


def test_legal_form_is_not_activity_or_private_person():
    assert classification({"promoteur": {"categorie_juridique": "6540"}})["client_type"] == "entreprise"
    assert classification({"filter_evidence": {"CJ_DEM": "5710", "APE_DEM": "71.11Z"}})["client_type"] == "entreprise"
    assert classification({"filter_evidence": {"CJ_DEM": "1000"}})["client_type"] == "inconnu"


def test_empty_selection_all_and_unknown_value_rejected():
    assert query_filters({}, work_types="", building_types="", client_types="") == RadarFilters().model_dump()
    assert query_filters({}, work_types="neuf,neuf, extension")["work_types"] == ["extension", "neuf"]
    with pytest.raises(HTTPException) as exc:
        query_filters({}, client_types="guessed_bank")
    assert exc.value.status_code == 422


def test_facets_or_within_groups_and_across_groups():
    rows = [
        {"id": "house", "classification": {"work_types": ["neuf"], "building_types": ["maison"], "client_type": "particulier"}},
        {"id": "extension", "classification": {"work_types": ["extension", "renovation"], "building_types": ["maison"], "client_type": "entreprise"}},
        {"id": "bank", "classification": {"work_types": ["neuf"], "building_types": ["collectif"], "client_type": "banque"}},
    ]
    selected = {"work_types": ["neuf", "extension"], "building_types": ["maison"], "client_types": []}
    found, facets = apply_filters(rows, selected)
    assert {item["id"] for item in found} == {"house", "extension"}
    assert next(option for option in facets["client_types"] if option["value"] == "banque")["count"] == 0
    assert len(facets["client_types"]) == len(OPTIONS["client_types"])
    selected["client_types"] = ["particulier"]
    assert [item["id"] for item in apply_filters(rows, selected)[0]] == ["house"]
    selected["building_types"] = ["collectif"]
    assert apply_filters(rows, selected)[0] == []


def test_mojibake_repair_retains_source_and_does_not_change_valid_text():
    raw = "RUE DE LA LIBERTÉ".encode().decode("latin1")
    row, changes = repair_source_row({"ADR_LIBVOIE_TER": raw, "DENOM_DEM": "SCI ÉTÉ"})
    assert row["ADR_LIBVOIE_TER"] == "RUE DE LA LIBERTÉ"
    assert changes["ADR_LIBVOIE_TER"]["raw"] == raw
    assert row["DENOM_DEM"] == "SCI ÉTÉ"
    permit = {"adresse": raw, "commune": "Créteil"}
    repair_cached_address(permit)
    assert permit["adresse"] == "RUE DE LA LIBERTÉ"
    assert permit["commune"] == "Créteil"
    assert "commune" not in permit["source_text_corrections"]