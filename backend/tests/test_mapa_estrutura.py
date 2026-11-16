"""Testes do mapa de quantidades medido numa planta estrutural em PDF (engines/mapa_estrutura).
A planta de teste é desenhada aqui (reportlab), à escala 1/100, com valores conhecidos."""
from __future__ import annotations

import asyncio
import io

import pytest
from reportlab.pdfgen import canvas

from engines.mapa_estrutura import assistant_tool, excel, leitura, medicao, vetores

M = 72 / 2.54                      # pontos PDF por metro real a 1/100
OX, OY = 4.0, 4.0                  # origem da planta na folha (m)


def _planta(tracejado_manual: bool = True, com_escala: bool = True, niveis: int = 2) -> bytes:
    """Laje 10 × 6 m ; 4 pilares 0,30 × 0,50 nos cantos ; parede 2,00 × 0,20 ; viga V1 (30×50) no bordo sul entre P1 e P2 ;
    6 moldes de 0,80 m ; 2 + 2 alinhamentos ; caixas de nível Piso 1 (Zsup 3,00, e 0,20) e Piso 2 (Zsup 6,00, e 0,20)."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(20 * M, 16 * M))

    def X(x):
        return (OX + x) * M

    def Y(y):
        return (OY + y) * M
    c.setLineWidth(0.3)
    c.setFont("Helvetica", 7)
    if com_escala:
        c.drawString(X(3), Y(9.2), "Planta Estrutural Piso 1 e 2")
        c.drawString(X(3), Y(8.9), "Esc: 1/100")
    c.drawString(X(0), Y(-2.6), "NOTA: Zona aligeirada: espessura da lâmina de betão de 7.5cm")
    c.setStrokeGray(0.6)                                    # alinhamentos : interrompido guardado no traço, a cinzento
    c.setDash(6, 3)
    for x, nome in ((0.15, "1"), (9.85, "2")):
        c.line(X(x), Y(-2), X(x), Y(8))
        c.drawCentredString(X(x), Y(8.3), nome)
    for y, nome in ((0.25, "A"), (5.75, "B")):
        c.line(X(-2), Y(y), X(12), Y(y))
        c.drawString(X(12.2), Y(y) - 2, nome)
    c.setDash()
    c.setStrokeGray(0)
    c.rect(X(0), Y(0), 10 * M, 6 * M, stroke=1, fill=0)     # contorno da laje
    for nome, x, y in (("P1", 0, 0), ("P2", 9.7, 0), ("P3", 0, 5.5), ("P4", 9.7, 5.5)):
        c.rect(X(x), Y(y), 0.3 * M, 0.5 * M, stroke=0, fill=1)
        c.drawString(X(x + (0.4 if x < 5 else -0.75)), Y(y + (0.65 if y < 3 else -0.3)), nome)
    c.rect(X(4), Y(3), 2.0 * M, 0.2 * M, stroke=0, fill=1)
    c.drawString(X(4.6), Y(3.35), "Par1")
    for i in range(3):                                      # moldes
        for j in range(2):
            c.rect(X(1 + 0.8 * i), Y(1.2 + 0.8 * j), 0.8 * M, 0.8 * M, stroke=1, fill=0)
    if tracejado_manual:                                    # face interior da viga : traço-ponto desenhado peça a peça (CAD)
        x = 0.3
        while x < 9.7 - 1e-6:
            c.line(X(x), Y(0.30), X(min(x + 0.08, 9.7)), Y(0.30))
            x += 0.12
    else:
        c.setDash(3, 2)
        c.line(X(0.3), Y(0.30), X(9.7), Y(0.30))
        c.setDash()
    c.drawString(X(4.5), Y(0.5), "V1(30x50)")
    for n in range(niveis):
        x = X(6.5 + 2.2 * n)
        for k, t in enumerate((f"Piso {n + 1}", f"Zsup: {3.0 * (n + 1):.2f} m", f"Zinf: {3.0 * (n + 1) - 0.2:.3f} m", "e=0.20 m")):
            c.drawString(x, Y(2.2) - 9 * k, t)
    c.showPage()
    c.save()
    return buf.getvalue()


@pytest.fixture(scope="module")
def lida():
    folha = vetores.ler(_planta())
    return folha, leitura.ler_folha(folha)


def test_escala_e_niveis(lida):
    folha, r = lida
    assert r["ok"] and r["escala"] == 100 and len(r["plantas"]) == 1
    niv = r["plantas"][0]["niveis"]
    assert [(n["nome"], n["zsup"], n["e"]) for n in niv] == [("Piso 1", 3.0, 0.2), ("Piso 2", 6.0, 0.2)]


def test_seccoes_medidas_e_etiquetadas(lida):
    p = lida[1]["plantas"][0]
    el = {e["nome"]: e for e in p["elementos"]}
    assert set(el) == {"P1", "P2", "P3", "P4", "Par1"}
    for n in ("P1", "P2", "P3", "P4"):
        assert el[n]["tipo"] == "Pilar" and (el[n]["a"], el[n]["b"]) == (0.5, 0.3) and el[n]["area"] == pytest.approx(0.15, abs=0.002)
    assert el["Par1"]["tipo"] == "Parede" and (el["Par1"]["a"], el["Par1"]["b"]) == (2.0, 0.2)
    assert p["etiquetas_sem_peca"] == []


def test_laje_moldes_e_viga(lida):
    p = lida[1]["plantas"][0]
    lj = p["laje"]
    assert lj["area_bruta"] == pytest.approx(60.0, abs=0.3)
    assert lj["moldes"] == 6 and lj["modulo"] == pytest.approx(0.80, abs=0.011)
    assert lj["aberturas"] == []
    assert [(v["nome"], v["b"], v["h"]) for v in p["vigas"]] == [("V1", 0.30, 0.50)]
    assert p["vigas"][0]["vao"] == pytest.approx(9.40, abs=0.03) and p["vigas"][0]["b_medido"] == pytest.approx(0.30, abs=0.011)
    assert p["n_eixos"] == 4


def test_quantidades(lida):
    folha, r = lida
    m = medicao.consolidar([r], textos=folha.texto)
    assert m["ok"] and m["parametros"]["lamina"] == 0.075
    assert [n["h_livre"] for n in m["niveis"]] == [2.8, 2.8]
    res = m["resumo"]
    assert res["betao_pilares_m3"] == pytest.approx(4 * 0.15 * 5.6, abs=0.02)
    assert res["betao_paredes_nucleos_m3"] == pytest.approx(0.4 * 5.6, abs=0.02)
    e_eq = medicao.espessura_equivalente(0.2, 0.075, 0.8, 0.16)
    assert e_eq == pytest.approx(0.12, abs=1e-6)
    assert res["betao_lajes_m3"] == pytest.approx(2 * ((60 - 3.84) * 0.2 + 3.84 * 0.12), abs=0.15)
    assert res["betao_vigas_m3"] == pytest.approx(0.30 * 0.30 * 9.4 * 2, abs=0.02)
    assert res["moldes_un"] == 12
    assert any("Cota de arranque" in q for q in m["perguntas"])           # o que não está no desenho é perguntado, não inventado
    assert not any("viga(s) sem secção" in q for q in m["perguntas"])     # a secção 30×50 está escrita


def test_cota_de_arranque_indicada_muda_so_o_tramo_de_base(lida):
    folha, r = lida
    a = medicao.consolidar([r], textos=folha.texto)
    b = medicao.consolidar([r], cota_base=-1.0, textos=folha.texto)
    assert b["niveis"][0]["h_livre"] == 3.8 and b["niveis"][1]["h_livre"] == 2.8
    assert b["resumo"]["betao_pilares_m3"] == pytest.approx(a["resumo"]["betao_pilares_m3"] + 4 * 0.15 * 1.0, abs=0.01)
    assert not any("Cota de arranque" in q for q in b["perguntas"])


def test_tracejado_guardado_no_traco_da_o_mesmo_resultado():
    r = leitura.ler_folha(vetores.ler(_planta(tracejado_manual=False)))
    p = r["plantas"][0]
    assert p["laje"]["area_bruta"] == pytest.approx(60.0, abs=0.3) and p["laje"]["moldes"] == 6
    assert p["vigas"] and p["vigas"][0]["vao"] == pytest.approx(9.40, abs=0.03)


def test_sem_escala_pergunta_em_vez_de_inventar():
    folha = vetores.ler(_planta(com_escala=False))
    r = leitura.ler_folha(folha)
    assert not r["ok"] and r["erro"] == "escala"
    assert leitura.ler_folha(folha, 100)["ok"]


def test_sem_caixas_de_nivel_assume_e_pergunta():
    folha = vetores.ler(_planta(niveis=0))
    m = medicao.consolidar([leitura.ler_folha(folha)], textos=folha.texto)
    assert m["ok"] and any("sem caixa de nível" in q for q in m["perguntas"])
    assert any("Espessura da laje" in q for q in m["perguntas"])


def test_seccao_sem_trama_num_so_nivel_e_pilar_que_nasce():
    """Regra entre plantas : desenhado só em contorno no nível onde arranca = ainda não existe abaixo."""
    def planta(i, estados):
        el = [{"nome": n, "tipo": "Pilar", "area": 0.16, "a": 0.4, "b": 0.4, "retangular": True, "perimetro": 1.6, "com_trama": s == "cheio",
               "completada": False, "etiquetado": True} for n, s in estados.items() if s != "sem"]
        return {"elementos": el, "vigas": [], "vigas_sem_medida": [], "etiquetas_sem_peca": [n for n, s in estados.items() if s == "sem"],
                "niveis": [{"nome": f"Piso {i}", "zsup": 3.0 * i, "zinf": None, "e": 0.2}],
                "laje": {"area_bruta": 50.0, "area_fora_do_perimetro": 0.0, "perimetro": 30.0, "aberturas": [], "moldes": 0, "modulo": None}}
    lt = {"plantas": [planta(1, {"P1": "cheio", "P2": "sem", "P3": "sem"}), planta(2, {"P1": "cheio", "P2": "vazio", "P3": "sem"}),
                      planta(3, {"P1": "cheio", "P2": "cheio", "P3": "cheio"})], "avisos": [], "escala": 100}
    m = medicao.consolidar([lt])
    v = {x["nome"]: x for x in m["verticais"]}
    assert len(v["P1"]["niveis"]) == 3
    assert len(v["P2"]["niveis"]) == 3 and any("sem trama" in n for n in v["P2"]["notas"])          # em falta em 2 níveis : omissão do desenho
    lt2 = {"plantas": [planta(1, {"P1": "cheio"}), planta(2, {"P1": "cheio", "P9": "vazio"}), planta(3, {"P1": "cheio", "P9": "cheio"})],
           "avisos": [], "escala": 100}
    v2 = {x["nome"]: x for x in medicao.consolidar([lt2])["verticais"]}
    assert v2["P9"]["niveis"] == ["Piso 3"] and any("nasce" in n for n in v2["P9"]["notas"])


def test_excel_tem_formulas_e_folhas(tmp_path, lida):
    from openpyxl import load_workbook
    folha, r = lida
    m = medicao.consolidar([r], textos=folha.texto)
    wb = load_workbook(excel.gerar(m, str(tmp_path / "mapa.xlsx"), "teste"))
    assert wb.sheetnames == ["Mapa", "Pressupostos", "Verticais", "Lajes", "Vigas"]
    assert str(wb["Verticais"]["K5"].value).startswith("=") and str(wb["Lajes"]["L5"].value).startswith("=")
    assert "SUMIFS" in str(wb["Mapa"]["D6"].value)
    assert wb["Verticais"]["C5"].font.color.rgb.endswith("0000FF")                              # medido = azul, editável


def test_ferramenta_do_assistente(tmp_path):
    class Col:
        def __init__(self):
            self.docs = []

        async def update_one(self, q, upd, upsert=False):
            self.docs.append(upd["$setOnInsert"])

    class DB:
        assistant_artifacts = Col()

    async def loader(db, ids, uid):
        return [("planta_estrutural.pdf", _planta())]
    db = DB()
    res = asyncio.run(assistant_tool.execute("medir_planta_estrutural", {"document_ids": ["doc_1"]}, {"user_id": "u1"}, {"conversation_id": "c1"},
                                             db, doc_loader=loader))
    assert res["ok"] and res["escala"] == "1/100" and res["resumo"]["n_pilares"] == 4
    assert [a["format"] for a in res["artifacts"]] == ["xlsx", "pdf"] and len(db.assistant_artifacts.docs) == 2
    assert all(d["user_id"] == "u1" and d["data_b64"] for d in db.assistant_artifacts.docs)
    vazio = asyncio.run(assistant_tool.execute("medir_planta_estrutural", {"document_ids": []}, {"user_id": "u1"}, {}, db, doc_loader=loader))
    assert vazio["ok"] is False
    assert assistant_tool.TOOL_NAMES == {"medir_planta_estrutural"} and "medir_planta_estrutural" in assistant_tool.INSTRUCTIONS
