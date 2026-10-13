"""Régressions locales, sans base de données ni appel réseau.

Exécution depuis backend : python -m unittest discover -s tests -p 'test_plan_*regressions.py' -v
"""
import copy
import math
import unittest
from pathlib import Path

import pymupdf

from engines.plan_refresh import extract_page_geometry, refresh_interior
from engines.plan_symbols import classify_by_label, label_walls
from engines.plan_vector_pdf import _segments, pdf_lines, pdf_text_blocks
from engines.plan_walls import _bands, analyze_walls, closed_bands, detect_walls, merged_lines, validate

FIXTURES = Path(__file__).parent / 'fixtures'
PX = 200 / 72


def synthetic_page():
    data = (FIXTURES / 'synth_walls_1_50.pdf').read_bytes()
    page = extract_page_geometry(data, 0, PX)
    with pymupdf.open(stream=data, filetype='pdf') as doc:
        page.update(dpi=200, width_px=doc[0].rect.width*PX, height_px=doc[0].rect.height*PX)
    return page


def report_items(page):
    return [{**d, 'index': i+101, 'source': 'pdf', 'indicated_m': d['value_m']}
            for i, d in enumerate(page['pdf_dimensions'])]


def wall(name, x, end, low=0, high=100):
    return dict(wall_id=name, orientation='vertical', pos_1=x, pos_2=end, axis_pos=(x+end)/2, lo=low, hi=high)


class GeometryRegressionTests(unittest.TestCase):
    def test_quad_and_rectangle_retain_all_four_edges(self):
        rect = dict(type='rect', x=10, y=20, w=5, h=100)
        quad = dict(type='quad', points=[[10,20],[15,20],[15,120],[10,120]])
        h1,v1,_ = _segments([rect]); h2,v2,_ = _segments([quad])
        self.assertEqual(sorted(h1), sorted(h2)); self.assertEqual(sorted(v1), sorted(v2))
        self.assertEqual((len(h1),len(v1)),(2,2))
        self.assertEqual(len(closed_bands([quad],25)),1)
        self.assertEqual(closed_bands([dict(type='quad',points=[[10,20],[15,21],[20,121],[15,120]])],25),[])

    def test_hatches_and_dashed_axes_do_not_split_faces(self):
        vectors = [dict(type='line',p1=[x,0],p2=[x,200],paint_type='s') for x in (0,20)]
        vectors += [dict(type='line',p1=[10,0],p2=[10,200],paint_type='s',dashes='[4 2] 0'),
                    dict(type='line',p1=[8,0],p2=[8,200],paint_type='f')]
        h,v = merged_lines(vectors)
        self.assertEqual([x[0] for x in v],[0,20])
        self.assertEqual(len(detect_walls(h,v,100)),1)

    def test_one_written_thickness_does_not_exclude_other_thicknesses(self):
        lines = [(0,0,300),(13,0,300),(200,0,300),(220,0,300),(400,0,300),(430,0,300)]
        cote = dict(orientation='h',p1=[0,-20],p2=[13,-20],value_m=.13,index=1)
        found = detect_walls([],lines,100,[cote])
        self.assertEqual(sorted(w['thickness_m'] for w in found),[.13,.20,.30])

    def test_known_six_cells_have_twelve_face_to_face_dimensions(self):
        r = synthetic_page()['walls_analysis']
        self.assertEqual(r['stats']['walls'],7)
        self.assertEqual(r['stats']['measurements'],12)
        self.assertEqual(r['stats']['rows_closed'],5)
        self.assertEqual(r['coverage']['confirmed'],6)
        self.assertEqual(sorted({round(m['geometric_dimension_m'],2) for m in r['interior_measurements']}),[3.,3.6,4.,4.4])
        self.assertTrue(r['validation']['complete'])
        self.assertFalse(any(w['is_post'] for w in r['walls']))

    def test_one_unconfirmed_dimension_blocks_completion(self):
        r = synthetic_page()['walls_analysis']
        r['interior_measurements'][0]['status']='probable'
        self.assertFalse(validate(r)['complete'])
        r = synthetic_page()['walls_analysis']
        r['interior_measurements'] = [m for m in r['interior_measurements'] if m['direction']=='horizontal']
        r.pop('coverage')
        self.assertFalse(validate(r)['complete'])

    def test_partial_refend_only_blocks_its_actual_extent(self):
        a,b,c = wall('A',0,20),wall('B',400,420),wall('C',200,220,0,30)
        spans = _bands([a,b,c],'vertical',100)
        ab = [s for s in spans if s['from']['wall_id']=='A' and s['to']['wall_id']=='B']
        self.assertEqual([(s['lo'],s['hi']) for s in ab],[(30,100)])
        post = {**c,'wall_id':'P','is_post':True}
        ab = _bands([a,b,post],'vertical',100)
        self.assertEqual([(s['lo'],s['hi']) for s in ab],[(0,100)])

    def test_edit_and_ignore_update_interior_without_moving_faces(self):
        page=synthetic_page(); items=report_items(page)
        old=refresh_interior(page,items)
        target=next(m for m in old['interior_measurements'] if m['written_dimension_m']==4.)
        item=next(i for i in items if i['index']==target['written_cote_index'])
        item['indicated_m']=4.02
        new=refresh_interior(page,items)
        m=next(m for m in new['interior_measurements'] if m['measurement_id']==target['measurement_id'])
        self.assertEqual(m['written_dimension_m'],4.02)
        self.assertAlmostEqual(m['geometric_dimension_m'],4.,places=3)
        self.assertEqual(m['coordinates'],target['coordinates'])
        self.assertEqual(m['status'],'to_confirm')
        self.assertFalse(new['validation']['complete'])
        item['ignored']=True
        new=refresh_interior(page,items)
        m=next(m for m in new['interior_measurements'] if m['measurement_id']==target['measurement_id'])
        self.assertIsNone(m['written_dimension_m'])
        self.assertFalse(new['validation']['complete'])
        self.assertTrue(all(c['index']!=item['index'] for c in new['cotes']))

    def test_changed_exterior_cote_reopens_closure(self):
        page=synthetic_page(); items=report_items(page)
        for item in items:
            if item['indicated_m']==12: item['indicated_m']=12.10
        r=refresh_interior(page,items)
        rows=[r for r in r['closure_equations'] if r['direction']=='horizontal']
        self.assertTrue(rows)
        self.assertTrue(all(r['status']=='open' and abs(r['difference_m']-.10)<.001 for r in rows))

    def test_cached_contours_recompute_thickness_at_new_scale(self):
        vectors=[dict(type='rect',x=10,y=10,w=10,h=200),dict(type='rect',x=210,y=10,w=10,h=200)]
        old=analyze_walls(vectors,[],[],50,1)
        original=copy.deepcopy(old)
        fresh=analyze_walls(vectors,[],[],100,1)
        cached=analyze_walls([],[],[],100,1,segments=old['segments'])
        self.assertEqual(cached['walls'],fresh['walls'])
        self.assertEqual([w['thickness_m'] for w in cached['walls']],[.1,.1])
        self.assertEqual(old,original)

    def test_invalid_scale_never_validates(self):
        for value in (None,0,-1,float('nan'),float('inf')):
            r=analyze_walls([],[],[],value,1)
            self.assertFalse(r['validation']['complete'])
            self.assertEqual(r['stats']['measurements'],0)
        self.assertFalse(refresh_interior(synthetic_page(),[],0)['validation']['complete'])

    def test_old_truncated_vectors_require_original(self):
        page=dict(dpi=200,vectors_truncated=True,vectors=[],walls_analysis={'pt_per_m':50})
        r=refresh_interior(page,[])
        self.assertFalse(r['validation']['complete'])
        self.assertIn('PDF original',r['validation']['failed_checks'][0])

    def test_rotated_text_and_vectors_share_display_coordinates(self):
        for rotation in (0,90,180,270):
            with pymupdf.open() as doc:
                p=doc.new_page(width=300,height=500)
                p.draw_line((40,60),(100,60));p.insert_text((40,55),'4.00')
                p.set_rotation(rotation)
                v=next(v for v in pdf_lines(p) if v['type']=='line')
                expected=pymupdf.Point(40,60)*p.rotation_matrix
                self.assertAlmostEqual(v['p1'][0],expected.x);self.assertAlmostEqual(v['p1'][1],expected.y)
                sp=p.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
                rect=pymupdf.Rect(sp['bbox'])*p.rotation_matrix;t=pdf_text_blocks(p)[0]
                self.assertAlmostEqual(t['x'],rect.x0);self.assertAlmostEqual(t['y'],rect.y0)

    def test_section_is_not_a_semelle_and_labels_are_dpi_independent(self):
        self.assertEqual(classify_by_label('50x30')[0],"Section d'ouvrage")
        results=[]
        for px in (1,PX,4):
            w={**wall('A',100,120,100,400),'source':'closed_contour'}
            label_walls([w],[dict(text='50x30',x=102,y=200,w=14,h=10)],px,100)
            results.append((w['labels'],w['ouvrage_class']))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])
        self.assertEqual(results[0][0],['50x30'])

    def test_houilles_quadrilaterals_kept_but_ambiguity_remains_blocking(self):
        with pymupdf.open(FIXTURES/'houilles_plan.pdf') as doc:
            expected=sum(item[0]=='qu' for d in doc[0].get_drawings() for item in d['items'])
            actual=sum(v['type']=='quad' for v in pdf_lines(doc[0]))
        self.assertEqual(expected,63);self.assertEqual(actual,expected)
        page=extract_page_geometry((FIXTURES/'houilles_plan.pdf').read_bytes(),0,PX)
        r=page['walls_analysis']
        # This structural sheet was resized to 70%: its printed 1:25 is unsafe.
        # Keep the 63 raw quadrilaterals, but do not turn them into measured walls.
        self.assertTrue(page['auto_calibration_blocked'])
        self.assertTrue(page['pdf_vector_scale']['declared_scale_conflict'])
        self.assertAlmostEqual(page['pdf_vector_scale']['observed_to_declared_ratio'],.7,places=3)
        self.assertEqual(r['walls'],[])
        self.assertFalse(r['validation']['complete'])
        self.assertFalse(any(w['is_post'] for w in r['walls']))


if __name__=='__main__':
    unittest.main()
