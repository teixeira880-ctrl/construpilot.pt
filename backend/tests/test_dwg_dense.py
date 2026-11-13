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
