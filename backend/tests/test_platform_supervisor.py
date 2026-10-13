"""Real engines/routes; isolated database, no external model or production call."""
import asyncio
import copy
import math
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from engines import platform_supervisor as S
from engines.calculator_validation import run_validated
from engines.calculators import CALCULATORS
from routes import agents as A, documents as D


MISSING = object()


def lookup(row, path):
    try:
        for part in path.split("."):
            row = row[int(part)] if isinstance(row, list) else row[part]
        return row
    except (KeyError, IndexError, TypeError):
        return MISSING


def matches(row, query):
    for key, expected in query.items():
        if key == "$or":
            if not any(matches(row, child) for child in expected):
                return False
            continue
        actual = lookup(row, key)
        if isinstance(expected, dict) and any(k.startswith("$") for k in expected):
            for op, value in expected.items():
                if op == "$exists" and (actual is not MISSING) != value:
                    return False
                if op == "$in" and not (any(v in value for v in actual) if isinstance(actual, list) else (None if actual is MISSING else actual) in value):
                    return False
                if op == "$ne" and actual == value:
                    return False
                if op == "$lt" and (actual is MISSING or not actual < value):
                    return False
                if op == "$regex" and not re.search(value, str(actual), re.I):
                    return False
                assert op in ("$exists", "$in", "$ne", "$lt", "$regex", "$options")
        elif (None if actual is MISSING else actual) != expected:
            return False
    return True


def put(row, path, value, remove=False):
    parts = path.split(".")
    for part in parts[:-1]:
        row = row[int(part)] if isinstance(row, list) else row.setdefault(part, {})
    key = int(parts[-1]) if isinstance(row, list) else parts[-1]
    if remove:
        row.pop(key, None)
    else:
        row[key] = copy.deepcopy(value)


class Cursor:
    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)

    def sort(self, key, direction=1):
        if isinstance(key, list):
            key, direction = key[0]
        self.rows.sort(key=lambda row: row.get(key) or "", reverse=direction < 0)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    async def to_list(self, count):
        return copy.deepcopy(self.rows[:count])

    def __aiter__(self):
        async def iterate():
            for row in self.rows:
                yield row
        return iterate()


class Collection:
    def __init__(self):
        self.rows = []
        self.before_update = None

    def find(self, query, projection=None):
        return Cursor([row for row in self.rows if matches(row, query)])

    async def find_one(self, query, projection=None, **kwargs):
        return next((copy.deepcopy(row) for row in self.rows if matches(row, query)), None)

    async def count_documents(self, query):
        return sum(matches(row, query) for row in self.rows)

    async def insert_one(self, row):
        self.rows.append(copy.deepcopy(row))

    async def update_one(self, query, update, upsert=False):
        if self.before_update:
            callback, self.before_update = self.before_update, None
            callback(self.rows)
        row = next((row for row in self.rows if matches(row, query)), None)
        matched = row is not None
        if row is None and upsert:
            row = copy.deepcopy(query)
            self.rows.append(row)
        if row is not None:
            for key, value in update.get("$set", {}).items():
                put(row, key, value)
            for key in update.get("$unset", {}):
                put(row, key, None, remove=True)
            for key, value in update.get("$push", {}).items():
                row.setdefault(key, []).extend(copy.deepcopy(value["$each"]))
                if "$slice" in value:
                    row[key] = row[key][value["$slice"]:]
        return SimpleNamespace(matched_count=int(matched))

    async def find_one_and_update(self, query, update, **kwargs):
        row = next((row for row in self.rows if matches(row, query)), None)
        if row is None:
            return None
        for key, value in update.get("$set", {}).items():
            put(row, key, value)
        return copy.deepcopy(row)


class Database:
    def __getattr__(self, key):
        collection = Collection()
        setattr(self, key, collection)
        return collection


USER = {"user_id": "owner", "account_type": "pro", "role": "admin"}


@pytest.fixture
def db(monkeypatch):
    database = Database()
    database.users.rows = [copy.deepcopy(USER)]
    monkeypatch.setattr(A, "db", database)
    monkeypatch.setattr(D, "db", database)
    import importlib
    access = importlib.import_module("engines.access")
    async def level(user):
        return "pro" if user.get("account_type") == "pro" else "particulier_gratuit"
    monkeypatch.setattr(access, "compute_level", level)
    return database


def plan(pid="p1", owner="owner"):
    return {"plan_id": pid, "user_id": owner, "filename": "RDC.pdf", "updated_at": "initial",
            "calibrations": {"0": {"pixels_per_meter": 100}, "1": {"pixels_per_meter": 50}},
            "measurements": [{"measurement_id": "m", "kind": "distance", "page_index": 1,
                              "points": [[0, 0], [100, 0]], "value_m": 99, "length_m": 99}], "rooms": []}


def quote(qid="q1", owner="owner"):
    return {"doc_id": qid, "user_id": owner, "doc_type": "quote", "status": "draft", "signed": False,
            "title": "Peinture", "updated_at": "initial", "deposit_pct": 20,
            "lines": [{"designation": "Mur", "unit": "m2", "qty": 10, "unit_price_ht": 20,
                       "discount_pct": 10, "vat_rate": 20}], "totals": {"ht": 999, "ttc": 1198.8}}


@pytest.mark.parametrize("key,params", [
    ("paint", {"length": -1}), ("paint", {"length": "nan"}), ("paint", {"length": "inf"}),
    ("paint", {"length": True}), ("paint", {"doors": 1.5}), ("paint", {"coats": 0}),
    ("paint", {"include_ceiling": "no"}), ("tile", {"tile_length": 0}), ("tile", {"tiles_per_box": 0}),
    ("tile", {"pose": "invalid"}), ("roof_facade", {"pitch_deg": 90}),
    ("roof_facade", {"openings_m2": 9999}), ("insulation", {"area": "bad"}),
])
def test_invalid_calculator_inputs(key, params):
    with pytest.raises(ValueError):
        run_validated(key, params)


@pytest.mark.parametrize("key", list(CALCULATORS))
def test_all_calculators_and_defaults_are_explicit(key):
    result = run_validated(key, {})
    assert result["validation"]["defaulted_fields"]
    if "estimated_budget" in result:
        assert math.isfinite(result["estimated_budget"])
    assert result["results"]
    assert result["validation"]["source_measurements_verified"] is False


def test_boolean_false_and_agent_missing_dimensions():
    result = run_validated("paint", {"include_ceiling": "false"})
    assert result["inputs"]["include_ceiling"] is False
    assert next(r["value"] for r in result["results"] if r["label"] == "Surface plafond") == 0
    with pytest.raises(ValueError, match="Précisez"):
        run_validated("concrete", {}, require_inputs=True)


def test_plan_uses_own_page_scale_and_preserves_sources():
    source = plan()
    result = S.audit_plan(source)
    assert next(c["after"] for c in result["changes"] if c["path"] == "measurements.0.value_m") == 2
    assert source["measurements"][0]["value_m"] == 99
    assert not any("points" in c["path"] or "calibrations" in c["path"] for c in result["changes"])


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p.update(calibrations={}), "missing_scale"),
    (lambda p: p["measurements"][0].update(points=[[0, 0], [float("nan"), 1]]), "invalid_geometry"),
    (lambda p: p["measurements"][0].update(openings=[{"width_m": 30, "height_m": 2}]), "invalid_geometry"),
    (lambda p: p["measurements"][0].update(kind="manual"), "manual_measure"),
])
def test_unknown_or_inconsistent_plan_data_are_not_invented(mutation, code):
    source = plan()
    mutation(source)
    result = S.audit_plan(source)
    assert not result["changes"]
    assert result["issues"][0]["code"] == code


def test_room_unknown_height_is_not_turned_into_a_verified_volume():
    source = plan()
    source["measurements"] = []
    source["rooms"] = [{"points": [[0, 0], [100, 0], [100, 100], [0, 100]], "surface_m2": 50, "volume_m3": 125}]
    result = S.audit_plan(source)
    assert any(c["path"] == "rooms.0.surface_m2" and c["after"] == 1 for c in result["changes"])
    assert not any("volume_m3" in c["path"] or "wall_area" in c["path"] for c in result["changes"])
    assert any(i["code"] == "missing_height" for i in result["issues"])


def test_corrupt_written_area_is_flagged_and_height_inputs_are_preserved():
    source = plan()
    source["measurements"][0]["wall_height_m"] = 0
    result = S.audit_plan(source)
    assert not any(c["path"].endswith("wall_height_m") for c in result["changes"])
    source["measurements"] = []
    source["rooms"] = [{"points": [[0, 0], [100, 0], [100, 100]], "surface_written_m2": float("nan")}]
    result = S.audit_plan(source)
    assert not result["changes"]
    assert result["issues"][0]["code"] == "invalid_geometry"


def test_quote_recomputed_with_discount_but_inputs_unchanged():
    source = quote()
    result = S.audit_quote(source)
    assert next(c["after"] for c in result["changes"] if c["path"] == "totals.ht") == 180
    assert next(c["after"] for c in result["changes"] if c["path"] == "totals.ttc") == 216
    assert all(c["path"].startswith("totals.") for c in result["changes"])


@pytest.mark.parametrize("state", [{"status": "sent"}, {"signed": True}, {"status": "signed"}])
def test_signed_or_sent_quotes_never_autorepaired(state):
    source = quote()
    source.update(state)
    result = S.audit_quote(source)
    assert not result["changes"]
    assert any(i["code"] == "locked_document" for i in result["issues"])


@pytest.mark.asyncio
async def test_repair_readback_history_undo_and_owner_isolation(db):
    db.plans_takeoff.rows = [plan(), plan("other", "another-owner")]
    db.pro_documents.rows = [quote()]
    result = await S.run_supervisor(db, USER, {"run_id": "r1"}, repair=True)
    assert (result["checked"], result["corrected"], result["needs_review"]) == (2, 2, 0)
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 2
    assert db.plans_takeoff.rows[1]["measurements"][0]["value_m"] == 99
    assert db.pro_documents.rows[0]["totals"]["ttc"] == 216
    assert db.pro_documents.rows[0]["facturx_pdf_b64"] is None
    assert (await S.undo_correction(db, USER, "plan", "p1", "r1"))["restored"]
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99
    with pytest.raises(HTTPException) as exc:
        await S.undo_correction(db, USER, "plan", "p1", "r1")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_audit_only_and_concurrent_edit_no_overwrite(db):
    db.plans_takeoff.rows = [plan()]
    await S.run_supervisor(db, USER, {"run_id": "r1"}, repair=False)
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99
    db.plans_takeoff.before_update = lambda rows: rows[0]["measurements"][0].update(points=[[0, 0], [500, 0]])
    result = await S.run_supervisor(db, USER, {"run_id": "r2"}, repair=True)
    assert result["corrected"] == 0
    assert result["resources"][0]["issues"][-1]["code"] == "conflict"
    assert db.plans_takeoff.rows[0]["measurements"][0]["points"][-1] == [500, 0]


@pytest.mark.asyncio
async def test_undo_never_overwrites_a_later_manual_value(db):
    db.pro_documents.rows = [quote()]
    await S.run_supervisor(db, USER, {"run_id": "r1"}, repair=True)
    db.pro_documents.rows[0]["totals"]["ht"] = 450
    with pytest.raises(HTTPException):
        await S.undo_correction(db, USER, "quote", "q1", "r1")
    assert db.pro_documents.rows[0]["totals"]["ht"] == 450


@pytest.mark.asyncio
async def test_whole_selection_resolved_before_any_write(db):
    db.plans_takeoff.rows = [plan()]
    with pytest.raises(HTTPException) as exc:
        await S.run_supervisor(db, USER, {"run_id": "r1", "plan_ids": ["p1"], "quote_ids": ["someone-elses-quote"]}, repair=True)
    assert exc.value.status_code == 404
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99


@pytest.mark.asyncio
async def test_revoked_user_or_quote_role_cannot_mutate(db):
    db.plans_takeoff.rows = [plan()]
    db.users.rows[0]["active"] = False
    with pytest.raises(HTTPException):
        await S.run_supervisor(db, USER, {"run_id": "r1"}, repair=True)
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99
    worker = {"user_id": "worker", "account_type": "pro", "organization_id": "org", "org_role": "ouvrier"}
    with pytest.raises(HTTPException):
        await S.run_supervisor(db, worker, {"run_id": "r2", "quote_ids": ["q1"]}, repair=True)


@pytest.mark.asyncio
async def test_individual_has_supervisor_but_no_professional_agents(db):
    individual = {"user_id": "personal", "account_type": "particulier"}
    result = await A.catalog(individual)
    assert [agent["key"] for agent in result["agents"]] == ["supervise"]
    with pytest.raises(HTTPException) as exc:
        await A.propose_plan(A.PlanIn(agent="devis", plan_ids=["p1"]), individual)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_compare_requires_both_owned_plans_and_no_duplicates(db):
    db.plans_takeoff.rows = [plan()]
    with pytest.raises(HTTPException) as exc:
        await A.propose_plan(A.PlanIn(agent="compare", plan_ids=["p1", "other"]), USER)
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await A.propose_plan(A.PlanIn(agent="compare", plan_ids=["p1", "p1"]), USER)
    assert not db.agent_runs.rows


@pytest.mark.asyncio
async def test_atomic_launch_and_single_worker_claim(db):
    proposal = await A.propose_plan(A.PlanIn(agent="supervise"), USER)
    rid = proposal["run"]["run_id"]
    results = await asyncio.gather(*(A.launch_run(rid, A.ExecIn(mode="repair"), USER) for _ in range(2)))
    assert all(r["queued"] for r in results)
    claims = await asyncio.gather(A._claim_agent_run("worker1"), A._claim_agent_run("worker2"))
    assert sum(claim is not None for claim in claims) == 1
    with pytest.raises(HTTPException):
        await A.launch_run(rid, A.ExecIn(), USER)


@pytest.mark.asyncio
async def test_synchronous_execution_also_claimed_atomically(db, monkeypatch):
    proposal = await A.propose_plan(A.PlanIn(agent="supervise"), USER)
    async def execute(*args):
        await asyncio.sleep(.01)
        return {"kind": "summary"}
    operation = AsyncMock(side_effect=execute)
    monkeypatch.setattr(A, "_do_execute", operation)
    results = await asyncio.gather(*(A.execute_run(proposal["run"]["run_id"], A.ExecIn(), USER) for _ in range(2)), return_exceptions=True)
    assert operation.await_count == 1
    assert sum(isinstance(r, HTTPException) for r in results) == 1
    assert db.agent_runs.rows[0]["status"] == "done"


@pytest.mark.asyncio
async def test_actual_background_supervisor_survives_request_return(db):
    db.plans_takeoff.rows = [plan()]
    proposal = await A.propose_plan(A.PlanIn(agent="supervise"), USER)
    await A.launch_run(proposal["run"]["run_id"], A.ExecIn(mode="repair"), USER)
    claim = await A._claim_agent_run("worker")
    await A._run_agent_job(claim)
    assert db.agent_runs.rows[0]["status"] == "done"
    assert db.agent_runs.rows[0]["result"]["corrected"] == 1
    assert db.notifications.rows[0]["user_id"] == "owner"
    assert db.agent_checks.rows[0]["applied"]


@pytest.mark.asyncio
async def test_queued_disabled_account_fails_without_mutation(db):
    db.plans_takeoff.rows = [plan()]
    proposal = await A.propose_plan(A.PlanIn(agent="supervise"), USER)
    await A.launch_run(proposal["run"]["run_id"], A.ExecIn(mode="repair"), USER)
    claim = await A._claim_agent_run("worker")
    db.users.rows[0]["active"] = False
    await A._run_agent_job(claim)
    assert db.agent_runs.rows[0]["status"] == "error"
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99


@pytest.mark.asyncio
async def test_old_worker_cannot_finish_new_claim(db):
    db.agent_runs.rows = [{"run_id": "r1", "user_id": "owner", "status": "running", "worker": "new", "agent": "supervise"}]
    await A._finish_agent({**db.agent_runs.rows[0], "worker": "old"}, "done", result={})
    assert db.agent_runs.rows[0]["status"] == "running"
    assert not db.notifications.rows


@pytest.mark.parametrize("room", [False, True])
def test_opening_heights_cannot_silently_validate_net_wall_area(room):
    source = plan()
    if room:
        source["measurements"] = []
        source["rooms"] = [{"points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                            "ceiling_height_m": 2.5, "openings": [{"width_m": 1}]}]
    else:
        source["measurements"][0].update(wall_height_m=2, openings=[{"width_m": 1, "height_m": 10}])
    result = S.audit_plan(source)
    assert not result["changes"]
    assert result["issues"][0]["code"] == "invalid_geometry"


@pytest.mark.asyncio
async def test_large_account_is_rejected_before_any_repairs(db):
    db.plans_takeoff.rows = [plan()]
    db.pro_documents.rows = [quote(str(n)) for n in range(201)]
    with pytest.raises(HTTPException) as exc:
        await S.run_supervisor(db, USER, {"run_id": "r1"}, repair=True)
    assert exc.value.status_code == 422
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99


@pytest.mark.asyncio
async def test_cancelled_job_cannot_apply_a_correction(db):
    db.plans_takeoff.rows = [plan()]
    run = (await A.propose_plan(A.PlanIn(agent="supervise"), USER))["run"]
    await A.launch_run(run["run_id"], A.ExecIn(mode="repair"), USER)
    claimed = await A._claim_agent_run("worker")
    await A.cancel_run(run["run_id"], USER)
    with pytest.raises(asyncio.CancelledError):
        await A._run_agent_job(claimed)
    assert db.agent_runs.rows[0]["status"] == "error"
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99
    assert not db.agent_checks.rows


@pytest.mark.asyncio
async def test_assistant_tools_read_actual_owner_state_and_cancel_queued_job(db):
    from engines.platform_agent_tools import execute_platform_tool as execute
    db.plans_takeoff.rows = [plan(), plan("secret", "other")]
    listed = await execute("list_platform_resources", {"query": "", "kind": "all"}, USER, {}, db)
    assert [r["id"] for r in listed["resources"]] == ["p1"]
    queued = await execute("supervise_platform", {"plan_ids": ["p1"], "quote_ids": [], "mode": "repair"}, USER, {}, db)
    state = await execute("get_supervision_result", {"run_id": queued["run_id"]}, USER, {}, db)
    assert state["status"] == "queued" and state["result"] is None
    with pytest.raises(HTTPException):
        await execute("get_supervision_result", {"run_id": queued["run_id"]}, {"user_id": "other"}, {}, db)
    await execute("cancel_supervision", {"run_id": queued["run_id"]}, USER, {}, db)
    assert await A._claim_agent_run("worker") is None
    assert db.plans_takeoff.rows[0]["measurements"][0]["value_m"] == 99


@pytest.mark.asyncio
async def test_quote_append_retry_is_idempotent_and_concurrent_edit_is_preserved(db, monkeypatch):
    import sys
    from engines import assistant_quote_service as Q
    monkeypatch.setattr(Q, "db", db)
    monkeypatch.setitem(sys.modules, "routes.library", SimpleNamespace(auto_save_from_lines=AsyncMock()))
    new_line = {"designation": "Sol", "unit": "m2", "qty": 4, "unit_price_ht": 12, "vat_rate": 20}
    monkeypatch.setattr(Q, "build_lines", AsyncMock(return_value=[new_line]))
    db.pro_documents.rows = [quote()]
    args = {"vat_rate": 20, "lines": [{"designation": "Sol", "line_id": None, "description": "",
        "quantity": 4, "unit": "m2", "unit_price": 12, "price_origin": "user", "vat_rate": 20, "lot": ""}]}
    conv = {"user_id": "owner", "conversation_id": "c1", "_quote_request_id": "request1"}
    await Q.append_quote_lines(args, USER, conv, doc_id="q1")
    again = await Q.append_quote_lines(args, USER, conv, doc_id="q1")
    assert len(again["draft"]["lines"]) == 2
    assert db.pro_documents.rows[0]["facturx_pdf_b64"] is None
    db.pro_documents.before_update = lambda rows: rows[0]["lines"][0].update(qty=27)
    with pytest.raises(HTTPException) as exc:
        await Q.append_quote_lines(args, USER, {**conv, "_quote_request_id": "request2"}, doc_id="q1")
    assert exc.value.status_code == 409
    assert db.pro_documents.rows[0]["lines"][0]["qty"] == 27
    assert len(db.pro_documents.rows[0]["lines"]) == 2


@pytest.mark.asyncio
async def test_deposit_uses_discounted_commercial_lines_only(db, monkeypatch):
    from engines import activity
    monkeypatch.setattr(activity, "log", AsyncMock())
    monkeypatch.setattr(D, "_next_number", AsyncMock(return_value="FA-001"))
    document = quote()
    document.update(signed=True, status="signed")
    document["lines"].append({"kind": "section", "qty": 1000, "unit_price_ht": 1000, "vat_rate": 20})
    db.pro_documents.rows = [document]
    result = await D.build_deposit_invoice("q1", USER, 30)
    assert result["totals"]["ht"] == 54
    assert result["totals"]["ttc"] == 64.8


@pytest.mark.asyncio
async def test_group_quote_keeps_margin_cost_and_count_units(db, monkeypatch):
    # Execute the real endpoint body without importing network-provider modules.
    import ast
    from pathlib import Path
    path = Path(__file__).parents[1] / "routes/plans_analysis.py"
    tree = ast.parse(path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "plan_group_to_quote")
    function.decorator_list = []
    ns = {"db": db, "Depends": lambda *args: None, "current_user": None, "HTTPException": HTTPException,
          "_load_ce_prefs": AsyncMock(return_value={"prices": {}, "ratios": {}}),
          "_measure_chiffrage_qty": lambda m: m["qty"], "_known_poste": lambda *args: True,
          "_estimate_poste": lambda *args: {"label": "Mur", "lines": [{"designation": "Mur", "unit": "m²", "qty": 10, "pu": 20}]}}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(path), "exec"), ns)
    create = AsyncMock(return_value={"doc_id": "new"})
    monkeypatch.setattr(D, "create_document", create)
    db.plan_groups.rows = [{"group_id": "g1", "user_id": "owner", "name": "Maison", "levels": [{"plan_id": "p1", "level_label": "RDC"}]}]
    db.plans_takeoff.rows = [{"plan_id": "p1", "user_id": "owner", "measurements": [
        {"poste": "wall", "qty": 10}, {"kind": "count", "qty": 3, "label": "Portes"}]}]
    await ns["plan_group_to_quote"]("g1", {"margin_pct": 25}, USER)
    rows = create.call_args.args[0].lines
    assert rows[0].unit_price_ht == 25 and rows[0].cost_price_ht == 20 and rows[0].price_estimated
    assert rows[1].unit == "u" and rows[1].price_missing
    assert create.call_args.args[0].title.startswith("Devis partiel")
    assert "pas un budget global" in create.call_args.args[0].notes
    db.plan_groups.rows[0]["levels"] += [{"plan_id":"p1"},{"plan_id":"missing"}]
    db.plans_takeoff.rows[0]["measurements"].append({"qty":float("nan")})
    result = await ns["plan_group_to_quote"]("g1", {"margin_pct":25}, USER)
    assert len(create.call_args.args[0].lines) == 2  # repeated plan is not charged twice
    assert result["coverage"]["missing_plan_ids"] == ["missing"]
    assert result["coverage"]["invalid_measurements"] == 1
    assert not result["coverage"]["project_complete"]
    for invalid in ("bad", float("nan"), float("inf"), -2):
        with pytest.raises(HTTPException) as exc:
            await ns["plan_group_to_quote"]("g1", {"margin_pct": invalid}, USER)
        assert exc.value.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_in_tool", [False, True])
async def test_gemini_failover_never_replays_an_attempted_tool(db, monkeypatch, fail_in_tool):
    import sys
    from engines import assistant_gemini as G
    class TextDelta:
        pass
    class ToolCallStart:
        pass
    class ToolCallReady:
        tool_call = SimpleNamespace(name="write_draft", raw_arguments="{}", id="call1")
    class StreamDone:
        usage = None
        finish_reason = "tool_calls"
    class Chat:
        created = 0
        def __init__(self, **kwargs):
            Chat.created += 1
            self.turns = 0
        def with_model(self, *args): return self
        def with_tools(self, *args, **kwargs): return self
        def with_params(self, **kwargs): return self
        def add_tool_result(self, *args): pass
        async def stream_message(self, *args):
            self.turns += 1
            if self.turns == 1:
                yield ToolCallReady()
                yield StreamDone()
            else:
                raise RuntimeError("quota exceeded")
    writes = []
    async def tool_turn(*args):
        writes.append("written")
        if fail_in_tool:
            raise RuntimeError("quota exceeded")
        args[8].append({"tool": "write_draft", "result": {"ok": True}})
        yield {"type": "result", "result": {"ok": True}, "attachments": [], "args": {}}
    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", SimpleNamespace(
        ImageContent=SimpleNamespace, LlmChat=Chat, StreamDone=StreamDone, TextDelta=TextDelta,
        ToolCallReady=ToolCallReady, ToolCallStart=ToolCallStart, UserMessage=SimpleNamespace))
    for key in ("GEMINI_API_KEY", "EMERGENT_LLM_KEY", "ASSISTANT_GEMINI_MODEL_FAST"):
        monkeypatch.setenv(key, "offline-test-value")
    monkeypatch.setattr(G, "db", db)
    events = [e async for e in G.run_chat_gemini(
        SimpleNamespace(response_mode="fast", web_enabled=False, text="Créer", doc_ids=[]), USER,
        {"_quote_request_id": "r1", "conversation_id": "c1", "title": "Test"}, [], "instructions", [], [],
        {"web_enabled": False}, {}, tool_turn, lambda: "now", lambda user: "pro")]
    assert writes == ["written"]
    assert Chat.created == 1
    assert events[-1]["type"] == "error"
