"""Nível pelo nome do ficheiro (regra de Martinho, 23/11/2026): R-1, PH-1, SS1, PH SS-1, PHss-2, sous-sol e cave são
subsolos; RDC e PH RDC são 0; R+n e PH R+n são pisos; fondations fica abaixo de tudo."""
import asyncio

import pytest

from routes.assistant import _auto_lower_plan, _nivel_do_nome


@pytest.mark.parametrize("name,nivel", [
    ("R-1.dwg", -1), ("PH-1.dwg", -1), ("SS1.dwg", -1), ("SS-2.dwg", -2),
    ("PH SS-1.dwg", -1), ("PHss-2.dwg", -2), ("PH.SS-1.dwg", -1),
    ("sous sol Nexity (2).dwg", -1), ("Cave B3.dwg", -1),
    ("RDC.dwg", 0), ("EXE_AES_BET_TZ_RDC_COF_(0001-D).dwg", 0), ("Vue en plan du PH RDC.dwg", 0),
    ("R+1.dwg", 1), ("AES_EXE_BET_TZ_R+2_COF_0200.dwg", 2), ("Vue en plan du PH R+1.dwg", 1), ("R+5.dwg", 5),
    ("AES_EXE_BET_TZ_FON_COF_5200.dwg", -99), ("Plan coffrage Fondation - A.dwg", -99),
    ("AXE (2).dwg", None), ("memoria.pdf", None),
])
def test_nivel_do_nome(name, nivel):
    assert _nivel_do_nome(name) == nivel


class _Cur:
    def __init__(self, rows): self._rows = rows
    def sort(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def __aiter__(self): self._it = iter(self._rows); return self
    async def __anext__(self):
        try: return next(self._it)
        except StopIteration: raise StopAsyncIteration


class _DB:
    def __init__(self, plans, docs): self._p, self._d = plans, docs
    class _Coll:
        def __init__(self, rows): self.rows = rows
        async def find_one(self, q, proj=None):
            for r in self.rows:
                if all(r.get(k) == v for k, v in q.items() if not isinstance(v, dict)): return dict(r)
            return None
        def find(self, q, proj=None): return _Cur([dict(r) for r in self.rows if r.get("user_id") == q.get("user_id")])
    @property
    def plans_takeoff(self): return self._Coll(self._p)
    @property
    def assistant_docs(self): return self._Coll(self._d)


def test_auto_lower_picks_floor_immediately_below(monkeypatch):
    from routes import assistant as A
    plans = [{"user_id": "u", "plan_id": "plan_rdc", "filename": "RDC.dxf", "cad_import": {"original_filename": "RDC.dwg"}},
             {"user_id": "u", "plan_id": "plan_ph1", "filename": "PH-1.dxf", "cad_import": {"original_filename": "PH-1.dwg"}},
             {"user_id": "u", "plan_id": "plan_fon", "filename": "FON_COF.dxf", "cad_import": {"original_filename": "Plan coffrage Fondation.dwg"}}]
    monkeypatch.setattr(A, "db", _DB(plans, []))
    assert asyncio.run(A._auto_lower_plan("plan_rdc", {"user_id": "u"})) == "plan_ph1"      # PH-1, não as fundações
    assert asyncio.run(A._auto_lower_plan("plan_ph1", {"user_id": "u"})) == "plan_fon"
    assert asyncio.run(A._auto_lower_plan("plan_fon", {"user_id": "u"})) is None
