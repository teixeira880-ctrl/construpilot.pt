"""Y.3 — CORS restrito em produção."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reload_server_with_env(monkeypatch, env_value: str,
                            cors_origins_prod: str | None = None):
    monkeypatch.setenv("ENV", env_value)
    if cors_origins_prod is not None:
        monkeypatch.setenv("CORS_ORIGINS_PROD", cors_origins_prod)
    for m in [k for k in list(sys.modules) if k == "server" or k.startswith("server.")]:
        sys.modules.pop(m, None)
    import server
    return server.app


def _cors_middleware_config(app):
    """Extrai options do CORSMiddleware montado no app."""
    for mw in app.user_middleware:
        if mw.cls.__name__ == "CORSMiddleware":
            return mw.kwargs
    return None


def test_y3_cors_production_restricts_to_construpilot_pt(monkeypatch):
    app = _reload_server_with_env(monkeypatch, "production")
    cfg = _cors_middleware_config(app)
    assert cfg is not None
    origins = cfg.get("allow_origins") or []
    assert "https://construpilot.pt" in origins
    assert "https://www.construpilot.pt" in origins
    # Em produção não há regex Emergent (preview URLs não autorizados)
    assert cfg.get("allow_origin_regex") is None
    assert cfg.get("allow_credentials") is True
    # Métodos explícitos, sem "*"
    methods = cfg.get("allow_methods") or []
    assert "*" not in methods
    assert "GET" in methods and "POST" in methods and "OPTIONS" in methods


def test_y3_cors_dev_keeps_wildcard_and_emergent_regex(monkeypatch):
    app = _reload_server_with_env(monkeypatch, "development")
    cfg = _cors_middleware_config(app)
    assert cfg is not None
    # Dev mantém allow_origin_regex para preview URLs dinâmicos
    assert cfg.get("allow_origin_regex") is not None
    assert "emergent" in cfg["allow_origin_regex"]
    methods = cfg.get("allow_methods") or []
    assert "*" in methods


def test_y3_cors_origins_prod_overridable_via_env(monkeypatch):
    app = _reload_server_with_env(
        monkeypatch, "production",
        cors_origins_prod="https://staging.construpilot.pt,https://backup.example.com",
    )
    cfg = _cors_middleware_config(app)
    origins = cfg.get("allow_origins") or []
    assert "https://staging.construpilot.pt" in origins
    assert "https://backup.example.com" in origins
    assert "https://construpilot.pt" not in origins  # override total


@pytest.mark.asyncio
async def test_y3_cors_accepts_construpilot_rejects_evil_in_production(monkeypatch):
    """Preflight em produção: construpilot.pt → OK, evil.example.com → omitido.
    Combinado num único teste para evitar reutilização de event-loop entre
    múltiplas instâncias de TestClient (motor/mongo partilhado em xdist)."""
    from starlette.testclient import TestClient
    app = _reload_server_with_env(monkeypatch, "production")
    with TestClient(app) as c:
        ok = c.options("/api/", headers={
            "Origin": "https://construpilot.pt",
            "Access-Control-Request-Method": "GET",
        })
        evil = c.options("/api/", headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        })
    assert ok.headers.get("access-control-allow-origin") == "https://construpilot.pt"
    assert evil.headers.get("access-control-allow-origin", "") != "https://evil.example.com"
