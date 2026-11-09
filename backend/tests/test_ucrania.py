"""Módulo Ucrânia: ДБН В.2.6-31:2021 (Rq,min por zona), ДБН В.1.2-2:2006 (neve / vento), perdas, gros-œuvre com planos em ucraniano."""
import json

import os

import pytest

os.environ.setdefault("CP_RENDER_SPP", "2")
os.environ.setdefault("CP_RENDER_W", "160")

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
    t0, tp = d[0].get_text() + d[1].get_text(), "".join(d[i].get_text() for i in range(len(d)))   # [0] = capa premium
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


def test_exemplo_clt_paineis_e_pontes():
    o = ucrania.note(ucrania.exemplo_clt())
    r, v = o["r"], o["go"]["verificacao"]
    assert all(e["ok"] for e in r["elementos"])
    parede = r["elementos"][0]
    assert parede["pontes_explicitas"] and parede["U"] > 1 / parede["R"]            # ψ / χ explícitos agravam o U
    clt = [e for e in v["elementos"] if e["tipo"] == "painel CLT"]
    assert len(clt) == 8 and all(e["ok"] for e in clt)
    assert any("Корте" not in h and "CLT" in h for h in r["hipoteses"])              # limites do CLT declarados (vibração, ETA)
    tp = "".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
    assert "Панель CLT" in tp and "Painel" not in tp


def test_rigidez_clt_referencia():
    from engines.calc_lots import gros_oeuvre
    r = gros_oeuvre.clt_rigidez([27.8] * 5)
    assert r["EI"] == pytest.approx(11e6 * (3 * 0.0278 ** 3 / 12 + 2 * 0.0278 * 0.0556 ** 2), rel=1e-6)
    assert r["V_Rd"] == pytest.approx(0.8 * 1.1e3 / 1.25 * r["I"] / (0.0278 * 0.0556), rel=1e-6)
    with pytest.raises(ValueError):
        gros_oeuvre.clt_rigidez([40, 40])


def test_fusao_codex_preenche_sem_confirmar():
    from engines.bet_clt_ua.engine import run
    raw = json.load(open("engines/bet_clt_ua/cases/synthetic_mechanics_only.json"))
    raw["site"]["locality"] = "Kharkiv"
    raw["assemblies"][0]["required_effective_r_m2k_w"] = None
    full, feito = ucrania.preencher_clt_ua(raw)
    assert full["site"]["snow_ground_kpa"] == pytest.approx(1.6) and full["site"]["thermal_zone"] == "I"
    assert full["assemblies"][0]["required_effective_r_m2k_w"] == 4.0 and len(feito) == 5
    assert raw["assemblies"][0]["required_effective_r_m2k_w"] is None                  # entrada intacta
    res = run(full)
    assert res["status"] in ("INPUT_REQUIRED", "LIMITED_CHECKS_FAILED") and res["certified"] is False   # nunca "confirmado" automaticamente
    assert "site.confirmed_basis" in res["missing"]


def test_ferramenta_clt():
    out = outils.run("calcul_ucrania", {"exemplo": True, "sistema": "clt", "cidade": "chernihiv"})
    assert "CLT" in out["resume"] and out["data"]["envolvente_conforme"]


def test_eta_rezult_valores_declarados():
    from engines.calc_lots import clt_produtos as CP
    p = CP.produto("Rezult")
    assert p["eta"].startswith("ETA-21/0914") and p["E0_mean"] == 12000 and p["G_R"] == 50 and p["beta_0"] == 0.65
    assert CP.fr_k(p, 20, "pinho") == 1.8 and CP.fr_k(p, 43, "pinho") == pytest.approx(1.34) and CP.fr_k(p, 30, None) == 1.1
    assert CP.k_sys(4) == pytest.approx(1.075) and CP.k_sys(20) == 1.2
    assert CP.validar_camadas(p, [40] * 5) == [] and CP.validar_camadas(p, [50, 50, 50])          # tábuas 50 mm fora da ETA
    assert CP.carbonizacao([40] * 5, 60, 0.65)["d_char"] == pytest.approx(39.0)
    assert CP.carbonizacao([40] * 5, 90, 0.65)["d_char"] == pytest.approx(71.0)                    # bilinear: 2·β após a 1.ª lamela


def test_exemplo_clt_rezult_fogo():
    o = ucrania.note(ucrania.exemplo_clt())
    v = o["go"]["verificacao"]
    paineis = [e for e in v["elementos"] if e["tipo"] == "painel CLT"]
    assert paineis and all(e["ok"] for e in paineis) and all("ETA-21/0914" in e["seccao"] for e in paineis)
    assert all(any(c["lib"] == "Fogo R" and c["ok"] for c in e["controles"]) for e in paineis)
    tp = "".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
    assert "Rezult CLT" in tp and "ETA-21/0914" in tp and "Painéis" not in tp
