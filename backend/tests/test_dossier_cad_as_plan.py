"""DWG/DXF de um processo importado (ZIP/pasta) utilizável como planta pelas ferramentas CAD do Assistente.

Regressão de 22/11/2026: processo «RDC + GRUE» (9 DWG de um prédio) → extract_autodesk_data recebia o doc_… como plan_id e
devolvia «Recurso inacessível» em ciclo; read_document tentava ler o DWG como PDF. Conversão DWG simulada (sem rede)."""
import asyncio
import base64

import pytest

from routes import assistant as A


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None, **_):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def update_one(self, q, upd, **_):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set", {}))
                return

    def find(self, q, proj=None):
        rows = [dict(d) for d in self.docs if all(d.get(k) == v for k, v in q.items())]

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
    def __init__(self):
        self.assistant_docs, self.plans_takeoff, self.assistant_doc_chunks = _Coll(), _Coll(), _Coll()


@pytest.fixture
def env(monkeypatch):
    db = _DB()
    monkeypatch.setattr(A, "db", db)
    calls = []

    async def fake_store(data, filename, content_type, user, project_id, deskew, cad_unit, display_name=None):
        await asyncio.sleep(0.01)
        calls.append(filename)
        pid = f"plan_{len(calls):012d}"
        db.plans_takeoff.docs.append({"plan_id": pid, "user_id": user["user_id"], "filename": filename})
        return {"plan_id": pid}

    import routes.plans_crud as P
    monkeypatch.setattr(P, "_process_and_store", fake_store)
    db.assistant_docs.docs += [
        {"doc_id": "doc_rdc", "user_id": "u1", "dossier_id": "dos_1", "filename": "RDC + GRUE.dwg", "format": "dwg",
         "data_b64": base64.b64encode(b"AC1027 fake").decode()},
        {"doc_id": "doc_pdf", "user_id": "u1", "dossier_id": "dos_1", "filename": "notice.pdf", "format": "pdf", "data_b64": ""},
        {"doc_id": "doc_other", "user_id": "u2", "dossier_id": "dos_9", "filename": "R+1.dwg", "format": "dwg", "data_b64": ""},
    ]
    return db, calls


@pytest.mark.anyio
async def test_dossier_dwg_doc_becomes_plan_once(env):
    db, calls = env
    user = {"user_id": "u1"}
    args = {"plan_id": "doc_rdc"}
    await A._resolve_plan_args(args, user)
    assert args["plan_id"].startswith("plan_")
    again = {"plan_id": "doc_rdc"}
    await A._resolve_plan_args(again, user)
    assert again["plan_id"] == args["plan_id"] and len(calls) == 1          # idempotente: uma só importação
    assert (await A._allowed_plan(args["plan_id"], "u1"))["plan_id"] == args["plan_id"]


@pytest.mark.anyio
async def test_concurrent_calls_import_once(env):
    db, calls = env
    user = {"user_id": "u1"}
    a, b = {"plan_id": "doc_rdc"}, {"dxf_plan_id": "doc_rdc"}
    await asyncio.gather(A._resolve_plan_args(a, user), A._resolve_plan_args(b, user))
    assert a["plan_id"] == b["dxf_plan_id"] and len(calls) == 1


@pytest.mark.anyio
async def test_filename_from_inventory_resolves(env):
    _, calls = env
    args = {"plan_id": "RDC + GRUE.dwg"}
    await A._resolve_plan_args(args, {"user_id": "u1"})
    assert args["plan_id"].startswith("plan_") and calls == ["RDC + GRUE.dwg"]


@pytest.mark.anyio
async def test_no_change_for_plans_pdfs_or_other_accounts(env):
    _, calls = env
    for args in ({"plan_id": "plan_abc"}, {"plan_id": "doc_pdf"}, {"plan_id": "doc_other"}, {"plan_id": "doc_inexistente"}):
        before = dict(args)
        await A._resolve_plan_args(args, {"user_id": "u1"})
        assert args == before
    assert calls == []
    with pytest.raises(PermissionError):                                    # isolamento de contas mantido
        await A._allowed_plan("doc_other", "u1")
