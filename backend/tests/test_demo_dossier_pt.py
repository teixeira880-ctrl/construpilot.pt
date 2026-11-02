"""Lote 46 PT — dossier demo « Moradia Ferreira » (planta real, levantamento exato, orçamento real)."""
import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import demo_dossier_pt as D  # noqa: E402


def _load_compute_totals():
    """routes.documents._compute_totals sem importar o módulo (que exige a base de dados)."""
    import ast
    tree = ast.parse((ROOT / "routes" / "documents.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_compute_totals")
    ns: dict = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "documents.py", "exec"), ns)
    return ns["_compute_totals"]


_compute_totals = _load_compute_totals()
from engines.catalog import LOTS_BY_KEY  # noqa: E402

UID = "user_demo_test"


def _data():
    return json.loads(D.DATA_FILE.read_text(encoding="utf-8"))["pro"]


def test_files_present():
    assert D.DATA_FILE.exists()
    for f in ("plan-moradia-ferreira-pt.pdf", "plan-moradia-ferreira-pt.png", "rooms_ferreira_pt.json"):
        assert (ROOT / "assets" / "demo_plans" / f).stat().st_size > 1000


def test_contents_and_no_real_company():
    d = _data()
    assert {k: len(v) for k, v in d.items()} == {"clients": 3, "chantiers": 3, "plans_takeoff": 1, "pro_documents": 4}
    raw = D.DATA_FILE.read_text(encoding="utf-8").lower()
    assert "cm renov" not in raw and "cmrenov" not in raw


def test_totals_match_app_engine():
    for doc in _data()["pro_documents"]:
        assert doc["totals"] == _compute_totals(doc["lines"], doc.get("deposit_pct") or 0), doc["doc_id"]


def test_quote_quantities_come_from_plan():
    d = _data()
    rooms = d["plans_takeoff"][0]["rooms"]
    assert len(rooms) == 9
    floor = round(sum(r["surface_m2"] for r in rooms), 2)
    assert floor == 115.59
    q = d["pro_documents"][0]
    assert q["number"] == "DEV-2026-0007" and q["totals"]["ht"] == 61940.19
    assert q["lines"][0]["qty"] == floor
    lot = LOTS_BY_KEY["demolition"]
    assert q["lines"][0]["unit_price_ht"] == lot["mat_std"] + lot["labour"]
    assert all(l["vat_rate"] == 23.0 for l in q["lines"])


def test_deposit_invoice_paid_and_linked():
    docs = {x["doc_id"]: x for x in _data()["pro_documents"]}
    inv = docs["doc_sousa_pt_inv"]
    q = docs[inv["parent_doc_id"]]
    assert q["signed"] and q["deposit_invoice_id"] == inv["doc_id"]
    assert inv["status"] == "paid" and inv["paid"] == inv["totals"]["ttc"] and inv["remaining_due"] == 0
    assert inv["lines"][0]["unit_price_ht"] == round(q["totals"]["ht"] * 0.30, 2)


class _Res:
    def __init__(self, upserted):
        self.upserted_id = upserted


class _Coll:
    def __init__(self):
        self.docs = []

    def _find(self, flt):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in flt.items())), None)

    async def update_one(self, flt, upd, upsert=False):
        if self._find(flt):
            return _Res(None)
        self.docs.append(dict(upd["$setOnInsert"]))
        return _Res("new")

    async def replace_one(self, flt, doc, upsert=False):
        cur = self._find(flt)
        if cur:
            self.docs.remove(cur)
        self.docs.append(dict(doc))
        return _Res(None if cur else "new")


class _DB(dict):
    def __getitem__(self, k):
        return self.setdefault(k, _Coll())


def test_apply_idempotent_and_restore():
    db = _DB()
    r1 = asyncio.run(D.apply_demo_dossier_pt(db, UID, "websummit_2026"))
    assert r1["written"] == {"clients": 3, "chantiers": 3, "plans_takeoff": 1, "pro_documents": 4}
    r2 = asyncio.run(D.apply_demo_dossier_pt(db, UID, "websummit_2026"))
    assert sum(r2["written"].values()) == 0
    assert len(db["pro_documents"].docs) == 4
    d = db["pro_documents"].docs[0]
    assert d["user_id"] == UID and d["is_demo"] and "__PRO_UID__" not in json.dumps(d)
    d["title"] = "alterado durante a demo"
    asyncio.run(D.apply_demo_dossier_pt(db, UID, "websummit_2026", restore=True))
    assert len(db["pro_documents"].docs) == 4
    assert all(x["title"] != "alterado durante a demo" for x in db["pro_documents"].docs)


def test_skips_without_user():
    assert asyncio.run(D.apply_demo_dossier_pt(_DB(), None, "x"))["status"] == "skipped_no_user"


def test_seed_hooks_present():
    src = (ROOT / "core" / "websummit_seed_pt.py").read_text(encoding="utf-8")
    assert src.count("apply_demo_dossier_pt") >= 2
    assert '"pro_documents", "plans_takeoff", "clients", "chantiers"' in src
