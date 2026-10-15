"""Y.1 — valida guard openapi/docs/redoc + HSTS em ENV=production.

Testes evitam TestClient de várias instâncias de app porque motor (mongo)
partilha event loop e dá RuntimeError. Em vez disso, testam o middleware
directamente e inspeccionam atributos do app FastAPI.
"""
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reload_with_env(monkeypatch, env_value: str):
    """Reload core.environment + server, retorna o novo app."""
    monkeypatch.setenv("ENV", env_value)
    import core.environment
    importlib.reload(core.environment)
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server
    return server.app


def test_y1_env_default_in_dotenv_is_development():
    """.env deve ter ENV=development após fix da linha 33."""
    content = (ROOT / ".env").read_text()
    assert "ENV=development" in content, "ENV=development não encontrado em .env"
    assert 'ENV="SENDER_PT_FROM' not in content, "linha 33 ainda corrompida"


def test_y1_guard_openapi_disabled_in_production(monkeypatch):
    """Com ENV=production, FastAPI é construído com openapi/docs/redoc = None."""
    app = _reload_with_env(monkeypatch, "production")
    assert app.openapi_url is None
    assert app.docs_url is None
    assert app.redoc_url is None


def test_y1_guard_openapi_enabled_in_development(monkeypatch):
    app = _reload_with_env(monkeypatch, "development")
    assert app.openapi_url == "/api/openapi.json"
    assert app.docs_url == "/api/docs"
    assert app.redoc_url == "/api/redoc"


@pytest.mark.asyncio
async def test_y1_security_headers_middleware_sets_fixed_headers(monkeypatch):
    """Chama o dispatch() do SecurityHeadersMiddleware directamente."""
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    app = _reload_with_env(monkeypatch, "development")

    shm_cls = None
    for mw in app.user_middleware:
        if mw.cls.__name__ == "SecurityHeadersMiddleware":
            shm_cls = mw.cls
            break
    assert shm_cls is not None, "SecurityHeadersMiddleware não encontrado"

    async def _call_next(_req):
        return PlainTextResponse("ok")

    scope = {"type": "http", "method": "GET", "headers": [], "path": "/api/",
             "query_string": b"", "scheme": "http", "server": ("test", 80),
             "root_path": "", "http_version": "1.1", "app": app}
    async def _recv():
        return {"type": "http.disconnect"}
    req = Request(scope, receive=_recv)
    instance = shm_cls(app)
    resp = await instance.dispatch(req, _call_next)
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert "strict-origin" in (resp.headers.get("referrer-policy") or "")
    assert "geolocation=()" in (resp.headers.get("permissions-policy") or "")
    # Dev → sem HSTS
    assert resp.headers.get("strict-transport-security") is None


@pytest.mark.asyncio
async def test_y1_hsts_only_in_production(monkeypatch):
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    app = _reload_with_env(monkeypatch, "production")

    shm_cls = None
    for mw in app.user_middleware:
        if mw.cls.__name__ == "SecurityHeadersMiddleware":
            shm_cls = mw.cls
            break
    assert shm_cls is not None

    async def _call_next(_req):
        return PlainTextResponse("ok")

    scope = {"type": "http", "method": "GET", "headers": [], "path": "/api/",
             "query_string": b"", "scheme": "http", "server": ("test", 80),
             "root_path": "", "http_version": "1.1", "app": app}
    async def _recv():
        return {"type": "http.disconnect"}
    req = Request(scope, receive=_recv)
    instance = shm_cls(app)
    resp = await instance.dispatch(req, _call_next)
    hsts = resp.headers.get("strict-transport-security")
    assert hsts is not None, "HSTS ausente em ENV=production"
    assert "max-age=31536000" in hsts
