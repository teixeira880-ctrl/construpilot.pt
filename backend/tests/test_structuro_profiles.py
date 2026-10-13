"""Catalogue EN 10365 étendu + classification de section EN 1993-1-1 Table 5.2."""
from engines import structuro_profiles as P


def test_catalog_completeness():
    fams = P.families()
    assert set(fams) == {"IPE", "HEA", "HEB", "UPN"}
    assert "IPE600" in P.PROFILE_DATA and "HEB600" in P.PROFILE_DATA and "UPN300" in P.PROFILE_DATA
    assert len(P.PROFILE_DATA) >= 60


def test_properties_match_published_ipe300():
    p = P.PROFILE_DATA["IPE300"]
    assert abs(p["A"] - 53.81) < 0.2 and abs(p["Iy"] - 8356) < 30
    assert abs(p["Wpl"] - 628.4) < 2 and abs(p["Av"] - 25.7) < 0.3
    assert abs(p["It"] - 19.75) < 1.0 and abs(p["Iw"] - 125900) < 4000


def test_classification_bending_vs_compression():
    # IPE300 S235 : flexion classe 1 ; âme en compression pure → classe 2
    cb = P.classify("IPE300", 235, "bending")
    cc = P.classify("IPE300", 235, "compression")
    assert cb["section_class"] == 1
    assert cc["section_class"] == 2
    assert cb["c_tw_ratio"] > 0 and cb["epsilon"] == 1.0


def test_classification_grade_sensitivity():
    # Classe plus défavorable quand fy augmente (ε plus petit)
    low = P.classify("IPE500", 235, "compression")["section_class"]
    high = P.classify("IPE500", 355, "compression")["section_class"]
    assert high >= low


def test_buckling_curves_auto():
    ipe = P.buckling_curves("IPE300", 235)   # h/b=2 → y=a, z=b
    heb = P.buckling_curves("HEB200", 235)   # h/b=1 → y=b, z=c
    assert ipe["y"] == "a" and ipe["z"] == "b"
    assert heb["y"] == "b" and heb["z"] == "c"
    assert P.buckling_curves("UPN200", 235)["y"] == "c"


def test_upn_is_mono_symmetric():
    assert P.PROFILE_DATA["UPN200"]["mono"] is True
    assert P.PROFILE_DATA["IPE300"]["mono"] is False
