"""Visto do engenheiro sobre o anteprojeto do autopiloto BET (.pt) — porta do «visa BET» francês, coleções em memória."""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_bet_visto")
os.environ.setdefault("JWT_SECRET", "test")

M = pytest.importorskip("routes.structuro_bet_visto")
from fastapi import HTTPException  # noqa: E402



class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: d.get(key) or "", reverse=direction == -1)
        return self

    async def to_list(self, n):
        return self.docs[:n]


class _Coll:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _match(d, q):
        return all(d.get(k) == v for k, v in q.items())

    async def insert_one(self, d):
        self.docs.append(dict(d))

    async def find_one(self, q, proj=None, **kw):
        d = next((d for d in self.docs if self._match(d, q)), None)
        return dict(d) if d else None

    def find(self, q, proj=None):
        return _Cur([dict(d) for d in self.docs if self._match(d, q)])

    async def update_one(self, q, upd, **kw):
        for d in self.docs:
            if self._match(d, q):
                d.update(upd.get("$set") or {})
                return

    async def delete_many(self, q):
        self.docs = [d for d in self.docs if not self._match(d, q)]


class _DB:
    def __init__(self):
        self.bet_dossiers, self.bet_vistos, self.structuro_calculations, self.users = _Coll(), _Coll(), _Coll(), _Coll()


@pytest.fixture
def env(monkeypatch):
    db = _DB()
    monkeypatch.setattr(M, "db", db)
    monkeypatch.setattr(M, "build_coffrage_pdf", lambda *a, **k: b"%PDF-1.4 cofragem")
    monkeypatch.setattr(M.autopilot, "element_marks", lambda model: {})
    sent = []

    async def fake_send(to, subject, html, **kw):
        sent.append((to, subject))
        return {"ok": True}

    import engines.emailer as em
    monkeypatch.setattr(em, "send_email", fake_send)
    db.users.docs.append({"user_id": "u1", "email": "pro@exemplo.pt", "company": "Construções Exemplo, Lda."})
    db.bet_dossiers.docs.append({"dossier_id": "d1", "user_id": "u1", "title": "Moradia exemplo",
                                 "autopilot": {"calc_study_id": "s1", "summary": {"total_elements": 42, "n_footings": 8},
                                               "soil": {"q_confirmed": True}}})
    db.bet_dossiers.docs.append({"dossier_id": "d2", "user_id": "u1", "title": "Sem anteprojeto"})
    db.structuro_calculations.docs.append({"study_id": "s1", "user_id": "u1", "model": {"title": "Moradia"}, "revision": 2})
    return db, sent


def _run(c):
    return asyncio.run(c)


U = {"user_id": "u1"}


def test_visto_fluxo(env):
    db, sent = env
    with pytest.raises(HTTPException) as e:
        _run(M.pedir_visto("d2", M.VistoPedidoIn(engineer_name="Eng. Exemplo", engineer_email="eng@exemplo.pt"), U))
    assert e.value.status_code == 422 and "anteprojeto" in e.value.detail
    r = _run(M.pedir_visto("d1", M.VistoPedidoIn(engineer_name="Eng. Exemplo", engineer_email="eng@exemplo.pt"), U))
    assert r["email_sent"] and sent[0][0] == "eng@exemplo.pt" and r["share_url"].startswith("/visto-bet/")
    token = r["share_url"].rsplit("/", 1)[-1]
    pub = _run(M.ver_visto(token))
    assert pub["status"] == "pendente" and pub["summary"]["total_elements"] == 42 and pub["soil_confirmed"] is True
    assert "termo de responsabilidade" in pub["reserva"] and "token" not in pub
    pdf = _run(M.visto_pdf(token))
    assert pdf.body.startswith(b"%PDF") and "Anteprojeto-BET" in pdf.headers["content-disposition"]
    with pytest.raises(HTTPException) as e:
        _run(M.assinar_visto(token, M.VistoAssinarIn(signatory="Eng. Exemplo", decision="recusar")))
    assert e.value.status_code == 422
    ok = _run(M.assinar_visto(token, M.VistoAssinarIn(signatory="Eng. Exemplo", ordem_numero="OE 00000", decision="visar")))
    assert ok["status"] == "visado"
    assert db.bet_dossiers.docs[0]["autopilot_visto"]["status"] == "visado"
    assert db.bet_dossiers.docs[0]["autopilot"]["calc_study_id"] == "s1"          # anteprojeto intacto
    with pytest.raises(HTTPException) as e:
        _run(M.assinar_visto(token, M.VistoAssinarIn(signatory="Outro", decision="visar")))
    assert e.value.status_code == 409
    got = _run(M.obter_visto("d1", U))["visto"]
    assert got["status"] == "visado" and got["ordem_numero"] == "OE 00000"


def test_novo_pedido_substitui_pendente(env):
    db, _ = env
    _run(M.pedir_visto("d1", M.VistoPedidoIn(engineer_name="Eng. A", engineer_email="a@exemplo.pt"), U))
    _run(M.pedir_visto("d1", M.VistoPedidoIn(engineer_name="Eng. B", engineer_email="b@exemplo.pt"), U))
    assert [v["engineer_name"] for v in db.bet_vistos.docs] == ["Eng. B"]
    with pytest.raises(HTTPException):
        _run(M.ver_visto("invalido"))
    with pytest.raises(HTTPException):
        _run(M.pedir_visto("d1", M.VistoPedidoIn(engineer_name="Eng. C", engineer_email="c@exemplo.pt"), {"user_id": "u2"}))
