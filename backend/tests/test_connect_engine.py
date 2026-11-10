"""Discovery Engine — regras de recomendação, score, motores das demos, catálogo e paridade offline."""
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "construpilot_test")

import pytest

from engines import geometry as G
from engines.connect import business_time as BT, catalog as C, demo_compute as D, emails as E, recommend as R, scoring as S

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / "backend/engines/connect/cases.json").read_text(encoding="utf-8"))["cases"]


# ------------------------------------------------------------ catálogo

def test_catalog_valid_and_trilingual():
    cat = C.load()
    assert cat["version"]
    assert {c["status"] for c in cat["capabilities"]} <= set(cat["statuses"])


def test_frontend_catalog_and_cases_are_identical_copies():
    for name in ("catalog.json", "cases.json"):
        back = (ROOT / "backend/engines/connect" / name).read_bytes()
        front = (ROOT / "frontend/src/connect" / name).read_bytes()
        assert back == front, f"{name}: execute scripts/sync_connect_catalog.py"


def test_validation_rejects_unknown_capability():
    cat = copy.deepcopy(C.load())
    cat["pains"][0]["capabilities"].append("cap_inexistente")
    with pytest.raises(C.CatalogError):
        C.validate(cat)


def test_engine_demo_cannot_use_unverified_capability():
    cat = copy.deepcopy(C.load())
    cat["demos"][0]["capabilities"].append("cap_mep_plans")
    with pytest.raises(C.CatalogError):
        C.validate(cat)


def test_public_view_hides_internal_evidence():
    c = C.caps_by_id()["cap_takeoff"]
    assert "evidence" in c and "evidence" not in C.public_capability(c)


# ------------------------------------------------------------ recomendação

@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_recommendation_cases(case):
    r = R.recommend_client(case["answers"])
    e = case["expect"]
    assert r["primary_case"] == e["primary_case"]
    assert r["demo"] == e["demo"]
    assert r["track"] == e["track"]
    assert [c["id"] for c in r["capabilities"]] == e["capabilities"]
    assert r["process"]["current"] == e["process_current"]
    assert r["process"]["with"] == e["process_with"]
    assert r["value_defaults"]["quotes_per_month"] == e["quotes_per_month"]
    assert r["value_defaults"]["hours_per_quote"] == e["hours_per_quote"]
    if "needs_human_review" in e:
        assert r["needs_human_review"] is e["needs_human_review"]


def test_never_recommends_non_public_capabilities():
    for p in C.load()["pains"]:
        r = R.recommend_client({"activity": "construction_company", "pains": [p["id"]], "urgency": "d30"})
        assert all(C.caps_by_id()[c["id"]]["status"] in C.PUBLIC_STATUSES for c in r["capabilities"])
        assert r["demo"] in {d["id"] for d in C.load()["demos"]}


def test_painter_and_engineer_get_different_paths():
    painter = R.recommend_client({"activity": "painting", "pains": ["p_quote_slow"], "urgency": "d30"})
    engineer = R.recommend_client({"activity": "civil_engineer", "pains": ["p_quote_slow"], "urgency": "d30"})
    assert painter["demo"] == "demo_painting" and engineer["demo"] == "demo_quote"


def test_partner_and_investor_recommendations():
    assert R.recommend("partner", {"partner_type": "design_office"})["use_case"] == "cap_takeoff"
    assert R.recommend("investor", {})["demo"] == "demo_quote"


# ------------------------------------------------------------ score

def test_mission_example_is_high_priority_with_explanation():
    a = CASES[3]["answers"]
    s = S.score("client", a, group="builder", next_step="individual_demo")
    assert s["priority"] == "high" and 75 <= s["score"] <= 100
    assert "é decisor" in s["explanation"] and "30 dias" in s["explanation"]


def test_explorer_homeowner_is_low_and_still_kept():
    s = S.score("client", CASES[4]["answers"], group="private", next_step="none")
    assert s["priority"] == "low" and s["score"] >= 0


def test_score_components_are_bounded():
    a = {"pains": ["p_measure", "p_margins", "p_billing"], "volume": {"quotes_per_month": "q40p"},
         "urgency": "immediate", "decision": "decide"}
    s = S.score("client", a, group="builder", next_step="pilot", demo_completed=True)
    assert s["components"] == {"fit": 25, "intensity": 25, "urgency": 20, "decision": 15, "interest": 15}
    assert s["score"] == 100


def test_score_ignores_country_and_language():
    a = dict(CASES[0]["answers"])
    base = S.score("client", a, group="trade")["score"]
    a2 = {**a, "extra": {"market": "m_other"}, "country": "Ucrânia", "lang": "fr"}
    assert S.score("client", a2, group="trade")["score"] == base


def test_thresholds_are_configurable():
    a = CASES[1]["answers"]
    s1 = S.score("client", a, group="design")
    s2 = S.score("client", a, group="design", overrides={"thresholds": {"high": 30, "medium": 10}})
    assert s1["score"] == s2["score"] and s2["priority"] == "high"


def test_investor_and_partner_scores():
    inv = S.score("investor", {"investor_type": "vc", "sectors": ["contech"], "stages": ["seed"], "availability": "this_week",
                               "collab": "equity", "organization": "Fund", "website": "fund.vc"}, next_step="meeting")
    assert inv["priority"] == "high"
    par = S.score("partner", {"partner_type": "distributor", "kinds": ["distribution"], "scale": "s500p", "timeline": "now",
                              "organization": "Dist"}, next_step="meeting")
    assert par["priority"] == "high"


# ------------------------------------------------------------ motores reais das demos

def test_takeoff_demo_uses_real_geometry_engine():
    t = D.takeoff()
    assert t["calibration"] == G.compute_calibration((100, 520), (600, 520), 5.0)
    assert t["room"]["surface_m2"] == pytest.approx(15.96)
    assert t["room"]["perimeter_m"] == pytest.approx(16.0)
    assert t["walls"]["wall_area_net_m2"] == pytest.approx(41.6 - 1.89 - 2.88)
    assert t["calibration_check"]["ok"] is True
    assert t["quantities"]["paint"] == G.paint_liters(t["walls"]["wall_area_net_m2"] + 15.96)


def test_wrong_calibration_is_flagged():
    t = D.takeoff(5.4)
    assert t["calibration_check"]["ok"] is False
    assert t["room"]["surface_m2"] > 15.96  # escala errada → áreas erradas


@pytest.mark.parametrize("bad", [0, -1, 51, float("nan"), "abc"])
def test_demo_inputs_are_bounded(bad):
    with pytest.raises(D.DemoInputError):
        D.takeoff(bad)


def test_quote_line_totals_and_margin_vs_markup():
    q = D.quote()
    for l in q["lines"]:
        assert l["total_ht"] == round(l["qty"] * l["unit_price_ht"], 2)
    t = q["totals"]
    assert t["margin_pct"] == round((t["vente_ht"] - t["cost_prev_ht"]) / t["vente_ht"] * 100, 1)
    assert t["markup_pct"] == round((t["vente_ht"] - t["cost_prev_ht"]) / t["cost_prev_ht"] * 100, 1)
    assert t["markup_pct"] > t["margin_pct"]  # markup e margem são grandezas diferentes


def test_quote_discount_and_override():
    base = D.quote()["totals"]["vente_ht"]
    disc = D.quote({"parquet": {"discount_pct": 10}})
    line = next(l for l in disc["lines"] if l["key"] == "parquet")
    assert line["total_ht"] == round(line["qty"] * line["unit_price_ht"] * 0.9, 2)
    assert disc["totals"]["vente_ht"] < base
    with pytest.raises(D.DemoInputError):
        D.quote({"unknown": {}})


@pytest.mark.asyncio
async def test_margin_formula_parity_with_real_chantier_costs_engine(monkeypatch):
    """Executa o motor real engines/chantier_costs.compute_chantier_costs sobre o orçamento de exemplo."""
    from mongomock_motor import AsyncMongoMockClient
    from engines import chantier_costs as CC
    database = AsyncMongoMockClient().test
    monkeypatch.setattr(CC, "db", database)
    q = D.quote()
    await database.pro_documents.insert_one({
        "doc_id": "q1", "user_id": "u", "chantier_id": "c1", "doc_type": "quote", "status": "signed", "trashed_at": None,
        "lines": [{"kind": "line", "designation": l["key"], "category": l["lot"], "qty": l["qty"],
                   "unit_price_ht": l["unit_price_ht"], "discount_pct": 0, "cost_price_ht": l["cost_price_ht"]} for l in q["lines"]]})
    res = await CC.compute_chantier_costs({"chantier_id": "c1", "user_id": "u"}, "u")
    totals = res["totals"]
    assert totals["vente_ht"] == q["totals"]["vente_ht"] and totals["cost_prev_ht"] == q["totals"]["cost_prev_ht"]
    assert totals["margin_pct"] == q["totals"]["margin_pct"]
    assert totals["markup_pct"] == q["totals"]["markup_pct"]


# ------------------------------------------------------------ horas úteis e e-mails

def test_business_hours_skip_nights_and_weekends():
    fri_17 = datetime(2026, 11, 13, 17, 0, tzinfo=timezone.utc)  # Lisboa = UTC em novembro
    assert BT.add_business_hours(fri_17, 2) == datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)
    sat = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    assert BT.add_business_hours(sat, 2) == datetime(2026, 11, 16, 11, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("lang", ["pt", "en", "fr"])
def test_emails_escape_and_localise(lang):
    subject, html = E.render("request_received", lang, name="<script>x</script>", next_step="<b>",
                             cta_url="https://construpilot.pt/connect/demo/demo_quote")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert f'lang="{lang}"' in html and subject


def test_meeting_confirmation_requires_real_date_template_field():
    _, html = E.render("meeting_confirmation", "pt", name="Ana", when="12/11/2026 15:00")
    assert "12/11/2026 15:00" in html


def test_offline_snapshots_match_live_engine():
    snaps = json.loads((ROOT / "frontend/src/connect/demo_snapshots.json").read_text(encoding="utf-8"))
    for demo_id, snap in snaps.items():
        live = json.loads(json.dumps(D.compute(demo_id), sort_keys=True))
        assert snap == live, f"{demo_id}: execute scripts/sync_connect_catalog.py"
