"""Redator de Caderno de Encargos (PT) : seleção, redação (IA simulada), salvaguardas, DOCX, mapa de quantidades, ZIP."""
import io
import json
import zipfile

import openpyxl
import pytest
from docx import Document

from engines import ai
from engines import cctp_pieces as P
from engines import cctp_redacteur as R
from engines.cctp_catalogue import LOTS

PROJETO = {"nom": "Moradia Silva", "adresse": "Rua das Flores, 12, 4700-000 Braga", "maitre_ouvrage": "Sr. e Sra. Silva",
           "maitre_oeuvre": "Atelier X", "nature": "renovation", "phase": "Concurso", "indice": "A"}


def _texto(docx_bytes: bytes) -> str:
    d = Document(io.BytesIO(docx_bytes))
    return ("\n".join(p.text for p in d.paragraphs) + "\n" + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
            + "\n" + "\n".join(p.text for s in d.sections for p in s.footer.paragraphs))


def test_catalogo_coerente_e_portugues():
    codes = [l["code"] for l in LOTS]
    assert len(codes) == len(set(codes)) and [l["numero"] for l in LOTS] == sorted(l["numero"] for l in LOTS)
    tudo = json.dumps(LOTS, ensure_ascii=False)
    for proibido in ("DTU", "NF C", "Code civil", "maître d'œuvre", "plâtrerie", "Consuel"):
        assert proibido not in tudo, proibido                                    # nenhuma norma / termo francês
    for termo in ("RTIEBT", "ITED", "Decreto Regulamentar n.º 23/95", "NP EN 520", "betonilha", "caixilharia"):
        assert termo.lower() in tudo.lower(), termo
    for lot in LOTS:
        assert lot["refs"] and lot["ouvrages"] and lot["prescriptions"]
        for o in lot["ouvrages"]:
            assert o["variantes"] and o["unite"] in ("m2", "ml", "m3", "un", "vg") and len(o["description"]) > 60
            assert not R.verifier_references(o["description"])[1], (lot["code"], o["code"])


def test_referencias_fora_da_lista_retiradas():
    texto, retiradas = R.verifier_references(
        "Conforme NP EN 520, Decreto-Lei n.º 273/2003, Decreto-Lei n.º 999/2099, NP EN 99999 e RTIEBT.")
    assert "NP EN 520" in texto and "Decreto-Lei n.º 273/2003" in texto and "999/2099" not in texto and "99999" not in texto
    assert retiradas == ["Decreto-Lei n.º 999/2099", "NP EN 99999"]


def test_selecao_a_partir_do_orcamento():
    lines = [{"designation": "Divisória em gesso cartonado 72/48", "qty": 45, "unit": "m2"},
             {"designation": "Demolição de parede divisória em tijolo", "qty": 10, "unit": "m2"},
             {"designation": "Azulejo em paredes da casa de banho", "qty": 20, "unit": "m2"},
             {"designation": "Parede em alvenaria de tijolo 15", "qty": 60, "unit": "m2"},
             {"designation": "Betonilha de regularização", "qty": 80, "unit": "m2"},
             {"kind": "section", "designation": "R/C"}]
    sel = {s["code"]: s for s in R.selection_depuis_devis(lines)}
    assert set(sel) == {"demolition", "platrerie", "sols_durs", "gros_oeuvre"}
    assert sel["platrerie"]["lignes"][0]["quantite"] == 45 and len(sel["sols_durs"]["lignes"]) == 2


@pytest.mark.asyncio
async def test_redacao_catalogo_sem_ia():
    sel = [{"code": "platrerie", "ouvrages": ["cloison_98", "trappe"],
            "lignes": [{"designation": "Divisória 72/48 em gesso cartonado", "unite": "m2", "quantite": 45, "localisation": "Quartos do 1.º piso"}]},
           {"code": "platrerie", "ouvrages": ["plafond_ba13"]}]
    lots = await R.rediger(PROJETO, sel, ia=False)
    assert len(lots) == 1 and lots[0]["mode"] == "catalogue" and lots[0]["numero"] == 1     # numeração seguida
    titulos = [a["titre"] for a in lots[0]["articles"]]
    assert titulos[0] == "DIVISÓRIAS DE 72/48" and "ALÇAPÕES DE VISITA" in titulos
    art = lots[0]["articles"][0]
    assert art["localisation"] == "Quartos do 1.º piso" and art["variantes"][0]["quantite"] == 45
    assert R.numeroter(lots[0])[0]["articles"][0]["variantes"][0]["num"] == "1.2.1.1"


@pytest.mark.asyncio
async def test_redacao_ia_salvaguardas(monkeypatch):
    async def falso(system, prompt, **kw):
        assert "português europeu" in system
        return json.dumps({
            "articles": [{"chapitre": "Divisórias", "titre": "Divisórias de 72/48",
                          "description": "Divisória conforme NP EN 520 e NP EN 77777 inventada, placas de 12,5 mm aparafusadas.",
                          "localisation": "Quartos", "variantes": [{"libelle": "Placa standard", "unite": "m2", "quantite": 45},
                                                                   {"libelle": "Placa hidrófuga", "unite": "m2", "quantite": 999}]}],
            "prescriptions_complementaires": [{"titre": "Obra habitada", "texto": "x", "texte": "Trabalhos com a casa habitada, por divisões."}],
            "points_a_verifier": ["Pé-direito a confirmar"]})
    monkeypatch.setattr(ai, "_complete", falso)
    sel = [{"code": "platrerie", "ouvrages": ["trappe"], "lignes": [{"designation": "Divisória 72/48", "unite": "m2", "quantite": 45}]}]
    lot = (await R.rediger(PROJETO, sel, ia=True))[0]
    assert lot["mode"] == "ia"
    a = lot["articles"][0]
    assert "NP EN 520" in a["description"] and "77777" not in a["description"]       # norma inventada retirada
    assert [v["quantite"] for v in a["variantes"]] == [45, None]                     # quantidade não introduzida recusada
    assert any(x["titre"] == "ALÇAPÕES DE VISITA" for x in lot["articles"])          # artigo de base perdido → reintegrado
    assert any("NP EN 77777" in p for p in lot["points"]) and "Pé-direito a confirmar" in lot["points"]


@pytest.mark.asyncio
async def test_ia_em_baixo_recurso_catalogo(monkeypatch):
    async def avaria(*a, **k):
        raise RuntimeError("Serviço IA indisponível")
    monkeypatch.setattr(ai, "_complete", avaria)
    lot = (await R.rediger(PROJETO, [{"code": "peinture"}], ia=True))[0]
    assert lot["mode"] == "catalogue" and len(lot["articles"]) == 4
    assert any("indisponível" in p for p in lot["points"])


def test_equipamento_por_divisao_rtiebt_ited():
    eq = lambda nome, s=None, zap=False: dict((lib, q) for q, lib in P.equipements_electricite({"nom": nome, "surface": s}, zap=zap))
    assert eq("Sala", 20)["Tomada 16 A com terra"] == 5 and eq("Sala", 30)["Tomada 16 A com terra"] == 7
    assert "Tomada mista de telecomunicações (pares de cobre + coaxial) (ITED)" in eq("Quarto 2")
    assert any(k.startswith("ZAP") for k in eq("Sala", 30, zap=True))
    assert not any(k.startswith("Tomada mista") for k in eq("Sala", 30, zap=True))   # a divisão da ZAP não leva tomada mista
    cz = eq("Cozinha", 12)
    assert cz["Tomada 16 A com terra sobre a bancada"] == 4 and "Tomada mista de telecomunicações (pares de cobre + coaxial) (ITED)" in cz
    wc = eq("Casa de banho comum")
    assert any("30 mA" in k and "volumes 0 a 2" in k for k in wc)
    assert P.type_piece({"nom": "Suite"}) == "chambre" and P.type_piece({"nom": "Casa de banho da suite"}) == "sdb"
    assert P.type_piece({"nom": "Lavabo social"}) == "wc"
    pl = dict((lib[:20], q) for q, lib in P.equipements_plomberie({"nom": "Casa de banho 1"}))
    assert set(pl) == {"Lavatório ou móvel c", "Sanita suspensa com ", "Base de duche extrap"}


PIECES = [{"nom": "Hall de entrada", "niveau": "R/C", "surface": 6}, {"nom": "Cozinha", "niveau": "R/C", "surface": 14},
          {"nom": "Sala", "niveau": "R/C", "surface": 38}, {"nom": "Lavabo", "niveau": "R/C"},
          {"nom": "Casa de banho 1", "niveau": "1.º piso", "surface": 5}, {"nom": "Quarto 1", "niveau": "1.º piso", "surface": 12},
          {"nom": "Quarto 2", "niveau": "1.º piso", "surface": 11, "extras": ["1 alimentação de estore elétrico"]}]


@pytest.mark.asyncio
async def test_processo_de_concurso_completo():
    projeto = {**PROJETO, "nature": "neuf", "style": "architecte", "tce": True, "pieces": PIECES, "delai": "10 meses",
               "intervenants": {"architecte": "Atelier Teste", "bet_fluides": "Gabinete de Redes Teste"},
               "plans": ["Planta do R/C", "Projeto ITED"], "consultation": {"date_limite": "15/01/2027"}}
    sel = [{"code": "electricite"},
           {"code": "cvc", "titre": "AVAC e águas e esgotos", "inclure": ["plomberie"], "ouvrages": ["vmc"]},
           {"code": "platrerie", "titre": "Acabamentos interiores", "inclure": ["peinture", "sols_durs"], "ouvrages": ["cloison_72"]},
           {"code": "peinture", "lignes": [{"designation": "Pintura de paredes acetinada", "unite": "m2", "quantite": 320}]}]
    lots = await R.rediger(projeto, sel, ia=False)
    assert [(l["numero"], l["titre"]) for l in lots] == [(1, "Acabamentos interiores"), (2, "AVAC e águas e esgotos"),
                                                        (3, "Instalações elétricas e de telecomunicações (ITED)")]
    amen, avac, elec = lots
    titulos = [a["titre"] for a in elec["articles"]]
    assert "SALA (R/C)" in titulos and "EQUIPAMENTOS COMUNS DA HABITAÇÃO" in titulos and "TOMADAS" not in titulos
    sala = next(a for a in elec["articles"] if a["titre"] == "SALA (R/C)")
    assert any(v["libelle"].startswith("ZAP") for v in sala["variantes"])            # ZAP na sala por defeito
    assert any(a["titre"] == "LAVABO (R/C)" for a in avac["articles"])
    assert any(v["quantite"] == 320 for a in amen["articles"] for v in a["variantes"])
    files = R.fichiers_dossier(projeto, lots, {"company_name": "Atelier Teste"})
    nomes = [f[0] for f in files]
    assert nomes == ["00_Capa-e-indice-do-processo_Moradia-Silva.docx", "PC_Programa-de-concurso_Moradia-Silva.docx",
                     "CE_Clausulas-gerais_Moradia-Silva.docx", "CE_Condicoes-tecnicas_Moradia-Silva.docx",
                     "MQT_Mapa-de-quantidades_Moradia-Silva.xlsx", "Nota-de-verificacao.txt"]
    capa, pc, cg, ce = (_texto(f[1]) for f in files[:4])
    assert "PROCESSO DE CONCURSO" in capa and "Gabinete de Redes Teste" in capa and "Projeto ITED" in capa
    assert "15/01/2027" in pc and "IMPIC" in pc and "90 dias" in pc and "Segurança Social" in pc
    assert "1225.º do Código Civil" in cg and "Decreto-Lei n.º 273/2003" in cg and "10 meses" in cg and "Portaria n.º 1268/2008" in cg
    for esperado in ("CADERNO DE ENCARGOS", "0. CONDIÇÕES TÉCNICAS GERAIS", "Cláusulas gerais", "1. ACABAMENTOS INTERIORES",
                     "Trabalhos incluídos no presente capítulo", "Localização :",
                     "Documento elaborado por Atelier Teste", "ZAP — Zona de Acesso Privilegiado", "NP EN 520"):
        assert esperado in ce, esperado
    for proibido in ("CCTP", "DTU", "Lot ", "Localisation", "maître"):
        assert proibido not in capa + pc + cg + ce, proibido
    wb = openpyxl.load_workbook(io.BytesIO(files[4][1]))
    assert wb.sheetnames == ["Resumo", "Cap. 01", "Cap. 02", "Cap. 03"]
    assert [c.value for c in wb["Cap. 01"][5]] == ["Art.º", "Designação", "Un.", "Quant.", "Preço unitário (€)", "Total (€)"]
    z = zipfile.ZipFile(io.BytesIO(R.zip_dossier(projeto, files)))
    assert "Concurso_Moradia-Silva/1_Pecas-do-procedimento/PC_Programa-de-concurso_Moradia-Silva.docx" in z.namelist()
    assert "Concurso_Moradia-Silva/2_Caderno-de-encargos/CE_Condicoes-tecnicas_Moradia-Silva.docx" in z.namelist()


@pytest.mark.asyncio
async def test_empreitada_por_lotes():
    projeto = {**PROJETO, "par_lots": True, "tce": False}
    lots = await R.rediger(projeto, [{"code": "platrerie", "numero": 6}, {"code": "electricite", "numero": 13}], ia=False)
    nomes = [f[0] for f in R.fichiers_dossier(projeto, lots)]
    assert nomes[0].startswith("CE_Cap-06_Divisorias") and nomes[1].startswith("CE_Cap-13_Instalacoes") and len(nomes) == 4
    t = _texto(R.cctp_docx(projeto, lots[0]))
    assert "6.1 CONDIÇÕES TÉCNICAS ESPECIAIS" in t and "Trabalhos em edifício existente" in t


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [l["code"] for l in LOTS])
async def test_cada_capitulo_gera_um_docx(code):
    lot = (await R.rediger({"nom": "Teste", "nature": "neuf"}, [{"code": code}], ia=False))[0]
    data = R.cctp_docx({"nom": "Teste", "nature": "neuf"}, lot)
    assert data[:2] == b"PK" and "Trabalhos em edifício existente" not in _texto(data)


@pytest.mark.asyncio
async def test_rotas_processo_completo(monkeypatch):
    import asyncio
    import copy

    from fastapi import HTTPException
    from routes import cctp as C
    from test_platform_supervisor import USER, Database

    database = Database()
    database.pro_documents.rows = [{"doc_id": "d1", "user_id": "owner", "lines": [
        {"kind": "line", "designation": "Pintura de paredes", "qty": 120, "unit": "m2"}]}]
    monkeypatch.setattr(C, "db", database)

    async def sem_logo(uid):
        return {"company_name": "Empresa Teste"}
    monkeypatch.setattr(C, "_branding", sem_logo)
    body = C.DossierIn(projet=C.Projet(nom="Moradia Silva", nature="renovation"), doc_id="d1", ia=False,
                       lots=[C.LotSel(code="platrerie", ouvrages=["cloison_98"])])
    out = await C.creer(body, copy.deepcopy(USER))
    await asyncio.gather(*list(C._TASKS))
    d = await C.lire(out["dossier_id"], USER)
    assert d["status"] == "done" and [l["numero"] for l in d["lots"]] == [1, 2]
    resp = await C.fichier(out["dossier_id"], 0, USER)
    assert resp.body[:2] == b"PK"
    z = await C.zip_complet(out["dossier_id"], USER)
    assert z.media_type == "application/zip"
    with pytest.raises(HTTPException):
        await C.lire(out["dossier_id"], {"user_id": "outro"})
    with pytest.raises(HTTPException):
        await C.creer(C.DossierIn(projet=C.Projet(nom="X"), lots=[C.LotSel(code="desconhecido")]), USER)
