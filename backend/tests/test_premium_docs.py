"""Lot 44 : les documents haut de gamme sont servis par /brochures (admin, ou sans en-tête client)."""
import os

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_premium_docs")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import core.security as S  # noqa: E402
from engines import premium_docs  # noqa: E402
from routes import brochures as B  # noqa: E402

ADMIN = {"user_id": "u_admin", "role": "admin"}
PRO = {"user_id": "u_pro", "role": "user", "account_type": "pro"}


def client(user):
    app = FastAPI()
    app.include_router(B.router, prefix="/api")
    app.dependency_overrides[S.current_user] = lambda: user
    app.dependency_overrides[S.admin_user] = lambda: user
    return TestClient(app)


@pytest.mark.parametrize("lang", ["fr", "pt", "en"])
def test_files_present(lang):
    for kind, ext in (("investor", "pdf"), ("investor", "pptx"), ("client", "pptx"), ("plaquette", "pdf")):
        assert premium_docs.available(kind, lang, ext), (kind, lang, ext)


@pytest.mark.parametrize("lang", ["fr", "pt", "en"])
def test_investor_served_static(lang):
    c = client(ADMIN)
    for ext, magic in (("pdf", b"%PDF"), ("pptx", b"PK")):
        r = c.get(f"/api/brochures/investisseurs.{ext}", params={"lang": lang})
        assert r.status_code == 200 and r.content[:4].startswith(magic)
        assert premium_docs.DOWNLOAD[lang]["investor"] in r.headers["content-disposition"]


def test_admin_gets_premium_plaquette_and_deck():
    c = client(ADMIN)
    r = c.get("/api/brochures/plaquette.pdf", params={"lang": "fr"})
    assert r.status_code == 200 and "ConstruPilot_Plaquette_FR" in r.headers["content-disposition"]
    r = c.get("/api/brochures/plaquette.pptx", params={"lang": "pt"})
    assert r.status_code == 200 and "ConstruPilot_Apresentacao-comercial_PT" in r.headers["content-disposition"]


def test_unbranded_pro_gets_premium():
    r = client(PRO).get("/api/brochures/plaquette.pdf", params={"lang": "en", "branded": "false"})
    assert r.status_code == 200 and "ConstruPilot_Brochure_EN" in r.headers["content-disposition"]


def test_bad_lang_rejected():
    assert client(ADMIN).get("/api/brochures/investisseurs.pdf", params={"lang": "de"}).status_code == 422
