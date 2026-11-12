"""Assistant BTP : tout devis revient avec devis + métré en PDF ET en Excel (09/11/2026)."""
import asyncio
import io
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret")
mm = pytest.importorskip("mongomock_motor")
openpyxl = pytest.importorskip("openpyxl")

DOC = {"doc_id": "doc_q1", "user_id": "u1", "doc_type": "quote", "status": "draft", "title": "Rénovation salle de bain",
       "client_name": "M. Martin", "updated_at": "2026-11-09T07:00:00+00:00",
       "lines": [
           {"line_id": "a", "designation": "Dépose carrelage", "description": "Murs et sol", "qty": 12.5, "unit": "m2",
            "unit_price_ht": 18.0, "vat_rate": 10, "category": "Démolition", "price_source": "user_input"},
           {"line_id": "b", "designation": "Carrelage 60x60", "description": "Fourniture et pose", "qty": 10, "unit": "m2",
            "unit_price_ht": 65.0, "vat_rate": 10, "category": "Revêtements", "price_estimated": True,
            "price_reference_label": "Prix moyen estimé — à vérifier"},
           {"line_id": "c", "designation": "Plinthes", "description": "", "qty": 0, "unit": "ml", "unit_price_ht": 0,
            "vat_rate": 10, "category": "Revêtements", "quantity_missing": True, "price_missing": True},
       ]}


def test_quote_xlsx_has_formulas_and_metre_sheet():
    from engines.assistant_quote_exports import build_quote_xlsx
    wb = openpyxl.load_workbook(io.BytesIO(build_quote_xlsx(DOC, {"company_name": "SARL Test"}, "fr")))
    assert wb.sheetnames == ["Devis", "Métré"]
    ws = wb["Devis"]
    assert ws["A1"].value == "SARL Test" and "BROUILLON" in ws["A3"].value
    assert ws["B8"].value == "Dépose carrelage" and ws["D8"].value == 12.5 and ws["H8"].value.startswith("=ROUND(")
    assert ws["D10"].value is None  # quantité inconnue jamais inventée
    assert any(str(c.value).startswith("=ROUND(SUM(H8:H10)") for row in ws.iter_rows() for c in row if c.value)


def test_metre_xlsx_and_pdf_without_prices_pt():
    from engines.assistant_quote_exports import build_metre_pdf, build_metre_xlsx
    wb = openpyxl.load_workbook(io.BytesIO(build_metre_xlsx(DOC, {}, "pt")))
    ws = wb.active
    assert ws.title == "Medicao" and "RASCUNHO" in ws["A3"].value
    values = [c.value for row in ws.iter_rows() for c in row if c.value is not None]
    assert "Quantidade a confirmar" in values and 65.0 not in values and 18.0 not in values  # aucun prix dans le métré
    assert build_metre_pdf(DOC, {}, "pt")[:5] == b"%PDF-"


def test_attach_exports_four_files_idempotent(monkeypatch):
    import engines.assistant_quote_exports as qx
    db = mm.AsyncMongoMockClient()["t_qx"]
    monkeypatch.setattr(qx, "db", db)

    async def ctx(doc, user):
        return doc, {"company_name": "SARL Test"}, "fr"
    monkeypatch.setattr(qx, "_context", ctx)
    monkeypatch.setattr(qx, "_quote_pdf", lambda doc, b, l: b"%PDF-1.4 devis")
    conv = {"conversation_id": "c1", "_quote_request_id": "r1"}

    async def go():
        await db.pro_documents.insert_one(dict(DOC))
        res = await qx.with_exports({"ok": True, "doc_id": "doc_q1"}, {"user_id": "u1"}, conv)
        files = res["artifacts"]
        assert [f["format"] for f in files] == ["pdf", "xlsx", "pdf", "xlsx", "pdf"]
        assert [f["quote_export"] for f in files] == ["quote_pdf", "quote_xlsx", "metre_pdf", "metre_xlsx", "economic_pdf"]
        assert all("data_b64" not in f and f["download"].startswith("/assistant/artifacts/") for f in files)
        assert await db.assistant_artifacts.count_documents({}) == 5
        again = await qx.with_exports({"ok": True, "doc_id": "doc_q1"}, {"user_id": "u1"}, conv)
        assert [f["artifact_id"] for f in again["artifacts"]] == [f["artifact_id"] for f in files]
        assert await db.assistant_artifacts.count_documents({}) == 5
        # nouvelle version du devis → 4 nouveaux fichiers
        await db.pro_documents.update_one({"doc_id": "doc_q1"}, {"$set": {"updated_at": "2026-11-09T08:00:00+00:00"}})
        await qx.with_exports({"ok": True, "doc_id": "doc_q1"}, {"user_id": "u1"}, conv)
        assert await db.assistant_artifacts.count_documents({}) == 10
        # un autre compte n'obtient rien
        other = await qx.with_exports({"ok": True, "doc_id": "doc_q1"}, {"user_id": "u2"}, conv)
        assert "artifacts" not in other
    asyncio.run(go())


def test_export_failure_never_breaks_quote(monkeypatch):
    import engines.assistant_quote_exports as qx

    async def boom(*a, **k):
        raise RuntimeError("x")
    monkeypatch.setattr(qx, "attach_quote_exports", boom)
    res = asyncio.run(qx.with_exports({"ok": True, "doc_id": "d"}, {"user_id": "u"}, {"conversation_id": "c"}))
    assert res["ok"] is True and "files_error" in res and "artifacts" not in res


def test_real_quote_pdf_builder_on_draft():
    from engines.assistant_quote_exports import _quote_pdf
    assert _quote_pdf(dict(DOC), {"company_name": "SARL Test"}, "fr")[:5] == b"%PDF-"


def test_instructions_require_four_files():
    from engines.assistant_quote_exports import EXPORT_INSTRUCTIONS
    assert "devis PDF, devis Excel, métré PDF, métré Excel" in EXPORT_INSTRUCTIONS
    assert "orçamento PDF, orçamento Excel, medição PDF, medição Excel" in EXPORT_INSTRUCTIONS
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent / "routes" / "assistant.py").read_text("utf-8")
    assert "QUOTE_INSTRUCTIONS + EXPORT_INSTRUCTIONS" in src
