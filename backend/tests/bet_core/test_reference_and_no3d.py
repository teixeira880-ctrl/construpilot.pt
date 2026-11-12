"""12/11/2026 (dia de demonstração): PC de referência já verificado → leitura imediata; imagens 3D desligadas no .pt."""
import asyncio

from engines import images3d
from engines.bet_core import reader


def test_reference_case_detected_from_pc_text():
    pages = [{"text": "Permis de construire PCMI01 — 3 Rue Beaufils 93120 La Courneuve", "doc": "PC.pdf", "page": 1, "kind": "autre"}]
    assert reader.reference_case(pages) == "la_courneuve"
    assert reader.reference_case([{"text": "PCMI 02 plan du RDC, Montreuil", "doc": "x", "page": 1, "kind": "plan"}]) is None


def test_reference_reading_is_instant_and_valid(monkeypatch):
    monkeypatch.setattr(reader, "pages_of", lambda data, name: [
        {"doc": name, "page": 1, "kind": "plan", "text": "PCMI02 PLAN DU RDC 3 rue Beaufils LA COURNEUVE", "words": "", "size_mm": (420, 297)}])

    async def no_llm(*a, **k):
        raise AssertionError("o PC de referência não deve chamar a IA")
    rd = asyncio.run(reader.read_building([("PC.pdf", b"%PDF")], "c'est un test", "FR", llm=no_llm))
    assert rd["ok"] and rd["reference"] == "la_courneuve" and rd["model"]["envelope"]["length_x"] == 11.14
    assert any("déjà vérifié" in d for d in rd["decisions"])


def test_3d_images_off_by_default(monkeypatch):
    monkeypatch.delenv("CP_3D_IMAGES", raising=False)
    assert images3d.enabled() is False
    monkeypatch.setenv("CP_3D_IMAGES", "1")
    assert images3d.enabled() is True


def test_3d_on_study_delivered_first_then_perspectives(monkeypatch, tmp_path):
    """Com as imagens 3D ligadas: o estudo é entregue primeiro; as perspetivas entram depois no MESMO dossier + imagens."""
    import base64
    from engines.bet_core import assistant_tool
    from tests.bet_core.test_assistant_tool import DB
    from tests.bet_core.test_typical_fallback import _memoria
    monkeypatch.setenv("CP_3D_IMAGES", "1")
    monkeypatch.setenv("RENDER_CACHE_DIR", str(tmp_path))
    db = DB()
    db.assistant_docs.docs.append({"doc_id": "d1", "user_id": "u1", "filename": "memoria.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(_memoria()).decode()})

    async def llm(*a, **k):
        return "{}"
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["d1"], "hypotheses": "é um teste",
                                                                         "country": "PT"}, user, conv, db, llm=llm, background=False))
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done"
    job = next(j for j in db.bet_study_jobs.docs if j["job_id"] == out["job_id"])
    assert job.get("renders_status") == "done"
    assert sum(a["kind"] == "render_png" for a in job["artifacts"]) >= 3
