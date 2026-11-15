"""Verificação estrutural LSF (engines.lsf.verificacao) — valores conferidos à mão e propriedades de equilíbrio."""
import json
import math

import pytest

from engines.lsf import defaults
from engines.lsf.engine import calcular
from engines.lsf import verificacao as V


@pytest.fixture(scope="module")
def exemplo():
    p = defaults.exemplo()
    r = calcular(p)
    return p, r, V.verificar(p, r)


def _ck(v, elemento):
    return next(c for c in v["verificacoes"] if c["elemento"] == elemento)


def test_seccao_bruta_c90_confere_formula_linha_media():
    s = V.seccao({"tipo": "C", "h": 90, "b": 43, "c": 10, "t": 1.2}, 350)
    # linha média: alma 88,8 + 2 banzos 41,8 + 2 lábios 9,4 = 191,2 mm × 1,2
    assert s["A"] == pytest.approx(191.2 * 1.2, rel=1e-6)
    # Iy = t·hc³/12 + 2·bc·t·(hc/2)² + 2·[t·cc³/12 + cc·t·(hc/2 − cc/2)²]
    hc, bc, cc, t = 88.8, 41.8, 9.4, 1.2
    iy = t * hc ** 3 / 12 + 2 * bc * t * (hc / 2) ** 2 + 2 * (t * cc ** 3 / 12 + cc * t * (hc / 2 - cc / 2) ** 2)
    assert s["Iy"] == pytest.approx(iy, rel=1e-6)
    assert 0 < s["Aeff"] < s["A"] and 0 < s["Weff_y"] <= s["Wel_y"] * 1.001
    assert 0.5 < s["chi_d"] <= 1.0


def test_seccao_compacta_fica_quase_bruta():
    s = V.seccao({"tipo": "C", "h": 50, "b": 40, "c": 12, "t": 3.0}, 235)
    assert s["Aeff"] == pytest.approx(s["A"], rel=0.02)


def test_trelica_fink_equilibrio_e_simetria():
    N, R, comp = V._fink(8.0, 30.0, 0.0, {"sup": (0.0, -1.0), "inf": -0.5})
    Ls = (8.0 / 4) / math.cos(math.radians(30))
    total = 1.0 * 4 * Ls + 0.5 * 8.0
    assert R["A"] + R["B"] == pytest.approx(total, rel=1e-9)
    assert R["A"] == pytest.approx(R["B"], rel=1e-9)
    assert N["BS1"] == pytest.approx(N["BS4"], rel=1e-9) and N["BS1"] < 0          # banzo superior comprimido
    assert N["BI1"] > 0 and N["BI2"] > 0                                          # banzo inferior traccionado
    assert comp["BI1"] == pytest.approx(8.0 / 3)


def test_vigas_de_piso_conferidas_a_mao(exemplo):
    p, r, v = exemplo
    c = _ck(v, "PISO1-A — flexão")
    s = V.seccao(p["perfis"]["C200_15"], 350)
    pp = s["kg_m"] * 9.81e-3
    q = 1.35 * (0.60 * 0.6 + pp) + 1.5 * (2.5 * 0.6)                     # G + Q (2,0 + 0,5 divisórias) × 0,6 m
    L = 3.997
    assert c["esforcos"]["q_kN_m"] == pytest.approx(q, abs=1e-3)
    assert c["ratio"] == pytest.approx(q * L * L / 8 * 1e6 / (s["Weff_y"] * 350), abs=2e-3)
    f = _ck(v, "PISO1-A — flecha")
    d = 5 * (0.60 * 0.6 + pp + 2.5 * 0.6) * L ** 4 / (384 * 210000 * s["Iy"] * 1e-9) * 1000
    assert f["esforcos"]["flecha_total_mm"] == pytest.approx(d, abs=0.1)


def test_vento_pt_zona_a_e_b(exemplo):
    p, r, v = exemplo
    assert v["acoes"]["vb"] == 27.0
    pb = {**p, "verificacao": {"zona_vento": "B"}}
    vb = V.verificar(pb, r)
    assert vb["acoes"]["vb"] == 30.0 and vb["acoes"]["qp"] > v["acoes"]["qp"]
    assert vb["parametros"]["zona_vento"]["valor"] == "B"


def test_neve_so_acima_de_200_m(exemplo):
    p, r, v = exemplo
    assert v["acoes"]["sk"] == 0.0
    alto = V.verificar({**p, "verificacao": {"altitude_m": 800, "zona_neve": "Z1"}}, r)
    assert alto["acoes"]["sk"] == pytest.approx(0.30 * (1 + (800 / 500) ** 2), rel=1e-3)
    assert alto["acoes"]["s"] == pytest.approx(0.8 * alto["acoes"]["sk"], rel=1e-3)


def test_combinacoes_reutilizam_en1990_e_separam_h(exemplo):
    _, _, v = exemplo
    ids = {c["id"] for c in v["combinacoes"]}
    assert {"ELU1", "ELScar1", "ELSqp", "ELU_lev"} <= ids
    for c in v["combinacoes"]:
        if c["factors"].get("H", 0) > 0:
            assert c["factors"].get("S", 0) == 0 and c["factors"].get("W", 0) == 0
    lev = next(c for c in v["combinacoes"] if c["id"] == "ELU_lev")
    assert lev["factors"]["G"] == 1.0 and lev["factors"]["Wup"] == 1.5


def test_caminho_de_cargas_paredes_de_apoio(exemplo):
    _, _, v = exemplo
    # paredes paralelas à cumeeira (RC-1/RC-3) recebem asnas + piso; empenas (RC-2/RC-4) quase nada
    assert _ck(v, "RC-1 — montante corrente")["esforcos"]["N_Ed_kN"] > 5 * _ck(v, "RC-2 — montante corrente")["esforcos"]["N_Ed_kN"]
    # a parede interior I1 recebe as duas metades do piso → aviso de parede portante
    assert any(a.startswith("I1:") and "PORTANTE" in a for a in v["avisos"])


def test_resultado_identifica_pecas_e_estado(exemplo):
    _, r, v = exemplo
    ids = {m["id"] for m in r["membros"]}
    assert len(ids) == len(r["membros"])                                     # ids únicos (BI ≠ BS nas asnas)
    for c in v["verificacoes"]:
        assert set(c["membros"]) <= ids
        assert c["status"] in ("ok", "proche", "a_revoir", "non_calcule")
    asn = _ck(v, "COB — Banzo inferior")
    assert asn["membros"] and all(".BI" in i for i in asn["membros"])
    assert set(v["ratio_membro"]) <= ids
    s = v["resumo"]
    assert s["n"] == s["ok"] + s["proximo"] + s["a_rever"] + s["nao_calculado"]


def test_resistencias_do_fabricante_opcionais(exemplo):
    p, r, v = exemplo
    cv = [c for c in v["verificacoes"] if c["grupo"] == "Contraventamento"]
    assert cv and all(c["status"] == "non_calcule" and c["esforcos"]["v_Ed_kN_m"] > 0 for c in cv)
    v2 = V.verificar({**p, "verificacao": {"contraventamento_vrd_kn_m": 10.0}}, r)
    cv2 = [c for c in v2["verificacoes"] if c["grupo"] == "Contraventamento"]
    assert all(c["ratio"] == pytest.approx(c["esforcos"]["v_Ed_kN_m"] / 10.0, abs=1e-3) for c in cv2)


def test_json_deterministico_e_no_estudo(exemplo):
    p, _, v = exemplo
    a = json.dumps(v, sort_keys=True)
    b = json.dumps(V.verificar(p, calcular(p)), sort_keys=True)
    assert a == b


def test_estudo_inclui_verificacao(exemplo, monkeypatch):
    p, _, _ = exemplo
    import engines.lsf as L
    monkeypatch.setattr(L, "precificar", lambda lin, bib, pr: {"total": 0, "linhas_sem_preco": len(lin), "linhas": len(lin), "por_origem": {}})
    st = L.estudo(p)
    assert st["resultado"]["verificacao"]["resumo"]["n"] > 0
    ruim = L.verificacao_segura({"perfis": {}}, {"paredes": [{"id": "X"}]})
    assert ruim["erro"].startswith("Verificação estrutural não calculada")


def test_secao_maior_resolve_verga_a_rever(exemplo):
    p, r, v = exemplo
    assert _ck(v, "RC-3 — verga P2")["status"] == "a_revoir"
    p2 = json.loads(json.dumps(p))
    p2["perfis"]["C200_20"] = {"tipo": "C", "h": 200, "b": 50, "c": 15, "t": 2.0}
    for tp in p2["tiposParede"].values():
        tp["verga"] = "C200_20"
    r2 = calcular(p2)
    v2 = V.verificar(p2, r2)
    assert _ck(v2, "RC-3 — verga P2")["ratio"] < _ck(v, "RC-3 — verga P2")["ratio"]
