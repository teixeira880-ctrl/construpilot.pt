"""Rotas /clt no .pt: criação a partir de planta lida / dados, edição, preços, PDF, Excel, 3D — sem Mongo real nem IA."""
import asyncio
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_clt")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.clt")
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
        self.clt_studies, self.plans_takeoff, self.users, self.organizations, self.company_price_libraries = (_Coll() for _ in range(5))


@pytest.fixture()
def db(monkeypatch):
    d = _DB()
    monkeypatch.setattr(M, "db", d)

    async def _lib(uid):
        return [{"designation": "Hold-down madeira-betão (tipo WHT / HTT)", "unit": "un", "unit_price": 18.4}]
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
    assert st["study_id"].startswith("clt_") and st["summary"]["paineis"] > 50 and st["summary"]["m3_liquido"] > 40
    hd = next(l for l in st["lines"] if l["code"].startswith("CON-HOLD-DOWN-MADEIRA-BETAO"))
    assert hd["preco"]["origem"] == "biblioteca" and hd["preco"]["unit"] == 18.4
    assert asyncio.run(M.list_studies(user))["studies"][0]["study_id"] == st["study_id"]
    pdf = asyncio.run(M.study_pdf(st["study_id"], "pt", user))
    assert pdf.body[:4] == b"%PDF" and "Estudo-CLT" in pdf.headers["content-disposition"]
    xl = asyncio.run(M.study_xlsx(st["study_id"], "pt", user))
    assert xl.body[:2] == b"PK" and ".xlsx" in xl.headers["content-disposition"]
    vw = asyncio.run(M.study_viewer(st["study_id"], "pt", user))
    assert b"window.CLT=" in vw.body
    proj = st["project"]
    proj["tiposParede"]["EXT"]["painel"] = "CLT120-3s"
    up = asyncio.run(M.update_project(st["study_id"], M.ProjectIn(project=proj), user))
    assert up["version"] == 2 and up["summary"]["m3_liquido"] > st["summary"]["m3_liquido"]
    pr = asyncio.run(M.price_study(st["study_id"], M.PriceIn(mercado=False), user))
    assert pr["totals"]["por_origem"]["biblioteca"] > 0
    res = asyncio.run(M.study_result(st["study_id"], user))
    assert res["paineis"] and res["planosPrensa"]
    assert asyncio.run(M.delete_study(st["study_id"], user))["ok"]


def test_projeto_clt_direto(db):
    user = {"user_id": "u1"}
    ex = asyncio.run(M.exemplo())
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=ex, title="Exemplo"), user))
    assert st["summary"]["paineis"] == 26


def test_foto_sem_motores(db, monkeypatch):
    user = {"user_id": "u1"}
    st = asyncio.run(M.create_from_input(M.FromInputIn(input=asyncio.run(M.exemplo()), title="Exemplo"), user))
    with pytest.raises(M.HTTPException) as e:          # sem render nem motores de imagem: 503, o estudo continua utilizável
        asyncio.run(M.study_photo(st["study_id"], user))
    assert e.value.status_code == 503


def test_planta_inexistente(db):
    with pytest.raises(M.HTTPException) as e:
        asyncio.run(M.create_from_plan(M.FromPlanIn(plan_id="nao-existe"), {"user_id": "u1"}))
    assert e.value.status_code == 404
