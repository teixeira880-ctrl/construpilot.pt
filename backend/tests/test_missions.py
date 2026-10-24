"""Programa IA de opções (PT): seleção, ordem, execução limitada às opções validadas.

Base isolée (fausse collection Mongo de test_platform_supervisor), aucun appel modèle."""
import copy
import importlib

import pytest
from fastapi import HTTPException

from engines import missions as M
from routes import agents as A, missions as R
from test_platform_supervisor import USER, Database



@pytest.fixture
def db(monkeypatch):
    database = Database()
    database.users.rows = [copy.deepcopy(USER)]
    monkeypatch.setattr(A, "db", database)
    monkeypatch.setattr(R, "db", database)
    access = importlib.import_module("engines.access")

    async def level(user):
        return "pro" if user.get("account_type") == "pro" else "particulier_gratuit"
    monkeypatch.setattr(access, "compute_level", level)
    monkeypatch.setenv("MISSION_SYNTHESIS", "0")
    return database


def plan(pid="p1", rooms=1):
    return {"plan_id": pid, "user_id": "owner", "filename": f"{pid}-RDC.pdf",
            "calibrations": {"0": {"pixels_per_meter": 100}},
            "measurements": [{"measurement_id": "m", "poste": "mur", "openings": [{}]}],
            "rooms": [{"room_id": f"r{i}", "page_index": 0, "surface_m2": 12,
                       "points": [[0, 0], [300, 0], [300, 400], [0, 400]]} for i in range(rooms)]}


CATALOG = {k: {**v, "key": k, "enabled": True, "prompt_version": 0} for k, v in M.OPTIONS.items()}


def test_resolve_keeps_catalog_order_and_never_adds_options():
    assert M.resolve(["dossier", "metre", "analyse_plans"], CATALOG, has_plans=True, has_chantier=False) == \
        ["analyse_plans", "metre", "dossier"]
    with pytest.raises(M.MissionError, match="Medição"):
        M.resolve(["devis"], CATALOG, has_plans=True, has_chantier=False)


@pytest.mark.parametrize("selected,kwargs,message", [
    ([], {"has_plans": True, "has_chantier": True}, "pelo menos uma opção"),
    (["metre", "metre"], {"has_plans": True, "has_chantier": True}, "duplicado"),
    (["inconnue"], {"has_plans": True, "has_chantier": True}, "desconhecida"),
    (["metre"], {"has_plans": False, "has_chantier": True}, "pelo menos uma planta"),
    (["planning"], {"has_plans": True, "has_chantier": False}, "processo de obra"),
])
def test_resolve_rejects_invalid_selection(selected, kwargs, message):
    with pytest.raises(M.MissionError, match=message):
        M.resolve(selected, CATALOG, **kwargs)


def test_disabled_option_is_rejected():
    catalog = copy.deepcopy(CATALOG)
    catalog["metre"]["enabled"] = False
    with pytest.raises(M.MissionError, match="indisponível"):
        M.resolve(["metre"], catalog, has_plans=True, has_chantier=False)


@pytest.mark.asyncio
async def test_admin_override_changes_prompt_and_disables(db):
    db.mission_options.rows = [{"key": "metre", "prompt": "Nouveau prompt métré", "version": 3},
                               {"key": "devis", "enabled": False}]
    catalog = await M.effective_options(db)
    assert catalog["metre"]["prompt"] == "Nouveau prompt métré" and catalog["metre"]["prompt_version"] == 3
    assert catalog["devis"]["enabled"] is False
    public = await R.catalog(USER)
    assert "devis" not in {o["key"] for o in public["options"]}
    assert all("prompt" not in o for o in public["options"])


@pytest.mark.asyncio
async def test_propose_records_validated_selection_without_running(db):
    db.plans_takeoff.rows = [plan()]
    out = await R.propose(R.MissionIn(options=["devis", "metre"], plan_ids=["p1"]), USER)
    run = out["run"]
    assert run["status"] == "proposed" and run["agent"] == "mission"
    assert [s["key"] for s in run["mission"]["steps"]] == ["metre", "devis"]
    assert all(s["status"] == "pending" and "prompt" not in s for s in run["mission"]["steps"])
    stored = db.agent_runs.rows[0]
    assert stored["mission"]["steps"][0]["prompt"] == M.OPTIONS["metre"]["prompt"]
    with pytest.raises(HTTPException) as exc:
        await R.propose(R.MissionIn(options=["devis"], plan_ids=["p1"]), USER)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_mission_agent_is_hidden_from_classic_flow(db):
    assert "mission" not in {a["key"] for a in (await A.catalog(USER))["agents"]}
    with pytest.raises(HTTPException) as exc:
        await A.propose_plan(A.PlanIn(agent="mission"), USER)
    assert exc.value.status_code == 422


def _run(keys):
    steps = [{"key": k, "name": M.OPTIONS[k]["name"], "depends_on": M.OPTIONS[k]["depends_on"],
              "prompt": M.OPTIONS[k]["prompt"], "status": "pending"} for k in keys]
    return {"run_id": "agr_x", "user_id": "owner", "agent": "mission", "worker": "w", "status": "running",
            "plan_ids": ["p1"], "plan_status": [], "chantier_id": None, "mission": {"options": keys, "steps": steps}}


@pytest.mark.asyncio
async def test_failed_option_blocks_dependents_only(db, monkeypatch):
    calls = []

    async def ok(ctx):
        calls.append("analyse_plans")
        return {"kind": "analysis", "plans": []}

    async def boom(ctx):
        calls.append("metre")
        raise HTTPException(422, "Plan sans échelle")

    async def never(ctx):
        calls.append("devis")
        return {}
    monkeypatch.setitem(R.EXECUTORS, "analyse_plans", ok)
    monkeypatch.setitem(R.EXECUTORS, "metre", boom)
    monkeypatch.setitem(R.EXECUTORS, "devis", never)
    run = _run(["analyse_plans", "metre", "devis"])
    db.agent_runs.rows = [copy.deepcopy(run)]
    result = await R.run_mission(run, A.ExecIn(), USER)
    assert calls == ["analyse_plans", "metre"]
    assert [s["status"] for s in result["steps"]] == ["done", "error", "skipped"]
    assert result["steps"][1]["error"] == "Plan sans échelle"
    assert (result["done"], result["error"], result["skipped"]) == (1, 1, 1)
    assert db.agent_runs.rows[0]["partial_result"]["steps"][2]["status"] == "skipped"


@pytest.mark.asyncio
async def test_only_validated_options_run_and_get_synthesis(db, monkeypatch):
    ran, prompts = [], []
    for key in M.OPTIONS:
        async def executor(ctx, key=key):
            ran.append(key)
            return {"kind": key}
        monkeypatch.setitem(R.EXECUTORS, key, executor)

    async def synth(prompt, result, feature="mission"):
        prompts.append(prompt)
        return "Synthèse"
    monkeypatch.setattr(M, "synthesize", synth)
    run = _run(["metre", "plan_electricite"])
    db.agent_runs.rows = [copy.deepcopy(run)]
    result = await R.run_mission(run, A.ExecIn(), USER)
    assert ran == ["metre", "plan_electricite"]
    assert prompts == [M.OPTIONS["metre"]["prompt"], M.OPTIONS["plan_electricite"]["prompt"]]
    assert all(s["synthese"] == "Synthèse" for s in result["steps"])


@pytest.mark.asyncio
async def test_all_options_failing_marks_run_as_error(db, monkeypatch):
    async def boom(ctx):
        raise RuntimeError("secret provider detail")
    monkeypatch.setitem(R.EXECUTORS, "metre", boom)
    run = _run(["metre"])
    db.agent_runs.rows = [copy.deepcopy(run)]
    with pytest.raises(HTTPException) as exc:
        await R.run_mission(run, A.ExecIn(), USER)
    assert "secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_mep_study_is_shared_between_electricity_and_plumbing(db, monkeypatch):
    import engines.mep as mep
    calls = []
    monkeypatch.setattr(mep, "generate", lambda data: calls.append(data) or {"summary": {"circuits": 4}})
    mep_routes = importlib.import_module("routes.mep")
    monkeypatch.setattr(mep_routes, "db", db)
    db.plans_takeoff.rows = [plan()]
    run = _run(["plan_electricite", "plan_plomberie"])
    run["plan_status"] = [{"plan_id": "p1", "filename": "p1-RDC.pdf"}]
    db.agent_runs.rows = [copy.deepcopy(run)]
    result = await R.run_mission(run, A.ExecIn(), USER)
    assert len(calls) == 1 and len(db.mep_studies.rows) == 1
    elec, plumb = (s["result"] for s in result["steps"])
    assert elec["studies"][0]["svg"].endswith("layer=elec")
    assert plumb["studies"][0]["svg"].endswith("layer=plumb")
    assert elec["studies"][0]["study_id"] == plumb["studies"][0]["study_id"]


@pytest.mark.asyncio
async def test_mep_without_rooms_reports_the_reason(db):
    db.plans_takeoff.rows = [plan(rooms=0)]
    run = _run(["plan_electricite"])
    run["plan_status"] = [{"plan_id": "p1", "filename": "p1-RDC.pdf"}]
    db.agent_runs.rows = [copy.deepcopy(run)]
    with pytest.raises(HTTPException) as exc:
        await R.run_mission(run, A.ExecIn(), USER)
    assert "Nenhuma divisão" in exc.value.detail


@pytest.mark.asyncio
async def test_planning_never_overwrites_existing_schedule(db, monkeypatch):
    planning = importlib.import_module("routes.planning")
    monkeypatch.setattr(planning, "COLL", db.chantier_plannings)
    db.chantier_plannings.rows = [{"chantier_id": "c1", "user_id": "owner", "tasks": [{"id": "t"}]}]

    async def init_plan(*a, **k):
        raise AssertionError("must not regenerate")
    monkeypatch.setattr(planning, "init_plan", init_plan)
    out = await R._exec_planning({"run": {"chantier_id": "c1"}, "user": USER})
    assert out["kept_existing"] is True and out["link"] == "/planning?chantier=c1"


@pytest.mark.asyncio
async def test_synthesis_is_optional(monkeypatch):
    monkeypatch.setenv("MISSION_SYNTHESIS", "1")
    ai = importlib.import_module("engines.ai")

    async def down(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(ai, "_complete", down)
    assert await M.synthesize("prompt", {"x": 1}) is None
    monkeypatch.setenv("MISSION_SYNTHESIS", "0")
    assert await M.synthesize("prompt", {"x": 1}) is None


def test_public_run_hides_prompts():
    run = _run(["metre"])
    run["result"] = {"kind": "mission", "steps": copy.deepcopy(run["mission"]["steps"])}
    out = R._public_run(run)
    assert "prompt" not in out["mission"]["steps"][0] and "prompt" not in out["result"]["steps"][0]
    assert "worker" not in out


@pytest.mark.asyncio
async def test_finished_mission_notification_opens_the_programme(db):
    await A._agent_notify("agr_x", "owner", "done", "Programme IA à options", "mission")
    await A._agent_notify("agr_y", "owner", "done", "Métré express", "metre")
    links = {n["notif_id"]: n["link"] for n in db.notifications.rows}
    assert links == {"n_agent_agr_x": "/missions?run=agr_x", "n_agent_agr_y": "/agents?run=agr_y"}
