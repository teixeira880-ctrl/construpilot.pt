"""13/11 (implantação de Valpaços): DWG lido no servidor (LibreDWG), bloco perdido longe não espreme a planta."""
import io

import ezdxf

from engines import dwg_local, plan_dxf


def test_far_away_block_does_not_squeeze_the_plan():
    d = ezdxf.new(units=6)
    m = d.modelspace()
    for i in range(30):
        m.add_lwpolyline([(i * 3, 0), (i * 3 + 2, 0), (i * 3 + 2, 2), (i * 3, 2)], close=True)
    m.add_line((-100000, 0), (-99999, 0))                    # objeto perdido a 100 km
    diags = []
    focus = plan_dxf._focus_by_density(d, (-100000, 0, 92, 2), diags)
    assert focus[0] > -100 and diags and diags[0]["code"] == "EXTENTS_FOCUSED_ON_DENSITY"


def test_libredwg_bundled_with_the_repo():
    """O deploy não instala pacotes npm do backend: o LibreDWG vai no repositório (tools/dwg/vendor)."""
    assert (dwg_local.TOOL / "vendor" / "libredwg-web" / "wasm" / "libredwg-web.wasm").is_file()
    assert (dwg_local.TOOL / "vendor" / "libredwg-web" / "js" / "libredwg-web.js").is_file()


def test_mm_declared_but_drawn_in_metres_is_corrected():
    """Valpaços: INSUNITS = mm mas coordenadas em metros → sem correção, quantidades 1000× pequenas."""
    diags = []
    u = plan_dxf._plausible_units({"name": "mm", "unit_to_m": 0.001, "source": "INSUNITS"}, (68800, 215500, 69100, 215960), diags)
    assert u["name"] == "m" and u["unit_to_m"] == 1.0 and diags[0]["code"] == "UNITS_CORRECTED_BY_EXTENTS"
    ok = plan_dxf._plausible_units({"name": "mm", "unit_to_m": 0.001, "source": "INSUNITS"}, (0, 0, 12000, 9000), [])
    assert ok["name"] == "mm"                                   # moradia de 12 m desenhada em mm: não mexe
    user = plan_dxf._plausible_units({"name": "mm", "unit_to_m": 0.001, "source": "user"}, (0, 0, 300, 400), [])
    assert user["name"] == "mm"                                 # escolha do utilizador: nunca alterada


def test_dense_plan_still_reads_walls_on_architecture_layers():
    import ezdxf as _e
    d = _e.new(units=6)
    m = d.modelspace()
    for i in range(160000):                                     # paisagismo denso
        m.add_line((i % 400, i // 400), (i % 400 + 0.3, i // 400), dxfattribs={"layer": "MC_PAISAGISMO"})
    for y in (0, 0.2, 8, 8.2):
        m.add_line((0, y), (12, y), dxfattribs={"layer": "A-PAREDES"})
    for x in (0, 0.2, 11.8, 12):
        m.add_line((x, 0), (x, 8.2), dxfattribs={"layer": "A-PAREDES"})
    buf = io.StringIO(); d.write(buf)
    p = plan_dxf.process_dxf(buf.getvalue().encode(), "dense.dxf", "m")
    codes = [x["code"] for x in p["cad_import"].get("diagnostics", [])]
    assert "DXF_NOISE_LAYERS_SKIPPED_FOR_WALLS" in codes
    assert "análise das paredes não tentada" not in str(p["pages"][0]["walls_analysis"]["validation"])
