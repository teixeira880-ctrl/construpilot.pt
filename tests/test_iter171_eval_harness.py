"""Iteration 171 — evaluation harness over the authorized eval set (ground truth = human-verified fields only)."""
import sys

from pypdf import PdfReader

sys.path.append("/app/backend")

from engines import eval_harness as ev


def test_harness_scores_identity_dimensions_counts_and_layers():
    text = PdfReader("/app/tests/fixtures/eval/AES_COF_0100_R+1_B.pdf").pages[0].extract_text()
    truths = ev.load_truths()
    assert "AES_COF_0100_R+1_B" in truths
    truth = truths["AES_COF_0100_R+1_B"]
    report = ev.evaluate_plan(text, truth, wall_layers=["A-WALL", "S-COLS"])
    assert report["identity"]["correct"] == 4 and report["identity"]["total"] == 4
    assert report["layers"]["ok"] is True and report["verified_by"].startswith("Cartouche")
    bad = ev.evaluate_plan(text, truth, wall_layers=["A-WALL", "A-ANNO-DIMS"])
    assert bad["layers"] == {"false_positive_layers": ["A-ANNO-DIMS"], "ok": False}
    dims = ev.score_dimensions([4.0, 5.0, 5.0, 0.2, 13.27], [4.0, 5.0, 0.2, 0.1])
    assert dims == {"expected": 4, "found": 3, "recall": 0.75, "unmatched_readings": 2, "duplicate_readings": 1}
    counts = ev.score_counts({"window": 3}, {"window": 2, "door": 1})
    assert counts["exact"] == 0 and counts["elements"]["door"]["read"] == 0
    s = ev.summary({"p": report, "q": {**report, "dimensions": dims}})
    assert s["plans"] == 2 and s["identity_fields_correct"] == "8/8" and s["dimension_recall_mean"] == 0.75 and "Échantillon" in s["note"]
