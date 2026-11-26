import asyncio
import io

from PIL import Image

from engines.atelier_archi import render_ia as RI


def _png(w, h, cor=(200, 100, 50)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), cor).save(b, "PNG")
    return b.getvalue()


def test_pad_e_recorte_mantem_a_vista():
    base = _png(1280, 720)
    padded, tamanho, box = RI._pad(base)
    w, h = Image.open(io.BytesIO(padded)).size
    assert abs(w / h - 1.5) < 0.01 and tamanho == (w, h)
    saida = RI._recortar(_png(1536, 1024), tamanho, box)
    assert Image.open(io.BytesIO(saida)).size == (1280, 720)


def test_openai_primeiro(monkeypatch):
    async def fake_openai(prompt, base, timeout):
        return b"\x89PNGok", "gpt-image-1"

    async def nunca(*a, **k):
        raise AssertionError("não devia chegar ao photoreal")
    monkeypatch.setattr(RI, "_openai", fake_openai)
    from engines import photoreal as PR
    monkeypatch.setattr(PR, "render", nunca)
    assert asyncio.run(RI.render(_png(64, 64), "casa")) == (b"\x89PNGok", "gpt-image-1")


def test_sem_openai_passa_aos_outros_motores(monkeypatch):
    async def sem(prompt, base, timeout):
        return None
    vistos = {}

    async def fake_pr(base, prompt, **k):
        vistos.update(k)
        return b"jpg", "nano_banana_3.1"
    monkeypatch.setattr(RI, "_openai", sem)
    from engines import photoreal as PR
    monkeypatch.setattr(PR, "render", fake_pr)
    assert asyncio.run(RI.render(_png(64, 64), "casa")) == (b"jpg", "nano_banana_3.1")
    assert "openai" not in vistos["engines"] and vistos["engines"][0] == "emergent"


def test_ordem_configuravel(monkeypatch):
    monkeypatch.setenv("ATELIER_RENDER_MOTORES", "emergent, gen4_image")
    assert RI.motores() == ["emergent", "gen4_image"]
