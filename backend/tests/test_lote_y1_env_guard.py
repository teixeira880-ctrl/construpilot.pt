"""Y.1 — valida guard openapi/docs/redoc + HSTS em ENV=production.

Testes evitam TestClient de várias instâncias de app porque motor (mongo)
partilha event loop e dá RuntimeError. Em vez disso, testam o middleware
directamente e inspeccionam atributos do app FastAPI.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_y1_env_default_in_dotenv_is_development():
    """.env deve ter ENV=development após fix da linha 33."""
    content = (ROOT / ".env").read_text()
    assert "ENV=development" in content, "ENV=development não encontrado em .env"
    assert 'ENV="SENDER_PT_FROM' not in content, "linha 33 ainda corrompida"


def test_y1_guard_openapi_disabled_in_production(monkeypatch):
    """Com ENV=production, FastAPI é construído com openapi/docs/redoc = None."""
    monkeypatch.setenv("ENV", "production")
    # Remove sys.modules para forçar re-exec das expressões no FastAPI(...).
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server
    assert server.app.openapi_url is None
    assert server.app.docs_url is None
    assert server.app.redoc_url is None


def test_y1_guard_openapi_enabled_in_development(monkeypatch):
    monkeypatch.setenv("ENV", "development")
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server
    assert server.app.openapi_url == "/api/openapi.json"
    assert server.app.docs_url == "/api/docs"
    assert server.app.redoc_url == "/api/redoc"


@pytest.mark.asyncio
async def test_y1_security_headers_middleware_sets_fixed_headers(monkeypatch):
    """Chama o dispatch() do SecurityHeadersMiddleware directamente."""
    from starlette.requests import Request
    from starlette.responses import PlainTextResponse

    monkeypatch.setenv("ENV", "development")
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server

    shm_cls = None
    for mw in server.app.user_middleware:
        if mw.cls.__name__ == "SecurityHeadersMiddleware":
            shm_cls = mw.cls
            break
    assert shm_cls is not None, "SecurityHeadersMiddleware não encontrado"

    async def _call_next(_req):
        return PlainTextResponse("ok")

    scope = {"type": "http", "method": "GET", "headers": [], "path": "/api/",
             "query_string": b"", "scheme": "http", "server": ("test", 80),
             "root_path": "", "http_version": "1.1", "app": server.app}
    async def _recv():
        return {"type": "http.disconnect"}
    req = Request(scope, receive=_recv)
    instance = shm_cls(server.app)
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

    monkeypatch.setenv("ENV", "production")
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server

    shm_cls = None
    for mw in server.app.user_middleware:
        if mw.cls.__name__ == "SecurityHeadersMiddleware":
            shm_cls = mw.cls
            break
    assert shm_cls is not None

    async def _call_next(_req):
        return PlainTextResponse("ok")

    scope = {"type": "http", "method": "GET", "headers": [], "path": "/api/",
             "query_string": b"", "scheme": "http", "server": ("test", 80),
             "root_path": "", "http_version": "1.1", "app": server.app}
    async def _recv():
        return {"type": "http.disconnect"}
    req = Request(scope, receive=_recv)
    instance = shm_cls(server.app)
    resp = await instance.dispatch(req, _call_next)
    hsts = resp.headers.get("strict-transport-security")
    assert hsts is not None, "HSTS ausente em ENV=production"
    assert "max-age=31536000" in hsts
