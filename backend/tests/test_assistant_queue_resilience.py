"""Fila do Assistente: um tratamento parado não pode bloquear a fila para sempre."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from engines import assistant_jobs as J


@pytest.fixture
def db(monkeypatch):
    database = AsyncMongoMockClient().test_queue
    monkeypatch.setattr(J, "db", database)
    return database


def _job(i, conv="c1", seq=1, status="queued", **kw):
    now = datetime.now(timezone.utc).isoformat()
    return {"job_id": f"j{i}", "user_id": "u1", "conversation_id": conv, "request_id": f"r{i}",
            "sequence": seq, "payload": {"text": "olá", "conversation_id": conv}, "status": status,
            "created_at": now, "updated_at": now, "live": None, "error": None, "cancel_requested": False, **kw}


def test_documento_antigo_invalido_nao_para_a_fila(db):
    async def go():
        await db.assistant_convs.insert_one({"conversation_id": "c2", "user_id": "u1"})
        await db.assistant_jobs.insert_one({"job_id": "velho", "status": "queued", "created_at": "2026-01-01"})
        await db.assistant_jobs.insert_one({"job_id": "sem_worker", "status": "running", "conversation_id": "cx",
                                            "user_id": "u1", "lease_until": datetime.now(timezone.utc) - timedelta(minutes=5)})
        await db.assistant_jobs.insert_one(_job(2, conv="c2"))
        await J.claim_next("w1")
        # (mongomock devolve None em find_one_and_update+AFTER+projection; verifica-se o estado gravado)
        assert (await db.assistant_jobs.find_one({"job_id": "j2"}))["status"] == "running"
        assert (await db.assistant_jobs.find_one({"job_id": "velho"}))["status"] == "failed"
    asyncio.run(go())


def test_unstick_liberta_trabalhos_parados(db):
    async def go():
        old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
        await db.assistant_jobs.insert_one(_job(3, status="running", worker="w", updated_at=old))
        await db.assistant_jobs.insert_one(_job(4, status="running", worker="w"))
        r = await J.unstick(10)
        assert r == {"unstuck": 1}
        assert (await db.assistant_jobs.find_one({"job_id": "j3"}))["status"] == "failed"
        assert (await db.assistant_jobs.find_one({"job_id": "j4"}))["status"] == "running"
        st = await J.queue_status()
        assert st["counts"]["running"] == 1
    asyncio.run(go())


def test_tratamento_sem_eventos_termina_por_tempo(db, monkeypatch):
    import routes.assistant as RA

    async def fake_prepare(body, user, turn_seq=None):
        return [{}]

    async def fake_run_chat(body, user, stream=True, prepared=None):
        await asyncio.sleep(3600)  # LLM que nunca responde
        yield {"type": "done", "message": {}}

    monkeypatch.setattr(RA, "_prepare", fake_prepare)
    monkeypatch.setattr(RA, "_run_chat", fake_run_chat)
    monkeypatch.setattr(J, "IDLE_SECONDS", 1)
    monkeypatch.setattr(J, "bind", lambda u: None)

    async def go():
        await db.users.insert_one({"user_id": "u1", "email": "a@b.c"})
        await db.assistant_convs.insert_one({"conversation_id": "c1", "user_id": "u1"})
        await db.assistant_jobs.insert_one(_job(5))
        await db.assistant_jobs.update_one({"job_id": "j5"}, {"$set": {"status": "running", "worker": "w1"}})
        job = await db.assistant_jobs.find_one({"job_id": "j5"}, {"_id": 0})
        await asyncio.wait_for(J.run_job(job), timeout=20)
        doc = await db.assistant_jobs.find_one({"job_id": "j5"})
        assert doc["status"] == "failed" and doc["error"] == J.TIMEOUT_ERROR
    asyncio.run(go())


def test_quatro_workers():
    assert J.WORKER_COUNT >= 4
