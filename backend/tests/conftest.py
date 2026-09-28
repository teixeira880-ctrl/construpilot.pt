"""Configuração pytest partilhada.

O `motor.AsyncIOMotorClient` (`core.db.client`) fica preso ao 1º event loop
que o usa. `pytest-anyio` cria um loop novo por teste, o que provoca
`RuntimeError: Event loop is closed` no 2º teste async que usa DB.

Solução: reinicializar o motor client + `db` no início de cada teste async.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _reset_motor_client(monkeypatch):
    """Reinstancia o motor client para atar-se ao event loop do teste atual."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import core.db as core_db

    new_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    new_db = new_client[os.environ["DB_NAME"]]
    monkeypatch.setattr(core_db, "client", new_client)
    monkeypatch.setattr(core_db, "db", new_db)
    yield
    new_client.close()
