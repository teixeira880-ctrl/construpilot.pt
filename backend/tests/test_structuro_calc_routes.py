"""Route-level permissions, concurrency and AI-boundary tests without paid services."""
import copy
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
os.environ.setdefault("MONGO_URL","mongodb://localhost:27017")
os.environ.setdefault("DB_NAME","structure_test")
os.environ.setdefault("JWT_SECRET","structure-test-only-not-production")
import pytest
from fastapi import HTTPException,FastAPI
from fastapi.testclient import TestClient
from engines.structuro_calc import example
from engines import structuro_pc
from routes import structuro_calc as R


class Collection:
    def __init__(self):self.rows=[]
    async def find_one(self,q,projection=None):
        return next((copy.deepcopy(x) for x in self.rows if all(x.get(k)==v for k,v in q.items())),None)
    async def insert_one(self,x):self.rows.append(copy.deepcopy(x))
    async def update_one(self,q,u):
        for x in self.rows:
            if all(x.get(k)==v for k,v in q.items()):
                for k,v in u["$set"].items():
                    if "." in k:
                        a,b=k.split(".",1);x.setdefault(a,{})[b]=copy.deepcopy(v)
                    else:x[k]=copy.deepcopy(v)
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def db(monkeypatch):
    db=SimpleNamespace(structuro_calculations=Collection(),plans_takeoff=Collection())
    monkeypatch.setattr(R,"db",db)
    return db


@pytest.mark.asyncio
async def test_ownership_cas_and_changed_model_recalculate(db):
    owner={"user_id":"owner"};other={"user_id":"other"}
    s=await R.create(R.CreateIn(demonstration=True),owner)
    with pytest.raises(HTTPException) as e:await R.get(s["study_id"],other)
    assert e.value.status_code==404
    with pytest.raises(HTTPException):await R.export(s["study_id"],"pdf",other)
    m=example();m.elements[0].density_kn_m3=None
    updated=await R.save(s["study_id"],R.SaveIn(expected_revision=1,model=m),owner)
    assert updated["revision"]==2 and updated["result"]["cases"]==[]
    assert updated["result"]["input_hash"]!=s["result"]["input_hash"]
    with pytest.raises(HTTPException) as e:await R.save(s["study_id"],R.SaveIn(expected_revision=1,model=example()),owner)
    assert e.value.status_code==409


@pytest.mark.asyncio
async def test_real_pc_never_receives_example_or_guessed_sections(db,monkeypatch):
    user={"user_id":"owner"}
    await db.plans_takeoff.insert_one({"plan_id":"pc","user_id":"owner","filename":"PC.pdf","updated_at":"v1","pages":[{"image_png_b64":"test"}]*11})
    with pytest.raises(HTTPException):await R.create(R.CreateIn(plan_id="pc",demonstration=True),user)
    with pytest.raises(HTTPException):await R.create(R.CreateIn(plan_id="pc"),{"user_id":"other"})
    s=await R.create(R.CreateIn(plan_id="pc"),user)
    assert not s["model"]["elements"] and s["page_count"]==11
    reader=AsyncMock(return_value={"page":11,"elements":[],"status":"unreviewed"})
    monkeypatch.setattr(structuro_pc,"read_page",reader)
    s2=await R.read_page(s["study_id"],R.ReadIn(expected_revision=1,page=11),user)
    assert s2["page_readings"]["11"]["page"]==11
    await R.read_page(s["study_id"],R.ReadIn(expected_revision=2,page=11),user)
    assert reader.await_count==1
    await db.plans_takeoff.update_one({"plan_id":"pc"},{"$set":{"updated_at":"v2"}})
    stale=await R.get(s["study_id"],user)
    assert stale["source_stale"] and stale["result"]["cases"]==[]
    with pytest.raises(HTTPException) as e:await R.export(s["study_id"],"pdf",user)
    assert e.value.status_code==409


@pytest.mark.asyncio
async def test_failed_ai_does_not_add_fake_success(db,monkeypatch):
    u={"user_id":"owner"}
    await db.plans_takeoff.insert_one({"plan_id":"pc","user_id":"owner","pages":[{"image_png_b64":"test"}]})
    s=await R.create(R.CreateIn(plan_id="pc"),u)
    monkeypatch.setattr(structuro_pc,"read_page",AsyncMock(side_effect=RuntimeError("provider")))
    with pytest.raises(HTTPException) as e:await R.read_page(s["study_id"],R.ReadIn(expected_revision=1,page=1),u)
    assert e.value.status_code==502
    stored=await R.get(s["study_id"],u)
    assert stored["revision"]==1 and stored["page_readings"]=={}


@pytest.mark.asyncio
async def test_ai_can_never_approve_or_supply_mechanical_inputs(monkeypatch):
    from engines import study_dossier_ai
    el=example().elements[0].model_dump()
    monkeypatch.setattr(study_dossier_ai,"_chat",AsyncMock(return_value={"kind":"plan","elements":[el]}))
    reading=await structuro_pc.read_page({"image_png_b64":"test"},9,"PC.pdf")
    e=reading["elements"][0]
    assert e["id"]=="p9_e1" and e["source"]["page"]==9
    assert not e["reviewed"] and e["density_kn_m3"] is None and not e["supports"] and not e["loads"]


def test_http_authentication_and_pro_guard():
    app=FastAPI();app.include_router(R.router)
    with TestClient(app) as client:
        assert client.get("/structuro/calc/schema").status_code==401
    async def denied():raise HTTPException(403,"pro required")
    app.dependency_overrides[R.router.dependencies[0].dependency]=denied
    app.dependency_overrides[R.current_user]=lambda:{"user_id":"owner"}
    with TestClient(app) as client:
        assert client.get("/structuro/calc/schema").status_code==403
