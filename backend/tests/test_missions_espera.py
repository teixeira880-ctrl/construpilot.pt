"""14/11: lancer_programme_ia espera pelo programa e devolve os entregáveis ou o erro (não termina com uma promessa)."""
import asyncio
from engines import assistant_missions as M


class _Col:
    def __init__(self, seq):
        self.seq = list(seq)

    async def find_one(self, *a, **k):
        return self.seq.pop(0) if len(self.seq) > 1 else self.seq[0]


class _DB:
    def __init__(self, seq):
        self.agent_runs = _Col(seq)


def test_espera_ate_terminar(monkeypatch):
    seq = [{"status": "running"}, {"status": "done", "result": {"steps": [{"key": "metre", "status": "done", "result": {"pdf": "/x.pdf"}}]}}]
    monkeypatch.setattr(M, "db", _DB(seq))
    monkeypatch.setattr(asyncio, "sleep", lambda s: asyncio.get_event_loop().create_future() if False else _nada())
    r = asyncio.run(M._esperar("r1", "u1"))
    assert r["status"] == "done" and r["resultats"][0]["liens"] == ["/x.pdf"]


async def _nada():
    return None


def test_fila_parada_dita_com_clareza(monkeypatch):
    import time
    monkeypatch.setattr(M, "db", _DB([{"status": "queued"}]))
    t = [0.0]

    def mono():
        t[0] += 50
        return t[0]
    monkeypatch.setattr(time, "monotonic", mono)
    monkeypatch.setattr(asyncio, "sleep", lambda s: _nada())
    r = asyncio.run(M._esperar("r1", "u1"))
    assert r["status"] == "queued" and "fila" in r["erreur"]
