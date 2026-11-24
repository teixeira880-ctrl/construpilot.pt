"""Motor do plano de estaleiro (PT): grua, alcance, carga na ponta da lança, implantação, normas portuguesas."""
import math

import pytest

from engines import pic

# Parcelle 60 × 40 m, bâtiment 20 × 12 m, image 600 × 400 px à 0,1 m/px
SITE = {"img_w": 600, "img_h": 400, "m_per_px": 0.1,
        "parcel": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "buildings": [[[0.5, 0.35], [0.8333333, 0.35], [0.8333333, 0.65], [0.5, 0.65]]],
        "accesses": [[0.0, 0.5]]}


def test_catalogue_is_consistent():
    for key, c in pic.CRANES.items():
        assert c["source"], key
        assert c["jib_max_m"] in [float(j) for j in c["tips"]] or c["jib_max_m"] in c["tips"], key
        for j, t in c["tips"].items():
            assert 0 < t <= c["cmax_t"] and j <= c["jib_max_m"], key
        for j, curve in (c.get("curves") or {}).items():
            loads = [l for _, l in sorted(curve)]
            assert loads == sorted(loads, reverse=True), key          # courbe décroissante
            assert sorted(curve)[-1] == (j, c["tips"][j]), key         # dernier point = bout de flèche
            assert sorted(curve)[0][1] == c["cmax_t"], key


def test_capacity_follows_published_curve_without_optimistic_interpolation():
    c = pic.CRANES["potain_mdt_178"]
    assert pic.capacity_at(c, 60, 60)["t"] == 1.5      # bout de flèche
    assert pic.capacity_at(c, 60, 10)["t"] == 8.0      # sous le rayon de charge max
    assert pic.capacity_at(c, 60, 40)["t"] == 2.55     # point tabulé
    assert pic.capacity_at(c, 60, 38)["t"] == 2.55     # entre 37 et 40 → valeur du rayon supérieur
    assert pic.capacity_at(c, 60, 61)["t"] == 0.0      # hors portée
    assert pic.capacity_at(c, 70, 30)["t"] == 0.0      # flèche inexistante


def test_tip_moment_bound_is_never_above_the_published_curve():
    for key in ("potain_mdt_178", "potain_mct_88"):
        c = pic.CRANES[key]
        j = c["jib_max_m"]
        bare = {**c, "curves": {}}
        for r, load in c["curves"][j]:
            assert pic.capacity_at(bare, j, r)["t"] <= load + 1e-9, (key, r)


def test_shorter_jib_uses_max_jib_curve_as_safe_value():
    c = pic.CRANES["potain_mdt_178"]
    res = pic.capacity_at(c, 40, 40)
    assert res["t"] == 2.55 and "prudent" in res["method"]
    c159 = pic.CRANES["potain_mdt_159"]
    assert pic.capacity_at(c159, 45, 45)["t"] == 3.3                      # pointe publiée à 45 m
    assert pic.capacity_at(c159, 45, 30)["t"] == pytest.approx(3.3 * 45 / 30)


def test_jib_selection():
    assert pic.jib_for(pic.CRANES["potain_mdt_178"], 41) == 45
    assert pic.jib_for(pic.CRANES["potain_igo_t99"], 32) == 33.8
    assert pic.jib_for(pic.CRANES["potain_igo_50"], 41) is None
    assert pic.jib_for(pic.CRANES["potain_igo_50"], 38) == 40


def test_design_load_concrete_bucket():
    d = pic.design_load({"benne_beton_m3": 1, "benne_tare_kg": 300, "accessoires_kg": 50})
    assert d["t"] == pytest.approx(2.5 + 0.3 + 0.05)
    assert pic.design_load({"benne_beton_m3": 1})["missing"]              # tare obligatoire
    assert pic.design_load({})["t"] is None
    assert pic.design_load({"charge_max_t": 3, "benne_beton_m3": 0.5, "benne_tare_kg": 200})["t"] == 3


def test_missing_inputs_are_reported_not_guessed():
    assert pic.compute({**SITE, "m_per_px": None})["missing"]
    assert pic.compute({**SITE, "parcel": []})["missing"]
    assert pic.compute({**SITE, "buildings": []})["missing"]
    r = pic.compute(SITE, {"grue": True})
    assert not r["ok"] and any("Carga" in m for m in r["missing"])


def test_full_plan_with_crane():
    r = pic.compute(SITE, {"grue": True, "charge_max_t": 2.0, "hauteur_batiment_m": 9,
                           "hauteur_charge_m": 4, "aire_livraison": True, "vehicule": "porteur",
                           "bennes": True, "nb_bennes": 2, "stockage": True, "stockage_m2": 40,
                           "base_vie": True, "effectif": 25, "nb_bungalows": 2})
    assert r["site"] == {"parcel_m2": 2400.0, "building_m2": 240.0, "free_m2": 2160.0,
                         "perimeter_ml": 200.0, "width_m": 60.0, "height_m": 40.0}
    assert r["cloture_ml"] == 200.0
    assert r["base_vie"]["wc"] == 1 and "46427" in r["base_vie"]["ref"]   # 25 trabalhadores → 1 retrete
    types = [e["type"] for e in r["elements"]]
    assert types.count("benne") == 2 and types.count("base_vie") == 2
    assert {"livraison", "stockage", "grue", "acces"} <= set(types)
    cr = r["crane"]
    # la portée annoncée est bien la distance au point le plus éloigné du bâtiment / des aires
    pts = [(30, 14), (50, 14), (50, 26), (30, 26)]
    assert cr["reach_building_m"] == pytest.approx(max(math.hypot(x - cr["x"], y - cr["y"]) for x, y in pts), abs=0.02)
    assert cr["reach_required_m"] >= cr["reach_building_m"]
    assert cr["jib_m"] >= cr["reach_required_m"]
    assert cr["capacity_at_reach_t"] >= 2.0 and cr["ok"] and r["ok"]
    assert cr["hsc_required_m"] == 15.0
    # plus petite grue suffisante : toutes celles classées avant sont refusées avec un motif
    alts = cr["alternatives"]
    idx = next(i for i, x in enumerate(alts) if x["key"] == cr["key"])
    assert all(not x["ok"] and x["reasons"] for x in alts[:idx])
    # aucun élément ne chevauche le bâtiment ni ne sort de la parcelle
    from shapely.geometry import box
    bat = box(30, 14, 50, 26)
    for e in r["elements"]:
        if e["type"] in ("acces", "grue"):
            continue
        rect = pic._rect(e["x"], e["y"], e["w"], e["h"], e["rot"])
        assert not rect.intersects(bat), e["label"]
        assert box(0, 0, 60, 40).buffer(0.01).contains(rect), e["label"]


def test_imposed_model_too_small_is_refused():
    r = pic.compute(SITE, {"grue": True, "grue_modele": "potain_igo_m14", "charge_max_t": 1.5,
                           "hauteur_batiment_m": 9, "hauteur_charge_m": 4})
    assert not r["crane"]["ok"] and not r["ok"]
    assert any(not c["ok"] for c in r["crane"]["checks"])


def test_custom_crane_from_rental_sheet():
    r = pic.compute(SITE, {"grue": True, "grue_modele": "autre", "grue_cmax_t": 6, "grue_jib_max_m": 45,
                           "grue_tip_t": 1.4, "fleche_m": 45, "charge_max_t": 1.4,
                           "hauteur_batiment_m": 9, "hauteur_charge_m": 4})
    cr = r["crane"]
    assert cr["tip_t"] == 1.4 and cr["ok"]
    assert cr["capacity_at_reach_t"] == pytest.approx(min(6, 1.4 * 45 / cr["reach_required_m"]), abs=0.01)
    r2 = pic.compute(SITE, {"grue": True, "grue_modele": "autre", "charge_max_t": 1})
    assert any("Ficha da grua" in m for m in r2["missing"])


def test_user_positions_are_kept_and_checked():
    placed = [{"id": "grue", "x": 10, "y": 20}, {"id": "benne_1", "x": 40, "y": 20, "w": 3.5, "h": 1.8, "rot": 0}]
    r = pic.compute(SITE, {"grue": True, "charge_max_t": 1, "hauteur_batiment_m": 9, "hauteur_charge_m": 4,
                           "bennes": True, "nb_bennes": 1}, placed=placed)
    assert (r["crane"]["x"], r["crane"]["y"]) == (10, 20)
    assert r["crane"]["reach_building_m"] == pytest.approx(math.hypot(40, 6), abs=0.01)
    assert any("sobrepõe-se ao edifício" in w for w in r["warnings"])


def test_jib_sweep_outside_site_is_flagged():
    r = pic.compute(SITE, {"grue": True, "charge_max_t": 1, "hauteur_batiment_m": 9, "hauteur_charge_m": 4})
    assert r["crane"]["survol_hors_emprise_m2"] > 0
    assert any("sobrevoa" in w for w in r["warnings"])


def test_no_crane_plan():
    r = pic.compute(SITE, {"grue": False, "bennes": True, "aire_livraison": True, "vehicule": "semi"})
    assert r["crane"] is None and r["ok"]
    liv = next(e for e in r["elements"] if e["type"] == "livraison")
    assert (liv["w"], liv["h"]) == (18.5, 4.55)


def test_questions_cover_the_requested_options():
    keys = {q["key"] for q in pic.questions({"levels": 3})}
    assert {"grue", "grue_modele", "fleche_m", "grue_tip_t", "bennes", "aire_livraison"} <= keys
    assert next(q for q in pic.questions({"levels": 3}) if q["key"] == "grue")["proposed"] is True
    assert next(q for q in pic.questions({}) if q["key"] == "grue")["proposed"] is None


def test_site_from_ai_reading_uses_the_written_dimension_only():
    d = {"reference": {"p1": [0.1, 0.5], "p2": [0.6, 0.5], "length_m": 30},
         "parcel": [[0, 0], [1, 0], [1, 1.2], [0, "a"]],
         "buildings": [{"polygon": [[.5, .35], [.8, .35], [.8, .65]], "levels": 3, "height_m": 9.5}, "bad"],
         "accesses": [{"point": [0, .5]}, None]}
    s = pic.site_from_analysis(d, 600, 400)
    assert s["m_per_px"] == pytest.approx(30 / 300)          # 0,5 × 600 px = 300 px pour 30 m
    assert s["parcel"] == [[0, 0], [1, 0], [1, 1.0]]         # point invalide écarté, borné à 0–1
    assert len(s["buildings"]) == 1 and s["accesses"] == [[0, .5]]
    assert pic.hints(d) == {"levels": 3, "building_height_m": 9.5}
    # pas de cote lisible → pas d'échelle inventée
    assert pic.site_from_analysis({"scale_detected": "1/200"}, 600, 400)["m_per_px"] is None


def test_texts_use_french_decimal_comma():
    r = pic.compute(SITE, {"grue": True, "benne_beton_m3": 1, "benne_tare_kg": 300,
                           "hauteur_batiment_m": 9, "hauteur_charge_m": 4, "aire_livraison": True})
    texts = r["warnings"] + r["hypotheses"] + [c["detail"] for c in r["crane"]["checks"]]
    import re
    assert texts and not any(re.search(r"\d\.\d", t) for t in texts)


# ---------------------------------------------------------------------------
# v2 : zone levable, liste de charges, deux grues, obstacles, matériel
# ---------------------------------------------------------------------------
BASE = {"grue": True, "hauteur_batiment_m": 9, "hauteur_charge_m": 4}


def test_max_radius_is_the_exact_limit_of_the_capacity_function():
    for key in ("potain_mdt_178", "potain_igo_50", "potain_mdt_159"):
        c = pic.CRANES[key]
        j = c["jib_max_m"]
        for load in (0.5, 1.2, 2.0, 3.7, c["cmax_t"]):
            r = pic.max_radius_for(c, j, load)
            assert pic.capacity_at(c, j, r)["t"] >= load - 1e-9 or r == 0
            if r < j:
                assert pic.capacity_at(c, j, round(r + 0.1, 1))["t"] < load
        assert pic.max_radius_for(c, j, c["cmax_t"] + 0.1) == 0.0
    assert pic.max_radius_for(pic.CRANES["potain_mdt_178"], 60, 1.5) == 60     # bout de flèche
    assert pic.max_radius_for(pic.CRANES["potain_mdt_178"], 60, 4.0) == 27.4   # point tabulé
    assert pic.max_radius_for(pic.CRANES["potain_igo_50"], 40, 2.2) == 20.0    # 1,1 × 40 / 2,2


def test_load_curve_is_decreasing_and_ends_at_the_tip():
    c = pic.CRANES["potain_mct_88"]
    curve = pic.load_curve(c, 52)
    loads = [p["t"] for p in curve]
    assert loads == sorted(loads, reverse=True)
    assert curve[-1] == {"r_m": 52.0, "t": 1.1} and curve[0]["t"] == 5.0


def test_load_list_and_per_load_coverage():
    ans = {**BASE, "grue_modele": "potain_igo_50", "fleche_m": 40, "accessoires_kg": 100,
           "charges": [{"label": "Palette de blocs", "t": 1.4}, {"label": "Banche", "t": 3.5},
                       {"label": "vide", "t": None}, "bad"]}
    r = pic.compute(SITE, ans)
    rows = {x["label"]: x for x in r["loads"]}
    assert set(rows) == {"Palette de blocs", "Banche"}
    assert rows["Palette de blocs"]["t"] == 1.5 and rows["Banche"]["t"] == 3.6
    assert r["crane"]["load"]["t"] == 3.6                                   # charge de calcul = la plus lourde
    # rayon levable = borne par le moment en pointe (1,1 t × 40 m)
    assert rows["Banche"]["radius_m"] == [pytest.approx(1.1 * 40 / 3.6, abs=0.1)]
    assert rows["Palette de blocs"]["radius_m"] == [pytest.approx(1.1 * 40 / 1.5, abs=0.1)]
    assert rows["Palette de blocs"]["coverage_pct"] > rows["Banche"]["coverage_pct"]
    assert not rows["Banche"]["ok"] and r["coverage"]["charge_pct"] == rows["Banche"]["coverage_pct"]
    assert r["coverage"]["portee_pct"] == 100.0
    assert any("só pode ser elevada em" in w for w in r["warnings"])
    assert r["crane"]["lift_radius_m"] == rows["Banche"]["radius_m"][0]


def test_coverage_is_the_real_area_share():
    from shapely.geometry import Point, box
    placed = [{"id": "grue", "x": 10, "y": 20}]
    r = pic.compute(SITE, {**BASE, "grue_modele": "potain_igo_50", "fleche_m": 30, "charge_max_t": 1.0}, placed=placed)
    bat = box(30, 14, 50, 26)
    expect = 100 * bat.intersection(Point(10, 20).buffer(30, 64)).area / bat.area
    assert r["coverage"]["portee_pct"] == pytest.approx(expect, abs=0.1)
    assert r["coverage"]["portee_pct"] < 100 and not r["crane"]["ok"]


BIG = {"img_w": 2000, "img_h": 800, "m_per_px": 0.1,                       # parcelle 200 × 80 m
       "parcel": [[0, 0], [1, 0], [1, 1], [0, 1]],
       "buildings": [[[0.1, 0.4], [0.9, 0.4], [0.9, 0.7], [0.1, 0.7]]],    # bâtiment 160 × 24 m
       "accesses": [[0.5, 0.0]]}


def test_two_cranes_split_a_long_building():
    one = pic.compute(BIG, {**BASE, "charge_max_t": 2.0})
    two = pic.compute(BIG, {**BASE, "charge_max_t": 2.0, "nb_grues": "2"})
    assert len(one["cranes"]) == 1 and len(two["cranes"]) == 2
    c1, c2 = two["cranes"]
    assert max(c1["reach_required_m"], c2["reach_required_m"]) < one["crane"]["reach_required_m"]
    assert c1["ok"] and c2["ok"] and two["coverage"]["portee_pct"] == 100.0 and two["coverage"]["charge_pct"] == 100.0
    assert {e["id"] for e in two["elements"] if e["type"] == "grue"} == {"grue", "grue_2"}
    inter = two["interference"]
    assert inter["distance_m"] == pytest.approx(math.hypot(c1["x"] - c2["x"], c1["y"] - c2["y"]), abs=0.01)
    assert inter["overlap"] == (inter["distance_m"] < c1["jib_m"] + c2["jib_m"])
    assert any("anticolisão" in x for x in two["checklist"])
    assert sum(1 for m in two["materiel"] if m["designation"].startswith("Grua-torre")) == 2


def test_two_cranes_too_close_are_refused():
    placed = [{"id": "grue", "x": 60, "y": 20}, {"id": "grue_2", "x": 80, "y": 20}]
    r = pic.compute(BIG, {**BASE, "charge_max_t": 1.0, "nb_grues": "2", "grue_modele": "potain_mdt_178",
                          "fleche_m": 60, "fleche2_m": 60}, placed=placed)
    assert r["interference"]["overlap"] and not r["interference"]["ok"] and not r["ok"]
    assert any("atinge a torre" in w for w in r["warnings"])
    far = [{"id": "grue", "x": 40, "y": 20}, {"id": "grue_2", "x": 160, "y": 20}]
    r2 = pic.compute(BIG, {**BASE, "charge_max_t": 1.0, "nb_grues": "2", "grue_modele": "potain_mdt_178",
                           "fleche_m": 60, "fleche2_m": 55}, placed=far)
    assert r2["interference"] == {**r2["interference"], "distance_m": 120.0, "overlap": False, "ok": True}
    assert [c["jib_m"] for c in r2["cranes"]] == [60, 55]


def test_second_crane_can_have_its_own_model():
    r = pic.compute(BIG, {**BASE, "charge_max_t": 1.0, "nb_grues": "2", "grue_modele": "potain_mdt_178",
                          "grue2_modele": "potain_mdt_159"})
    assert [c["key"] for c in r["cranes"]] == ["potain_mdt_178", "potain_mdt_159"]


def test_obstacles_read_on_the_plan_are_checked():
    d = {"parcel": SITE["parcel"], "buildings": [{"polygon": SITE["buildings"][0]}],
         "reference": {"p1": [0, 0.5], "p2": [1, 0.5], "length_m": 60},
         "obstacles": [{"type": "ligne_electrique", "label": "Ligne HTA", "bbox": [0.3, 0.02, 0.9, 0.05]},
                       {"type": "arbre", "label": "Chêne", "bbox": [0.02, 0.4, 0.12, 0.6]},
                       {"type": "inconnu", "bbox": [0.9, 0.9, 0.95, 0.95]}, {"bbox": [0.1, 0.1]}, "bad"]}
    site = pic.site_from_analysis(d, 600, 400)
    assert [o["type"] for o in site["obstacles"]] == ["ligne_electrique", "arbre", "autre"]
    r = pic.compute(site, {**BASE, "charge_max_t": 1.0, "bennes": True, "aire_livraison": True, "base_vie": True,
                           "effectif": 8})
    assert any("Ligne HTA" in w and "E-REDES" in w and "5 m" in w for w in r["warnings"])
    assert len(r["obstacles"]) == 3
    from shapely.geometry import box
    tree = box(1.2, 16, 7.2, 24)
    for e in r["elements"]:
        if e["type"] not in ("acces", "grue"):
            assert not pic._rect(e["x"], e["y"], e["w"], e["h"], e["rot"]).intersects(tree), e["label"]


def test_equipment_list_is_computed_from_the_plan():
    r = pic.compute(SITE, {"grue": False, "bennes": True, "nb_bennes": 2, "base_vie": True, "effectif": 25,
                           "nb_bungalows": 3, "stationnement": True, "nb_places": 4, "silo": True,
                           "branchements": True, "aire_livraison": True})
    m = {x["designation"]: x for x in r["materiel"]}
    assert m["Vedação do estaleiro — comprimento"]["quantite"] == 200.0
    assert m["Painéis de vedação móvel de 3,5 m"]["quantite"] == math.ceil((200 - 4) / 3.5) == 56
    assert m["Bases de vedação"]["quantite"] == 57
    assert m["Contentor 8 m³"]["quantite"] == 2 and m["Contentor social 6,06 × 2,44 m"]["quantite"] == 3
    assert m["Retretes"]["quantite"] == 1 and "Urinoirs" not in m       # só o mínimo verificado na lei
    assert m["Lugares de estacionamento"]["quantite"] == 4
    liv = next(x for x in r["materiel"] if x["designation"].startswith("Zona de cargas e descargas"))
    assert liv["quantite"] == pytest.approx(14 * 4.55, abs=0.05) and liv["unite"] == "m²"
    park = next(e for e in r["elements"] if e["id"] == "parking")
    assert (park["w"], park["h"]) == (10.0, 5.0)
    assert {"armoire", "point_eau", "silo"} <= {e["id"] for e in r["elements"]}
    assert pic.compute(SITE, {"grue": False, "cloture": False})["materiel"] == []


def test_questions_v2():
    qs = {q["key"]: q for q in pic.questions({})}
    assert {"nb_grues", "grue2_modele", "fleche2_m", "charges", "stationnement", "silo", "branchements"} <= set(qs)
    assert qs["charges"]["type"] == "loads"
    assert all(o["value"] not in ("auto", "autre") for o in qs["grue2_modele"]["options"][1:])


# ---------------------------------------------------------------------------
# v3 : vue aérienne géoréférencée
# ---------------------------------------------------------------------------
def test_meters_per_degree_matches_known_values():
    m_lat, m_lon = pic.meters_per_degree(0)
    assert m_lat == pytest.approx(110574, abs=5) and m_lon == pytest.approx(111320, abs=5)
    m_lat, m_lon = pic.meters_per_degree(45)
    assert m_lat == pytest.approx(111132, abs=5) and m_lon == pytest.approx(78847, abs=5)


def _square(lat, lon, side_m):
    m_lat, m_lon = pic.meters_per_degree(lat)
    dy, dx = side_m / 2 / m_lat, side_m / 2 / m_lon
    ring = [[lon - dx, lat - dy], [lon + dx, lat - dy], [lon + dx, lat + dy], [lon - dx, lat + dy], [lon - dx, lat - dy]]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


def test_aerial_frame_gives_an_exact_metric_scale():
    f = pic.aerial_frame(48.85, 2.35, 200, 1000)
    assert f["m_per_px"] == 0.2
    m_lat, m_lon = pic.meters_per_degree(48.85)
    assert (f["maxlat"] - f["minlat"]) * m_lat == pytest.approx(200, abs=1e-6)
    assert (f["maxlon"] - f["minlon"]) * m_lon == pytest.approx(200, abs=1e-6)
    assert pic.geo_to_norm(f, 2.35, 48.85) == [0.5, 0.5]
    assert pic.geo_to_norm(f, f["minlon"], f["maxlat"]) == [0.0, 0.0]      # nord-ouest = coin haut-gauche


def test_aerial_site_uses_the_cadastral_parcel_at_true_size():
    geom = _square(45.76, 4.83, 50)                                       # parcelle carrée de 50 m
    f = pic.aerial_frame_for(geom, 45.0, 4.0)                              # centre recalé sur la parcelle
    assert (f["lat"], f["lon"]) == (pytest.approx(45.76), pytest.approx(4.83))
    assert f["span_m"] == pytest.approx(110, abs=0.01)                     # 2,2 × l'étendue
    site = pic.aerial_site(f, geom)
    assert site["base"] == "aerial" and len(site["parcel"]) == 4 and site["buildings"] == []
    res = pic.compute({**site, "buildings": [[[0.45, 0.45], [0.55, 0.45], [0.55, 0.55], [0.45, 0.55]]]},
                      {"grue": False})
    assert res["site"]["parcel_m2"] == pytest.approx(2500, rel=0.002)      # 50 × 50 m retrouvés sur l'image
    assert res["site"]["building_m2"] == pytest.approx(121, rel=0.002)     # 10 % de 110 m = 11 m de côté
    # sans parcelle cadastrale : cadrage par défaut sur l'adresse, emprise à tracer
    f2 = pic.aerial_frame_for(None, 45.0, 4.0)
    assert f2["span_m"] == 160 and pic.aerial_site(f2, None)["parcel"] == []
    assert pic.aerial_frame_for(geom, 45, 4, span_m=5000)["span_m"] == 800  # borné
    assert pic._ring_points({"type": "Polygon", "coordinates": "bad"}) == []


# ---------------------------------------------------------------------------
# Versão portuguesa: normas e textos
# ---------------------------------------------------------------------------
def test_normas_portuguesas_e_textos_em_portugues():
    r = pic.compute(BIG, {**BASE, "charge_max_t": 2.0, "nb_grues": "2", "aire_livraison": True, "vehicule": "semi",
                          "bennes": True, "base_vie": True, "effectif": 60, "branchements": True})
    assert pic.sanitaires(60)["wc"] == 3 and pic.sanitaires(25)["wc"] == 1 and pic.sanitaires(26)["wc"] == 2
    assert set(pic.sanitaires(10)) == {"wc", "ref", "nota"}          # nada além do mínimo confirmado na lei
    texto = " ".join(r["checklist"] + r["hypotheses"] + r["warnings"] + [m["base"] for m in r["materiel"]])
    for ref in ("Decreto-Lei n.º 50/2005", "Decreto-Lei n.º 273/2003", "Decreto-Lei n.º 132/2017", "Decreto n.º 46427",
                "E-REDES", "ocupação da via pública"):
        assert ref in texto, ref
    for fr in ("Code du travail", "CACES", "DT-DICT", "arrêté", "voirie", "R4228", "R4534", "R312"):
        assert fr not in texto, fr
    import re
    frances = re.compile(r"\b(grue|flèche|portée|chantier|bâtiment|loueur|emprise|benne|clôture|avec|des|les|une)\b", re.I)
    todos = [texto] + [e["label"] for e in r["elements"]] + [m["designation"] for m in r["materiel"]] \
        + [c["label"] + " " + c["detail"] for cr in r["cranes"] for c in cr["checks"]] \
        + [q["label"] for q in pic.questions({})] + [o["label"] for q in pic.questions({}) for o in q.get("options", [])]
    assert not [t for t in todos if frances.search(t)]
    liv = next(e for e in r["elements"] if e["type"] == "livraison")
    assert (liv["w"], liv["h"]) == (18.5, 4.55)                     # veículo articulado 16,50 × 2,55 m + margem
