"""Mémoire de lecture de l'Assistant BTP (09/11/2026) : les pages déjà lues ne sont pas relues."""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret")
mm = pytest.importorskip("mongomock_motor")


def test_ranges():
    from engines.assistant_read_memory import ranges as _ranges
    assert _ranges({1, 2, 3, 5, 7, 8}) == "1–3, 5, 7–8"
    assert _ranges([4]) == "4"


def test_pages_read_map(monkeypatch):
    from engines.assistant_read_memory import pages_read_map
    db = mm.AsyncMongoMockClient()["t_read"]

    async def go():
        for first in (1, 4, 7, 16, 19):
            await db.assistant_actions.insert_one({"conversation_id": "c1", "user_id": "u", "tool": "read_document",
                                                   "doc_id": "doc_pc", "pages_read": [first, first + 1, first + 2], "total_pages": 21})
        await db.assistant_actions.insert_one({"conversation_id": "c1", "user_id": "u", "tool": "read_document",
                                               "doc_id": "doc_g2", "pages_read": [22, 23, 24], "total_pages": 25})
        await db.assistant_actions.insert_one({"conversation_id": "other", "user_id": "u", "tool": "read_document",
                                               "doc_id": "doc_pc", "pages_read": [10], "total_pages": 21})
        m = await pages_read_map(db, "c1", "u")
        assert m["doc_pc"]["pages"] == set(range(1, 10)) | set(range(16, 22))
        assert m["doc_pc"]["total"] == 21 and 10 not in m["doc_pc"]["pages"]
        assert m["doc_g2"]["pages"] == {22, 23, 24}
    asyncio.run(go())
