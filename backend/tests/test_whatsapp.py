"""Botão WhatsApp da empresa (gerente e colaboradores): normalização dos números, escolha por sítio e API.

Execução isolada: MongoDB simulada (mongomock_motor), nenhuma chamada de rede.
"""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")
os.environ.setdefault("FRONTEND_URL", "https://example.test")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines import whatsapp as wa  # noqa: E402


def test_normalizar_telefone():
    assert wa.normalizar_telefone("912 345 678") == "351912345678"
    assert wa.normalizar_telefone("+351 912-345-678") == "351912345678"
    assert wa.normalizar_telefone("00351912345678") == "351912345678"
    assert wa.normalizar_telefone("06 12 34 56 78", "33") == "33612345678"
    assert wa.normalizar_telefone("+33 6 12 34 56 78") == "33612345678"
    for mau in ("", "abc", "123", "+0123456789", "91234567a"):
        assert wa.normalizar_telefone(mau) is None, mau


def test_validar_e_publicos_por_sitio():
    erro, _ = wa.validar([{"nome": "Rui", "telefone": "12"}])
    assert erro and "Rui" in erro
    erro, cs = wa.validar([{"nome": "Ana Gerente", "funcao": "Gerente", "telefone": "912345678", "locais": {"pagina": True, "orcamentos": True}},
                           {"nome": "Rui", "telefone": "+351 913 000 000", "locais": {"portal": True, "operarios": True, "xpto": True}},
                           {"nome": "Duplicado", "telefone": "00351912345678", "locais": {"pagina": True}},
                           {"nome": "", "telefone": "912345678"}])
    assert erro is None and [c["nome"] for c in cs] == ["Ana Gerente", "Rui"] and cs[0]["telefone"] == "+351912345678"
    assert set(cs[1]["locais"]) == set(wa.LOCAIS)
    cfg = {"ativo": True, "contactos": cs}
    pag = wa.publicos(cfg, "pagina", "Construtora X")
    assert [c["nome"] for c in pag] == ["Ana Gerente"] and pag[0]["link"].startswith("https://wa.me/351912345678?text=")
    assert "Construtora%20X" in pag[0]["link"]
    assert [c["nome"] for c in wa.publicos(cfg, "portal", ref="CP-1")] == ["Rui"]
    assert wa.publicos({**cfg, "ativo": False}, "pagina") == []          # desativado: nada é mostrado
    assert wa.publicos(None, "pagina") == [] and wa.publicos(cfg, "outro") == []


@pytest.fixture()
def api(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_wa"]
    from routes import company_page, portal, whatsapp
    for mod in (whatsapp, company_page, portal):
        monkeypatch.setattr(mod, "db", db)

    async def seed():
        await db.users.insert_many([
            {"user_id": "u_owner", "name": "Ana Silva", "phone": "912345678", "email": "ana@x.pt", "public_slug": "construtora-x",
             "public_published": True, "brand_company_name": "Construtora X"},
            {"user_id": "u_worker", "name": "Rui Operário", "role": "worker", "employer_id": "u_owner", "poste": "Encarregado", "phone": "913000000"},
            {"user_id": "u_outro", "name": "Outra empresa", "phone": "914000000"}])
    asyncio.run(seed())
    users = {"u_owner": {"user_id": "u_owner", "role": "user"}, "u_worker": {"user_id": "u_worker", "role": "worker", "employer_id": "u_owner"},
             "u_outro": {"user_id": "u_outro", "role": "user"}}

    async def fake_user(request: Request):
        u = users.get(request.headers.get("X-User") or "")
        if not u:
            raise HTTPException(401, "Não autenticado")
        return u

    from core import security
    app = FastAPI()
    app.include_router(whatsapp.router, prefix="/api")
    app.include_router(company_page.router, prefix="/api")
    app.dependency_overrides[security.current_user] = fake_user
    c = TestClient(app)
    c.db = db
    return c


def test_api_configurar_e_mostrar(api):
    h = {"X-User": "u_owner"}
    v = api.get("/api/company/whatsapp", headers=h).json()
    assert not v["ativo"] and {s["nome"] for s in v["sugestoes"]} == {"Ana Silva", "Rui Operário"}   # só a sua equipa
    assert next(s for s in v["sugestoes"] if s["nome"] == "Ana Silva")["funcao"] == "Gerente"
    # antes de configurar: a página pública não mostra números
    assert api.get("/api/public/company/construtora-x").json()["whatsapp"] == []
    body = {"ativo": True, "contactos": [
        {"nome": "Ana Silva", "funcao": "Gerente", "telefone": "912345678", "user_id": "u_owner", "locais": {"pagina": True, "orcamentos": True, "portal": True}},
        {"nome": "Rui Operário", "funcao": "Encarregado", "telefone": "913000000", "user_id": "u_worker", "locais": {"operarios": True, "portal": True}}]}
    r = api.put("/api/company/whatsapp", json=body, headers=h)
    assert r.status_code == 200 and r.json()["ativo"]
    pub = api.get("/api/public/company/construtora-x").json()["whatsapp"]
    assert [c["nome"] for c in pub] == ["Ana Silva"] and "wa.me/351912345678" in pub[0]["link"]
    eq = api.get("/api/company/whatsapp/equipa", params={"ref": "CP-1"}, headers={"X-User": "u_worker"}).json()["itens"]
    assert [c["nome"] for c in eq] == ["Rui Operário"]
    # o operário e outra empresa não alteram nem veem a configuração
    assert api.get("/api/company/whatsapp", headers={"X-User": "u_worker"}).status_code == 403
    assert api.get("/api/company/whatsapp", headers={"X-User": "u_outro"}).json()["contactos"] == []
    assert api.put("/api/company/whatsapp", json={"contactos": [{"nome": "X", "telefone": "1"}]}, headers=h).status_code == 422
