"""Vento / neve (AN PT) e acessibilidade (DL 163/2006) — versão PT."""
import pytest

from engines.calc_lots import accessibilite as A
from engines.calc_lots import couverture as C


def test_vento_neve_pt():
    assert C.vent({"categorie_terrain": "III", "hauteur_m": 10})["ce"] == pytest.approx(1.71, abs=0.01)
    assert C.vent({"altitude_m": 700})["vb0"] == 30
    assert C.neige({"zona_neve": "Z1", "altitude_m": 900})["sk_kn_m2"] == pytest.approx(0.3 * (1 + 1.8 ** 2))
    o = C.note({"vent": {"hauteur_m": 8}})
    assert o["pdf"][:4] == b"%PDF" and o["titre"].startswith("Nota de cobertura")


def test_acessibilidade_pt():
    r = A.verifier({"mesures": {"pente_rampe_pct": 6, "longueur_rampe_m": 9, "desnivel_rampa_m": 0.54, "porte_entree_utile_m": 0.90}})
    assert r["contexte"] == "pt" and all(c["ok"] for c in r["controles"] if c["ok"] is not None)
