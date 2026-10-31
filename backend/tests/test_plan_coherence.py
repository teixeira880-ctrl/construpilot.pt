"""Contrôle archi ↔ BET (engines.plan_coherence) — cas réel Houilles (plan archi RDC image + coffrage BET Structuro vectoriel).

Régression du 30/10/2026 : l'ancienne comparaison « à l'IA » annonçait « travée centrale archi 2,70 / BET 4,70 » (cote verticale
comparée à une horizontale) et « profondeur 4,53 + 4,53 » (cotes de terrasse). Ces tests verrouillent les règles du moteur."""
import io
import json
from pathlib import Path

import pytest

from engines import plan_coherence as pc

FIX = Path(__file__).parent / "fixtures" / "plan_coherence"


@pytest.fixture(scope="module")
def bet():
    return pc.prepare_vector((FIX / "bet_houilles_coffrage.pdf").read_bytes(), 0, "RDC", "Estruturas")


@pytest.fixture(scope="module")
def archi():
    vis = json.loads((FIX / "archi_houilles_rdc_vision.json").read_text())
    return pc.prepare_raster((FIX / "archi_houilles_rdc.jpg").read_bytes(), vis, "Arquitetura")


@pytest.fixture(scope="module")
def result(archi, bet):
    return pc.finalize(archi, bet, "Superposition RDC — archi × BET")


def test_bet_multi_view_sheet_picks_requested_level(bet):
    assert bet["ok"] and bet["source"] == "vetorial"
    assert bet["view"] == "PH RDC"
    assert set(bet["views"]) >= {"PH RDC", "PH VS", "PH R+1", "TOITURE"}


def test_bet_reference_chains_keep_orientation(bet):
    h = pc.reference_chain(bet["chains"], "h")
    v = pc.reference_chain(bet["chains"], "v")
    assert h["values"] == [5.2, 2.7, 5.33]
    assert v["values"] == [4.7, 4.7, 5.2]


def test_matches_compare_same_orientation_only(result):
    h, v = result["matches"]["h"], result["matches"]["v"]
    assert h["archi_chain"] == [5.2, 2.7, 5.19] and h["bet_chain"] == [5.2, 2.7, 5.33]
    assert v["archi_chain"] == [4.7, 4.7, 5.2] and v["bet_chain"] == [4.7, 4.7, 5.2]
    assert [r["statut"] for r in h["rows"]] == ["conforme", "conforme", "incoherence"]
    assert h["rows"][2]["ecart_mm"] == 140
    assert all(r["statut"] == "conforme" for r in v["rows"])


def test_old_false_findings_never_come_back(result):
    text = " ".join(f["detail"] for f in result["findings"])
    assert "4,70 m / BET" not in text or "archi 2,70" not in text
    assert not any(f.get("type") == "archi_vs_bet" and f.get("bet_m") == 4.7 and f.get("archi_m") == 2.7 for f in result["findings"])
    assert not any(f.get("type") == "archi_vs_bet" and 4.53 in (f.get("archi_m"), f.get("bet_m")) for f in result["findings"])
    unused = [u["values"] for u in result["unused_archi_chains"]]
    assert [4.53, 4.53] in unused  # terrasse : listée, jamais comparée au bâtiment


def test_internal_inconsistencies(result):
    kinds = {(f["type"], f.get("plan")) for f in result["findings"]}
    assert ("chaines_opposees", "Arquitetura") in kinds          # 5,20 / 2,70 en tête vs 5,60 / 2,10 en pied
    assert ("totaux_opposes", "Estruturas") in kinds              # 13,10 en haut vs 13,23 en bas : façade est biaise
    assert ("cote_vs_dessin", "Arquitetura") in kinds            # 5,60 écrit, ≈ 5,2 dessiné


def test_overlay_is_computed_and_calibrated(result):
    cal = result["calibration"]
    assert cal and cal["residual_px"] < 6
    from PIL import Image
    im = Image.open(io.BytesIO(result["overlay_png"]))
    assert im.width > 1500 and im.height > 1500


def test_vision_orientation_is_checked_against_geometry():
    import numpy as np
    img = np.full((400, 400, 3), 255, np.uint8)
    data = {"chains": [{"orientation": "horizontal", "values": [2.0, 3.0], "ticks_px": [[100, 50], [100, 150], [100, 300]], "objet": "batiment"},
                       {"orientation": "vertical", "values": [2.0, 3.0], "ticks_px": [[50, 380], [150, 380], [300, 380]], "objet": "batiment"}]}
    chains, scale, notes = pc.chains_from_vision(data, img)
    assert sorted(c["o"] for c in chains) == ["h", "v"]
    assert chains[0]["o"] != "h" or chains[0]["values"] == [2.0, 3.0]
    assert len(notes) == 2 and scale == pytest.approx(50, rel=0.01)


def test_no_cross_orientation_match():
    ref = {"o": "h", "orientation": "horizontal", "values": [4.7, 4.7], "sum_m": 9.4}
    vertical_only = [{"o": "v", "values": [4.7, 4.7], "sum_m": 9.4}]
    assert pc.match_reference(vertical_only, ref) is None


def test_tool_schema_is_strict():
    from engines.plan_coherence_tool import PLANS_COHERENCE_TOOL
    p = PLANS_COHERENCE_TOOL["parameters"]
    assert set(p["required"]) == set(p["properties"]) and p["additionalProperties"] is False


def test_tool_end_to_end_stores_png_and_pdf(monkeypatch):
    import asyncio
    asyncio.run(_e2e(monkeypatch))


async def _e2e(monkeypatch):
    """Outil complet : sources chargées, relevé image simulé (aucun appel IA), PNG + PDF stockés comme artefacts NON illustratifs."""
    import base64
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:1")
    os.environ.setdefault("DB_NAME", "test")
    from engines import plan_coherence_tool as tool

    vis = json.loads((FIX / "archi_houilles_rdc_vision.json").read_text())

    async def fake_vision(png):
        return vis, "test/vision"
    monkeypatch.setattr(tool, "_vision_chains", fake_vision)

    stored = {}

    class Coll:
        async def update_one(self, q, u, upsert=False):
            stored[q["artifact_id"]] = u["$setOnInsert"]

    class DB:
        assistant_artifacts = Coll()

    async def load_source(ident, uid):
        if ident == "doc_archi":
            return {"filename": "archi.jpg", "image_b64": base64.b64encode((FIX / "archi_houilles_rdc.jpg").read_bytes()).decode()}
        return {"filename": "bet.pdf", "pdf_bytes": (FIX / "bet_houilles_coffrage.pdf").read_bytes()}

    res = await tool.run({"document_archi": "doc_archi", "document_bet": "doc_bet", "level": "RDC", "page_archi": 0, "page_bet": 0},
                         {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}, DB(), load_source)
    assert res["ok"] and res["sources"]["bet"]["vue"] == "PH RDC"
    assert res["artifact"]["format"] == "png" and res["pdf_artifact"]["format"] == "pdf"
    assert all(d["illustrative"] is False and d["computed_overlay"] for d in stored.values())
    assert res["matches"]["h"]["rows"][2]["ecart_mm"] == 140


def test_image_tools_refused_in_plan_comparison_context(monkeypatch):
    import asyncio
    asyncio.run(_guard(monkeypatch))


async def _guard(monkeypatch):
    """Régression ERR-EF3B / ERR-F146 (30/10, 23 h 39) : sur une relance « mets à jour le tableau et les schémas comparatifs » sans mot
    « BET », l'Assistant retouchait le plan par IA. Le contexte (plans joints, contrôle déjà lancé) doit suffire à refuser."""
    import os
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:1")
    os.environ.setdefault("DB_NAME", "test")
    os.environ.setdefault("JWT_SECRET", "test-only-not-a-secret")
    for k, v in {"STUDIES_MODEL_ANALYSIS": "test", "STUDIES_MODEL_LIGHT": "test"}.items():
        os.environ.setdefault(k, v)  # import du module seulement : aucun appel de modèle dans ce test  # sans effet en préproduction : la vraie valeur du .env prime
    import routes.assistant as ra

    class Actions:
        def __init__(self, hit):
            self.hit = hit

        async def find_one(self, q, proj=None):
            return {"x": 1} if self.hit and q.get("tool") == "check_plans_coherence" else None

    class Cursor:
        def limit(self, n):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class Msgs:
        def find(self, q, proj=None):
            return Cursor()

    class DB:
        def __init__(self, hit):
            self.assistant_actions = Actions(hit)
            self.assistant_msgs = Msgs()

    plans = [{"doc_id": "doc_a", "filename": "Plan RDC archi.jpg", "kind": "photo"},
             {"doc_id": "doc_b", "filename": "STRUCTURO-Coffrage-général-v21.pdf", "kind": "plan"}]
    monkeypatch.setattr(ra, "db", DB(False))
    ctx = ra._plan_comparison_context
    assert await ctx({"_user_request_text": "Podes atualizar com este quadro e os esquemas comparativos?", "_conv_docs": plans}, "u")
    assert await ctx({"_user_request_text": "refaz a imagem", "_conv_docs": plans}, "u")                     # 2 plans joints
    assert await ctx({"_user_request_text": "encontra as incoerências", "_conv_docs": []}, "u")
    assert not await ctx({"_user_request_text": "retoca a foto: fachada em reboco branco", "_conv_docs": [
        {"doc_id": "doc_p", "filename": "IMG_2041.jpg", "kind": "photo"}]}, "u")                            # vraie photo : autorisé
    monkeypatch.setattr(ra, "db", DB(True))
    assert await ctx({"_user_request_text": "corrige a imagem", "_conv_docs": []}, "u")                       # contrôle déjà lancé

    conv = {"_user_request_text": "atualiza o quadro comparativo em imagem", "_conv_docs": plans, "conversation_id": "c"}
    r1 = await _guarded(ra, "create_downloadable_file", {"format": "jpg"}, conv)
    r2 = await _guarded(ra, "edit_image_from_photo", {"document_id": "doc_a"}, conv)
    assert r1["ok"] is False and "check_plans_coherence" in r1["error"]
    assert r2["ok"] is False and "check_plans_coherence" in r2["error"]


async def _guarded(ra, name, args, conv):
    """Rejoue uniquement la garde placée en tête des deux branches de _exec_tool (sans base ni modèle)."""
    if name == "create_downloadable_file" and args.get("format") == "jpg" and await ra._plan_comparison_context(conv, "u"):
        return {"ok": False, "error": ra.PLAN_IMAGE_REFUSAL}
    if name == "edit_image_from_photo" and await ra._plan_comparison_context(conv, "u"):
        return {"ok": False, "error": ra.PLAN_IMAGE_REFUSAL}
    return {"ok": True}
