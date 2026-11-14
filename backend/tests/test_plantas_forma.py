"""14/11: plantas redistribuídas quando a casa muda no Estúdio — incluindo casas em L e em T (nenhuma divisão no recorte)."""
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from engines.urbanismo_pt import volumes as V
from engines.urbanismo_pt.auto import plantas as PL, programa as PG

VOL = {"shape": "rectangle", "footprint_l_m": 13, "footprint_w_m": 10, "levels": 2, "storey_h_m": 3, "setback_side_m": 4,
       "setback_front_m": 6, "plot_l_m": 40, "plot_w_m": 40}


def _base():
    prog = PG.programa("T3", 2, False, 0)
    pl = PL.distribuir(VOL, prog, "frente", "esquerda")
    assert pl["ok"], pl
    return pl


def _dentro(vol, pl):
    casa = unary_union([Polygon(p["pts"]) for p in V.building_polygons(vol) if not p["annexe"]]).buffer(0.01)
    return all(casa.contains(box(c["x0"], c["y0"], c["x1"], c["y1"])) for p in pl["pisos"] for c in p["compartimentos"])


def test_redistribui_maior_e_em_l_e_t():
    base = _base()
    for novo in ({**VOL, "footprint_l_m": 15}, {**VOL, "shape": "l", "footprint_l_m": 16, "footprint_w_m": 12},
                 {**VOL, "shape": "t", "footprint_l_m": 16, "footprint_w_m": 13, "wing_l_m": 9}):
        area_nova = V.union_area([p for p in V.building_polygons(novo) if not p["annexe"]])
        x0, y0, x1, y1 = base["casa_rect"]
        prog = PL.programa_das_plantas(base, "frente", area_nova / ((x1 - x0) * (y1 - y0)))
        nomes0 = sorted(c["nome"] for p in base["pisos"] for c in p["compartimentos"])
        pl = PL.distribuir(novo, prog, "frente", "esquerda")
        assert pl["ok"], (novo["shape"], pl.get("motivo"))
        assert sorted(c["nome"] for p in pl["pisos"] for c in p["compartimentos"]) == nomes0
        assert _dentro(novo, pl), f"divisão fora da casa ({novo['shape']})"


def test_t_estreito_diz_que_nao_cabe():
    base = _base()
    novo = {**VOL, "shape": "t", "footprint_l_m": 16, "footprint_w_m": 13, "wing_l_m": 4}
    pl = PL.distribuir(novo, PL.programa_das_plantas(base, "frente", 1.2), "frente", "esquerda")
    assert not pl["ok"] and "não cabem" in pl["motivo"]


def test_volume_aceita_forma_minuscula():
    import os
    for k in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
        os.environ.setdefault(k, "x" if k != "MONGO_URL" else "mongodb://localhost:27017")
    from routes.urbanismo import VolumeIn
    assert VolumeIn(shape="l").shape == "l" and VolumeIn(shape="T").shape == "T"
