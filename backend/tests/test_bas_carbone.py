"""Carta de Obra de Baixo Carbono (PT) : cálculo, leitura de documentos (sem IA), controlos, exportações, rotas e estudo completo."""
import io
import json
from datetime import date
from pathlib import Path

import openpyxl
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from test_platform_supervisor import Database, USER
from engines.bas_carbone import calculer, nouveau_dossier, documents as D, export_xlsx, export_pdf, import_xlsx, referentiel as R
from engines.bas_carbone.depuis_etude import dossier_depuis_etude
from routes import bas_carbone as RB

DAP = """Declaração Ambiental de Produto (DAP) — EN 15804+A2 — Programa DAPHabitat
Betão pronto C25/30 CEM III/A — Betões do Norte, S.A.
Unidade declarada : 1 m³ de betão
N.º de registo : DAP 012:2024
Válida até : 12/03/2029
Alterações climáticas - total   kg CO2 eq   1,62E+02
"""
FDES_FR_KG = "FDES NF EN 15804\nAcier d'armature recyclé\nUnité fonctionnelle : 1 kg d'acier\nChangement climatique - total kg CO2 eq 7,2E-01\n"
GUIA = "GUIA DE REMESSA N.º GR-2026/0042\nLocal de carga : Central de betão, 4470-000 Maia\nBetão C25/30 CEM III/A 32,5 m3\nDistância percorrida 18 km\n"
EGAR = "e-GAR — Guia eletrónica de acompanhamento de resíduos (SILiAmb)\nCódigo LER 17 01 07\nQuantidade 4,2 t\nOperação R5\n"
FATURA = "Fatura n.º 123\nGasóleo colorido e marcado 1 200 litros\nHVO100 300 litros\n"


async def lire(txt, nom):
    return await D.lire(txt.encode(), nom, use_ai=False)


def dossier():
    d = nouveau_dossier("Moradia teste", "Moradia unifamiliar", 1000)
    d["materiaux"][0]["quantite_prevue"] = 30
    return d


def codes(res):
    return {c["code"] for c in res["controles"]}


# ---------------------------------------------------------------------------------------------------------------- cálculo
def test_sem_meta_legal_em_portugal():
    assert all(R.seuil_ic(t, "") is None for t in R.TYPOLOGIES)
    res = calculer(dossier())
    assert res["totaux"]["seuil"] is None and "PRJ-02" in codes(res)
    d = dossier()
    d["projet"]["seuil_ic"] = 600
    res = calculer(d)
    assert res["totaux"]["seuil"] == 600 and res["projet"]["seuil_source"].startswith("Meta introduzida")


def test_sem_dap_nenhum_ganho():
    b = calculer(dossier())["materiaux"][0]
    assert b["poids_ref"] == b["poids_reel"] == 30 * 250 and b["gain"] == 0


def test_eletricidade_fator_apa():
    e = next(x for x in nouveau_dossier()["emissions"] if x["id"] == "elec_base_vie")
    assert e["fe"] == 0.107


def test_estado_da_carta_automatico():
    d = dossier()
    c03 = next(c for c in d["charte"] if c["id"] == "c03")
    c03["realise"] = 140
    assert next(c for c in calculer(d)["charte"] if c["id"] == "c03")["statut"] == "Não conforme"
    c03["realise"] = 60
    assert next(c for c in calculer(d)["charte"] if c["id"] == "c03")["statut"] == "Conforme"


# ---------------------------------------------------------------------------------------------------------------- leitura
@pytest.mark.asyncio
async def test_dap_portuguesa_lida_por_regras():
    doc = await lire(DAP, "dap.txt")
    ex = doc["extrait"]
    assert doc["type"] == "fdes" and ex["fe_fdes"] == 162 and ex["fdes_unite"] == "m³"
    assert ex["fdes_validite"] == "2029-03-12" and ex["famille"] == "beton"


@pytest.mark.asyncio
async def test_fdes_francesa_tambem_aceite():
    d = dossier()
    D.appliquer(d, await lire(FDES_FR_KG, "acier.txt"))
    assert next(m for m in d["materiaux"] if m["code"] == "acier")["fe_fdes"] == pytest.approx(720)


@pytest.mark.asyncio
async def test_documentos_preenchem_e_retiram_se():
    d = dossier()
    docs = [await lire(x, n) for x, n in ((DAP, "dap.txt"), (GUIA, "guia.txt"), (EGAR, "egar.txt"), (FATURA, "fatura.txt"))]
    assert [x["type"] for x in docs] == ["fdes", "bon_livraison", "bsd", "carburant"]
    for x in docs:
        D.appliquer(d, x)
    res = calculer(d, date(2026, 11, 25))
    b = res["materiaux"][0]
    assert b["fe_fdes"] == 162 and b["quantite"] == 32.5 and b["distance_km"] == 18
    assert res["kpi"]["taux_valorisation"] == 100 and res["kpi"]["part_engins_bas_carbone"] == 20
    for x in docs:
        D.retirer(d, x["doc_id"])
    assert d["materiaux"][0]["fe_fdes"] is None and d["materiaux"][0]["quantite_livree"] is None
    assert all(e["quantite"] == 0 for e in d["emissions"]) and not d["documents"]


@pytest.mark.asyncio
async def test_guia_nunca_contada_duas_vezes():
    d = dossier()
    D.appliquer(d, await lire(GUIA, "guia.txt"))
    D.appliquer(d, await lire(GUIA + "\ncópia", "guia_scan.txt"))
    assert d["materiaux"][0]["quantite_livree"] == 32.5
    assert any(x["statut"] == "duplicado" for x in d["documents"])


@pytest.mark.asyncio
async def test_desvios_aos_imperativos():
    d = dossier()
    D.appliquer(d, await lire(DAP.replace("1,62E+02", "1,62E+00"), "dap.txt"))
    D.appliquer(d, await lire(GUIA.replace("18 km", "160 km").replace("32,5", "45"), "guia.txt"))
    res = calculer(d, date(2030, 1, 1))
    assert {"MAT-04", "MAT-06", "MAT-08", "MAT-12"} <= codes(res)
    assert res["controles"][0]["niveau"] == "bloquant"


def test_valor_ia_ausente_rejeitado():
    out, notes = D.fusionner({"type": "fdes", "famille": "beton"}, {"fe_fdes": 170}, DAP)
    assert out.get("fe_fdes") is None and any("rejeitado" in n for n in notes)


# ---------------------------------------------------------------------------------------------------------------- exportações
@pytest.mark.asyncio
async def test_exportacoes_excel_e_pdf_em_portugues():
    d = dossier()
    D.appliquer(d, await lire(DAP, "dap.txt"))
    res = calculer(d)
    wb = openpyxl.load_workbook(io.BytesIO(export_xlsx.construire(res, "Empresa")))
    assert wb.sheetnames == ["Sintese", "Grelha_Carta", "Materiais", "Emissoes_Obra", "Controlos", "Documentos", "Metodo_Fontes"]
    assert wb["Materiais"]["L3"].value.startswith("=E3*") and wb["Materiais"]["H3"].value == 162
    assert "Materiais!K" in wb["Sintese"]["G5"].value and wb["Materiais"]["B2"].value == "Família de Materiais"
    pdf = export_pdf.construire(res, None, "Empresa")
    assert pdf[:4] == b"%PDF" and len(pdf) > 20000


def test_importa_o_modelo_frances_v3():
    src = Path(__file__).resolve().parent / "fixtures" / "Charte_Chantier_Bas_Carbone-v3.xlsx"
    d = nouveau_dossier()
    import_xlsx.importer(d, src.read_bytes())
    assert len(d["materiaux"]) == 14 and [m["code"] for m in d["materiaux"]][:3] == ["beton", "acier", "bois"]
    assert all(m["lot"] in R.LOTS and m["typologie"] in R.TYPOLOGIES_MATERIAU for m in d["materiaux"])
    assert d["projet"]["typologie"] == "Habitação coletiva"


def test_reimporta_a_propria_exportacao():
    d = dossier()
    d["emissions"][0]["quantite"] = 500
    data = export_xlsx.construire(calculer(d), "E")
    d2 = nouveau_dossier()
    import_xlsx.importer(d2, data)
    assert d2["materiaux"][0]["quantite_prevue"] == 30 and d2["emissions"][0]["quantite"] == 500


# ---------------------------------------------------------------------------------------------------------------- estudo completo
def test_estudo_completo_pt_preenchido_pela_medicao():
    from engines.bet_core import model, structure, timber, mep, devis, thermal
    raw = json.loads((Path(__file__).resolve().parents[1] / "engines/bet_core/cases/moradia_pt_demo.json").read_text(encoding="utf-8"))
    m = model.from_dict(raw)
    r = structure.compute(m)
    tim = timber.compute(m, r["loads"])
    lines = devis.build_lines(m, r, tim, mep.electrical(m), mep.plumbing(m))
    d = dossier_depuis_etude(raw, r, tim, lines, thermal.sref(m))
    q = {x["code"]: x["quantite_prevue"] for x in d["materiaux"]}
    assert q["beton"] == r["quantities"]["concrete_total_m3"]
    assert q["acier"] == pytest.approx(r["quantities"]["steel_total_kg"] / 1000)
    assert all(x["origine"] == "étude" and x["typologie"] == "Standard" for x in d["materiaux"])
    assert calculer(d)["projet"]["typologie"] == "Moradia unifamiliar"


# ---------------------------------------------------------------------------------------------------------------- rotas
@pytest.fixture
def db(monkeypatch):
    database = Database()
    monkeypatch.setattr(RB, "db", database)
    database.chantiers.rows = [{"chantier_id": "c1", "user_id": "owner", "name": "Moradia Silva", "address": "", "city": ""},
                               {"chantier_id": "c2", "user_id": "outro", "name": "Outro"}]

    async def no_geo(dossier, adresse):
        return []
    monkeypatch.setattr(D, "completer_distances", no_geo)
    real = D.lire

    async def lire_sem_ia(data, nom, use_ai=True):
        return await real(data, nom, use_ai=False)
    monkeypatch.setattr(D, "lire", lire_sem_ia)

    async def upload(f, kind="any", max_mb=None, allowed_ext=None):
        return await f.read()
    monkeypatch.setattr(RB, "read_upload", upload)
    return database


def up(txt, nom):
    return UploadFile(io.BytesIO(txt.encode()), filename=nom)


@pytest.mark.asyncio
async def test_rotas_deposito_controlo_exportacao(db):
    out = await RB.get_bas_carbone("c1", USER)
    assert out["dossier"]["projet"]["nom"] == "Moradia Silva"
    out = await RB.upload_documents("c1", [up(DAP, "dap.txt"), up(GUIA, "guia.txt")], USER)
    assert [x["statut"] for x in out["lus"]] == ["lido", "lido"]
    b = out["resultats"]["materiaux"][0]
    assert b["fe_fdes"] == 162 and b["quantite"] == 32.5
    out = await RB.delete_document("c1", out["dossier"]["documents"][1]["doc_id"], USER)
    assert out["resultats"]["materiaux"][0]["quantite_livree"] is None
    resp = await RB.export("c1", "pdf", USER)
    assert resp.media_type == "application/pdf" and "Carta-baixo-carbono" in resp.headers["content-disposition"]


@pytest.mark.asyncio
async def test_rotas_isolamento_e_validacao(db):
    with pytest.raises(HTTPException) as e:
        await RB.get_bas_carbone("c2", USER)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        await RB.update_bas_carbone("c1", RB.MajIn(projet=RB.ProjetIn(typologie="Castelo")), USER)
    out = await RB.update_bas_carbone("c1", RB.MajIn(projet=RB.ProjetIn(sref_m2=120, seuil_ic=500), emissions={"gnr": 500},
                                                     charte={"c03": {"realise": 40}}), USER)
    assert out["resultats"]["totaux"]["seuil"] == 500 and out["resultats"]["totaux"]["chantier"] == 1580
    assert next(c for c in out["resultats"]["charte"] if c["id"] == "c03")["statut"] == "Conforme"


@pytest.mark.asyncio
async def test_distancia_media_ponderada_e_alerta_por_entrega():
    d = dossier()
    D.appliquer(d, await lire(GUIA, "g1.txt"))
    g2 = await lire(GUIA.replace("0042", "0057").replace("32,5", "10").replace("18 km", "160 km"), "g2.txt")
    D.appliquer(d, g2)
    res = calculer(d)
    assert res["materiaux"][0]["distance_km"] == pytest.approx(round((32.5 * 18 + 10 * 160) / 42.5, 1))
    assert "MAT-13" in codes(res)
    D.retirer(d, g2["doc_id"])
    assert d["materiaux"][0]["distance_km"] == 18
