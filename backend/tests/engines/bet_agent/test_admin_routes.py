"""Testes das rotas admin do BET-PT Agent (dependency override, sem Claude live)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def admin_test_client():
    """TestClient em escopo de módulo (único event loop para motor client)."""
    import os as _os
    _os.environ["BET_AGENT_ENABLED"] = "false"

    from server import app
    from core.security import admin_user

    async def _fake_admin():
        return {"user_id": "admin-test", "role": "admin", "is_demo": False, "email": "admin@test"}

    def _fake_not_demo(user, action="x"):
        return None

    app.dependency_overrides[admin_user] = _fake_admin
    import routes.admin_bet_agent as mod
    original_ensure = mod.ensure_not_demo
    mod.ensure_not_demo = _fake_not_demo

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(admin_user, None)
    mod.ensure_not_demo = original_ensure


def test_status_returns_flags(admin_test_client: TestClient) -> None:
    r = admin_test_client.get("/api/admin/bet-agent/status")
    assert r.status_code == 200
    body = r.json()
    assert "feature_flag" in body
    assert "anthropic_key_present" in body
    assert "cost_limit_eur" in body
    assert body["feature_flag"] is False  # default desligado em CI
    # Resposta não revela nenhum valor de segredo.
    serialized = r.text
    assert "sk-ant" not in serialized


def test_run_blocked_when_feature_disabled(admin_test_client: TestClient) -> None:
    import io
    files = {
        "arquitectura": ("arq.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"),
    }
    data = {"brief_json": "{}"}
    r = admin_test_client.post("/api/admin/bet-agent/run", files=files, data=data)
    assert r.status_code == 503
    body = r.json()
    assert body["detail"]["error"] == "feature_disabled"


def test_run_blocked_when_anthropic_key_missing(
    admin_test_client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BET_AGENT_ENABLED", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import io
    files = {
        "arquitectura": ("arq.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"),
    }
    data = {"brief_json": "{}"}
    r = admin_test_client.post("/api/admin/bet-agent/run", files=files, data=data)
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "anthropic_key_missing"


def test_run_rejects_invalid_brief_json(admin_test_client: TestClient,
                                        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BET_AGENT_ENABLED", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-FAKE-FOR-TEST-ONLY")
    import io
    files = {
        "arquitectura": ("arq.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf"),
    }
    data = {"brief_json": "not-json"}
    r = admin_test_client.post("/api/admin/bet-agent/run", files=files, data=data)
    assert r.status_code == 400
    assert "brief_json inválido" in r.json()["detail"] or "inválido" in r.json()["detail"]


def test_costs_endpoint_empty_safe(admin_test_client: TestClient) -> None:
    r = admin_test_client.get("/api/admin/bet-agent/costs")
    # Mongo collection é vazia em CI → resposta válida com runs_count=0 ou valor baixo.
    assert r.status_code == 200
    body = r.json()
    assert "runs_count" in body
    assert "total_eur" in body
    assert "runs" in body


def test_runs_list_endpoint(admin_test_client: TestClient) -> None:
    r = admin_test_client.get("/api/admin/bet-agent/runs?limit=5")
    assert r.status_code == 200
    assert "runs" in r.json()


def test_run_detail_404_for_unknown_id(admin_test_client: TestClient) -> None:
    r = admin_test_client.get("/api/admin/bet-agent/runs/non-existent-run-id")
    assert r.status_code == 404
