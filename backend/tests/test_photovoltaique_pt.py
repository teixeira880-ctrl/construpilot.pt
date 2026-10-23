"""Fotovoltaico (versão PT)."""
from engines.calc_lots import photovoltaique as P


def test_pt_por_defeito():
    r = P.calculer({"puissance_kwc": 4, "code_postal": "8000-100", "consommation_kwh": 4000})
    assert r["pays"] == "pt" and r["productible"] > 1600
    o = P.note({"puissance_kwc": 4, "code_postal": "4000-123", "consommation_kwh": 4000})
    assert o["pdf"][:4] == b"%PDF" and o["titre"] == "Pré-dimensionamento fotovoltaico"
