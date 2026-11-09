"""09/11/2026 : moteur bois massif CLT / lamellé-collé (bet_clt) — calculs vérifiés à la main + dossiers FR / PT / UA."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engines.bet_clt import pipeline, timber  # noqa: E402
from engines.bet_clt.lang import use_lang  # noqa: E402

CASES = Path(__file__).resolve().parents[1] / "engines" / "bet_clt" / "cases"


def test_clt_gamma_3_layers_hand_calc():
    # 3 plis 40/40/40, portée 4 m : γ1 = 1/(1 + π²·E·A·(t2/2)/(G_R·b·L²)), (EI)_ef = Σ E·I + Σ γ·E·A·a²
    E, A, GR, b, L = 11000.0, 40000.0, 50.0, 1000.0, 4000.0
    g = 1 / (1 + math.pi ** 2 * E * A * 20 / (GR * b * L ** 2))
    EI = 2 * E * b * 40 ** 3 / 12 + 2 * g * E * A * 40 ** 2
    p = timber.clt_props((40, 40, 40), L)
    assert abs(p["gamma"][0] - g) < 1e-3
    assert abs(p["EI"] - EI) / EI < 1e-6
    # σ_max = M·E·(γ·a + t/2)/EI
    assert abs(p["s_fac"] - E * (g * 40 + 20) / EI) < 1e-12


def test_clt_5_layers_center_gamma_one():
    p = timber.clt_props((40, 20, 40, 20, 40), 5000.0)
    assert p["gamma"][1] == 1.0 and p["gamma"][0] == p["gamma"][2] < 1.0


def test_char_depth_layer_falloff():
    # 30 min sur pli de 40 : 0,65 × 30 = 19,5 mm (pas encore de chute de pli)
    assert abs(timber.char_depth(30, (40, 40, 40)) - 19.5) < 0.2
    # 90 min : chute du 1er pli à ≈ 61,5 min puis 2β0 sur 25 mm → plus que 0,65 × 90
    assert timber.char_depth(90, (40, 40, 40)) > 0.65 * 90


def test_gl_beam_hand_calc():
    # GL24h 160×720, L = 7,2 m, g = 10 kN/m, q = 3 kN/m : M = (1,35·(g+pp) + 1,5·q)·L²/8
    r = timber.check_gl_beam(160, 720, "GL24h", 7.2, 10.0, 3.0, [], [], R=0)
    pp = 4.6 * 0.16 * 0.72
    M = (1.35 * (10 + pp) + 1.5 * 3.0) * 7.2 ** 2 / 8
    assert abs(r["M_Ed"] - round(M, 1)) < 0.11
    W = 160 * 720 ** 2 / 6
    Mg = 1.35 * (10 + pp) * 7.2 ** 2 / 8          # G seul avec k_mod permanent = 0,6 (souvent dimensionnant en bois)
    u = max(M * 1e6 / W / (0.8 * 24 / 1.25), Mg * 1e6 / W / (0.6 * 24 / 1.25))
    assert abs(r["u_m"] - u) < 2e-3


def test_screw_withdrawal_en1995():
    r = timber.screw_axial(8, 100, 350, 90, kmod=0.8)
    fax = 0.52 * 8 ** -0.5 * 100 ** -0.1 * 350 ** 0.8
    assert abs(r["fax_k"] - fax) < 0.01
    assert r["R_k"] == round(fax * 8 * 100)


def test_column_buckling_kc():
    r = timber.check_gl_column(240, 240, "GL24h", 3.5, 300, 100, 0, 0)
    i = 240 / math.sqrt(12)
    lr = 3500 / i / math.pi * math.sqrt(24 / 9600)
    k = 0.5 * (1 + 0.1 * (lr - 0.3) + lr ** 2)
    assert abs(r["kc"] - 1 / (k + math.sqrt(k * k - lr * lr))) < 1e-3


def _run(name, tmp, langs=None):
    raw = json.loads((CASES / name).read_text(encoding="utf-8"))
    return pipeline.run(raw, tmp, langs=langs)


def test_pipeline_fr_offices(tmp_path):
    r = _run("bureaux_clt_fr.json", tmp_path)
    assert r["status"].startswith("PRÊT") and r["blocking"] == 0
    s = r["summary"]
    assert s["system"] == "post_beam" and all(f["u"] <= 1 for f in s["floors"])
    assert any(x.startswith("CL40") for x in r["sheets"]) and any(x.startswith("CL31") for x in r["sheets"])
    for k in ("pdf", "plans_pdf", "xlsx", "zip"):
        assert Path(r["files"][k]).stat().st_size > 1000


def test_pipeline_pt(tmp_path):
    r = _run("habitacao_clt_pt.json", tmp_path)
    assert r["lang"] == "pt" and r["blocking"] == 0
    assert r["summary"]["R"] == 30           # RT-SCIE, h = 9 m


def test_pipeline_ua_uk_en(tmp_path):
    r = _run("budynok_clt_ua.json", tmp_path, langs=["en"])
    assert r["lang"] == "uk" and r["langs"] == ["uk", "en"]
    assert r["summary"]["system"] == "walls" and r["blocking"] == 0
    assert "pdf_en" in r["files"] and Path(r["files"]["pdf_en"]).exists()
    from pypdf import PdfReader
    txt = PdfReader(r["files"]["pdf"]).pages[0].extract_text()
    assert "Розрахункова записка" in txt


def test_routing_clt():
    from engines.bet_frame.hook import _wants_clt
    assert _wants_clt([], "maison CLT R+1")
    assert _wants_clt([], "immeuble de bureaux en bois lamellé-croisé, poteaux lamellé-collé")
    assert _wants_clt([], "Житловий будинок CLT")
    assert not _wants_clt([], "immeuble collectif béton armé R+4")


def test_four_languages_texts():
    from engines.bet_clt.lang import t
    for lg, word in (("fr", "Plancher"), ("pt", "Piso"), ("en", "Floor"), ("uk", "Перекриття")):
        with use_lang(lg):
            assert t("Plancher", "Piso", "Floor", "Перекриття") == word


# ---- 09/11/2026 : plan réel « Home A » (CLT Rezult) — compositions imposées, étages en L, thermique, devis final aux prix UA
def test_layup_parser():
    from engines.bet_clt.mat import layup
    assert layup("CLT Panel 240-7s")[0] == "240 L7s"
    assert layup("CLT Panel140-5s")[0] == "140 L5s"
    assert layup("100 L5s")[1] == (20, 20, 20, 20, 20)
    assert layup("n'importe quoi") is None


def test_home_a_imposed_layups_checked_per_span(tmp_path):
    r = _run("home_a_clt_rezult_pt.json", tmp_path)
    fl = {f["name"]: f for f in r["summary"]["floors"]}
    assert fl["1.º andar"]["clt"] == "240 L7s" and fl["Cobertura"]["clt"] == "140 L5s"     # composições da planta, não substituídas
    txt = " ".join(r["decisions"])
    assert "5,10 m → 0,93" in txt                     # vão real da sala : 240-7s OK
    assert "5,61 m → 1,11 ✗" in txt                  # se os painéis vencerem N–S sobre os quartos : vibração
    assert "5,10 m → 1,39 ✗" in txt                  # cobertura 140-5s insuficiente sobre a sala (terraço do R/C)
    walls = {w["id"]: w for w in r["summary"]["walls"]}
    assert walls["WN"]["segs"][0][1] == "80 L3s"     # mitoyen 2 × 80 L3s
    assert "WF1" in walls and len(walls["WS"]["segs"]) == 1     # façade du 1.º andar en retrait (alinhamento 2), pas de mur fantôme


def test_home_a_thermal_pt_and_fr(tmp_path):
    from engines.bet_clt import thermal
    from engines.bet_frame import model
    raw = json.loads((CASES / "home_a_clt_rezult_pt.json").read_text(encoding="utf-8"))
    th = thermal.compute(model.from_dict(raw))
    s = th["solutions"]
    # parede : 1 / (0,13 + 0,025/0,25 + 0,10/0,13 + 0,10/0,035 + 0,01/1,0 + 0,04)
    assert abs(s["wall"]["U"] - 1 / (0.13 + 0.1 + 0.1 / 0.13 + 0.1 / 0.035 + 0.01 + 0.04)) < 1e-3
    g = th["geometry"]["storeys"]
    assert g[1]["fac"]["x0"] == 13.53 and g[0]["party"] == 13.53 and abs(g[0]["roof"] - 50.87) < 0.05
    assert th["reh"]["classe"] in ("A+", "A") and th["ok"]
    raw = json.loads((CASES / "home_a_clt_rezult_fr.json").read_text(encoding="utf-8"))
    th = thermal.compute(model.from_dict(raw))
    assert th["re2020"]["conforme"] and th["re2020"]["Bbio"] < th["re2020"]["seuils"]["Bbio_max"]


def test_home_a_final_estimate_ua(tmp_path):
    r = _run("home_a_clt_rezult_pt.json", tmp_path, langs=["en", "uk"])
    for k in ("estimate_pdf", "estimate_xlsx", "estimate_pdf_en", "estimate_pdf_uk"):
        assert Path(r["files"][k]).stat().st_size > 5000
    d = r["summary"]["devis"]
    assert 25000 < d["ua_per_m2"] < 48000          # dans la fourchette du marché ukrainien 2026 (maison clés en main)
    from pypdf import PdfReader
    assert "грн" in PdfReader(r["files"]["estimate_pdf_uk"]).pages[0].extract_text()
