"""Agendador (APScheduler) numa única instância.

Sem este bloqueio, com 2 processos uvicorn ou 2 réplicas, todas as tarefas automáticas (e-mails de relance,
faturas, artigos, Google Ads…) correriam em duplicado. Um documento ``scheduler_leader`` no MongoDB funciona
como lease: só o processo que o detém arranca o agendador; os outros tentam de novo a cada LEASE_S/2.

``SCHEDULER_ENABLED=false`` desliga completamente as tarefas agendadas (ambiente de staging: nenhum e-mail,
nenhuma publicação, nenhuma despesa automática). Por defeito fica ligado, como hoje.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from core.db import db

log = logging.getLogger(__name__)

LEASE_S = int(os.environ.get("SCHEDULER_LEASE_S", "90"))
OWNER = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
_KEY = "scheduler_leader"


def enabled() -> bool:
    return os.environ.get("SCHEDULER_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")


async def _acquire_or_renew() -> bool:
    now = datetime.now(timezone.utc)
    until = now + timedelta(seconds=LEASE_S)
    try:
        res = await db.app_locks.update_one(
            {"_id": _KEY, "$or": [{"owner": OWNER}, {"until": {"$lt": now}}]},
            {"$set": {"owner": OWNER, "until": until, "renewed_at": now}},
            upsert=True)
        return bool(res.matched_count or res.upserted_id)
    except Exception as exc:  # noqa: BLE001 — DuplicateKeyError = outro processo detém o lease
        if type(exc).__name__ != "DuplicateKeyError":
            log.warning("scheduler lock: %s", type(exc).__name__)
        return False


async def _loop(scheduler) -> None:
    started = False
    while True:
        leader = await _acquire_or_renew()
        if leader and not started:
            scheduler.start()
            started = True
            log.info("Agendador arrancado neste processo (%s)", OWNER)
        elif not leader and started:
            # Perdeu o lease (ex.: MongoDB indisponível muito tempo): pára para não haver duas instâncias.
            scheduler.shutdown(wait=False)
            started = False
            log.warning("Agendador parado: lease perdido (%s)", OWNER)
        await asyncio.sleep(max(5, LEASE_S // 3))


def start(scheduler, app=None):
    """Arranca o agendador só no processo líder. Devolve a tarefa de vigilância (ou None se desligado)."""
    if not enabled():
        log.info("Agendador DESLIGADO (SCHEDULER_ENABLED=false) — nenhuma tarefa automática")
        return None
    task = asyncio.create_task(_loop(scheduler))
    if app is not None:
        app.state.scheduler_lock_task = task
    return task
