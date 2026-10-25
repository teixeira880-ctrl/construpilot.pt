"""Lote 19 : o levantamento tem de seguir a geometria real das plantas (cotas exteriores, trama, áreas das frações)."""
import copy
import json
from pathlib import Path

from engines.bet_frame import geometry, model, pipeline

CASE = json.loads((Path(__file__).resolve().parents[2] / "engines" / "bet_frame" / "cases" / "immeuble_demo_pt.json").read_text(encoding="utf-8"))


def codes(an, level=None):
    return {a["code"] for a in an if level is None or a["level"] == level}


def test_caso_coerente_sem_bloqueio_geometrico():
    assert not codes(geometry.check(CASE), model.BLOCK)


def test_sem_cotas_exteriores_bloqueia_no_leitor_e_avisa_no_calculo():
    raw = copy.deepcopy(CASE)
    raw.pop("geometry")
    assert "GEO-00" in codes(geometry.check(raw), model.BLOCK)
    _, an = pipeline.validate(raw)                          # estudo já aceite : só aviso
    assert "GEO-00" in codes(an, model.WARN) and "GEO-00" not in codes(an, model.BLOCK)


def test_trama_incompativel_com_as_cotas():
    raw = copy.deepcopy(CASE)
    raw["geometry"]["overall"]["length"] = 26.40
    assert "GEO-01" in codes(geometry.check(raw), model.BLOCK)


def test_cota_inventada_e_trama_idealizada_contra_o_texto_vetorial():
    raw = copy.deepcopy(CASE)
    pages = [{"text": "PLANTA PISO 1 " + "parede 0,20 porta 0,90 " * 20 + " cota 12,35 4,15 3,80"}]
    an = geometry.check(raw, pages)
    assert {"GEO-02", "GEO-03"} <= codes(an, model.BLOCK)
    ov = raw["geometry"]["overall"]
    spans = [round(b - a, 2) for g in (raw["grid"]["x"], raw["grid"]["y"]) for a, b in zip(g, g[1:])]
    pages = [{"text": "PLANTA " + " ".join(f"{v:.2f}".replace(".", ",") for v in [ov["length"], ov["width"]] + spans) + " x" * 200}]
    assert not codes(geometry.check(raw, pages), model.BLOCK)


def test_area_declarada_e_sobreposicao():
    raw = copy.deepcopy(CASE)
    u = raw["units"][0]
    u["area_declared"] = round((u["x1"] - u["x0"]) * (u["y1"] - u["y0"]) * 0.5, 1)
    assert "GEO-04" in codes(geometry.check(raw), model.BLOCK)
    raw = copy.deepcopy(CASE)
    a, b = raw["units"][0], raw["units"][1]
    b.update({k: a[k] for k in ("x0", "y0", "x1", "y1")})
    b["levels"] = a["levels"]
    assert "GEO-05" in codes(geometry.check(raw), model.BLOCK)


def test_cotas_em_cm_e_mm():
    cs = geometry.cotes([{"text": "2640 26400 15,20"}])
    assert 26.4 in cs and 15.2 in cs
