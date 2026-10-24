"""Rotas /mep (planos de execução) no .pt: criação a partir de dados, layout, SVG, PDF e preços — sem Mongo real nem IA."""
import asyncio
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_mep")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.mep")
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
        self.mep_studies, self.plans_takeoff = _Coll(), _Coll()


def test_fluxo_completo_pt(monkeypatch):
    db = _DB()
    monkeypatch.setattr(M, "db", db)
    user = {"user_id": "u1"}
    data = json.load(open(FIX))
    data["country"] = "pt"
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=data, title="Moradia exemplo"), user))
    assert st["country"] == "pt" and st["lang"] == "pt" and st["norms"].startswith("RTIEBT")
    lst = asyncio.run(M.list_studies(user))
    assert lst["studies"][0]["study_id"] == st["study_id"]
    svg = asyncio.run(M.study_svg(st["study_id"], "elec", None, user))
    assert b"<svg" in svg.body
    pdf = asyncio.run(M.study_pdf(st["study_id"], user))
    assert pdf.body[:4] == b"%PDF" and "Planos-execucao" in pdf.headers["content-disposition"]
    pts = st["points"][:-1]
    up = asyncio.run(M.update_layout(st["study_id"], M.LayoutIn(points=pts), user))
    assert up["version"] == 2
    assert asyncio.run(M.delete_study(st["study_id"], user))["ok"]


def test_planta_sem_divisoes_mensagem_pt(monkeypatch):
    db = _DB()
    db.plans_takeoff.docs.append({"plan_id": "p1", "user_id": "u1", "filename": "planta.pdf", "rooms": []})
    monkeypatch.setattr(M, "db", db)
    with pytest.raises(M.HTTPException) as e:
        asyncio.run(M.create_from_plan(M.FromPlanIn(plan_id="p1", country="pt"), {"user_id": "u1"}))
    assert e.value.status_code == 422 and "Nenhuma divisão" in e.value.detail
