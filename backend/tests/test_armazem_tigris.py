"""Ficheiros pesados no Tigris : envio verificado, leitura transparente, nada muda sem configuração."""
import asyncio
import base64

from core import armazem as A
from core import armazem_offload as O


class _Res:
    def __init__(self, n): self.modified_count = n


class _Cur:
    def __init__(self, rows): self.rows = rows
    def sort(self, *a, **k): return self
    def limit(self, n): self.rows = self.rows[:n]; return self
    def __aiter__(self):
        self._i = iter(self.rows); return self
    async def __anext__(self):
        try: return dict(next(self._i))
        except StopIteration: raise StopAsyncIteration
    async def to_list(self, n=None): return [dict(r) for r in self.rows]


def _proj(d, p):
    if not p:
        return dict(d)
    incl = [k for k, v in p.items() if k != "_id" and v]
    if incl:
        return {k: d[k] for k in incl if k in d}
    return {k: v for k, v in d.items() if p.get(k, 1) != 0}


class _Col:
    def __init__(self, rows): self.rows = rows
    async def find_one(self, q, projection=None):
        for r in self.rows:
            if all(r.get(k) == v for k, v in q.items() if not isinstance(v, dict)):
                return _proj(r, projection)
    def find(self, q, projection=None):
        out = []
        for r in self.rows:
            ok = all(r.get(k) == v for k, v in q.items() if not isinstance(v, dict) and k != "$or")
            if "tigris_key" in q and "tigris_key" in r:
                ok = False
            if ok:
                out.append(_proj(r, projection))
        return _Cur(out)
    async def update_one(self, q, u):
        for r in self.rows:
            if r.get("doc_id", r.get("artifact_id")) == q.get("doc_id", q.get("artifact_id")) and "tigris_key" not in r:
                r.update(u["$set"]); [r.pop(k, None) for k in u.get("$unset", {})]
                return _Res(1)
        return _Res(0)
    async def delete_many(self, q): return None


class _DB(dict):
    def __getattr__(self, n): return self[n]


BIG = b"%PDF" + b"x" * 200_000


def test_sem_tigris_nada_muda(monkeypatch):
    for k in ("TIGRIS_BUCKET", "TIGRIS_ACCESS_KEY_ID", "TIGRIS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert not A.configurado()
    assert asyncio.run(O.descarregar(_DB())) == {"enviados": 0, "motivo": "Tigris não configurado"}


def test_envio_verificado_e_leitura_transparente(monkeypatch):
    monkeypatch.setenv("TIGRIS_BUCKET", "b"); monkeypatch.setenv("TIGRIS_ACCESS_KEY_ID", "k"); monkeypatch.setenv("TIGRIS_SECRET_ACCESS_KEY", "s")
    loja = {}
    monkeypatch.setattr(A, "enviar", lambda k, data, sha: (loja.__setitem__(k, data), len(data))[1])
    monkeypatch.setattr(A, "ler", lambda k: loja[k])
    docs = _Col([{"doc_id": "doc_1", "user_id": "u", "created_at": "2020-01-01T00:00:00+00:00", "data_b64": base64.b64encode(BIG).decode()},
                 {"doc_id": "doc_2", "user_id": "u", "created_at": "2020-01-01T00:00:00+00:00", "data_b64": base64.b64encode(b"pequeno").decode()}])
    arts = _Col([])
    db = _DB(assistant_docs=docs, assistant_artifacts=arts, assistant_doc_chunks=_Col([]))
    r = asyncio.run(O.descarregar(db))
    assert r["enviados"] == 1 and r["ignorados"] == 1
    assert "data_b64" not in docs.rows[0] and docs.rows[0]["tigris_key"].endswith("/assistant_docs/u/doc_1")
    assert "data_b64" in docs.rows[1]                                         # pequeno : fica na base
    W = A.BaseDados(_DB(assistant_docs=docs, assistant_artifacts=arts))
    d = asyncio.run(W.assistant_docs.find_one({"doc_id": "doc_1", "user_id": "u"}, {"_id": 0}))
    assert base64.b64decode(d["data_b64"]) == BIG and d["chunk_count"] == 0
    d = asyncio.run(W.assistant_docs.find_one({"doc_id": "doc_1"}, {"_id": 0, "filename": 1, "data_b64": 1}))
    assert base64.b64decode(d["data_b64"]) == BIG and "tigris_key" not in d     # chave técnica não vaza
    d = asyncio.run(W.assistant_docs.find_one({"doc_id": "doc_1"}, {"_id": 0, "data_b64": 0}))
    assert "data_b64" not in d                                                # listagens sem bytes : nenhum pedido ao Tigris

    async def todos():
        return [x async for x in W.assistant_docs.find({"user_id": "u"}, {"_id": 0}).sort("created_at", -1).limit(10)]
    rows = asyncio.run(todos())
    assert base64.b64decode(rows[0]["data_b64"]) == BIG


def test_tamanho_errado_nao_apaga(monkeypatch):
    monkeypatch.setenv("TIGRIS_BUCKET", "b"); monkeypatch.setenv("TIGRIS_ACCESS_KEY_ID", "k"); monkeypatch.setenv("TIGRIS_SECRET_ACCESS_KEY", "s")
    monkeypatch.setattr(A, "enviar", lambda k, data, sha: len(data) - 1)
    docs = _Col([{"doc_id": "doc_1", "user_id": "u", "created_at": "2020-01-01T00:00:00+00:00", "data_b64": base64.b64encode(BIG).decode()}])
    r = asyncio.run(O.descarregar(_DB(assistant_docs=docs, assistant_artifacts=_Col([]), assistant_doc_chunks=_Col([]))))
    assert r["falhas"] == 1 and "data_b64" in docs.rows[0] and "tigris_key" not in docs.rows[0]
