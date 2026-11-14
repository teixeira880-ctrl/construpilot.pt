"""Construção tradicional: as quantidades são conferidas com o que está escrito na planta (altura, áreas, espessuras) e o
dossier mostra o cruzamento; o que não está escrito fica dito, não assumido."""
import fitz

from engines.takeoff_core import dossier, escrito, estudo

SALA = [(0.1, 0.1), (5.9, 0.1), (5.9, 3.9), (0.1, 3.9)]          # 5,8 × 3,8 = 22,04 m²


def _project(altura=2.9, espessura=200, divisoes=True):
    walls = [{"id": f"P{i}", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1], "thickness_mm": espessura}
             for i, (a, b) in enumerate([((0, 0), (6, 0)), ((6, 0), (6, 4)), ((6, 4), (0, 4)), ((0, 4), (0, 0))], 1)]
    return estudo.Project(nome="Casa", sistema="alvenaria_tijolo", pisos=[{
        "nome": "RC", "nivel": 0, "altura_m": altura, "altura_fonte": "corte", "paredes": walls,
        "divisoes": [{"nome": "Sala", "poligono": SALA}] if divisoes else []}])


def _rows(project, text):
    result = estudo.run(project)
    rooms = {f.nome: [list(r.poligono) for r in f.divisoes] for f in project.pisos}
    return result, {r["item"]: r for r in escrito.cruzar(result, {"RC": text} if text is not None else {}, rooms)}


def test_le_alturas_areas_e_espessuras_escritas_em_pt_fr_en():
    w = escrito.ler("Sala 22,04 m²\nQuarto 12.50 m2\nÁrea bruta 80,00 m²\nPé-direito: 2,70 m\nParede de tijolo 20 cm")
    assert w["areas"] == [22.04, 12.5] and w["totais"][0][1] == 80.0 and w["alturas_m"] == [2.7] and w["espessuras_mm"] == [200]
    assert escrito.ler("HSP 2,50 m · mur ép. 20 cm · Séjour 30,10 m²") == {"areas": [30.1], "totais": [], "alturas_m": [2.5], "espessuras_mm": [200]}
    assert escrito.ler("Ceiling height 2700 mm, wall 200 mm")["alturas_m"] == [2.7]


def test_tudo_escrito_e_igual_confere():
    _res, r = _rows(_project(), "Sala 22,04 m²\nPé-direito 2,70 m\nParede 20 cm")
    assert r["altura"]["ok"] is True and r["divisoes"]["ok"] is True and r["espessuras"]["ok"] is True


def test_altura_abaixo_do_pe_direito_escrito_nao_confere():
    _res, r = _rows(_project(altura=2.4), "Pé-direito 2,70 m")
    assert r["altura"]["ok"] is False and r["altura"]["nota"] == "altura_fora"


def test_area_medida_diferente_da_escrita_nao_confere():
    _res, r = _rows(_project(), "Sala 30,00 m²")
    assert r["divisoes"]["ok"] is False and r["divisoes"]["nota"] == "divisoes_area"


def test_espessura_que_nao_esta_escrita_nao_confere():
    _res, r = _rows(_project(espessura=300), "Parede de tijolo 20 cm")
    assert r["espessuras"]["ok"] is False


def test_o_que_nao_esta_escrito_fica_sem_texto_e_nao_como_certo():
    _res, r = _rows(_project(), "planta sem cotas")
    assert all(x["ok"] is None for x in r.values()) and r["altura"]["nota"] == "nao_escrito"
    _res, r = _rows(_project(), None)
    assert r["texto"]["ok"] is None and r["texto"]["nota"] == "sem_folha"


def test_dossier_mostra_o_cruzamento_e_o_anexo_de_paredes_numeradas():
    for lang, titulo, nao in (("pt", "Cruzamento com o que está escrito nas plantas", "NÃO confere"),
                              ("fr", "Recoupement avec ce qui est écrit sur les plans", "NON conforme"),
                              ("en", "Cross-check with what is written on the plans", "does NOT agree")):
        project = _project(altura=2.4)
        result, _r = _rows(project, "Sala 22,04 m²\nPé-direito 2,70 m\nParede 20 cm")
        result["escrito"] = escrito.cruzar(result, {"RC": "Sala 22,04 m²\nPé-direito 2,70 m\nParede 20 cm"}, {"RC": [SALA]})
        with fitz.open(stream=dossier.build(result, lang=lang), filetype="pdf") as doc:
            text = " ".join(" ".join(pg.get_text().split()) for pg in doc)
        assert titulo in text and nao in text and "P1" in text, lang


def test_dossier_sem_texto_diz_que_nao_foi_conferido():
    result = estudo.run(_project())
    with fitz.open(stream=dossier.build(result, lang="pt"), filetype="pdf") as doc:
        text = " ".join(" ".join(pg.get_text().split()) for pg in doc)
    assert "não foram conferidas por texto" in text


def test_agente_le_o_texto_da_folha_de_cada_piso_em_pdf_e_em_dwg_importado():
    """Plantas de casas: o texto vem da própria folha de onde o piso foi lido (PDF anexado ou DWG/DXF importado)."""
    import asyncio
    import base64

    from mongomock_motor import AsyncMongoMockClient

    from engines import assistant_clt_agent as A
    pdf = fitz.open()
    pdf.new_page().insert_text((50, 50), "capa")
    pdf.new_page().insert_text((50, 50), "Sala 22,04 m2  Pe-direito 2,70 m  Parede 20 cm")
    data = pdf.tobytes()
    db = AsyncMongoMockClient()["t"]

    async def load_doc(doc_id, uid):
        assert (doc_id, uid) == ("doc_1", "u1")
        return {"data_b64": base64.b64encode(data).decode(), "mime": "application/pdf"}

    doc = {"pisos": {"RC": {"nome": "RC", "ordem": 0, "document_id": "doc_1", "pagina": 2, "paredes": []},
                     "Piso 1": {"nome": "Piso 1", "ordem": 1, "document_id": "", "plan_id": "p1", "pagina": 1, "paredes": []},
                     "Foto": {"nome": "Foto", "ordem": 2, "document_id": "doc_x", "pagina": 1, "paredes": []}}}

    async def go():
        await db.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "u1", "pages": [
            {"index": 0, "text_blocks": [{"text": "Quarto 12,50 m²"}, {"text": "HSP 2,50 m"}]}]})
        await db.plans_takeoff.insert_one({"plan_id": "p1", "user_id": "outro", "pages": [{"index": 0, "text_blocks": [{"text": "X 99,00 m²"}]}]})

        async def loader(doc_id, uid):
            if doc_id == "doc_x":
                return {"data_b64": base64.b64encode(b"\x89PNG....").decode(), "mime": "image/png"}
            return await load_doc(doc_id, uid)
        return await A.written_texts(doc, {"user_id": "u1"}, db, loader)
    textos = asyncio.run(go())
    assert set(textos) == {"RC", "Piso 1"}, "a folha em imagem não tem texto: fica de fora, não é inventada"
    assert escrito.ler(textos["RC"])["alturas_m"] == [2.7] and escrito.ler(textos["Piso 1"])["areas"] == [12.5]
