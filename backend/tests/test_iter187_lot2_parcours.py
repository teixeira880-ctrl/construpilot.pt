"""Iter 187 — LOT 2 parcours : dossiers chantier, favoris de navigation, demande de devis publique, onboarding réel."""
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PRO_EMAIL, PRO_PWD = "pro@construpilot.fr", "Pro2026!"
COL_EMAIL, COL_PWD = "collegue@construpilot.fr", "Collegue2026!"
CLI_EMAIL, CLI_PWD = "client@construpilot.fr", "Client2026!"
SLUG = "marc-btp-pro"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pro():
    return _login(PRO_EMAIL, PRO_PWD)


@pytest.fixture(scope="module")
def collegue():
    return _login(COL_EMAIL, COL_PWD)


@pytest.fixture(scope="module")
def particulier():
    return _login(CLI_EMAIL, CLI_PWD)


@pytest.fixture(scope="module")
def client_id(pro):
    r = pro.post(f"{BASE_URL}/api/clients", json={"first_name": "Iter187", "last_name": "Client", "email": f"iter187-{uuid.uuid4().hex[:6]}@test.fr",
                                                   "address": "1 rue du Test", "postal_code": "75001", "city": "Paris"})
    assert r.status_code == 200, r.text
    cid = r.json()["client_id"]
    yield cid
    pro.delete(f"{BASE_URL}/api/clients/{cid}")


@pytest.fixture(scope="module")
def chantier(pro, client_id):
    r = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "Iter187 Villa", "client_id": client_id})
    assert r.status_code == 200, r.text
    c = r.json()
    yield c
    pro.delete(f"{BASE_URL}/api/chantiers/{c['chantier_id']}")


class TestChantiers:
    def test_create_copies_client_address_and_name(self, chantier):
        assert chantier["chantier_id"].startswith("cht_")
        assert chantier["client_name"] == "Iter187 Client"
        assert chantier["city"] == "Paris" and chantier["postal_code"] == "75001"
        assert chantier["status"] == "en_cours"

    def test_unknown_client_404(self, pro):
        r = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "X", "client_id": "cli_doesnotexist"})
        assert r.status_code == 404

    def test_list_with_counts_and_filters(self, pro, chantier):
        r = pro.get(f"{BASE_URL}/api/chantiers", params={"q": "Iter187"})
        assert r.status_code == 200
        items = [c for c in r.json()["chantiers"] if c["chantier_id"] == chantier["chantier_id"]]
        assert len(items) == 1 and "counts" in items[0]
        r = pro.get(f"{BASE_URL}/api/chantiers", params={"status": "termine"})
        assert all(c["status"] == "termine" for c in r.json()["chantiers"])

    def test_document_created_with_chantier_id_appears_in_dossier(self, pro, chantier, client_id):
        body = {"doc_type": "quote", "title": "Devis iter187", "client_id": client_id, "chantier_id": chantier["chantier_id"],
                "lines": [{"designation": "Ligne", "qty": 2, "unit": "u", "unit_price_ht": 50, "vat_rate": 20}]}
        r = pro.post(f"{BASE_URL}/api/documents", json=body)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["chantier_id"] == chantier["chantier_id"]
        d = pro.get(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}").json()
        assert any(x["doc_id"] == doc["doc_id"] for x in d["documents"])
        assert d["client"]["client_id"] == client_id
        assert d["kpis"]["quotes"] >= 1
        assert "lines" not in d["documents"][0]
        pro.delete(f"{BASE_URL}/api/documents/{doc['doc_id']}")

    def test_foreign_chantier_id_ignored_on_document(self, pro, collegue, chantier):
        body = {"doc_type": "quote", "title": "Devis collègue", "chantier_id": chantier["chantier_id"],
                "lines": [{"designation": "L", "qty": 1, "unit": "u", "unit_price_ht": 10, "vat_rate": 20}]}
        r = collegue.post(f"{BASE_URL}/api/documents", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["chantier_id"] is None
        collegue.delete(f"{BASE_URL}/api/documents/{r.json()['doc_id']}")

    def test_attach_detach_document(self, pro, chantier):
        r = pro.post(f"{BASE_URL}/api/documents", json={"doc_type": "quote", "title": "Libre", "lines": []})
        doc_id = r.json()["doc_id"]
        assert r.json().get("chantier_id") is None
        a = pro.post(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}/attach", json={"kind": "document", "ref_id": doc_id})
        assert a.status_code == 200, a.text
        assert pro.get(f"{BASE_URL}/api/documents/{doc_id}").json()["chantier_id"] == chantier["chantier_id"]
        d = pro.post(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}/detach", json={"kind": "document", "ref_id": doc_id})
        assert d.status_code == 200
        assert pro.get(f"{BASE_URL}/api/documents/{doc_id}").json().get("chantier_id") is None
        bad = pro.post(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}/attach", json={"kind": "plan", "ref_id": "plan_nope"})
        assert bad.status_code == 404
        pro.delete(f"{BASE_URL}/api/documents/{doc_id}")

    def test_isolation_between_accounts(self, collegue, chantier):
        assert collegue.get(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}").status_code == 404
        assert collegue.put(f"{BASE_URL}/api/chantiers/{chantier['chantier_id']}", json={"name": "Hack"}).status_code == 404

    def test_particulier_blocked(self, particulier):
        assert particulier.get(f"{BASE_URL}/api/chantiers").status_code in (401, 403)

    def test_update_and_delete_unlinks(self, pro, client_id):
        c = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "Temp 187", "client_id": client_id}).json()
        u = pro.put(f"{BASE_URL}/api/chantiers/{c['chantier_id']}", json={"name": "Temp 187 bis", "status": "termine", "client_id": None})
        assert u.status_code == 200 and u.json()["status"] == "termine" and u.json()["client_name"] == ""
        doc = pro.post(f"{BASE_URL}/api/documents", json={"doc_type": "quote", "title": "T", "chantier_id": c["chantier_id"], "lines": []}).json()
        assert doc["chantier_id"] == c["chantier_id"]
        assert pro.delete(f"{BASE_URL}/api/chantiers/{c['chantier_id']}").status_code == 200
        assert pro.get(f"{BASE_URL}/api/documents/{doc['doc_id']}").json().get("chantier_id") is None
        assert pro.get(f"{BASE_URL}/api/chantiers/{c['chantier_id']}").status_code == 404
        pro.delete(f"{BASE_URL}/api/documents/{doc['doc_id']}")


class TestNavFavorites:
    def test_put_and_me(self, pro):
        r = pro.put(f"{BASE_URL}/api/auth/nav-favorites", json={"favorites": ["/chantiers", "/devis", "/chantiers", "notapath"]})
        assert r.status_code == 200
        assert r.json()["nav_favorites"] == ["/chantiers", "/devis"]
        assert pro.get(f"{BASE_URL}/api/auth/me").json()["nav_favorites"] == ["/chantiers", "/devis"]
        pro.put(f"{BASE_URL}/api/auth/nav-favorites", json={"favorites": []})
        assert pro.get(f"{BASE_URL}/api/auth/me").json()["nav_favorites"] == []


class TestPublicQuoteRequest:
    def test_creates_lead_and_client_then_dedupes(self, pro):
        email = f"prospect-{uuid.uuid4().hex[:8]}@example.com"
        body = {"name": "Paul Prospect", "email": email, "phone": "0611223344", "description": "Rénovation cuisine 12 m² avec électricité",
                "postal_code": "92100", "city": "Boulogne"}
        r = requests.post(f"{BASE_URL}/api/public/company/{SLUG}/quote-request", json=body, timeout=30)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["ok"] and d["client_created"] is True
        leads = pro.get(f"{BASE_URL}/api/leads/assigned").json()
        lead = next(x for x in leads if x["lead_id"] == d["lead_id"])
        assert lead["source"] == "company_page" and lead["is_mine"] is True and lead["department"] == "92"
        clients = pro.get(f"{BASE_URL}/api/clients", params={"q": email}).json()["clients"]
        assert len(clients) == 1 and clients[0]["source"] == "company_page" and clients[0]["first_name"] == "Paul"
        r2 = requests.post(f"{BASE_URL}/api/public/company/{SLUG}/quote-request", json={**body, "email": email.upper()}, timeout=30)
        assert r2.status_code == 201 and r2.json()["client_created"] is False
        assert len(pro.get(f"{BASE_URL}/api/clients", params={"q": email}).json()["clients"]) == 1
        notifs = pro.get(f"{BASE_URL}/api/notifications").json()
        items = notifs if isinstance(notifs, list) else notifs.get("items") or notifs.get("notifications") or []
        assert any(n.get("type") == "company_page_lead" for n in items)
        pro.delete(f"{BASE_URL}/api/clients/{clients[0]['client_id']}")

    def test_validation_and_unknown_slug(self):
        r = requests.post(f"{BASE_URL}/api/public/company/{SLUG}/quote-request", json={"name": "A", "email": "bad", "description": "court"}, timeout=30)
        assert r.status_code == 422
        r = requests.post(f"{BASE_URL}/api/public/company/does-not-exist/quote-request",
                          json={"name": "Paul Prospect", "email": "p@example.com", "description": "Rénovation cuisine complète"}, timeout=30)
        assert r.status_code == 404

    def test_honeypot_silently_ignored(self, pro):
        email = f"bot-{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/public/company/{SLUG}/quote-request",
                          json={"name": "Robot Spam", "email": email, "description": "spam spam spam spam", "website": "http://spam"}, timeout=30)
        assert r.status_code == 201 and "lead_id" not in r.json()
        assert pro.get(f"{BASE_URL}/api/clients", params={"q": email}).json()["count"] == 0


class TestOnboarding:
    def test_status_real_data(self, pro, chantier):
        r = pro.get(f"{BASE_URL}/api/onboarding/status")
        assert r.status_code == 200
        d = r.json()
        assert set(d) >= {"client", "chantier", "plan", "quote", "project", "page_published", "identity"}
        assert d["client"] is True and d["chantier"] is True and d["quote"] is True and d["page_published"] is True and d["identity"] is True

    def test_status_particulier(self, particulier):
        d = particulier.get(f"{BASE_URL}/api/onboarding/status").json()
        assert d["chantier"] is False and isinstance(d["project"], bool)
