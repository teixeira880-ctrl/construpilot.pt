"""Rédacteur CCTP / DCE : sélection, rédaction (IA simulée), garde-fous, DOCX, DPGF et ZIP."""
import io
import json
import zipfile

import openpyxl
import pytest
from docx import Document

from engines import ai
from engines import cctp_redacteur as R
from engines.cctp_catalogue import LOTS

PROJET = {"nom": "Maison Dupont", "adresse": "12 rue des Lilas, 78800 Houilles", "maitre_ouvrage": "M. et Mme Dupont",
          "maitre_oeuvre": "Atelier X", "nature": "renovation", "phase": "DCE", "indice": "A"}


def _texte(docx_bytes: bytes) -> str:
    d = Document(io.BytesIO(docx_bytes))
    return "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)


def test_catalogue_coherent():
    codes = [l["code"] for l in LOTS]
    assert len(codes) == len(set(codes)) and [l["numero"] for l in LOTS] == sorted(l["numero"] for l in LOTS)
    plat = next(l for l in LOTS if l["code"] == "platrerie")
    assert plat["numero"] == 6 and any("25.41" in r for r in plat["refs"])
    for lot in LOTS:
        assert lot["refs"] and lot["ouvrages"] and lot["prescriptions"]
        for o in lot["ouvrages"]:
            assert o["variantes"] and o["unite"] and len(o["description"]) > 60
            texte, retirees = R.verifier_references(o["description"])
            assert not retirees, (lot["code"], o["code"], retirees)        # le catalogue ne cite que la liste blanche


def test_references_hors_liste_retirees():
    texte, retirees = R.verifier_references("Conforme au NF DTU 25.41, au DTU 99.9 et à la NF C 15-100.")
    assert "NF DTU 25.41" in texte and "NF C 15-100" in texte and "99.9" not in texte
    assert retirees == ["DTU 99.9"]


def test_selection_depuis_devis():
    lines = [{"designation": "Cloison placo 72/48", "qty": 45, "unit": "m2"},
             {"designation": "Démolition cloison briques", "qty": 10, "unit": "m2"},
             {"designation": "Faïence (mur) salle de bain", "qty": 20, "unit": "m2"},
             {"designation": "Mur parpaing 20 cm", "qty": 60, "unit": "m2"},
             {"kind": "section", "designation": "RDC"}]
    sel = {s["code"]: s for s in R.selection_depuis_devis(lines)}
    assert set(sel) == {"demolition", "platrerie", "sols_durs", "gros_oeuvre"}
    assert sel["platrerie"]["lignes"][0]["quantite"] == 45


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_rediger_catalogue_sans_ia():
    sel = [{"code": "platrerie", "ouvrages": ["cloison_98", "trappe"],
            "lignes": [{"designation": "Cloison 72/48 BA13", "unite": "m2", "quantite": 45, "localisation": "Chambres R+1"}]},
           {"code": "platrerie", "ouvrages": ["plafond_ba13"]}]                        # même lot deux fois : fusionné
    lots = await R.rediger(PROJET, sel, ia=False)
    assert len(lots) == 1 and lots[0]["mode"] == "catalogue"
    titres = [a["titre"] for a in lots[0]["articles"]]
    assert titres[0] == "CLOISONS DE DISTRIBUTION 72/48" and "TRAPPES DE VISITE" in titres
    art = lots[0]["articles"][0]
    assert art["localisation"] == "Chambres R+1" and art["variantes"][0]["quantite"] == 45
    chap = R.numeroter(lots[0])
    assert chap[0]["num"] == "6.2" and chap[0]["articles"][0]["variantes"][0]["num"] == "6.2.1.1"


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_rediger_ia_garde_fous(monkeypatch):
    async def fake(system, prompt, **kw):
        return json.dumps({
            "articles": [{"chapitre": "Cloisons", "titre": "Cloisons de distribution 72/48",
                          "description": "Cloison 72/48 conforme au NF DTU 25.41 et au DTU 77.7 inventé, plaques BA13 vissées.",
                          "localisation": "Chambres", "variantes": [{"libelle": "BA13", "unite": "m2", "quantite": 45},
                                                                    {"libelle": "Hydro", "unite": "m2", "quantite": 999}]}],
            "prescriptions_complementaires": [{"titre": "Site occupé", "texte": "Travaux en site occupé, phasage par pièce."}],
            "points_a_verifier": ["Hauteur sous plafond à confirmer"]})
    monkeypatch.setattr(ai, "_complete", fake)
    sel = [{"code": "platrerie", "ouvrages": ["trappe"], "lignes": [{"designation": "Cloison 72/48", "unite": "m2", "quantite": 45}]}]
    lot = (await R.rediger(PROJET, sel, ia=True))[0]
    assert lot["mode"] == "ia"
    a = lot["articles"][0]
    assert "NF DTU 25.41" in a["description"] and "77.7" not in a["description"]       # référence inventée retirée
    assert [v["quantite"] for v in a["variantes"]] == [45, None]                      # quantité non saisie refusée
    assert any(x["titre"] == "TRAPPES DE VISITE" for x in lot["articles"])            # article de base perdu → réintégré
    assert lot["complementaires"] == [("Site occupé", "Travaux en site occupé, phasage par pièce.")]
    assert any("DTU 77.7" in p for p in lot["points"]) and "Hauteur sous plafond à confirmer" in lot["points"]


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_rediger_ia_en_panne_repli(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("Service IA momentanément indisponible")
    monkeypatch.setattr(ai, "_complete", boom)
    lot = (await R.rediger(PROJET, [{"code": "peinture"}], ia=True))[0]
    assert lot["mode"] == "catalogue" and len(lot["articles"]) == 4                  # lot coché sans détail : tous les articles types
    assert any("indisponible" in p for p in lot["points"])


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_fichiers_et_zip():
    sel = [{"code": "platrerie", "ouvrages": ["cloison_98"], "lignes": [{"designation": "Cloison 72/48", "unite": "m2", "quantite": 45}]},
           {"code": "electricite", "ouvrages": ["prises"]}]
    lots = await R.rediger(PROJET, sel, ia=False)
    files = R.fichiers_dossier(PROJET, lots, {"company_name": "Entreprise Test"})
    noms = [f[0] for f in files]
    assert noms[0].startswith("CCTP_Lot-06_") and noms[1].startswith("CCTP_Lot-13_") and noms[2] == "DPGF_Maison-Dupont.xlsx"
    t = _texte(files[0][1])
    for attendu in ("C.C.T.P.", "LOT N°06", "6.1 PRESCRIPTIONS PARTICULIÈRES", "6.1.1.1 Objet de la prestation", "6.1.1.3 Connaissance du projet",
                    "Travaux en site existant", "NF DTU 25.41", "Localisation :", "Quantité indicative : 45 m2", "Entreprise Test"):
        assert attendu in t, attendu
    wb = openpyxl.load_workbook(io.BytesIO(files[2][1]))
    assert wb.sheetnames == ["Récapitulatif", "Lot 06", "Lot 13"]
    rows = [r for r in wb["Lot 06"].iter_rows(values_only=True) if r and r[0] and str(r[0]).count(".") == 3]
    assert rows[0][:4] == ("6.2.1.1", "Cloison 72/48", "m2", 45) and str(rows[0][5]).startswith("=IF(")
    z = zipfile.ZipFile(io.BytesIO(R.zip_dossier(PROJET, files)))
    assert sorted(z.namelist()) == sorted(["DCE_Maison-Dupont/2_CCTP/" + noms[0], "DCE_Maison-Dupont/2_CCTP/" + noms[1],
                                           "DCE_Maison-Dupont/3_DPGF/DPGF_Maison-Dupont.xlsx",
                                           "DCE_Maison-Dupont/Note-de-verification.txt"])


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
@pytest.mark.parametrize("code", [l["code"] for l in LOTS])
async def test_chaque_lot_genere_un_docx(code):
    lot = (await R.rediger({"nom": "Test", "nature": "neuf"}, [{"code": code}], ia=False))[0]
    data = R.cctp_docx({"nom": "Test", "nature": "neuf"}, lot)
    assert data[:2] == b"PK" and "Travaux en site existant" not in _texte(data)


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_routes_dossier_complet(monkeypatch):
    import asyncio
    import copy

    from fastapi import HTTPException
    from routes import cctp as C
    from test_platform_supervisor import USER, Database

    database = Database()
    database.pro_documents.rows = [{"doc_id": "d1", "user_id": "owner", "lines": [
        {"kind": "line", "designation": "Peinture murs", "qty": 120, "unit": "m2"}]}]
    monkeypatch.setattr(C, "db", database)

    async def no_branding(uid):
        return {"company_name": "Entreprise Test"}
    monkeypatch.setattr(C, "_branding", no_branding)
    body = C.DossierIn(projet=C.Projet(nom="Maison Dupont", nature="renovation"), doc_id="d1", ia=False,
                       lots=[C.LotSel(code="platrerie", ouvrages=["cloison_98"])])
    out = await C.creer(body, copy.deepcopy(USER))
    await asyncio.gather(*list(C._TASKS))
    d = await C.lire(out["dossier_id"], USER)
    assert d["status"] == "done" and [l["numero"] for l in d["lots"]] == [6, 10]
    assert "data_b64" not in d["fichiers"][0]
    resp = await C.fichier(out["dossier_id"], 0, USER)
    assert resp.body[:2] == b"PK" and "wordprocessingml" in resp.media_type
    z = await C.zip_complet(out["dossier_id"], USER)
    assert z.media_type == "application/zip"
    with pytest.raises(HTTPException):
        await C.lire(out["dossier_id"], {"user_id": "autre"})                        # dossier d'un autre compte
    with pytest.raises(HTTPException):
        await C.creer(C.DossierIn(projet=C.Projet(nom="X"), lots=[C.LotSel(code="inconnu")]), USER)


# ---------------------------------------------------------------- modèle architecte / DCE complet
PIECES = [{"nom": "Entrée", "niveau": "RDC", "surface": 6}, {"nom": "Cuisine", "niveau": "RDC", "surface": 14},
          {"nom": "Séjour", "niveau": "RDC", "surface": 38}, {"nom": "WC", "niveau": "RDC"},
          {"nom": "Salle de bain 1", "niveau": "R+1", "surface": 5}, {"nom": "Chambre 1", "niveau": "R+1", "surface": 12},
          {"nom": "Chambre 2", "niveau": "R+1", "surface": 11, "extras": ["1 alimentation volet roulant"]}]


def test_equipements_nfc15100_par_piece():
    from engines import cctp_pieces as P
    eq = lambda nom, s=None: dict((lib, q) for q, lib in P.equipements_electricite({"nom": nom, "surface": s}))
    assert eq("Séjour", 20)["PC 16 A+T"] == 5 and eq("Séjour", 30)["PC 16 A+T"] == 7
    assert eq("Séjour", 30)["Prises RJ45 juxtaposées"] == 2
    cui = eq("Cuisine", 12)
    assert cui["PC 16 A+T au-dessus du plan de travail"] == 4 and cui["PC 16 A+T"] == 2
    assert eq("Cuisine", 3)["PC 16 A+T au-dessus du plan de travail"] == 3
    assert "Sortie de câble 32 A+T pour appareil de cuisson" in cui
    assert eq("Chambre 3")["PC 16 A+T"] == 3 and eq("Chambre 3")["Prise RJ45"] == 1
    assert list(eq("WC")) == ["Point d'éclairage en plafond équipé DCL, commandé depuis l'entrée de la pièce"]
    assert "PC 16 A+T" not in eq("Dégagement", 3) and eq("Dégagement", 6)["PC 16 A+T"] == 1
    assert P.type_piece({"nom": "Suite parentale"}) == "chambre" and P.type_piece({"nom": "SDB 3"}) == "sdb"


@pytest.mark.asyncio      # construpilot.pt : pytest.ini sans asyncio_mode = auto
async def test_dce_modele_architecte():
    projet = {**PROJET, "nature": "neuf", "style": "architecte", "tce": True, "pieces": PIECES,
              "intervenants": {"architecte": "Atelier Test", "bet_fluides": "BET Fluides Test"},
              "plans": ["Plan RDC", "Plan électricité RDC"], "consultation": {"date_limite": "15/12/2026"}}
    sel = [{"code": "electricite", "numero": 4},
           {"code": "cvc", "numero": 5, "titre": "CVC – Plomberie", "inclure": ["plomberie"], "ouvrages": ["vmc"]},
           {"code": "platrerie", "numero": 6, "titre": "Aménagements intérieurs", "inclure": ["peinture", "sols_durs"],
            "ouvrages": ["cloison_72"]},
           {"code": "peinture", "lignes": [{"designation": "Peinture murs satinée", "unite": "m2", "quantite": 320}]}]
    lots = await R.rediger(projet, sel, ia=False)
    assert [(l["numero"], l["titre"]) for l in lots] == [(4, "Électricité – Courants faibles"), (5, "CVC – Plomberie"),
                                                        (6, "Aménagements intérieurs")]                # peinture fusionnée dans le lot 6
    elec, cvc, amen = lots
    titres = [a["titre"] for a in elec["articles"]]
    assert "SÉJOUR (RDC)" in titres and "ÉQUIPEMENTS COMMUNS DU LOGEMENT" in titres
    assert "PRISES DE COURANT" not in titres                                   # remplacé par les articles par pièce
    sej = next(a for a in elec["articles"] if a["titre"] == "SÉJOUR (RDC)")
    assert {v["libelle"]: v["quantite"] for v in sej["variantes"]}["PC 16 A+T"] == 7
    ch2 = next(a for a in elec["articles"] if a["titre"] == "CHAMBRE 2 (R+1)")
    assert "- 1 alimentation volet roulant" in ch2["description"]
    assert any(a["titre"] == "WC (RDC)" for a in cvc["articles"])                 # plomberie par pièce dans le lot regroupé
    assert any("NF DTU 68.3" in r for r in cvc["refs"]) and any("NF DTU 60.1" in r for r in cvc["refs"])
    assert any(v["quantite"] == 320 for a in amen["articles"] for v in a["variantes"])
    files = R.fichiers_dossier(projet, lots, {"company_name": "Atelier Test"})
    noms = [f[0] for f in files]
    assert noms[:3] == ["00_Page-de-garde-DCE_Maison-Dupont.docx", "RC_Reglement-de-consultation_Maison-Dupont.docx",
                        "CCTP_Lot-00_Clauses-generales-TCE_Maison-Dupont.docx"]
    garde, rc, tce = (_texte(f[1]) for f in files[:3])
    assert "DOSSIER DE CONSULTATION DES ENTREPRISES" in garde and "BET Fluides Test" in garde and "Plan électricité RDC" in garde
    assert "CCTP Lot n°06 — Aménagements intérieurs" in garde
    assert "15/12/2026" in rc and "L8222-1" in rc and "90 jours" in rc
    assert "1792-6" in tce and "L241-1" in tce and "pénalités de retard éventuelles sont fixées au CCAP" in tce
    t4 = _texte(files[3][1])
    for attendu in ("4.1 GÉNÉRALITÉS", "Objet de la prestation", "Connaissance des clauses générales TCE",
                    "Prestations à la charge du présent lot", "Position :", "DESCRIPTIF DES TRAVAUX",
                    "Document établi par Atelier Test", "7 PC 16 A+T"):
        assert attendu in t4 or attendu in "\n".join(p.text for s in Document(io.BytesIO(files[3][1])).sections
                                                     for p in s.footer.paragraphs), attendu
    z = zipfile.ZipFile(io.BytesIO(R.zip_dossier(projet, files)))
    assert "DCE_Maison-Dupont/1_Pieces-administratives/RC_Reglement-de-consultation_Maison-Dupont.docx" in z.namelist()
    assert "DCE_Maison-Dupont/2_CCTP/CCTP_Lot-00_Clauses-generales-TCE_Maison-Dupont.docx" in z.namelist()
