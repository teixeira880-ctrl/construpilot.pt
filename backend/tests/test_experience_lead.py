"""ConstruPilot Experience : criação da oportunidade a partir do diagnóstico público.

Execução isolada : MongoDB simulada (mongomock_motor), e-mail simulado (nenhuma chamada de rede).
"""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

BODY = {"name": "Ana Teste", "company": "Obras Teste Lda", "email": "Ana@Example.com", "lang": "pt", "demo": True,
        "goal": "Ver medições", "consent": True, "role": "reno", "role_label": "Especialista em remodelação",
        "team": "2-5", "decision": "decide", "urgency": "now",
        "needs": [{"id": "estimation_1", "label": "Orçamentos rápidos"}],
        "priority": {"id": "estimation_1", "label": "Orçamentos rápidos"},
        "answers": {"Quantos orçamentos preparas por mês?": "12"},
        "estimate": {"scenario_pct": 60, "hours_month_today": 72, "hours_month_saved": 43.2, "value_month_eur": 1080},
        "elapsed_ms": 60000, "submission_id": "sub-1"}


@pytest.fixture()
def env(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_experience"]
    from core.rate_limit import limiter
    from routes import experience
    monkeypatch.setattr(experience, "db", db)
    monkeypatch.delenv("EXPERIENCE_LEAD_EMAILS", raising=False)
    monkeypatch.setattr(limiter, "enabled", False)
    sent = []
    from engines import emailer

    async def _mail(to, subject, html, reply_to=None, from_name=None):
        sent.append({"to": to, "subject": subject, "html": html, "reply_to": reply_to})
        return {"ok": True}
    monkeypatch.setattr(emailer, "send_email", _mail)
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(experience.router, prefix="/api")
    return TestClient(app), db, sent, experience


def leads(db):
    return asyncio.run(db.commercial_leads.find({}, {"_id": 0}).to_list(50))


def test_creates_opportunity_and_notifies_both_mailboxes(env):
    c, db, sent, _ = env
    r = c.post("/api/experience/lead", json=BODY)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["lead_id"].startswith("lead_")
    (d,) = leads(db)
    assert d["source"] == "experience" and d["status"] == "demo_requested" and d["email"] == "ana@example.com"
    assert d["consent"]["given"] and d["consent"]["at"] and d["retain_until"] > d["created_at"]
    # 3 (72 h) + 3 (já) + 2 (adequação) + 3 (decide) + 0 (orçamento) + 3 (demonstração)
    assert d["score"]["total"] == 14 and d["score"]["suggest_qualified"]
    assert [m["to"] for m in sent] == ["info@construpilot.pt", "info@construpilot.fr"]
    assert sent[0]["reply_to"] == "ana@example.com" and "Obras Teste Lda" in sent[0]["html"]
    # leitura rápida: tipo de pedido, quem, pontuação e valor estão no assunto e no topo do e-mail
    assert sent[0]["subject"].startswith("[Experience] DEMO ATÉ ") and sent[0]["subject"].endswith("· Demonstração pedida · Obras Teste Lda · Especialista em remodelação · 14/18")
    h = sent[0]["html"]
    assert "DEMONSTRAÇÃO PEDIDA" in h and "Responder a Ana" in h and "mailto:ana@example.com" in h
    assert "1\u202f080\u00a0€" in h and "Prioridade alta" in h and "★ Orçamentos rápidos" in h
    assert h.index("DEMONSTRAÇÃO PEDIDA") < h.index("Próximo passo") < h.index("Todas as respostas")
    assert d["notified"] == ["info@construpilot.pt", "info@construpilot.fr"]


def test_report_only_status_and_html_is_escaped(env):
    c, db, sent, _ = env
    r = c.post("/api/experience/lead", json={**BODY, "demo": False, "company": "<script>x</script>", "submission_id": "s2"})
    assert r.status_code == 200
    assert leads(db)[0]["status"] == "discovery_completed"
    assert "RELATÓRIO PEDIDO" in sent[0]["html"] and "Relatório pedido" in sent[0]["subject"]
    assert "<script>" not in sent[0]["html"] and "&lt;script&gt;" in sent[0]["html"]


def test_consent_is_required_and_nothing_is_stored(env):
    c, db, sent, _ = env
    r = c.post("/api/experience/lead", json={**BODY, "consent": False})
    assert r.status_code == 422 and not leads(db) and not sent


def test_invalid_email_and_role_rejected(env):
    c, db, _, _ = env
    assert c.post("/api/experience/lead", json={**BODY, "email": "mau"}).status_code == 422
    assert c.post("/api/experience/lead", json={**BODY, "role": "hacker"}).status_code == 422
    assert not leads(db)


def test_spam_is_dropped_silently(env):
    c, db, sent, _ = env
    assert c.post("/api/experience/lead", json={**BODY, "website": "http://spam"}).json()["ok"]
    assert c.post("/api/experience/lead", json={**BODY, "elapsed_ms": 300}).json()["ok"]
    assert not leads(db) and not sent


def test_duplicate_within_24h_is_not_stored_twice(env):
    c, db, sent, _ = env
    first = c.post("/api/experience/lead", json=BODY).json()
    again = c.post("/api/experience/lead", json={**BODY, "submission_id": "other"}).json()
    assert again["duplicate"] and again["lead_id"] == first["lead_id"]
    assert len(leads(db)) == 1 and len(sent) == 2


def test_lead_is_kept_when_email_fails(env, monkeypatch):
    c, db, _, _ = env
    from engines import emailer

    async def _boom(*a, **k):
        raise RuntimeError("RESEND_API_KEY em falta")
    monkeypatch.setattr(emailer, "send_email", _boom)
    assert c.post("/api/experience/lead", json=BODY).status_code == 200
    assert leads(db)[0]["notified"] == []


def test_recipients_can_be_overridden(env, monkeypatch):
    _, _, _, experience = env
    monkeypatch.setenv("EXPERIENCE_LEAD_EMAILS", "a@x.pt, b@y.fr ,lixo")
    assert experience.recipients() == ["a@x.pt", "b@y.fr"]


def test_admin_list_requires_authentication(env):
    c, _, _, _ = env
    assert c.get("/api/experience/leads").status_code in (401, 403)


def test_owner_profile_scores_decision_and_stake(env):
    c, db, _, _ = env
    body = {**BODY, "role": "owner", "decision": "", "demo": False, "submission_id": "s9",
            "estimate": {"scenario_pct": 60, "at_stake_eur": 30000}}
    assert c.post("/api/experience/lead", json=body).status_code == 200
    d = leads(db)[0]
    assert d["score"]["has_estimate"] and {r["criterion"]: r["points"] for r in d["score"]["rows"]}["decision_authority"] == 3


def test_business_days_skip_weekends():
    from datetime import datetime, timezone
    from routes.experience import add_business_days
    wed = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)   # quarta-feira
    assert add_business_days(wed, 5).date().isoformat() == "2026-11-18"
    fri = datetime(2026, 11, 13, 18, 0, tzinfo=timezone.utc)  # sexta-feira
    assert add_business_days(fri, 5).date().isoformat() == "2026-11-20"
    sat = datetime(2026, 11, 14, 9, 0, tzinfo=timezone.utc)   # sábado
    assert add_business_days(sat, 1).date().isoformat() == "2026-11-16"


def test_now_plus_demo_commits_to_a_working_demo_in_5_business_days(env):
    from datetime import datetime
    c, db, sent, experience = env
    r = c.post("/api/experience/lead", json=BODY).json()
    d = leads(db)[0]
    assert d["next_action"] == "deliver_demo" and d["demo_due_at"] == d["follow_up_at"] == r["demo_due_at"]
    created, due = datetime.fromisoformat(d["created_at"]), datetime.fromisoformat(d["demo_due_at"])
    assert due == experience.add_business_days(created, 5) and due.weekday() < 5
    assert "5 dias úteis" in r["message"]
    h = sent[0]["html"]
    assert "Compromisso · 5 dias úteis" in h and "Demo funcional até" in h and due.strftime("%d/%m/%Y") in h
    assert h.index("Compromisso · 5 dias úteis") < h.index("Próximo passo")


def test_no_commitment_without_now_or_without_demo(env):
    c, db, sent, _ = env
    a = c.post("/api/experience/lead", json={**BODY, "urgency": "q", "submission_id": "a", "email": "a@example.com"}).json()
    b = c.post("/api/experience/lead", json={**BODY, "demo": False, "submission_id": "b", "email": "b@example.com"}).json()
    assert a["demo_due_at"] is None and b["demo_due_at"] is None and "2 dias úteis" in a["message"]
    assert all(d["demo_due_at"] is None for d in leads(db))
    assert all("Compromisso · 5 dias úteis" not in m["html"] and "DEMO ATÉ" not in m["subject"] for m in sent)
