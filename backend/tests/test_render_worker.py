"""20/11: renderização física num processo separado — o servidor nunca fica preso e o prazo é respeitado."""
import asyncio
import time

from shapely.geometry import Polygon

from engines import render_worker
from engines.bet_geo.model import Building


def _geo():
    b = Building(footprint=Polygon([(0, 0), (12, 0), (12, 8), (0, 8)]), roof_level=3.2)
    return {**b.to_dict(), "slab_h": 0.22}


def test_prazo_excedido_termina_o_processo_e_devolve_none():
    t0 = time.time()
    out = asyncio.run(render_worker.render("geo", _geo(), "main", 2560, 1440, 512, timeout=1.0))
    assert out is None and time.time() - t0 < 10


def test_ciclo_de_eventos_livre_durante_a_renderizacao():
    gaps = []

    async def run():
        async def tick():
            last = time.time()
            for _ in range(40):
                await asyncio.sleep(0.05)
                now = time.time()
                gaps.append(now - last)
                last = now
        await asyncio.gather(tick(), render_worker.render("geo", _geo(), "main", 640, 360, 4, timeout=60))
    asyncio.run(run())
    assert max(gaps) < 0.5
