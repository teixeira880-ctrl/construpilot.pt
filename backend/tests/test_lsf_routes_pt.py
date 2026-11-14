"""Rotas /lsf no .pt: criação a partir de planta lida / dados, edição, preços, PDF, Excel, 3D — sem Mongo real nem IA."""
import asyncio
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lsf")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.lsf")
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mep_moradia_exemplo.json")


class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Coll:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _match(d, q):
        return all(d.get(k) == v for k, v in q.items())

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def find_one(self, q, proj=None):
        d = next((d for d in self.docs if self._match(d, q)), None)
        return dict(d) if d else None

    def find(self, q, proj=None):
        return _Cur([dict(d) for d in self.docs if self._match(d, q)])

    async def update_one(self, q, upd):
        for d in self.docs:
            if self._match(d, q):
                d.update(upd.get("$set") or {})

    async def delete_one(self, q):
        n = len(self.docs)
        self.docs = [d for d in self.docs if not self._match(d, q)]

        class R:
            deleted_count = n - len(self.docs)
        return R()


class _DB:
    def __init__(self):
        self.lsf_studies, self.plans_takeoff, self.users, self.organizations, self.company_price_libraries = (_Coll() for _ in range(5))


@pytest.fixture()
def db(monkeypatch):
    d = _DB()
    monkeypatch.setattr(M, "db", d)

    async def _lib(uid):
        return [{"designation": "OSB/3 12 mm", "unit": "un", "unit_price": 14.5}]
    monkeypatch.setattr(M, "_biblioteca", _lib)

    async def _no_render(doc, st, uid):
        return []
    monkeypatch.setattr(M, "_render", _no_render)
    d.users.docs.append({"user_id": "u1", "brand_company_name": "Construtora Teste, Lda"})
    return d


def test_fluxo_completo(db):
    user = {"user_id": "u1"}
    data = json.load(open(FIX))
    data["country"] = "pt"
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=data, title="Moradia exemplo"), user))
    assert st["study_id"].startswith("lsf_") and st["summary"]["pecas"] > 1000
    osb = next(l for l in st["lines"] if l["code"] == "PL-OSB12")
    assert osb["preco"]["origem"] == "biblioteca" and osb["preco"]["unit"] == 14.5
    assert asyncio.run(M.list_studies(user))["studies"][0]["study_id"] == st["study_id"]
    pdf = asyncio.run(M.study_pdf(st["study_id"], "pt", user))
    assert pdf.body[:4] == b"%PDF" and "Estudo-LSF" in pdf.headers["content-disposition"]
    xl = asyncio.run(M.study_xlsx(st["study_id"], "pt", user))
    assert xl.body[:2] == b"PK" and ".xlsx" in xl.headers["content-disposition"]
    vw = asyncio.run(M.study_viewer(st["study_id"], "pt", user))
    assert b"window.LSF=" in vw.body
    proj = st["project"]
    for T in proj["tiposParede"].values():
        T["espacamento"] = 400
    up = asyncio.run(M.update_project(st["study_id"], M.ProjectIn(project=proj), user))
    assert up["version"] == 2 and up["summary"]["pecas"] > st["summary"]["pecas"]
    pr = asyncio.run(M.price_study(st["study_id"], M.PriceIn(mercado=False), user))
    assert pr["totals"]["por_origem"]["biblioteca"] > 0
    assert asyncio.run(M.delete_study(st["study_id"], user))["ok"]


def test_projeto_lsf_direto(db):
    user = {"user_id": "u1"}
    ex = asyncio.run(M.exemplo())
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=ex, title="Exemplo"), user))
    assert st["summary"]["pecas"] == 720 and st["warnings"] == []


def test_planta_inexistente(db):
    with pytest.raises(M.HTTPException) as e:
        asyncio.run(M.create_from_plan(M.FromPlanIn(plan_id="nao-existe"), {"user_id": "u1"}))
    assert e.value.status_code == 404
