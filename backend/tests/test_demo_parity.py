"""A cópia JS dos motores usada no modo demonstração offline (frontend/src/lib/demoTradeCalcs.js)
tem de dar exatamente os mesmos resultados que os motores do servidor."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engines import field_records as F, trade_calcs as C

JS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "demoTradeCalcs.js"
SALA = {"name": "Sala", "length_m": 5, "width_m": 4, "height_m": 2.6, "openings": [{"width_m": 0.9, "height_m": 2.1}, {"width_m": 1.5, "height_m": 1.2}]}
CASES = [
    ("paint", {"rooms": [SALA, {"name": "Quarto", "length_m": 3.3, "width_m": 2.9, "height_m": 2.55, "paint_ceiling": True}], "coats": 2, "yield_m2_per_l": 11, "can_size_l": 4}),
    ("paint", {"rooms": [{"name": "Q", "length_m": 3, "width_m": None, "height_m": 2.5}], "coats": None}),
    ("floor", {"length_m": 4.2, "width_m": 3.1, "waste_pct": 12, "piece_length_m": 0.6, "piece_width_m": 0.3, "pieces_per_package": 8, "package_price": 19.9}),
    ("floor", {"area_m2": 12}),
    ("masonry", {"wall_length_m": 5, "wall_height_m": 2.5, "block_length_m": 0.5, "block_height_m": 0.2, "joint_m": 0.01, "waste_pct": 5, "openings": [{"width_m": 1, "height_m": 2}]}),
    ("points", {"trade": "canalizacao", "items": [{"type": "sanita", "qty": 2, "room": "WC"}, {"type": "agua_fria", "qty": 5, "room": "WC"}, {"type": "outro", "label": "Torneira jardim", "qty": 1}, {"type": "lavatorio", "qty": None}], "prices": {"Sanita": 80}}),
    ("carpentry", {"pieces": [{"name": "Lateral", "length_m": 2, "width_m": 0.6, "qty": 2, "material": "MDF 19", "edges_m": 2.6, "hardware": [{"name": "Dobradiça", "qty": 2}]}, {"name": "Prateleira", "length_m": 0.8, "width_m": 0.4, "qty": 3, "material": "MDF 19"}], "waste_pct": 15, "sheet_m2": 5.06}),
]
QUOTE = {"rooms": [SALA, {"name": "Quarto 1", "length_m": 3, "width_m": 3, "height_m": 2.5}], "coats": 2, "yield_m2_per_l": 10, "can_size_l": 15,
         "crack_repair": True, "crack_repair_ml": 6, "prices": {"labor_per_m2": 8, "prep_per_m2": 2, "paint_per_can": 60}}
DAILY = ["Hoje fomos dois, colocámos o chão da cozinha e faltou cola.", "Eu e o Rui pintámos a sala e o quarto, das 8h às 17h. Acabou a tinta branca",
         "Estivemos na obra e reparámos fissuras", "Éramos 3 trabalhadores, assentámos azulejo e ficámos sem cimento cola"]

SCRIPT = """
import * as M from "./demo.mjs";
const input = JSON.parse(process.argv[2]);
const out = {
  tools: input.cases.map(([t, p]) => M.TOOLS[t](p)),
  quote: M.paintingQuoteLines(input.quote),
  daily: input.daily.map(M.parseDaily),
};
console.log(JSON.stringify(out));
"""


def _drop(d, keys):
    return {k: v for k, v in d.items() if k not in keys}


@pytest.mark.skipif(not shutil.which("node"), reason="node indisponível")
def test_js_demo_engines_match_server(tmp_path):
    (tmp_path / "demo.mjs").write_text(JS.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "run.mjs").write_text(SCRIPT, encoding="utf-8")
    payload = json.dumps({"cases": CASES, "quote": QUOTE, "daily": DAILY})
    res = subprocess.run(["node", "run.mjs", payload], cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)
    for (tool, p), got in zip(CASES, js["tools"]):
        exp = json.loads(json.dumps(C.compute(tool, p)))
        if tool == "points":
            exp = _drop(exp, {"lines"})
        if tool == "paint":
            exp = _drop(exp, {"provenance"})
            got = _drop(got, set())
        assert got == exp, tool
    py_quote = json.loads(json.dumps(C.painting_quote_lines(QUOTE)))
    assert js["quote"]["lines"] == py_quote["lines"] and js["quote"]["to_confirm"] == py_quote["to_confirm"]
    for text, got in zip(DAILY, js["daily"]):
        assert got == json.loads(json.dumps(F.parse_daily(text))), text


def test_demo_catalog_fixture_is_up_to_date():
    import importlib.util
    spec = importlib.util.spec_from_file_location("exp", Path(__file__).resolve().parents[1] / "scripts" / "export_work_profile_catalog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fixture = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "workProfileCatalog.json"
    assert json.loads(fixture.read_text(encoding="utf-8")) == json.loads(json.dumps(mod.export(), ensure_ascii=False)), \
        "Execute: python scripts/export_work_profile_catalog.py"
