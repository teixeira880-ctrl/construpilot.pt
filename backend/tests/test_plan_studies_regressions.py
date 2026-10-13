"""Contrat API simulé : aucun appel OpenAI et aucune base de production.

Charge le vrai module avec core.db remplacé pendant l'import seulement.
"""
import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf

ROOT = Path(__file__).parents[1]
_spec = importlib.util.spec_from_file_location('isolated_studies_engine', ROOT/'engines/openai_studies.py')
AI = importlib.util.module_from_spec(_spec)
_db = types.ModuleType('core.db'); _db.db = None
with patch.dict(sys.modules, {'core.db': _db}):
    _spec.loader.exec_module(AI)

from engines.interior_prompt import INTERIOR_SCHEMA
from engines.studies_prompt import ANALYSIS_SCHEMA, VERIFY_SCHEMA
from engines.plan_refresh import extract_page_geometry


def empty_value(schema):
    if 'enum' in schema: return schema['enum'][0]
    typ=schema['type']
    if isinstance(typ,list): return None if 'null' in typ else empty_value({**schema,'type':typ[0]})
    if typ=='object': return {k:empty_value(schema['properties'][k]) for k in schema.get('required',[])}
    return {'array':[], 'string':'', 'integer':0, 'number':0., 'boolean':False, 'null':None}[typ]


def interior_review(engine, source_page=1):
    data=empty_value(INTERIOR_SCHEMA)
    data.update(analysis_complete=True,summary='Relecture simulée')
    for w in engine.get('walls') or []:
        d=empty_value(INTERIOR_SCHEMA['properties']['walls']['items'])
        d.update(wall_id=w['wall_id'],orientation=w['orientation'],thickness_m=w['thickness_m'],engine_agreement='confirmed')
        data['walls'].append(d)
    for m in engine.get('interior_measurements') or []:
        d=empty_value(INTERIOR_SCHEMA['properties']['interior_measurements']['items'])
        d.update({k:v for k,v in m.items() if k in d});d['page']=source_page
        data['interior_measurements'].append(d)
    for r in engine.get('closure_equations') or []:
        d=empty_value(INTERIOR_SCHEMA['properties']['closure_equations']['items'])
        d.update({k:v for k,v in r.items() if k in d});d['exterior_dimension_m']=r['written_exterior_m']
        data['closure_equations'].append(d)
    return data


def response(data, status='completed'):
    return types.SimpleNamespace(output_text=json.dumps(data),status=status,usage=types.SimpleNamespace())


def pdf_two_pages():
    with pymupdf.open() as doc:
        doc.new_page().insert_text((60,60),'PAGE ONE EXCLUDED')
        doc.new_page().insert_text((60,60),'PAGE TWO SELECTED')
        return doc.tobytes()


def fake_client(outputs):
    return types.SimpleNamespace(files=types.SimpleNamespace(create=AsyncMock(return_value=types.SimpleNamespace(id='file-test')),
                                                           delete=AsyncMock()),
                                 responses=types.SimpleNamespace(create=AsyncMock(side_effect=outputs)),close=AsyncMock())


class StudiesRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def analyze(self, client, walls=None):
        with patch.object(AI,'_client',return_value=client), patch.object(AI,'check_quota',new=AsyncMock()), patch.object(AI,'_log_usage',new=AsyncMock()):
            return await AI.analyze_plan(user_id='test-user',plan_id='test-plan',project_id=None,pdf_bytes=pdf_two_pages(),filename='source.pdf',
                                         page_index=1,request_text='Seulement les murs du vide sanitaire',engine_json={},crops=[],lang='fr',walls_result=walls)

    def replies(self, engine):
        review=interior_review(engine,2)
        analysis=empty_value(ANALYSIS_SCHEMA);analysis['pages_analyzed']=[2]
        verification=empty_value(VERIFY_SCHEMA);verification['verified']=True
        return [response(review),response(review),response(review),response(analysis),response(verification)]

    async def test_only_selected_source_page_is_sent_and_file_is_deleted(self):
        engine=extract_page_geometry((ROOT/'tests/fixtures/synth_walls_1_50.pdf').read_bytes(),0,200/72)['walls_analysis']
        client=fake_client(self.replies(engine))
        result=await self.analyze(client,engine)
        uploaded=client.files.create.call_args.kwargs['file'][1]
        with pymupdf.open(stream=uploaded,filetype='pdf') as pdf:
            self.assertEqual(len(pdf),1)
            self.assertIn('TWO SELECTED',pdf[0].get_text());self.assertNotIn('ONE EXCLUDED',pdf[0].get_text())
        self.assertEqual(client.responses.create.await_count,5)
        self.assertTrue(result['verified'])
        self.assertEqual(result['interior']['engine']['interior_measurements'],engine['interior_measurements'])
        for call in client.responses.create.call_args_list:
            parts=call.kwargs['input'][0]['content']
            self.assertEqual(parts[0]['detail'],'high')
            self.assertIn('Seulement les murs du vide sanitaire',json.dumps(parts,ensure_ascii=False))
        client.files.delete.assert_awaited_once_with('file-test');client.close.assert_awaited_once()

    async def test_missing_geometry_cannot_be_validated_by_optimistic_ai(self):
        client=fake_client(self.replies({}))
        result=await self.analyze(client)
        self.assertEqual(client.responses.create.await_count,5)
        self.assertFalse(result['verified']);self.assertFalse(result['interior']['complete'])
        self.assertTrue(result['incomplete_message'])

    async def test_failed_call_still_deletes_file_and_closes_client(self):
        client=fake_client([RuntimeError('simulated failure')])
        with self.assertRaises(AI.StudiesError): await self.analyze(client)
        client.files.delete.assert_awaited_once_with('file-test');client.close.assert_awaited_once()

    async def test_incomplete_or_invalid_json_is_rejected(self):
        for r in [response({},'incomplete'),response({}),types.SimpleNamespace(status='completed',output_text='{')]:
            client=fake_client([r])
            with self.assertRaises(AI.StudiesError):
                await AI._respond(client,'model','high','scope',[],ANALYSIS_SCHEMA,'test')

    async def test_wrong_page_cannot_be_saved(self):
        replies=self.replies({});wrong=empty_value(ANALYSIS_SCHEMA);wrong['pages_analyzed']=[1,2]
        replies[3]=response(wrong);client=fake_client(replies)
        with self.assertRaisesRegex(AI.StudiesError,'page source'): await self.analyze(client)
        client.files.delete.assert_awaited_once()

    def test_ai_changed_measurement_or_missing_measurement_blocks_completion(self):
        engine=extract_page_geometry((ROOT/'tests/fixtures/synth_walls_1_50.pdf').read_bytes(),0,200/72)['walls_analysis']
        r=interior_review(engine)
        self.assertEqual(AI.review_disagreements(r,engine,0),[])
        r['interior_measurements'][0]['geometric_dimension_m']+=.02
        self.assertTrue(AI.review_disagreements(r,engine,0))
        r=interior_review(engine);r['interior_measurements'].pop()
        self.assertTrue(AI.review_disagreements(r,engine,0))

    def test_no_detected_walls_still_produces_original_pdf_zooms(self):
        crops=AI.zone_crops(pdf_two_pages(),1,{},1,max_crops=3)
        self.assertEqual(len(crops),3)
        self.assertTrue(all(c['data_url'].startswith('data:image/png;base64,') for c in crops))

    def test_json_payload_is_complete_or_explicitly_rejected(self):
        value={'description':'é'*70000}
        self.assertEqual(json.loads(AI._json_payload(value)),value)
        with self.assertRaises(AI.StudiesError): AI._json_payload({'value':'x'*500001})


if __name__=='__main__': unittest.main()
