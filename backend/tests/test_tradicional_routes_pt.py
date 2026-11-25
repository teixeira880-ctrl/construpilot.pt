"""Rotas /tradicional no .pt: criação a partir de planta lida / dados, edição, preços, PDF, Excel, 3D — sem Mongo real nem IA."""
import asyncio
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_trad")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.tradicional")
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
        self.trad_studies, self.plans_takeoff, self.users, self.organizations, self.company_price_libraries = (_Coll() for _ in range(5))


@pytest.fixture()
def db(monkeypatch):
    d = _DB()
    monkeypatch.setattr(M, "db", d)

    async def _lib(uid):
        return [{"designation": "Tijolo cerâmico furado 30×20×22 cm", "unit": "un", "unit_price": 0.62}]
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
    assert st["study_id"].startswith("trd_") and st["summary"]["m3_betao"] > 30 and st["summary"]["unidades_alvenaria"] > 1000
    tij = [l for l in st["lines"] if l["designacao"] == "Tijolo cerâmico furado 30×20×22 cm"]
    assert tij and all(l["preco"]["origem"] == "biblioteca" for l in tij)
    pdf = asyncio.run(M.study_pdf(st["study_id"], "pt", user))
    assert pdf.body[:4] == b"%PDF" and "Construcao-tradicional" in pdf.headers["content-disposition"]
    assert asyncio.run(M.study_xlsx(st["study_id"], "pt", user)).body[:2] == b"PK"
    assert b"window.CLT=" in asyncio.run(M.study_viewer(st["study_id"], "pt", user)).body
    proj = st["project"]
    proj["regras"]["q_adm_kpa"] = 100
    up = asyncio.run(M.update_project(st["study_id"], M.ProjectIn(project=proj), user))
    assert up["version"] == 2 and up["summary"]["m3_betao"] > st["summary"]["m3_betao"]       # sapatas maiores
    assert asyncio.run(M.study_result(st["study_id"], user))["pilares"]
    assert asyncio.run(M.delete_study(st["study_id"], user))["ok"]


def test_exemplo(db):
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=asyncio.run(M.exemplo()), title="Exemplo"), {"user_id": "u1"}))
    assert st["summary"]["pilares"] == 10


def test_planta_inexistente(db):
    with pytest.raises(M.HTTPException) as e:
        asyncio.run(M.create_from_plan(M.FromPlanIn(plan_id="nao-existe"), {"user_id": "u1"}))
    assert e.value.status_code == 404
