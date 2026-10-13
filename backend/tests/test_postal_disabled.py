"""Testes do guard `POSTAL_ENABLED` — garante que todas as rotas postais
devolvem 410 e que a API externa Merci Facteur nunca é instanciada quando
a funcionalidade está desligada (default em Portugal).
"""
from __future__ import annotations

import os

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport


def _reload_app() -> FastAPI:
    import importlib
    import routes.public_config as pc
    importlib.reload(pc)
    import engines.postal_guard as pg
    importlib.reload(pg)
    # Nota: `server.py` cria o scheduler no startup real; os testes abaixo não
    # invocam startup — montamos uma mini-app com apenas o router a validar.
    import routes.radar as radar_routes
    importlib.reload(radar_routes)

    app = FastAPI()
    app.include_router(pc.router, prefix="/api")

    @app.exception_handler(Exception)
    async def _any(_, exc):  # pragma: no cover - diagnóstico
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": str(exc)}, status_code=500)

    return app


@pytest.fixture
def postal_disabled(monkeypatch):
    monkeypatch.setenv("POSTAL_ENABLED", "false")
    return _reload_app()


@pytest.fixture
def postal_enabled(monkeypatch):
    monkeypatch.setenv("POSTAL_ENABLED", "true")
    return _reload_app()


@pytest.mark.asyncio
async def test_config_devolve_postal_false_por_defeito(postal_disabled):
    async with httpx.AsyncClient(transport=ASGITransport(app=postal_disabled),
                                  base_url="http://t") as c:
        resp = await c.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["postal_enabled"] is False
    assert data["radar_enabled"] is True
    assert data["country"] == "PT"


@pytest.mark.asyncio
async def test_config_devolve_postal_true_quando_ativo(postal_enabled):
    async with httpx.AsyncClient(transport=ASGITransport(app=postal_enabled),
                                  base_url="http://t") as c:
        resp = await c.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["postal_enabled"] is True


def test_guard_lanca_410_quando_desativado(monkeypatch):
    monkeypatch.setenv("POSTAL_ENABLED", "false")
    import importlib
    import routes.public_config as pc
    importlib.reload(pc)
    import engines.postal_guard as pg
    importlib.reload(pg)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        pg.ensure_postal_enabled()
    assert exc.value.status_code == 410
    assert "Portugal" in exc.value.detail


def test_guard_nao_lanca_quando_ativo(monkeypatch):
    monkeypatch.setenv("POSTAL_ENABLED", "true")
    import importlib
    import routes.public_config as pc
    importlib.reload(pc)
    import engines.postal_guard as pg
    importlib.reload(pg)
    pg.ensure_postal_enabled()  # nenhum raise


def test_mercifacteur_nao_e_instanciado_quando_desativado(monkeypatch):
    """Verifica que o cliente Merci Facteur não é tocado pelo guard."""
    monkeypatch.setenv("POSTAL_ENABLED", "false")
    import importlib
    import routes.public_config as pc
    importlib.reload(pc)
    import engines.postal_guard as pg
    importlib.reload(pg)

    accessed: list[str] = []

    class _Sentry:
        def __getattr__(self, name):
            accessed.append(name)
            raise AssertionError(f"Merci Facteur foi acedido: {name}")

    monkeypatch.setattr("engines.mercifacteur.configured", lambda: accessed.append("configured"))
    monkeypatch.setattr("engines.mercifacteur.MODES", ("normal",))
    monkeypatch.setattr("engines.mercifacteur.postage_price", _Sentry())

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        pg.ensure_postal_enabled()
    assert exc.value.status_code == 410
    assert accessed == []  # nenhum acesso ao MF
