"""Fluxo de obra entre apps: percurso de um processo (registo, deduplicação, isolamento, dossier)."""
import copy
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import fluxo_obra as F


def _match(row, q):
    return all(row.get(k) == v for k, v in q.items())


class _Cur:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, key, direction=1):
        self.rows.sort(key=lambda r: r.get(key) or "", reverse=direction < 0)
        return self

    async def to_list(self, n):
        return copy.deepcopy(self.rows[:n])


class _Col:
    def __init__(self):
        self.rows = []

    def _proj(self, row, proj):
        row = copy.deepcopy(row)
        for k, v in (proj or {}).items():
            if v == 0:
                row.pop(k, None)
        return row

    def find(self, q, proj=None):
        return _Cur([self._proj(r, proj) for r in self.rows if _match(r, q)])

    async def find_one(self, q, proj=None):
        r = next((r for r in self.rows if _match(r, q)), None)
        return self._proj(r, proj) if r else None

    async def count_documents(self, q):
        return sum(_match(r, q) for r in self.rows)

    async def update_one(self, q, upd, upsert=False):
        row = next((r for r in self.rows if _match(r, q)), None)
        created = row is None and upsert
        if created:
            row = dict(q)
            self.rows.append(row)
            row.update(copy.deepcopy(upd.get("$setOnInsert", {})))
        if row is not None:
            row.update(copy.deepcopy(upd.get("$set", {})))
            for k, v in upd.get("$inc", {}).items():
                row[k] = row.get(k, 0) + v
        return SimpleNamespace(matched_count=int(row is not None and not created))

    async def delete_one(self, q):
        before = len(self.rows)
        self.rows = [r for r in self.rows if not _match(r, q)]
        return SimpleNamespace(deleted_count=before - len(self.rows))


class _Db:
    def __getattr__(self, key):
        col = _Col()
        setattr(self, key, col)
        return col


A = {"user_id": "a"}
B = {"user_id": "b"}


@pytest.fixture
def db(monkeypatch):
    d = _Db()
    d.chantiers.rows = [{"chantier_id": "c1", "user_id": "a", "name": "Moradia 200 m²"},
                        {"chantier_id": "c2", "user_id": "b", "name": "Outro"}]
    monkeypatch.setattr(F, "db", d)
    return d


@pytest.mark.asyncio
async def test_registar_e_reabrir_o_mesmo_trabalho_da_um_so_passo(db):
    body = F.PassoIn(rota="/atelier-arquiteto", params={"projet": "arch_516faad6faec", "chantier": "c1", "tab": "x"}, app="Ateliê Arquiteto")
    p1 = await F.registar_passo("c1", body, user=A)
    p2 = await F.registar_passo("c1", body, user=A)
    assert p1["passo_id"] == p2["passo_id"]
    assert p2["aberturas"] == 2
    assert p2["params"] == {"projet": "arch_516faad6faec"}  # chantier/tab não identificam o trabalho
    assert p2["url"] == "/atelier-arquiteto?chantier=c1&projet=arch_516faad6faec"
    lista = await F.listar_percurso("c1", user=A)
    assert len(lista["passos"]) == 1 and lista["nome"] == "Moradia 200 m²"


@pytest.mark.asyncio
async def test_trabalhos_diferentes_em_apps_diferentes(db):
    await F.registar_passo("c1", F.PassoIn(rota="/atelier-arquiteto", params={"projet": "arch_1"}), user=A)
    await F.registar_passo("c1", F.PassoIn(rota="/bim", params={"model": "m1"}), user=A)
    await F.registar_passo("c1", F.PassoIn(rota="/devis-editeur/doc_9"), user=A)
    lista = await F.listar_percurso("c1", user=A)
    assert {p["rota"] for p in lista["passos"]} == {"/atelier-arquiteto", "/bim", "/devis-editeur/doc_9"}
    resumo = await F.percurso_resumido("c1", "a")
    assert len(resumo) == 3 and all("url" in p for p in resumo)


@pytest.mark.asyncio
async def test_isolamento_entre_contas(db):
    with pytest.raises(HTTPException) as e:
        await F.registar_passo("c2", F.PassoIn(rota="/bim"), user=A)
    assert e.value.status_code == 404
    with pytest.raises(HTTPException):
        await F.listar_percurso("c1", user=B)
    p = await F.registar_passo("c1", F.PassoIn(rota="/bim"), user=A)
    with pytest.raises(HTTPException):
        await F.remover_passo("c1", p["passo_id"], user=B)
    assert (await F.remover_passo("c1", p["passo_id"], user=A))["ok"]


@pytest.mark.parametrize("rota", ["https://evil.com/x", "//evil.com", "/a/../admin", "javascript:alert(1)", "/a b"])
def test_rotas_externas_ou_invalidas_sao_recusadas(rota):
    with pytest.raises(ValidationError):
        F.PassoIn(rota=rota)


def test_rota_normalizada_sem_query():
    assert F.PassoIn(rota="/plan/?x=1#y").rota == "/plan"


@pytest.mark.asyncio
async def test_percurso_resumido_nunca_rebenta():
    class Mau:
        def __getattr__(self, k):
            raise RuntimeError("db em baixo")
    assert await F.percurso_resumido("c1", "a", database=Mau()) == []
