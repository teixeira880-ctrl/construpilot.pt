"""Dossier regressions: real calculation/routes with isolated, owner-aware data."""
import copy
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_platform_supervisor import Database, USER, plan, quote
from engines import chantier_costs as C, platform_supervisor as S
from engines.chantier_workspace import build_workspace
from routes import chantiers as R, agents as A


@pytest.fixture
def db(monkeypatch):
    database = Database()
    for module in (C, R, A):
        monkeypatch.setattr(module, "db", database)
    database.users.rows = [copy.deepcopy(USER)]
    database.chantiers.rows = [{"chantier_id": "c1", "user_id": "owner", "name": "Maison"}]
    return database


def chantier(db):
    return db.chantiers.rows[0]


def purchase(oid="o1", **kw):
    return {"order_id": oid, "user_id": "owner", "chantier_id": "c1", "status": "confirmé",
            "items": [{"qty": 4, "unit_price": 5, "line_total": 20}], **kw}


def q(qid="q1", **kw):
    return {**quote(qid), "chantier_id": "c1", "lines": [{"designation": "Mur", "qty": 10, "unit_price_ht": 20,
            "discount_pct": 10, "cost_price_ht": 8, "category": "Murs"}], **kw}


@pytest.mark.asyncio
async def test_discount_sections_and_known_zero_cost(db):
    db.pro_documents.rows = [q()]
    db.pro_documents.rows[0]["lines"].extend([
        {"kind": "section", "designation": "Titre", "qty": 900, "unit_price_ht": 100},
        {"designation": "Offert", "qty": 1, "unit_price_ht": 0, "cost_price_ht": 0, "cost_confirmed_zero": True}])
    out = await C.compute_chantier_costs(chantier(db), "owner")
    assert out["totals"]["vente_ht"] == 180
    assert out["totals"]["cost_prev_ht"] == 80
    assert out["totals"]["margin_ht"] == 100
    assert out["totals"]["coverage"]["total"] == 2


@pytest.mark.asyncio
async def test_quote_variants_never_sum_without_selection(db):
    db.pro_documents.rows = [q("q1"), q("q2")]
    out = await C.compute_chantier_costs(chantier(db), "owner")
    assert out["scope"]["selection_required"] and out["totals"]["vente_ht"] is None
    out = await R.save_cost_settings("c1", R.CostSettingsIn(quote_ids=["q2"], remaining_cost_ht=0), USER)
    assert out["totals"]["vente_ht"] == 180
    assert out["forecast"]["final_cost_ht"] == 0
    assert out["cost_version"] == 1
    with pytest.raises(HTTPException) as exc:
        await R.save_cost_settings("c1", R.CostSettingsIn(expected_version=0, quote_ids=["q1"]), USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_quote_selection_requires_owned_same_dossier(db):
    db.pro_documents.rows = [q("elsewhere", chantier_id="other"), q("foreign", user_id="other")]
    for ids in (["elsewhere"], ["foreign"], ["missing"], ["foreign", "foreign"]):
        with pytest.raises(HTTPException):
            await R.save_cost_settings("c1", R.CostSettingsIn(quote_ids=ids), USER)
    assert "cost_settings" not in chantier(db)


@pytest.mark.asyncio
async def test_labor_tenant_boundary_and_explicit_other_dossier(db):
    db.hr_timesheets.rows = [
        {"entry_id": "own", "employer_id": "owner", "project_id": "c1", "hours": 4, "status": "validated"},
        {"entry_id": "foreign", "employer_id": "other", "project_name": "Maison", "hours": 900, "status": "validated"},
        {"entry_id": "otherproject", "employer_id": "owner", "project_id": "c2", "project_name": "Maison", "hours": 800, "status": "validated"},
        {"entry_id": "legacy", "employer_id": "owner", "project_name": "Maison", "hours": 1, "status": "validated"}]
    out = await C.compute_chantier_costs(chantier(db), "owner", 20)
    assert out["labor"]["hours_validated"] == 5 and out["labor"]["cost_est"] == 100
    for eid in ("foreign", "otherproject"):
        with pytest.raises(HTTPException) as exc:
            await R.assign_labor_lot("c1", eid, R.LotAssignIn(lot="Murs"), USER)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_orders_line_totals_zero_prices_and_drafts(db):
    db.material_orders.rows = [purchase(), purchase("free", items=[{"unit_price": 0, "qty": 3}]),
                              purchase("draft", status="brouillon"), purchase("cancel", status="cancelled"),
                              purchase("other", chantier_id="other", project="Maison"), purchase("foreign", user_id="other")]
    out = await C.compute_chantier_costs(chantier(db), "owner")
    assert out["purchases"]["priced_total"] == 20
    assert out["purchases"]["orders"] == 2 and out["purchases"]["all_orders"] == 4
    assert out["purchases"]["unpriced_items"] == 0
    assert next(e for e in out["purchase_entries"] if e["order_id"] == "free")["amount"] == 0
    with pytest.raises(HTTPException):
        await R.assign_purchase_lot("c1", "other", R.LotAssignIn(lot="Murs"), USER)


@pytest.mark.asyncio
async def test_forecast_missing_inputs_stays_unknown(db):
    db.pro_documents.rows = [q()]
    db.material_orders.rows = [purchase(items=[{"qty": 8}])]
    chantier(db)["cost_settings"] = {"remaining_cost_ht": 20, "labor_rate": 30}
    out = await C.compute_chantier_costs(chantier(db), "owner")
    assert not out["forecast"]["complete"] and out["forecast"]["margin_ht"] is None
    db.material_orders.rows[0]["items"][0]["unit_price"] = 2
    out = await C.compute_chantier_costs(chantier(db), "owner")
    assert out["forecast"]["final_cost_ht"] == 36 and out["forecast"]["margin_ht"] == 144
    db.hr_timesheets.rows = [{"employer_id": "owner", "project_id": "c1", "hours": 2, "status": "pending"}]
    assert not (await C.compute_chantier_costs(chantier(db), "owner"))["forecast"]["complete"]


@pytest.mark.asyncio
async def test_delivery_version_validation_and_isolation(db):
    db.material_orders.rows = [purchase(), purchase("foreign", user_id="other"), purchase("draft", status="brouillon")]
    body = R.DeliveryIn(status="partial", expected_date="2026-10-15", notes="2 palettes reçues")
    await R.save_delivery("c1", "o1", body, USER)
    assert db.material_orders.rows[0]["delivery"]["status"] == "partial"
    for oid in ("o1", "foreign", "draft"):
        with pytest.raises(HTTPException):
            await R.save_delivery("c1", oid, body, USER)
    with pytest.raises(HTTPException) as exc:
        await R.save_delivery("c1", "o1", R.DeliveryIn(expected_version=1, expected_date="2026-02-31"), USER)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_pilot_scopes_repairs_and_detects_changed_source(db):
    db.plans_takeoff.rows = [{**plan(), "chantier_id": "c1"}, {**plan("p2"), "chantier_id": "c2"}, plan("foreign", "other")]
    run = {"run_id": "r1", "chantier_id": "c1"}
    out = await S.run_supervisor(db, USER, run, repair=True)
    assert out["checked"] == 1 and out["corrected"] == 1
    assert db.plans_takeoff.rows[1]["measurements"][0]["value_m"] == 99
    workspace = await build_workspace(db, chantier(db), USER)
    assert workspace["summary"]["checked"] == 1
    db.plans_takeoff.rows[0]["calibrations"]["1"]["pixels_per_meter"] = 25
    assert (await build_workspace(db, chantier(db), USER))["summary"]["stale"] == 1
    with pytest.raises(HTTPException):
        await S.run_supervisor(db, USER, {**run, "plan_ids": ["p2"]}, repair=True)
    with pytest.raises(HTTPException):
        await S.run_supervisor(db, USER, {**run, "chantier_id": "foreign"}, repair=True)


@pytest.mark.asyncio
async def test_settings_compare_and_swap(db):
    db.chantiers.before_update = lambda rows: rows[0].update(cost_version=1, cost_settings={"labor_rate": 80})
    with pytest.raises(HTTPException) as exc:
        await R.save_cost_settings("c1", R.CostSettingsIn(labor_rate=20), USER)
    assert exc.value.status_code == 409
    assert chantier(db)["cost_settings"]["labor_rate"] == 80


@pytest.mark.parametrize("value", [float("inf"), float("nan"), -1])
def test_invalid_forecast_inputs(value):
    with pytest.raises(ValidationError):
        R.CostSettingsIn(labor_rate=value)


@pytest.mark.parametrize("item,expected", [({"line_total": 15, "qty": 100}, 15), ({"line_total": 0, "unit_price": 20}, 0),
    ({"unit_price": 3, "commandable_qty": 2, "qty": 80}, 6), ({"unit_price": -2, "qty": 4}, None),
    ({"line_total": "NaN"}, None), ({"qty": 0, "unit_price": 5}, 0)])
def test_purchase_prices(item, expected):
    assert C.item_amount(item) == expected


@pytest.mark.asyncio
async def test_revision_routes_use_owned_discounted_reference_and_negative_draft(db, monkeypatch):
    from btp_ai import routes as B
    from routes import documents as D
    monkeypatch.setattr(B, "db", db)
    db.plans_takeoff.rows = [{**plan(), "chantier_id": "c1"}]
    db.btp_quantities.rows = [{"plan_id": "p1", "user_id": "owner", "dependent_documents": ["q1", "foreign"]}]
    db.pro_documents.rows = [q(), q("foreign", user_id="other")]
    for doc in db.pro_documents.rows:
        doc["lines"] = [{"description": "Métré q_wall · origine", "designation": "Mur", "unit": "m²", "qty": 11,
                         "unit_price_ht": 20, "discount_pct": 10}]
    before = {"quantity_id": "q_wall", "designation": "Mur", "lot": "Murs", "unit": "m2", "quantity_net": 10, "quantity_to_order": 11}
    db.btp_revisions.rows = [{"plan_id": "p1", "user_id": "owner", "revision": "a", "at": "2026-10-01", "count": 1, "lines": [before]},
                             {"plan_id": "p1", "user_id": "owner", "revision": "b", "at": "2026-10-02", "count": 0, "lines": []}]
    out = await B.revisions_diff("p1", "a", "b", USER)
    assert out["impact_total_ht"] == -198 and out["rows"][0]["delta_to_order"] == -11
    captured = []
    async def create(body, user):
        captured.append(body)
        return {"doc_id": "new"}
    monkeypatch.setattr(D, "create_document", create)
    await B.amendment_draft("p1", "a", "b", "", USER)
    assert captured[0].status == "draft" and captured[0].chantier_id == "c1"
    assert captured[0].lines[0].qty == -11 and captured[0].lines[0].unit_price_ht == 18
    assert db.pro_documents.rows[0]["lines"][0]["qty"] == 11
    db.pro_documents.rows.append({**copy.deepcopy(db.pro_documents.rows[0]), "doc_id": "q2"})
    db.btp_quantities.rows[0]["dependent_documents"].append("q2")
    assert (await B.revisions_diff("p1", "a", "b", USER))["rows"][0]["impact_ht"] is None


@pytest.mark.asyncio
async def test_agent_proposal_carries_and_rejects_wrong_project(db):
    db.plans_takeoff.rows = [{**plan(), "chantier_id": "c1"}, {**plan("p2"), "chantier_id": "c2"}]
    proposed = await A.propose_plan(A.PlanIn(agent="supervise", chantier_id="c1"), USER)
    assert proposed["run"]["chantier_id"] == "c1"
    with pytest.raises(HTTPException):
        await A.propose_plan(A.PlanIn(agent="supervise", chantier_id="c1", plan_ids=["p2"]), USER)
    with pytest.raises(HTTPException):
        await A.propose_plan(A.PlanIn(agent="supervise", chantier_id="absent"), USER)


@pytest.mark.asyncio
async def test_reassigned_dossier_during_correction_is_not_written(db):
    db.plans_takeoff.rows = [{**plan(), "chantier_id": "c1"}]
    db.plans_takeoff.before_update = lambda rows: rows[0].update(chantier_id="c2")
    out = await S.run_supervisor(db, USER, {"run_id": "r", "chantier_id": "c1"}, repair=True)
    assert out["corrected"] == 0 and out["needs_review"] == 1
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99


@pytest.mark.asyncio
async def test_linked_hr_project_and_merged_order_are_included(db):
    db.projects.rows = [{"project_id": "hr1", "user_id": "owner", "chantier_id": "c1"}]
    db.hr_timesheets.rows = [{"employer_id": "owner", "project_id": "hr1", "hours": 3, "status": "validated"}]
    db.plans_takeoff.rows = [{**plan(), "chantier_id": "c1"}]
    order = purchase(plan_ids=["elsewhere", "p1"])
    order.pop("chantier_id")
    db.material_orders.rows = [order]
    out = await C.compute_chantier_costs(chantier(db), "owner", 20)
    assert out["labor"]["hours_validated"] == 3
    assert out["purchases"]["priced_total"] == 0
    assert out["purchases"]["unpriced_items"] == 1
    assert out["purchase_entries"][0]["allocation_required"]
    db.material_orders.rows[0]["chantier_id"] = "c1"
    assert (await C.compute_chantier_costs(chantier(db), "owner", 20))["purchases"]["priced_total"] == 20


@pytest.mark.asyncio
async def test_placeholder_prices_are_not_free_materials_or_known_budget(db):
    db.pro_documents.rows = [q()]
    db.pro_documents.rows[0]["lines"][0].update(price_missing=True, unit_price_ht=0)
    assert (await C.compute_chantier_costs(chantier(db), "owner"))["totals"]["vente_ht"] is None
    assert C.item_amount({"line_total": 0, "unit_price": 0, "price_source": "—"}) is None
    assert C.item_amount({"unit_price": 2, "priced_qty": 5, "qty": 80}) == 10
