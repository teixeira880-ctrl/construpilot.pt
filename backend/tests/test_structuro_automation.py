"""Independent numerical checks and regeneration boundaries; no remote services."""
import io
import math
import zipfile

import pytest
from fastapi import HTTPException
from pypdf import PdfReader
from test_structuro_calc_routes import db  # noqa: F401

from engines.structuro_automation import anchorage, generation_hash, run_automation
from engines.structuro_automation_exports import build_automation_pdf
from engines.structuro_calc import Combination, Model, calculate
from engines.structuro_drawing_example import automation_example, drawing_example
from engines.structuro_drawings import Placement, compile_dossier
from routes import structuro_calc as R


def elem(m,id):return next(e for e in m.elements if e.id==id)
def design(r,id):return next(e for e in r['designs'] if e['element_id']==id)


def test_one_run_from_no_drawings_and_independent_equilibrium():
    original=automation_example();assert not original.drawings.bars and not original.drawings.placements and not original.drawings.cuts
    m,r=run_automation(original)
    assert not original.drawings.bars # no caller mutation
    assert r['drawings_ready'] and r['status']=='partial' and not r['execution_ready']
    assert len(r['coverage'])==len(m.elements) and len(r['designs'])==2
    slab=elem(m,'D1');d=design(r,'D1');case=d['cases'][0]
    q=1.35*slab.height_m*slab.density_kn_m3+sum(l.value*(1.35 if l.action=='G' else 1.5) for l in slab.loads)
    assert case['input']['med_knm']==pytest.approx(q*slab.width_m**2/8)
    assert case['input']['ved_kn']==pytest.approx(q*slab.width_m/2)
    assert d['as_provided_mm2_m']==pytest.approx(math.pi*d['diameter_mm']**2/4*1000/d['spacing_mm'])
    assert d['as_provided_mm2_m']>=d['as_required_mm2_m']
    b=design(r,'B1');beam=elem(m,'B1');bars=[x for x in m.drawings.bars if x.element_id=='B1']
    bottom=next(x for x in bars if x.mark.endswith('_B'));links=next(x for x in bars if x.mark.endswith('_E'))
    assert b['d_mm']==pytest.approx(beam.height_m*1000-bottom.points[0].z*1000)
    assert b['as_provided_mm2']==pytest.approx(bottom.count*math.pi*bottom.diameter_mm**2/4)
    assert b['asw_provided_mm2_m']==pytest.approx(2*math.pi*links.diameter_mm**2/4/links.repeat.x)
    assert b['asw_provided_mm2_m']>=b['asw_required_mm2_m']
    assert b['stirrup_spacing_mm']<=.75*b['d_mm']
    for c in calculate(m)['cases']:assert c['external_kn']==pytest.approx(c['ground_kn'])


def test_anchorage_reference_no_confinement_and_poor_bond():
    s=automation_example().automation_settings;a=anchorage(12,s)
    assert a['fbd_mpa']==pytest.approx(1.89)
    assert a['lb_rqd_mm']==pytest.approx(690.1311249137336)
    assert a['lbd_mm']==700 and a['lap_mm']==1040
    s.bond_eta1=1.;assert anchorage(12,s)['lbd_mm']==490


def test_repeat_and_json_roundtrip_do_not_accumulate_bars_or_self_weight():
    first,r=run_automation(automation_example());again,t=run_automation(first)
    assert first.model_dump()==again.model_dump()
    loaded=Model.model_validate_json(first.model_dump_json())
    assert loaded.automation_generated_hash==generation_hash(loaded)
    assert compile_dossier(loaded)['can_export']
    assert r['output_input_hash']==t['output_input_hash']


def test_load_change_requires_regeneration_and_changes_steel():
    m,r=run_automation(automation_example());original=design(r,'B1')
    elem(m,'D1').loads[0].value+=15.
    assert not compile_dossier(m)['can_export']
    updated,t=run_automation(m);b=design(t,'B1')
    assert b['as_required_mm2']>original['as_required_mm2']
    assert b['as_provided_mm2']>original['as_provided_mm2']
    assert t['drawings_ready'] and updated.automation_generated_hash!=m.automation_generated_hash


def test_all_selected_combinations_and_actual_centroid_are_checked():
    m=automation_example();m.combinations.append(Combination(id='HEAVY',label='Essai majoré',factors={'G':1.5,'Q':3.},source=m.combinations[0].source))
    m.automation_settings.uls_case_ids.append('HEAVY')
    n,r=run_automation(m);b=design(r,'B1')
    assert {c['case_id'] for c in b['cases']}=={'ELU','HEAVY'}
    assert all(c['input']['d_mm']==b['d_mm'] and all(c['result']['checks'].values()) for c in b['cases'])
    m.automation_settings.diameters_mm=[8];m.automation_settings.max_bars_per_layer=2
    n,r=run_automation(m)
    assert not any(c['element_id']=='B1' for c in r['designs'])
    assert not any(b.element_id=='B1' for b in n.drawings.bars)


@pytest.mark.parametrize('mutation',[
    lambda s:setattr(s,'confirmed',False),lambda s:setattr(s,'materials',None),
    lambda s:setattr(s,'uls_case_ids',['G']),lambda s:setattr(s,'fctk005_mpa',3.),
])
def test_unknown_inputs_never_receive_engineering_defaults(mutation):
    m=automation_example();mutation(m.automation_settings);n,r=run_automation(m)
    assert r['status']=='blocked' and not n.drawings.bars and r['issues']


def test_bearing_search_recomputes_weight_and_preserves_centres():
    m=automation_example();old=m.model_copy(deep=True);n,r=run_automation(m)
    for f in r['foundations']:
        before=elem(old,f['element_id']);after=elem(n,f['element_id'])
        assert before.x_m+before.length_m/2==pytest.approx(after.x_m+after.length_m/2)
        assert before.y_m+before.width_m/2==pytest.approx(after.y_m+after.width_m/2)
        assert after.height_m==before.height_m
        for row in f['cases']:
            result=next(c for c in calculate(n)['cases'] if c['id']==row['case_id'])
            force=next(e for e in result['elements'] if e['id']==after.id)['total_kn']
            assert row['total_kn']==pytest.approx(force)
            assert row['q_kpa']==pytest.approx(force/after.length_m/after.width_m)
            assert row['q_kpa']<=row['limit_kpa']
        assert f['status']=='bearing_area_only' and f['unresolved']


@pytest.mark.parametrize('failure',['other_site','eccentric','impossible'])
def test_unsuitable_soil_or_foundation_retains_original_geometry(failure):
    m=automation_example();rule=m.automation_settings.foundations[0]
    if failure=='other_site':rule.same_site_confirmed=False
    if failure=='eccentric':elem(m,rule.element_id).x_m+=.05
    if failure=='impossible':rule.q_sls_kpa=.1;rule.q_uls_kpa=.1
    old=elem(m,rule.element_id).model_dump();n,r=run_automation(m)
    assert elem(n,rule.element_id).model_dump()==old
    assert not any(f['element_id']==rule.element_id for f in r['foundations'])
    assert any(x['element']==rule.element_id and x['stage']=='foundations' for x in r['issues'])


def test_manual_bars_openings_and_non_rc_members_are_not_overridden():
    m=automation_example();manual=drawing_example().drawings.bars[0]
    m.drawings.bars=[manual];m.automation_settings.rc_element_ids=[]
    n,r=run_automation(m);assert n.drawings.bars==[manual] and not r['designs']
    m=automation_example();m.drawings.openings=drawing_example().drawings.openings
    n,r=run_automation(m);assert not any(b.element_id=='D1' for b in n.drawings.bars)
    assert n.drawings.openings==m.drawings.openings


def test_levels_regenerate_but_manual_altitudes_are_preserved():
    m,_r=run_automation(automation_example());m.automation_settings.level_top_z_m['R+1']=5.
    level=elem(m,'D1').level;m.automation_settings.level_top_z_m[level]=5.
    m.drawings.placements=[p for p in m.drawings.placements if p.element_id!='B1']+[Placement(element_id='B1',base_z_m=3.,source='Relevé manuel')]
    n,_r=run_automation(m);placements={p.element_id:p for p in n.drawings.placements}
    assert placements['D1'].base_z_m==pytest.approx(5-elem(n,'D1').height_m)
    assert placements['B1'].base_z_m==3. and placements['B1'].generated_by is None


def test_pdf_reports_unresolved_work_and_rejects_stale_report():
    m,r=run_automation(automation_example());pdf=build_automation_pdf(m,r,4)
    pages=PdfReader(io.BytesIO(pdf)).pages;text='\n'.join(p.extract_text() for p in pages)
    assert len(pages)>=6 and 'NON EXÉCUTOIRE' in text and '700 mm' in text and 'Non dimensionné' in text
    m.title+=' changement'
    with pytest.raises(ValueError):build_automation_pdf(m,r,4)


def test_transverse_stirrup_detail_shows_its_actual_bending_plane():
    from engines.structuro_drawing_exports import build_scene
    m,_r=run_automation(automation_example());d=compile_dossier(m)
    b=next(b for b in m.drawings.bars if b.mark.endswith('_E'))
    sh=next(s for s in d['sheets'] if s.get('mark')==b.mark)
    scene=build_scene(m,d,sh)
    labels=[p['text'] for p in scene.items if p['kind']=='text']
    assert 'Vue locale Y / Z' in labels
    assert sum(t.startswith('L2=') for t in labels)==1 # no labels stacked in the collapsed side view


@pytest.mark.asyncio
async def test_owned_one_click_autosave_and_zip_routes(db):  # noqa: F811
    owner={'user_id':'automatic-owner'};s=await R.create(R.CreateIn(automation_demonstration=True),owner)
    assert not s['model']['drawings']['bars']
    body=R.SaveIn(expected_revision=1,model=Model.model_validate(s['model']))
    with pytest.raises(HTTPException) as e:await R.automate(s['study_id'],body,{'user_id':'other'})
    assert e.value.status_code==404
    s=await R.automate(s['study_id'],body,owner);assert s['revision']==2 and s['automation_result']['drawings_ready']
    with pytest.raises(HTTPException) as e:await R.automate(s['study_id'],body,owner)
    assert e.value.status_code==409
    m=Model.model_validate(s['model']);elem(m,'D1').loads[0].value+=5.
    s=await R.save(s['study_id'],R.SaveIn(expected_revision=2,model=m),owner)
    assert s['revision']==3 and s['automation_result']['drawings_ready']
    response=await R.export(s['study_id'],'dossier',owner,expected_revision=3)
    with zipfile.ZipFile(io.BytesIO(response.body)) as z:
        assert len(z.namelist())==6 and z.read('01_plans_A3.pdf').startswith(b'%PDF')
        assert z.read('02_note_automatisation.pdf').startswith(b'%PDF')
        assert Model.model_validate_json(z.read('05_modele.json')).automation_generated_hash==s['model']['automation_generated_hash']
    with pytest.raises(HTTPException):await R.export(s['study_id'],'dossier',owner,expected_revision=2)


@pytest.mark.asyncio
async def test_import_recalculates_and_source_race_prevents_save(db,monkeypatch):  # noqa: F811
    m,r=run_automation(automation_example());elem(m,'D1').loads[0].value+=5.
    owner={'user_id':'owner'};s=await R.import_model(R.ImportIn(model=m),owner)
    assert s['automation_result']['generation_hash']!=r['generation_hash']
    await db.plans_takeoff.insert_one({'plan_id':'pc','user_id':'owner','updated_at':'v1','pages':[]})
    pc=await R.create(R.CreateIn(plan_id='pc'),owner)
    real=R.run_automation
    def changing(model):
        db.plans_takeoff.rows[0]['updated_at']='v2'
        return real(model)
    monkeypatch.setattr(R,'run_automation',changing)
    with pytest.raises(HTTPException) as e:await R.automate(pc['study_id'],R.SaveIn(expected_revision=1,model=automation_example()),owner)
    assert e.value.status_code==409
    assert db.structuro_calculations.rows[-1]['revision']==1
