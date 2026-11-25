"""Limites globais para trabalho pesado de CPU/RAM (renders 3D).

Antes, vários renders Blender (Cycles, até 1 500 s, todos os núcleos) e Mitsuba podiam correr ao mesmo tempo
— causa principal dos picos de 100 % de CPU e de memória. Agora:
- no máximo ``HEAVY_RENDER_CONCURRENCY`` renders em simultâneo por processo (1 por defeito); os seguintes
  esperam a sua vez em vez de saturarem o servidor;
- cada render usa no máximo ``render_threads()`` núcleos (metade dos núcleos por defeito), para a API
  continuar a responder durante um render.

O resultado de cada render é idêntico: só muda quando e com quantos núcleos corre.
Funciona tanto em código síncrono (threads) como em código chamado via ``asyncio.to_thread``.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager

RENDER_CONCURRENCY = max(1, int(os.environ.get("HEAVY_RENDER_CONCURRENCY", "1")))
_render_slots = threading.BoundedSemaphore(RENDER_CONCURRENCY)


def render_threads() -> int:
    """Núcleos por render: BLENDER_THREADS / RENDER_THREADS se definidos, senão metade dos núcleos (mín. 1)."""
    for key in ("RENDER_THREADS", "BLENDER_THREADS"):
        raw = (os.environ.get(key) or "").strip()
        if raw.isdigit() and int(raw) > 0:
            return int(raw)
    return max(1, (os.cpu_count() or 2) // 2)


@contextmanager
def render_slot(timeout_s: float | None = None):
    """Reserva um lugar de render. ``timeout_s``: tempo máximo de espera na fila (None = sem limite)."""
    ok = _render_slots.acquire(timeout=timeout_s) if timeout_s is not None else _render_slots.acquire()
    if not ok:
        raise TimeoutError("Fila de renders ocupada; tente novamente dentro de alguns minutos.")
    try:
        yield
    finally:
        _render_slots.release()
