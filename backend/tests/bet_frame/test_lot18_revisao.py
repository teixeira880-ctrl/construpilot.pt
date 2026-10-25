"""Lote 18 : correções vistas num processo real (frações empilhadas, potência do quadro, cortes de sapatas, sismo)."""
import json
from pathlib import Path

from engines.bet_frame.model import unit_name, from_dict
from engines.bet_frame.calc import sp
from engines.bet_core import mep as hmep

CASE = Path(__file__).resolve().parents[2] / "engines" / "bet_frame" / "cases" / "immeuble_demo_pt.json"


def test_fracoes_empilhadas_um_nome_por_piso():
    assert [unit_name("Frações E, I, N, R", k, 4) for k in range(4)] == ["Fração E", "Fração I", "Fração N", "Fração R"]
    assert unit_name("Logements B, F et J", 2, 3) == "Logement J"
    assert unit_name("Fração A", 0, 5) == "Fração A"          # nome não divisível : inalterado
    raw = json.loads(CASE.read_text(encoding="utf-8"))
    u = next(x for x in raw["units"] if len(x.get("levels") or []) > 1)
    u["name"] = "Frações " + ", ".join(f"X{i}" for i in range(len(u["levels"])))
    m = from_dict(raw)
    assert [x.name for x in m.units if x.id.endswith("-" + u["id"])] == [f"Fração X{i}" for i in range(len(u["levels"]))]


def test_quadro_de_entrada_usa_potencia_da_fracao():
    class M:
        raw = {"project": {"subscribed_kva": 10.35}}
    assert "10,35 kVA" in hmep._head(M()) and "15/45 A" in hmep._head(M())
    M.raw = {"project": {}}
    assert hmep._head(M()) == "Disjoncteur de branchement 500 mA 15/45 A (Enedis, 12 kVA mono à confirmer)"


def test_espacamento_sem_zero_final():
    assert sp(0.09) == "0,09" and sp(0.175) == "0,175" and sp(0.30) == "0,30"
