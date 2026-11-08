"""Edifício 3D — rotas + execução REAL do Blender (bpy) de ponta a ponta, Mongo/GridFS em memória."""
import asyncio
import importlib.util
import os
import struct

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_edificio3d")
os.environ.setdefault("JWT_SECRET", "test")
os.environ["EDIFICIO3D_WORKER_TOKEN"] = "tok-test"

httpx = pytest.importorskip("httpx")
from fastapi import FastAPI  # noqa: E402

from core import security  # noqa: E402
from engines.edificio3d import servico as S  # noqa: E402
from routes import edificio3d as R  # noqa: E402


def _get(d, path):
    for k in path.split("."):
        d = (d or {}).get(k) if isinstance(d, dict) else None
    return d


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, k, o):
        self.docs.sort(key=lambda d: d.get(k) or "", reverse=o < 0)
        return self

    async def to_list(self, n):
        return [dict(d) for d in self.docs[:n]]


class Coll:
    def __init__(self):
        self.docs = []

    def _m(self, d, q):
        for k, v in q.items():
            x = _get(d, k)
            if isinstance(v, dict):
                if "$ne" in v and x == v["$ne"]:
                    return False
                if "$gte" in v and not (x is not None and x >= v["$gte"]):
                    return False
            elif x != v:
                return False
        return True

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def find_one(self, q, proj=None):
        d = next((x for x in self.docs if self._m(x, q)), None)
        return dict(d) if d else None

    def _apply(self, d, upd):
        for k, v in upd.get("$set", {}).items():
            d[k] = v
        for k, v in upd.get("$push", {}).items():
            d.setdefault(k, []).append(v)
        for k, v in upd.get("$addToSet", {}).items():
            if v not in d.setdefault(k, []):
                d[k].append(v)

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if self._m(d, q):
                self._apply(d, upd)
                return
        if upsert:
            d = dict(q)
            self._apply(d, upd)
            self.docs.append(d)

    async def find_one_and_update(self, q, upd, sort=None, projection=None):
        for d in self.docs:
            if self._m(d, q):
                self._apply(d, upd)
                return {k: v for k, v in d.items() if k != "user_id"}
        return None

    def find(self, q, proj=None):
        return Cursor([d for d in self.docs if self._m(d, q)])


class DB(dict):
    def __getitem__(self, k):
        return self.setdefault(k, Coll())

    def __getattr__(self, k):
        return self[k]


class Bucket:
    files = {}

    class _F:
        def __init__(self, n):
            self._id = n

    def find(self, q):
        n = q["filename"]

        async def gen():
            if n in Bucket.files:
                yield Bucket._F(n)
        return gen()

    async def delete(self, i):
        Bucket.files.pop(i, None)

    async def upload_from_stream(self, n, data, metadata=None):
        Bucket.files[n] = bytes(data)

    async def open_download_stream_by_name(self, n):
        if n not in Bucket.files:
            raise FileNotFoundError(n)
        d = Bucket.files[n]

        class St:
            async def read(self):
                return d
        return St()


@pytest.fixture()
def app(monkeypatch):
    fake = DB()
    Bucket.files = {}
    monkeypatch.setattr(S, "db", fake)
    monkeypatch.setattr(R, "db", fake)
    monkeypatch.setattr(S, "bucket", lambda: Bucket())
    from engines.urbanismo_pt.auto import geo as G

    async def geocode(m):
        return {"ok": True, "data": {"lat": 38.7369, "lon": -9.1427}, "fonte": "teste"}

    async def elev(pts):
        return {"ok": True, "data": {"z": [92.4]}, "fonte": "teste-dem"}

    async def orto(lat, lon, meia_largura_m=60.0, px=1024):
        return {"ok": False}
    monkeypatch.setattr(G, "geocode", geocode)
    monkeypatch.setattr(G, "elevacoes", elev)
    monkeypatch.setattr(G, "ortofoto", orto)
    a = FastAPI()
    a.include_router(R.router)
    a.dependency_overrides[security.current_user] = lambda: {"user_id": "u1", "role": "user"}
    return a, fake


def _client(a):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=a), base_url="http://t")


async def _espera(c, jid, fim=("concluido", "erro", "em_fila"), t=600):
    for _ in range(t * 2):
        j = (await c.get(f"/edificio3d/projetos/{jid}")).json()
        if j["estado"] in fim:
            return j
        await asyncio.sleep(0.5)
    raise AssertionError("timeout")


def test_validacao_e_worker(app, monkeypatch):
    a, fake = app
    monkeypatch.setattr(S, "blender_no_servidor", lambda: None)   # sem Blender no servidor → vai para o posto

    async def run():
        async with _client(a) as c:
            assert (await c.post("/edificio3d/projetos", json={"nome": "x"})).status_code == 422
            r = await c.post("/edificio3d/projetos", json={"morada": "Av. da República, Lisboa", "usar_arcgis": True})
            jid = r.json()["job_id"]
            j = await _espera(c, jid)
            assert j["estado"] == "em_fila" and j["modo"] == "worker"
            assert j["params"]["latitude"] == 38.7369 and j["params"]["altitude_m"] == 92.4
            # posto sem token → 401
            assert (await c.post("/edificio3d/worker/proximo", json={})).status_code == 401
            h = {"X-Worker-Token": "tok-test"}
            # posto só com Blender não pode apanhar trabalho que pede ArcGIS
            r = await c.post("/edificio3d/worker/proximo", json={"nome": "pc1", "arcgis": False}, headers=h)
            assert r.json()["trabalho"] is None
            r = await c.post("/edificio3d/worker/proximo", json={"nome": "pc1", "arcgis": True}, headers=h)
            assert r.json()["trabalho"]["job_id"] == jid
            assert (await c.post(f"/edificio3d/worker/{jid}/ficheiros/edificio.glb", content=b"glTF....", headers=h)).json()["ok"]
            assert (await c.post(f"/edificio3d/worker/{jid}/ficheiros/../x", content=b"1", headers=h)).status_code != 200
            r = await c.post(f"/edificio3d/worker/{jid}/concluir", headers=h,
                             json={"ok": True, "manifesto": {"glb": "edificio.glb"}, "arcgis": {"ok": True}})
            j = (await c.get(f"/edificio3d/projetos/{jid}")).json()
            assert j["estado"] == "concluido" and "edificio.glb" in j["ficheiros"] and j["arcgis"]["ok"]
            g = await c.get(f"/edificio3d/projetos/{jid}/ficheiros/edificio.glb")
            assert g.status_code == 200 and g.headers["content-type"] == "model/gltf-binary"
            s = (await c.get("/edificio3d/sistema")).json()
            assert s["arcgis_disponivel"] is True and s["postos"][0]["nome"] == "pc1"
    asyncio.run(run())


@pytest.mark.skipif(importlib.util.find_spec("bpy") is None, reason="Blender (bpy) não instalado")
def test_blender_real_no_servidor(app, monkeypatch):
    a, fake = app
    monkeypatch.setitem(R.QUAL, "rapida", {"largura_px": 320, "altura_px": 214, "amostras": 4,
                                           "vistas": ["perspetiva", "antes_perspetiva"]})

    async def run():
        async with _client(a) as c:
            r = await c.post("/edificio3d/projetos", json={"latitude": 41.15, "longitude": -8.61, "azimute_fachada_graus": 135,
                                                           "qualidade": "rapida"})
            jid = r.json()["job_id"]
            j = await _espera(c, jid, fim=("concluido", "erro"))
            assert j["estado"] == "concluido", j.get("erro")
            m = j["manifesto"]
            assert m["geometria"]["vertices"] > 2000 and m["geometria"]["objetos"] >= 8
            assert m["dimensoes"]["largura_m"] == 12 and m["dimensoes"]["pisos"] == 2
            assert abs(m["dimensoes"]["altura_cumeeira_m"] - (6 + 4.5 * 0.57735)) < 0.05
            glb = (await c.get(f"/edificio3d/projetos/{jid}/ficheiros/edificio.glb")).content
            assert glb[:4] == b"glTF" and struct.unpack("<I", glb[8:12])[0] == len(glb)
            img = (await c.get(f"/edificio3d/projetos/{jid}/ficheiros/perspetiva.jpg")).content
            assert img[:2] == b"\xff\xd8"
            assert "antes_perspetiva.jpg" in j["ficheiros"]
    asyncio.run(run())
