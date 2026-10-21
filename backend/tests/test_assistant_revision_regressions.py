"""Révisions des brouillons et lecture de détails, sans API réelle."""
import types
import os
import unittest
from unittest.mock import AsyncMock, patch

import pymupdf
from engines.assistant_workspace import inspect_region
from test_assistant_workspace_regressions import A, Database, call, response


class DraftRevisions(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        env = patch.dict(os.environ, {"ASSISTANT_MODEL_THOROUGH": "test-thorough", "ASSISTANT_MODEL_FAST": "test-fast"})
        env.start()
        self.addCleanup(env.stop)
        self.db=Database();self.patcher=patch.object(A,'db',self.db);self.patcher.start()
        self.user={'user_id':'u'}
        self.conv={'conversation_id':'conv','title':'Courrier','project_id':None,'_quote_request_id':'test-request','_settings':{'web_enabled':False,'learning_mode':'off'}}
        self.db.assistant_work_drafts.rows=[{'draft_id':'work_a','user_id':'u','kind':'email','title':'Objet','recipient':'',
                                             'body':'Texte initial','status':'draft','revision':0}]
    async def asyncTearDown(self):self.patcher.stop()

    async def test_stale_model_update_cannot_overwrite_manual_correction(self):
        read=await A._exec_tool('read_work_draft',{'draft_id':'work_a'},self.user,self.conv)
        await A.update_work_draft('work_a',A.WorkDraftIn(kind='email',title='Objet',body='Correction manuelle',expected_revision=0),self.user)
        with self.assertRaises(A.HTTPException) as exc:
            await A._exec_tool('update_work_draft',{'draft_id':'work_a','expected_revision':read['draft']['revision'],
                                                   'title':'Objet','recipient':'','body':'Ancienne réponse IA'},self.user,self.conv)
        self.assertEqual(exc.exception.status_code,409)
        self.assertEqual((await A._owned_draft('work_a','u'))['body'],'Correction manuelle')

    async def test_atomic_update_conflict_is_reported(self):
        with patch.object(self.db.assistant_work_drafts,'update_one',new=AsyncMock(return_value=types.SimpleNamespace(matched_count=0))):
            with self.assertRaises(A.HTTPException) as exc:
                await A.update_work_draft('work_a',A.WorkDraftIn(kind='email',title='Objet',body='Nouveau',expected_revision=0),self.user)
        self.assertEqual(exc.exception.status_code,409)

    async def test_ten_previous_versions_and_restoration_keeps_new_revision(self):
        for index in range(12):
            await A.update_work_draft('work_a',A.WorkDraftIn(kind='email',title='Objet',body=f'Texte {index+1}',expected_revision=index),self.user)
        result=await A.work_draft_versions('work_a',self.user)
        self.assertEqual(len(result['versions']),10)
        self.assertEqual(result['versions'][0]['revision'],11)
        chosen=result['versions'][-1]
        saved=await A.update_work_draft('work_a',A.WorkDraftIn(kind='email',title=chosen['title'],body=chosen['body'],expected_revision=12),self.user)
        self.assertEqual(saved['revision'],13)
        self.assertEqual(saved['body'],chosen['body'])
        self.assertNotIn('history',saved)

    async def test_legacy_draft_without_revision_can_be_edited(self):
        del self.db.assistant_work_drafts.rows[0]['revision']
        saved=await A.update_work_draft('work_a',A.WorkDraftIn(kind='email',title='Objet',body='Révisé',expected_revision=0),self.user)
        self.assertEqual(saved['revision'],1)

    async def test_versions_and_changes_require_owner(self):
        with self.assertRaises(A.HTTPException):await A.work_draft_versions('work_a',{'user_id':'other'})
        with self.assertRaises(A.HTTPException):await A._exec_tool('read_work_draft',{'draft_id':'work_a'},{'user_id':'other'},self.conv)

    async def test_second_read_in_same_turn_returns_current_revision(self):
        update={'draft_id':'work_a','expected_revision':0,'title':'Objet','recipient':'','body':'Révisé par IA'}
        outputs=[response(calls=[call('read_work_draft',{'draft_id':'work_a'},'read1')]),
                 response(calls=[call('update_work_draft',update,'update1')]),
                 response(calls=[call('read_work_draft',{'draft_id':'work_a'},'read2')]),response('Révision prête.')]
        client=types.SimpleNamespace(responses=types.SimpleNamespace(create=AsyncMock(side_effect=outputs)),close=AsyncMock())
        with patch.object(A,'_client',return_value=client):
            events=[e async for e in A._run_chat(A.MsgIn(conversation_id='conv',text='Révise le courrier'),self.user,False,prepared=(self.conv,[],'instructions',[]))]
        reads=[e['action']['result']['draft'] for e in events if e['type']=='action' and e['action']['tool']=='read_work_draft']
        self.assertEqual([d['revision'] for d in reads],[0,1])
        self.assertEqual(reads[-1]['body'],'Révisé par IA')


class DetailedReading(unittest.TestCase):
    def test_zoom_on_rotated_pdf_reads_the_displayed_region(self):
        with pymupdf.open() as pdf:
            page=pdf.new_page(width=400,height=200)
            page.insert_text((30,30),'LEFT');page.insert_text((300,30),'RIGHT');page.set_rotation(90)
            data=pdf.tobytes()
        result=inspect_region(data,'application/pdf',1,[.6,.65,.99,.99])
        self.assertIn('RIGHT',result['text']);self.assertNotIn('LEFT',result['text'])
        self.assertLessEqual(max(result['pixel_size']),2401)
        self.assertEqual(result['_model_attachments'][1]['type'],'input_image')

    def test_invalid_region_is_rejected_before_render(self):
        for box in ([0,0,float('nan'),1],[.5,.5,.1,.9],[0,0,.001,1],[-1,0,1,1]):
            with self.subTest(box=box),self.assertRaises(ValueError):inspect_region(b'not parsed','application/pdf',1,box)

