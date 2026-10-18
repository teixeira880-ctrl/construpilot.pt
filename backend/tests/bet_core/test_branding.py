"""Dossier aux couleurs de l'entreprise : nom et logo sur la couverture, les en-têtes et chaque cartouche."""
import base64
import io
import json
from pathlib import Path

import pymupdf
from PIL import Image

from engines.bet_core import brand, pipeline

CASE = json.loads((Path(__file__).parents[2] / "engines/bet_core/cases/la_courneuve.json").read_text(encoding="utf-8"))


def _logo():
    buf = io.BytesIO()
    Image.new("RGB", (400, 120), (20, 54, 92)).save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_branded_dossier(tmp_path):
    b = {"company_name": "ENTREPRISE TEST", "contact_line": "1 rue de l'Essai 75000 Paris", "siret": "123", "accent_color": "#7A1F3D",
         "logo_b64": _logo(), "footer_text": "ENTREPRISE TEST — SAS"}
    res = pipeline.run(CASE, tmp_path, branding=b, stem="T")
    doc = pymupdf.open(res["files"]["pdf"])
    assert "ENTREPRISE TEST" in doc[0].get_text() and doc[0].get_images()          # couverture : nom + logo
    plan = next(p for p in doc if "GO-01" in p.get_text())
    assert "ENTREPRISE TEST" in plan.get_text() and plan.get_images()               # cartouche des planches
    assert brand.get().name == "ConstruPilot"                                          # état de rendu remis à zéro


def test_bad_logo_falls_back_to_name():
    br = brand.from_branding({"company_name": "X", "logo_b64": "pas-une-image"})
    assert br.logo is None and br.name == "X"


def test_french_project_in_portuguese_keeps_french_norms(tmp_path):
    res = pipeline.run(CASE, tmp_path, lang="pt", stem="T")
    t = " ".join(p.get_text() for p in pymupdf.open(res["files"]["pdf"]))
    assert "NF EN 1992" in t and "B500B" in t and "A500NR" not in t
