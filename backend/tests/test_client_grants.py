"""Acessos oferecidos a clientes (core/client_grants.py) — sem rede, BD falsa."""
import asyncio
from datetime import datetime, timedelta, timezone

from core import client_grants as cg


class _Col:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd["$set"])
                return
        if upsert:
            self.docs.append(dict(upd["$set"]))


class _DB:
    def __init__(self):
        self.users, self.entitlements = _Col(), _Col()


_NOW = datetime(2026, 10, 24, 21, 0, tzinfo=timezone.utc)


def _run(db, monkeypatch, pw="Prov-teste-123"):
    if pw is None:
        monkeypatch.delenv("GRANT_RUI_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("GRANT_RUI_PASSWORD", pw)
    ids = iter(f"user_{i}" for i in range(10))
    return asyncio.run(cg.apply_client_grants(db, lambda p: "h:" + p, lambda: next(ids), now=_NOW))


def test_cria_conta_pro_business_90_dias_com_mudanca_obrigatoria(monkeypatch):
    db = _DB()
    s = _run(db, monkeypatch)
    assert s["ruifilipemaga@gmail.com"] == "created+granted"
    u = db.users.docs[0]
    assert u["email"] == "ruifilipemaga@gmail.com"
    assert u["must_change_password"] is True and u["password_hash"] == "h:Prov-teste-123"
    assert u["account_type"] == "pro_business" and u["active_plan_id"] == "pro_business_yearly"
    e = db.entitlements.docs[0]
    assert e["plan_id"] == "pro_business_yearly" and e["status"] == "active"
    assert e["expires_at"] == (_NOW + timedelta(days=90)).isoformat()


def test_idempotente_nao_reescreve_password_nem_validade(monkeypatch):
    db = _DB()
    _run(db, monkeypatch)
    db.users.docs[0]["password_hash"] = "h:nova-do-cliente"
    db.users.docs[0]["must_change_password"] = False
    exp = db.entitlements.docs[0]["expires_at"]
    s = _run(db, monkeypatch, pw="outra")
    assert s["ruifilipemaga@gmail.com"] == "exists"
    assert len(db.users.docs) == 1 and len(db.entitlements.docs) == 1
    assert db.users.docs[0]["password_hash"] == "h:nova-do-cliente"
    assert db.users.docs[0]["must_change_password"] is False
    assert db.entitlements.docs[0]["expires_at"] == exp


def test_sem_variavel_nao_cria_conta(monkeypatch):
    db = _DB()
    s = _run(db, monkeypatch, pw=None)
    assert s["ruifilipemaga@gmail.com"] == "skipped_no_password"
    assert db.users.docs == [] and db.entitlements.docs == []


def test_conta_ja_registada_recebe_so_o_acesso(monkeypatch):
    db = _DB()
    db.users.docs.append({"email": "ruifilipemaga@gmail.com", "user_id": "u_old",
                          "password_hash": "h:dele", "must_change_password": False})
    s = _run(db, monkeypatch)
    assert s["ruifilipemaga@gmail.com"] == "exists+granted"
    assert db.users.docs[0]["password_hash"] == "h:dele"
    assert db.entitlements.docs[0]["user_id"] == "u_old"


def test_sem_password_em_claro_no_modulo():
    src = open(cg.__file__, encoding="utf-8").read()
    assert "os.environ.get" in src and "GRANT_RUI_PASSWORD" in src
