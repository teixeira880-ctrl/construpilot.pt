"""Cortes/alçados à escala com cotas NGF absolutas (23/11/2026, dossier Amarante ~304 m NGF).

Antes da correção, sheet_sections/sheet_elevations usavam as cotas absolutas como altura do
quadro → escala 1:1000 e desenho ilegível. Agora desenham relativo ao pavimento."""
import io
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from engines.bet_geo import drawings
from engines.bet_geo.model import Building, Wall
from engines.bet_geo import structure

_REAL_FRAME = drawings.Frame


def _building(fl: float) -> Building:
    b = Building(footprint=box(0, 0, 24, 10), floor_level=fl, roof_level=fl + 3.06)
    for a, bq in [((0, 0), (24, 0)), ((24, 0), (24, 10)), ((24, 10), (0, 10)), ((0, 10), (0, 0))]:
        b.walls.append(Wall(a, bq, 0.20, "alvenaria", True))
    return b


def _render(monkeypatch, fl: float) -> list[int]:
    from reportlab.pdfgen import canvas as rl_canvas
    scales = []

    class SpyFrame(_REAL_FRAME):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            scales.append(self.scale)

    monkeypatch.setattr(drawings, "Frame", SpyFrame)
    b = _building(fl)
    R = structure.design(b)
    slab_h = 0.20
    env = SimpleNamespace(hsp=2.70)
    sol = SimpleNamespace(etics=100, roof=120, floor=100, uw=1.4, g=0.5,
                          U={"parede": 0.4, "cobertura": 0.3, "pavimento": 0.35})
    esp = {"env": env, "solution": sol}
    meta = {"obra": "teste", "local": "teste", "logo": None}
    c = rl_canvas.Canvas(io.BytesIO())
    drawings.sheet_sections(c, b, R, esp, meta, slab_h)
    drawings.sheet_elevations(c, b, esp, meta, slab_h)
    assert scales, "nenhum Frame criado"
    return scales


def test_cotas_ngf_absolutas_ficam_a_escala(monkeypatch):
    scales = _render(monkeypatch, 304.60)
    assert max(scales) <= 200, f"escala ilegível com cotas NGF: {scales}"


def test_cotas_relativas_inalteradas(monkeypatch):
    s_rel = _render(monkeypatch, 0.0)
    s_ngf = _render(monkeypatch, 304.60)
    assert s_rel == s_ngf, f"escala deve ser independente do datum: {s_rel} vs {s_ngf}"
