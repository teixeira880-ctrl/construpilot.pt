"""Testes Perplexity Plus — mocks ai_router + MongoDB."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.perplexity_plus.pplx_cache import cache_key  # noqa: E402
from engines.perplexity_plus.pplx_presets import PRESETS, get_preset, preset_system  # noqa: E402
from engines.perplexity_plus.pplx_client import _extract_json  # noqa: E402


class TestPresets:
    def test_presets_pt(self):
        assert "DRE" in PRESETS
        assert "LNEC" in PRESETS
        assert "APA" in PRESETS
        assert "ADENE" in PRESETS
        assert "IHRU" in PRESETS

    def test_dre_domains(self):
        p = get_preset("DRE")
        assert "dre.pt" in p["domains"]

    def test_preset_lower_case_resolves(self):
        assert get_preset("lnec") is not None
        assert get_preset("UNKNOWN") is None
        assert get_preset(None) is None

    def test_preset_system_fallback(self):
        s = preset_system(None, "custom")
        assert s == "custom"
        s2 = preset_system("LNEC")
        assert "LNEC" in s2 or "engenheiro" in s2.lower()


class TestCache:
    def test_cache_key_deterministic(self):
        k1 = cache_key("ask", "prompt1", "sys", 100)
        k2 = cache_key("ask", "prompt1", "sys", 100)
        k3 = cache_key("ask", "prompt1", "sys", 200)
        assert k1 == k2
        assert k1 != k3
        assert len(k1) == 64  # sha256


class TestExtractJson:
    def test_plain_json(self):
        d = _extract_json('{"a": 1}')
        assert d == {"a": 1}

    def test_markdown_wrapped(self):
        d = _extract_json('```json\n{"b": 2}\n```')
        assert d == {"b": 2}

    def test_json_with_text_before_after(self):
        d = _extract_json("Some text {\"c\": 3} tail")
        assert d == {"c": 3}

    def test_invalid_returns_none(self):
        assert _extract_json("not json") is None
        assert _extract_json("") is None


class TestClient:
    @pytest.mark.anyio
    async def test_is_configured(self):
        from engines.perplexity_plus.pplx_client import PplxPlusClient
        c = PplxPlusClient()
        # Depende do env mas não deve falhar
        assert isinstance(c.is_configured(), bool)

    @pytest.mark.anyio
    async def test_ask_structured_uses_cache_on_hit(self):
        from engines.perplexity_plus import pplx_client as mod
        with patch.object(mod, "cache_get", new=AsyncMock(return_value={"text": "cached", "parsed": {"ok": True}})):
            with patch.object(mod, "cache_set", new=AsyncMock()):
                r = await mod.pplx_plus_client.ask_structured(
                    prompt="x", system="y", use_cache=True,
                )
        assert r["cache"] == "HIT"
        assert r["parsed"] == {"ok": True}

    @pytest.mark.anyio
    async def test_ask_structured_cache_miss_calls_provider(self):
        from engines.perplexity_plus import pplx_client as mod
        from engines.ai_providers.base import AIResponse, AIUsage, Citation

        fake_resp = AIResponse(
            text='{"ok":true}', provider="perplexity", model="sonar",
            latency_ms=100, usage=AIUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            citations=[Citation(url="https://dre.pt/x", title="t", snippet="s")],
            request_id="r1", stop_reason="stop",
        )
        fake_pplx = MagicMock()
        fake_pplx.ask = AsyncMock(return_value=fake_resp)

        with patch.object(mod, "cache_get", new=AsyncMock(return_value=None)):
            with patch.object(mod, "cache_set", new=AsyncMock()) as cs:
                with patch.object(mod.ai_router, "_perplexity", fake_pplx, create=True):
                    # Força `perplexity` property devolver fake
                    with patch.object(type(mod.ai_router), "perplexity",
                                      new=property(lambda self: fake_pplx)):
                        r = await mod.pplx_plus_client.ask_structured(
                            prompt="normas RGEU", system="sys", use_cache=True,
                        )
        assert r["cache"] == "MISS"
        assert r["parsed"] == {"ok": True}
        assert len(r["citations"]) == 1
        assert r["citations"][0]["url"] == "https://dre.pt/x"
        cs.assert_called_once()


class TestRoutesSmoke:
    @pytest.mark.anyio
    async def test_presets_endpoint_shape(self):
        from routes.perplexity_plus import list_presets
        fake_user = {"user_id": "u1"}
        r = await list_presets(user=fake_user)
        assert len(r["presets"]) == 5
        codes = {p["code"] for p in r["presets"]}
        assert codes == {"DRE", "LNEC", "APA", "ADENE", "IHRU"}
