"""Stockage et réextraction réels, base et routes externes isolées."""
import ast
import base64
import copy
import secrets
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pymupdf
import ezdxf
from engines import plan_sources as S
from engines import plan_cotes as C
from engines.plan_dxf import process_dxf
from test_cad_regressions import drawing_bytes
from test_assistant_workspace_regressions import Database


def route_functions(file, names, db):
    path=Path(__file__).parents[1]/'routes'/file
    nodes=[n for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    for n in nodes:n.decorator_list=[]
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0)]+nodes,type_ignores=[])
    ns={'db':db,'C':C,'secrets':secrets,'_now':lambda:'test-now','Depends':lambda *a,**kw:None,'current_user':None,
        'HTTPException':S.HTTPException,'_insert_plan_safe':AsyncMock(),'copy_plan_sources':S.copy_plan_sources,'delete_plan_sources':S.delete_plan_sources}
    exec(compile(ast.fix_missing_locations(module),str(path),'exec'),ns)
    return ns


class SourceStorage(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.db=Database()

    async def test_large_source_is_chunked_and_byte_exact(self):
        data=b'PDF-SOURCE'*1000000  # 10 MB, above the inline threshold
        await S.save_plan_source(self.db,'p','u',data,mime='application/pdf')
        metadata=self.db.plan_sources.rows[0]
        self.assertNotIn('data_b64',metadata)
        self.assertGreater(metadata['chunk_count'],1)
        self.assertTrue(all(len(c['data_b64'])<1500000 for c in self.db.plan_source_chunks.rows))
        loaded=await S.load_plan_source(self.db,'p','u')
        self.assertEqual(base64.b64decode(loaded['data_b64']),data)
        self.assertIsNone(await S.load_plan_source(self.db,'p','other'))

    async def test_missing_or_corrupted_piece_rejected(self):
        with patch.object(S,'INLINE_LIMIT',2):
            await S.save_plan_source(self.db,'p','u',b'abcdef')
        self.db.plan_source_chunks.rows[0]['data_b64']=base64.b64encode(b'abcdeg').decode()
        with self.assertRaises(S.HTTPException):await S.load_plan_source(self.db,'p','u')
        self.db.plan_source_chunks.rows=[]
        with self.assertRaises(S.HTTPException):await S.load_plan_source(self.db,'p','u')

    async def test_failed_publication_preserves_previous_source(self):
        await S.save_plan_source(self.db,'p','u',b'previous')
        with patch.object(S,'INLINE_LIMIT',2),patch.object(self.db.plan_sources,'update_one',new=AsyncMock(side_effect=RuntimeError('write failed'))):
            with self.assertRaises(RuntimeError):await S.save_plan_source(self.db,'p','u',b'new bytes')
        self.assertFalse(self.db.plan_source_chunks.rows)
        self.assertEqual(base64.b64decode((await S.load_plan_source(self.db,'p','u'))['data_b64']),b'previous')

    async def test_lost_acknowledgement_keeps_published_pieces(self):
        real=self.db.plan_sources.update_one
        async def committed_then_failed(*args,**kwargs):
            await real(*args,**kwargs)
            raise RuntimeError('ack lost')
        with patch.object(S,'INLINE_LIMIT',2),patch.object(self.db.plan_sources,'update_one',new=committed_then_failed):
            with self.assertRaises(RuntimeError):await S.save_plan_source(self.db,'p','u',b'published')
        self.assertEqual(base64.b64decode((await S.load_plan_source(self.db,'p','u'))['data_b64']),b'published')

    async def test_native_cad_chunks_check_expected_count(self):
        await S.save_cad_source(self.db,'p','u','converted_dxf',b'DXF')
        self.db.plan_cad_sources.rows[0]['chunk_count']=2
        with self.assertRaises(S.HTTPException):await S.load_cad_source(self.db,'p','u','converted_dxf')
        self.assertIsNone(await S.load_cad_source(self.db,'p','other','converted_dxf'))

    async def test_legacy_inline_source_is_compatible(self):
        self.db.plan_sources.rows=[{'plan_id':'p','user_id':'u','data_b64':base64.b64encode(b'legacy').decode()}]
        self.assertEqual(base64.b64decode((await S.load_plan_source(self.db,'p','u'))['data_b64']),b'legacy')

    async def test_copy_is_independent_and_preserves_cad_metadata(self):
        with patch.object(S,'INLINE_LIMIT',2):
            await S.save_plan_source(self.db,'original','u',b'pdf source',mime='application/pdf')
            await S.save_cad_source(self.db,'original','u','original',b'CAD bytes')
            self.db.plans_takeoff.rows=[{'plan_id':'original','user_id':'u','kind':'dxf','filename':'plan.dxf','pages':[],
                                         'cad_import':{'units':{'name':'m'}},'structural_metre':{'wall_length':4}}]
            ns=route_functions('plans_crud.py',{'duplicate_plan','_duplicate_filename'},self.db)
            result=await ns['duplicate_plan']('original',{'user_id':'u'})
        copied=ns['_insert_plan_safe'].call_args.args[0]
        self.assertEqual(copied['cad_import']['units']['name'],'m')
        self.assertEqual(copied['structural_metre']['wall_length'],4)
        await S.delete_plan_sources(self.db,'original','u')
        self.assertEqual(base64.b64decode((await S.load_plan_source(self.db,result['plan_id'],'u'))['data_b64']),b'pdf source')
        self.assertEqual(await S.load_cad_source(self.db,result['plan_id'],'u','original'),b'CAD bytes')

    async def test_duplicate_database_failure_cleans_only_new_copy(self):
        await S.save_plan_source(self.db,'original','u',b'PDF')
        self.db.plans_takeoff.rows=[{'plan_id':'original','user_id':'u','kind':'pdf','pages':[]}]
        ns=route_functions('plans_crud.py',{'duplicate_plan','_duplicate_filename'},self.db)
        ns['_insert_plan_safe'].side_effect=RuntimeError('database failed')
        with self.assertRaises(RuntimeError):await ns['duplicate_plan']('original',{'user_id':'u'})
        self.assertEqual([r['plan_id'] for r in self.db.plan_sources.rows],['original'])

    def test_image_pdf_has_same_display_coordinate_system(self):
        from PIL import Image,ImageDraw
        import io
        img=Image.new('RGB',(400,200),'white');ImageDraw.Draw(img).rectangle((90,40,110,60),fill='black')
        out=io.BytesIO();img.save(out,format='PNG')
        source=S.image_plan_pdf({'width_px':400,'height_px':200,'dpi':96,'image_png_b64':base64.b64encode(out.getvalue()).decode()})
        with pymupdf.open(stream=source,filetype='pdf') as pdf:
            pix=pdf[0].get_pixmap(matrix=pymupdf.Matrix(96/72,96/72),alpha=False)
            self.assertEqual((pix.width,pix.height),(400,200))
            self.assertLess(sum(pix.pixel(100,50)),30)


class NativeReextraction(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        doc=ezdxf.new();doc.header['$INSUNITS']=6
        doc.modelspace().add_lwpolyline([(0,0),(4,0),(4,.2),(0,.2)],close=True)
        doc.modelspace().add_linear_dim(base=(0,1),p1=(0,0),p2=(4,0)).render()
        cls.data=drawing_bytes(doc);cls.parsed=process_dxf(cls.data)

    async def asyncSetUp(self):
        self.db=Database()
        self.plan={'plan_id':'p','user_id':'u','kind':'dxf','filename':'plan.dxf','pages':copy.deepcopy(self.parsed['pages']),
                   'cad_import':copy.deepcopy(self.parsed['cad_import'])}
        self.db.plans_takeoff.rows=[self.plan]
        await S.save_cad_source(self.db,'p','u','original',self.data)
        self.ns=route_functions('plans_cotes.py',{'cotes_reextract'},self.db)

    async def test_cad_reextraction_stays_native(self):
        with patch('engines.plan_refresh.extract_page_geometry') as pdf_reader,patch.object(self.db.plans_takeoff,'update_one',new=AsyncMock()) as update:
            result=await self.ns['cotes_reextract']('p',{'user_id':'u'})
        pdf_reader.assert_not_called()
        fields=update.call_args.args[1]['$set']
        self.assertEqual(fields['pages.$.geometry_coordinate_space'],'image_px')
        self.assertEqual(fields['pages.$.unit_to_m'],1)
        self.assertEqual(fields['pages.$.dxf_dimensions'][0]['value_m'],4)
        self.assertEqual(result['pages'][0]['source'],'dxf')

    async def test_missing_native_does_not_fall_back_to_rendered_pdf(self):
        self.db.plan_cad_sources.rows=[]
        await S.save_plan_source(self.db,'p','u',base64.b64decode(self.parsed['analysis_pdf_b64']))
        with patch.object(self.db.plans_takeoff,'update_one',new=AsyncMock()) as update:
            with self.assertRaises(S.HTTPException) as error:await self.ns['cotes_reextract']('p',{'user_id':'u'})
        self.assertEqual(error.exception.status_code,409);update.assert_not_awaited()

    async def test_changed_preview_does_not_move_manual_measurements(self):
        self.plan['pages'][0]['image_png_b64']='previous-render'
        with patch.object(self.db.plans_takeoff,'update_one',new=AsyncMock()) as update:
            with self.assertRaises(S.HTTPException):await self.ns['cotes_reextract']('p',{'user_id':'u'})
        update.assert_not_awaited()

    async def test_unmatched_user_edit_blocks_publication(self):
        self.plan['cotes_checks']={'0':{'items':[{'index':1,'source':'dxf','edited':True,'indicated_m':3.9,
                                                 'x1':99999,'y1':0,'x2':100000,'y2':0}]}}
        with patch.object(self.db.plans_takeoff,'update_one',new=AsyncMock()) as update:
            with self.assertRaises(S.HTTPException):await self.ns['cotes_reextract']('p',{'user_id':'u'})
        update.assert_not_awaited()
