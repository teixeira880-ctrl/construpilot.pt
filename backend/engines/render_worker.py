"""Renderização física (Mitsuba) num PROCESSO SEPARADO.

20/11: no servidor, o Mitsuba corria em threads do próprio backend e prendia o GIL em blocos de segundos — com 4 vistas
HD o estudo BET ficava parado no passo «imagens» e o servidor inteiro ficava lento. Agora cada imagem é feita num
subprocesso com prazo: o servidor nunca bloqueia e, se o prazo acabar, o processo é terminado e fica a vista calculada.

Uso interno: python -m engines.render_worker  < JSON {"kind": "geo"|"raw", "model": {...}, "view", "w", "h", "spp"}  > PNG
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

log = logging.getLogger(__name__)
_SEM: list = []


def _sem() -> asyncio.Semaphore:
    """No máximo N renderizações em simultâneo (por defeito 1): o resto do servidor continua com CPU."""
    if not _SEM:
        _SEM.append(asyncio.Semaphore(max(1, int(os.environ.get("PBR_MAX_PARALLEL") or 1))))
    return _SEM[0]


async def render(kind: str, model: dict, view: str, w: int, h: int, spp: int, timeout: float = 600.0) -> bytes | None:
    """PNG ou None (motor ausente, erro ou prazo excedido). Nunca bloqueia o ciclo de eventos."""
    payload = json.dumps({"kind": kind, "model": model, "view": view, "w": int(w), "h": int(h), "spp": int(spp)},
                         default=str).encode()
    backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    async with _sem():
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "engines.render_worker", cwd=backend,
                                                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.wait()
            log.warning("pbr render %s %dx%d spp%d: prazo de %.0f s excedido — processo terminado", view, w, h, spp, timeout)
            return None
    if proc.returncode != 0 or not out.startswith(b"\x89PNG"):
        log.warning("pbr render %s failed (rc=%s): %s", view, proc.returncode, (err or b"")[-400:].decode(errors="ignore"))
        return None
    return out


def _main() -> int:
    req = json.loads(sys.stdin.buffer.read() or b"{}")
    if req.get("kind") == "geo":
        from engines.bet_geo import views as V
        from engines.bet_geo.model import Building
        png = V.render_pbr(Building.from_dict(req["model"]), req["view"], req["w"], req["h"], req["spp"])
    else:
        from engines import house_pbr
        png = house_pbr.render(req["model"], req["w"], req["h"], req["view"], req["spp"])
    if not png:
        return 2
    sys.stdout.buffer.write(png)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(_main())
