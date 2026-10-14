"""Testes do rate-limit e proteção de autenticação (Lote N5)."""

import os

import pytest
from fastapi.testclient import TestClient

# Ativa o limiter mesmo em testes
os.environ["RATE_LIMIT_ENABLED"] = "1"


@pytest.fixture(scope="module")
def client():
    from server import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_limiter():
    from core.rate_limit import limiter
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001
        pass
    yield


def test_diagnostico_e_publico_200(client):
    r = client.post("/api/particulares/autorizacao/diagnostico",
                    json={"tipo_obra": "moradia_nova"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_memoria_preview_exige_auth(client):
    r = client.post("/api/particulares/autorizacao/memoria/preview",
                    json={"respostas": {"tipo_obra": "moradia_nova"}, "diagnostico": {}})
    assert r.status_code == 401


def test_dossier_gerar_exige_auth(client):
    r = client.post("/api/particulares/autorizacao/dossier/gerar",
                    json={"respostas": {"tipo_obra": "moradia_nova"}, "diagnostico": {}})
    assert r.status_code == 401


def test_subscricao_pedir_exige_auth(client):
    r = client.post("/api/particulares/autorizacao/subscricao/pedir",
                    json={"tecnico_id": "x", "dossier": {}})
    assert r.status_code == 401


def test_rate_limit_diagnostico_30h(client):
    # 30 OK; a 31ª deve devolver 429
    last_status = 200
    for i in range(31):
        r = client.post("/api/particulares/autorizacao/diagnostico",
                        json={"tipo_obra": "muro", "subtipo_muro": "vedacao"})
        last_status = r.status_code
        if last_status == 429:
            break
    assert last_status == 429, f"Esperava 429 após 30 pedidos; último estado = {last_status}"


def test_tecnicos_devolve_catalogo_vazio_por_defeito(client):
    r = client.get("/api/particulares/autorizacao/tecnicos?especialidade=arquitetura")
    assert r.status_code == 200
    data = r.json()
    assert "tecnicos" in data
    # Em prod o JSON está vazio e a coleção Mongo também pode estar vazia
    if not data["tecnicos"]:
        assert data["catalogo_vazio"] is True


def test_guia_pepu_publico(client):
    r = client.get("/api/particulares/autorizacao/guia-pepu.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
