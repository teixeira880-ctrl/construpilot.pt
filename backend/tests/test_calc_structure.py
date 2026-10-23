"""Ferramenta calcul_structure (PT): ponte para os motores EC2 / EC5 / EC7 / laje / lintel / escada existentes."""
import math

import pytest

from engines.calc_lots import structure as S


def test_poutre_ba_moment_et_acier():
    r = S.calculer({"element": "poutre_ba", "portee_m": 5, "b_m": 0.25, "h_m": 0.45, "g_kn_m": 15, "q_kn_m": 6})
    g = 15 + 25 * 0.25 * 0.45
    assert r["sollicitations"]["med"] == pytest.approx((1.35 * g + 1.5 * 6) * 25 / 8)
    as_req = r["details"]["flexure"]["as_req_cm2"]
    assert r["barres"]["as_cm2"] >= as_req
    assert all(c["ok"] for c in r["controles"])
    assert 40 < r["quantites"]["ratio_kg_m3"] < 200


def test_poutre_ba_trop_elancee_ko():
    r = S.calculer({"element": "poutre_ba", "portee_m": 9, "b_m": 0.2, "h_m": 0.3, "g_kn_m": 10, "q_kn_m": 5})
    assert any(c["ok"] is False for c in r["controles"])


def test_poutre_bois_fleche():
    ok = S.calculer({"element": "poutre_bois", "portee_m": 4, "b_m": 0.075, "h_m": 0.225, "g_kn_m": 1.0, "q_kn_m": 1.2})
    ko = S.calculer({"element": "poutre_bois", "portee_m": 6, "b_m": 0.063, "h_m": 0.15, "g_kn_m": 1.0, "q_kn_m": 1.2})
    assert all(c["ok"] for c in ok["controles"]) and any(c["ok"] is False for c in ko["controles"])


def test_semelle_g2_et_ec7():
    r = S.calculer({"element": "semelle", "b_m": 0.5, "g_kn": 60, "q_kn": 20, "q_adm_els_kpa": 150})
    assert r["controles"][0]["ok"] is False
    r = S.calculer({"element": "semelle", "b_m": 0.6, "g_kn": 60, "q_kn": 20, "phi_deg": 28, "profondeur_m": 0.8})
    assert r["controles"][0]["ok"] is True
    with pytest.raises(ValueError):
        S.calculer({"element": "semelle", "b_m": 0.6, "g_kn": 60})


def test_dalle_linteau_escalier():
    d = S.calculer({"element": "dalle_ba", "lx_m": 4.5, "ly_m": 5.5, "h_m": 0.2})
    assert d["quantites"]["beton_m3"] == pytest.approx(4.95)
    li = S.calculer({"element": "linteau", "portee_m": 2.4, "hauteur_maconnerie_m": 1.2, "g_kn_m": 8, "q_kn_m": 3})
    assert li["controles"][0]["ok"]
    e = S.calculer({"element": "escalier", "hauteur_a_monter_mm": 2750, "reculement_mm": 4500, "largeur_mm": 900})
    assert 600 <= e["details"]["blondel_value_mm"] <= 640
    court = S.calculer({"element": "escalier", "hauteur_a_monter_mm": 2750, "reculement_mm": 2500, "largeur_mm": 900})
    assert any(c["ok"] is False for c in court["controles"])


def test_note_pdf_pt():
    out = S.note({"element": "poutre_ba", "portee_m": 5, "b_m": 0.25, "h_m": 0.45, "g_kn_m": 15, "q_kn_m": 6})
    assert out["pdf"][:4] == b"%PDF" and out["png"][:4] == b"\x89PNG"
    assert "Ø" in out["barres"]["label"] and "HA" not in out["barres"]["label"]
    assert out["titre"].startswith("Pré-dimensionamento — Viga")
    assert math.isfinite(out["quantites"]["acier_kg"])
    assert S.note({"element": "poteau_ba", "b_m": 0.25, "h_m": 0.25, "hauteur_m": 2.7, "n_ed_kn": 600})["pdf"][:4] == b"%PDF"
    with pytest.raises(ValueError):
        S.calculer({"element": "poutre_ba"})
    with pytest.raises(ValueError):
        S.calculer({"element": "inexistant"})


def test_textos_sem_frances():
    casos = [{"element": "poutre_ba", "portee_m": 5, "b_m": 0.25, "h_m": 0.45, "g_kn_m": 15, "q_kn_m": 6, "appuis": "continue_rive"},
             {"element": "dalle_ba", "lx_m": 4.5, "ly_m": 5.5, "h_m": 0.2, "x1": "continu"},
             {"element": "linteau", "portee_m": 2.4, "hauteur_maconnerie_m": 0.3, "g_kn_m": 8, "q_kn_m": 3},
             {"element": "escalier", "hauteur_a_monter_mm": 2750, "reculement_mm": 4500, "largeur_mm": 900},
             {"element": "escalier", "hauteur_a_monter_mm": 2750, "reculement_mm": 2500, "largeur_mm": 900},
             {"element": "semelle", "b_m": 0.6, "g_kn": 60, "q_kn": 20, "phi_deg": 28, "profondeur_m": 0.8},
             {"element": "poinconnement", "d_m": 0.18, "c1_m": 0.3, "v_ed_kn": 400}]
    for c in casos:
        r = S.calculer(c)
        textos = [r["element"], r["section"], *r["hypotheses"]] + [str(x.get(k) or "") for x in r["controles"] for k in ("ref", "exigence", "valeur", "note")]
        for t in textos:
            for fr in ("poutre", "dalle", "semelle", "à vérifier", "non conforme", "Giron", "Reculement", " de la ", "HA1", "HA2", "HA8"):
                assert fr not in t, (c["element"], t)


def test_corrections_relecture():
    r = S.calculer({"element": "poutre_ba", "portee_m": 4, "b_m": 0.2, "h_m": 0.4, "g_kn_m": 40, "q_kn_m": 30})
    assert "s = 16" in r["etriers"] or "s = 15" in r["etriers"]
    assert any(c["ok"] is False for c in S.calculer({"element": "dalle_ba", "lx_m": 6, "ly_m": 7, "h_m": 0.12})["controles"])
    S.calculer({"element": "dalle_ba", "lx_m": 9, "ly_m": 8, "h_m": 0.14, "q_kn_m2": 20})            # sem erro, vãos trocados
    b = S.calculer({"element": "poutre_bois", "portee_m": 4, "b_m": 0.075, "h_m": 0.225, "g_kn_m": 2.6, "q_kn_m": 0.2})
    assert any("1,35 G" in c["ref"] and c["ok"] is False for c in b["controles"])
    e = S.calculer({"element": "escalier", "hauteur_a_monter_mm": 2700, "reculement_mm": 3500, "largeur_mm": 900})
    assert e["element"].startswith("Escada reta") and all(c["ok"] for c in e["controles"])


def test_poteau_et_poinconnement():
    r = S.calculer({"element": "poteau_ba", "b_m": 0.25, "h_m": 0.25, "hauteur_m": 2.7, "n_ed_kn": 600})
    assert r["details"]["lambda"] > r["details"]["lambda_lim"] and r["sollicitations"]["m2"] > 0
    assert all(c["ok"] is not False for c in r["controles"]) and r["barres"]["as_cm2"] >= 4.5
    gros = S.calculer({"element": "poteau_ba", "b_m": 0.3, "h_m": 0.3, "hauteur_m": 3, "n_ed_kn": 2500})
    assert any(c["ok"] is False for c in gros["controles"])
    from engines.calc_lots.structure import _nm_capacite
    assert _nm_capacite(0.3, 0.3, 0.05, 4e-4, 25 / 1.5, 500 / 1.15, 10 ** 6) is None      # acima de N_Rd,max
    p = S.calculer({"element": "poinconnement", "d_m": 0.18, "c1_m": 0.3, "v_ed_kn": 400})
    assert p["details"]["asw_cm2_contour"] > 0
    assert any(c["ok"] is False for c in S.calculer({"element": "poinconnement", "d_m": 0.16, "c1_m": 0.25, "v_ed_kn": 900})["controles"])
