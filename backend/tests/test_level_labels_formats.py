"""Cotas impressas noutros formatos (processo AES/TZ, 23/11/2026): símbolo de laje Revit (cota + espessura separadas),
norma AES «b» (bruto = AS) / «f» (acabado, nunca AS) e Ai de lintéis/vigas separados do Ai das lajes."""
import ezdxf

from engines.metre.cross_layer_faces import level_labels


def _msp(items):
    doc = ezdxf.new(); msp = doc.modelspace()
    for layer, text, x, y in items:
        msp.add_text(text, dxfattribs={"layer": layer, "insert": (x, y)})
    return msp


def test_revit_slab_symbol_level_and_thickness():
    items = [("S-FLOR-SYMB", "22", 10 * i, 0) for i in range(4)] + [("S-FLOR-SYMB", "63.39", 10 * i, 0.4) for i in range(4)]
    lv = level_labels(_msp(items), 1.0)
    assert lv["dominant"] == {"as_plancher_haut_m": 63.39, "epaisseur_dalle_m": 0.22}


def test_aes_brut_is_as_and_finished_is_never_used():
    items = [("AES-Dalle-txt", "25", 5 * i, 0) for i in range(3)] + [("AES-Dalle-txt", "66.39b", 5 * i, 0.3) for i in range(3)] \
        + [("AES-Dalle-txt", "65.63f", 5 * i, 0.1) for i in range(5)]
    lv = level_labels(_msp(items), 1.0)
    assert lv["dominant"] == {"as_plancher_haut_m": 66.39, "epaisseur_dalle_m": 0.25}
    assert len(lv["finished_levels"]) == 5


def test_only_finished_levels_gives_no_as_and_says_so():
    lv = level_labels(_msp([("AES-Dalle-txt", "57.69f", i, 0) for i in range(4)]), 1.0)
    assert lv["dominant"] is None and "acabado" in lv["note"]


def test_lintel_and_beam_ai_are_not_slab_ai():
    items = [("AES-Linteau-txt", "LT(Ai:56.82)", 0, 0), ("AES-Poutre-txt", "(Ai:56.95)", 1, 0), ("AES-Tremie-txt", "Ai:54.12", 2, 0),
             ("TEXT", "Ai: 92,77 NGF", 3, 0)]
    lv = level_labels(_msp(items), 1.0)
    assert [a["ngf"] for a in lv["ai_texts"]] == [92.77]
    assert lv["ai_lintels"][0]["ngf"] == 56.82 and lv["ai_beams"][0]["ngf"] == 56.95 and lv["ai_other"][0]["ngf"] == 54.12


def test_two_isolated_tags_are_not_a_dominant_slab():
    items = [("AES-Dalle-txt", "25", 0, 0), ("AES-Dalle-txt", "67.19b", 0, 0.3), ("AES-Dalle-txt", "25", 9, 0), ("AES-Dalle-txt", "66.84b", 9, 0.3)]
    assert level_labels(_msp(items), 1.0)["dominant"] is None
