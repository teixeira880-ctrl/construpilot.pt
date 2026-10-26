"""Moteur MEP (plans d'exécution électricité & plomberie) — tests déterministes, sans réseau ni LLM.

Cas d'exemple anonymisé (RDC + R+1, éch. 1/50), géométrie relevée sur des PDF
vectoriels (tests/fixtures/mep_moradia_exemplo.json).
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.mep import generate, recompute  # noqa: E402
from engines.mep import geometry as G  # noqa: E402
from engines.mep.adapter import AdapterError, from_takeoff  # noqa: E402
from engines.mep.equipment import FOOTPRINT  # noqa: E402
from engines.mep.rules import classify_room, rules_for, simultaneity  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "mep_moradia_exemplo.json")


def _house(country="fr"):
    with open(FIXTURE, encoding="utf-8") as f:
        d = json.load(f)
    d["country"] = country
    return d


_CACHE = {}


def _study(country="fr"):
    if country not in _CACHE:
        _CACHE[country] = generate(_house(country))
    return copy.deepcopy(_CACHE[country])


def _box_house():
    """Maison minimale : séjour, cuisine, chambre, salle de bains, WC — sans appareils sur le plan."""
    return {"country": "fr", "levels": [{"id": "RDC", "name": "RDC", "rooms": [
        {"id": "s", "name": "Séjour", "polygon": [[0, 0], [6, 0], [6, 5], [0, 5]]},
        {"id": "k", "name": "Cuisine", "polygon": [[6.2, 0], [9.5, 0], [9.5, 3.5], [6.2, 3.5]]},
        {"id": "c", "name": "Chambre 1", "polygon": [[0, 5.2], [3.5, 5.2], [3.5, 8.5], [0, 8.5]]},
        {"id": "b", "name": "Salle de bains", "polygon": [[3.7, 5.2], [6.2, 5.2], [6.2, 8.5], [3.7, 8.5]]},
        {"id": "w", "name": "WC", "polygon": [[6.4, 3.7], [7.4, 3.7], [7.4, 5.5], [6.4, 5.5]]},
        {"id": "e", "name": "Entrée", "polygon": [[7.6, 3.7], [9.5, 3.7], [9.5, 6.5], [7.6, 6.5]]}],
        "openings": [
            {"kind": "porte", "a": [8.0, 6.6], "b": [8.9, 6.6]},
            {"kind": "passage", "a": [6.1, 1.0], "b": [6.1, 3.0]},
            {"kind": "porte", "a": [1.0, 5.1], "b": [1.8, 5.1]},
            {"kind": "porte", "a": [4.5, 5.1], "b": [5.3, 5.1]},
            {"kind": "porte", "a": [7.5, 4.0], "b": [7.5, 4.8]},
            {"kind": "passage", "a": [8.0, 3.6], "b": [9.0, 3.6]},
            {"kind": "fenetre", "a": [2.0, -0.1], "b": [4.0, -0.1]}]}],
        "options": {"water_heater": "ballon_electrique"}}


# --------------------------------------------------------------------------------- règles
def test_room_classifier_fr_and_pt():
    assert classify_room("SaM & Salon") == "sejour"
    assert classify_room("Célier") == "cellier"
    assert classify_room("Salle d'Eau") == "salle_d_eau"
    assert classify_room("Circu") == "circulation"
    assert classify_room("WC") == "wc"
    assert classify_room("Cozinha") == "cuisine"
    assert classify_room("Quarto 2") == "chambre"
    assert classify_room("Casa de banho") == "salle_d_eau"
    assert classify_room("Sala de estar") == "sejour"


def test_simultaneity_dtu():
    assert simultaneity(1) == 1.0
    assert abs(simultaneity(5) - 0.4) < 1e-9          # 0,8 / √4
    assert simultaneity(1000) == 0.2                  # borne basse


def test_fr_minimum_sockets():
    s = rules_for("fr")["elec"]["sockets"]
    assert s("sejour", 20) == 5 and s("sejour", 36.6) == 10 and s("sejour", 30) == 8
    assert s("chambre", 9) == 3 and s("circulation", 3) == 0 and s("circulation", 5) == 1


# --------------------------------------------------------------------------------- étude réelle
def test_exemple_house_has_no_blocking_error():
    st = _study()
    assert st["summary"]["errors"] == 0, [c["message"] for c in st["checks"] if c["status"] == "error"]
    assert len(st["levels"]) == 2 and st["norms"].startswith("NF C 15-100")
    assert "professionnel qualifié" in st["disclaimer"]


def test_exemple_room_equipment():
    st = _study()
    pts = st["points"]
    cnt = lambda room, kind: sum(1 for p in pts if p["room_id"] == room and p["kind"] == kind)  # noqa: E731
    assert cnt("sejour", "prise") >= 10                      # 36,6 m² → 1 socle / 4 m²
    assert cnt("cuisine", "prise_plan_travail") == 4
    assert cnt("cuisine", "prise") >= 2
    for room in ("chambre_rdc", "bureau", "ch1", "ch2", "ch3"):
        assert cnt(room, "prise") >= 3 and cnt(room, "rj45") >= 1
    assert cnt("sejour", "rj45") >= 2
    for lv in st["levels"]:
        for r in lv["rooms"]:
            if r["type"] not in ("escalier", "exterieur"):
                assert cnt(r["id"], "point_lumineux") >= 1, r["name"]
    assert sum(1 for p in pts if p["kind"] == "tableau" and p["room_id"] == "entree") == 1
    assert {p["level_id"] for p in pts if p["kind"] == "daaf"} == {"RDC", "R1"}


def test_specialised_circuits_and_protections():
    st = _study()
    el = st["electrical"]
    uses = {c["use"] for c in el["circuits"] if c["kind"] == "specialise"}
    assert {"plaque", "four", "lave_vaisselle", "lave_linge", "chauffe_eau", "vmc"} <= uses
    plaque = next(c for c in el["circuits"] if c["use"] == "plaque")
    assert plaque["section_mm2"] == 6.0 and plaque["breaker_a"] == 32
    for c in el["circuits"]:
        if c["kind"] == "eclairage":
            assert len(c["points"]) <= 8 and c["section_mm2"] == 1.5
        if c["kind"] == "prises":
            assert len(c["points"]) <= 8 and c["section_mm2"] == 2.5
        if c["kind"] == "prises_cuisine":
            assert len(c["points"]) <= 6
        assert c["rcd_id"] and c["length_m"] > 0
    assert len(el["rcds"]) == 4                              # > 100 m² habitables
    assert all(len(r["circuits"]) <= 8 and r["sensitivity_ma"] == 30 for r in el["rcds"])
    # éclairages répartis sur plusieurs DDR (continuité de service)
    light_rcds = {c["rcd_id"] for c in el["circuits"] if c["kind"] == "eclairage"}
    assert len(light_rcds) >= 2
    pnl = el["panel"]
    assert pnl["modules_reserve"] >= 0.2 * pnl["modules_used"] and pnl["contactor_hc"]


def test_bathroom_sockets_out_of_volume_2():
    st = _study()
    wet = [f for f in st["equipment"] if f["kind"] in ("douche", "baignoire")]
    for p in st["points"]:
        if p["kind"] == "prise" and p["room_id"] in ("sde_rdc", "sde_r1"):
            fps = [G.rect_footprint((f["x"], f["y"]), *FOOTPRINT[f["kind"]]) for f in wet if f["room_id"] == p["room_id"]]
            assert min(G.dist_point_to_rect((p["x"], p["y"]), fp) for fp in fps) >= 0.6


def test_plumbing_network():
    st = _study()
    pl = st["plumbing"]
    assert all(s["velocity_ms"] <= 2.0 for s in pl["supplies"] + pl["risers"])
    assert pl["main"]["velocity_ms"] <= 2.0
    wc = next(d for d in pl["drains"] if d["fixture"] == "wc")
    assert wc["diameter_mm"] == 100 and wc["net"] == "EV"
    assert len(pl["stacks"]) == 1 and pl["stacks"][0]["level_id"] == "R1"
    assert pl["collector"]["diameter_mm"] >= 100 and pl["exit"]
    hot = {s["fixture"] for s in pl["supplies"] if s["net"] == "ECS"}
    assert "wc" not in hot and {"evier", "lavabo", "douche"} <= hot
    assert {m["level_id"] for m in pl["manifolds"]} == {"RDC", "R1"}
    assert all(d["drop_m"] <= d["available_m"] for d in pl["drains"])
    # lave-linge et chauffe-eau implantés automatiquement dans le cellier
    auto = {f["kind"]: f["room_id"] for f in st["equipment"] if f["source"] == "auto"}
    assert auto.get("lave_linge") == "cellier" and auto.get("chauffe_eau") == "cellier"


def test_quantities_never_invent_prices():
    st = _study()
    codes = {q["code"].split("-")[0] + "-" + q["code"].split("-")[1] for q in st["quantities"]}
    assert {"EL-PRISE", "EL-DCL", "EL-CABLE", "EL-TABLEAU", "PL-TUBE", "PL-PVC", "PL-NOURRICE"} <= codes
    assert all("unit_price" not in q or q["unit_price"] is None for q in st["quantities"])


def test_price_only_from_company_library():
    try:
        from engines.mep.quantities import price
        import engines.price_library  # noqa: F401  (pymupdf / openpyxl requis)
    except ImportError:
        return
    st = _study()
    lib = [{"designation": "Socle de prise de courant 2P+T 16 A encastré", "unit": "u", "unit_price": 18.5}]
    res = price(st["quantities"], lib)
    line = next(q for q in st["quantities"] if q["code"] == "EL-PRISE")
    assert line["unit_price"] == 18.5 and res["priced_lines"] >= 1
    assert res["unpriced_lines"] > 0          # le reste reste « à chiffrer »


# --------------------------------------------------------------------------------- édition
def test_user_edit_is_rechecked():
    st = _study()
    pts = [p for p in st["points"] if not (p["room_id"] == "ch2" and p["kind"] == "prise")]
    st2 = recompute(st, {"points": pts})
    errs = [c for c in st2["checks"] if c["status"] == "error"]
    assert any("Chambre" in c["message"] and "0 socle" in c["message"] for c in errs)


def test_socket_moved_into_shower_zone_is_flagged():
    st = _study()
    shower = next(f for f in st["equipment"] if f["kind"] == "douche" and f["room_id"] == "sde_rdc")
    pts = copy.deepcopy(st["points"])
    sock = next(p for p in pts if p["room_id"] == "sde_rdc" and p["kind"] == "prise")
    sock["x"], sock["y"], sock["source"] = shower["x"] + 0.5, shower["y"], "user"
    st2 = recompute(st, {"points": pts})
    assert any(c["status"] == "error" and "volume 2" in c["message"] for c in st2["checks"])


# --------------------------------------------------------------------------------- génériques
def test_auto_equipment_on_plan_without_fixtures():
    st = generate(_box_house())
    kinds = {f["kind"] for f in st["equipment"]}
    assert {"evier", "plaque", "wc", "lavabo", "baignoire", "lave_linge", "chauffe_eau"} <= kinds
    assert all(f["source"] == "auto" for f in st["equipment"])
    assert any(c["status"] == "warning" and "automatiquement" in c["message"] for c in st["checks"])
    assert st["summary"]["errors"] == 0, [c["message"] for c in st["checks"] if c["status"] == "error"]


def test_portugal_mode():
    st = _study("pt")
    assert st["lang"] == "pt" and st["norms"].startswith("RTIEBT")
    assert "técnico qualificado" in st["disclaimer"]
    assert any(c["status"] == "info" and "RTIEBT" in c["message"] for c in st["checks"])
    lt = next(c for c in st["electrical"]["circuits"] if c["kind"] == "eclairage")
    assert lt["breaker_a"] == 10
    wc = next(d for d in st["plumbing"]["drains"] if d["fixture"] == "wc")
    assert wc["diameter_mm"] == 110
    assert any(q["designation"].startswith("Tomada") for q in st["quantities"])


def test_adapter_from_takeoff():
    plan = {"plan_id": "p1", "filename": "maison.pdf",
            "calibrations": {"0": {"pixels_per_meter": 100.0}},
            "rooms": [{"room_id": "r1", "page_index": 0, "name": "Séjour",
                       "points": [[0, 0], [500, 0], [500, 400], [0, 400]]}],
            "structure": {"0": {"openings": [{"kind": "porte", "x1": 100, "y1": 400, "x2": 190, "y2": 400}]}}}
    d = from_takeoff(plan)
    assert d["levels"][0]["rooms"][0]["polygon"][2] == [5.0, 4.0]
    assert d["levels"][0]["openings"][0]["b"] == [1.9, 4.0]
    st = generate(d)
    assert st["summary"]["points"] > 0
    plan["calibrations"] = {}
    try:
        from_takeoff(plan)
        assert False, "échelle manquante non détectée"
    except AdapterError as exc:
        assert "Échelle manquante" in str(exc)


def test_renders_svg_and_pdf():
    from engines.mep import render as R
    from engines.mep.pdf import build_pdf
    st = _study()
    svg = R.elec_scene(st, "RDC").to_svg()
    assert svg.startswith("<svg") and R.PHASE in svg
    svg = R.plumb_scene(st, "RDC", rules_for("fr")).to_svg()
    assert R.EF in svg and R.ECS in svg
    pdf = build_pdf(st)
    assert pdf[:4] == b"%PDF" and len(pdf) > 20_000


if __name__ == "__main__":       # exécution sans pytest : python tests/test_mep_engine.py
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print("FAIL", name, "→", repr(exc))
    sys.exit(1 if failed else 0)
