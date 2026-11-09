"""Offre commerciale B2B 2026-11 : catalogue, limites, checkout, Enterprise, webhooks.

Exécution isolée : MongoDB simulée (mongomock_motor), Stripe simulé (aucun appel réseau).
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cp_test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-prod")

mm = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from engines import commercial_plans as cp  # noqa: E402

SOLO = {"user_id": "u_solo", "email": "solo@atelier.pt", "name": "Solo"}


def run(c):
    return asyncio.run(c)


@pytest.fixture()
def env(monkeypatch):
    db = mm.AsyncMongoMockClient()["t_commercial"]
    from engines import monetization, usage_meter
    from routes import commercial
    for mod in (monetization, usage_meter, commercial):
        monkeypatch.setattr(mod, "db", db)
    monkeypatch.delenv("FREE_PROMO_MODE", raising=False)
    monkeypatch.setenv("PLAN_LIMITS_MODE", "enforce")
    monkeypatch.setenv("CP_MARKET", "pt")
    return SimpleNamespace(db=db, monetization=monetization, usage=usage_meter, commercial=commercial)


async def _subscribe(db, user_id, plan_id, **extra):
    for d in cp.db_plan_docs():
        await db.plans.update_one({"plan_id": d["plan_id"]}, {"$setOnInsert": d}, upsert=True)
    await db.entitlements.insert_one({"user_id": user_id, "plan_id": plan_id, "status": "active",
                                      "kind": "subscription", "granted_at": datetime.now(timezone.utc).isoformat(),
                                      **extra})


# ------------------------------------------------------------------ catalogue & prix

def test_prix_publics_et_annuel_15pct():
    assert cp.price_cents("solo", "month") == 9900
    assert cp.price_cents("professional", "month") == 24900
    assert cp.price_cents("business", "month") == 59900
    assert cp.price_cents("solo", "year") == 100980          # 1 009,80 €
    assert cp.price_cents("professional", "year") == 253980  # 2 539,80 €
    assert cp.price_cents("business", "year") == 610980      # 6 109,80 €


def test_enterprise_sans_aucun_montant():
    with pytest.raises(ValueError):
        cp.price_cents("enterprise", "month")
    with pytest.raises(ValueError):
        cp.price_cents("enterprise", "year")
    cat = cp.public_catalog()
    ent = next(p for p in cat["plans"] if p["key"] == "enterprise")
    assert "price" not in ent and ent["checkout"] is False
    blob = json.dumps(ent)
    for forbidden in ("cents", "amount", "1499", "149900", "\"price\":"):
        assert forbidden not in blob
    assert not any(d["plan_id"].startswith("cp_enterprise") for d in cp.db_plan_docs())


def test_professional_mis_en_avant_et_limites():
    cat = {p["key"]: p for p in cp.public_catalog()["plans"]}
    assert [p["key"] for p in cp.public_catalog()["plans"]] == ["solo", "professional", "business", "enterprise"]
    assert cat["professional"]["highlight"] and not cat["solo"]["highlight"]
    assert cat["solo"]["limits"] == {"seats": 1, "active_projects": 10, "pages_monthly": 100,
                                      "storage_bytes": 10 * cp.GB}
    assert cat["business"]["limits"]["pages_monthly"] == 3000
    assert cat["enterprise"]["limits_are_reference"] is True
    assert cat["business"]["price"]["year_monthly_equiv_cents"] == 50915  # 509,15 €/mois


def test_ids_et_tiers_sans_collision_de_prefixe():
    for d in cp.db_plan_docs("fr"):
        assert not d["plan_id"].startswith("pro")
        assert d["lookup_key"].startswith("construpilot_fr_cp_")
        assert d["stripe_sync"] is False and d["tax_behavior"] == "exclusive"
        assert d["audience"] == "b2b"
    assert cp.tier_for_plan_id("cp_solo_monthly") == "pro"
    assert cp.tier_for_plan_id("cp_professional_yearly") == "pro_business"
    assert cp.tier_for_plan_id("cp_business_monthly") == "pro_business"
    # Plans historiques : comportement inchangé
    assert cp.tier_for_plan_id("pro_monthly") == "pro"
    assert cp.tier_for_plan_id("pro_business_yearly") == "pro_business"
    assert cp.tier_for_plan_id("premium_monthly") == "premium"
    assert cp.tier_for_plan_id("project_pass") == "project_pass"
    assert cp.limits_for_plan_id("pro_business_monthly") is None  # clients existants : pas de nouvelle limite
    assert cp.lookup_key("solo", "month", "pt") != cp.lookup_key("solo", "month", "fr")


def test_user_tier_nouveaux_plans(env):
    async def go():
        await _subscribe(env.db, "u1", "cp_professional_monthly")
        assert await env.monetization.user_tier("u1") == "pro_business"
        await _subscribe(env.db, "u2", "cp_solo_yearly")
        assert await env.monetization.user_tier("u2") == "pro"
    run(go())


def test_stripe_sync_ignore_les_nouveaux_plans(env, monkeypatch):
    created = []
    monkeypatch.setattr(env.monetization.stripe, "api_key", "sk_test_x")
    monkeypatch.setattr(env.monetization, "_index_existing_products", lambda: {})
    monkeypatch.setattr(env.monetization, "_upsert_product", lambda plan, ex: created.append(plan["plan_id"]) or SimpleNamespace(id="prod"))
    monkeypatch.setattr(env.monetization, "_upsert_price", lambda plan, prod: SimpleNamespace(id="price"))
    monkeypatch.delenv("COMMERCIAL_STRIPE_SYNC", raising=False)

    async def go():
        for d in cp.db_plan_docs():
            await env.db.plans.insert_one(dict(d))
        await env.db.plans.insert_one({"plan_id": "pro_monthly", "kind": "subscription", "active": True,
                                       "lookup_key": "construpilot_pro_monthly"})
        await env.monetization.ensure_stripe_catalog()
    run(go())
    assert created == ["pro_monthly"]


# ------------------------------------------------------------------ limites backend

def test_limite_projets_solo_enforce(env):
    async def go():
        await _subscribe(env.db, "u_solo", "cp_solo_monthly")
        for i in range(10):
            await env.db.projects.insert_one({"project_id": f"p{i}", "user_id": "u_solo", "status": "active"})
        await env.db.projects.insert_one({"project_id": "old", "user_id": "u_solo", "status": "archived"})
        with pytest.raises(Exception) as ei:
            await env.usage.check_new_project(SOLO)
        assert ei.value.status_code == 402 and ei.value.detail["resource"] == "active_projects"
        await env.db.projects.update_one({"project_id": "p0"}, {"$set": {"status": "archived"}})
        await env.usage.check_new_project(SOLO)  # repasse sous la limite
    run(go())


def test_mode_observe_ne_bloque_jamais(env, monkeypatch):
    monkeypatch.setenv("PLAN_LIMITS_MODE", "observe")

    async def go():
        await _subscribe(env.db, "u_solo", "cp_solo_monthly")
        for i in range(12):
            await env.db.projects.insert_one({"project_id": f"p{i}", "user_id": "u_solo", "status": "active"})
        await env.usage.check_new_project(SOLO)
        assert await env.db.usage_events.count_documents({"kind": "limit_would_block"}) == 1
    run(go())


def test_clients_historiques_jamais_brides(env):
    async def go():
        await env.db.entitlements.insert_one({"user_id": "u_old", "plan_id": "pro_business_monthly",
                                              "status": "active", "granted_at": "2026-01-01"})
        for i in range(300):
            await env.db.projects.insert_one({"project_id": f"p{i}", "user_id": "u_old", "status": "active"})
        await env.usage.check_new_project({"user_id": "u_old"})
        r = await env.usage.consume_pages({"user_id": "u_old"}, 5000, ref="plan_x")
        assert r["counted"] == 5000
    run(go())


def test_pages_idempotentes_et_plafond(env):
    async def go():
        await _subscribe(env.db, "u_solo", "cp_solo_monthly")
        assert (await env.usage.consume_pages(SOLO, 60, ref="plan_a"))["counted"] == 60
        assert (await env.usage.consume_pages(SOLO, 60, ref="plan_a")).get("duplicate")  # même import
        with pytest.raises(Exception) as ei:
            await env.usage.consume_pages(SOLO, 41, ref="plan_b")  # 60 + 41 > 100
        assert ei.value.status_code == 402 and ei.value.detail["resource"] == "pages_monthly"
        assert (await env.usage.consume_pages(SOLO, 40, ref="plan_c"))["counted"] == 40
        snap = await env.usage.snapshot(SOLO)
        assert snap["used"]["pages_monthly"] == 100 and snap["limits"]["pages_monthly"] == 100
        # Pack de pages acheté : relève le plafond du mois
        await env.db.usage_monthly.update_one({"_id": f"u_solo:{env.usage.period()}"}, {"$inc": {"bonus_pages": 500}})
        assert (await env.usage.consume_pages(SOLO, 200, ref="plan_d"))["counted"] == 200
    run(go())


def test_compte_entreprise_mutualise_les_membres(env):
    async def go():
        await _subscribe(env.db, "u_owner", "cp_professional_monthly")
        await env.db.organizations.insert_one({"org_id": "org1", "owner_user_id": "u_owner"})
        await env.db.users.insert_one({"user_id": "u_owner", "organization_id": "org1", "org_role": "owner"})
        for i in range(4):
            await env.db.users.insert_one({"user_id": f"m{i}", "organization_id": "org1", "org_role": "member"})
        member = {"user_id": "m1"}
        acc = await env.usage.billing_account(member)
        assert acc["account_id"] == "u_owner" and len(acc["member_ids"]) == 5
        with pytest.raises(Exception) as ei:  # 5 lugares déjà utilisés
            await env.usage.check_new_seat({"user_id": "u_owner"})
        assert ei.value.detail["resource"] == "seats"
        await env.usage.consume_pages(member, 10, ref="p1")
        assert (await env.usage.snapshot({"user_id": "u_owner"}))["used"]["pages_monthly"] == 10
    run(go())


def test_stockage(env):
    async def go():
        await _subscribe(env.db, "u_solo", "cp_solo_monthly")
        await env.db.plans_takeoff.insert_one({"plan_id": "a", "user_id": "u_solo", "size_bytes": 10 * cp.GB - 100})
        await env.usage.check_storage(SOLO, 50)
        with pytest.raises(Exception):
            await env.usage.check_storage(SOLO, 200)
    run(go())


# ------------------------------------------------------------------ API (checkout + Enterprise)

def _client(env, user=SOLO):
    from core.rate_limit import limiter
    from core.security import current_user
    app = FastAPI()
    app.state.limiter = limiter
    limiter.reset()
    app.include_router(env.commercial.router, prefix="/api")
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def test_catalogue_public_api(env):
    r = _client(env).get("/api/commercial/plans")
    assert r.status_code == 200
    body = r.json()
    assert body["checkout_open"] is False and body["market"] == "pt"
    assert "price" not in next(p for p in body["plans"] if p["key"] == "enterprise")


def test_checkout_ferme_par_defaut_et_enterprise_refuse(env, monkeypatch):
    c = _client(env)
    monkeypatch.delenv("COMMERCIAL_CHECKOUT_ENABLED", raising=False)
    r = c.post("/api/commercial/checkout", json={"plan": "solo", "interval": "month"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "checkout_not_open"
    monkeypatch.setenv("COMMERCIAL_CHECKOUT_ENABLED", "true")
    r = c.post("/api/commercial/checkout", json={"plan": "enterprise", "interval": "year"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "contact_sales"
    r = c.post("/api/commercial/checkout", json={"plan": "solo", "interval": "week"})
    assert r.status_code == 422
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_abc")
    monkeypatch.delenv("STRIPE_LIVE_ALLOWED", raising=False)
    r = c.post("/api/commercial/checkout", json={"plan": "solo", "interval": "month"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "live_charges_blocked"


def test_checkout_sandbox_prix_serveur_tva_et_origine(env, monkeypatch):
    monkeypatch.setenv("COMMERCIAL_CHECKOUT_ENABLED", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr(env.monetization.stripe, "api_key", "sk_test_abc")
    captured = {}

    async def fake_price(plan):
        captured["price_plan"] = plan

    async def fake_resolve(lookup):
        return SimpleNamespace(id="price_1", unit_amount=captured["price_plan"]["amount_cents"], currency="eur")

    async def fake_customer(user):
        return "cus_1"

    def fake_session(**kw):
        captured["kw"] = kw
        return SimpleNamespace(id="cs_test_1", url="https://checkout.stripe.test/cs_test_1")

    monkeypatch.setattr(env.monetization, "ensure_plan_price", fake_price)
    monkeypatch.setattr(env.monetization, "_resolve_price", fake_resolve)
    monkeypatch.setattr(env.monetization, "get_or_create_customer", fake_customer)
    monkeypatch.setattr(env.monetization.stripe.checkout.Session, "create", staticmethod(fake_session))

    async def seed():  # une tentative de falsification du montant en DB est corrigée
        doc = next(d for d in cp.db_plan_docs() if d["plan_id"] == "cp_business_yearly")
        await env.db.plans.insert_one({**doc, "amount_cents": 100})
    run(seed())
    r = _client(env).post("/api/commercial/checkout",
                          json={"plan": "business", "interval": "year", "origin_url": "https://evil.example"})
    assert r.status_code == 200, r.text
    kw = captured["kw"]
    assert captured["price_plan"]["amount_cents"] == 610980
    assert kw["automatic_tax"] == {"enabled": True} and kw["tax_id_collection"] == {"enabled": True}
    assert kw["success_url"].startswith("https://construpilot.pt/")
    assert kw["metadata"]["plan_id"] == "cp_business_yearly"

    async def audit():
        tx = await env.db.payment_transactions.find_one({"session_id": "cs_test_1"})
        assert tx["amount_cents"] == 610980
        assert await env.db.billing_audit.count_documents({"action": "checkout.created"}) == 1
    run(audit())


def test_checkout_refuse_second_abonnement(env, monkeypatch):
    monkeypatch.setenv("COMMERCIAL_CHECKOUT_ENABLED", "true")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc")
    run(_subscribe(env.db, "u_solo", "cp_solo_monthly", stripe_subscription_id="sub_1"))
    r = _client(env).post("/api/commercial/checkout", json={"plan": "business", "interval": "month"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "use_portal"


LEAD = {"name": "Ana Silva", "company": "Construções Norte", "email": "ana@cnorte.pt", "phone": "+351 912 345 678",
        "country": "Portugal", "employees": "51-200", "projects": "100-500", "features": ["erp", "teams", "hack"],
        "message": "<script>alert(1)</script> Precisamos de ERP.", "consent": True, "lang": "pt",
        "elapsed_ms": 12000, "submission_id": "s1"}


def test_formulaire_enterprise(env, monkeypatch):
    sent = []

    async def fake_send(to, subject, html, reply_to=None, from_name=None):
        sent.append((to, subject, html, reply_to))
        return {"ok": True}
    from engines import emailer
    monkeypatch.setattr(emailer, "send_email", fake_send)
    c = _client(env)
    r = c.post("/api/commercial/enterprise-lead", json=LEAD)
    assert r.status_code == 200 and r.json()["ok"] and "equipa comercial" in r.json()["message"]
    assert len(sent) == 1 and sent[0][0] == "info@construpilot.pt" and sent[0][3] == "ana@cnorte.pt"
    assert "<script>" not in sent[0][2] and "&lt;script&gt;" in sent[0][2]
    # Double clic / renvoi : pas de doublon ni de seconde notification
    r2 = c.post("/api/commercial/enterprise-lead", json=LEAD)
    assert r2.json()["duplicate"] is True and len(sent) == 1

    async def check():
        docs = await env.db.commercial_leads.find({}).to_list(10)
        assert len(docs) == 1 and docs[0]["features"] == ["erp", "teams"]
        assert docs[0]["consent"]["given"] and docs[0]["professional_email"] and docs[0]["notified"]
        assert docs[0]["retain_until"]
    run(check())


def test_formulaire_enterprise_validation_et_antispam(env, monkeypatch):
    from engines import emailer

    async def boom(*a, **k):
        raise AssertionError("aucun e-mail ne doit partir")
    monkeypatch.setattr(emailer, "send_email", boom)
    c = _client(env)
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "consent": False}).status_code == 422
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "email": "x"}).status_code == 422
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "phone": "abc"}).status_code == 422
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "employees": "9999"}).status_code == 422
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "website": "http://spam"}).json()["ok"]
    assert c.post("/api/commercial/enterprise-lead", json={**LEAD, "elapsed_ms": 300}).json()["ok"]
    assert run(env.db.commercial_leads.count_documents({})) == 0


def test_formulaire_enterprise_limite_de_debit(env, monkeypatch):
    from engines import emailer

    async def ok(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(emailer, "send_email", ok)
    c = _client(env)
    codes = [c.post("/api/commercial/enterprise-lead",
                    json={**LEAD, "email": f"a{i}@cnorte.pt", "submission_id": f"s{i}"}).status_code for i in range(7)]
    assert codes[:5] == [200] * 5 and 429 in codes[5:]


# ------------------------------------------------------------------ webhooks Stripe

def _event(env, monkeypatch, evt):
    monkeypatch.setattr(env.monetization.stripe.Webhook, "construct_event", staticmethod(lambda p, s, k: evt))
    return run(env.monetization.handle_webhook(b"{}", "sig"))


def test_webhook_idempotent_et_echec_de_paiement(env, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    run(_subscribe(env.db, "u_solo", "cp_solo_monthly", stripe_subscription_id="sub_9"))
    evt = {"id": "evt_1", "type": "invoice.payment_failed", "data": {"object": {"subscription": "sub_9"}}}
    assert _event(env, monkeypatch, evt)["received"]
    assert _event(env, monkeypatch, evt).get("duplicate") is True
    # Relances Stripe en cours : l'accès est conservé (statut past_due visible)
    assert run(env.db.entitlements.find_one({"stripe_subscription_id": "sub_9"}))["status"] == "past_due"
    assert run(env.monetization.user_tier("u_solo")) == "pro"
    _event(env, monkeypatch, {"id": "evt_2", "type": "invoice.paid", "data": {"object": {"subscription": "sub_9"}}})
    assert run(env.db.entitlements.find_one({"stripe_subscription_id": "sub_9"}))["status"] == "active"
    # Stripe abandonne les relances → unpaid : accès retiré
    _event(env, monkeypatch, {"id": "evt_4", "type": "customer.subscription.updated",
                              "data": {"object": {"id": "sub_9", "status": "unpaid"}}})
    assert run(env.monetization.user_tier("u_solo")) == "free"


def test_webhook_sans_secret_refuse(env, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.setattr(env.monetization, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(RuntimeError):
        run(env.monetization.handle_webhook(b"{}", "sig"))


def test_webhook_upgrade_depuis_le_portail(env, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    run(_subscribe(env.db, "u_solo", "cp_solo_monthly", stripe_subscription_id="sub_up"))
    run(env.db.users.insert_one({"user_id": "u_solo", "account_type": "pro"}))
    obj = {"id": "sub_up", "status": "active",
           "items": {"data": [{"price": {"metadata": {"plan_id": "cp_business_monthly"}}}]}}
    _event(env, monkeypatch, {"id": "evt_3", "type": "customer.subscription.updated", "data": {"object": obj}})
    ent = run(env.db.entitlements.find_one({"stripe_subscription_id": "sub_up"}))
    assert ent["plan_id"] == "cp_business_monthly" and ent["previous_plan_id"] == "cp_solo_monthly"
    assert run(env.db.users.find_one({"user_id": "u_solo"}))["account_type"] == "pro_business"
    assert run(env.monetization.user_tier("u_solo")) == "pro_business"
    assert run(env.db.billing_audit.count_documents({"action": "plan.changed"})) == 1


def test_webhook_handler_en_echec_libere_l_evenement(env, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    async def boom(obj):
        raise RuntimeError("db down")
    monkeypatch.setitem(env.monetization._WEBHOOK_HANDLERS, "invoice.paid", boom)
    evt = {"id": "evt_x", "type": "invoice.paid", "data": {"object": {"subscription": "s"}}}
    with pytest.raises(RuntimeError):
        _event(env, monkeypatch, evt)
    assert run(env.db.stripe_events.count_documents({"_id": "evt_x"})) == 0
