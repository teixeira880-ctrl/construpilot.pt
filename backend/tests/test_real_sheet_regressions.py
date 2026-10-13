"""Synthetic regressions derived from real sheets; no private project PDF in git."""
import ast
import math
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest

from engines.plan_page_context import initial_pdf_calibrations, page_context, scale_denominators
from engines.plan_processor import process_pdf, _detect_level_from_text, _detect_scale_from_text
from engines.plan_refresh import extract_page_geometry, refresh_interior
from engines.plan_vector_pdf import extract_vector_dimensions
from engines.plan_cotes import dims_from_pdf_vectors, check_dimensions


def pdf(*texts):
    with pymupdf.open() as doc:
        for text in texts:
            page = doc.new_page(width=600, height=400)
            page.insert_text((30, 25), text)
            # One actual 4 m cote at 1:50: insufficient for self calibration.
            x0, x1, y = 80, 80 + 4 * 1000 / 50 * 72 / 25.4, 160
            page.draw_line((x0, y), (x1, y))
            page.draw_line((x0, y-15), (x0, y+15))
            page.draw_line((x1, y-15), (x1, y+15))
            page.insert_text(((x0+x1)/2-10, y-4), "4.00", fontsize=10)
        return doc.tobytes()


@pytest.mark.parametrize("text,expected", [("1:50, 1:200", [50,200]), ("1:50\n1/50",[50]), ("13/09/2024", []), ("1:10000",[10000])])
def test_all_declared_scales(text, expected):
    assert scale_denominators(text) == expected
    assert _detect_scale_from_text(text) == (expected[0] if len(expected)==1 else None)


@pytest.mark.parametrize("text", ["PLAN R+1\nPLAN DE RDC", "PLAN R-1 ET RDC", "R+1\nR+2", "Sous-sol\nRDC"])
def test_conflicting_levels_are_not_silently_assigned(text):
    assert _detect_level_from_text(text) is None
    context = page_context(text)
    assert context['level_index'] is None
    assert len(context['level_candidates']) > 1
    assert context['reading_warnings']


def test_negative_and_multi_digit_levels():
    assert _detect_level_from_text('PLAN R-2') == (-2, 'R-2')
    assert _detect_level_from_text('PLAN R+12') == (12, 'R+12')


def test_declared_scale_reaches_import_and_refresh():
    data = pdf('PLAN RDC\n1:50')
    result = process_pdf(data, render_dpi=72)
    page = result['pages'][0]
    assert page['pdf_dimensions']
    assert page['pdf_vector_scale']['scale_source'] == 'declared'
    assert page['pdf_dimensions'][0]['value_m'] == 4
    assert page['pdf_dimensions'][0]['measured_m'] == pytest.approx(4, abs=.001)
    refreshed = extract_page_geometry(data, 0, 1)
    assert refreshed['pdf_dimensions'] == page['pdf_dimensions']
    assert 'level_index' not in refreshed  # do not erase a manually assigned level
    cal = initial_pdf_calibrations(result, 'test')['0']
    assert cal['method'] == 'auto_pdf_scale'
    assert cal['confidence'] == .75


def test_each_page_gets_its_own_scale():
    result = process_pdf(pdf('PLAN RDC\n1:50', 'PLAN R+1\n1:100'), render_dpi=72)
    assert result['detected_scale_denominator'] is None
    cal = initial_pdf_calibrations(result, 'test')
    assert cal['0']['pixels_per_meter'] / cal['1']['pixels_per_meter'] == pytest.approx(2, abs=.0001)
    assert cal['0']['scale_denominator'] == 50
    assert cal['1']['scale_denominator'] == 100


def resized_pdf(factor):
    with pymupdf.open() as doc:
        page = doc.new_page(width=1000, height=500)
        page.insert_text((30, 25), 'PLAN RDC\n1:25')
        for y, meters in [(100, 5.2), (220, 4.7), (340, 2.7)]:
            x0, x1 = 50, 50 + meters * 1000 / 25 * 72 / 25.4 * factor
            page.draw_line((x0, y), (x1, y))
            page.draw_line((x0, y-15), (x0, y+15))
            page.draw_line((x1, y-15), (x1, y+15))
            page.insert_text(((x0+x1)/2-10, y-4), f'{meters:.2f}', fontsize=10)
        return doc.tobytes()


@pytest.mark.parametrize('factor', [.7, 1.4])
def test_resized_pdf_blocks_printed_scale_at_import_and_refresh(factor):
    data = resized_pdf(factor)
    parsed = process_pdf(data, render_dpi=72)
    assert not initial_pdf_calibrations(parsed, 'test')
    for page in [parsed['pages'][0], extract_page_geometry(data, 0, 1)]:
        assert page['auto_calibration_blocked']
        assert page['pdf_vector_scale']['declared_scale_conflict']
        assert page['pdf_vector_scale']['observed_to_declared_ratio'] == pytest.approx(factor, abs=.001)
        assert page['pdf_vector_scale']['pt_per_m'] is None
        assert len(page['pdf_dimensions']) == 3
        assert all(d['unverified'] for d in page['pdf_dimensions'])
        assert not page['pdf_elements']
        assert not page['pdf_auto_spans']
        assert not page['walls_analysis']['walls']
        assert any('cartouche' in w for w in page['reading_warnings'])


def test_consistent_printed_scale_remains_available():
    parsed = process_pdf(resized_pdf(1), render_dpi=72)
    assert not parsed['pages'][0]['auto_calibration_blocked']
    assert initial_pdf_calibrations(parsed, 'test')['0']['scale_denominator'] == 25


def test_mixed_scales_do_not_calibrate_or_infer_rooms_even_after_refresh():
    data = pdf('PLAN DU RDC\n1:200\nCOUPE SUR RAMPE\n1:50')
    result = process_pdf(data, render_dpi=72)
    page = result['pages'][0]
    assert page['auto_calibration_blocked']
    assert not initial_pdf_calibrations(result, 'test')
    assert page['pdf_dimensions'] == []
    assert not page['walls_analysis']['validation']['complete']
    assert not refresh_interior(page, [], 100)['walls']
    assert extract_page_geometry(data, 0, 1)['auto_calibration_blocked']


@pytest.mark.parametrize('title', ['COUPE AA SUR BATIMENT A', 'FACADES BAT D', 'NOMENCLATURE DES BAIES'])
def test_non_floor_drawings_do_not_produce_false_interior_walls(title):
    page = process_pdf(pdf(title+'\n1:50'), render_dpi=72)['pages'][0]
    assert page['interior_analysis_blocked']
    assert not page['walls_analysis']['walls']
    assert not refresh_interior(page, [], 100)['walls']
    assert not page['pdf_elements']
    assert not page['pdf_auto_spans']


def test_facade_and_fire_notes_do_not_block_a_floor_plan():
    page = page_context('PLAN RDC\nFACADE AVEUGLE\nCoupe-feu 1h\n1:50')
    assert not page['interior_analysis_blocked']


@pytest.mark.parametrize('title,kind', [
    ('Coffrages - Fondation', 'structural_plan'),
    ('Coffrages - 1\nPH VS\nPH RDC\nPH R+1', 'structural_plan'),
    ('PLAN DE COFFRAGE DU RDC', 'structural_plan'),
    ('Armature Inférieure\nArmature Supérieure', 'structural_detail'),
    ('CHAINE POTEAUX 24\nCADRES', 'structural_detail'),
    ('PLANCHER\nPoutrelles Precontraintes', 'structural_detail'),
    ('Arche Dalle EC2 Version 2023\nTreillis soude', 'structural_detail'),
    ('RECAPITULATIF DES SECTIONS ET FERRAILLAGE DES LINTEAUX', 'structural_schedule'),
    ('NOTE DE CALCUL', 'calculation_note'),
])
def test_structural_sheets_do_not_create_interior_walls(title, kind):
    data = pdf(title+'\n1:50')
    page = process_pdf(data, render_dpi=72)['pages'][0]
    assert page['view_kind'] == kind
    assert page['interior_analysis_blocked']
    assert page['reading_warnings']
    assert not page['walls_analysis']['walls']
    assert not page['pdf_elements']
    assert not page['pdf_auto_spans']
    assert not refresh_interior(page, [], 100)['walls']
    assert extract_page_geometry(data, 0, 1)['interior_analysis_blocked']
    if kind in ('structural_plan', 'structural_detail'):
        assert page['pdf_dimensions'][0]['value_m'] == 4
        assert initial_pdf_calibrations({'pages':[page]}, 'test')
    else:
        assert not page['pdf_dimensions']
        assert not initial_pdf_calibrations({'pages':[page]}, 'test')


def test_raster_page_has_explicit_reading_gap():
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=300)
        picture = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
        picture.clear_with(255)
        page.insert_image(page.rect, pixmap=picture)
        result = process_pdf(doc.tobytes(), render_dpi=72)
    page = result['pages'][0]
    assert page['view_kind'] == 'text_unavailable'
    assert page['auto_calibration_blocked']
    assert page['interior_analysis_blocked']
    assert any('OCR' in w for w in page['reading_warnings'])
    assert not initial_pdf_calibrations(result, 'test')


def test_structural_terms_in_a_floor_note_do_not_classify_it_as_a_detail():
    context = page_context('PLAN RDC\nVoir plan de coffrage et ferraillage du BET\n1:50')
    assert context['view_kind'] == 'floor_plan'
    assert not context['interior_analysis_blocked']


def test_no_dimensions_must_report_zero_matches():
    v = [{'type':'line','p1':[0,50],'p2':[100,50]},
         {'type':'line','p1':[0,40],'p2':[0,60]},
         {'type':'line','p1':[100,40],'p2':[100,60]}]
    d = extract_vector_dimensions(v,[{'text':'4.00','x':40,'y':40,'w':20,'h':8}],1)
    assert not d['dimensions']
    assert d['matched'] == 0
    assert d['candidate_matches'] == 1


@pytest.mark.parametrize('angle', [1.02, -12, 32])
def test_rotated_dimension_is_measured_in_its_own_frame(angle):
    c,s = math.cos(math.radians(angle)),math.sin(math.radians(angle))
    def rotate(p):
        return [c*p[0]-s*p[1]+100, s*p[0]+c*p[1]+100]
    v = [{'type':'line','p1':rotate(a),'p2':rotate(b),'stroke_color':[.2,.4,.6]}
         for a,b in [([0,50],[200,50]),([0,30],[0,70]),([200,30],[200,70])]]
    # A nearby furniture line in a different ink must not replace the cote.
    v.append({'type':'line','p1':rotate([0,46]),'p2':rotate([90,46]),'stroke_color':[0,0,0]})
    center=rotate([100,41])
    t={'text':'4.00','x':center[0]-10,'y':center[1]-4,'w':20,'h':8,'direction':[c,s],'color':0x336699}
    result=extract_vector_dimensions(v,[t],1,50)
    assert len(result['dimensions']) == 1
    d=result['dimensions'][0]
    assert d['measured_m'] == pytest.approx(4, abs=.001)
    assert [d['x1'],d['y1']] == pytest.approx(rotate([0,50]), abs=.02)
    assert [d['x2'],d['y2']] == pytest.approx(rotate([200,50]), abs=.02)


@pytest.mark.parametrize("measured", [1, 4])
def test_uncertain_pdf_attachment_is_not_reported_as_a_proven_error(measured):
    d={'x1':0,'y1':0,'x2':100,'y2':0,'value_m':4,'measured_m':measured,'unverified':True}
    report=check_dimensions(dims_from_pdf_vectors([d]),100,2,3,600,400)
    assert report['items'][0]['status']=='nd'
    assert report['items'][0]['confidence'] < 1


def test_old_multi_page_global_scale_is_not_reused_on_unknown_pages():
    assert not initial_pdf_calibrations({'detected_scale_denominator':50,'pages':[{'index':0},{'index':1}]},'test')


def test_import_route_calls_page_scoped_calibration():
    path = Path(__file__).parents[1]/'routes/plans_crud.py'
    node = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name=='_auto_calibrate_pages')
    ns = {'_now':lambda:'test'}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(path),'exec'),ns)
    parsed = {'kind':'pdf','pages':[{'index':0,'auto_calibration_blocked':True}], 'detected_scale_denominator':50}
    with patch('engines.plan_page_context.initial_pdf_calibrations', wraps=initial_pdf_calibrations) as helper:
        assert ns['_auto_calibrate_pages'](parsed) == {}
    helper.assert_called_once_with(parsed, 'test')
