from __future__ import annotations

import asyncio
import math
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pymupdf
import pytest
from shapely.geometry import Point

from engines.bet_core import foundation_sheets, geometry_review, strip_foundations as strips
from test_bet_geometry_review import EXPECTED, make_pdf


def example_sheet():
    return [strips.MARKER, "tipo=ensaio", "applicability=paredes_continuas_centradas_no_contorno",
            "fonte_geotecnia=Hipótese de ensaio, sem prospeção. Limites brutos assumidos.",
            "fonte_reacoes=Reações lineares fictícias para testar os seis tramos.",
            "largura_parede_m=.20", "profundidade_m=.90", "recobrimento_mm=50", "agregado_mm=20",
            "fck_mpa=25", "fyk_mpa=500", "gamma_c=1.50", "gamma_s=1.15", "alpha_cc=.85", "alpha_ct=1.0",
            "gamma_g=1.35", "peso_betao_kn_m3=25", "aterro_kpa=10", "qrd_kpa=180", "qlim_els_kpa=125",
            "tramo=0;0;6;0;72;1.4;50;1.0", "tramo=6;0;6;5;60;0.8;42;0.5",
            "tramo=6;5;12;5;54;-1.1;39;-0.8", "tramo=12;5;12;10;64;1.4;46;0.9",
            "tramo=12;10;0;10;86;1.7;62;1.1", "tramo=0;10;0;0;80;-1.5;58;-1.0"]


def sheet_pdf(lines):
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        for i, line in enumerate(lines):
            page.insert_text((42, 44+21*i), line, fontsize=10)
        return pdf.tobytes()


@pytest.fixture
def source():
    return geometry_review.inspect(make_pdf(), "Moradia em L com 180 m²")


@pytest.fixture
def inputs():
    return strips.read_inputs([("ficha.pdf", sheet_pdf(example_sheet()))])


def test_l_footings_use_the_verified_outline_and_roundtrip_pdf_dxf(source, inputs, tmp_path):
    design = strips.calculate(source, inputs)
    assert len(design["edges"]) == len(design["checks"]) == 6
    assert design["outline"].area == 90
    assert design["outline"].length == 44
    assert set(design["outline"].exterior.coords) == set(EXPECTED)
    assert design["band"].area == pytest.approx(44 * design["width_mm"] / 1000)
    assert not design["band"].covers(Point(9, 2.5))
    assert design["band"].covers(Point(6, 5))
    assert design["execution_verified"] is False
    for check in design["checks"]:
        assert 0 < check["q_min_ed"] <= check["q_ed"] <= 180
        assert 0 < check["q_min_ser"] <= check["q_ser"] <= 125
        assert check["as_prov"] >= check["as_req"]
        assert check["l_bd_mm"] <= check["l_av_mm"]
        assert check["v_ed"] <= check["v_rd"]
    folder = tmp_path
    path = folder / "fundações.pdf"
    foundation_sheets.write_pdf(design, path)
    foundation_sheets.write_cad(design, folder / "fundações.zip")
    with pymupdf.open(path) as pdf:
        assert len(pdf) == 3
        assert all("ENSAIO COM DADOS FICTÍCIOS" in page.get_text() for page in pdf)
        assert all("REVISÃO ESTRUTURAL" in page.get_text() for page in pdf)
        for tramo in (f"S{i:02d}" for i in range(1, 7)):
            assert tramo in pdf[0].get_text() and tramo in pdf[2].get_text()


def test_moments_and_shear_against_independent_numerical_integration(source, inputs):
    design = strips.calculate(source, inputs)
    b, h = design["width_mm"]/1000, design["height_mm"]/1000
    phi = design["bar_mm"]
    overhang = (b - inputs.values["largura_parede_m"])/2
    depth = h - (inputs.values["recobrimento_mm"] + phi/2)/1000
    for edge, row in zip(design["edges"], design["checks"]):
        action = inputs.actions[strips._edge_key(*edge)]
        # Pressure at x relative to the centreline. Integrate both sides of the
        # wall separately. For the shear cut use only the loaded length beyond d.
        q = lambda x: action.ned / b + (h*25 + 10)*1.35 + 12*action.med*x/b**3
        step = overhang / 10000
        for field, limit in (("m_ed", overhang), ("v_ed", max(0.0, overhang-depth))):
            checks = []
            for side in (-1, 1):
                checks.append(sum(q(side*(b/2-(j+.5)*step)) * step * (overhang-(j+.5)*step if field == "m_ed" else 1)
                                  for j in range(round(limit/step))))
            assert row[field] == pytest.approx(max(checks), abs=.003)
        assert math.pi * phi**2 / 4 * 10 / design["spacing_mm"] == pytest.approx(row["as_prov"])


@pytest.mark.parametrize("extension", ["qrd_kpa=NaN", "altura_lote=1", "tramo=6;0;0;0;72;1.4;50;1.0"])
def test_invalid_input_fails_before_drawing(extension):
    with pytest.raises(strips.InputError):
        strips.read_inputs([("ficha.pdf", sheet_pdf([*example_sheet(), extension]))])


def test_absent_input_uses_geometry_only_and_bad_reactions_never_produce_a_sheet(source, inputs):
    assert strips.read_inputs(make_pdf()) is None
    actions = dict(inputs.actions)
    actions.pop(next(iter(actions)))
    with pytest.raises(strips.InputError, match="coordenadas"):
        strips.calculate(source, replace(inputs, actions=actions))
    with pytest.raises(strips.InputError, match="Nenhuma secção"):
        strips.calculate(source, replace(inputs, values={**inputs.values, "qrd_kpa": 10}))


@pytest.mark.parametrize("include_sheet", [True, False])
def test_assistant_saves_the_checked_drawings_and_never_marks_them_for_execution(monkeypatch, include_sheet):
    from engines import house_pbr
    from engines.bet_core import assistant_tool

    docs = make_pdf()
    if include_sheet:
        docs.append(("ficha.pdf", sheet_pdf(example_sheet())))
    job_db = SimpleNamespace(bet_study_jobs=SimpleNamespace(find_one=AsyncMock(return_value=None)))
    step = AsyncMock()

    async def store(db, uid, cid, request_id, kind, path, label):
        assert path.stat().st_size > 0
        return {"name": path.name, "kind": kind, "label": label}

    monkeypatch.setattr(house_pbr, "dossier_renders", lambda *args: [])
    monkeypatch.setattr(assistant_tool, "_store", store)
    preserved = asyncio.run(assistant_tool._preserve_geometry(job_db, "job", "uid", "cid", "rid", docs,
                                                            "Moradia em L com 180 m²", "PT", step))
    assert preserved is True
    done = next(c.kwargs for c in step.await_args_list if c.kwargs.get("status") == "done")
    assert done["geometry_verified"] is True
    assert done["execution_verified"] is False
    assert done["foundation_study"]["status"] == ("preliminary" if include_sheet else "inputs_required")
    generated = {a["name"] for a in done["artifacts"]}
    assert {"Plantas_de_origem.pdf", "Contornos_cotados.pdf", "DXF.zip"} <= generated
    for name in ("Fundacoes_Armaduras_em_L.pdf", "Fundacoes_em_L_DXF.zip"):
        assert (name in generated) == include_sheet
