"""13/11: estrutura metálica medida em ml, nunca m² (caso real: pilares/vigas/correias/contraventamento = área da cobertura)."""
from engines import quote_units as Q


def _lines(*rows):
    return {"lines": [{"designation": d, "unit": u} for d, u in rows]}


def test_steel_linear_elements_in_m2_are_rejected():
    bad = Q.bad_linear_lines(_lines(("Pilares em perfis HEA/HEB", "m²"), ("Vigas e travessas principais IPE/HEA", "m²"),
                                    ("Correias de cobertura (perfis Z/C)", "m²"), ("Contraventamento (tubo/perfil angular)", "m2"),
                                    ("Pannes de toiture Z", "m²")))
    assert len(bad) == 5
    assert "ml" in Q.message(bad, "pt") and "ml" in Q.message(bad, "fr")


def test_surfaces_and_correct_units_are_accepted():
    assert Q.bad_linear_lines(_lines(("Cobertura painel sanduíche", "m²"), ("Fachada painel sanduíche", "m²"),
                                     ("Laje de piso BA e=15 cm", "m²"), ("Tratamento de superfície dos perfis", "m²"),
                                     ("Pilares HEA 200", "ml"), ("Vigas IPE 300", "kg"), ("Chumbadouros/chapas de base", "vg"))) == []
