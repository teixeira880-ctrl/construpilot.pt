"""Testes da auditoria `admin_actions` — role_change em `PUT /api/admin/users/{id}`.

Valida:
- Admin pode promover utilizador a admin.
- Promoção regista uma linha em `db.admin_actions` com actor/target/timestamp/role.
- Idempotente: se já é admin e role continua "admin", NÃO regista nova linha.
- `GET /api/admin/admin-actions` devolve lista ordenada por timestamp desc.
- Não-admin recebe 401/403 (via `admin_user` dependency, não testamos aqui — já
  coberto pelo middleware; esta suite foca-se na auditoria quando o admin age).
"""
import asyncio
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "/app/backend")


class _Coll:
    def __init__(self):
        self.docs = []

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, q, upd):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(upd.get("$set") or {})
                return

    def find(self, q, proj=None):
        matched = [dict(d) for d in self.docs if all(d.get(k) == v for k, v in q.items())]
        return _Cur(matched, proj)


class _Cur:
    def __init__(self, docs, proj=None):
        self.docs = docs
        self._sort = None
        self._limit = None

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key, ""), reverse=(direction == -1))
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, n):
        out = self.docs
        if self._limit:
            out = out[:self._limit]
        return out[:n]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if sys.version_info < (3, 10) else asyncio.run(coro)


class _FakeRequest:
    def __init__(self, ip="1.2.3.4"):
        self.headers = {"x-forwarded-for": ip}
        class _C:  # noqa: E701
            host = ip
        self.client = _C()


@pytest.fixture
def db_mock(monkeypatch):
    class _DB:
        users = _Coll()
        admin_actions = _Coll()
    _db = _DB()
    import routes.admin as admin_mod
    monkeypatch.setattr(admin_mod, "db", _db)
    return _db


def test_promote_to_admin_logs_action(db_mock):
    """Promoção regista linha em `admin_actions` com role_change."""
    from routes.admin import UserIn, update_user

    _run(db_mock.users.insert_one({"user_id": "u-target", "role": "user", "email": "x@y"}))
    actor = {"user_id": "u-admin", "role": "admin"}

    result = _run(update_user("u-target", UserIn(role="admin"), _FakeRequest("10.0.0.1"), actor))
    assert result["role"] == "admin"

    assert len(db_mock.admin_actions.docs) == 1
    log = db_mock.admin_actions.docs[0]
    assert log["actor_user_id"] == "u-admin"
    assert log["target_user_id"] == "u-target"
    assert log["action"] == "role_change:user->admin"
    assert log["before"] == {"role": "user"}
    assert log["after"] == {"role": "admin"}
    assert log["ip_address"] == "10.0.0.1"
    assert log["action_id"].startswith("act_")
    # timestamp em ISO
    datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))


def test_promote_idempotent_no_duplicate_log(db_mock):
    """Se o role actual == role pedido, NÃO regista nova linha."""
    from routes.admin import UserIn, update_user

    _run(db_mock.users.insert_one({"user_id": "u-already-admin", "role": "admin", "email": "a@b"}))
    actor = {"user_id": "u-admin", "role": "admin"}

    _run(update_user("u-already-admin", UserIn(role="admin"), _FakeRequest(), actor))
    assert len(db_mock.admin_actions.docs) == 0


def test_other_field_change_does_not_log(db_mock):
    """Mudança de `account_type` ou `plan` não gera entrada admin_actions."""
    from routes.admin import UserIn, update_user

    _run(db_mock.users.insert_one({"user_id": "u-x", "role": "user",
                                   "account_type": "particulier", "email": "x@y"}))
    actor = {"user_id": "u-admin", "role": "admin"}
    _run(update_user("u-x", UserIn(account_type="pro"), _FakeRequest(), actor))
    assert len(db_mock.admin_actions.docs) == 0


def test_demote_admin_also_logs(db_mock):
    """Despromoção (admin→user) também é registada."""
    from routes.admin import UserIn, update_user

    _run(db_mock.users.insert_one({"user_id": "u-ex-admin", "role": "admin", "email": "e@f"}))
    actor = {"user_id": "u-admin", "role": "admin"}
    _run(update_user("u-ex-admin", UserIn(role="user"), _FakeRequest(), actor))
    assert len(db_mock.admin_actions.docs) == 1
    assert db_mock.admin_actions.docs[0]["action"] == "role_change:admin->user"


def test_404_when_target_user_absent(db_mock):
    """Target inexistente → 404, zero log."""
    from fastapi import HTTPException

    from routes.admin import UserIn, update_user

    actor = {"user_id": "u-admin", "role": "admin"}
    with pytest.raises(HTTPException) as exc:
        _run(update_user("ghost", UserIn(role="admin"), _FakeRequest(), actor))
    assert exc.value.status_code == 404
    assert len(db_mock.admin_actions.docs) == 0


def test_list_admin_actions_ordered_desc(db_mock):
    """`GET /admin-actions` devolve por timestamp decrescente."""
    from routes.admin import list_admin_actions

    base = "2026-10-19T"
    _run(db_mock.admin_actions.insert_one({"action_id": "act_1", "timestamp": base + "10:00:00+00:00",
                                            "actor_user_id": "u", "target_user_id": "a",
                                            "action": "role_change:user->admin"}))
    _run(db_mock.admin_actions.insert_one({"action_id": "act_2", "timestamp": base + "12:00:00+00:00",
                                            "actor_user_id": "u", "target_user_id": "b",
                                            "action": "role_change:user->admin"}))
    _run(db_mock.admin_actions.insert_one({"action_id": "act_3", "timestamp": base + "11:00:00+00:00",
                                            "actor_user_id": "u", "target_user_id": "c",
                                            "action": "role_change:user->admin"}))
    out = _run(list_admin_actions(limit=50))
    assert [x["action_id"] for x in out] == ["act_2", "act_3", "act_1"]
