"""Espera inteligente dos workers de fila (assistente, agentes, estudos).

Antes, cada worker consultava o MongoDB a cada 1–2 s mesmo sem trabalho (≈14 operações/s em repouso,
24 h por dia). Agora:
- quando um pedido é posto na fila neste processo, ``wake(nome)`` acorda os workers de imediato
  (latência igual ou melhor do que antes);
- sem trabalho, o intervalo entre consultas cresce de 1 s até ``WORKER_IDLE_MAX_S`` (10 s por defeito),
  o que continua a apanhar pedidos criados por outro processo;
- as limpezas de leases expirados continuam a correr antes de cada tentativa (mesma semântica de antes).

Nenhuma regra de negócio muda: só a frequência das consultas em repouso.
"""
from __future__ import annotations

import asyncio
import os

IDLE_MIN_S = 1.0
IDLE_MAX_S = max(IDLE_MIN_S, float(os.environ.get("WORKER_IDLE_MAX_S", "10")))

_events: dict[str, asyncio.Event] = {}


def _event(name: str) -> asyncio.Event:
    ev = _events.get(name)
    if ev is None:
        ev = _events[name] = asyncio.Event()
    return ev


def wake(name: str) -> None:
    """Acorda os workers ``name`` (chamar depois de pôr um trabalho na fila)."""
    try:
        _event(name).set()
    except Exception:  # noqa: BLE001 — nunca pode fazer falhar o pedido que pôs o trabalho na fila
        pass


async def idle_wait(name: str, current: float | None) -> float:
    """Espera até ser acordado ou até ao fim do intervalo atual; devolve o intervalo seguinte (recuo exponencial)."""
    delay = IDLE_MIN_S if not current else min(IDLE_MAX_S, current)
    ev = _event(name)
    try:
        await asyncio.wait_for(ev.wait(), timeout=delay)
        ev.clear()
        return IDLE_MIN_S
    except asyncio.TimeoutError:
        return min(IDLE_MAX_S, delay * 2)

