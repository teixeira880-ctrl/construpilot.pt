"""Lote 21 : plantas A1 digitalizadas — ampliações legíveis do edifício e leitura independente das cotas contra a geometria inventada."""
import asyncio
import copy
import io
import json
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

from engines.bet_frame import geometry, model, reader, zoom

CASE = json.loads((Path(__file__).resolve().parents[2] / "engines" / "bet_frame" / "cases" / "immeuble_demo_pt.json").read_text(encoding="utf-8"))


def _a1_scan() -> bytes:
    """Planche A1 raster (sans texte) : un bâtiment hachuré dense au centre-droit, du terrain clair autour."""
    im = Image.new("L", (3300, 2340), 255)
    d = ImageDraw.Draw(im)
    d.rectangle((20, 20, 3280, 2320), outline=0, width=4)
    for x in range(1300, 2300, 9):
        d.line((x, 700, x, 1500), fill=0, width=3)
    d.rectangle((1300, 700, 2300, 1500), outline=0, width=12)
    for k in range(0, 3300, 300):
        d.line((k, 0, k + 200, 2340), fill=120, width=1)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    doc = fitz.open()
    pg = doc.new_page(width=2384, height=1684)
    pg.insert_image(pg.rect, stream=buf.getvalue())
    return doc.tobytes()


def test_ampliacoes_do_edificio_numa_planta_a1():
    data = _a1_scan()
    with fitz.open(stream=data, filetype="pdf") as d:
        x0, y0, x1, y1 = zoom.building_box(d[0])
    sx = 2384 / 3300
    assert x0 <= 1300 * sx <= x1 and x0 <= 2300 * sx <= x1 and y0 <= 700 * sx <= y1
    assert (x1 - x0) < 0.75 * 2384                            # recorte, não a folha inteira
    assert len(zoom.zooms(data, 1)) == 3


def test_geometria_diferente_da_leitura_independente_bloqueia():
    raw = copy.deepcopy(CASE)
    ov = raw["geometry"]["overall"]
    ref = {"overall": {"length": ov["length"] - 8.0, "width": ov["width"]}, "cotes": []}
    assert "GEO-09" in {a["code"] for a in geometry.check(raw, None, ref) if a["level"] == model.BLOCK}
    ref = {"overall": {"length": ov["length"], "width": ov["width"]}, "cotes": []}
    assert "GEO-09" not in {a["code"] for a in geometry.check(raw, None, ref)}


def test_geometria_deduzida_das_areas_bloqueia():
    raw = copy.deepcopy(CASE)
    raw["geometry"]["overall"]["source"] = "Dimensões deduzidas a partir do quadro de áreas"
    assert "GEO-08" in {a["code"] for a in geometry.check(raw) if a["level"] == model.BLOCK}
    raw = copy.deepcopy(CASE)
    raw["_decisions"] = ["As dimensões gerais e a malha estrutural foram recalculadas para coincidir com as áreas."]
    assert "GEO-08" in {a["code"] for a in geometry.check(raw) if a["level"] == model.BLOCK}


def test_leitor_envia_ampliacoes_e_cotas_independentes():
    calls = []

    async def llm(system, text, images=None, model=None, max_tokens=0, json_schema=None):
        calls.append((system[:20], len(images or []), text))
        if system.startswith("Tu es métreur"):
            ov = CASE["geometry"]["overall"]
            return json.dumps({"overall": {"length": ov["length"], "width": ov["width"], "where": "planta"}, "cotes": [6.2, 3.1]})
        return json.dumps(CASE)
    out = asyncio.run(reader.read_frame([("plantas.pdf", _a1_scan())], "", "PT", llm=llm))
    assert out["ok"], out["anomalies"]
    metreur, frame = calls[0], calls[1]
    assert metreur[0].startswith("Tu es métreur") and metreur[1] >= 4         # página + 3 ampliações
    assert "AGRANDISSEMENT" in frame[2] and "lecture indépendante" in frame[2]


def test_cave_maior_que_os_pisos_tem_de_ser_respeitada():
    raw = copy.deepcopy(CASE)
    m = model.from_dict(raw)
    L, W = geometry.storey_bbox(m, m.levels[0].id)
    cave = next(l for l in raw["levels"] if l["id"] == m.levels[0].id)
    ref = {"per_level": [{"level": cave.get("name") or "Piso -1", "length": L + 8.0, "width": W + 12.0}]}
    if geometry._level_no(cave.get("name") or "") is None:
        ref["per_level"][0]["level"] = m.levels[0].name
    assert "GEO-10" in {a["code"] for a in geometry.check(raw, None, ref) if a["level"] == model.BLOCK}
    ref = {"per_level": [{"level": ref["per_level"][0]["level"], "length": L, "width": W}]}
    assert "GEO-10" not in {a["code"] for a in geometry.check(raw, None, ref)}


def test_numero_do_piso():
    assert geometry._level_no("Piso -1 — estacionamento") == -1 and geometry._level_no("Cave") == -1
    assert geometry._level_no("R/C (piso 0)") == 0 and geometry._level_no("Piso 3") == 3
