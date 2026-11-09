"""Módulo Ucrânia: ДБН В.2.6-31:2021 (Rq,min por zona), ДБН В.1.2-2:2006 (neve / vento), perdas, gros-œuvre com planos em ucraniano."""
import json

import pytest

pytest.importorskip("reportlab")
pymupdf = pytest.importorskip("pymupdf")

from engines.calc_lots import outils, ucrania  # noqa: E402


def test_valores_normativos():
    assert ucrania.RQMIN["parede"] == {"I": 4.0, "II": 3.5} and ucrania.RQMIN["cobertura"] == {"I": 7.0, "II": 6.0}
    assert ucrania.RQMIN["janela"] == {"I": 0.9, "II": 0.7}
    c = ucrania.clima("Kyiv")
    assert c["zona"] == "I" and c["theta_e"] == -22 and c["s0_pa"] == 1550 and c["w0_pa"] == 370
    assert ucrania.clima("odesa")["zona"] == "II"
    k = ucrania.navantazhennya(c)
    assert k["sm_kpa"] == pytest.approx(1.55) and k["wm_kpa"] == pytest.approx(0.259)
    assert ucrania.navantazhennya(c, inclinacao_graus=40)["mu"] == pytest.approx(20 / 35)
    with pytest.raises(ValueError):
        ucrania.clima("Madrid")


def test_parede_insuficiente_detectada():
    c = ucrania.clima("kharkiv")
    e = ucrania.elemento({"tipo": "parede", "area_m2": 50, "camadas": [{"material": "tsehla_povnotila", "espessura_mm": 510}]}, c, 20, 0.55, "residencial")
    assert not e["ok"] and e["R"] < 4.0


def test_exemplo_kyiv_completo():
    o = ucrania.note(ucrania.exemplo_kyiv())
    r = o["r"]
    assert all(e["ok"] for e in r["elementos"])
    assert 4000 < r["phi_w"] < 9000 and 60 < r["q_kwh_m2"] < 160
    assert o["go"]["verificacao"]["conforme"]
    d = pymupdf.open(stream=o["pdf"], filetype="pdf")
    t0, tp = d[0].get_text(), "".join(d[i].get_text() for i in range(len(d)))
    assert "Київ" in t0 and "Summary (English)" in t0 and "ДБН В.2.6-31:2021" in t0
    assert "ПЛАН ФУНДАМЕНТІВ З РОЗМІРАМИ" in tp and "РОЗРІЗ" in tp and "10000" in tp
    assert "Sapata" not in tp and "CORTE" not in tp                    # nada em português nas peças ucranianas


def test_ferramenta_e_nome_do_ficheiro():
    out = outils.run("calcul_ucrania", {"exemplo": True, "cidade": "odesa", "modelo_estrutural_json": None})
    assert out["pdf"][:4] == b"%PDF" and "Ukraine" in out["titre"] and "Odesa" in out["resume"]
    assert out["data"]["zona"] == "II"
    m = json.dumps(ucrania.modelo_casa_kyiv())
    out2 = outils.run("calcul_ucrania", {"cidade": "lviv", "modelo_estrutural_json": m,
                                         "elementos": [{"tipo": "parede", "area_m2": 80, "R": 4.2}]})
    assert "Structure" in out2["resume"]
