"""14/11 (Martinho): contas de testes e do stand Web Summit apagadas; empresa fictícia Teste Websummit mantida mas fora das
contas oficiais; telefone obrigatório em todas as contas (validação de formato, sem SMS)."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from core import demo_accounts as DA
from core.phone import normalizar


def test_telefone_normalizado_e_invalidos_recusados():
    assert normalizar("912 345 678", "pt") == "+351912345678"
    assert normalizar("+351 912-345-678") == "+351912345678"
    assert normalizar("0033 6 12 34 56 78") == "+33612345678"
    assert normalizar("06 12 34 56 78", "fr") == "+33612345678"
    assert normalizar("+44 7700 900123") == "+447700900123"
    for mau in ("", None, "abc", "12345", "+12", "9123456789012345678"):
        with pytest.raises(ValueError):
            normalizar(mau, "pt")


def test_registo_exige_telefone():
    from pydantic import ValidationError
    from routes.auth import RegisterIn
    with pytest.raises(ValidationError):
        RegisterIn(name="A", email="a@b.pt", password="abcdef")
    assert RegisterIn(name="A", email="a@b.pt", password="abcdef", phone="912345678").phone == "912345678"


def test_contas_sem_telefone_tem_de_o_indicar_exceto_demo():
    from routes.auth import _public
    assert _public({"user_id": "u", "email": "x@y.pt"})["phone_required"] is True
    assert _public({"user_id": "u", "email": "x@y.pt", "phone": "+351912345678"})["phone_required"] is False
    assert _public({"user_id": "u", "email": "trolha01@tws.construpilot.pt", "is_demo": True})["phone_required"] is False


def _db(monkeypatch):
    db = AsyncMongoMockClient()["t"]
    import core.account_purge as AP
    monkeypatch.setattr(AP, "db", db)
    users = [
        {"user_id": "own", "email": "teste.websummit@construpilot.pt", "organization_id": "org1"},
        {"user_id": "t1", "email": "trolha01@tws.construpilot.pt", "employer_id": "own"},
        {"user_id": "c1", "email": "familia.martins@clientes.tws.construpilot.pt"},
        {"user_id": "j1", "email": "jetable76-63c361ac@test.fr"},
        {"user_id": "j2", "email": "x@example.com"},
        {"user_id": "s1", "email": "demo.websummit@construpilot.pt"},
        {"user_id": "s2", "email": "demo.websummit.particular@construpilot.pt"},
        {"user_id": "real", "email": "info@leveldesire.com"},
        {"user_id": "clt", "email": "clt-rezult.demo@construpilot.pt"},
        {"user_id": "adm", "email": "admin@test.fr", "role": "admin"},
    ]

    async def go():
        await db.users.insert_many(users)
        await db.projects.insert_many([{"user_id": "j1", "name": "teste"}, {"user_id": "real", "name": "obra real"}])
    asyncio.run(go())
    return db


def test_apaga_so_testes_e_stand_uma_vez(monkeypatch):
    monkeypatch.delenv("WEBSUMMIT_DEMO_EMAIL_PT", raising=False)
    monkeypatch.delenv("WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT", raising=False)
    db = _db(monkeypatch)
    dry = asyncio.run(DA.purge_test_and_stand(db, dry_run=True))
    assert sorted(dry["accounts"]) == sorted(["jetable76-63c361ac@test.fr", "x@example.com", "demo.websummit@construpilot.pt",
                                              "demo.websummit.particular@construpilot.pt"])
    out = asyncio.run(DA.purge_test_and_stand(db))
    assert out["deleted_accounts"] == 4
    restantes = {u["email"] for u in asyncio.run(db.users.find({}).to_list(100))}
    assert {"info@leveldesire.com", "clt-rezult.demo@construpilot.pt", "admin@test.fr", "trolha01@tws.construpilot.pt",
            "teste.websummit@construpilot.pt"} <= restantes
    assert asyncio.run(db.projects.count_documents({"user_id": "j1"})) == 0          # dados da conta apagada também
    assert asyncio.run(db.projects.count_documents({"user_id": "real"})) == 1
    assert asyncio.run(DA.purge_test_and_stand(db))["status"] == "already_done"      # nunca corre duas vezes


def test_empresa_ficticia_marcada_e_fora_das_contas_oficiais(monkeypatch):
    db = _db(monkeypatch)
    assert asyncio.run(DA.mark_demo(db)) == 3
    oficiais = {u["email"] for u in asyncio.run(db.users.find(DA.NOT_DEMO).to_list(100))}
    assert "trolha01@tws.construpilot.pt" not in oficiais and "teste.websummit@construpilot.pt" not in oficiais
    assert "info@leveldesire.com" in oficiais
    assert DA.is_demo_email("trolha50@tws.construpilot.pt") and not DA.is_demo_email("cliente@gmail.com")
