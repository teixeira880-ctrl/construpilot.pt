"""Cascade photoréaliste (engines.photoreal) : ordre, repli, aucune exception."""
import asyncio
import io

from PIL import Image

from engines import photoreal as PR


def _img():
    b = io.BytesIO(); Image.new("RGB", (800, 450), (90, 120, 160)).save(b, "PNG"); return b.getvalue()


def test_order_env(monkeypatch):
    monkeypatch.setenv("PHOTOREAL_MODELS", "gen4_image, emergent")
    assert PR._order() == ["gen4_image", "emergent"]
    monkeypatch.delenv("PHOTOREAL_MODELS")
    assert PR._order()[0] == "gpt_image_2"


def test_cascade_falls_through(monkeypatch):
    calls = []

    async def fake(model, prompt, refs, timeout):
        calls.append((model, prompt[:20], [t for t, _ in refs]))
        if model != "gen4_image":
            raise RuntimeError("down")
        return _img()
    monkeypatch.setattr(PR, "_runway", fake)
    monkeypatch.setenv("PHOTOREAL_MODELS", "gpt_image_2,gemini_image3_pro,gen4_image")
    data, eng = asyncio.run(PR.render(_img(), "A house.", style_ref=_img()))
    assert eng == "gen4_image" and [c[0] for c in calls] == ["gpt_image_2", "gemini_image3_pro", "gen4_image"]
    assert calls[0][2] == ["model", "style"] and Image.open(io.BytesIO(data)).size[0] == 3840


def test_all_fail_none(monkeypatch):
    async def fake(*a):
        return None
    monkeypatch.setattr(PR, "_runway", fake)
    assert asyncio.run(PR.render(_img(), "x", engines=["gpt_image_2", "gen4_image"])) is None


def test_data_uri_small():
    assert PR._data_uri(_img()).startswith("data:image/jpeg;base64,")
