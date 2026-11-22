"""«Recurso inacessível» em ciclo (22-23/11/2026, processo RDC + GRUE): o erro passa a dar ao modelo os identificadores reais."""
import asyncio
import re

from routes import assistant as A


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    def find(self, q, proj=None):
        def ok(d):
            for k, v in q.items():
                if isinstance(v, dict) and "$regex" in v:
                    if not re.search(v["$regex"], d.get(k) or "", re.I):
                        return False
                elif d.get(k) != v:
                    return False
            return True
        rows = [d for d in self.docs if ok(d)]

        class _Cur:
            def sort(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def __aiter__(self):
                self._it = iter(rows); return self
            async def __anext__(self):
                try: return next(self._it)
                except StopIteration: raise StopAsyncIteration
        return _Cur()


class _DB:
    plans_takeoff = _Coll([{"user_id": "u", "plan_id": "plan_abc", "filename": "R+1.dxf"}, {"user_id": "x", "plan_id": "plan_zzz", "filename": "outro.dxf"}])
    assistant_docs = _Coll([{"user_id": "u", "doc_id": "doc_1", "filename": "PH-1.dwg"}, {"user_id": "u", "doc_id": "doc_2", "filename": "memoria.pdf"}])


def test_hint_lists_only_this_account_plans_and_cad_docs(monkeypatch):
    monkeypatch.setattr(A, "db", _DB())
    h = asyncio.run(A._available_ids_hint("u"))
    assert "plan_abc (R+1.dxf)" in h and "doc_1 (PH-1.dwg)" in h
    assert "plan_zzz" not in h and "doc_2" not in h


def test_hint_when_nothing_attached(monkeypatch):
    class _Empty:
        plans_takeoff = _Coll([]); assistant_docs = _Coll([])
    monkeypatch.setattr(A, "db", _Empty())
    assert "anexar" in asyncio.run(A._available_ids_hint("u"))
