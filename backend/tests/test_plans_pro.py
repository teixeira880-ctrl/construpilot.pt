"""Testes Plans Pro — mocks Autodesk + AI providers."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro import plan_metadata  # noqa: E402
from engines.plans_pro.plan_metadata import aggregate_quantities  # noqa: E402


class TestAggregateQuantities:
    def test_revit_categories(self):
        views = [
            {"categories": [("Walls", 42), ("Doors", 7), ("Windows", 12)]},
            {"categories": [("Walls", 40)]},  # outra view
        ]
        q = aggregate_quantities(views)
        assert "Walls" in q
        assert q["Walls"]["count"] == 42
        assert q["Walls"]["source"] == "categories"

    def test_dwg_layers_grouping(self):
        views = [
            {
                "layers": [
                    ("A-WALL-INT", 50),
                    ("A-WALL-EXT", 30),
                    ("A-DOOR", 10),
                    ("A-WIND", 15),
                ]
            }
        ]
        q = aggregate_quantities(views)
        assert "Paredes" in q
        assert q["Paredes"]["count"] == 80
        assert q["Portas"]["count"] == 10
        assert q["Janelas"]["count"] == 15
        assert any(l["layer"] == "A-WALL-INT" for l in q["Paredes"]["layers"])

    def test_empty_views(self):
        assert aggregate_quantities([]) == {}
        assert aggregate_quantities([{"categories": [], "layers": []}]) == {}

    def test_pt_order(self):
        views = [
            {
                "layers": [
                    ("ESCADA-01", 2),
                    ("PAREDE-01", 20),
                    ("LAJE-01", 5),
                ]
            }
        ]
        q = aggregate_quantities(views)
        keys = list(q.keys())
        # Paredes antes de Lajes antes de Escadas
        assert keys.index("Paredes") < keys.index("Lajes") < keys.index("Escadas")


class TestAutodeskClient:
    @pytest.mark.anyio
    async def test_is_configured(self):
        from engines.plans_pro.autodesk_client import AutodeskClient
        c = AutodeskClient()
        # Depende do env, mas não deve falhar
        assert isinstance(c.is_configured(), bool)
        assert isinstance(c.bucket_key, str)
        assert len(c.bucket_key) >= 3

    @pytest.mark.anyio
    async def test_token_cached(self):
        from engines.plans_pro.autodesk_client import AutodeskClient
        c = AutodeskClient()
        with patch.object(c, "_fetch_token", new=AsyncMock(return_value=("fake_token", 3599))):
            t1 = await c.access_token()
            t2 = await c.access_token()
            assert t1 == t2 == "fake_token"
            # 2 chamadas, 1 fetch
            assert c._fetch_token.call_count == 1

    @pytest.mark.anyio
    async def test_viewer_token_shape(self):
        from engines.plans_pro.autodesk_client import AutodeskClient
        c = AutodeskClient()
        with patch.object(c, "_fetch_token", new=AsyncMock(return_value=("v_token", 3599))):
            tok = await c.viewer_token()
            assert tok["access_token"] == "v_token"
            assert tok["token_type"] == "Bearer"
            assert tok["expires_in"] > 0


class TestLayerCategory:
    def test_pt_layer_mapping(self):
        from engines.plans_pro.plan_metadata import _layer_category
        assert _layer_category("A-PAREDE-INT") == "Paredes"
        assert _layer_category("JANELA-01") == "Janelas"
        assert _layer_category("PILAR-estrutural") == "Pilares"
        assert _layer_category("ESGOTO-01") == "Canalização"
        assert _layer_category("foobar123") == "Outros"
