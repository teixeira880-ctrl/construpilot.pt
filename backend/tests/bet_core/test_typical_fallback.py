"""Documentos sem desenhos (só memória descritiva): o estudo NÃO pára — corre sobre um modelo-tipo (ESTUDO INDICATIVO)."""
import asyncio
import base64
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from engines.bet_core import assistant_tool, typical


def _memoria():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for i, t in enumerate(["MEMÓRIA DESCRITIVA E JUSTIFICATIVA", "Moradia unifamiliar T3 de rés-do-chão, concelho de Loures.",
                           "Área bruta de construção: 160,00 m2.", "Cobertura plana (laje de cobertura) não acessível."]):
        c.drawString(60, 780 - 20 * i, t)
    c.showPage(); c.save()
    return buf.getvalue()


def test_facts_from_text():
    f = typical.facts("Moradia T3 de rés-do-chão, concelho de Loures. Área bruta de construção: 160,00 m2. laje de cobertura")
    assert f["area"] == 160 and f["typology"] == 3 and f["floors"] == 1 and f["flat"] and f["concelho"] == "Loures"


def test_model_single_storey_has_no_stair():
    raw, dec = typical.model([("memoria.pdf", _memoria())], "", "PT")
    assert len(raw["levels"]) == 1 and "stair" not in raw and raw["roof"]["type"] == "terrasse"
    assert raw["envelope"]["width_y"] <= 7.6 and "INDICATIVO" in raw["project"]["name"] and dec


def test_study_without_drawings_completes():
    from tests.bet_core.test_assistant_tool import DB
    db = DB()
    db.assistant_docs.docs.append({"doc_id": "d1", "user_id": "u1", "filename": "memoria.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(_memoria()).decode()})

    async def llm(system, text, images=None, model=None, max_tokens=0):
        return "{}"                                   # leitor não encontra nenhum desenho
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute(
        "generate_full_bet_study", {"document_ids": ["d1"], "hypotheses": "faça o melhor que puder", "country": "PT"},
        user, conv, db, llm=llm, background=False))
    assert out["ok"], out
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done", st
    assert any("INDICATIVO" in d for d in st["decisions"])
    assert len(st["artifacts"]) >= 5


def test_model_fr_labels():
    raw, dec = typical.model([], "Maison T4 de plain-pied, surface habitable 120 m²", "FR")
    assert "INDICATIVE" in raw["project"]["name"] and dec[0].startswith("ÉTUDE INDICATIVE")


def test_slow_reading_falls_back_to_typical(monkeypatch):
    """Leitura demasiado longa (peças escritas sem desenhos): o estudo passa ao modelo-tipo em vez de ficar preso."""
    from tests.bet_core.test_assistant_tool import DB
    from engines.bet_core import reader
    monkeypatch.setenv("BET_READ_TIMEOUT", "1")

    async def slow(*a, **k):
        await asyncio.sleep(30)
    monkeypatch.setattr(reader, "read_building", slow)
    db = DB()
    db.assistant_docs.docs.append({"doc_id": "d1", "user_id": "u1", "filename": "memoria.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(_memoria()).decode()})
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute(
        "generate_full_bet_study", {"document_ids": ["d1"], "hypotheses": "é um teste", "country": "PT"},
        user, conv, db, llm=None, background=False))
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done", st
    assert any("INDICATIVO" in d for d in st["decisions"])


def test_real_drawings_never_replaced_by_typical_model():
    """PC com plantas A3: mesmo que a leitura falhe, NUNCA se troca a casa real por uma moradia-tipo."""
    from reportlab.lib.pagesizes import A3, landscape
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    c.drawString(50, 50, "PLAN DU REZ-DE-CHAUSSEE"); c.rect(100, 100, 800, 500); c.showPage(); c.save()
    assert typical.has_drawings([("PC.pdf", buf.getvalue())])
    assert typical.has_drawings([("x.pdf", buf.getvalue())])
    assert not typical.has_drawings([("G2-AVP etude de sol.pdf", buf.getvalue())])
    assert not typical.has_drawings([("memoria.pdf", _memoria())])
