"""Botão «Criar conta» do admin (core/admin_create_account.py) — sem rede, BD falsa."""
import asyncio

import pytest

from core.admin_create_account import create_account, AccountCreateError


class _Col:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))


class _DB:
    def __init__(self):
        self.users = _Col()


def _create(db, **kw):
    data = {"email": "Cliente@Empresa.PT", "temp_password": "ContaProv2026",
            "company_name": "Empresa Teste Lda"}
    data.update(kw)
    return asyncio.run(create_account(db, data, hash_password=lambda p: "h:" + p,
                                      new_user_id=lambda: "user_x", admin_id="admin_1"))


def test_cria_conta_pro_business_com_mudanca_obrigatoria():
    db = _DB()
    u = _create(db)
    stored = db.users.docs[0]
    assert stored["email"] == "cliente@empresa.pt"
    assert stored["password_hash"] == "h:ContaProv2026"
    assert stored["must_change_password"] is True
    assert stored["account_type"] == "pro_business" and stored["plan"] == "pro"
    assert stored["email_verified"] is True and stored["role"] == "user"
    assert stored["phone"] is None  # telefone pedido no primeiro início de sessão
    assert stored["name"] == "Empresa Teste Lda"
    assert "password_hash" not in u and "temp_password" not in stored


def test_email_duplicado_recusado_sem_alterar_a_conta():
    db = _DB()
    _create(db)
    with pytest.raises(AccountCreateError):
        _create(db, temp_password="OutraPalavra99")
    assert len(db.users.docs) == 1
    assert db.users.docs[0]["password_hash"] == "h:ContaProv2026"


@pytest.mark.parametrize("kw", [
    {"email": "sem-arroba"},
    {"temp_password": "curta"},
    {"account_type": "admin"},
    {"plan": "gold"},
])
def test_validacoes(kw):
    with pytest.raises(AccountCreateError):
        _create(_DB(), **kw)


def test_nunca_cria_admin():
    db = _DB()
    _create(db, role="admin")
    assert db.users.docs[0]["role"] == "user"
