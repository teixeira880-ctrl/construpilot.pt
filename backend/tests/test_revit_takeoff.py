"""Medição Revit: modelos sintéticos Model Derivative (sem chamadas Autodesk). Código partilhado com o construpilot.fr."""
import io
from unittest.mock import AsyncMock, patch

import pytest
from openpyxl import load_workbook

from engines.revit_takeoff import category_info, index_tree, parse_quantity, takeoff
from plans_pro.revit_workbook import revit_workbook


def _tree(categories):
    """categories: {cat: {family: {type: [(objectid, name, [children])]}}} → arbre MD Revit."""
    oid = [1000]

    def nid():
        oid[0] += 1
        return oid[0]

    cats = []
    for cat, fams in categories.items():
        fam_nodes = []
        for fam, types in fams.items():
            type_nodes = []
            for typ, insts in types.items():
                type_nodes.append({"objectid": typ[0], "name": typ[1],
                                   "objects": [{"objectid": i[0], "name": i[1], "objects": i[2] if len(i) > 2 else []} for i in insts]})
            fam_nodes.append({"objectid": nid(), "name": fam, "objects": type_nodes})
        cats.append({"objectid": nid(), "name": cat, "objects": fam_nodes})
    return {"data": {"type": "objects", "objects": [{"objectid": 1, "name": "Model", "objects": cats}]}}


FR_TREE = _tree({
    "Murs": {"Mur de base": {(10, "Béton 20 cm"): [(11, "Mur de base [200001]"), (12, "Mur de base [200002]")],
                             (20, "Parpaing 20 cm"): [(21, "Mur de base [200003]")]}},
    "Sols": {"Sol": {(30, "Dalle BA 20 cm"): [(31, "Sol [300001]")]}},
    "Portes": {"Porte simple": {(40, "90 x 210"): [(41, "Porte simple [400001]"), (42, "Porte simple [400002]")]}},
    "Murs-rideaux": {},
    "Niveaux": {"Niveau": {(50, "Tête"): [(51, "Niveau [1]")]}},
    "Escaliers": {"Escalier assemblé": {(60, "Béton"): [(61, "Escalier [600001]", [{"objectid": 62, "name": "Limon [600002]"}])]}},
})
FR_PROPS = [
    {"objectid": 11, "name": "Mur de base [200001]", "externalId": "a-1", "properties": {
        "Contraintes": {"Contrainte inférieure": "RDC", "Hauteur non connectée": "2,700 m"},
        "Cotes": {"Longueur": "10,000 m", "Surface": "25,500 m²", "Volume": "5,100 m³"},
        "Phase": {"Phase de création": "Nouvelle construction", "Phase de démolition": "Aucun"}}},
    {"objectid": 12, "name": "Mur de base [200002]", "properties": {
        "Contraintes": {"Contrainte inférieure": "R+1"}, "Cotes": {"Longueur": "4,000 m", "Surface": "10,800 m²", "Volume": "2,160 m³"}}},
    {"objectid": 21, "name": "Mur de base [200003]", "properties": {
        "Contraintes": {"Contrainte inférieure": "RDC"}, "Cotes": {"Longueur": "5,000 m", "Surface": "13,500 m²", "Volume": "2,700 m³"},
        "Phase": {"Phase de démolition": "Existant"}}},
    {"objectid": 10, "name": "Béton 20 cm", "properties": {"Construction": {"Largeur": "200 mm"}, "Matériaux": {"Matériau structurel": "Béton C25/30"}}},
    {"objectid": 31, "name": "Sol [300001]", "properties": {"Contraintes": {"Niveau": "RDC"}, "Cotes": {"Surface": "120,000 m²", "Volume": "24,000 m³"}}},
    {"objectid": 41, "name": "Porte simple [400001]", "properties": {"Contraintes": {"Niveau": "RDC"}}},
    {"objectid": 42, "name": "Porte simple [400002]", "properties": {"Contraintes": {"Niveau": "R+1"}}},
    {"objectid": 40, "name": "90 x 210", "properties": {"Cotes": {"Largeur": "900 mm", "Hauteur": "2 100 mm"}}},
    {"objectid": 61, "name": "Escalier [600001]", "properties": {"Contraintes": {"Niveau de base": "RDC"}}},
    {"objectid": 62, "name": "Limon [600002]", "properties": {"Cotes": {"Longueur": "4,000 m"}}},
]


def test_units_metric_imperial_and_locales():
    assert parse_quantity("25,500 m²", "area") == pytest.approx(25.5)
    assert parse_quantity("12.25 m^2", "area") == pytest.approx(12.25)
    assert parse_quantity("1 250,50 m²", "area") == pytest.approx(1250.5)
    assert parse_quantity("1,250.50 m^2", "area") == pytest.approx(1250.5)
    assert parse_quantity("200 mm", "length") == pytest.approx(0.2)
    assert parse_quantity("10' - 6\"", "length") == pytest.approx(3.2004)
    assert parse_quantity("10' - 6 1/2\"", "length") == pytest.approx(3.2131, abs=1e-4)
    assert parse_quantity("100 SF", "area") == pytest.approx(9.290304)
    assert parse_quantity("10.00 ft^3", "volume") == pytest.approx(0.28316846592)
    # Jamais d'unité devinée
    assert parse_quantity("12.5", "area") is None
    assert parse_quantity(12.5, "area") is None
    assert parse_quantity("12 m", "area") is None


def test_categories_localized_and_ignored():
    assert category_info("Walls") == ("Murs", "m2")
    assert category_info("Revit Walls") == ("Murs", "m2")
    assert category_info("Paredes") == ("Murs", "m2")
    assert category_info("Fenêtres") == ("Fenêtres", "u")
    assert category_info("Niveaux") is None
    assert category_info("Levels") is None
    assert category_info("Catégorie maison") == ("Catégorie maison", "u")


def test_tree_index_depths():
    idx = index_tree(FR_TREE)
    assert idx[11]["category"] == "Murs" and idx[11]["family"] == "Mur de base" and idx[11]["type"] == "Béton 20 cm"
    assert idx[11]["type_id"] == 10 and idx[11]["depth"] == 4
    assert idx[62]["depth"] == 5 and idx[62]["top_instance"] == 61


def test_french_model_takeoff():
    t = takeoff(FR_PROPS, FR_TREE, filename="maison.rvt")
    assert t["levels"] == ["RDC", "R+1"]
    rows = {(r["level"], r["ouvrage"], r["type"]): r for r in t["rows"]}
    beton_rdc = rows[("RDC", "Murs", "Béton 20 cm")]
    assert beton_rdc["unit"] == "m2" and beton_rdc["quantity"] == pytest.approx(25.5) and beton_rdc["volume_m3"] == pytest.approx(5.1)
    assert beton_rdc["materials"] == ["Béton C25/30"]  # matériau du type
    assert beton_rdc["revit_ids"] == ["200001"]
    # Mur démoli (phase « Existant ») : hors totaux, listé à part
    assert ("RDC", "Murs", "Parpaing 20 cm") not in rows
    assert [e["revit_id"] for e in t["demolished"]] == ["200003"]
    assert t["by_ouvrage"]["Murs"]["total_area_m2"] == pytest.approx(36.3)
    assert t["by_ouvrage"]["Murs"]["count"] == 2
    # Dalle, portes par niveau, largeur héritée du type
    assert rows[("RDC", "Dalles / planchers", "Dalle BA 20 cm")]["quantity"] == pytest.approx(120)
    assert rows[("RDC", "Portes", "90 x 210")]["quantity"] == 1 and rows[("R+1", "Portes", "90 x 210")]["quantity"] == 1
    door = next(e for e in t["elements"] if e["revit_id"] == "400001")
    assert door["width_m"] == pytest.approx(0.9) and door["height_m"] == pytest.approx(2.1)
    # Niveaux Revit ignorés ; limon d'escalier non recompté
    assert "Niveaux" not in t["by_ouvrage"]
    assert t["by_ouvrage"]["Escaliers"]["count"] == 1 and not t["by_ouvrage"]["Escaliers"]["total_length_m"]
    assert any("sous-composant" in w for w in t["warnings"])


def test_deterministic():
    assert takeoff(FR_PROPS, FR_TREE) == takeoff(list(reversed(FR_PROPS)), FR_TREE)


def test_imperial_english_model_and_unknown_unit():
    tree = _tree({"Walls": {"Basic Wall": {(10, "Generic - 8\""): [(11, "Basic Wall [1]"), (12, "Basic Wall [2]")]}},
                  "Railings": {"Railing": {(20, "Handrail"): [(21, "Railing [3]")]}}})
    props = [
        {"objectid": 11, "properties": {"Constraints": {"Base Constraint": "Level 1"}, "Dimensions": {"Area": "107.64 SF", "Length": "20' - 0\""}}},
        {"objectid": 12, "properties": {"Constraints": {"Base Constraint": "Level 1"}, "Dimensions": {"Area": "50"}}},
        {"objectid": 21, "properties": {"Constraints": {"Base Level": "Level 1"}, "Dimensions": {"Length": "32' - 9 3/4\""}}},
    ]
    t = takeoff(props, tree)
    wall = next(r for r in t["rows"] if r["ouvrage"] == "Murs")
    assert wall["quantity"] == pytest.approx(10.0, abs=0.01) and wall["count"] == 2
    assert wall["length_m"] == pytest.approx(6.096)
    rail = next(r for r in t["rows"] if r["ouvrage"] == "Garde-corps")
    assert rail["unit"] == "ml" and rail["quantity"] == pytest.approx(10.0013, abs=1e-3)
    assert any("unité n'est pas reconnue" in w for w in t["warnings"])
    assert next(e for e in t["elements"] if e["revit_id"] == "2")["unparsed"] == ["50"]


def test_missing_main_unit_falls_back_to_count():
    tree = _tree({"Toits": {"Toit de base": {(10, "Tuiles"): [(11, "Toit [9]")]}}})
    t = takeoff([{"objectid": 11, "properties": {"Contraintes": {"Niveau de base": "Toiture"}}}], tree)
    row = t["rows"][0]
    assert row["unit"] == "u" and row["quantity"] == 1 and "non fourni" in row["quantity_note"]


def test_workbook_sheets_and_formulas():
    t = takeoff(FR_PROPS, FR_TREE, filename="maison.rvt")
    wb = load_workbook(io.BytesIO(revit_workbook({"filename": "maison.rvt"}, t)))
    assert wb.sheetnames == ["Synthèse", "Métré par niveau", "Éléments (contrôle)", "Démolitions (hors totaux)"]
    wm = wb["Métré par niveau"]
    values = [[c.value for c in row] for row in wm.iter_rows()]
    assert any(v[1] == "Sous-total RDC" for v in values) and any(v[1] == "TOTAL HT" for v in values)
    line = next(v for v in values if v[3] == "Béton 20 cm")
    assert line[4] == "m²" and line[5] == pytest.approx(25.5) and str(line[12]).startswith("=IF(")
    ids = [row[1].value for row in wb["Éléments (contrôle)"].iter_rows(min_row=2)]
    assert "200001" in ids and "200003" not in ids


@pytest.mark.asyncio
async def test_extract_full_uses_complete_takeoff():
    from plans_pro import autodesk_pipeline
    t = takeoff(FR_PROPS, FR_TREE)
    raw = {"urn": "u", "status": "success", "views": [], "sample_objects": [], "revit_takeoff": t}
    with patch("engines.autodesk_md.extract", AsyncMock(return_value=raw)):
        out = await autodesk_pipeline.extract_full(b"x", "m.rvt", user_id="u1")
    assert out["quantities"] is t["by_ouvrage"]


@pytest.mark.asyncio
async def test_extract_full_dwg_unchanged():
    from plans_pro import autodesk_pipeline
    raw = {"urn": "u", "status": "success", "views": [{"layers": [["A-WALL", 12]], "categories": []}], "sample_objects": []}
    with patch("engines.autodesk_md.extract", AsyncMock(return_value=raw)):
        out = await autodesk_pipeline.extract_full(b"x", "m.dwg", user_id="u1")
    assert out["quantities"]["Paredes"]["count"] == 12 and out["quantities"]["Paredes"]["source"] == "layers"


@pytest.mark.asyncio
async def test_md_revit_takeoff_reads_3d_view_and_never_breaks():
    from engines import autodesk_md
    job = {"urn": "u", "job_id": "md_1", "filename": "maison.rvt"}
    views = [{"guid": "g2d", "name": "Plan RDC", "role": "2d"}, {"guid": "g3d", "name": "{3D}", "role": "3d"}]
    props, tree = AsyncMock(return_value=FR_PROPS), AsyncMock(return_value=FR_TREE)
    with patch.object(autodesk_md, "_properties", props), patch.object(autodesk_md, "_object_tree", tree):
        out = await autodesk_md._revit_takeoff(job, views)
    props.assert_awaited_once_with("u", "g3d")
    assert out["view"] == "{3D}" and out["by_ouvrage"]["Paredes"]["count"] == 2 and out["lang"] == "pt"
    with patch.object(autodesk_md, "_properties", AsyncMock(side_effect=RuntimeError("boom"))):
        assert await autodesk_md._revit_takeoff(job, views) is None


@pytest.mark.asyncio
async def test_md_cached_rvt_gets_takeoff_without_new_translation():
    from engines import autodesk_md
    cached = {"key": "k", "status": "success", "ext": "rvt", "urn": "u", "views": [{"guid": "g3d", "name": "{3D}", "role": "3d"}]}
    submit = AsyncMock()
    with patch.object(autodesk_md, "config", lambda n: "x"), \
         patch.object(autodesk_md, "_job", AsyncMock(return_value=(dict(cached), False))), \
         patch.object(autodesk_md, "_submit", submit), \
         patch.object(autodesk_md, "_update", AsyncMock(side_effect=lambda job, **v: job.update(v))), \
         patch.object(autodesk_md, "_properties", AsyncMock(return_value=FR_PROPS)), \
         patch.object(autodesk_md, "_object_tree", AsyncMock(return_value=FR_TREE)):
        out = await autodesk_md.extract(b"x", "maison.rvt", user_id="u1")
    submit.assert_not_awaited()
    assert out["cached"] is True and out["revit_takeoff"]["elements_count"] == 6


def test_portuguese_output():
    t = takeoff(FR_PROPS, FR_TREE, filename="moradia.rvt", lang="pt")
    assert "Paredes" in t["by_ouvrage"] and "Portas" in t["by_ouvrage"] and "Murs" not in t["by_ouvrage"]
    assert any("demolido" in w for w in t["warnings"]) and "Revit" in t["method"]
    wb = load_workbook(io.BytesIO(revit_workbook({"filename": "moradia.rvt"}, t)))
    assert wb.sheetnames == ["Síntese", "Medição por nível", "Elementos (controlo)", "Demolições (fora dos totais)"]
    values = [[c.value for c in row] for row in wb["Medição por nível"].iter_rows()]
    assert any(v[1] == "Subtotal RDC" for v in values) and any(v[1] == "TOTAL s/ IVA" for v in values)
    # mêmes chiffres qu'en français
    assert t["by_ouvrage"]["Paredes"]["total_area_m2"] == takeoff(FR_PROPS, FR_TREE)["by_ouvrage"]["Murs"]["total_area_m2"]
