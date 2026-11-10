"""Discovery Engine — integração HTTP das rotas /api/connect (Mongo em memória, sem e-mails reais)."""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "construpilot_test")
os.environ.setdefault("JWT_SECRET", "connect-test-only")

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient
from slowapi.errors import RateLimitExceeded

from core import rate_limit
from core.security import admin_user
from routes import connect as RC

ADMIN = {"user_id": "adm", "email": "admin@construpilot.pt", "role": "admin"}
CLIENT_ANSWERS = {"activity": "general_contractor", "volume": {"quotes_per_month": "q6_15"},
                  "pains": ["p_quote_slow", "p_margins"], "deep": {"tools": "excel", "b_time": "h3_8"},
                  "urgency": "d30", "decision": "decide"}
CONTACT = {"name": "Rui Empreiteiro", "company": "Obras Rui Lda", "email": "rui@obrasrui.pt", "country": "Portugal",
           "channel": "phone", "next_step": "individual_demo", "privacy_ack": True}


@pytest.fixture
def ctx(monkeypatch):
    database = AsyncMongoMockClient().connect_test
    monkeypatch.setattr(RC, "db", database)
    monkeypatch.setattr(RC, "_indexes_ready", False)
    monkeypatch.setenv("CONNECT_ENABLED", "1")
    sent = []

    async def fake_send(to, subject, html, **kw):
        sent.append({"to": to, "subject": subject, "html": html})
        return {"id": "fake"}

    import engines.emailer as EM
    import engines.activity_crm.record as REC
    monkeypatch.setattr(EM, "send_email", fake_send)

    async def fake_record(**kw):
        return "x"
    monkeypatch.setattr(REC, "record_activity", fake_record)
    rate_limit.limiter.reset()

    app = FastAPI()
    app.state.limiter = rate_limit.limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit.rate_limit_exceeded_handler)
    app.include_router(RC.router, prefix="/api")
    state = {"admin": ADMIN}

    async def fake_admin():
        if state["admin"] is None:
            raise HTTPException(401, "Não autenticado")
        if state["admin"].get("role") != "admin":
            raise HTTPException(403, "Acesso de administrador necessário")
        return state["admin"]
    app.dependency_overrides[admin_user] = fake_admin
    with TestClient(app) as client:
        yield {"c": client, "db": database, "sent": sent, "state": state}


def _session(c, profile="client", **kw):
    r = c.post("/api/connect/sessions", json={"profile": profile, "lang": "pt", **kw})
    assert r.status_code == 200, r.text
    return r.json()


def _h(s):
    return {"X-Connect-Token": s["token"]}


def _wait():
    import time
    time.sleep(0.15)  # tarefas pós-submissão (asyncio.create_task)


def test_catalog_public_without_evidence(ctx):
    r = ctx["c"].get("/api/connect/catalog")
    assert r.status_code == 200
    assert all("evidence" not in c for c in r.json()["capabilities"])


def test_feature_flag_disables_everything(ctx, monkeypatch):
    monkeypatch.setenv("CONNECT_ENABLED", "0")
    c = ctx["c"]
    assert c.get("/api/connect/catalog").status_code == 404
    assert c.post("/api/connect/sessions", json={"profile": "client"}).status_code == 404
    assert c.get("/api/connect/admin/leads").status_code == 404
    assert c.get("/api/connect/status").json() == {"enabled": False}


def test_feature_flag_defaults_to_pt_market_only(monkeypatch):
    monkeypatch.delenv("CONNECT_ENABLED", raising=False)
    monkeypatch.setenv("CP_MARKET", "fr")
    assert RC.connect_enabled() is False
    monkeypatch.setenv("CP_MARKET", "pt")
    assert RC.connect_enabled() is True


def test_full_client_journey_creates_scored_lead(ctx):
    c, db = ctx["c"], ctx["db"]
    s = _session(c, source="websummit2026", utm_campaign="stand-qr")
    r = c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS, "step": 6}, headers=_h(s))
    assert r.status_code == 200 and r.json()["complete"] is True
    rec = r.json()["recommendation"]
    assert rec["demo"] == "demo_quote" and rec["process"]["current"] == "excel"
    assert c.post(f"/api/connect/sessions/{s['session_id']}/demo", json={"demo_id": "demo_quote", "event": "completed", "step": 6},
                  headers=_h(s)).status_code == 200
    r = c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s))
    assert r.status_code == 200 and r.json()["created"] is True
    _wait()
    lead = c.get("/api/connect/admin/leads").json()["items"][0]
    assert lead["priority"] == "high" and lead["stage"] == "demo_requested" and lead["source"] == "websummit2026"
    assert lead["owner"] == "Diana Araujo" and lead["open_tasks"] >= 1 and lead["next_contact_at"]
    detail = c.get(f"/api/connect/admin/leads/{lead['lead_id']}").json()
    assert "demo_quote" in detail["demos_viewed"]
    assert detail["consents"][0]["marketing"] is False
    assert "é decisor" in detail["score_detail"]["explanation"]
    assert detail["utm"]["campaign"] == "stand-qr"
    # e-mail transacional pedido (demonstração individual) + alerta ao responsável
    tos = sorted(m["to"] for m in ctx["sent"])
    assert tos == ["dianaaraujo@construpilot.pt", "rui@obrasrui.pt"]


def test_duplicate_submission_updates_same_lead_and_no_double_email(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    for _ in range(3):
        assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s)).status_code == 200
    _wait()
    assert c.get("/api/connect/admin/leads").json()["total"] == 1
    assert sum(1 for m in ctx["sent"] if m["to"] == "rui@obrasrui.pt") == 1
    # outra sessão com o mesmo e-mail e perfil, dentro de 30 dias → mesma oportunidade
    s2 = _session(c)
    c.put(f"/api/connect/sessions/{s2['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s2))
    assert c.post(f"/api/connect/sessions/{s2['session_id']}/contact", json=CONTACT, headers=_h(s2)).json()["created"] is False
    assert c.get("/api/connect/admin/leads").json()["total"] == 1


def test_teste5_other_visitor_cannot_read_result(ctx):
    c = ctx["c"]
    a, b = _session(c), _session(c)
    c.put(f"/api/connect/sessions/{a['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(a))
    assert c.get(f"/api/connect/sessions/{a['session_id']}", headers=_h(a)).status_code == 200
    assert c.get(f"/api/connect/sessions/{a['session_id']}", headers=_h(b)).status_code == 403
    assert c.get(f"/api/connect/sessions/{a['session_id']}").status_code == 403
    assert c.get("/api/connect/sessions/cs_inexistente123", headers=_h(a)).status_code == 403
    assert c.post(f"/api/connect/sessions/{a['session_id']}/contact", json=CONTACT, headers=_h(b)).status_code == 403


def test_session_ids_are_unpredictable(ctx):
    ids = {_session(ctx["c"])["session_id"] for _ in range(5)}
    assert len(ids) == 5 and all(len(i) > 20 for i in ids)


@pytest.mark.parametrize("bad", [
    {"activity": "hacker"}, {"pains": ["p_measure", "p_errors", "p_margins", "p_billing"]},
    {"pains": ["x"]}, {"deep": {"inexistente": "a"}}, {"deep": {"tools": "word"}},
    {"volume": {"quotes_per_month": "q999"}}, {"other_text": "x" * 501}, {"urgency": "ontem"},
])
def test_answers_strict_validation(ctx, bad):
    c = ctx["c"]
    s = _session(c)
    r = c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": {**CLIENT_ANSWERS, **bad}}, headers=_h(s))
    assert r.status_code == 422


def test_contact_validation_honeypot_and_incomplete(ctx):
    c = ctx["c"]
    s = _session(c)
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s)).status_code == 409
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "email": "nao-email"}, headers=_h(s)).status_code == 422
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "privacy_ack": False}, headers=_h(s)).status_code == 422
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "phone": "<script>"}, headers=_h(s)).status_code == 422
    r = c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "website_url": "http://spam"}, headers=_h(s))
    assert r.status_code == 200
    assert c.get("/api/connect/admin/leads").json()["total"] == 0


def test_contact_rate_limited(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    codes = [c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s)).status_code for _ in range(12)]
    assert 429 in codes


def test_explorer_without_request_gets_no_email(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers",
          json={"answers": {"activity": "homeowner", "pains": ["p_quantities"], "urgency": "exploring", "decision": "personal"}}, headers=_h(s))
    c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "next_step": "none"}, headers=_h(s))
    _wait()
    assert not [m for m in ctx["sent"] if m["to"] == "rui@obrasrui.pt"]
    lead = c.get("/api/connect/admin/leads").json()["items"][0]
    assert lead["priority"] == "low"


def test_teste4_investor_flow_public_only(ctx):
    c = ctx["c"]
    s = _session(c, profile="investor")
    ans = {"investor_type": "vc", "sectors": ["contech"], "stages": ["pre_seed", "seed"], "geos": ["pt", "eu"],
           "collab": "equity", "availability": "this_week", "organization": "Lisbon Ventures", "website": "https://lv.vc"}
    r = c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": ans}, headers=_h(s))
    assert r.json()["recommendation"]["profile"] == "investor"
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "next_step": "meeting"}, headers=_h(s)).status_code == 200
    _wait()
    lead = c.get("/api/connect/admin/leads?profile=investor").json()["items"][0]
    assert lead["stage"] == "meeting_requested" and lead["owner"] == "Ângelo Cunha"
    visitor_mail = next(m for m in ctx["sent"] if m["to"] == "rui@obrasrui.pt")
    assert "confidencial" in visitor_mail["html"] and "pitch" not in visitor_mail["html"].lower()


def test_partner_flow(ctx):
    c = ctx["c"]
    s = _session(c, profile="partner")
    ans = {"partner_type": "distributor", "kinds": ["distribution", "pilot"], "scale": "s50_500", "timeline": "quarter",
           "organization": "Materiais Norte"}
    r = c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": ans}, headers=_h(s))
    assert r.json()["recommendation"]["use_case"] == "cap_quote"
    assert c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "next_step": "meeting"}, headers=_h(s)).status_code == 200
    assert c.get("/api/connect/admin/leads?profile=partner").json()["items"][0]["stage"] == "meeting"


def test_admin_permissions(ctx):
    c, state = ctx["c"], ctx["state"]
    state["admin"] = None
    assert c.get("/api/connect/admin/leads").status_code == 401
    assert c.get("/api/connect/admin/dashboard").status_code == 401
    assert c.get("/api/connect/admin/export.csv").status_code == 401
    state["admin"] = {"user_id": "u", "role": "pro"}
    assert c.get("/api/connect/admin/leads").status_code == 403
    assert c.put("/api/connect/admin/settings", json={"retention_days": 90}).status_code == 403


def test_admin_crm_operations_and_audit(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s))
    lid = c.get("/api/connect/admin/leads").json()["items"][0]["lead_id"]
    assert c.patch(f"/api/connect/admin/leads/{lid}", json={"stage": "invested"}).status_code == 422  # etapa de investidor
    r = c.patch(f"/api/connect/admin/leads/{lid}", json={"stage": "demo_done", "owner": "Martinho Araujo",
                                                          "next_action": "Enviar proposta de piloto",
                                                          "next_contact_at": "2026-11-12T10:00:00Z"})
    assert r.status_code == 200 and r.json()["stage"] == "demo_done"
    assert c.post(f"/api/connect/admin/leads/{lid}/notes", json={"text": "Chamada feita", "type": "call"}).status_code == 200
    t = c.post(f"/api/connect/admin/leads/{lid}/tasks", json={"title": "Preparar piloto", "due_at": "2026-11-13T09:00:00Z"}).json()
    assert c.patch(f"/api/connect/admin/leads/{lid}/tasks/{t['task_id']}", json={"done": True}).json()["done"] is True
    assert c.post(f"/api/connect/admin/leads/{lid}/email", json={"template": "meeting_confirmation"}).status_code == 422
    assert c.post(f"/api/connect/admin/leads/{lid}/email", json={"template": "meeting_confirmation", "when": "12/11 15h"}).json()["ok"] is True
    assert c.post(f"/api/connect/admin/leads/{lid}/email", json={"template": "meeting_confirmation", "when": "12/11 15h"}).json()["ok"] is False
    rows = c.get("/api/connect/admin/leads?q=obras&stage=demo_done").json()
    assert rows["total"] == 1 and rows["items"][0]["owner"] == "Martinho Araujo"
    d = c.get(f"/api/connect/admin/leads/{lid}").json()
    assert d["first_response_at"] and len(d["activities"]) >= 4
    actions = {a["action"] for a in c.get(f"/api/connect/admin/audit?lead_id={lid}").json()}
    assert {"update", "note", "task_add", "task_update", "email", "view"} <= actions


def test_dashboard_uses_real_data_only(ctx):
    c = ctx["c"]
    empty = c.get("/api/connect/admin/dashboard").json()
    assert empty["diagnosis"]["started"] == 0 and empty["diagnosis"]["completion_rate"] is None
    s = _session(c, source="websummit2026")
    _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s))
    d = c.get("/api/connect/admin/dashboard").json()
    assert d["diagnosis"] == {"started": 2, "completed": 1, "completion_rate": 50.0, "converted_to_lead": 1}
    assert d["leads_by_source"] == {"websummit2026": 1}
    assert d["top_pains"] == {"p_quote_slow": 1, "p_margins": 1}


def test_csv_export_neutralises_formulas(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    c.post(f"/api/connect/sessions/{s['session_id']}/contact", json={**CONTACT, "company": "=HYPERLINK(\"x\")"}, headers=_h(s))
    r = c.get("/api/connect/admin/export.csv")
    assert r.status_code == 200 and "'=HYPERLINK" in r.content.decode("utf-8-sig")


def test_gdpr_anonymize(ctx):
    c = ctx["c"]
    s = _session(c)
    c.put(f"/api/connect/sessions/{s['session_id']}/answers", json={"answers": CLIENT_ANSWERS}, headers=_h(s))
    c.post(f"/api/connect/sessions/{s['session_id']}/contact", json=CONTACT, headers=_h(s))
    lid = c.get("/api/connect/admin/leads").json()["items"][0]["lead_id"]
    assert c.post(f"/api/connect/admin/leads/{lid}/anonymize", json={"confirm": False}).status_code == 422
    assert c.post(f"/api/connect/admin/leads/{lid}/anonymize", json={"confirm": True}).status_code == 200
    d = c.get(f"/api/connect/admin/leads/{lid}").json()
    assert d["contact"]["email"] == "" and d["anonymized"] is True
    assert c.post(f"/api/connect/admin/leads/{lid}/email", json={"template": "follow_up", "note": "x"}).status_code == 409


def test_events_only_stored_with_consent(ctx):
    c, db = ctx["c"], ctx["db"]
    s = _session(c)
    assert c.post(f"/api/connect/sessions/{s['session_id']}/events", json={"name": "demo_started"}, headers=_h(s)).json()["stored"] is False
    assert c.post(f"/api/connect/sessions/{s['session_id']}/events", json={"name": "demo_started", "analytics_consent": True},
                  headers=_h(s)).json()["stored"] is True
    assert c.post(f"/api/connect/sessions/{s['session_id']}/events", json={"name": "email=a@b.c", "analytics_consent": True},
                  headers=_h(s)).status_code == 422


def test_demo_compute_endpoint(ctx):
    c = ctx["c"]
    r = c.post("/api/connect/demo/demo_takeoff/compute", json={"params": {"calibration_real_m": 5}})
    assert r.status_code == 200 and r.json()["takeoff"]["room"]["surface_m2"] == 15.96
    assert c.post("/api/connect/demo/demo_takeoff/compute", json={"params": {"calibration_real_m": 1e9}}).status_code == 422
    assert c.post("/api/connect/demo/demo_billing/compute", json={}).status_code == 422
    q = c.post("/api/connect/demo/demo_margin/compute", json={"params": {"lines": {"parquet": {"cost_price_ht": 35}}}}).json()
    assert q["quote"]["totals"]["margin_pct"] < 31.5


def test_settings_validation(ctx):
    c = ctx["c"]
    assert c.put("/api/connect/admin/settings", json={"scoring": {"thresholds": {"high": 40, "medium": 60}}}).status_code == 422
    r = c.put("/api/connect/admin/settings", json={"owners": {"investor": {"name": "Ângelo Cunha", "email": "angelo@construpilot.pt"}}})
    assert r.status_code == 200 and r.json()["owners"]["investor"]["email"] == "angelo@construpilot.pt"
    assert r.json()["owners"]["client"]["name"] == "Diana Araujo"
