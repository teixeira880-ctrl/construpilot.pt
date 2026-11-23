"""Testes do mapa de quantidades de arquitetura medido num DWFX (engines/mapa_arquitetura).
O DWFX de teste é escrito aqui (XPS mínimo com camadas W2X), com medidas conhecidas : edifício 6 × 5 m, paredes exteriores de
0,20, parede interior de 0,10 a meio → Quarto 2,80 × 4,60 e Sala 2,70 × 4,60 ; uma porta de 0,80 ; alçado com 2 janelas 1,20 × 1,00."""
from __future__ import annotations

import asyncio
import io
import zipfile

import pytest
from openpyxl import load_workbook

from engines.mapa_arquitetura import assistant_tool, camadas, dwfx, medicao

U = 100.0          # unidades DWF por metro
DOC = "dwf/documents/D1"


def _p(nome, data, fill=False):
    return f'<Path Name="{nome}" Stroke="#000000" StrokeThickness="1"' + (' Fill="#DCDCDC"' if fill else "") + f' Data="{data}"/>'


def _ln(x0, y0, x1, y1):
    return f"M{x0 * U:g},{y0 * U:g}L{x1 * U:g},{y1 * U:g}"


def _rect(x0, y0, x1, y1):
    return _ln(x0, y0, x1, y0) + f"L{x1 * U:g},{y1 * U:g}L{x0 * U:g},{y1 * U:g}Z"


def _folha(paths_por_camada, textos, nome):
    corpo, sync, n = [], [], 0
    for num, (camada, datas) in enumerate(paths_por_camada, 1):
        for i, d in enumerate(datas):
            n += 1
            nm = f"P_{n}"
            if i == 0:
                sync.append(f'<RenditionSync refName="{nm}"><Layer Name="{camada}" Number="{num}"/></RenditionSync>')
            corpo.append(_p(nm, d, fill="terreno" in camada))
    for t, x, y in textos:
        corpo.append(f'<Glyphs Fill="#000000" FontRenderingEmSize="20" FontUri="f.odttf" OriginX="{x * U:g}" OriginY="{y * U:g}" UnicodeString="{t}"/>')
    fpage = ('<?xml version="1.0" encoding="utf-8"?><FixedPage xmlns="http://schemas.microsoft.com/xps/2005/06" Width="2000" Height="1000">'
             '<Canvas RenderTransform="0.24,0,0,0.24,0,0">' + "".join(corpo) + "</Canvas></FixedPage>")
    w2x = ('<W2X><Units Transform="100,0,0,0,0,100,0,0,0,0,1,0,0,0,0,1"/>' + "".join(sync) + "</W2X>")
    desc = f'<ePlot:Page xmlns:ePlot="DWF-ePlot:1.2" name="{nome}"/>'
    return fpage, w2x, desc


def _dwfx() -> bytes:
    parede_ext = [_rect(0, 0, 6, 5), _rect(0.2, 0.2, 5.8, 4.8)]
    parede_int = [_ln(3.0, 0.2, 3.0, 4.8), _ln(3.1, 0.2, 3.1, 4.8)]
    porta = ["M3.05,1.6 a 80,80 0 0 1 80,80".replace("3.05", f"{3.05 * U:g}").replace("1.6", f"{1.6 * U:g}")]
    planta = _folha([("paredes", parede_ext + parede_int), ("fino", porta)],
                    [("Quarto", 1.0, 2.5), ("Sala", 4.0, 2.5)], "Planta do 1 Andar")
    # alçado : contorno 6 m (= largura da planta) ; 2 janelas ; vizinho à direita (x 8–12) com uma janela ; chaminé acima das paredes ;
    # retângulo coberto de trama cheia de terreno (abaixo do solo) — só as 2 janelas são vãos da fachada
    alc = _folha([("paredes", [_rect(0, 0, 6, 6), _rect(8, 1, 12, 6)]),
                  ("fino", [_rect(1, 2, 2.2, 3), _rect(3.5, 2, 4.7, 3), _rect(9, 2, 10.2, 3), _rect(1, -1.5, 1.6, -0.6), _rect(2, 6.5, 3, 7.5)]),
                  ("Trama terreno", [_rect(0, 6.4, 7, 7.6)])],
                 [("Alçado Principal", 2.0, 8.5)], "Alcado Principal")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("FixedDocumentSequence.fdseq", "<FixedDocumentSequence/>")
        z.writestr(f"{DOC}/FixedDocument.fdoc", "<FixedDocument>" + "".join(
            f'<PageContent Source="/{DOC}/sections/S{i}/FixedPage.fpage"/>' for i in (1, 2)) + "</FixedDocument>")
        for i, (fp, w2x, desc) in ((1, planta), (2, alc)):
            z.writestr(f"{DOC}/sections/S{i}/FixedPage.fpage", fp)
            z.writestr(f"{DOC}/sections/S{i}/w2x.xml", w2x)
            z.writestr(f"{DOC}/sections/S{i}/descriptor.xml", desc)
    return buf.getvalue()


def test_reconhece_dwfx():
    assert dwfx.e_dwfx(_dwfx())
    assert not dwfx.e_dwfx(b"%PDF-1.4 ...")
    assert not dwfx.e_dwfx(b"PK\x03\x04 lixo")


def test_leitor_escala_camadas_e_textos():
    z = dwfx.abrir(_dwfx())
    f = dwfx.ler(z, 0)
    assert f.nome == "Planta do 1 Andar" and f.upm == 100.0
    assert set(f.camadas) == {"paredes", "fino"}
    xs = [p[0] for e in f.elementos if e.tipo == "path" and e.camada == "paredes" for pl in e.pls for p in pl]
    assert min(xs) == pytest.approx(0.0) and max(xs) == pytest.approx(6.0)       # metros, transformação da Canvas desfeita
    arcos = [a for e in f.elementos for a in e.arcos]
    assert arcos == [pytest.approx(0.8)]
    assert {e.texto for e in f.elementos if e.tipo == "texto"} == {"Quarto", "Sala"}


def test_papeis_das_camadas():
    m = camadas.mapa(["paredes", "trama corte", "trama", "traço fino", "MUROS", "SANITARIOS", "cozinha", "cotas"])
    assert m["paredes"] == "paredes" and m["trama corte"] == "trama" and m["trama"] is None
    assert m["traço fino"] == "fino" and m["MUROS"] == "muros" and m["SANITARIOS"] == "sanitarios" and m["cotas"] is None


def test_medicao_planta_e_alcado():
    m = medicao.medir(_dwfx(), pe_direito=2.5)
    assert m["ok"], m
    p = m["pisos"][0]
    comps = {c["nome"]: c for c in p["compartimentos"]}
    assert comps["Quarto"]["area"] == pytest.approx(2.8 * 4.6, abs=0.05)
    assert comps["Sala"]["area"] == pytest.approx(2.7 * 4.6, abs=0.05)
    assert not any(c["exterior"] for c in comps.values())
    tipos = {w["tipo"] for w in p["paredes"]}
    assert "interior" in tipos and "fachada" in tipos
    interior = sum(w["comprimento"] for w in p["paredes"] if w["tipo"] == "interior")
    assert interior == pytest.approx(4.6, abs=0.05)
    assert [(d["L"], d["tipo"]) for d in p["portas"]] == [(0.8, "interior")]
    r = {x["artigo"]: x["qtd"] for x in m["resumo"]}
    assert r["Pavimento interior (sem caixa do elevador)"] == pytest.approx(25.30, abs=0.1)
    assert r["Portas interiores"] == 1
    assert len(m["alcados"]) == 1
    assert sorted((d["L"], d["H"]) for d in m["alcados"][0]["vaos"]) == [(1.2, 1.0), (1.2, 1.0)]
    assert r["Vãos exteriores nos alçados (área)"] == pytest.approx(2.4)
    assert not any("altura" in q for q in m["perguntas"])


def test_sem_altura_pergunta():
    m = medicao.medir(_dwfx())
    assert any("altura" in q for q in m["perguntas"])


def test_ficheiros_excel_com_controlo(tmp_path):
    m = assistant_tool.medir([("teste.dwfx", _dwfx())], 2.5, None, str(tmp_path))
    assert m["ok"]
    wb = load_workbook(m["files"]["xlsx"])
    assert {"Mapa", "Pressupostos", "Compartimentos", "Paredes", "Portas", "Vãos", "Controlo"} <= set(wb.sheetnames)
    assert len(wb["Controlo"]._images) == 2                       # 1 planta + 1 alçado : imagens do que foi medido
    assert open(m["files"]["controlo"], "rb").read(4) == b"%PDF"
    for ws in wb:                                                  # nenhuma nota de texto lida como fórmula
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    assert "!" in c.value or c.value[1:2].isalpha() or c.value[1:2] in "(", c.value


def test_nao_dwfx():
    assert not assistant_tool.medir([("x.pdf", b"%PDF-1.4")])["ok"]


class _Col:
    def __init__(self, docs=None):
        self.docs = docs or []
        self.saved = []

    async def find_one(self, q, proj=None):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in q.items())), None)

    async def update_one(self, q, upd, upsert=False):
        self.saved.append(upd["$setOnInsert"])


class _DB:
    def __init__(self, data):
        import base64
        self.assistant_docs = _Col([{"doc_id": "doc_1", "user_id": "u1", "filename": "obra.dwfx", "data_b64": base64.b64encode(data).decode()}])
        self.assistant_artifacts = _Col()


def test_ferramenta_do_assistente():
    db = _DB(_dwfx())
    res = asyncio.run(assistant_tool.execute("medir_arquitetura_dwfx", {"document_ids": ["doc_1"], "pe_direito_m": 2.5},
                                             {"user_id": "u1"}, {"conversation_id": "c1"}, db))
    assert res["ok"], res
    assert [a["format"] for a in res["artifacts"]] == ["xlsx", "pdf"]
    assert res["pisos"][0]["portas_interiores"] == 1
    neg = asyncio.run(assistant_tool.execute("medir_arquitetura_dwfx", {"document_ids": ["doc_1"]}, {"user_id": "outro"}, {}, db))
    assert not neg["ok"]


def test_area_escrita_pelo_arquiteto_e_controlo_cruzado():
    from engines.mapa_arquitetura import plantas
    z = dwfx.abrir(_dwfx())
    f = dwfx.ler(z, 0)
    f.elementos.append(dwfx.Elemento("TEXTO", "texto", texto="12.88", pos=(1.0, 3.0)))
    f.elementos.append(dwfx.Elemento("TEXTO", "texto", texto="104.06", pos=(4.0, 3.0)))   # cota, não área
    r = plantas.medir(f, camadas.mapa(f.camadas))
    c = {x["nome"]: x for x in r["compartimentos"]}
    assert c["Quarto"]["area_no_desenho"] == 12.88 and c["Sala"]["area_no_desenho"] is None


def test_alcados_isola_edificio_e_vistas_repetidas():
    from engines.mapa_arquitetura import alcados
    m = medicao.medir(_dwfx())
    v = m["alcados"][0]
    assert v["isolamento"].startswith("contorno")
    assert v["zona"][0] == pytest.approx(0.0) and v["zona"][2] == pytest.approx(6.0)
    a = {"vista": "Alçado Lat. Direito (pelo lote)", "vaos": [1, 2, 3]}
    b = {"vista": "Alçado Lat. Direito (pelo vizinho)", "vaos": [1]}
    c = {"vista": "Alçado Lat. Esquerdo", "vaos": [1]}
    ficam, rep = alcados.sem_repetidas([b, a, c])
    assert [x["vista"] for x in ficam] == [a["vista"], c["vista"]] and rep[0]["repete"] == a["vista"]


def test_altura_das_paredes_pelas_cotas_das_plantas():
    pisos = [{"piso": "Cave", "paredes": [1], "cota": {"candidatos": {27.75: 2, 101.28: 1}}},     # 27,75 = área escrita : fica de fora
             {"piso": "R/C", "paredes": [1], "cota": {"candidatos": {104.08: 2, 101.24: 1}}},
             {"piso": "1.º", "paredes": [1], "cota": {"candidatos": {107.08: 2, 104.06: 3}}},     # 104,06 = cota do piso de baixo
             {"piso": "Sótão", "paredes": [1], "cota": {"candidatos": {110.08: 1}}}]
    medicao.alturas(pisos)
    assert [p["cota"]["valor"] for p in pisos] == [101.28, 104.08, 107.08, 110.08]
    assert [p["altura"] for p in pisos] == [2.8, 3.0, 3.0, None]
    medicao.alturas(pisos, pe_direito=2.7)
    assert all(p["altura"] == 2.7 for p in pisos)


def test_vao_sem_aro_e_grelha_nao_sao_vaos():
    from shapely.geometry import box
    from engines.mapa_arquitetura import alcados
    f = dwfx.Folha(0, "t", 100.0, [
        dwfx.Elemento("fino", "path", [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]]),                       # janela com aro
        dwfx.Elemento("fino", "path", [[(2 + 0.1 * k, 0.05), (2 + 0.1 * k, 0.95)] for k in range(1, 6)]),  # grelha (TGBT)
        dwfx.Elemento("fino", "path", [[(2, 0), (2.7, 0), (2.7, 1), (2, 1), (2, 0)]]),
    ], ["fino"])
    pap = {"fino": "fino"}
    assert alcados._e_vao(box(0, 0, 1, 1), f, pap)
    assert not alcados._e_vao(box(2, 0, 2.7, 1), f, pap)              # só barras verticais por dentro
    assert not alcados._e_vao(box(5, 0, 6, 1), f, pap)                # face sem aro próprio


def test_corte_altura_entre_lajes():
    """Corte sintético : coluna de cotas 100,00 / 103,00 / 106,00 (y = 10, 7, 4) ; lajes cortadas de 0,30 com topo a cada cota."""
    from engines.mapa_arquitetura import cortes
    els = [dwfx.Elemento("cotas", "texto", texto=f"{v:.2f}", pos=(0.0, y)) for v, y in ((100.0, 10.0), (103.0, 7.0), (106.0, 4.0))]
    for y in (10.0, 7.0, 4.0):                       # topo da laje na cota (y), base 0,30 abaixo (y + 0,30)
        els.append(dwfx.Elemento("trama corte", "path", [[(2, y), (12, y), (12, y + 0.3), (2, y + 0.3), (2, y)]], fill="#808080"))
    f = dwfx.Folha(0, "Corte A", 100.0, els, ["trama corte", "cotas"])
    ls = cortes.lajes(f, camadas.mapa(f.camadas))
    assert ls and sorted((lo, hi) for lo, hi, _ in ls[0][1]) == [(99.7, 100.0), (102.7, 103.0), (105.7, 106.0)]


def test_perfil_da_cobertura_no_sotao():
    """Corte : laje do sótão (topo cota 110,00, y = 10) ; cobertura de duas águas cortada (0,20) : beirado 0,50 acima da laje nas
    pontas (x 2 e 12) e cumeeira 2,50 a meio (x 7)."""
    from engines.mapa_arquitetura import cortes
    def faixa(x0, x1, h0, h1):                      # banda inclinada de 0,20, face inferior h acima da laje (y cresce para baixo)
        return [(x0, 10 - h0), (x1, 10 - h1), (x1, 10 - h1 - 0.2), (x0, 10 - h0 - 0.2), (x0, 10 - h0)]
    els = [dwfx.Elemento("cotas", "texto", texto=f"{v:.2f}", pos=(0.0, y)) for v, y in ((104.0, 16.0), (107.0, 13.0), (110.0, 10.0))]
    els += [dwfx.Elemento("trama corte", "path", [pl], fill="#808080") for pl in (
        [(1.8, 10), (12.2, 10), (12.2, 10.3), (1.8, 10.3), (1.8, 10)], faixa(1.8, 7, 0.5, 2.5), faixa(7, 12.2, 2.5, 0.5))]
    f = dwfx.Folha(0, "Corte A", 100.0, els, ["trama corte", "cotas"])

    class Z:          # o perfil só usa dwfx.ler → substituir por esta folha
        pass
    orig = dwfx.ler
    try:
        dwfx.ler = lambda z, i, lista=None: f
        pc = cortes.perfil_cobertura(Z(), [("p", "s", "Corte A")], 110.0)
    finally:
        dwfx.ler = orig
    assert pc["h_max"] == pytest.approx(2.5, abs=0.05) and pc["h_min"] == pytest.approx(0.5, abs=0.1)
    assert pc["area_perfil"] == pytest.approx(10.4 * 1.5, rel=0.03)


def test_mapa_premium_pdf_e_excel(tmp_path):
    from openpyxl import load_workbook
    from engines.mapa_arquitetura import premium
    m = medicao.medir(_dwfx(), pe_direito=2.5)
    premium.numerar(m)
    assert {c["id"] for c in m["pisos"][0]["compartimentos"]} == {"C1.01", "C1.02"}
    assert all(w.get("id", "").startswith("W1.") for w in m["pisos"][0]["paredes"])
    assert [d["id"] for d in m["pisos"][0]["portas"]] == ["P1.01"]
    L = premium.linhas(m)
    caps = {r["capitulo"] for r in L}
    assert {"Alvenarias", "Pavimentos", "Portas e carpintarias", "Caixilharias e serralharias"} <= caps
    pdf = premium.gerar_pdf(m, str(tmp_path / "m.pdf"), "Teste", nao_medido=premium.NAO_MEDIDO_PADRAO)
    assert open(pdf, "rb").read(4) == b"%PDF"
    x = premium.gerar_xlsx(m, str(tmp_path / "m.xlsx"), "Teste", nao_medido=premium.NAO_MEDIDO_PADRAO)
    wb = load_workbook(x)
    assert wb.sheetnames[:2] == ["Mapa", "Elementos numerados"]
    assert any(c.value == "a medir" for row in wb["Mapa"].iter_rows() for c in row)


def _pdf_quadro_fundacoes() -> bytes:
    """Quadro de elementos de fundação desenhado aqui (reportlab), com o texto das notas do recobrimento."""
    import io
    from reportlab.pdfgen import canvas
    b = io.BytesIO()
    c = canvas.Canvas(b, pagesize=(800, 400))
    c.setFont("Helvetica", 7)
    c.drawString(300, 380, "QUADRO DE ELEMENTOS DE FUNDAÇÃO")
    for x, t in ((60, "Referências"), (180, "Dimensões"), (260, "Altura"), (320, "Armadura"), (420, "Armadura")):
        c.drawString(x, 360, t)
    for y, (ref, dim, h, ax, ay) in zip((340, 325), (("P14, P27 e P28", "1,6x1,6", "0,5", "10Ø12af.0,15", "10Ø12af.0,15"),
                                                     ("P11", "2,2x2,2", "0,5", "11Ø16af.0,2", "11Ø16af.0,2"))):
        for x, t in ((60, ref), (180, dim), (260, h), (320, ax), (420, ay)):
            c.drawString(x, y, t)
    c.drawString(60, 100, "Betonagem contra o terreno com recobrimento de 80 mm")
    c.save()
    return b.getvalue()


def test_quadro_de_fundacoes_no_mapa():
    from engines.mapa_estrutura import fundacoes
    q = fundacoes.ler_quadro(_pdf_quadro_fundacoes())
    assert q["recobrimento"] == 0.08
    r = {x["ref_txt"]: x for x in q["linhas"]}
    assert r["P14, P27 e P28"]["n"] == 3 and r["P11"]["lx"] == 2.2 and r["P11"]["h"] == 0.5
    L = fundacoes.linhas_mapa(q)
    betao = sum(x["qtd"] for x in L if x["designacao"].endswith("— betão"))
    assert betao == pytest.approx(3 * 1.6 * 1.6 * 0.5 + 2.2 * 2.2 * 0.5)
    aco = sum(x["qtd"] for x in L if x["un"] == "kg")
    assert aco == pytest.approx(3 * 2 * 10 * (1.6 - 0.16) * 0.888 + 2 * 11 * (2.2 - 0.16) * 1.578, rel=1e-6)
