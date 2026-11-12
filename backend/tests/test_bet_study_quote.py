"""Orçamento oficial = métré determinístico do estudo BET: mesmos documentos → mesmo orçamento (sem divergências)."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import pytest


def test_study_quote_matches_study_and_is_stable(monkeypatch):
    mm = pytest.importorskip("mongomock_motor")
    db = mm.AsyncMongoMockClient()["t"]
    import core.db
    monkeypatch.setattr(core.db, "db", db)
    import engines.bet_core.assistant_tool as AT
    import engines.assistant_quote_exports  # noqa: F401
    import engines.assistant_quote_pricing  # noqa: F401
    import engines.assistant_quote_service  # noqa: F401
    for m in list(sys.modules.values()):
        if type(getattr(m, "db", None)).__name__ in ("AsyncIOMotorDatabase", "AgnosticDatabase"):
            monkeypatch.setattr(m, "db", db)
    from engines.bet_core import pipeline
    raw = json.loads((Path(__file__).resolve().parents[1] / "engines/bet_core/cases/moradia_pt_demo.json").read_text())
    res = pipeline.run(json.loads(json.dumps(raw)), tempfile.mkdtemp(), None, "pt", None, None)

    async def run():
        await db.users.insert_one({"user_id": "u1", "account_type": "pro", "plan": "business", "brand_country": "PT"})
        a = await AT.study_quote(db, "u1", "c1", "job1", res, "PT", raw)
        b = await AT.study_quote(db, "u1", "c1", "job1", res, "PT", raw)
        return a, b, await db.pro_documents.find_one({"doc_id": a[0]})
    a, b, d = asyncio.run(run())
    assert a[0] and a[0] == b[0]
    assert abs(d["totals"]["ht"] - res["devis_ht"]) < 0.05 and abs(d["totals"]["ttc"] - res["devis_ttc"]) < 0.05
    assert [f["quote_export"] for f in a[1]] == ["quote_pdf", "quote_xlsx", "metre_pdf", "metre_xlsx", "economic_pdf"]
    assert d["source"] == "bet_study" and d["assistant_conversation_id"] == "c1"
