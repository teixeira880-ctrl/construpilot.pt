"""Fonctions de route réelles isolées via AST ; dépendances DB/IA simulées.

Ceci ne remplace pas le test HTTP avec FastAPI/MongoDB en préproduction.
"""
import ast
import base64
import copy
import sys
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from engines import plan_cotes as C
from engines.plan_refresh import carry_user_edits
from test_plan_geometry_regressions import synthetic_page, report_items
from test_plan_studies_regressions import AI


class HttpError(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code
        super().__init__(detail)


def route_namespace():
    path=Path(__file__).parents[1]/'routes/plans_cotes.py'
    source=ast.parse(path.read_text())
    names={'_interior_report','_recompute','studies_analyze','_engine_json'}
    funcs=[n for n in source.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    for f in funcs: f.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+funcs,type_ignores=[])
    ns={'C':C,'uuid':uuid,'_now':lambda:'test-now','Depends':lambda *a,**kw:None,'Query':lambda v,*a,**kw:v,
        'current_user':None,'HTTPException':HttpError,'_ensure_current_geometry':AsyncMock(return_value=False)}
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),ns)
    return ns


class RoutesRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_recompute_saves_fresh_interior_and_invalidates_old_study(self):
        ns=route_namespace();page=synthetic_page()
        ppm=page['walls_analysis']['pt_per_m']*200/72
        report=C.check_dimensions(C.dims_from_pdf_vectors(page['pdf_dimensions']),ppm,2.,3.,page['width_px'],page['height_px'])
        report.update(revision='old',calibration={'pixels_per_meter':ppm},geometry={'narratif':{'text':'ancien'}})
        items=copy.deepcopy(report['items'])
        for item in items:
            if item['indicated_m']==4.:item['indicated_m']=4.02;item['edited']=True
        update=AsyncMock();ns['db']=types.SimpleNamespace(plans_takeoff=types.SimpleNamespace(update_one=update))
        fresh=await ns['_recompute']({'user_id':'u'},page,'p',0,report,items,2.,3.)
        self.assertNotEqual(fresh['revision'],'old')
        self.assertFalse(fresh['interior']['validation']['complete'])
        self.assertTrue(fresh['geometry']['stale']);self.assertTrue(fresh['geometry']['narratif']['stale'])
        values={m['written_dimension_m'] for m in fresh['interior']['interior_measurements']}
        self.assertIn(4.02,values)
        self.assertIn('studies.0',update.call_args.args[1]['$unset'])

    async def test_study_finishing_after_edit_is_rejected(self):
        ns=route_namespace();page=synthetic_page();page['image_png_b64']='mock-preview'
        report={'engine_version':2,'revision':'old','items':report_items(page),'calibration':{'pixels_per_meter':page['walls_analysis']['pt_per_m']*200/72}}
        plan={'cotes_checks':{'0':report},'page_count':1}
        update=AsyncMock(return_value=types.SimpleNamespace(matched_count=0))
        source=base64.b64encode((Path(__file__).parent/'fixtures/synth_walls_1_50.pdf').read_bytes()).decode()
        ns.update(_plan_page=AsyncMock(return_value=(plan,page)),_report_lang=AsyncMock(return_value='fr'),_snapshot=AsyncMock(),
                  db=types.SimpleNamespace(plan_sources=types.SimpleNamespace(find_one=AsyncMock(return_value={'data_b64':source})),
                                           plans_takeoff=types.SimpleNamespace(find_one=AsyncMock(return_value={}),update_one=update)))
        with patch.dict(sys.modules,{'engines.openai_studies':AI}),patch.object(AI,'check_quota',new=AsyncMock()), \
             patch.object(AI,'small_dimension_crops',return_value=[]),patch.object(AI,'zone_crops',return_value=[]), \
             patch.object(AI,'analyze_plan',new=AsyncMock(return_value={'verified':True,'analysis':{}})):
            with self.assertRaises(HttpError) as caught:
                await ns['studies_analyze']('p',types.SimpleNamespace(page_index=0,request='murs',effort='high'),False,{'user_id':'u'})
        self.assertEqual(caught.exception.status_code,409)
        self.assertEqual(update.call_args.args[0]['cotes_checks.0.revision'],'old')
        self.assertEqual(update.call_args.args[0]['user_id'],'u')
        ns['_snapshot'].assert_not_awaited()

    def test_reextraction_carries_edits_by_coordinates_not_old_index(self):
        page=synthetic_page();items=report_items(page)
        old=next(i for i in items if i['indicated_m']==4.)
        old.update(edited=True,indicated_m=4.02,original_m=4.)
        dims=list(reversed(C.dims_from_pdf_vectors(page['pdf_dimensions'])))
        self.assertEqual(carry_user_edits(dims,items),[])
        edited=[d for d in dims if d.get('edited')]
        self.assertEqual(len(edited),1);self.assertEqual(edited[0]['value_m'],4.02)
        self.assertEqual(edited[0]['x1'],old['x1'])
        self.assertEqual(carry_user_edits([],items),[old['index']])


if __name__=='__main__':unittest.main()
