"""Fixtures CAO synthétiques, aucun service de conversion ni fichier client."""
import asyncio
import base64
import io
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ezdxf
from PIL import Image
from engines.cad_geometry import resolve_units, CadUnitsRequired, walk_entities, polyline_length_area, hatch_area, entity_vectors, inventory
from engines.plan_dxf import process_dxf, _extract_dimensions
from engines import dwg_convert


def drawing_bytes(doc):
    stream = io.StringIO(); doc.write(stream); return stream.getvalue().encode(doc.output_encoding)


class CadRegressions(unittest.TestCase):
    def test_declared_units_and_override(self):
        doc = ezdxf.new()
        for code, factor in [(1,.0254),(2,.3048),(4,.001),(5,.01),(6,1)]:
            doc.header['$INSUNITS'] = code
            self.assertAlmostEqual(resolve_units(doc)['unit_to_m'], factor)
        self.assertEqual(resolve_units(doc, 'mm')['source'], 'user')

    def test_missing_units_are_not_guessed(self):
        doc = ezdxf.new(); doc.header['$INSUNITS'] = 0
        doc.modelspace().add_line((0,0),(15000,0))
        with self.assertRaises(CadUnitsRequired): resolve_units(doc)
        self.assertEqual(resolve_units(doc, 'm')['unit_to_m'], 1)

    def test_nested_block_transforms_and_layer_inheritance(self):
        doc = ezdxf.new(); doc.layers.new('MURS')
        inner = doc.blocks.new('INNER'); inner.add_line((0,0),(2,0))
        outer = doc.blocks.new('OUTER'); outer.add_blockref('INNER',(1,0),dxfattribs={'rotation':90})
        doc.modelspace().add_blockref('OUTER',(10,20),dxfattribs={'xscale':2,'yscale':2,'layer':'MURS'})
        entities = list(walk_entities(doc)); self.assertEqual(len(entities),1)
        self.assertEqual(entities[0].dxf.layer,'MURS')
        self.assertAlmostEqual(entities[0].dxf.start.x,12)
        self.assertAlmostEqual(entities[0].dxf.end.y,24)

    def test_hidden_parent_layer_and_multi_insert(self):
        doc = ezdxf.new(); layer=doc.layers.new('HIDDEN'); layer.off()
        block=doc.blocks.new('B');block.add_line((0,0),(1,0))
        doc.modelspace().add_blockref('B',(0,0),dxfattribs={'layer':'HIDDEN'})
        doc.modelspace().add_blockref('B',(0,0),dxfattribs={'row_count':2,'row_spacing':3,'column_count':2,'column_spacing':4})
        entities=list(walk_entities(doc));self.assertEqual(len(entities),4)
        self.assertEqual({tuple(e.dxf.start)[:2] for e in entities},{(0.,0.),(4.,0.),(0.,3.),(4.,3.)})

    def test_polyline_bulge_including_closing_edge(self):
        doc=ezdxf.new()
        poly=doc.modelspace().add_lwpolyline([(0,0,0),(2,0,1)],format='xyb',close=True)
        length,area=polyline_length_area(poly)
        self.assertAlmostEqual(length,2+math.pi)
        self.assertAlmostEqual(area,math.pi/2)

    def test_hatch_hole_is_subtracted(self):
        doc=ezdxf.new();h=doc.modelspace().add_hatch()
        h.paths.add_polyline_path([(0,0),(4,0),(4,4),(0,4)],is_closed=True,flags=1)
        h.paths.add_polyline_path([(1,1),(3,1),(3,3),(1,3)],is_closed=True,flags=0)
        self.assertAlmostEqual(hatch_area(h),12)

    def test_linear_dimension_is_projected_not_diagonal(self):
        doc=ezdxf.new();d=doc.modelspace().add_linear_dim(base=(0,3),p1=(0,0),p2=(4,1),angle=0);d.render()
        values=_extract_dimensions(doc.modelspace(),lambda x,y:(x,y),1)
        self.assertEqual(values[0]['measured_m'],4)
        self.assertEqual(values[0]['y1'],values[0]['y2'])

    def test_dimension_override_with_dimlfac(self):
        doc=ezdxf.new();d=doc.modelspace().add_linear_dim(base=(0,3000),p1=(0,0),p2=(4000,0),text='4.20',override={'dimlfac':.001});d.render()
        values=_extract_dimensions(doc.modelspace(),lambda x,y:(x,y),.001)
        self.assertEqual(values[0]['value_m'],4.2)
        self.assertEqual(values[0]['measured_m'],4.)

    def test_dimension_graphics_have_role_and_curve_fragments_marked(self):
        doc=ezdxf.new();doc.modelspace().add_linear_dim(base=(0,3),p1=(0,0),p2=(4,0)).render()
        entities=list(walk_entities(doc))
        self.assertTrue(entities)
        self.assertTrue(all(e._cp_role=='dimension' for e in entities))
        arc=doc.modelspace().add_arc((0,0),2,0,90)
        self.assertTrue(all(v['curve_approximation'] for v in entity_vectors(arc,lambda x,y:(x,y),.001)))

    def test_hatch_wall_contour_and_layer_dashes(self):
        doc=ezdxf.new();doc.layers.new('AXES',dxfattribs={'linetype':'DASHED'})
        doc.modelspace().add_line((0,0),(4,0),dxfattribs={'layer':'AXES'})
        h=doc.modelspace().add_hatch();h.paths.add_polyline_path([(0,0),(4,0),(4,.2),(0,.2)],is_closed=True)
        entities=list(walk_entities(doc))
        line=entity_vectors(entities[0],lambda x,y:(x,y),.001)[0]
        self.assertNotEqual(line['dashes'],'[] 0')
        contour=entity_vectors(entities[1],lambda x,y:(x,y),.001)[0]
        self.assertEqual(contour['type'],'quad')
        self.assertEqual(len(contour['points']),4)

    def test_cad_refresh_keeps_native_scale_and_reserves(self):
        from engines.plan_refresh import refresh_interior
        from engines.plan_walls import analyze_walls
        vectors=[{'type':'quad','points':[[0,0],[400,0],[400,20],[0,20]]}]
        before=analyze_walls(vectors,[],[],100,1,page_size_px=(600,600))
        page={'dpi':240,'geometry_coordinate_space':'image_px','vectors':vectors,'walls_analysis':before,
              'width_px':600,'height_px':600,'cad_import':{'diagnostics':[{'code':'XREF_UNRESOLVED'}]}}
        after=refresh_interior(page,[],100)
        self.assertEqual(after['pt_per_m'],100)
        self.assertEqual(after['walls'][0]['thickness_m'],.2)
        self.assertFalse(after['validation']['complete'])

    def test_empty_layout_is_not_flagged_but_populated_layout_is(self):
        doc=ezdxf.new();diagnostics=[]
        self.assertTrue(inventory(doc,[],diagnostics)['complete'])
        doc.layout().add_text('Présentation à contrôler')
        self.assertFalse(inventory(doc,[],diagnostics)['complete'])
        self.assertEqual(diagnostics[0]['code'],'PAPERSPACE_NOT_ANALYZED')

    def test_render_coordinates_and_native_units_match(self):
        doc=ezdxf.new();doc.header['$INSUNITS']=4
        doc.modelspace().add_lwpolyline([(0,0),(4000,0),(4000,200),(0,200)],close=True)
        result=process_dxf(drawing_bytes(doc))
        page=result['pages'][0]; image=Image.open(io.BytesIO(base64.b64decode(page['image_png_b64']))).convert('L')
        self.assertEqual(image.size,(page['width_px'],page['height_px']))
        v=next(v for v in page['vectors'] if v['type']=='quad')
        a,b=v['points'][:2]
        self.assertAlmostEqual(math.dist(a,b)/page['dxf_ratio']*page['unit_to_m'],4.,places=4)
        x,y=map(round,((a[0]+b[0])/2,(a[1]+b[1])/2))
        self.assertLess(min(image.crop((x-3,y-3,x+4,y+4)).getdata()),200)
        self.assertEqual(page['geometry_coordinate_space'],'image_px')
        self.assertTrue(base64.b64decode(result['analysis_pdf_b64']).startswith(b'%PDF'))


class DwgRegressions(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_magic_never_calls_converter(self):
        with patch.object(dwg_convert,'_local_dwg_to_dxf') as convert:
            with self.assertRaises(RuntimeError):await dwg_convert.dwg_to_dxf(b'not a DWG')
            convert.assert_not_called()

    async def test_local_converter_has_priority_and_no_external_fallback(self):
        with patch.dict(os.environ,{'ODA_FILE_CONVERTER':'/configured/oda','CLOUDCONVERT_API_KEY':'test-only'}), patch.object(dwg_convert,'_local_dwg_to_dxf',side_effect=RuntimeError('local fail')), patch.object(dwg_convert.httpx,'AsyncClient') as client:
            with self.assertRaisesRegex(RuntimeError,'local fail'):await dwg_convert.dwg_to_dxf(b'AC1032synthetic')
            client.assert_not_called()

    async def test_cloud_job_deleted_even_if_upload_fails(self):
        import types
        create=types.SimpleNamespace(status_code=200,is_success=True,json=lambda:{'data':{'id':'test-job','tasks':[{'name':'upload-dwg','result':{'form':{'url':'https://example.invalid/upload','parameters':{}}}}]}})
        fail=types.SimpleNamespace(status_code=500,is_success=False)
        client=types.SimpleNamespace(post=AsyncMock(side_effect=[create,fail]),delete=AsyncMock())
        cm=AsyncMock();cm.__aenter__.return_value=client
        with patch.dict(os.environ,{'ODA_FILE_CONVERTER':'','CLOUDCONVERT_API_KEY':'test-only','APS_DWG_ENABLED':'false'}),patch.object(dwg_convert.httpx,'AsyncClient',return_value=cm):
            with self.assertRaises(RuntimeError):await dwg_convert.dwg_to_dxf(b'AC1032synthetic')
        client.delete.assert_awaited_once()

    async def test_local_conversion_argument_array_and_result_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            executable=Path(temp)/'oda';executable.touch()
            def run(args,**kwargs):
                self.assertIsInstance(args,list); self.assertNotIn('shell',kwargs)
                (Path(args[2])/'plan.dxf').write_bytes(b'0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n')
            with patch.dict(os.environ,{'ODA_FILE_CONVERTER':str(executable)}),patch('subprocess.run',side_effect=run):
                self.assertIn(b'SECTION',await dwg_convert.dwg_to_dxf(b'AC1032synthetic'))
