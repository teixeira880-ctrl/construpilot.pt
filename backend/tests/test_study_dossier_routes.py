"""Real routes and jobs, isolated async Mongo model; no production/paid AI calls."""
import asyncio
import copy
import os
from datetime import timedelta
from unittest.mock import AsyncMock
os.environ.setdefault('MONGO_URL','mongodb://localhost:27017')
os.environ.setdefault('DB_NAME','construpilot_test')
os.environ.setdefault('JWT_SECRET','dossier-test-only-not-production')
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from mongomock_motor import AsyncMongoMockClient
from engines import study_dossier_jobs as J, study_dossier_ai as AI
from routes import study_dossier as R, plans_pc as P, documents as D
from test_study_dossier import reference,calculate,tiny
from engines.study_dossier import build_dossier

USER={'user_id':'owner','account_type':'pro','plan':'pro','active':True,'organization_id':'company'}

@pytest.fixture
async def db(monkeypatch):
    database=AsyncMongoMockClient().test
    for module in (J,R,P,D):monkeypatch.setattr(module,'db',database)
    monkeypatch.setattr(J,'study_settings',AsyncMock(return_value={'country':'FR','vat_rate':20,'vat_assumed':True}))
    monkeypatch.setattr(R,'study_settings',AsyncMock(side_effect=lambda owner,saved: saved))
    await database.users.insert_one(copy.deepcopy(USER))
    await database.plans_takeoff.insert_one({'plan_id':'plan_a','user_id':'owner','updated_at':'v1','filename':'PC.pdf','pages':[{'index':i,'image_png_b64':'fixture'} for i in range(11)],'pc_study':calculate(tiny())})
    await database.pc_study_jobs.create_index('job_id',unique=True)
    await database.pc_study_jobs.create_index('active_key',unique=True,partialFilterExpression={'active':True})
    return database

@pytest.mark.asyncio
async def test_all_pages_queued_idempotency_cancel_and_tenant(db):
    a=await J.enqueue_study('plan_a',{'request_id':'request'},USER)
    b=await J.enqueue_study('plan_a',{'request_id':'request'},USER)
    assert a['job_id']==b['job_id']
    job=await db.pc_study_jobs.find_one({'job_id':a['job_id']})
    assert job['indices']==list(range(11))
    with pytest.raises(HTTPException):await R.get_job(a['job_id'],{'user_id':'other'})
    with pytest.raises(HTTPException):await J.enqueue_study('plan_a',{}, {'user_id':'other'})
    cancelled=await R.cancel_job(a['job_id'],USER);assert cancelled['status']=='cancelled'
    assert (await J.enqueue_study('plan_a',{'request_id':'request'},USER))['status']=='cancelled'

@pytest.mark.asyncio
async def test_team_readonly_cannot_launch_or_revise(db):
    colleague={**USER,'user_id':'colleague'}
    with pytest.raises(HTTPException) as e: await J.enqueue_study('plan_a',{},colleague)
    assert e.value.status_code==403
    study=(await db.plans_takeoff.find_one({'plan_id':'plan_a'}))['pc_study']
    with pytest.raises(HTTPException) as e: await R.revise_dossier('plan_a',R.DossierRevisionIn(expected_revision=study['revision']),colleague)
    assert e.value.status_code==403

@pytest.mark.asyncio
async def test_revision_recalculates_archives_conflict_and_unreview(db):
    study=(await db.plans_takeoff.find_one({'plan_id':'plan_a'}))['pc_study']
    updated=await R.revise_dossier('plan_a',R.DossierRevisionIn(expected_revision=study['revision'],parameter_changes={'area':12},price_changes={'wall':3},review_states={'area':True}),USER)
    assert updated['totals']['ht']==36 and updated['items'][0]['quantity_status']=='M'
    assert await db.pc_study_history.count_documents({})==1
    with pytest.raises(HTTPException) as e: await R.revise_dossier('plan_a',R.DossierRevisionIn(expected_revision=study['revision']),USER)
    assert e.value.status_code==409
    next=await R.revise_dossier('plan_a',R.DossierRevisionIn(expected_revision=updated['revision'],review_states={'area':False}),USER)
    assert next['items'][0]['quantity_status']=='H'

@pytest.mark.parametrize('value',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_revision_rejected(value):
    with pytest.raises(ValidationError):R.DossierRevisionIn(expected_revision='r',parameter_changes={'unused':value})

@pytest.mark.asyncio
async def test_quote_snapshot_idempotent_does_not_overwrite_edits(db,monkeypatch):
    from core import permissions
    monkeypatch.setattr(permissions,'require_feature',lambda *args:None)
    f=reference();st=build_dossier(f['spec'],page_count=11,settings=f['settings'])
    await db.plans_takeoff.update_one({'plan_id':'plan_a'},{'$set':{'pc_study':st}})
    res=await R.create_quote('plan_a',R.DossierQuoteIn(expected_revision=st['revision']),USER)
    doc=await db.pro_documents.find_one({'doc_id':res['doc_id']})
    assert doc['totals']['ht']==280619.68 and doc['totals']['tva']==56123.94
    assert doc['study_dossier']['revision']==st['revision'] and doc['assistant_review_required']
    await db.pro_documents.update_one({'doc_id':res['doc_id']},{'$set':{'title':'Manually changed'}})
    await R.create_quote('plan_a',R.DossierQuoteIn(expected_revision=st['revision']),USER)
    assert await db.pro_documents.count_documents({})==1
    assert (await db.pro_documents.find_one({'doc_id':res['doc_id']}))['title']=='Manually changed'
    await db.plans_takeoff.update_one({'plan_id':'plan_a'},{'$set':{'pc_study':calculate(tiny(None))}})
    with pytest.raises(HTTPException):await R.create_quote('plan_a',R.DossierQuoteIn(expected_revision=calculate(tiny(None))['revision']),USER)

@pytest.mark.parametrize('selection',[[64],list(range(65)),[],[True],[-1]])
def test_invalid_selection_never_silently_truncated(selection):
    with pytest.raises(HTTPException):J.selection([{}]*64,selection)

@pytest.mark.asyncio
async def test_ai_reads_last_page_and_flags_failed_pages(monkeypatch):
    calls=[]
    async def chat(prompt,**kwargs):
        calls.append(prompt)
        if prompt.startswith(AI.PAGE_PROMPT):
            if 'Page 2.' in prompt:raise RuntimeError('provider failure')
            return {'kind':'plan','observations':[{'label':'area','value':8,'unit':'m²','status':'observed'}]}
        s=tiny();s['parameters'][0].update(status='observed',observation_ids=['p11_o1'],sources=[{'page':11,'text':'surface'}]);return s
    monkeypatch.setattr(AI,'_chat',chat)
    spec,coverage,analyses=await AI.analyze_dossier([{'image_png_b64':'fixture'}]*11,list(range(11)),pdf_bytes=None,request='GO')
    assert coverage['analyzed_pages'][-1]==11 and coverage['failed_pages']==[2]
    assert len(calls)==12 and len(analyses)==10
    assert not spec['parameters'][0].get('conflict')

@pytest.mark.asyncio
async def test_background_job_stale_plan_never_overwrites(db,monkeypatch):
    from engines import plan_sources
    monkeypatch.setattr(plan_sources,'load_plan_source',AsyncMock(return_value=None))
    async def analyze(*args,**kwargs):
        await db.plans_takeoff.update_one({'plan_id':'plan_a'},{'$set':{'updated_at':'edited'}})
        return tiny(),{},[]
    monkeypatch.setattr(AI,'analyze_dossier',analyze)
    job=await J.enqueue_study('plan_a',{},USER)
    await db.pc_study_jobs.update_one({'job_id':job['job_id']},{'$set':{'status':'running','worker':'w','lease_until':J.now()+timedelta(seconds=45)}})
    stored=await db.pc_study_jobs.find_one({'job_id':job['job_id']})
    with pytest.raises(J.StudyError,match='modifié pendant'):await J.run_job(stored)
    assert (await db.plans_takeoff.find_one({'plan_id':'plan_a'}))['updated_at']=='edited'

@pytest.mark.asyncio
async def test_cancel_before_commit_preserves_old_study(db,monkeypatch):
    from engines import plan_sources
    monkeypatch.setattr(plan_sources,'load_plan_source',AsyncMock(return_value=None))
    job=await J.enqueue_study('plan_a',{},USER)
    await db.pc_study_jobs.update_one({'job_id':job['job_id']},{'$set':{'status':'running','worker':'w','lease_until':J.now()+timedelta(seconds=45)}})
    stored=await db.pc_study_jobs.find_one({'job_id':job['job_id']})
    async def analyze(*args,**kwargs):
        await R.cancel_job(job['job_id'],USER)
        return tiny(20),{},[]
    monkeypatch.setattr(AI,'analyze_dossier',analyze)
    with pytest.raises(asyncio.CancelledError):await J.run_job(stored)
    assert (await db.plans_takeoff.find_one({'plan_id':'plan_a'}))['pc_study']['totals']['ht']==20

@pytest.mark.asyncio
async def test_commit_phase_cannot_be_cancelled(db):
    job=await J.enqueue_study('plan_a',{},USER)
    await db.pc_study_jobs.update_one({'job_id':job['job_id']},{'$set':{'status':'committing'}})
    with pytest.raises(HTTPException) as e:await R.cancel_job(job['job_id'],USER)
    assert e.value.status_code==409

def test_decimal_commercial_vat_and_half_cent():
    out=D._compute_totals([{'qty':1,'unit_price_ht':.03,'vat_rate':20} for _ in range(3)])
    assert out['tva']==.02
    assert D._compute_totals([{'qty':1,'unit_price_ht':1.005,'vat_rate':20}])['ht']==1.01
