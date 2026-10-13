"""Iteration 169 — Phase 4: Model Derivative summary (real translation of the authorized DWG, cached job) and revision comparison (H)."""
import asyncio
import sys

sys.path.append("/app/backend")

from engines.autodesk_md import summarize, urn_for
from engines.autodesk_md_tools import compare_revisions, plan_text


def test_summarize_dwg_entities_are_not_walls():
    collection = [{"objectid": 1, "name": "Line", "properties": {"General": {"Layer": "A-WALL", "Name ": "Line"}, "Geometry": {"Length": 2.5}}},
                  {"objectid": 2, "name": "Line", "properties": {"General": {"Layer": "A-WALL"}}},
                  {"objectid": 3, "name": "Text", "properties": {"General": {"Layer": "A-ANNO-DIMS"}, "Text": {"Contents": "13.27"}}}]
    s = summarize(collection, "dwg")
    assert s["objects"] == 3 and s["layers"][0] == ("A-WALL", 2) and "ne sont pas des murs identifiés" in s["note"]
    assert "Text/Contents" in s["property_keys"]
    assert "exploitables telles quelles" in summarize(collection, "rvt")["note"]


def test_urn_is_base64url_of_object_id():
    urn = urn_for("urn:adsk.objects:os.object:bucket/md-x-input.dwg")
    assert urn.startswith("dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6") and "=" not in urn


def _plan(pid, text, md=None):
    return {"plan_id": pid, "filename": f"{pid}.pdf", "pages": [{"text_blocks": [{"text": text}]}], **({"model_derivative": md} if md else {})}


TB_A = "TITRE DU PLAN ECHELLE TYPE N° DOC NIVEAU ZONE INDICE Plan coffrage PH R+1 1/50 COF 0100 R+1 TZ A  A 22/10/2021 AES - M.R Première Diffusion"
TB_B = "TITRE DU PLAN ECHELLE TYPE N° DOC NIVEAU ZONE INDICE Plan coffrage PH R+1 1/50 COF 0100 R+1 TZ B  A 22/10/2021 AES - M.R Première Diffusion  B 23/11/2021 AES - M.R MAJ Générale"


def test_H_revisions_are_kept_separate_and_never_summed():
    md_a = {"views": [{"layers": [["A-WALL", 7000], ["S-BEAM", 1700]]}]}
    md_b = {"views": [{"layers": [["A-WALL", 7520], ["S-BEAM", 1769], ["S-COLS", 1246]]}]}
    res = compare_revisions(_plan("pA", TB_A, md_a), _plan("pB", TB_B, md_b), md_a, md_b)
    assert res["status"] == "different_revisions" and "ne doivent PAS être additionnées" in res["note"]
    assert res["a"]["revision_index"] == "A" and res["b"]["revision_index"] == "B" and res["b"]["revision_date"] == "23/11/2021"
    assert {d["layer"]: (d["a"], d["b"]) for d in res["layer_differences"]} == {"A-WALL": (7000, 7520), "S-BEAM": (1700, 1769), "S-COLS": (0, 1246)}
    assert res["scale_warning"] is None
    same = compare_revisions(_plan("pB", TB_B), _plan("pB2", TB_B), None, None)
    assert same["status"] == "same_revision"
    other = compare_revisions(_plan("pB", TB_B), _plan("pX", "Plan architecte ARC 0200 R+2 1/100 A 01/02/2022 X Diffusion"), None, None)
    assert other["status"] == "different_documents" and other["scale_warning"]


def test_real_translation_job_is_cached_for_the_authorized_dwg():
    """The authorized DWG (AES COF 0100 R+1 indice B) was translated once; the cached job must expose real layers."""
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from core.db import db

    async def fetch():
        return await db.model_derivative_jobs.find_one({"filename": "AES_COF_0100_R+1_B.dwg", "status": "success"}, {"_id": 0, "views": 1, "cached": 1})
    job = asyncio.get_event_loop().run_until_complete(fetch())
    assert job, "translation job missing — run /tmp/md_run.py once (consumes Autodesk credits)"
    layers = dict(map(tuple, job["views"][0]["layers"]))
    assert job["views"][0]["objects"] > 10000 and layers["A-WALL"] > 7000 and "A-ANNO-DIMS" in layers
    assert plan_text({"pages": [{"text_blocks": [{"text": "a"}, {"text": "b"}]}]}) == "a b"
