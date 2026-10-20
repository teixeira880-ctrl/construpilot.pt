"""Détail de montage de menuiserie : toutes les combinaisons usuelles se dessinent, cotes de réservation cohérentes, FR/PT, refus explicites."""
import pymupdf
import pytest

from engines import baie_detail as B

CASES = [
    {},
    {"ouvrage": "fenetre", "pose": "tunnel", "coffre": "tunnel"},
    {"ouvrage": "fenetre", "pose": "applique_int", "coffre": "aucun", "materiau": "alu"},
    {"ouvrage": "fenetre", "pose": "feuillure", "coffre": "tunnel", "isolation": "aucune", "materiau": "bois", "mur": "brique"},
    {"ouvrage": "fenetre", "pose": "renovation", "coffre": "exterieur", "isolation": "aucune", "mur": "pierre", "mur_ep_mm": 450},
    {"ouvrage": "porte_fenetre", "pose": "tunnel", "coffre": "interieur", "materiau": "alu"},
    {"ouvrage": "fenetre", "pose": "applique_ext", "coffre": "monobloc", "isolation": "ite", "mur": "beton", "mur_ep_mm": 180},
    {"ouvrage": "coulissant", "pose": "tunnel", "coffre": "tunnel", "isolation": "ite", "materiau": "alu"},
    {"ouvrage": "porte_fenetre", "pose": "applique_ext", "coffre": "aucun", "isolation": "ite", "materiau": "alu", "seuil_pmr": False},
    {"ouvrage": "fenetre", "pose": "tunnel", "coffre": "tunnel", "lang": "pt", "mur": "brique"},
]


@pytest.mark.parametrize("params", CASES)
def test_every_configuration_renders_two_real_views(params):
    out = B.render(params)
    doc = pymupdf.open(stream=out["pdf"], filetype="pdf")
    assert doc.page_count == 2
    text = doc[0].get_text() + doc[1].get_text()
    word = "CORTE" if params.get("lang") == "pt" else "COUPE"
    assert f"{word} VERTICAL" in text and f"{word} HORIZONTAL" in text
    assert "semelle" not in text.lower() and "drain" not in text.lower()          # plus de gabarit « mur sur fondation »
    assert out["png_vertical"].startswith(b"\x89PNG") and out["png_horizontal"].startswith(b"\x89PNG")


def test_monobloc_door_window_reservation_and_roll():
    d = B.Detail({"ouvrage": "porte_fenetre", "pose": "applique_int", "coffre": "monobloc", "hauteur_mm": 2150, "largeur_mm": 1400})
    d.vertical()
    kv = dict(d.key_values())
    assert 160 < d.roll < 175                                          # tablier 2,15 m enroulé ≈ Ø 167
    assert d.Hc >= d.roll + 40
    assert d.res_h == pytest.approx(d.hb)                              # porte-fenêtre : réservation depuis la dalle brute
    assert kv["Largeur de réservation (maçonnerie)"] == "1330 mm"      # applique : 1400 − 2 × 35
    assert any("Bloc-baie" in n for n in d.notes_list())


def test_tunnel_window_reservation_includes_box_height():
    d = B.Detail({"ouvrage": "fenetre", "pose": "tunnel", "coffre": "tunnel", "hauteur_mm": 1350, "allege_mm": 950})
    d.vertical()
    # réservation = menuiserie + cales/assise (5) + coffre + jeu (10) + hauteur d'appui (60) sous le dormant
    assert d.res_h == pytest.approx(1350 + 5 + d.Hc + 10 + 60)


def test_incompatible_combination_is_refused_with_explanation():
    with pytest.raises(ValueError, match="incompatible"):
        B.render({"pose": "tunnel", "coffre": "monobloc"})
    with pytest.raises(ValueError, match="ITE"):
        B.render({"pose": "applique_ext", "coffre": "aucun", "isolation": "iti"})


def test_defaults_are_declared_as_hypotheses():
    out = B.render({"ouvrage": "fenetre", "pose": "tunnel", "coffre": "aucun", "hauteur_mm": 1250, "largeur_mm": 1000})
    assert "par défaut" in out["notes"][0] and "hauteur" not in out["notes"][0].split(":")[1]


def test_tool_schema_accepts_a_full_call():
    args = {"ouvrage": "porte_fenetre", "pose": "applique_int", "coffre": "monobloc", "isolation": "iti", "materiau": "pvc", "mur": "parpaing",
            "mur_ep_mm": 200, "isolant_ep_mm": None, "isolant_ext_ep_mm": None, "hauteur_mm": 2150, "largeur_mm": None, "allege_mm": None,
            "linteau_h_mm": None, "dalle_ep_mm": None, "hauteur_coffre_mm": None, "seuil_pmr": True, "lang": "fr"}
    from jsonschema import Draft202012Validator
    Draft202012Validator(B.WINDOW_TOOL["parameters"]).validate(args)
    assert B.render(args)["params"]["hauteur_mm"] == 2150


def test_pt_endpoint_defaults_to_portuguese():
    import asyncio
    from routes.tools import PormenorIn, pormenor_caixilharia
    out = asyncio.run(pormenor_caixilharia(PormenorIn(params={"ouvrage": "fenetre", "pose": "tunnel", "coffre": "tunnel"})))
    assert out["title"].startswith("Janela") and out["png_vertical_b64"]
