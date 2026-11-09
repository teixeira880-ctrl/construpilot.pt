"""09/11/2026 : choix « maison CLT » respecté + étude BET tuée par un redémarrage détectée en 3 min."""
import asyncio

from engines.bet_frame.hook import _user_says_house
from engines.bet_core import assistant_tool as at


def test_user_choice_house_clt():
    assert _user_says_house("maison CLT / bois massif, R+1")
    assert _user_says_house("on garde maison CLT comme hypothèse ; le moteur avait proposé immeuble_collectif")
    assert _user_says_house("moradia em madeira maciça CLT")
    assert _user_says_house("Single-family house, cross-laminated timber")
    assert not _user_says_house("immeuble de logements collectifs R+5, ossature béton")
    assert not _user_says_house("")


def test_stale_threshold_short():
    assert at.STALE_MIN <= 3 and at.HEARTBEAT_S * 2 < at.STALE_MIN * 60


def test_heartbeat_updates_and_stops(monkeypatch):
    calls = []

    class Coll:
        async def update_one(self, q, u):
            calls.append(q)

    class DB:
        bet_study_jobs = Coll()

    monkeypatch.setattr(at, "HEARTBEAT_S", 0.01)

    async def work():
        await asyncio.sleep(0.05)
        return "ok"

    async def go():
        assert await at._with_heartbeat(DB(), "job1", work()) == "ok"
        n = len(calls)
        await asyncio.sleep(0.05)
        assert n >= 2 and len(calls) == n  # battements pendant le calcul, plus aucun après
    asyncio.run(go())
