"""Configuração pytest partilhada.

O `motor.AsyncIOMotorClient` (`core.db.client`) fica preso ao 1º event loop
que o usa. `pytest-anyio` cria um loop novo por teste, o que provoca
`RuntimeError: Event loop is closed` no 2º teste async que usa DB.

Solução: reinicializar o motor client + `db` no início de cada teste async
e propagar a nova referência aos módulos que fazem `from core.db import db`.
"""
from __future__ import annotations

import os

import pytest


_MODULOS_COM_DB_IMPORTADO = (
    "routes.orcamento_public_link",
    "engines.btp_assistant.tools.executors",
    "engines.emailer",
    "engines.alerting",
    "engines.mail_sender_config",
)


@pytest.fixture(autouse=True)
def _reset_motor_client():
    """Reinstancia o motor client para atar-se ao event loop do teste atual.

    IMPORTANTE: usamos `setattr` directo (não `monkeypatch`) para que a
    nova referência persista entre testes — se usássemos monkeypatch, o
    rollback faria voltar ao motor atado ao loop fechado.
    """
    from motor.motor_asyncio import AsyncIOMotorClient
    import core.db as core_db

    new_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    new_db = new_client[os.environ["DB_NAME"]]
    core_db.client = new_client
    core_db.db = new_db
    # Propaga a nova referência aos módulos que importam `db` por valor
    for mod_path in _MODULOS_COM_DB_IMPORTADO:
        try:
            mod = __import__(mod_path, fromlist=["db"])
            setattr(mod, "db", new_db)
        except Exception:
            pass
    yield
