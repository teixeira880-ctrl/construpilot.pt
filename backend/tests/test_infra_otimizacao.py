"""Testes das otimizações de infraestrutura (sem servidor nem MongoDB)."""
import asyncio
import importlib
import threading
import time

import pytest


# ── Armazenamento S3/R2 ────────────────────────────────────────────────────────
@pytest.fixture
def s3_env(monkeypatch):
    moto = pytest.importorskip("moto")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET", "cp-test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "x")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    with moto.mock_aws():
        import boto3
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="cp-test")
        from engines import object_storage
        importlib.reload(object_storage)
        yield object_storage
    importlib.reload(object_storage)


def test_s3_put_get_mesma_api(s3_env):
    obj = s3_env
    res = obj.put_object("construpilot/site/u1/a.pdf", b"%PDF-1.7 teste", "application/pdf")
    assert res["path"] == "construpilot/site/u1/a.pdf" and res["size"] == 14
    data, ct = obj.get_object("construpilot/site/u1/a.pdf")
    assert data == b"%PDF-1.7 teste" and ct == "application/pdf"
    assert obj.s3_exists("construpilot/site/u1/a.pdf") and not obj.s3_exists("nao/existe")


def test_storage_wrapper_delega_para_s3(s3_env):
    from engines import storage
    storage.put_object("construpilot/photos/x.jpg", b"jpg", "image/jpeg")
    assert storage.get_object("construpilot/photos/x.jpg") == (b"jpg", "image/jpeg")


def test_modo_misto_le_na_emergent_quando_falta_no_s3(s3_env, monkeypatch):
    obj = s3_env
    monkeypatch.setattr(obj, "BACKEND", "s3+emergent")
    monkeypatch.setattr(obj, "emergent_get", lambda p: (b"antigo", "image/png"))
    assert obj.get_object("construpilot/ainda/na-emergent.png") == (b"antigo", "image/png")
    obj.put_object("construpilot/novo.png", b"novo", "image/png")
    assert obj.get_object("construpilot/novo.png") == (b"novo", "image/png")


def test_backend_por_defeito_continua_emergent(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    from engines import object_storage
    importlib.reload(object_storage)
    assert object_storage.BACKEND == "emergent"


# ── Espera dos workers ─────────────────────────────────────────────────────────
def test_idle_wait_recuo_e_despertar():
    from core import job_wake

    async def run():
        d = await job_wake.idle_wait("t1", None)          # sem trabalho: 1 s → 2 s
        assert d == 2.0
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, job_wake.wake, "t1")
        t0 = time.monotonic()
        d = await job_wake.idle_wait("t1", 8.0)           # acordado logo, intervalo volta a 1 s
        assert time.monotonic() - t0 < 1.0 and d == job_wake.IDLE_MIN_S
        assert job_wake.IDLE_MAX_S >= job_wake.IDLE_MIN_S

    asyncio.run(run())


# ── Limite de renders ──────────────────────────────────────────────────────────
def test_render_slot_um_de_cada_vez():
    from core import heavy_limit
    ativos, maximo, lock = [0], [0], threading.Lock()

    def trabalho():
        with heavy_limit.render_slot():
            with lock:
                ativos[0] += 1
                maximo[0] = max(maximo[0], ativos[0])
            time.sleep(0.05)
            with lock:
                ativos[0] -= 1

    ts = [threading.Thread(target=trabalho) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert maximo[0] == heavy_limit.RENDER_CONCURRENCY == 1


def test_render_threads(monkeypatch):
    from core import heavy_limit
    monkeypatch.setenv("BLENDER_THREADS", "3")
    assert heavy_limit.render_threads() == 3
    monkeypatch.delenv("BLENDER_THREADS")
    monkeypatch.delenv("RENDER_THREADS", raising=False)
    assert heavy_limit.render_threads() >= 1


def test_scheduler_desligavel(monkeypatch):
    from core import scheduler_lock
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    assert scheduler_lock.enabled() is False
    assert scheduler_lock.start(object()) is None
    monkeypatch.delenv("SCHEDULER_ENABLED")
    assert scheduler_lock.enabled() is True
