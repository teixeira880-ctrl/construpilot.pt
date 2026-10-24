"""Assistant BTP ↔ moteur IA à options : lecture du catalogue, lancement en file, suivi. Base de test isolée."""
import copy
import importlib

import pytest

from engines import assistant_missions as AM
from routes import agents as A, missions as R
from test_platform_supervisor import USER, Database
from test_missions import plan


@pytest.fixture
def db(monkeypatch):
    database = Database()
    database.users.rows = [copy.deepcopy(USER)]
    for mod in (A, R, AM):
        monkeypatch.setattr(mod, "db", database)
    access = importlib.import_module("engines.access")

    async def level(user):
        return "pro" if user.get("account_type") == "pro" else "particulier_gratuit"
    monkeypatch.setattr(access, "compute_level", level)
    monkeypatch.setenv("MISSION_SYNTHESIS", "0")
    return database


def test_tools_are_strict():
    for t in AM.MISSION_TOOLS:
        p = t["parameters"]
        assert t["strict"] and set(p["required"]) == set(p["properties"])
    assert "nunca" in AM.MISSION_INSTRUCTIONS and "envias" in AM.MISSION_INSTRUCTIONS


@pytest.mark.asyncio
async def test_options_list_catalog_and_owned_plans(db):
    db.plans_takeoff.rows = [plan(), {**plan("p2"), "user_id": "autre"}]
    out = await AM.run_mission_tool("programme_ia_options", {"chantier_id": None}, USER)
    assert out["ok"] and "metre" in {o["key"] for o in out["options"]}
    assert [p["plan_id"] for p in out["plans"]] == ["p1"]
    assert all("prompt" not in o for o in out["options"])


@pytest.mark.asyncio
async def test_launch_queues_only_requested_options(db):
    db.plans_takeoff.rows = [plan()]
    out = await AM.run_mission_tool("lancer_programme_ia",
                                    {"options": ["devis", "metre"], "plan_ids": ["p1"], "chantier_id": None, "note": "lot 1"}, USER)
    assert out["ok"] and out["status"] == "queued" and out["options"] == ["metre", "devis"]
    run = db.agent_runs.rows[0]
    assert run["status"] == "queued" and run["agent"] == "mission" and run["prompt"] == "lot 1"
    follow = await AM.run_mission_tool("suivre_programme_ia", {"run_id": out["run_id"]}, USER)
    assert follow["statut"] == "queued" and [o["option"] for o in follow["options"]] == ["metre", "devis"]
    listing = await AM.run_mission_tool("suivre_programme_ia", {"run_id": None}, USER)
    assert listing["programmes"][0]["run_id"] == out["run_id"]


@pytest.mark.asyncio
async def test_launch_refuses_missing_dependency_without_adding_it(db):
    db.plans_takeoff.rows = [plan()]
    out = await AM.run_mission_tool("lancer_programme_ia", {"options": ["devis"], "plan_ids": ["p1"], "chantier_id": None, "note": ""}, USER)
    assert not out["ok"] and "Medição" in out["error"]
    assert not db.agent_runs.rows


@pytest.mark.asyncio
async def test_other_users_plan_and_individual_account_refused(db):
    db.plans_takeoff.rows = [{**plan(), "user_id": "autre"}]
    out = await AM.run_mission_tool("lancer_programme_ia", {"options": ["metre"], "plan_ids": ["p1"], "chantier_id": None, "note": ""}, USER)
    assert not out["ok"]
    indiv = {"user_id": "personal", "account_type": "particulier"}
    out = await AM.run_mission_tool("programme_ia_options", {"chantier_id": None}, indiv)
    assert not out["ok"]
