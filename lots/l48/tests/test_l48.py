"""Lot 48 — l'import PDF refuse un document dont le numéro existe déjà."""
import ast
import asyncio
import pathlib

SRC = (pathlib.Path(__file__).resolve().parents[1] / "routes" / "documents.py").read_text(encoding="utf-8")


def _fn():
    tree = ast.parse(SRC)
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_already_imported")
    return node


class _Coll:
    def __init__(self, docs):
        self.docs = docs

    async def find_one(self, flt, proj=None):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)


class _DB:
    def __init__(self, docs):
        self.pro_documents = _Coll(docs)


def _load(db):
    ns = {"db": db}
    exec(compile(ast.Module(body=[_fn()], type_ignores=[]), "documents.py", "exec"), ns)
    return ns["_already_imported"]


def test_detects_duplicate_only_same_user_type_number():
    db = _DB([{"user_id": "u1", "doc_type": "invoice", "number": "F202600114", "doc_id": "d1"}])
    f = _load(db)
    assert asyncio.run(f("u1", "invoice", "F202600114")) is True
    assert asyncio.run(f("u1", "quote", "F202600114")) is False
    assert asyncio.run(f("u2", "invoice", "F202600114")) is False
    assert asyncio.run(f("u1", "invoice", None)) is False


def test_both_import_paths_guarded():
    assert SRC.count("await _already_imported(") == 2
    assert '"duplicate": True' in SRC
