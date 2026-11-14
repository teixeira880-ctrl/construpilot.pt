"""Seguimento das quantidades de um DWG/DXF: tudo o que é medido aparece desenhado e numerado, o desenhado tem de dar a
mesma quantidade da medição e as áreas escritas no desenho são conferidas com o elemento medido."""
import ezdxf

from engines import cad_seguimento as S
from engines.cad_quantidades_camadas import medir


def _doc(escrito="PAVIMENTO 200.00 m²", ilha=False):
    d = ezdxf.new()
    d.header["$INSUNITS"] = 6
    m = d.modelspace()
    h = m.add_hatch(dxfattribs={"layer": "SMC_PAV BETUMINOSO"})
    h.paths.add_polyline_path([(0, 0), (20, 0), (20, 10), (0, 10)], is_closed=True)
    if ilha:
        h.paths.add_polyline_path([(5, 2), (10, 2), (10, 6), (5, 6)], is_closed=True)      # ilha de 20 m²
    h2 = m.add_hatch(dxfattribs={"layer": "SMC_PAVE PERMEAVEL"})
    h2.paths.add_polyline_path([(0, 20), (10, 20), (10, 30), (0, 30)], is_closed=True)
    m.add_lwpolyline([(0, -1), (50, -1)], dxfattribs={"layer": "LANCIL"})
    m.add_lwpolyline([(0, -1.15), (50, -1.15)], dxfattribs={"layer": "LANCIL"})
    m.add_lwpolyline([(0, 50), (40, 50)], dxfattribs={"layer": "muro"})
    d.blocks.new("CAND").add_circle((0, 0), 0.2)
    for x in (2, 12, 22):
        m.add_blockref("CAND", (x, 40), dxfattribs={"layer": "SMC_CANDEEIROS"})
    if escrito:
        m.add_text(escrito, dxfattribs={"layer": "SMC_TEXTO", "insert": (3, 8)})
    return d


def test_cada_artigo_medido_tem_numero_e_desenho_com_a_mesma_quantidade():
    d = _doc()
    med = medir(d)
    f = S.formas(d, med)
    assert [a["n"] for a in f["artigos"]] == list(range(1, len(med["linhas"]) + 1))
    assert {a["camada"] for a in f["artigos"]} == {l["camada"] for l in med["linhas"]}
    for a in f["artigos"]:
        if a["medida"] != "comprimento":
            assert a["confere"] is True and abs(a["desenhado"] - a["qty"]) < 0.02, a["camada"]
        else:
            assert a["linhas"], "um comprimento medido tem as linhas desenhadas"
    cand = next(a for a in f["artigos"] if a["camada"] == "SMC_CANDEEIROS")
    assert len(cand["pontos"]) == 3 == cand["qty"]
    assert f["excluidas"], "a camada de levantamento aparece no desenho (a cinzento), não desaparece"


def test_ilhas_da_trama_sao_descontadas_no_desenho_como_na_medicao():
    d = _doc(escrito="", ilha=True)
    med = medir(d)
    a = next(x for x in S.formas(d, med)["artigos"] if x["camada"] == "SMC_PAV BETUMINOSO")
    assert abs(a["qty"] - 180) < 0.01 and abs(a["desenhado"] - 180) < 0.01 and a["confere"]


def test_area_escrita_e_conferida_com_o_elemento_que_contem_o_texto():
    d = _doc()
    r = S.cruzar_escrito(S.formas(d, medir(d)))
    assert len(r) == 1 and r[0]["ok"] is True and r[0]["camada"] == "SMC_PAV BETUMINOSO" and r[0]["medido"] == 200.0


def test_area_escrita_diferente_da_medida_e_erro_declarado():
    d = _doc(escrito="PAVIMENTO 260.00 m²")
    med = medir(d)
    out = S.pdf(d, med, titulo="t")
    assert out["escrito"][0]["ok"] is False and out["erros"] == 1


def test_sem_areas_escritas_fica_dito_e_nao_assumido():
    d = _doc(escrito="")
    out = S.pdf(d, medir(d), titulo="t")
    assert out["escrito"] == [] and any("áreas escritas" in a for a in out["avisos"])


def test_quantidade_da_medicao_alterada_e_apanhada_pelo_desenho():
    d = _doc()
    med = medir(d)
    for l in med["linhas"]:
        if l["camada"] == "SMC_PAV BETUMINOSO":
            l["qty"] = 240.0
    out = S.pdf(d, med, titulo="t")
    a = next(x for x in out["artigos"] if x["camada"] == "SMC_PAV BETUMINOSO")
    assert a["confere"] is False and out["erros"] >= 1


def test_pdf_tem_planta_e_tabela_com_os_mesmos_numeros_pt_e_fr():
    import fitz
    d = _doc()
    med = medir(d)
    for lang, palavra in (("pt", "Seguimento das quantidades medidas"), ("fr", "Suivi des quantités mesurées")):
        out = S.pdf(d, medir(d, lang=lang), titulo="Valpaços", lang=lang, estrutura={"malha": {"x": [0, 5, 10], "y": [0, 6]}, "pilares": 6})
        with fitz.open(stream=out["pdf"], filetype="pdf") as doc:
            assert len(doc) >= 2
            planta, tabela = doc[0].get_text(), " ".join(pg.get_text() for pg in doc)
        assert palavra in planta
        for a in out["artigos"]:
            assert str(a["n"]) in planta and a["camada"] in tabela
    assert len(med["linhas"]) == len(out["artigos"])


def test_unidades_do_desenho_em_mm_dao_o_mesmo_seguimento_em_metros():
    d = ezdxf.new()
    d.header["$INSUNITS"] = 4
    m = d.modelspace()
    h = m.add_hatch(dxfattribs={"layer": "SMC_PAV BETUMINOSO"})
    h.paths.add_polyline_path([(0, 0), (20000, 0), (20000, 10000), (0, 10000)], is_closed=True)
    med = medir(d)
    a = S.formas(d, med)["artigos"][0]
    assert abs(med["fator_m"] - 0.001) < 1e-9 and abs(a["desenhado"] - 200) < 0.01 and a["confere"]


def test_ferramenta_de_medicao_entrega_sempre_a_folha_de_seguimento(monkeypatch):
    import asyncio
    import io
    import os
    for k in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
        os.environ.setdefault(k, "x" if k != "MONGO_URL" else "mongodb://localhost:27017")
    from mongomock_motor import AsyncMongoMockClient

    from engines import plan_sources
    from routes import assistant
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(assistant, "db", db)
    buf = io.StringIO()
    _doc().write(buf)
    dxf = buf.getvalue().encode()

    async def fonte(_db, plan_id, uid, kind):
        return dxf if kind == "original" else None
    monkeypatch.setattr(plan_sources, "load_cad_source", fonte)
    user = {"user_id": "u1", "role": "particulier", "account_type": "individual"}

    async def go():
        await db.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "u1", "kind": "dxf", "filename": "V.dxf"})
        out = await assistant._exec_tool_inner("medir_camadas_cad", {"plan_id": "p1", "recalcular": False}, user,
                                               {"user_id": "u1", "conversation_id": "c1"})
        art = await db.assistant_artifacts.find_one({"artifact_id": out["artifacts"][0]["artifact_id"], "user_id": "u1"})
        return out, art
    out, art = asyncio.run(go())
    assert out["ok"] and out["seguimento"]["estado"] == "gerado" and art["mime"] == "application/pdf" and art["size"] > 1000
    assert all(l.get("n_seguimento") for l in out["linhas"]), "cada linha da medição traz o número com que aparece na planta"
    nomes = [v["verificacao"] for v in out["verificacao_cruzada"]]
    assert "seguimento: desenhado = medido" in nomes and "áreas escritas no desenho" in nomes
    assert all(v["estado"] == "ok" for v in out["verificacao_cruzada"] if v["verificacao"] in ("seguimento: desenhado = medido", "áreas escritas no desenho"))


def test_sem_ficheiro_cad_a_medicao_segue_e_diz_que_nao_ha_planta_de_controlo(monkeypatch):
    import asyncio
    import os
    for k in ("MONGO_URL", "DB_NAME", "JWT_SECRET"):
        os.environ.setdefault(k, "x" if k != "MONGO_URL" else "mongodb://localhost:27017")
    from mongomock_motor import AsyncMongoMockClient

    from engines import cad_quantidades_camadas as CQ
    from routes import assistant
    db = AsyncMongoMockClient()["t"]
    monkeypatch.setattr(assistant, "db", db)
    med = {"versao": CQ.VERSAO, "unidades": "m", "excluidas": [], "edificio": None,
           "linhas": [{"category": "Pavimentos", "designation": "Pavimento betuminoso — camada X", "unit": "m2", "qty": 100.0, "description": "d", "camada": "X"}]}

    async def go():
        await db.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "u1", "kind": "dxf", "filename": "V.dwg", "cad_quantidades": med})
        return await assistant._exec_tool_inner("medir_camadas_cad", {"plan_id": "p1", "recalcular": False},
                                                {"user_id": "u1", "role": "particulier", "account_type": "individual"}, {"user_id": "u1"})
    out = asyncio.run(go())
    assert out["ok"] and out["linhas"][0]["qty"] == 100.0 and out["seguimento"]["estado"] == "não gerado" and not out.get("artifacts")
