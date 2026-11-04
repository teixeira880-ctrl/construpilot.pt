"""Lot 58 — chaque manifeste du pitch deck correspond aux fichiers servis."""
import hashlib
import json
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[1] / "assets" / "investors"


def test_manifests_match_files():
    mans = list(BASE.rglob("manifest.json"))
    assert mans
    for man in mans:
        m = json.loads(man.read_text(encoding="utf-8"))
        for rel, meta in m["files"].items():
            f = man.parent / rel
            assert f.exists(), f
            assert hashlib.sha256(f.read_bytes()).hexdigest() == meta["sha256"], f
            assert f.stat().st_size == meta["byte_size"], f
        assert m["source_sha256"] == m["files"]["ConstruPilot_PitchDeck.pptx"]["sha256"]
