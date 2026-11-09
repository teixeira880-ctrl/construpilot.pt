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
    # Environnement propre : les variables du serveur (origine, clés Stripe, interrupteurs)
    # ne doivent pas influencer les tests.
    for var in ("FREE_PROMO_MODE", "APP_ORIGIN", "COMMERCIAL_ALLOWED_ORIGINS", "STRIPE_API_KEY",
                "STRIPE_SECRET_KEY", "STRIPE_LIVE_ALLOWED", "COMMERCIAL_CHECKOUT_ENABLED",
                "COMMERCIAL_SALES_EMAIL", "COMMERCIAL_STRIPE_SYNC", "AI_PRICE_TABLE", "FREE_AI_BUDGET_EUR",
                "AI_BUDGET_RATIO_COMMERCIAL", "AI_BUDGET_RATIO_LEGACY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("PLAN_LIMITS_MODE", "enforce")
    monkeypatch.setenv("CP_MARKET", "pt")
    from engines import emailer

    async def _no_mail(*a, **k):
        return {"ok": True}
    monkeypatch.setattr(emailer, "send_email", _no_mail)
    usage_meter._budget_cache.clear()
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


# ------------------------------------------------------------------ garde-fou de coût IA (09/11)

def test_estimation_cout_appel():
    from engines import usage_meter as um
    # Sonnet : 10 000 tokens entrée × 3 $ + 2 000 sortie × 15 $ = 0,06 €
    assert um.estimate_cost_micros("claude-sonnet-5-5", {"calls": 1, "input_tokens": 10_000, "output_tokens": 2_000}) == 60_000
    # Modèle inconnu → prix maximal ; appel sans compteur → plancher
    assert um.estimate_cost_micros("mystery", {"calls": 1, "input_tokens": 1000, "output_tokens": 0}) == 20_000
    assert um.estimate_cost_micros("claude-sonnet-5-5", {"calls": 1}) == um.PER_CALL_FLOOR_MICROS
    assert um.estimate_cost_micros("gpt-image", {"calls": 1, "images": 2}) >= 2 * um.PER_IMAGE_MICROS


def test_budget_ia_bloque_avant_perte(env):
    async def go():
        await _subscribe(env.db, "u_solo", "cp_solo_monthly")
        acc = await env.usage.billing_account(SOLO)
        b = await env.usage.ai_budget(acc)
        assert b["budget_micros"] == int(9900 * 0.97 * 0.70 * 10_000)  # 67,23 € pour 99 €
        await env.db.usage_monthly.update_one({"_id": f"u_solo:{env.usage.period()}"},
                                              {"$set": {"ai_cost_micros": b["budget_micros"]}}, upsert=True)
        env.usage._budget_cache.clear()
        with pytest.raises(Exception) as ei:
            await env.usage.check_ai_budget("u_solo")
        assert ei.value.status_code == 402 and ei.value.detail["resource"] == "ai_budget"
        assert await env.db.usage_events.count_documents({"kind": "ai_budget_reached"}) == 1
        # Pack de pages acheté : budget relevé, appels de nouveau autorisés
        await env.usage.credit_pages_pack("u_solo", 1, "admin")
        await env.usage.check_ai_budget("u_solo")
    run(go())


def test_budget_gratuit_admin_et_historique(env):
    async def go():
        await env.db.users.insert_one({"user_id": "u_free"})
        await env.db.users.insert_one({"user_id": "u_admin", "role": "admin"})
        for uid in ("u_free", "u_admin"):
            await env.db.usage_monthly.update_one({"_id": f"{uid}:{env.usage.period()}"},
                                                  {"$set": {"ai_cost_micros": 50_000_000}}, upsert=True)
        with pytest.raises(Exception):
            await env.usage.check_ai_budget("u_free")      # gratuit : 3 € / mois
        await env.usage.check_ai_budget("u_admin")         # admin : jamais bloqué
        await env.usage.check_ai_budget(None)              # tâche système
        # Client historique Pro Business 249 € : budget = revenu net (équilibre, jamais de perte)
        await env.db.plans.insert_one({"plan_id": "pro_business_monthly", "amount_cents": 24900, "interval": "month"})
        await env.db.entitlements.insert_one({"user_id": "u_old", "plan_id": "pro_business_monthly", "status": "active",
                                              "granted_at": "2026-01-01"})
        b = await env.usage.ai_budget(await env.usage.billing_account({"user_id": "u_old"}))
        assert b["budget_micros"] == int(24900 * 0.97 * 1.0 * 10_000)
    run(go())


def test_note_ai_cost_cumule(env):
    async def go():
        await env.usage.note_ai_cost("u_solo", "claude-sonnet-5-5", {"calls": 1, "input_tokens": 10_000, "output_tokens": 2_000})
        await env.usage.note_ai_cost("u_solo", "claude-sonnet-5-5", {"calls": 1, "input_tokens": 10_000, "output_tokens": 2_000})
        doc = await env.db.usage_monthly.find_one({"_id": f"u_solo:{env.usage.period()}"})
        assert doc["ai_cost_micros"] == 120_000
    run(go())


def test_options_tarifs_et_lugares(env):
    assert cp.ADDONS["extra_seat"]["unit_cents"] == 3900 and "solo" not in cp.ADDONS["extra_seat"]["available_for"]
    assert cp.ADDONS["pages_500"]["unit_cents"] == 7900
    # 500 pages à 0,12 €/page = 60 € < 79 € × 0,97 → marge positive au scénario central
    assert 500 * 0.12 < 79 * 0.97

    async def go():
        await _subscribe(env.db, "u_owner", "cp_professional_monthly")
        await env.db.organizations.insert_one({"org_id": "org1", "owner_user_id": "u_owner", "extra_seats": 2})
        await env.db.users.insert_one({"user_id": "u_owner", "organization_id": "org1"})
        _, limits = await env.usage.account_plan(await env.usage.billing_account({"user_id": "u_owner"}))
        assert limits["seats"] == 7
    run(go())


def test_admin_credit_option_exige_accord(env, monkeypatch):
    from core.security import admin_user
    c = _client(env)
    c.app.dependency_overrides[admin_user] = lambda: {"user_id": "adm", "role": "admin"}
    run(_subscribe(env.db, "u_solo", "cp_solo_monthly"))
    r = c.post("/api/commercial/admin/addons/credit", json={"account_id": "u_solo", "addon": "pages_500", "quantity": 1})
    assert r.status_code == 422  # référence d'accord client obligatoire
    r = c.post("/api/commercial/admin/addons/credit", json={"account_id": "u_solo", "addon": "pages_500", "quantity": 1,
                                                            "customer_consent_ref": "devis D-2026-001"})
    assert r.status_code == 200 and r.json()["bonus_pages"] == 500
    run(env.db.organizations.insert_one({"org_id": "o9", "owner_user_id": "u_solo"}))
    r = c.post("/api/commercial/admin/addons/credit", json={"account_id": "u_solo", "addon": "extra_seat", "quantity": 1,
                                                            "customer_consent_ref": "mail 09/11"})
    assert r.status_code == 400  # Solo : pas d'utilisateur supplémentaire


def test_metering_refuse_avant_appel(env, monkeypatch):
    import sys, types
    if "emergentintegrations.llm.chat" not in sys.modules:
        pkg = types.ModuleType("emergentintegrations"); llm = types.ModuleType("emergentintegrations.llm")
        chat = types.ModuleType("emergentintegrations.llm.chat")
        chat.LlmChat = object; chat.StreamDone = object
        sys.modules.update({"emergentintegrations": pkg, "emergentintegrations.llm": llm, "emergentintegrations.llm.chat": chat})
    from engines.expenses import metering, context
    calls = []

    class Inner:
        async def send_message(self, *a, **k):
            calls.append(1)
            return types.SimpleNamespace(usage={"input_tokens": 100, "output_tokens": 10})

    async def fake_observe(**k):
        return None
    monkeypatch.setattr(metering, "observe", fake_observe)
    m = metering.MeteredChat.__new__(metering.MeteredChat)
    m._inner, m._model, m._feature, m._billing = Inner(), "claude-sonnet-5-5", "t", "other"

    async def go():
        await env.db.users.insert_one({"user_id": "u_free"})
        await env.db.usage_monthly.update_one({"_id": f"u_free:{env.usage.period()}"},
                                              {"$set": {"ai_cost_micros": 99_000_000}}, upsert=True)
        env.usage._budget_cache.clear()
        context.bind({"user_id": "u_free"})
        with pytest.raises(Exception) as ei:
            await m.send_message("x")
        assert ei.value.status_code == 402 and calls == []  # aucun appel payant n'est parti
    run(go())
