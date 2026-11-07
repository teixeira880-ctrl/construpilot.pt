"""Fila de processamento BIM (MongoDB + processos isolados).

* Uma versão de modelo = um trabalho (``bim_versions``); o estado vive na base de dados,
  portanto sobrevive a reinícios e funciona com vários processos uvicorn (reserva atómica).
* Cada trabalho corre num subprocesso ``python -I worker_main.py`` com limites de memória,
  CPU, tamanho de saída e tempo total — o servidor principal nunca bloqueia.
* Progresso, cancelamento, recuperação de trabalhos órfãos e métricas de duração.
"""
from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from bim_studio import config, storage
from bim_studio.store import get_db

log = logging.getLogger("bim_studio.jobs")

WORKER_ID = f"{os.getpid()}-{uuid.uuid4().hex[:6]}"
_RUNNING: dict[str, asyncio.subprocess.Process] = {}
_WAKE = asyncio.Event()
_TASKS: list[asyncio.Task] = []
_WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worker_main.py")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def job_key(model_id: str, version: int) -> str:
    return f"{model_id}:v{version}"


def wake() -> None:
    try:
        _WAKE.set()
    except RuntimeError:  # pragma: no cover
        pass


async def _claim():
    db = get_db()
    from pymongo import ReturnDocument
    doc = await db.bim_versions.find_one_and_update(
        {"status": "queued", "cancel_requested": {"$ne": True}},
        {"$set": {"status": "processing", "worker_id": WORKER_ID, "started_at": _now().isoformat(),
                  "progress": 0.01, "stage": "a iniciar"}, "$inc": {"attempts": 1}},
        sort=[("created_at", 1)], return_document=ReturnDocument.AFTER)
    if doc:
        doc.pop("_id", None)
    return doc


async def _set(model_id: str, version: int, **fields) -> None:
    await get_db().bim_versions.update_one({"model_id": model_id, "version": version}, {"$set": fields})


async def run_job(v: dict) -> None:
    """Executa um trabalho já reservado (usado pelo loop e diretamente nos testes)."""
    db = get_db()
    model_id, version, tenant = v["model_id"], v["version"], v["tenant_id"]
    work = os.path.join(config.WORK_DIR, f"{model_id}_v{version}_{uuid.uuid4().hex[:6]}")
    out_dir = os.path.join(work, "out")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.monotonic()
    key = job_key(model_id, version)
    try:
        data = await storage.get(v["storage_key"])
        ifc_path = os.path.join(work, "model.ifc")
        with open(ifc_path, "wb") as fh:
            fh.write(data)
        del data
        limits = json.dumps({
            "memory_mb": config.WORKER_MEMORY_MB, "cpu_seconds": config.WORKER_CPU_S,
            "output_mb": config.WORKER_OUTPUT_MB, "max_elements": config.MAX_ELEMENTS,
            "max_triangles": config.MAX_TRIANGLES, "threads": config.WORKER_THREADS})
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "OMP_NUM_THREADS": "1",
               "HOME": work, "TMPDIR": work}
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-I", _WORKER, ifc_path, out_dir, limits,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=work, env=env)
        _RUNNING[key] = proc
        final: dict | None = None
        last_write = 0.0

        async def _read():
            nonlocal final, last_write
            assert proc.stdout is not None
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if "progress" in msg and time.monotonic() - last_write > 1.0:
                    last_write = time.monotonic()
                    await _set(model_id, version, progress=min(0.95, float(msg["progress"]) * 0.9),
                               stage=str(msg.get("stage", ""))[:120])
                    cur = await db.bim_versions.find_one({"model_id": model_id, "version": version},
                                                         {"_id": 0, "cancel_requested": 1})
                    if cur and cur.get("cancel_requested"):
                        proc.kill()
                if msg.get("done") or msg.get("error"):
                    final = msg
            await proc.wait()

        try:
            await asyncio.wait_for(_read(), timeout=config.JOB_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            final = {"error": f"Tempo limite excedido ({config.JOB_TIMEOUT_S} s).", "code": "timeout"}
        stderr_tail = b""
        if proc.stderr is not None:
            try:
                stderr_tail = (await asyncio.wait_for(proc.stderr.read(), 5))[-2000:]
            except Exception:  # noqa: BLE001
                pass

        cur = await db.bim_versions.find_one({"model_id": model_id, "version": version},
                                             {"_id": 0, "cancel_requested": 1})
        if cur and cur.get("cancel_requested"):
            await _set(model_id, version, status="cancelled", stage="anulado pelo utilizador",
                       finished_at=_now().isoformat(), duration_s=round(time.monotonic() - t0, 2))
            return
        if not final or final.get("error") or proc.returncode != 0:
            code = (final or {}).get("code") or ("killed" if (proc.returncode or 0) < 0 else "crash")
            msg = (final or {}).get("error") or {
                "killed": "O processamento foi interrompido (limite de memória ou CPU).",
            }.get(code, "Falha no processamento do modelo.")
            log.warning("BIM job %s falhou: %s %s %s", key, code, (final or {}).get("detail"),
                        stderr_tail.decode("utf-8", "replace")[-500:])
            await _set(model_id, version, status="failed", error=msg, error_code=code, progress=1.0,
                       stage="falhou", finished_at=_now().isoformat(),
                       duration_s=round(time.monotonic() - t0, 2))
            return
        await _ingest(v, out_dir, t0)
    except Exception as exc:  # noqa: BLE001
        log.exception("BIM job %s erro interno", key)
        await _set(model_id, version, status="failed", error="Erro interno no processamento.",
                   error_code="internal", stage="falhou", finished_at=_now().isoformat(),
                   detail=f"{type(exc).__name__}"[:120])
    finally:
        _RUNNING.pop(key, None)
        shutil.rmtree(work, ignore_errors=True)


async def _ingest(v: dict, out_dir: str, t0: float) -> None:
    db = get_db()
    model_id, version, tenant = v["model_id"], v["version"], v["tenant_id"]
    await _set(model_id, version, progress=0.92, stage="a gravar resultados")
    res_path = os.path.join(out_dir, "result.json.gz")
    with gzip.open(res_path, "rt", encoding="utf-8") as fh:
        result = json.load(fh)
    chunk_keys = []
    i = 0
    while os.path.exists(os.path.join(out_dir, f"geom_{i}.json.gz")):
        k = storage.key_for(tenant, model_id, version, f"geom_{i}.json.gz")
        with open(os.path.join(out_dir, f"geom_{i}.json.gz"), "rb") as fh:
            await storage.put(k, fh.read(), "application/gzip")
        chunk_keys.append(k)
        i += 1
    with open(res_path, "rb") as fh:
        await storage.put(storage.key_for(tenant, model_id, version, "result.json.gz"), fh.read(), "application/gzip")

    await db.bim_elements.delete_many({"model_id": model_id, "version": version})
    docs = []
    for e in result["elements"]:
        e.update({"tenant_id": tenant, "model_id": model_id, "version": version, "included": bool(e.get("counted"))})
        docs.append(e)
        if len(docs) >= 1000:
            await db.bim_elements.insert_many(docs)
            docs = []
    if docs:
        await db.bim_elements.insert_many(docs)
    await _set(model_id, version, status="done", progress=1.0, stage="concluído",
               stats=result["stats"], storeys=result["storeys"], units=result["units"],
               schema=result["schema"], warnings=result["warnings"], engine_version=result["engine_version"],
               ifcopenshell_version=result["ifcopenshell_version"], chunk_keys=chunk_keys,
               finished_at=_now().isoformat(), duration_s=round(time.monotonic() - t0, 2))
    await db.bim_models.update_one({"model_id": model_id},
                                   {"$set": {"updated_at": _now().isoformat(), "last_done_version": version}})


async def cancel(model_id: str, version: int) -> None:
    db = get_db()
    await db.bim_versions.update_one({"model_id": model_id, "version": version,
                                      "status": {"$in": ["queued", "processing"]}},
                                     {"$set": {"cancel_requested": True}})
    # Ainda em fila → anula de imediato
    await db.bim_versions.update_one({"model_id": model_id, "version": version, "status": "queued"},
                                     {"$set": {"status": "cancelled", "stage": "anulado pelo utilizador",
                                               "finished_at": _now().isoformat()}})
    proc = _RUNNING.get(job_key(model_id, version))
    if proc and proc.returncode is None:
        proc.kill()


async def recover_orphans() -> int:
    """Trabalhos 'processing' sem progresso há demasiado tempo → nova tentativa (máx. 2) ou falha."""
    db = get_db()
    limit = (_now() - timedelta(seconds=config.JOB_TIMEOUT_S + 120)).isoformat()
    n = 0
    async for v in db.bim_versions.find({"status": "processing", "started_at": {"$lt": limit}}, {"_id": 0}):
        if int(v.get("attempts", 1)) < 2:
            await _set(v["model_id"], v["version"], status="queued", stage="retomado após interrupção")
        else:
            await _set(v["model_id"], v["version"], status="failed", error="Processamento interrompido.",
                       error_code="orphan", finished_at=_now().isoformat())
        n += 1
    return n


async def _loop(slot: int) -> None:
    while True:
        try:
            v = await _claim()
            if v:
                await run_job(v)
                continue
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("BIM dispatcher (slot %s)", slot)
        try:
            await asyncio.wait_for(_WAKE.wait(), timeout=5)
        except asyncio.TimeoutError:
            pass
        _WAKE.clear()


async def start() -> list[asyncio.Task]:
    if not config.enabled():
        return []
    os.makedirs(config.WORK_DIR, exist_ok=True)
    try:
        await recover_orphans()
    except Exception:  # noqa: BLE001
        log.exception("BIM recover_orphans")
    for i in range(config.MAX_CONCURRENT_JOBS):
        _TASKS.append(asyncio.create_task(_loop(i)))
    log.info("BIM Studio: %s worker(s) iniciados (%s)", len(_TASKS), WORKER_ID)
    return _TASKS


async def stop() -> None:
    for proc in list(_RUNNING.values()):
        if proc.returncode is None:
            proc.kill()
    for t in _TASKS:
        t.cancel()
    await asyncio.gather(*_TASKS, return_exceptions=True)
    _TASKS.clear()
