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
