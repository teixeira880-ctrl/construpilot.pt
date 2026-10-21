"""Iter 54 — Régression du parseur de prix Tavily.

Vérifie que le parseur :
- extrait tous les prix visibles dans le snippet,
- rejette les micro-prix (< 3 €) et les prix aberrants (> 3000 €),
- retourne le plus bas plausible en cas d'ambiguïté.
"""
from engines.price_search import _parse_all_prices, _pick_plausible_price, _parse_price


def test_parse_all_prices_multi():
    text = "Peinture 8,99 € HT ou 10,98 € TTC (note 4,5)"
    prices = _parse_all_prices(text)
    assert 8.99 in prices
    assert 10.98 in prices
    # 4,5 sans '€' n'est pas capturé — c'est la valeur normalisée uniquement quand suivie/précédée de €
    assert 4.5 not in prices


def test_pick_plausible_filters_micro_and_aberrant():
    # Aberrant (>3000 €) et micro-prix (<3 €) doivent être filtrés
    assert _pick_plausible_price([8000.0, 1.5]) is None
    # Micro-prix filtré, on retient le suivant
    assert _pick_plausible_price([2.7, 3.24]) == 3.24
    # Cas valide multiple : on retient le plus bas
    assert _pick_plausible_price([8.99, 27.9, 49.9]) == 8.99


def test_parse_price_end_to_end():
    # BA13 réel : contient plusieurs prix
    text = "Plaque BA13 250x120 — À partir de 2,70 € HT ou 3,24 € TTC. Livraison 39 €."
    price = _parse_price(text)
    # 2.70 est < 3 (filtré), 3.24 retenu, 39 possible mais > 3.24 → min = 3.24
    assert price == 3.24


def test_parse_price_no_valid():
    assert _parse_price("Note 4,5/5 — plus de 2 000 avis") is None
    assert _parse_price("") is None
    assert _parse_price(None) is None


def test_parse_price_range_boundaries():
    from engines.price_search import PRICE_MIN_EUR, PRICE_MAX_EUR
    # Aux bornes
    assert _pick_plausible_price([PRICE_MIN_EUR]) == PRICE_MIN_EUR
    assert _pick_plausible_price([PRICE_MAX_EUR]) == PRICE_MAX_EUR
    # Juste sous / au-dessus
    assert _pick_plausible_price([PRICE_MIN_EUR - 0.01]) is None
    assert _pick_plausible_price([PRICE_MAX_EUR + 0.01]) is None
