"""Rotas /urbanismo-auto e ferramentas do Assistente BTP — coleções em memória, serviços oficiais simulados."""
import asyncio
import base64
import io
import os
import zipfile

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_urbanismo_auto")
os.environ.setdefault("JWT_SECRET", "test")

UA = pytest.importorskip("routes.urbanismo_auto")
import test_urbanismo_auto as TU  # noqa: E402
from engines.urbanismo_pt.auto import geo as G  # noqa: E402


def _get(d, path):
    for k in path.split("."):
        d = (d or {}).get(k)
    return d


class Coll:
    def __init__(self):
        self.docs = []

    def _m(self, d, q):
        for k, v in q.items():
            if isinstance(v, dict) and "$exists" in v:
                if (_get(d, k) is not None) != v["$exists"]:
                    return False
            elif _get(d, k) != v:
                return False
        return True

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def find_one(self, q, proj=None):
        d = next((x for x in self.docs if self._m(x, q)), None)
        return dict(d) if d else None

    async def replace_one(self, q, d, upsert=False):
        self.docs = [x for x in self.docs if not self._m(x, q)] + [dict(d)]

    async def update_one(self, q, upd):
        for d in self.docs:
            if self._m(d, q):
                for k, v in (upd.get("$set") or {}).items():
                    cur = d
                    parts = k.split(".")
                    for p in parts[:-1]:
                        cur = cur.setdefault(p, {})
                    cur[parts[-1]] = v
                for k, v in (upd.get("$push") or {}).items():
                    d.setdefault(k, []).append(v)
                return

    def find(self, q, proj=None):
        docs = [dict(d) for d in self.docs if self._m(d, q)]

        class Cur:
            def sort(self, *a):
                return self

            async def to_list(self, n):
                return docs[:n]
        return Cur()


class DB:
    def __init__(self):
        self.urbanismo_processos = Coll()
        self.urbanismo_auto_jobs = Coll()


@pytest.fixture()
def env(monkeypatch):
    db = DB()
    monkeypatch.setattr(UA, "db", db)
    G.set_transport(TU.fake())
    G._COLLECTIONS.update(t=0.0, list=[])
    yield db
    G.set_transport(None)


USER = {"user_id": "u1", "role": "user"}


def run(c):
    return TU._loop_run(c)


def test_fluxo_pedido_processo_materiais_zip(env):
    async def go():
        r = await UA.executar_e_gravar({"texto": "autorização de construção na rua do monte nº7 padim da graça braga"}, USER)
        assert r["ok"] and r["processo_id"] and r["coerencia"]["ok"]
        pid = r["processo_id"]
        d = await UA.obter(pid, USER)
        assert d["coerencia"]["ok"] and len(d["desenhos"]) >= 8
        assert "b64" not in (d["processo"]["auto"].get("orto") or {})
        m = await UA.get_modelo3d(pid, USER)
        assert m["volumes"] and m["vaos"] and m["terreno_grelha"]
        mm = await UA.materiais(pid, UA.MateriaisIn(fachada="xisto", cobertura="telha_preta"), USER)
        assert mm["materiais"]["fachada"] == "xisto"
        doc = await env.urbanismo_processos.find_one({"processo_id": pid})
        assert "xisto" in doc["memoria_texto"].lower()
        z = await UA.exportar(pid, USER)
        names = zipfile.ZipFile(io.BytesIO(z.body)).namelist()
        assert "06_relatorio_piloto_automatico.txt" in names and "03_memoria_descritiva.pdf" in names
        assert any(n.startswith("desenhos/planta_piso_") for n in names)
        # outro utilizador não vê
        with pytest.raises(Exception):
            await UA.obter(pid, {"user_id": "u2"})
        # respostas às perguntas → recalcula no mesmo processo
        r2 = await UA.refazer(pid, UA.PedidoIn(area_terreno_m2=950, requerente=UA.RequerenteIn(nome="Ana Silva", nif="123456789")), USER)
        assert r2["ok"] and r2["processo_id"] == pid and r2["casa"]["area_terreno_m2"] == 950
        doc = await env.urbanismo_processos.find_one({"processo_id": pid})
        assert doc["requerente"]["nome"] == "Ana Silva" and doc["auto"]["materiais"]["fachada"] == "xisto"
    run(go())


def test_ferramentas_do_assistente(env):
    from engines.assistant_autorizacao_tool import run_autorizacao_tool

    async def go():
        r = await run_autorizacao_tool("licenciamento_automatico", {"texto": "quero uma casa T2 em madeira na Rua do Monte 7, Braga"}, USER, {})
        assert r["ok"] and r["casa"]["tipologia"] == "T2" and r["casa"]["fachada"] == "madeira"
        m = await run_autorizacao_tool("licenciamento_materiais", {"processo_id": r["processo_id"], "fachada": "granito"}, USER, {})
        assert m["materiais"]["fachada"] == "granito"
        u = await run_autorizacao_tool("licenciamento_atualizar", {"processo_id": r["processo_id"], "tipologia": "T3", "requerente_nome": "Rui"}, USER, {})
        assert u["ok"] and u["casa"]["tipologia"] == "T3"
        bad = await run_autorizacao_tool("licenciamento_materiais", {"processo_id": "nao_existe", "fachada": "granito"}, USER, {})
        assert not bad["ok"]
    run(go())
