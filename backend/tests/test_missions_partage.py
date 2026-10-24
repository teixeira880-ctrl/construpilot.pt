"""Opção « partage » do programa de opções (PT): ligação criada inativa, ativada só pelo profissional."""
import copy
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from routes import agents as A, missions as R
from test_missions import _run, plan
from test_platform_supervisor import USER, Database


@pytest.fixture
def db(monkeypatch):
    database = Database()
    database.users.rows = [copy.deepcopy(USER)]
    for mod in (A, R, importlib.import_module("routes.mep")):
        monkeypatch.setattr(mod, "db", database)
    access = importlib.import_module("engines.access")

    async def level(user):
        return "pro"
    monkeypatch.setattr(access, "compute_level", level)
    monkeypatch.setenv("MISSION_SYNTHESIS", "0")
    monkeypatch.setenv("PUBLIC_BACKEND_URL", "https://api.exemplo.pt")
    database.plans_takeoff.rows = [plan()]
    return database


@pytest.mark.asyncio
async def test_share_of_mep_studies_is_inactive_until_pro_activates(db):
    run = {**_run(["plan_electricite", "partage"]), "plan_status": [{"plan_id": "p1", "filename": "p1-RDC.pdf"}]}
    db.agent_runs.rows = [copy.deepcopy(run)]
    result = await R.run_mission(run, A.ExecIn(), USER)
    assert [s["status"] for s in result["steps"]] == ["done", "done"], result["steps"]
    share = result["steps"][1]["result"]
    assert share["kind"] == "share" and share["active"] is False and share["files"] == ["Planos de execução — p1-RDC.pdf"]
    token = db.mission_shares.rows[0]["token"]
    study_id = db.mission_shares.rows[0]["items"][0]["id"]
    with pytest.raises(HTTPException):                                   # inativa: nada público
        await R.public_share(token)
    with pytest.raises(HTTPException):
        await R.activate_share(share["share_id"], R.ShareActivateIn(days=7), {**USER, "user_id": "outro"})
    act = await R.activate_share(share["share_id"], R.ShareActivateIn(days=7), USER)
    assert act["url"] == f"https://api.exemplo.pt/api/missions/public/{token}"
    page = await R.public_share(token)
    assert "Planos de execução".encode() in page.body and b"noindex" in page.body
    assert (await R.public_share_file(token, study_id)).body[:4] == b"%PDF"
    with pytest.raises(HTTPException):
        await R.public_share_file(token, "outro_estudo")
    db.mission_shares.rows[0]["expires_at"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with pytest.raises(HTTPException):
        await R.public_share(token)
    await R.activate_share(share["share_id"], None, USER)
    await R.revoke_share(share["share_id"], USER)
    with pytest.raises(HTTPException):
        await R.public_share(token)


@pytest.mark.asyncio
async def test_share_without_studies_fails(db):
    with pytest.raises(HTTPException, match="Nenhum entregável"):
        await R._exec_partage({"run": {**_run(["partage"]), "run_id": "r1"}, "user": USER, "cache": {}, "results": {}})
