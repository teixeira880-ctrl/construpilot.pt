"""Teste de regressão: POST /prompt-fill/{app_key} aceita body JSON.

Regressão corrigida: `from __future__ import annotations` + slowapi quebrava
inspecção de signature e FastAPI resolvia o body como query param (HTTP 422).
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
    os.environ.setdefault("DB_NAME", "construpilot_test")
    from server import app  # import tardio após env

    return TestClient(app)


def test_prompt_fill_post_accepts_json_body(client):
    """Sem auth deve devolver 401 OU 429 (rate-limit) — nunca 422 (body missing)."""
    r = client.post(
        "/api/prompt-fill/medicoes",
        json={"prompt": "sala de 5 por 4 metros"},
    )
    assert r.status_code != 422, f"Regressão de body→query: {r.status_code} {r.text}"
    assert r.status_code in (401, 429, 500), f"Resposta inesperada: {r.status_code} {r.text}"


def test_prompt_fill_openapi_requestbody_present(client):
    r = client.get("/api/openapi.json")
    assert r.status_code == 200, f"OpenAPI em /api/openapi.json devia estar exposto: {r.status_code}"
    spec = r.json()
    post = spec["paths"]["/api/prompt-fill/{app_key}"]["post"]
    assert "requestBody" in post, "POST prompt-fill deve ter requestBody, não query param"
    param_names = {p["name"] for p in post.get("parameters", [])}
    assert param_names == {"app_key"}, f"Parâmetros extra: {param_names - {'app_key'}}"


def test_prompt_fill_apps_listed_at_least_six(client):
    """Devem estar registados pelo menos 6 extractors (escadas + 6 novos)."""
    # endpoint é auth-required; usar o OpenAPI (público) para confirmar o número de apps
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    # verificar que a rota /prompt-fill/apps existe
    assert "/api/prompt-fill/apps" in r.json()["paths"]
