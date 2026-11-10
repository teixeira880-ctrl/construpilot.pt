"""A leitura dos planos por IA tem prazo total: um plano novo nunca deixa o estudo parado indefinidamente."""
import asyncio
import time

from engines.bet_core import reader as R


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def test_fornecedores_lentos_respeitam_o_prazo(monkeypatch):
    chamadas = []

    async def lento(system, text, images=None, model=None, max_tokens=4096, **kw):
        chamadas.append(1)
        await asyncio.sleep(3600)

    for n in list(R.PROVIDERS):
        monkeypatch.setitem(R.PROVIDERS, n, lento)

    async def go():
        tok = R.abrir_prazo(25)       # 25 s: o 1.º fornecedor tem ~25 s, os outros já não arrancam (< 20 s)
        try:
            return await R._default_llm("s", "t")
        finally:
            R.fechar_prazo(tok)
    t = time.monotonic()
    try:
        _run(go())
        assert False, "devia falhar"
    except R.ProvidersDown:
        pass
    assert time.monotonic() - t < 30
    assert len(chamadas) == 1


def test_sem_tempo_nao_ha_correcao():
    async def go():
        tok = R.abrir_prazo(100)      # < FIX_MIN_S (150): nenhuma correção arranca
        try:
            return R.ha_tempo(), R.ha_tempo(50)
        finally:
            R.fechar_prazo(tok)
    assert _run(go()) == (False, True)
    assert R.ha_tempo() is True       # fora de uma leitura: sem prazo


def test_prazo_aninhado_nao_e_alargado():
    async def go():
        t1 = R.abrir_prazo(100)
        t2 = R.abrir_prazo(10_000)    # read_frame dentro de read_building: mantém o prazo exterior
        r = R.prazo_resta()
        R.fechar_prazo(t2)
        R.fechar_prazo(t1)
        return t2, r
    t2, r = _run(go())
    assert t2 is None and r <= 100
