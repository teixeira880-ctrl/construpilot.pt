"""Lot 62 — un prix de bibliothèque n'est retenu que pour le même type de travail."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import engines.assistant_quote_pricing as qp  # noqa: E402


def test_work_family():
    assert qp._work_family("Demolição de azulejos de parede") == "demolition"
    assert qp._work_family("Dépose de faïence murale") == "demolition"
    assert qp._work_family("Azulejo de parede") == "work"
    assert qp._work_family("Instalação e desmontagem de estaleiro") == "site"


def test_demolition_not_priced_with_supply_item(monkeypatch):
    monkeypatch.setattr(qp, "_find_price_lot62_base",
                        lambda d, u, s: {"unit_price_ht": 50.7, "price_reference_label": "Azulejo de parede"})
    assert qp.find_price("Demolição de azulejos de parede", "m²", []) is None
    assert qp.find_price("Revestimento cerâmico de parede", "m²", [])["unit_price_ht"] == 50.7
    monkeypatch.setattr(qp, "_find_price_lot62_base",
                        lambda d, u, s: {"unit_price_ht": 14.5, "price_reference_label": "Instalação e desmontagem de estaleiro"})
    assert qp.find_price("Pintura de teto", "m²", []) is None
